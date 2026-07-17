"""Closed multi-host packet testbed for the FSO research prototype.

The roles in this module are intended to run only on an orchestrator-created
Docker network marked ``Internal``.  They have no generic destination option:
the sender may contact only configured carrier aliases and every resolved
destination must be loopback, RFC 1918, or IPv6 unique-local address space.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import ipaddress
import json
import math
import os
import random
import resource
import signal
import socket
import time
from collections import Counter
from pathlib import Path
from typing import Any

from capme.io import write_csv, write_json
from capme.model import WORKLOADS

from .crypto import AckAuthenticator, EnvelopeCipher, EnvelopeError
from .framing import FragmentReassembler, FramingError, fragment_envelope, peek_fragment
from .protocol import FSOReceiver, FSOSender
from .scheduler import build_scheduler
from .testbed import _dispatch, _profile
from .types import FUNCTIONS, Operation

CONTROL_MAGIC = b"CAPME-LAB-CONTROL-v1|"
CONTROL_TAG_BYTES = 16
MAX_CONTROL_BYTES = 16_384

_RFC1918 = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_IPV6_ULA = ipaddress.ip_network("fc00::/7")


def is_closed_lab_address(value: str) -> bool:
    """Return whether a literal address is permitted by the closed-lab policy."""

    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in network for network in _RFC1918)
    return address in _IPV6_ULA


def resolve_closed_lab_host(host: str, port: int) -> tuple[str, ...]:
    """Resolve a configured alias and reject every non-laboratory address."""

    if not host or not 1 <= port <= 65_535:
        raise ValueError("closed-lab destination requires a host and valid port")
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except socket.gaierror as error:
        raise ValueError(f"cannot resolve closed-lab host: {host}") from error
    addresses = tuple(sorted({str(record[4][0]) for record in records}))
    if not addresses:
        raise ValueError(f"closed-lab host resolved to no addresses: {host}")
    rejected = [address for address in addresses if not is_closed_lab_address(address)]
    if rejected:
        raise ValueError(
            f"external destination rejected by multi-host testbed: {host} -> "
            + ", ".join(rejected)
        )
    return addresses


def _session_key(seed: int) -> bytes:
    return hashlib.sha256(f"capme-multihost-lab-v1|{seed}".encode()).digest()


def encode_control(key: bytes, record: dict[str, object]) -> bytes:
    body = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    tag = hmac.new(key, CONTROL_MAGIC + body, hashlib.sha256).digest()[:CONTROL_TAG_BYTES]
    packet = CONTROL_MAGIC + tag + body
    if len(packet) > MAX_CONTROL_BYTES:
        raise ValueError("laboratory control record is too large")
    return packet


def decode_control(key: bytes, packet: bytes) -> dict[str, object]:
    if not packet.startswith(CONTROL_MAGIC):
        raise ValueError("wrong laboratory control magic")
    if len(packet) < len(CONTROL_MAGIC) + CONTROL_TAG_BYTES + 2:
        raise ValueError("truncated laboratory control record")
    if len(packet) > MAX_CONTROL_BYTES:
        raise ValueError("laboratory control record is too large")
    offset = len(CONTROL_MAGIC)
    tag = packet[offset : offset + CONTROL_TAG_BYTES]
    body = packet[offset + CONTROL_TAG_BYTES :]
    expected = hmac.new(key, CONTROL_MAGIC + body, hashlib.sha256).digest()[
        :CONTROL_TAG_BYTES
    ]
    if not hmac.compare_digest(tag, expected):
        raise ValueError("laboratory control authentication failed")
    decoded = json.loads(body)
    if not isinstance(decoded, dict):
        raise ValueError("laboratory control record must be an object")
    return decoded


def _rate(value: object, name: str) -> float:
    rate = float(value)
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"{name} must lie in [0, 1]")
    return rate


def validate_multihost_config(config: dict[str, Any]) -> None:
    if config.get("closed_world") is not True:
        raise ValueError("closed_world must be true")
    if config.get("docker_internal_network_required") is not True:
        raise ValueError("docker_internal_network_required must be true")
    if config.get("strict_trust") is not True:
        raise ValueError("strict_trust must be true")
    if config.get("scheduler_strategy") != "fso_no_feedback":
        raise ValueError("multi-host scheduler_strategy must be fso_no_feedback")
    if int(config.get("schema_version", 0)) != 1:
        raise ValueError("unsupported multi-host schema version")
    if int(config.get("operations_per_function_per_phase", 0)) <= 0:
        raise ValueError("operations_per_function_per_phase must be positive")
    if int(config.get("max_fragment_data", 0)) <= 0:
        raise ValueError("max_fragment_data must be positive")
    if not 0 <= float(config.get("phase_gc_grace_ms", -1)) <= 5_000:
        raise ValueError("phase_gc_grace_ms must lie in [0, 5000]")
    receiver = config.get("receiver")
    if not isinstance(receiver, dict) or not receiver.get("host"):
        raise ValueError("receiver host is required")
    port = int(receiver.get("port", 0))
    if not 1 <= port <= 65_535:
        raise ValueError("receiver port is invalid")
    lanes = config.get("lanes")
    if not isinstance(lanes, list) or len(lanes) < 2:
        raise ValueError("at least two carrier lanes are required")
    names = [str(row.get("name", "")) for row in lanes]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("carrier lane names must be non-empty and unique")
    for row in lanes:
        if not row.get("proxy_host"):
            raise ValueError("every carrier lane requires a proxy_host")
        proxy_port = int(row.get("proxy_port", 0))
        if not 1 <= proxy_port <= 65_535:
            raise ValueError("carrier proxy port is invalid")
        _rate(row.get("loss_rate", 0.0), "loss_rate")
        if float(row.get("latency_ms", 0.0)) <= 0:
            raise ValueError("lane latency_ms must be positive")
    phases = config.get("phases")
    if not isinstance(phases, list) or len(phases) < 2:
        raise ValueError("at least two declared impairment phases are required")
    phase_names: set[str] = set()
    for phase in phases:
        phase_name = str(phase.get("name", ""))
        if not phase_name or phase_name in phase_names:
            raise ValueError("phase names must be non-empty and unique")
        phase_names.add(phase_name)
        impairments = phase.get("lanes")
        if not isinstance(impairments, dict) or set(impairments) != set(names):
            raise ValueError(f"phase {phase_name} must declare every carrier lane")
        for lane_name, impairment in impairments.items():
            if not isinstance(impairment, dict):
                raise ValueError(f"phase {phase_name}/{lane_name} is not an object")
            for key in (
                "data_loss",
                "ack_loss",
                "data_corruption",
                "ack_corruption",
                "data_duplication",
            ):
                _rate(impairment.get(key, 0.0), key)
            if float(impairment.get("latency_ms", 0.0)) < 0:
                raise ValueError("phase latency_ms cannot be negative")
            if float(impairment.get("jitter_ms", 0.0)) < 0:
                raise ValueError("phase jitter_ms cannot be negative")


def _load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("multi-host configuration must be an object")
    validate_multihost_config(config)
    return config


def _control_reply(
    key: bytes, request: dict[str, object], kind: str, **values: object
) -> bytes:
    return encode_control(
        key,
        {"kind": kind, "token": request.get("token", ""), **values},
    )


class ReceiverProtocol(asyncio.DatagramProtocol):
    def __init__(self, key: bytes) -> None:
        self.key = key
        self.receiver = FSOReceiver(EnvelopeCipher(key))
        self.ack = AckAuthenticator(key)
        self.reassembler = FragmentReassembler()
        self.transport: asyncio.DatagramTransport | None = None
        self.counters: Counter[str] = Counter()
        self.functions: Counter[str] = Counter()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def _stats(self) -> dict[str, object]:
        return {
            "datagrams_received": self.counters["datagrams_received"],
            "fragments_completed": self.counters["fragments_completed"],
            "operations_completed": len(self.receiver.completed),
            "function_completions": dict(sorted(self.functions.items())),
            "fragment_failures": self.counters["fragment_failures"],
            "envelope_auth_failures": self.counters["envelope_auth_failures"],
            "expired_fragment_sets": self.counters["expired_fragment_sets"],
            "expired_coded_messages": self.counters["expired_coded_messages"],
            "reassembly_evictions": self.reassembler.evictions,
            "reassembly_inflight": self.reassembler.inflight,
            "coded_messages_inflight": len(self.receiver.buffers),
        }

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.counters["datagrams_received"] += 1
        if data.startswith(CONTROL_MAGIC):
            try:
                request = decode_control(self.key, data)
            except (ValueError, json.JSONDecodeError):
                self.counters["control_auth_failures"] += 1
                return
            if request.get("kind") == "receiver_stats" and self.transport is not None:
                self.transport.sendto(
                    _control_reply(self.key, request, "receiver_stats_reply", stats=self._stats()),
                    addr,
                )
            elif request.get("kind") == "receiver_gc" and self.transport is not None:
                expired_fragments = self.reassembler.expire_incomplete()
                expired_messages = self.receiver.expire_incomplete()
                self.counters["expired_fragment_sets"] += expired_fragments
                self.counters["expired_coded_messages"] += expired_messages
                self.transport.sendto(
                    _control_reply(
                        self.key,
                        request,
                        "receiver_gc_reply",
                        expired_fragment_sets=expired_fragments,
                        expired_coded_messages=expired_messages,
                        stats=self._stats(),
                    ),
                    addr,
                )
            return
        try:
            reassembled = self.reassembler.ingest(data, peer=f"{addr[0]}:{addr[1]}")
        except FramingError:
            self.counters["fragment_failures"] += 1
            return
        if reassembled.status != "complete" or reassembled.packet is None:
            return
        self.counters["fragments_completed"] += 1
        try:
            result = self.receiver.ingest(reassembled.packet)
        except (EnvelopeError, ValueError):
            self.counters["envelope_auth_failures"] += 1
            return
        status = 1
        if result.status == "complete" and result.operation is not None:
            status = 2
            self.functions[result.operation.function] += 1
        elif result.status == "replay":
            status = 3
        if self.transport is not None:
            self.transport.sendto(
                self.ack.seal(result.message_id, result.shard_index, status=status), addr
            )


class CarrierProxyProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        *,
        key: bytes,
        lane: str,
        phases: dict[str, dict[str, Any]],
        receiver: tuple[str, int],
        receiver_addresses: set[str],
        seed: int,
    ) -> None:
        self.key = key
        self.lane = lane
        self.phases = phases
        self.phase = next(iter(phases))
        self.receiver = receiver
        self.receiver_addresses = receiver_addresses
        self.rng = random.Random(seed)
        self.transport: asyncio.DatagramTransport | None = None
        self.client_addr: tuple[str, int] | None = None
        self.counters: Counter[str] = Counter()
        self.phase_counters: dict[str, Counter[str]] = {
            name: Counter() for name in phases
        }

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def _count(self, name: str) -> None:
        self.counters[name] += 1
        self.phase_counters[self.phase][name] += 1

    def _stats(self) -> dict[str, object]:
        return {
            "lane": self.lane,
            "active_phase": self.phase,
            "counters": dict(sorted(self.counters.items())),
            "phase_counters": {
                phase: dict(sorted(values.items()))
                for phase, values in self.phase_counters.items()
            },
        }

    def _delay(self, impairment: dict[str, Any]) -> float:
        latency = float(impairment["latency_ms"])
        jitter = float(impairment["jitter_ms"])
        return max(0.0, self.rng.gauss(latency, jitter)) / 1000.0

    @staticmethod
    def _corrupt(data: bytes) -> bytes:
        if not data:
            return data
        changed = bytearray(data)
        changed[-1] ^= 0x01
        return bytes(changed)

    def _send_later(self, data: bytes, destination: tuple[str, int], delay: float) -> None:
        if self.transport is None:
            return
        asyncio.get_running_loop().call_later(delay, self.transport.sendto, data, destination)

    def _handle_control(self, data: bytes, addr: tuple[str, int], from_receiver: bool) -> None:
        if self.transport is None:
            return
        try:
            request = decode_control(self.key, data)
        except (ValueError, json.JSONDecodeError):
            self._count("control_auth_failures")
            return
        kind = request.get("kind")
        if from_receiver:
            if self.client_addr is not None:
                self.transport.sendto(data, self.client_addr)
            return
        self.client_addr = addr
        if kind == "set_phase":
            requested = str(request.get("phase", ""))
            if requested not in self.phases:
                reply = _control_reply(
                    self.key, request, "phase_error", lane=self.lane, phase=requested
                )
            else:
                self.phase = requested
                self.counters["phase_changes"] += 1
                reply = _control_reply(
                    self.key, request, "phase_ack", lane=self.lane, phase=self.phase
                )
            self.transport.sendto(reply, addr)
        elif kind == "proxy_stats":
            self.transport.sendto(
                _control_reply(self.key, request, "proxy_stats_reply", stats=self._stats()),
                addr,
            )
        elif kind in {"receiver_stats", "receiver_gc"}:
            self.transport.sendto(data, self.receiver)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        from_receiver = addr[0] in self.receiver_addresses and addr[1] == self.receiver[1]
        if data.startswith(CONTROL_MAGIC):
            self._handle_control(data, addr, from_receiver)
            return
        impairment = self.phases[self.phase]
        if from_receiver:
            self._count("ack_received")
            if self.client_addr is None:
                self._count("ack_without_client")
                return
            if self.rng.random() < float(impairment["ack_loss"]):
                self._count("ack_dropped")
                return
            if self.rng.random() < float(impairment["ack_corruption"]):
                data = self._corrupt(data)
                self._count("ack_corrupted")
            self._send_later(data, self.client_addr, self._delay(impairment))
            self._count("ack_forwarded")
            return
        self.client_addr = addr
        self._count("data_received")
        try:
            peek_fragment(data)
        except FramingError:
            self._count("invalid_fragment")
            return
        if self.rng.random() < float(impairment["data_loss"]):
            self._count("data_dropped")
            return
        if self.rng.random() < float(impairment["data_corruption"]):
            data = self._corrupt(data)
            self._count("data_corrupted")
        delay = self._delay(impairment)
        self._send_later(data, self.receiver, delay)
        self._count("data_forwarded")
        if self.rng.random() < float(impairment["data_duplication"]):
            self._send_later(data, self.receiver, delay + 0.001)
            self._count("data_duplicated")


class NetworkClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, key: bytes, *, max_fragment_data: int) -> None:
        self.key = key
        self.ack = AckAuthenticator(key)
        self.max_fragment_data = max_fragment_data
        self.transport: asyncio.DatagramTransport | None = None
        self.pending: dict[tuple[bytes, int], asyncio.Future[tuple[float, int]]] = {}
        self.control_pending: dict[str, asyncio.Future[dict[str, object]]] = {}
        self.ack_auth_failures = 0
        self.control_auth_failures = 0
        self._token = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, _addr: tuple[str, int]) -> None:
        if data.startswith(CONTROL_MAGIC):
            try:
                response = decode_control(self.key, data)
            except (ValueError, json.JSONDecodeError):
                self.control_auth_failures += 1
                return
            future = self.control_pending.pop(str(response.get("token", "")), None)
            if future is not None and not future.done():
                future.set_result(response)
            return
        try:
            ack = self.ack.open(data)
        except EnvelopeError:
            self.ack_auth_failures += 1
            return
        future = self.pending.pop((ack.message_id, ack.shard_index), None)
        if future is not None and not future.done():
            future.set_result((time.perf_counter(), ack.status))

    async def control(
        self, record: dict[str, object], *, expected_kind: str, timeout: float = 2.0
    ) -> dict[str, object]:
        if self.transport is None:
            raise RuntimeError("client transport is not connected")
        self._token += 1
        token = f"{os.getpid()}-{self._token}"
        request = {**record, "token": token}
        future = asyncio.get_running_loop().create_future()
        self.control_pending[token] = future
        self.transport.sendto(encode_control(self.key, request))
        try:
            response = await asyncio.wait_for(future, timeout)
        except TimeoutError:
            self.control_pending.pop(token, None)
            raise
        if response.get("kind") != expected_kind:
            raise RuntimeError(
                f"laboratory control expected {expected_kind}, got {response.get('kind')}"
            )
        return response

    async def send(self, packet: bytes, timeout_ms: float) -> tuple[bool, float, int]:
        if self.transport is None:
            raise RuntimeError("client transport is not connected")
        public = EnvelopeCipher.peek(packet)
        key = (public.message_id, public.index)
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        started = time.perf_counter()
        datagrams = fragment_envelope(packet, max_fragment_data=self.max_fragment_data)
        wire_bytes = sum(len(datagram) for datagram in datagrams)
        for datagram in datagrams:
            self.transport.sendto(datagram)
        try:
            completed, _status = await asyncio.wait_for(future, timeout_ms / 1000.0)
            return True, (completed - started) * 1000.0, wire_bytes
        except TimeoutError:
            self.pending.pop(key, None)
            return False, timeout_ms, wire_bytes


class NetworkLane:
    def __init__(
        self,
        name: str,
        transport: asyncio.DatagramTransport,
        protocol: NetworkClientProtocol,
        addresses: tuple[str, ...],
    ) -> None:
        self.name = name
        self.transport = transport
        self.protocol = protocol
        self.addresses = addresses

    async def send(self, packet: bytes, timeout_ms: float) -> tuple[bool, float, int]:
        return await self.protocol.send(packet, timeout_ms)

    def close(self) -> None:
        self.transport.close()


def _at_least_k(probabilities: list[float], threshold: int) -> float:
    distribution = [1.0] + [0.0] * len(probabilities)
    for probability in probabilities:
        updated = [0.0] * len(distribution)
        for successes in range(len(probabilities)):
            updated[successes] += distribution[successes] * (1.0 - probability)
            updated[successes + 1] += distribution[successes] * probability
        distribution = updated
    return sum(distribution[threshold:])


def packet_success_probability(
    *,
    fragment_count: int,
    impairment: dict[str, Any],
    timeout_ms: float,
) -> float:
    """Declared independent-loss approximation used for concordance checks."""

    delivery = (
        (1.0 - float(impairment["data_loss"]))
        * (1.0 - float(impairment["data_corruption"]))
    ) ** fragment_count
    acknowledgement = (1.0 - float(impairment["ack_loss"])) * (
        1.0 - float(impairment["ack_corruption"])
    )
    latency = float(impairment["latency_ms"])
    jitter = float(impairment["jitter_ms"])
    if jitter == 0.0:
        on_time = float(2.0 * latency <= timeout_ms)
    else:
        z = (timeout_ms - 2.0 * latency) / (math.sqrt(2.0) * jitter)
        round_trip_cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        on_time = max(0.0, min(1.0, round_trip_cdf)) ** fragment_count
    return max(0.0, min(1.0, delivery * acknowledgement * on_time))


def prepared_success_probability(
    prepared: Any,
    phase: dict[str, Any],
    *,
    timeout_ms: float,
    max_fragment_data: int,
) -> float:
    probabilities = []
    for lane, packet in zip(
        prepared.decision.lanes, prepared.packets, strict=True
    ):
        fragment_count = len(
            fragment_envelope(packet, max_fragment_data=max_fragment_data)
        )
        probabilities.append(
            packet_success_probability(
                fragment_count=fragment_count,
                impairment=phase["lanes"][lane],
                timeout_ms=timeout_ms,
            )
        )
    return _at_least_k(probabilities, prepared.decision.threshold)


async def _open_client_lane(
    row: dict[str, Any], key: bytes, max_fragment_data: int
) -> NetworkLane:
    host = str(row["proxy_host"])
    port = int(row["proxy_port"])
    addresses = resolve_closed_lab_host(host, port)
    protocol = NetworkClientProtocol(key, max_fragment_data=max_fragment_data)
    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: protocol, remote_addr=(host, port)
    )
    return NetworkLane(
        str(row["name"]), transport, protocol, addresses  # type: ignore[arg-type]
    )


async def run_client(config_path: Path, output_dir: Path) -> dict[str, object]:
    config = _load_config(config_path)
    seed = int(config["seed"])
    key = _session_key(seed)
    max_fragment_data = int(config["max_fragment_data"])
    sender = FSOSender(EnvelopeCipher(key))
    profiles = [_profile(row) for row in config["lanes"]]
    scheduler_strategy = str(config["scheduler_strategy"])
    scheduler = build_scheduler(
        scheduler_strategy,
        profiles,
        strict_trust=True,
        seed=seed,
        correlation_weight=0.35,
    )
    lane_rows = {str(row["name"]): row for row in config["lanes"]}
    lanes: dict[str, NetworkLane] = {}
    for row in config["lanes"]:
        lane = await _open_client_lane(row, key, max_fragment_data)
        lanes[lane.name] = lane

    observations: list[dict[str, object]] = []
    attempted_counts: Counter[str] = Counter()
    phase_summaries: list[dict[str, object]] = []
    process_cpu_start = time.process_time()
    started_wall = time.perf_counter()
    try:
        for phase_index, phase in enumerate(config["phases"]):
            phase_name = str(phase["name"])
            await asyncio.gather(
                *(
                    lane.protocol.control(
                        {"kind": "set_phase", "phase": phase_name},
                        expected_kind="phase_ack",
                    )
                    for lane in lanes.values()
                )
            )
            phase_start = len(observations)
            for function_index, function in enumerate(FUNCTIONS):
                payload_size = int(config["payload_bytes"][function])
                for operation_index in range(
                    int(config["operations_per_function_per_phase"])
                ):
                    payload = bytes(
                        (
                            (
                                phase_index
                                + function_index
                                + operation_index
                                + offset
                            )
                            % 251
                            for offset in range(payload_size)
                        )
                    )
                    operation = Operation(
                        function,
                        payload,
                        WORKLOADS[function].deadline_ms,
                        strict_trust=True,
                    )
                    decision = scheduler.plan(operation)
                    prepared = sender.prepare(operation, decision)
                    timeout_ms = min(
                        float(config["timeout_cap_ms"]),
                        max(
                            float(config["timeout_floor_ms"]),
                            operation.deadline_ms * float(config["timeout_deadline_fraction"]),
                        ),
                    )
                    predicted = prepared_success_probability(
                        prepared,
                        phase,
                        timeout_ms=timeout_ms,
                        max_fragment_data=max_fragment_data,
                    )
                    cpu_start = time.process_time()
                    operation_start = time.perf_counter()
                    results = await _dispatch(prepared, lanes, timeout_ms=timeout_ms)
                    elapsed_ms = (time.perf_counter() - operation_start) * 1000.0
                    cpu_ms = (time.process_time() - cpu_start) * 1000.0
                    acknowledged = sum(int(result[1]) for result in results)
                    success = acknowledged >= decision.threshold
                    for lane_name, lane_success, latency, _wire_bytes in results:
                        attempted_counts[lane_name] += 1
                        scheduler.update(
                            lane_name,
                            function,
                            success=lane_success,
                            latency_ms=latency,
                        )
                    provider_attempts = sum(
                        int(lane_rows[result[0]]["provider_controls_delivery"])
                        for result in results
                    )
                    if provider_attempts:
                        raise AssertionError("strict-trust testbed used a provider-controlled lane")
                    wire_bytes = sum(int(result[3]) for result in results)
                    observations.append(
                        {
                            "phase": phase_name,
                            "function": function,
                            "operation": operation_index,
                            "success": int(success),
                            "predicted_success_probability": predicted,
                            "brier_component": (predicted - int(success)) ** 2,
                            "elapsed_ms": elapsed_ms,
                            "client_cpu_ms": cpu_ms,
                            "client_peak_rss_kib": resource.getrusage(
                                resource.RUSAGE_SELF
                            ).ru_maxrss,
                            "payload_bytes": payload_size,
                            "wire_bytes": wire_bytes,
                            "byte_overhead": wire_bytes / payload_size,
                            "timeout_ms": timeout_ms,
                            "threshold": decision.threshold,
                            "total_shards": decision.total_shards,
                            "dispatch_mode": decision.dispatch_mode,
                            "scheduler_predicted_completion": decision.estimated_completion,
                            "planned_lanes": ";".join(decision.lanes),
                            "attempted_lanes": ";".join(result[0] for result in results),
                            "acked_shards": acknowledged,
                            "provider_controlled_attempts": provider_attempts,
                        }
                    )
            rows = observations[phase_start:]
            phase_summaries.append(
                {
                    "phase": phase_name,
                    "operations": len(rows),
                    "availability": sum(int(row["success"]) for row in rows) / len(rows),
                    "mean_predicted_success": sum(
                        float(row["predicted_success_probability"]) for row in rows
                    )
                    / len(rows),
                    "brier_score": sum(float(row["brier_component"]) for row in rows)
                    / len(rows),
                    "mean_elapsed_ms": sum(float(row["elapsed_ms"]) for row in rows)
                    / len(rows),
                }
            )
            await asyncio.sleep(float(config["phase_gc_grace_ms"]) / 1000.0)
            first_lane = next(iter(lanes.values()))
            gc_response = await first_lane.protocol.control(
                {"kind": "receiver_gc"}, expected_kind="receiver_gc_reply"
            )
            phase_summaries[-1]["expired_fragment_sets"] = gc_response[
                "expired_fragment_sets"
            ]
            phase_summaries[-1]["expired_coded_messages"] = gc_response[
                "expired_coded_messages"
            ]
            phase_summaries[-1]["reassembly_inflight_after_gc"] = gc_response[
                "stats"
            ]["reassembly_inflight"]
            phase_summaries[-1]["coded_messages_inflight_after_gc"] = gc_response[
                "stats"
            ]["coded_messages_inflight"]

        proxy_stats: dict[str, object] = {}
        for name, lane in lanes.items():
            response = await lane.protocol.control(
                {"kind": "proxy_stats"}, expected_kind="proxy_stats_reply"
            )
            proxy_stats[name] = response["stats"]
        first_lane = next(iter(lanes.values()))
        receiver_response = await first_lane.protocol.control(
            {"kind": "receiver_stats"}, expected_kind="receiver_stats_reply"
        )
        receiver_stats = receiver_response["stats"]
    finally:
        for lane in lanes.values():
            lane.close()
        await asyncio.sleep(0)

    observation_hash = write_csv(output_dir / "observations.csv", observations)
    successes = sum(int(row["success"]) for row in observations)
    brier = sum(float(row["brier_component"]) for row in observations) / len(observations)
    calibration_mae = sum(
        abs(float(row["availability"]) - float(row["mean_predicted_success"]))
        for row in phase_summaries
    ) / len(phase_summaries)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "closed_world": True,
        "docker_internal_network_required": True,
        "synthetic_payloads": True,
        "external_destinations": 0,
        "live_interfaces": 0,
        "strict_trust": True,
        "scheduler_strategy": scheduler_strategy,
        "provider_controlled_attempts": sum(
            int(row["provider_controlled_attempts"]) for row in observations
        ),
        "roles": {
            "sender": 1,
            "carrier_fault_adapters": len(lanes),
            "receiver": 1,
        },
        "operations": len(observations),
        "successful_operations": successes,
        "acknowledged_availability": successes / len(observations),
        "receiver_completed_operations": receiver_stats["operations_completed"],
        "payload_bytes": sum(int(row["payload_bytes"]) for row in observations),
        "wire_bytes": sum(int(row["wire_bytes"]) for row in observations),
        "byte_overhead": sum(int(row["wire_bytes"]) for row in observations)
        / sum(int(row["payload_bytes"]) for row in observations),
        "wall_time_seconds": time.perf_counter() - started_wall,
        "client_cpu_seconds": time.process_time() - process_cpu_start,
        "client_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "brier_score": brier,
        "phase_calibration_mae": calibration_mae,
        "phase_summaries": phase_summaries,
        "lane_attempts": dict(sorted(attempted_counts.items())),
        "proxy_stats": proxy_stats,
        "receiver_stats": receiver_stats,
        "resolved_proxy_addresses": {
            name: list(lane.addresses) for name, lane in sorted(lanes.items())
        },
        "ack_auth_failures": sum(
            lane.protocol.ack_auth_failures for lane in lanes.values()
        ),
        "control_auth_failures": sum(
            lane.protocol.control_auth_failures for lane in lanes.values()
        ),
        "prediction_scope": (
            "implementation-concordance check under declared independent per-datagram "
            "loss/corruption and Gaussian-delay approximations; not external validity"
        ),
        "cryptography": (
            "ChaCha20-Poly1305 shard envelopes, domain-separated HMAC-SHA-256 "
            "acknowledgements, and authenticated laboratory control records"
        ),
        "observations_sha256": observation_hash,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


async def _wait_for_stop() -> None:
    loop = asyncio.get_running_loop()
    stopped = loop.create_future()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                signum, lambda: stopped.done() or stopped.set_result(None)
            )
        except NotImplementedError:
            pass
    await stopped


async def run_receiver(config_path: Path) -> None:
    config = _load_config(config_path)
    key = _session_key(int(config["seed"]))
    receiver = config["receiver"]
    protocol = ReceiverProtocol(key)
    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: protocol,
        local_addr=(str(receiver.get("bind_host", "0.0.0.0")), int(receiver["port"])),
    )
    print("CAPME_READY receiver", flush=True)
    try:
        await _wait_for_stop()
    finally:
        transport.close()
        print(json.dumps({"receiver": protocol._stats()}, sort_keys=True), flush=True)


async def run_proxy(config_path: Path, lane_name: str) -> None:
    config = _load_config(config_path)
    row = next((row for row in config["lanes"] if row["name"] == lane_name), None)
    if row is None:
        raise ValueError(f"unknown carrier lane: {lane_name}")
    receiver_host = str(config["receiver"]["host"])
    receiver_port = int(config["receiver"]["port"])
    receiver_addresses = set(resolve_closed_lab_host(receiver_host, receiver_port))
    phases = {
        str(phase["name"]): phase["lanes"][lane_name] for phase in config["phases"]
    }
    lane_index = [item["name"] for item in config["lanes"]].index(lane_name)
    protocol = CarrierProxyProtocol(
        key=_session_key(int(config["seed"])),
        lane=lane_name,
        phases=phases,
        receiver=(next(iter(sorted(receiver_addresses))), receiver_port),
        receiver_addresses=receiver_addresses,
        seed=int(config["seed"]) + 10_007 * (lane_index + 1),
    )
    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: protocol,
        local_addr=(str(row.get("proxy_bind_host", "0.0.0.0")), int(row["proxy_port"])),
    )
    print(f"CAPME_READY proxy {lane_name}", flush=True)
    try:
        await _wait_for_stop()
    finally:
        transport.close()
        print(json.dumps({"proxy": protocol._stats()}, sort_keys=True), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="role", required=True)
    receiver = subparsers.add_parser("receiver")
    receiver.add_argument("--config", type=Path, required=True)
    proxy = subparsers.add_parser("proxy")
    proxy.add_argument("--config", type=Path, required=True)
    proxy.add_argument("--lane", required=True)
    client = subparsers.add_parser("client")
    client.add_argument("--config", type=Path, required=True)
    client.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.role == "receiver":
        asyncio.run(run_receiver(args.config))
    elif args.role == "proxy":
        asyncio.run(run_proxy(args.config, args.lane))
    else:
        manifest = asyncio.run(run_client(args.config, args.output))
        print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
