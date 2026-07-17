"""Deterministic closed-world carrier adapters and failure injection for FSO."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from capme.io import sha256_file, write_csv, write_json
from capme.model import WORKLOADS

from .crypto import AckAuthenticator, EnvelopeCipher, EnvelopeError
from .framing import (
    FRAGMENT_HEADER,
    FragmentReassembler,
    FramingError,
    fragment_envelope,
)
from .protocol import FSOReceiver, FSOSender, PreparedTransmission
from .scheduler import Scheduler, build_scheduler
from .types import FUNCTIONS, LaneProfile, Operation


class DeterministicLabEntropy:
    """Counter-mode test entropy; reproducible and forbidden for deployment."""

    def __init__(self, seed: int, label: str) -> None:
        self.seed = seed
        self.label = label
        self.counter = 0
        self.outputs: set[bytes] = set()

    def __call__(self, length: int) -> bytes:
        if length <= 0:
            raise ValueError("entropy length must be positive")
        self.counter += 1
        output = bytearray()
        block = 0
        while len(output) < length:
            material = (
                f"FSO-LAB|{self.seed}|{self.label}|{self.counter}|{block}"
            ).encode("utf-8")
            output.extend(hashlib.sha256(material).digest())
            block += 1
        value = bytes(output[:length])
        if value in self.outputs:
            raise AssertionError("deterministic lab entropy collision")
        self.outputs.add(value)
        return value


def _unit(seed: int, *parts: object) -> float:
    material = "|".join((str(seed), *(str(part) for part in parts))).encode(
        "utf-8"
    )
    integer = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return (integer + 0.5) / (2**64)


@dataclass(frozen=True)
class FailurePhase:
    name: str
    loss_multiplier: float
    loss_additive: float
    latency_multiplier: float
    burst_probability: float
    burst_loss_additive: float
    duplicate_rate: float
    tamper_rate: float
    ack_loss_rate: float
    ack_tamper_rate: float
    outage_domains: frozenset[str]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "FailurePhase":
        return cls(
            name=str(row["name"]),
            loss_multiplier=float(row.get("loss_multiplier", 1.0)),
            loss_additive=float(row.get("loss_additive", 0.0)),
            latency_multiplier=float(row.get("latency_multiplier", 1.0)),
            burst_probability=float(row.get("burst_probability", 0.0)),
            burst_loss_additive=float(row.get("burst_loss_additive", 0.0)),
            duplicate_rate=float(row.get("duplicate_rate", 0.0)),
            tamper_rate=float(row.get("tamper_rate", 0.0)),
            ack_loss_rate=float(row.get("ack_loss_rate", 0.0)),
            ack_tamper_rate=float(row.get("ack_tamper_rate", 0.0)),
            outage_domains=frozenset(str(value) for value in row.get("outage_domains", [])),
        )


@dataclass(frozen=True)
class ScheduledFragment:
    arrival_ms: float
    datagram: bytes


@dataclass(frozen=True)
class PlannedTransmission:
    lane: str
    packet: bytes
    fragments: tuple[ScheduledFragment, ...]
    expected_fragments: int
    dropped_fragments: int
    tampered_fragments: int
    duplicated_fragments: int
    data_arrival_ms: float
    ack_arrival_ms: float
    ack_drop: bool
    ack_tamper: bool
    wire_bytes: int

    @property
    def can_form_envelope(self) -> bool:
        unique = {
            fragment.datagram[: FRAGMENT_HEADER.size] for fragment in self.fragments
        }
        return (
            self.dropped_fragments == 0
            and self.tampered_fragments == 0
            and len(unique) >= self.expected_fragments
        )


@dataclass(frozen=True)
class TransmissionOutcome:
    lane: str
    acked: bool
    latency_ms: float
    receiver_status: str
    completion_ms: float | None
    wire_bytes: int
    dropped_fragments: int
    tampered_fragments: int
    duplicated_fragments: int
    data_auth_rejections: int
    ack_drops: int
    ack_auth_rejections: int


class SimulatedCarrierAdapter:
    """One closed-world carrier with deterministic path and ACK impairments."""

    def __init__(self, profile: LaneProfile, row: dict[str, Any]) -> None:
        self.profile = profile
        self.loss_rate = float(row["loss_rate"])
        self.jitter_ms = float(row["jitter_ms"])

    def plan(
        self,
        packet: bytes,
        *,
        seed: int,
        phase: FailurePhase,
        operation_index: int,
        correlation_weight: float,
        max_fragment_data: int,
        offset_ms: float = 0.0,
    ) -> PlannedTransmission:
        datagrams = fragment_envelope(
            packet, max_fragment_data=max_fragment_data
        )
        outage = self.profile.failure_domain in phase.outage_domains
        burst = (
            _unit(
                seed,
                phase.name,
                operation_index,
                self.profile.failure_domain,
                "burst",
            )
            < phase.burst_probability
        )
        loss_probability = min(
            0.999,
            max(
                0.0,
                self.loss_rate * phase.loss_multiplier
                + phase.loss_additive
                + (phase.burst_loss_additive if burst else 0.0),
            ),
        )
        scheduled: list[ScheduledFragment] = []
        dropped = 0
        tampered = 0
        duplicated = 0
        wire_bytes = 0
        for part, datagram in enumerate(datagrams):
            wire_bytes += len(datagram)
            domain_draw = _unit(
                seed,
                phase.name,
                operation_index,
                self.profile.failure_domain,
                part,
                "fragment-loss",
            )
            lane_draw = _unit(
                seed,
                phase.name,
                operation_index,
                self.profile.name,
                part,
                "fragment-loss",
            )
            selector = _unit(
                seed,
                phase.name,
                operation_index,
                self.profile.name,
                part,
                "correlation-selector",
            )
            draw = domain_draw if selector < correlation_weight else lane_draw
            if outage or draw < loss_probability:
                dropped += 1
                continue
            delivered = datagram
            if (
                _unit(
                    seed,
                    phase.name,
                    operation_index,
                    self.profile.name,
                    part,
                    "fragment-tamper",
                )
                < phase.tamper_rate
            ):
                changed = bytearray(delivered)
                changed[-1] ^= 0x01
                delivered = bytes(changed)
                tampered += 1
            jitter = self.jitter_ms * (
                2.0
                * _unit(
                    seed,
                    phase.name,
                    operation_index,
                    self.profile.name,
                    part,
                    "fragment-latency",
                )
                - 1.0
            )
            arrival = offset_ms + max(
                0.1,
                self.profile.latency_prior_ms * phase.latency_multiplier + jitter,
            )
            scheduled.append(ScheduledFragment(arrival, delivered))
            if (
                _unit(
                    seed,
                    phase.name,
                    operation_index,
                    self.profile.name,
                    part,
                    "fragment-duplicate",
                )
                < phase.duplicate_rate
            ):
                scheduled.append(ScheduledFragment(arrival + 0.01, delivered))
                duplicated += 1
                wire_bytes += len(delivered)
        data_arrival = max(
            (fragment.arrival_ms for fragment in scheduled),
            default=offset_ms + self.profile.latency_prior_ms * phase.latency_multiplier,
        )
        reverse_jitter = self.jitter_ms * (
            2.0
            * _unit(
                seed,
                phase.name,
                operation_index,
                self.profile.name,
                "ack-latency",
            )
            - 1.0
        )
        ack_arrival = data_arrival + max(
            0.1,
            self.profile.latency_prior_ms * phase.latency_multiplier + reverse_jitter,
        )
        ack_drop = (
            _unit(
                seed,
                phase.name,
                operation_index,
                self.profile.name,
                "ack-loss",
            )
            < phase.ack_loss_rate
        )
        ack_tamper = (
            _unit(
                seed,
                phase.name,
                operation_index,
                self.profile.name,
                "ack-tamper",
            )
            < phase.ack_tamper_rate
        )
        return PlannedTransmission(
            lane=self.profile.name,
            packet=packet,
            fragments=tuple(sorted(scheduled, key=lambda item: item.arrival_ms)),
            expected_fragments=len(datagrams),
            dropped_fragments=dropped,
            tampered_fragments=tampered,
            duplicated_fragments=duplicated,
            data_arrival_ms=data_arrival,
            ack_arrival_ms=ack_arrival,
            ack_drop=ack_drop,
            ack_tamper=ack_tamper,
            wire_bytes=wire_bytes,
        )


def _deliver(
    plan: PlannedTransmission,
    *,
    receiver: FSOReceiver,
    reassembler: FragmentReassembler,
    acknowledgements: AckAuthenticator,
    timeout_ms: float,
) -> TransmissionOutcome:
    reassembled = None
    reassembled_at: float | None = None
    data_auth_rejections = 0
    ack_auth_rejections = 0
    ack_drops = 0
    receiver_status = "fragment-loss"
    completion_ms: float | None = None
    for fragment in plan.fragments:
        if fragment.arrival_ms > timeout_ms:
            receiver_status = "deadline-expired"
            continue
        try:
            result = reassembler.ingest(fragment.datagram, peer=plan.lane)
        except FramingError:
            data_auth_rejections += 1
            receiver_status = "framing-rejected"
            continue
        if result.status == "complete":
            reassembled = result.packet
            reassembled_at = fragment.arrival_ms
    acked = False
    ack_arrival_ms: float | None = None
    wire_bytes = plan.wire_bytes
    if reassembled is not None:
        try:
            received = receiver.ingest(reassembled)
            receiver_status = received.status
            if received.status == "complete":
                completion_ms = reassembled_at
        except (EnvelopeError, ValueError):
            data_auth_rejections += 1
            receiver_status = "envelope-auth-rejected"
        else:
            public = EnvelopeCipher.peek(reassembled)
            ack_packet = acknowledgements.seal(public.message_id, public.index)
            wire_bytes += len(ack_packet)
            if plan.ack_drop:
                ack_drops = 1
            elif reassembled_at is not None:
                reverse_latency = plan.ack_arrival_ms - plan.data_arrival_ms
                ack_arrival_ms = reassembled_at + reverse_latency
                if ack_arrival_ms <= timeout_ms:
                    if plan.ack_tamper:
                        changed = bytearray(ack_packet)
                        changed[-1] ^= 0x01
                        ack_packet = bytes(changed)
                    try:
                        ack = acknowledgements.open(ack_packet)
                    except EnvelopeError:
                        ack_auth_rejections = 1
                    else:
                        acked = (
                            ack.status == 1
                            and ack.message_id == public.message_id
                            and ack.shard_index == public.index
                        )
    return TransmissionOutcome(
        lane=plan.lane,
        acked=acked,
        latency_ms=(
            ack_arrival_ms
            if acked and ack_arrival_ms is not None
            else timeout_ms
        ),
        receiver_status=receiver_status,
        completion_ms=completion_ms,
        wire_bytes=wire_bytes,
        dropped_fragments=plan.dropped_fragments,
        tampered_fragments=plan.tampered_fragments,
        duplicated_fragments=plan.duplicated_fragments,
        data_auth_rejections=data_auth_rejections,
        ack_drops=ack_drops,
        ack_auth_rejections=ack_auth_rejections,
    )


def _execute(
    prepared: PreparedTransmission,
    *,
    scheduler: Scheduler,
    adapters: dict[str, SimulatedCarrierAdapter],
    receiver: FSOReceiver,
    reassembler: FragmentReassembler,
    acknowledgements: AckAuthenticator,
    phase: FailurePhase,
    operation: Operation,
    operation_index: int,
    seed: int,
    correlation_weight: float,
    max_fragment_data: int,
) -> dict[str, object]:
    timeout_ms = operation.deadline_ms
    names = prepared.decision.lanes
    packets = prepared.packets
    outcomes: list[TransmissionOutcome] = []

    def plan(index: int, offset_ms: float = 0.0) -> PlannedTransmission:
        return adapters[names[index]].plan(
            packets[index],
            seed=seed,
            phase=phase,
            operation_index=operation_index,
            correlation_weight=correlation_weight,
            max_fragment_data=max_fragment_data,
            offset_ms=offset_ms,
        )

    mode = prepared.decision.dispatch_mode
    if mode == "sequential":
        offset = 0.0
        for index in range(len(names)):
            outcome = _deliver(
                plan(index, offset),
                receiver=receiver,
                reassembler=reassembler,
                acknowledgements=acknowledgements,
                timeout_ms=timeout_ms,
            )
            outcomes.append(outcome)
            if outcome.acked:
                break
            offset += min(
                timeout_ms * 0.45,
                adapters[names[index]].profile.latency_prior_ms * 1.7,
            )
    else:
        plans: list[PlannedTransmission]
        if mode == "hot_standby" and len(names) > 1:
            fallback_at = min(
                operation.deadline_ms * 0.22,
                adapters[names[0]].profile.latency_prior_ms * 0.65,
            )
            primary = plan(0)
            if (
                primary.can_form_envelope
                and not primary.ack_drop
                and not primary.ack_tamper
                and primary.ack_arrival_ms <= fallback_at
            ):
                plans = [primary]
            else:
                plans = [primary] + [
                    plan(index, fallback_at) for index in range(1, len(names))
                ]
        else:
            plans = [plan(index) for index in range(len(names))]
        for planned in sorted(plans, key=lambda item: item.data_arrival_ms):
            outcomes.append(
                _deliver(
                    planned,
                    receiver=receiver,
                    reassembler=reassembler,
                    acknowledgements=acknowledgements,
                    timeout_ms=timeout_ms,
                )
            )

    for outcome in outcomes:
        scheduler.update(
            outcome.lane,
            operation.function,
            success=outcome.acked,
            latency_ms=outcome.latency_ms,
        )
    completion_candidates = [
        outcome.completion_ms
        for outcome in outcomes
        if outcome.completion_ms is not None
    ]
    return {
        "success": int(prepared.message_id in receiver.completed),
        "completion_ms": (
            min(completion_candidates)
            if completion_candidates
            else operation.deadline_ms
        ),
        "wire_bytes": sum(outcome.wire_bytes for outcome in outcomes),
        "attempted_lanes": tuple(outcome.lane for outcome in outcomes),
        "acked_shards": sum(int(outcome.acked) for outcome in outcomes),
        "dropped_fragments": sum(outcome.dropped_fragments for outcome in outcomes),
        "tampered_fragments": sum(outcome.tampered_fragments for outcome in outcomes),
        "duplicated_fragments": sum(outcome.duplicated_fragments for outcome in outcomes),
        "data_auth_rejections": sum(outcome.data_auth_rejections for outcome in outcomes),
        "ack_drops": sum(outcome.ack_drops for outcome in outcomes),
        "ack_auth_rejections": sum(outcome.ack_auth_rejections for outcome in outcomes),
        "provider_controlled_attempts": sum(
            int(adapters[outcome.lane].profile.provider_controls_delivery)
            for outcome in outcomes
        ),
    }


def _profile(row: dict[str, Any]) -> LaneProfile:
    return LaneProfile(
        name=str(row["name"]),
        architecture=str(row["architecture"]),
        failure_domain=str(row["failure_domain"]),
        latency_prior_ms=float(row["latency_ms"]),
        survival_prior=1.0 - float(row["loss_rate"]),
        endpoint_resilience=float(row["endpoint_resilience"]),
        provider_controls_delivery=bool(row["provider_controls_delivery"]),
        byte_cost=float(row.get("byte_cost", 1.0)),
    )


def run_lab(config_path: Path, output_dir: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("synthetic_only") is not True or config.get("closed_world") is not True:
        raise ValueError("deterministic lab requires synthetic_only and closed_world")
    seed = int(config["seed"])
    key = hashlib.sha256(f"FSO-LAB-SESSION|{seed}".encode("utf-8")).digest()
    nonce_source = DeterministicLabEntropy(seed, "nonce")
    message_id_source = DeterministicLabEntropy(seed, "message-id")
    cipher = EnvelopeCipher(key, nonce_source=nonce_source)
    acknowledgements = AckAuthenticator(key)
    sender = FSOSender(cipher, message_id_source=message_id_source)
    receiver = FSOReceiver(cipher)
    reassembler = FragmentReassembler(
        max_inflight=int(config.get("max_inflight_fragments", 4096))
    )
    profiles = [_profile(row) for row in config["lanes"]]
    adapters = {
        profile.name: SimulatedCarrierAdapter(profile, row)
        for profile, row in zip(profiles, config["lanes"], strict=True)
    }
    strict_trust = bool(config["strict_trust"])
    correlation_weight = float(config["correlation_weight"])
    scheduler = build_scheduler(
        "fso",
        profiles,
        strict_trust=strict_trust,
        seed=seed,
        correlation_weight=correlation_weight,
    )
    phases = [FailurePhase.from_row(row) for row in config["phases"]]
    operations_per_phase = int(config["operations_per_phase"])
    max_fragment_data = int(config["max_fragment_data"])
    observations: list[dict[str, object]] = []
    expired_fragment_sets = 0
    expired_shard_sets = 0
    global_operation = 0
    for phase in phases:
        for phase_operation in range(operations_per_phase):
            function_index = global_operation % len(FUNCTIONS)
            function = FUNCTIONS[function_index]
            payload_size = int(config["payload_bytes"][function])
            payload = bytes(
                (
                    (seed + global_operation + function_index + offset) % 251
                    for offset in range(payload_size)
                )
            )
            operation = Operation(
                function,
                payload,
                WORKLOADS[function].deadline_ms,
                strict_trust=strict_trust,
            )
            decision = scheduler.plan(operation)
            prepared = sender.prepare(operation, decision)
            result = _execute(
                prepared,
                scheduler=scheduler,
                adapters=adapters,
                receiver=receiver,
                reassembler=reassembler,
                acknowledgements=acknowledgements,
                phase=phase,
                operation=operation,
                operation_index=global_operation,
                seed=seed,
                correlation_weight=correlation_weight,
                max_fragment_data=max_fragment_data,
            )
            recovered = receiver.completed.get(prepared.message_id)
            if recovered is not None and recovered.payload != payload:
                raise AssertionError("deterministic lab payload mismatch")
            attempted_lanes = tuple(str(value) for value in result["attempted_lanes"])
            observations.append(
                {
                    "phase": phase.name,
                    "phase_operation": phase_operation,
                    "operation": global_operation,
                    "function": function,
                    "success": result["success"],
                    "completion_ms": result["completion_ms"],
                    "deadline_ms": operation.deadline_ms,
                    "payload_bytes": payload_size,
                    "wire_bytes": result["wire_bytes"],
                    "byte_overhead": float(result["wire_bytes"]) / payload_size,
                    "threshold": decision.threshold,
                    "total_shards": decision.total_shards,
                    "dispatch_mode": decision.dispatch_mode,
                    "attempted_lanes": ";".join(attempted_lanes),
                    "acked_shards": result["acked_shards"],
                    "dropped_fragments": result["dropped_fragments"],
                    "tampered_fragments": result["tampered_fragments"],
                    "duplicated_fragments": result["duplicated_fragments"],
                    "data_auth_rejections": result["data_auth_rejections"],
                    "ack_drops": result["ack_drops"],
                    "ack_auth_rejections": result["ack_auth_rejections"],
                    "provider_controlled_attempts": result[
                        "provider_controlled_attempts"
                    ],
                }
            )
            expired_fragment_sets += reassembler.discard_message(
                prepared.message_id
            )
            expired_shard_sets += int(receiver.discard(prepared.message_id))
            global_operation += 1
    observation_hash = write_csv(output_dir / "observations.csv", observations)
    phase_counts: Counter[str] = Counter()
    phase_successes: Counter[str] = Counter()
    for row in observations:
        phase = str(row["phase"])
        phase_counts[phase] += 1
        phase_successes[phase] += int(row["success"])
    payload_bytes = sum(int(row["payload_bytes"]) for row in observations)
    wire_bytes = sum(int(row["wire_bytes"]) for row in observations)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "deterministic": True,
        "synthetic_only": True,
        "closed_world": True,
        "simulated_carrier_adapters": True,
        "external_destinations": 0,
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "seed": seed,
        "phases": [phase.name for phase in phases],
        "operations": len(observations),
        "successful_operations": sum(int(row["success"]) for row in observations),
        "availability": sum(int(row["success"]) for row in observations) / len(observations),
        "payload_bytes": payload_bytes,
        "wire_bytes": wire_bytes,
        "byte_overhead": wire_bytes / payload_bytes,
        "phase_availability": {
            phase: phase_successes[phase] / phase_counts[phase]
            for phase in sorted(phase_counts)
        },
        "provider_controlled_attempts": sum(
            int(row["provider_controlled_attempts"]) for row in observations
        ),
        "failure_injection": {
            key: sum(int(row[key]) for row in observations)
            for key in (
                "dropped_fragments",
                "tampered_fragments",
                "duplicated_fragments",
                "data_auth_rejections",
                "ack_drops",
                "ack_auth_rejections",
            )
        },
        "fragment_reassembly_evictions": reassembler.evictions,
        "fragment_reassembly_inflight_at_end": reassembler.inflight,
        "expired_fragment_sets": expired_fragment_sets,
        "expired_shard_sets": expired_shard_sets,
        "envelopes": nonce_source.counter,
        "unique_nonces": len(nonce_source.outputs),
        "message_ids": message_id_source.counter,
        "unique_message_ids": len(message_id_source.outputs),
        "cryptography": (
            "ChaCha20-Poly1305 envelopes and domain-separated HMAC-SHA-256 "
            "acknowledgements; deterministic entropy is laboratory-only"
        ),
        "observations_sha256": observation_hash,
    }
    if manifest["provider_controlled_attempts"] != 0:
        raise AssertionError("strict-trust deterministic lab used a provider-controlled lane")
    if manifest["envelopes"] != manifest["unique_nonces"]:
        raise AssertionError("deterministic lab repeated an envelope nonce")
    if manifest["message_ids"] != manifest["unique_message_ids"]:
        raise AssertionError("deterministic lab repeated a message ID")
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = run_lab(args.config, args.output)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
