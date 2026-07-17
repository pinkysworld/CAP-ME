"""Closed-world CensorLab bridge for packet-level FSO evaluation.

The bridge deliberately treats CensorLab as an external executable.  It
generates synthetic PCAPs containing real FSO envelopes and reconstructs
message-level outcomes from the packet decisions printed by CensorLab's PCAP
mode.  It does not send packets, configure a host firewall, or contact any
destination.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import struct
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from capme.io import sha256_file, write_csv, write_json
from capme.model import WORKLOADS

from .crypto import AckAuthenticator, EnvelopeCipher
from .framing import fragment_envelope
from .lab import DeterministicLabEntropy
from .protocol import FSOSender
from .scheduler import Scheduler, build_scheduler
from .types import FUNCTIONS, LaneProfile, Operation, ScheduleDecision

PCAP_GLOBAL_HEADER = struct.Struct("<IHHIIII")
PCAP_RECORD_HEADER = struct.Struct("<IIII")
ETHERNET_TYPE_IPV4 = 0x0800
IP_PROTOCOL_TCP = 6
IP_PROTOCOL_UDP = 17

ACTION_LINE = re.compile(
    r"^\s*(\d+):\s*(?:Ok\()?"
    r"(Drop|Reset|Inject|None|Ignore|Allow|TerminateAll)\b",
    re.IGNORECASE | re.MULTILINE,
)
ERROR_LINE = re.compile(
    r"^\s*(\d+):\s*Err\((.+)\)\s*$", re.IGNORECASE | re.MULTILINE
)
TIMING_LINE = re.compile(
    r"Pcap mode took\s+(\d+)us to process the file\s+"
    r"\((\d+)us including I/O\)",
    re.IGNORECASE,
)
BLOCKING_ACTIONS = frozenset({"drop", "reset", "inject", "terminateall"})


@dataclass(frozen=True)
class LaneAdapter:
    """A declared synthetic mapping from one FSO lane to an IP flow."""

    profile: LaneProfile
    transport: str
    server_ip: str
    server_port: int

    def __post_init__(self) -> None:
        if self.transport not in {"tcp", "udp"}:
            raise ValueError("lane transport must be tcp or udp")
        address = ipaddress.ip_address(self.server_ip)
        if not address.is_private:
            # RFC 5737 documentation ranges are not consistently reported as
            # private by every Python release, so check them explicitly below.
            documentation = (
                ipaddress.ip_network("192.0.2.0/24"),
                ipaddress.ip_network("198.51.100.0/24"),
                ipaddress.ip_network("203.0.113.0/24"),
            )
            if not any(address in network for network in documentation):
                raise ValueError("server_ip must be private or documentation-only")
        if not 1 <= self.server_port <= 65535:
            raise ValueError("server_port must lie in [1, 65535]")


@dataclass(frozen=True)
class CensorLabDecision:
    packet_index: int
    action: str

    @property
    def blocked(self) -> bool:
        return self.action.lower() in BLOCKING_ACTIONS


@dataclass(frozen=True)
class CensorLabOutput:
    decisions: Mapping[int, CensorLabDecision]
    errors: Mapping[int, str]
    processing_us: int | None
    total_us: int | None


@dataclass(frozen=True)
class TraceMessage:
    epoch: int
    operation_index: int
    kind: str
    function: str
    message_id: str
    deadline_ms: float
    decision: ScheduleDecision


@dataclass(frozen=True)
class TraceBuild:
    messages: tuple[TraceMessage, ...]
    packet_rows: tuple[dict[str, object], ...]
    pcap_sha256: str
    labels_sha256: str


Backend = Callable[[Path, Path, int], str]


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    value = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while value >> 16:
        value = (value & 0xFFFF) + (value >> 16)
    return (~value) & 0xFFFF


def _transport_segment(
    payload: bytes,
    *,
    transport: str,
    src_ip: bytes,
    dst_ip: bytes,
    src_port: int,
    dst_port: int,
    sequence: int,
) -> tuple[int, bytes]:
    if transport == "tcp":
        offset_and_flags = (5 << 12) | 0x018  # PSH + ACK
        header = struct.pack(
            "!HHIIHHHH",
            src_port,
            dst_port,
            sequence,
            1,
            offset_and_flags,
            65535,
            0,
            0,
        )
        pseudo = src_ip + dst_ip + struct.pack(
            "!BBH", 0, IP_PROTOCOL_TCP, len(header) + len(payload)
        )
        checksum = _checksum(pseudo + header + payload)
        header = struct.pack(
            "!HHIIHHHH",
            src_port,
            dst_port,
            sequence,
            1,
            offset_and_flags,
            65535,
            checksum,
            0,
        )
        return IP_PROTOCOL_TCP, header + payload
    if transport == "udp":
        length = 8 + len(payload)
        header = struct.pack("!HHHH", src_port, dst_port, length, 0)
        pseudo = src_ip + dst_ip + struct.pack(
            "!BBH", 0, IP_PROTOCOL_UDP, length
        )
        checksum = _checksum(pseudo + header + payload) or 0xFFFF
        header = struct.pack("!HHHH", src_port, dst_port, length, checksum)
        return IP_PROTOCOL_UDP, header + payload
    raise ValueError(f"unsupported transport: {transport}")


def build_ethernet_ipv4_frame(
    payload: bytes,
    *,
    transport: str,
    src_ip: str,
    dst_ip: str,
    src_port: int,
    dst_port: int,
    identification: int,
    sequence: int,
    reverse_macs: bool = False,
) -> bytes:
    """Build one valid Ethernet/IPv4/TCP-or-UDP frame without networking."""

    source = ipaddress.IPv4Address(src_ip).packed
    destination = ipaddress.IPv4Address(dst_ip).packed
    protocol, segment = _transport_segment(
        payload,
        transport=transport,
        src_ip=source,
        dst_ip=destination,
        src_port=src_port,
        dst_port=dst_port,
        sequence=sequence,
    )
    total_length = 20 + len(segment)
    ip_header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        identification & 0xFFFF,
        0,
        64,
        protocol,
        0,
        source,
        destination,
    )
    ip_checksum = _checksum(ip_header)
    ip_header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        identification & 0xFFFF,
        0,
        64,
        protocol,
        ip_checksum,
        source,
        destination,
    )
    client_mac = bytes.fromhex("aabbccddee01")
    server_mac = bytes.fromhex("aabbccddee02")
    source_mac, destination_mac = (
        (server_mac, client_mac) if reverse_macs else (client_mac, server_mac)
    )
    ethernet = destination_mac + source_mac + struct.pack("!H", ETHERNET_TYPE_IPV4)
    return ethernet + ip_header + segment


def write_pcap(path: Path, frames: Iterable[tuple[int, bytes]]) -> str:
    """Write a deterministic microsecond-resolution classic PCAP."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(
            PCAP_GLOBAL_HEADER.pack(
                0xA1B2C3D4,
                2,
                4,
                0,
                0,
                65535,
                1,
            )
        )
        for timestamp_us, frame in frames:
            seconds, micros = divmod(timestamp_us, 1_000_000)
            handle.write(
                PCAP_RECORD_HEADER.pack(seconds, micros, len(frame), len(frame))
            )
            handle.write(frame)
    return sha256_file(path)


