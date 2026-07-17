"""FSO operation serialization, transmission preparation, and reassembly."""

from __future__ import annotations

import os
import struct
from collections.abc import Callable
from dataclasses import dataclass

from .coding import ReedSolomonCodec, Shard
from .crypto import EnvelopeCipher
from .types import CODE_FUNCTIONS, FUNCTION_CODES, Operation, ScheduleDecision

INNER_MAGIC = b"OP01"
INNER_HEADER = struct.Struct("!4sBI")


def serialize_operation(operation: Operation) -> bytes:
    return INNER_HEADER.pack(
        INNER_MAGIC, FUNCTION_CODES[operation.function], len(operation.payload)
    ) + operation.payload


def deserialize_operation(payload: bytes) -> Operation:
    if len(payload) < INNER_HEADER.size:
        raise ValueError("truncated operation")
    magic, function_code, payload_length = INNER_HEADER.unpack_from(payload)
    if magic != INNER_MAGIC or function_code not in CODE_FUNCTIONS:
        raise ValueError("invalid operation header")
    body = payload[INNER_HEADER.size :]
    if len(body) != payload_length:
        raise ValueError("operation length mismatch")
    return Operation(CODE_FUNCTIONS[function_code], body, deadline_ms=1.0)


@dataclass(frozen=True)
class PreparedTransmission:
    message_id: bytes
    decision: ScheduleDecision
    packets: tuple[bytes, ...]


@dataclass(frozen=True)
class ReceiveResult:
    status: str
    message_id: bytes
    shard_index: int
    operation: Operation | None = None


class FSOSender:
    def __init__(
        self,
        cipher: EnvelopeCipher,
        *,
        message_id_source: Callable[[int], bytes] = os.urandom,
    ) -> None:
        self.cipher = cipher
        self._message_id_source = message_id_source

    def prepare(self, operation: Operation, decision: ScheduleDecision) -> PreparedTransmission:
        if operation.function != decision.function:
            raise ValueError("operation and schedule function differ")
        message_id = self._message_id_source(16)
        if len(message_id) != 16:
            raise ValueError("message ID source must return exactly 16 bytes")
        codec = ReedSolomonCodec(decision.threshold, decision.total_shards)
        shards = codec.encode(serialize_operation(operation), message_id)
        packets = tuple(self.cipher.seal(shard) for shard in shards)
        return PreparedTransmission(message_id, decision, packets)


class FSOReceiver:
    def __init__(self, cipher: EnvelopeCipher, *, completed_window: int = 4096) -> None:
        self.cipher = cipher
        self.buffers: dict[bytes, dict[int, Shard]] = {}
        self.completed: dict[bytes, Operation] = {}
        self.completed_order: list[bytes] = []
        self.completed_window = completed_window

    def discard(self, message_id: bytes) -> bool:
        """Expire an incomplete message after its application deadline."""

        return self.buffers.pop(message_id, None) is not None

    def expire_incomplete(self) -> int:
        """Expire every incomplete coded message at a controlled deadline boundary."""

        count = len(self.buffers)
        self.buffers.clear()
        return count

    def ingest(self, packet: bytes) -> ReceiveResult:
        public = self.cipher.peek(packet)
        if public.message_id in self.completed:
            return ReceiveResult("replay", public.message_id, public.index)
        shard = self.cipher.open(packet)
        buffer = self.buffers.setdefault(shard.message_id, {})
        if shard.index in buffer:
            return ReceiveResult("duplicate", shard.message_id, shard.index)
        if buffer:
            first = next(iter(buffer.values()))
            if (
                shard.threshold != first.threshold
                or shard.total != first.total
                or shard.original_length != first.original_length
            ):
                raise ValueError("inconsistent shard set")
        buffer[shard.index] = shard
        if len(buffer) < shard.threshold:
            return ReceiveResult("buffered", shard.message_id, shard.index)
        codec = ReedSolomonCodec(shard.threshold, shard.total)
        operation = deserialize_operation(codec.decode(list(buffer.values())))
        self.completed[shard.message_id] = operation
        self.completed_order.append(shard.message_id)
        del self.buffers[shard.message_id]
        while len(self.completed_order) > self.completed_window:
            expired = self.completed_order.pop(0)
            self.completed.pop(expired, None)
        return ReceiveResult("complete", shard.message_id, shard.index, operation)
