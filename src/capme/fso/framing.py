"""Bounded datagram fragmentation for authenticated FSO envelopes."""

from __future__ import annotations

import struct
from collections import OrderedDict
from dataclasses import dataclass

from .crypto import EnvelopeCipher, EnvelopeError

FRAGMENT_MAGIC = b"FG01"
FRAGMENT_HEADER = struct.Struct("!4s16sBHH")
MAX_FRAGMENTS = 255


class FramingError(ValueError):
    pass


@dataclass(frozen=True)
class FragmentHeader:
    message_id: bytes
    shard_index: int
    part: int
    total: int


@dataclass(frozen=True)
class ReassemblyResult:
    status: str
    header: FragmentHeader
    packet: bytes | None = None


def peek_fragment(datagram: bytes) -> FragmentHeader:
    if len(datagram) <= FRAGMENT_HEADER.size:
        raise FramingError("truncated fragment")
    magic, message_id, shard_index, part, total = FRAGMENT_HEADER.unpack_from(datagram)
    if magic != FRAGMENT_MAGIC:
        raise FramingError("wrong fragment magic")
    if not 1 <= total <= MAX_FRAGMENTS or part >= total:
        raise FramingError("invalid fragment dimensions")
    return FragmentHeader(message_id, shard_index, part, total)


def fragment_envelope(packet: bytes, *, max_fragment_data: int) -> tuple[bytes, ...]:
    if max_fragment_data <= 0:
        raise ValueError("max_fragment_data must be positive")
    try:
        public = EnvelopeCipher.peek(packet)
    except EnvelopeError as error:
        raise FramingError("cannot fragment an invalid envelope") from error
    chunks = [
        packet[offset : offset + max_fragment_data]
        for offset in range(0, len(packet), max_fragment_data)
    ]
    if not chunks or len(chunks) > MAX_FRAGMENTS:
        raise FramingError("envelope exceeds the fragment-count limit")
    return tuple(
        FRAGMENT_HEADER.pack(
            FRAGMENT_MAGIC,
            public.message_id,
            public.index,
            part,
            len(chunks),
        )
        + chunk
        for part, chunk in enumerate(chunks)
    )


class FragmentReassembler:
    """Duplicate-tolerant bounded reassembly keyed by peer, message, and shard."""

    def __init__(
        self, *, max_inflight: int = 4096, completed_window: int = 4096
    ) -> None:
        if max_inflight <= 0 or completed_window <= 0:
            raise ValueError("reassembly bounds must be positive")
        self.max_inflight = max_inflight
        self.completed_window = completed_window
        self._buffers: OrderedDict[
            tuple[str, bytes, int], tuple[int, dict[int, bytes]]
        ] = OrderedDict()
        self._completed: OrderedDict[tuple[str, bytes, int], None] = OrderedDict()
        self.evictions = 0

    @property
    def inflight(self) -> int:
        return len(self._buffers)

    def discard_message(self, message_id: bytes) -> int:
        keys = [key for key in self._buffers if key[1] == message_id]
        for key in keys:
            self._buffers.pop(key, None)
        return len(keys)

    def expire_incomplete(self) -> int:
        """Expire every incomplete fragment set at a controlled deadline boundary."""

        count = len(self._buffers)
        self._buffers.clear()
        return count

    def ingest(self, datagram: bytes, *, peer: str) -> ReassemblyResult:
        header = peek_fragment(datagram)
        key = (peer, header.message_id, header.shard_index)
        if key in self._completed:
            self._completed.move_to_end(key)
            return ReassemblyResult("replay", header)
        if key not in self._buffers and len(self._buffers) >= self.max_inflight:
            self._buffers.popitem(last=False)
            self.evictions += 1
        declared_total, fragments = self._buffers.setdefault(
            key, (header.total, {})
        )
        if declared_total != header.total:
            self._buffers.pop(key, None)
            raise FramingError("inconsistent fragment count")
        self._buffers.move_to_end(key)
        if header.part in fragments:
            return ReassemblyResult("duplicate", header)
        fragments[header.part] = datagram[FRAGMENT_HEADER.size :]
        if len(fragments) != header.total:
            return ReassemblyResult("buffered", header)
        try:
            packet = b"".join(fragments[index] for index in range(header.total))
        except KeyError as error:
            self._buffers.pop(key, None)
            raise FramingError("fragment set is incomplete") from error
        self._buffers.pop(key, None)
        self._completed[key] = None
        while len(self._completed) > self.completed_window:
            self._completed.popitem(last=False)
        return ReassemblyResult("complete", header, packet)