def parse_censorlab_output(output: str) -> CensorLabOutput:
    decisions: dict[int, CensorLabDecision] = {}
    for match in ACTION_LINE.finditer(output):
        packet_index = int(match.group(1))
        action = match.group(2).lower()
        decisions[packet_index] = CensorLabDecision(packet_index, action)
    timing = TIMING_LINE.search(output)
    return CensorLabOutput(
        decisions=decisions,
        errors={
            int(match.group(1)): match.group(2)
            for match in ERROR_LINE.finditer(output)
        },
        processing_us=int(timing.group(1)) if timing else None,
        total_us=int(timing.group(2)) if timing else None,
    )


def _lane_from_config(row: Mapping[str, object]) -> LaneAdapter:
    profile = LaneProfile(
        name=str(row["name"]),
        architecture=str(row["architecture"]),
        failure_domain=str(row["failure_domain"]),
        latency_prior_ms=float(row["latency_ms"]),
        survival_prior=float(row["survival_prior"]),
        endpoint_resilience=float(row["endpoint_resilience"]),
        provider_controls_delivery=bool(row["provider_controls_delivery"]),
        byte_cost=float(row.get("byte_cost", 1.0)),
    )
    return LaneAdapter(
        profile=profile,
        transport=str(row["transport"]).lower(),
        server_ip=str(row["server_ip"]),
        server_port=int(row["server_port"]),
    )


def _payload(seed: int, epoch: int, operation: int, function: str, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        material = (
            f"CAPME-CENSORLAB|{seed}|{epoch}|{operation}|{function}|{counter}"
        ).encode("utf-8")
        output.extend(hashlib.sha256(material).digest())
        counter += 1
    return bytes(output[:length])


def _single_lane_decision(function: str, lane: str) -> ScheduleDecision:
    return ScheduleDecision(
        strategy="lane_probe",
        function=function,
        threshold=1,
        total_shards=1,
        lanes=(lane,),
        dispatch_mode="single",
        estimated_completion=1.0,
        predicted_overhead=1.0,
        rationale="declared per-epoch calibration probe",
    )


def build_epoch_trace(
    *,
    epoch: int,
    config: Mapping[str, Any],
    scheduler: Scheduler,
    sender: FSOSender,
    acknowledgements: AckAuthenticator,
    adapters: Mapping[str, LaneAdapter],
    pcap_path: Path,
    labels_path: Path,
) -> TraceBuild:
    client_ip = str(config["client_ip"])
    calibration_ip = str(config["calibration_blocked_ip"])
    max_fragment_data = int(config["max_fragment_data"])
    seed = int(config["seed"])
    packet_rows: list[dict[str, object]] = []
    frames: list[tuple[int, bytes]] = []
    messages: list[TraceMessage] = []
    packet_index = 0
    identification = epoch * 10_000

    def append_packet(
        payload: bytes,
        *,
        timestamp_us: int,
        lane: LaneAdapter | None,
        operation_index: int,
        function: str,
        message_id: str,
        shard_index: int,
        fragment_part: int,
        fragment_total: int,
        direction: str,
        role: str,
        kind: str,
        source_port: int,
    ) -> None:
        nonlocal packet_index, identification
        packet_index += 1
        identification += 1
        if lane is None:
            transport = "tcp"
            server_ip = calibration_ip
            server_port = 8443
        else:
            transport = lane.transport
            server_ip = lane.server_ip
            server_port = lane.server_port
        reverse = direction == "server_to_client"
        frame = build_ethernet_ipv4_frame(
            payload,
            transport=transport,
            src_ip=server_ip if reverse else client_ip,
            dst_ip=client_ip if reverse else server_ip,
            src_port=server_port if reverse else source_port,
            dst_port=source_port if reverse else server_port,
            identification=identification,
            sequence=(
                ((operation_index + 1) * 100_000 + fragment_part * 2_000)
                & 0xFFFFFFFF
            ),
            reverse_macs=reverse,
        )
        frames.append((timestamp_us, frame))
        packet_rows.append(
            {
                "packet_index": packet_index,
                "epoch": epoch,
                "operation": operation_index,
                "kind": kind,
                "function": function,
                "message_id": message_id,
                "lane": lane.profile.name if lane else "calibration",
                "shard_index": shard_index,
                "fragment_part": fragment_part,
                "fragment_total": fragment_total,
                "direction": direction,
                "role": role,
                "transport": transport,
                "server_ip": server_ip,
                "server_port": server_port,
                "payload_bytes": len(payload),
                "timestamp_us": timestamp_us,
            }
        )

    # First frame is intentionally guaranteed to match the static IP rule in
    # the pinned official mega_gfw configuration.  It lets us detect whether
    # a CensorLab release reports PCAP indices as zero- or one-based.
    append_packet(
        b"CAPME-PCAP-INDEX-CALIBRATION",
        timestamp_us=epoch * 100_000_000,
        lane=None,
        operation_index=-1,
        function="calibration",
        message_id="",
        shard_index=-1,
        fragment_part=0,
        fragment_total=1,
        direction="client_to_server",
        role="calibration",
        kind="calibration",
        source_port=32000,
    )

    planned: list[tuple[str, int, Operation, ScheduleDecision]] = []
    if bool(config.get("probe_each_lane", True)):
        for probe_index, lane in enumerate(adapters.values()):
            if bool(config["strict_trust"]) and lane.profile.provider_controls_delivery:
                continue
            operation = Operation(
                "text",
                _payload(seed, epoch, -1000 - probe_index, "text", 96),
                WORKLOADS["text"].deadline_ms,
                strict_trust=bool(config["strict_trust"]),
            )
            planned.append(
                ("probe", -1000 - probe_index, operation, _single_lane_decision("text", lane.profile.name))
            )

    operations_per_epoch = int(config["operations_per_epoch"])
    payload_bytes = config["payload_bytes"]
    for local_index in range(operations_per_epoch):
        operation_index = epoch * operations_per_epoch + local_index
        function = FUNCTIONS[operation_index % len(FUNCTIONS)]
        operation = Operation(
            function,
            _payload(
                seed,
                epoch,
                operation_index,
                function,
                int(payload_bytes[function]),
            ),
            WORKLOADS[function].deadline_ms,
            strict_trust=bool(config["strict_trust"]),
        )
        planned.append(("application", operation_index, operation, scheduler.plan(operation)))

    for ordinal, (kind, operation_index, operation, decision) in enumerate(planned):
        prepared = sender.prepare(operation, decision)
        message_id = prepared.message_id.hex()
        messages.append(
            TraceMessage(
                epoch=epoch,
                operation_index=operation_index,
                kind=kind,
                function=operation.function,
                message_id=message_id,
                deadline_ms=operation.deadline_ms,
                decision=decision,
            )
        )
        base_timestamp = epoch * 100_000_000 + (ordinal + 1) * 1_000_000
        for shard_index, (lane_name, envelope) in enumerate(
            zip(decision.lanes, prepared.packets, strict=True)
        ):
            lane = adapters[lane_name]
            fragments = fragment_envelope(
                envelope, max_fragment_data=max_fragment_data
            )
            source_port = 33000 + ((epoch * 500 + ordinal * 7 + shard_index) % 30000)
            for fragment_part, fragment in enumerate(fragments):
                append_packet(
                    fragment,
                    timestamp_us=base_timestamp + fragment_part * 1_000,
                    lane=lane,
                    operation_index=operation_index,
                    function=operation.function,
                    message_id=message_id,
                    shard_index=shard_index,
                    fragment_part=fragment_part,
                    fragment_total=len(fragments),
                    direction="client_to_server",
                    role="data",
                    kind=kind,
                    source_port=source_port,
                )
            ack = acknowledgements.seal(prepared.message_id, shard_index)
            append_packet(
                ack,
                timestamp_us=(
                    base_timestamp
                    + len(fragments) * 1_000
                    + round(2.0 * lane.profile.latency_prior_ms * 1_000)
                ),
                lane=lane,
                operation_index=operation_index,
                function=operation.function,
                message_id=message_id,
                shard_index=shard_index,
                fragment_part=0,
                fragment_total=1,
                direction="server_to_client",
                role="ack",
                kind=kind,
                source_port=source_port,
            )

    pcap_hash = write_pcap(pcap_path, frames)
    labels_hash = write_csv(labels_path, packet_rows)
    return TraceBuild(tuple(messages), tuple(packet_rows), pcap_hash, labels_hash)


def _decision_offset(
    output: CensorLabOutput, packet_rows: Sequence[Mapping[str, object]]
) -> int:
    calibration = next(
        int(row["packet_index"])
        for row in packet_rows
        if row["role"] == "calibration"
    )
    candidates = [
        index
        for index, decision in output.decisions.items()
        if decision.blocked and index in {calibration - 1, calibration, calibration + 1}
    ]
    if not candidates:
        raise ValueError(
            "the CensorLab output did not block the index-calibration packet; "
            "check that the pinned mega_gfw configuration is in use"
        )
    return min(candidates) - calibration


def evaluate_epoch(
    trace: TraceBuild,
    output: CensorLabOutput,
    *,
    scheduler: Scheduler,
    adapters: Mapping[str, LaneAdapter],
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    if output.errors:
        raise RuntimeError(
            "CensorLab reported packet-processing errors: "
            + "; ".join(
                f"{index}: {message}"
                for index, message in sorted(output.errors.items())
            )
        )
    offset = _decision_offset(output, trace.packet_rows)
    packet_rows: list[dict[str, object]] = []
    by_message_shard: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for original in trace.packet_rows:
        row = dict(original)
        external_index = int(row["packet_index"]) + offset
        decision = output.decisions.get(external_index)
        row["censorlab_packet_index"] = external_index
        row["action"] = decision.action if decision else "allow"
        row["blocked"] = int(bool(decision and decision.blocked))
        packet_rows.append(row)
        if row["message_id"]:
            by_message_shard[(str(row["message_id"]), int(row["shard_index"]))].append(row)

    operation_rows: list[dict[str, object]] = []
    for message in trace.messages:
        lane_outcomes: list[tuple[str, bool, float]] = []
        blocked_data = 0
        blocked_acks = 0
        wire_bytes = 0
        for shard_index, lane_name in enumerate(message.decision.lanes):
            rows = by_message_shard[(message.message_id, shard_index)]
            data_rows = [row for row in rows if row["role"] == "data"]
            ack_rows = [row for row in rows if row["role"] == "ack"]
            if not data_rows or len(ack_rows) != 1:
                raise AssertionError("trace is missing data fragments or acknowledgement")
            data_passed = all(not int(row["blocked"]) for row in data_rows)
            ack_passed = not int(ack_rows[0]["blocked"])
            blocked_data += sum(int(row["blocked"]) for row in data_rows)
            blocked_acks += int(ack_rows[0]["blocked"])
            wire_bytes += sum(int(row["payload_bytes"]) for row in rows)
            lane = adapters[lane_name]
            completion_ms = (
                2.0 * lane.profile.latency_prior_ms
                + max(int(row["fragment_part"]) for row in data_rows)
            )
            acked = data_passed and ack_passed and completion_ms <= message.deadline_ms
            lane_outcomes.append((lane_name, acked, completion_ms))
            scheduler.update(
                lane_name,
                message.function,
                success=acked,
                latency_ms=completion_ms,
            )
        successful_lanes = [item for item in lane_outcomes if item[1]]
        success = len(successful_lanes) >= message.decision.threshold
        baseline_success = (
            sum(
                1
                for lane_name in message.decision.lanes
                if 2.0 * adapters[lane_name].profile.latency_prior_ms
                <= message.deadline_ms
            )
            >= message.decision.threshold
        )
        completion_ms = (
            sorted(item[2] for item in successful_lanes)[message.decision.threshold - 1]
            if success
            else message.deadline_ms
        )
        operation_rows.append(
            {
                "epoch": message.epoch,
                "operation": message.operation_index,
                "kind": message.kind,
                "function": message.function,
                "message_id": message.message_id,
                "strategy": message.decision.strategy,
                "threshold": message.decision.threshold,
                "total_shards": message.decision.total_shards,
                "dispatch_mode": message.decision.dispatch_mode,
                "attempted_lanes": ";".join(message.decision.lanes),
                "acked_lanes": ";".join(item[0] for item in successful_lanes),
                "success": int(success),
                "conditional_no_censor_success": int(baseline_success),
                "completion_ms": completion_ms,
                "deadline_ms": message.deadline_ms,
                "blocked_data_packets": blocked_data,
                "blocked_ack_packets": blocked_acks,
                "wire_payload_bytes": wire_bytes,
            }
        )
    return operation_rows, packet_rows, offset


def run_study(
    config_path: Path,
    output_dir: Path,
    backend: Backend,
    *,
    environment: Mapping[str, object] | None = None,
) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("synthetic_only") is not True or config.get("closed_world") is not True:
        raise ValueError("CensorLab study requires synthetic_only and closed_world")
    if config.get("backend", {}).get("mode") != "pcap":
        raise ValueError("only offline CensorLab PCAP mode is authorized")
    seed = int(config["seed"])
    adapters = {
        lane.profile.name: lane
        for lane in (_lane_from_config(row) for row in config["lanes"])
    }
    profiles = [lane.profile for lane in adapters.values()]
    scheduler = build_scheduler(
        "fso",
        profiles,
        strict_trust=bool(config["strict_trust"]),
        seed=seed,
        correlation_weight=float(config["correlation_weight"]),
    )
    key = hashlib.sha256(f"FSO-CENSORLAB-SESSION|{seed}".encode()).digest()
    cipher = EnvelopeCipher(
        key, nonce_source=DeterministicLabEntropy(seed, "censorlab-nonce")
    )
    sender = FSOSender(
        cipher,
        message_id_source=DeterministicLabEntropy(seed, "censorlab-message-id"),
    )
    acknowledgements = AckAuthenticator(key)
    traces_dir = output_dir / "traces"
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    all_operations: list[dict[str, object]] = []
    all_packets: list[dict[str, object]] = []
    epoch_rows: list[dict[str, object]] = []
    trace_hashes: list[dict[str, object]] = []
    offsets: set[int] = set()

    for epoch in range(int(config["epochs"])):
        pcap_path = traces_dir / f"epoch-{epoch:02d}.pcap"
        labels_path = traces_dir / f"epoch-{epoch:02d}-labels.csv"
        trace = build_epoch_trace(
            epoch=epoch,
            config=config,
            scheduler=scheduler,
            sender=sender,
            acknowledgements=acknowledgements,
            adapters=adapters,
            pcap_path=pcap_path,
            labels_path=labels_path,
        )
        raw_output = backend(pcap_path, labels_path, epoch)
        log_path = logs_dir / f"epoch-{epoch:02d}.log"
        log_path.write_text(raw_output, encoding="utf-8")
        parsed = parse_censorlab_output(raw_output)
        operation_rows, packet_rows, offset = evaluate_epoch(
            trace, parsed, scheduler=scheduler, adapters=adapters
        )
        offsets.add(offset)
        all_operations.extend(operation_rows)
        all_packets.extend(packet_rows)
        applications = [row for row in operation_rows if row["kind"] == "application"]
        epoch_rows.append(
            {
                "epoch": epoch,
                "application_operations": len(applications),
                "successful_operations": sum(int(row["success"]) for row in applications),
                "availability": sum(int(row["success"]) for row in applications) / len(applications),
                "conditional_no_censor_availability": sum(
                    int(row["conditional_no_censor_success"]) for row in applications
                ) / len(applications),
                "censored_packets": sum(int(row["blocked"]) for row in packet_rows),
                "packets": len(packet_rows),
                "processing_us": parsed.processing_us,
                "total_us": parsed.total_us,
                "pcap_index_offset": offset,
            }
        )
        trace_hashes.append(
            {
                "epoch": epoch,
                "pcap": str(pcap_path.relative_to(output_dir)),
                "pcap_sha256": trace.pcap_sha256,
                "labels": str(labels_path.relative_to(output_dir)),
                "labels_sha256": trace.labels_sha256,
                "log": str(log_path.relative_to(output_dir)),
                "log_sha256": sha256_file(log_path),
            }
        )

    operations_hash = write_csv(output_dir / "operations.csv", all_operations)
    packets_hash = write_csv(output_dir / "packet-decisions.csv", all_packets)
    epochs_hash = write_csv(output_dir / "epochs.csv", epoch_rows)
    applications = [row for row in all_operations if row["kind"] == "application"]
    probes = [row for row in all_operations if row["kind"] == "probe"]
    function_counts: Counter[str] = Counter()
    function_successes: Counter[str] = Counter()
    for row in applications:
        function = str(row["function"])
        function_counts[function] += 1
        function_successes[function] += int(row["success"])
    manifest: dict[str, object] = {
        "schema_version": 1,
        "synthetic_only": True,
        "closed_world": True,
        "offline_pcap_only": True,
        "external_destinations": 0,
        "live_interfaces": 0,
        "backend": config["backend"],
        "environment": dict(environment or {}),
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "seed": seed,
        "epochs": int(config["epochs"]),
        "application_operations": len(applications),
        "probe_operations": len(probes),
        "successful_operations": sum(int(row["success"]) for row in applications),
        "availability": sum(int(row["success"]) for row in applications) / len(applications),
        "conditional_no_censor_availability": sum(
            int(row["conditional_no_censor_success"]) for row in applications
        ) / len(applications),
        "function_availability": {
            function: function_successes[function] / function_counts[function]
            for function in sorted(function_counts)
        },
        "packets": len(all_packets),
        "censored_packets": sum(int(row["blocked"]) for row in all_packets),
        "pcap_index_offsets": sorted(offsets),
        "provider_controlled_attempts": sum(
            lane_name in adapters
            and adapters[lane_name].profile.provider_controls_delivery
            for row in all_operations
            for lane_name in str(row["attempted_lanes"]).split(";")
        ),
        "interpretation": (
            "Results characterize the pinned declared CensorLab configuration "
            "on synthetic FSO traces; they are not measurements of China or "
            "of the contemporary Great Firewall."
        ),
        "operations_sha256": operations_hash,
        "packet_decisions_sha256": packets_hash,
        "epochs_sha256": epochs_hash,
        "traces": trace_hashes,
    }
    if manifest["provider_controlled_attempts"] != 0:
        raise AssertionError("strict-trust CensorLab study used a provider-controlled lane")
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def docker_backend(
    *,
    image: str,
    censorlab_repo: Path,
    config_relative: Path,
    output_root: Path,
    client_ip: str,
    config_origin: str = "image",
    artifact_root: Path | None = None,
) -> Backend:
    """Create a no-network, read-only Docker backend for CensorLab PCAP mode."""

    repo = censorlab_repo.resolve()
    root = output_root.resolve()
    if config_origin == "image":
        config_path = repo / config_relative
        container_config = f"/external-censorlab/{config_relative.as_posix()}"
        artifact_mount: list[str] = []
    elif config_origin == "artifact":
        if artifact_root is None:
            raise ValueError("artifact_root is required for an artifact config")
        artifact = artifact_root.resolve()
        config_path = artifact / config_relative
        container_config = f"/capme-artifact/{config_relative.as_posix()}"
        artifact_mount = [
            "--mount",
            f"type=bind,src={artifact},dst=/capme-artifact,readonly",
        ]
    else:
        raise ValueError("config_origin must be image or artifact")
    if not config_path.is_file():
        raise FileNotFoundError(config_path)

    def run(pcap_path: Path, _labels_path: Path, _epoch: int) -> str:
        relative_pcap = pcap_path.resolve().relative_to(root)
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--mount",
            f"type=bind,src={root},dst=/capme-study,readonly",
            *artifact_mount,
            image,
            "censorlab",
            "-c",
            container_config,
            "pcap",
            f"/capme-study/{relative_pcap.as_posix()}",
            client_ip,
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode:
            raise RuntimeError(
                f"CensorLab exited with status {completed.returncode}:\n{output}"
            )
        return output

    return run


def verify_external_censorlab(repo: Path, expected_commit: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    actual = completed.stdout.strip()
    if actual != expected_commit:
        raise ValueError(
            f"CensorLab commit mismatch: expected {expected_commit}, found {actual}"
        )
    return actual
