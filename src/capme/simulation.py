"""Deterministic, controlled event simulation for CAP-ME."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np

from .detector import DiagonalGaussianDetector, calibrate_threshold, operating_point
from .model import Architecture, CensorRegime, NetworkCondition, WORKLOADS, Workload

BENIGN_MEAN = np.array([0.50, 0.46, 0.44, 0.36, 0.48], dtype=float)
BENIGN_STD = np.array([0.13, 0.12, 0.14, 0.15, 0.13], dtype=float)
SEPARATION_DIRECTION = np.array([0.62, -0.35, 0.51, -0.58, 0.43], dtype=float)


@dataclass
class Endpoint:
    identifier: int
    born_epoch: int
    blocked_until: int = -1
    reputation: int = 0
    operations: int = 0

    def available(self, epoch: int) -> bool:
        return epoch >= self.blocked_until


@dataclass(frozen=True)
class SimulationConfig:
    epochs: int = 36
    operations_per_function: int = 16
    training_positive: int = 180
    training_benign: int = 500
    calibration_benign: int = 2_000
    evaluation_positive: int = 500
    prevalence: float = 0.001
    sustained_windows: int = 3

    def validate(self) -> None:
        if self.epochs < 2:
            raise ValueError("epochs must be at least two")
        if self.operations_per_function < 1:
            raise ValueError("operations_per_function must be positive")
        if self.calibration_benign < 1 / self.prevalence:
            raise ValueError("calibration sample is too small for the prevalence")


@dataclass
class SimulationResult:
    rows: list[dict[str, object]]
    endpoint_events: list[dict[str, object]]
    manifest: dict[str, object]


def _clip_features(values: np.ndarray) -> np.ndarray:
    return np.clip(values, 0.001, 0.999)


def benign_features(rng: np.random.Generator, count: int) -> np.ndarray:
    # A three-component mixture prevents the detector from seeing a single,
    # unrealistically homogeneous benign class.
    components = rng.choice(3, size=count, p=[0.56, 0.27, 0.17])
    offsets = np.array(
        [
            [0.00, 0.00, 0.00, 0.00, 0.00],
            [0.08, -0.05, 0.06, -0.04, 0.09],
            [-0.07, 0.08, -0.04, 0.09, -0.06],
        ]
    )
    samples = rng.normal(BENIGN_MEAN + offsets[components], BENIGN_STD, size=(count, 5))
    return _clip_features(samples)


def _variant_vector(architecture: Architecture, generation: int) -> np.ndarray:
    if generation == 0 or architecture.protocol_diversity == 0:
        return np.zeros(5)
    digest = hashlib.sha256(f"{architecture.name}:{generation}".encode()).digest()
    values = np.frombuffer(digest[:5], dtype=np.uint8).astype(float)
    centered = (values / 255.0 - 0.5) * 2.0
    return centered * architecture.protocol_diversity * 0.32


def architecture_features(
    rng: np.random.Generator,
    architecture: Architecture,
    count: int,
    generation: int,
    workload: Workload | None = None,
) -> np.ndarray:
    mean = BENIGN_MEAN + SEPARATION_DIRECTION * architecture.passive_separability
    mean = mean + _variant_vector(architecture, generation)
    if workload is not None:
        scale = math.log1p(workload.payload_mb) / 8.0
        mean = mean + np.array([0.06, 0.03, -0.02, -0.01, 0.07]) * scale
    std = BENIGN_STD * (0.90 + architecture.protocol_diversity * 0.8)
    return _clip_features(rng.normal(mean, std, size=(count, 5)))


def _protocol_generation(architecture: Architecture, epoch: int) -> int:
    if architecture.protocol_rotation_period <= 0:
        return 0
    return epoch // architecture.protocol_rotation_period


def _network_success_probability(
    architecture: Architecture,
    workload: Workload,
    network: NetworkCondition,
    rng: np.random.Generator,
) -> tuple[float, float]:
    latency = max(1.0, rng.normal(network.latency_ms, network.jitter_ms))
    transfer_ms = workload.payload_mb * 8_000.0 / network.bandwidth_mbps
    completion_ms = architecture.transport_overhead * (
        latency * workload.round_trips + transfer_ms
    )
    delivered = (1.0 - network.loss_rate) ** workload.segments
    delivery_margin = min(1.0, delivered / max(workload.required_delivery, 1e-9))
    if completion_ms <= workload.deadline_ms:
        deadline_factor = 1.0
    else:
        deadline_factor = math.exp(
            -(completion_ms - workload.deadline_ms) / max(workload.deadline_ms, 1.0)
        )
    return max(0.0, min(1.0, delivery_margin * deadline_factor)), completion_ms


def _rotate_endpoints(
    endpoints: list[Endpoint],
    architecture: Architecture,
    epoch: int,
    next_identifier: int,
    events: list[dict[str, object]],
) -> int:
    period = architecture.endpoint_rotation_period
    if period <= 0 or epoch == 0 or epoch % period:
        return next_identifier
    count = max(1, round(len(endpoints) * architecture.endpoint_rotation_fraction))
    candidates = sorted(endpoints, key=lambda item: (item.blocked_until, item.born_epoch), reverse=True)
    retiring = {item.identifier for item in candidates[:count]}
    kept = [item for item in endpoints if item.identifier not in retiring]
    for item in candidates[:count]:
        events.append(
            {
                "event": "retired",
                "endpoint_id": item.identifier,
                "epoch": epoch,
                "lifetime": epoch - item.born_epoch,
            }
        )
    for _ in range(count):
        kept.append(Endpoint(next_identifier, epoch))
        events.append({"event": "born", "endpoint_id": next_identifier, "epoch": epoch})
        next_identifier += 1
    endpoints[:] = kept
    return next_identifier


def run_simulation(
    architecture: Architecture,
    censor: CensorRegime,
    network: NetworkCondition,
    seed: int,
    config: SimulationConfig,
) -> SimulationResult:
    config.validate()
    # Independent deterministic substreams implement common random numbers
    # across layer ablations. Turning one censor layer on no longer perturbs
    # unrelated workload, network, or classifier draws.
    streams = np.random.SeedSequence(seed).spawn(6)
    rng_classifier = np.random.default_rng(streams[0])
    rng_features = np.random.default_rng(streams[1])
    rng_endpoint = np.random.default_rng(streams[2])
    rng_censor = np.random.default_rng(streams[3])
    rng_network = np.random.default_rng(streams[4])
    rng_policy = np.random.default_rng(streams[5])
    endpoints = [Endpoint(identifier=i, born_epoch=0) for i in range(architecture.endpoint_pool)]
    next_identifier = architecture.endpoint_pool
    endpoint_events: list[dict[str, object]] = [
        {"event": "born", "endpoint_id": item.identifier, "epoch": 0} for item in endpoints
    ]
    rows: list[dict[str, object]] = []
    detector = DiagonalGaussianDetector()
    learned_generation = 0
    threshold = math.inf
    detector_metrics = {"tpr": 0.0, "fpr": 0.0, "precision": 1.0}
    calibration_scores = np.array([], dtype=float)

    for epoch in range(config.epochs):
        generation = _protocol_generation(architecture, epoch)
        next_identifier = _rotate_endpoints(
            endpoints, architecture, epoch, next_identifier, endpoint_events
        )
        should_train = epoch == 0 or (
            censor.adaptive_training and epoch % max(censor.retrain_interval, 1) == 0
        )
        if should_train:
            # Adaptive training learns the previous observation window, which
            # creates a measurable lag after protocol rotation.
            learned_generation = _protocol_generation(architecture, max(0, epoch - 1))
            positive_train = architecture_features(
                rng_classifier, architecture, config.training_positive, learned_generation
            )
            benign_train = benign_features(rng_classifier, config.training_benign)
            detector.fit(positive_train, benign_train)
            calibration = benign_features(rng_classifier, config.calibration_benign)
            calibration_scores = detector.score(calibration)
            threshold = calibrate_threshold(calibration_scores, censor.false_positive_cap)
        evaluation_positive = architecture_features(
            rng_classifier, architecture, config.evaluation_positive, generation
        )
        positive_scores = detector.score(evaluation_positive)
        if should_train or epoch == 0:
            detector_metrics = operating_point(
                positive_scores, calibration_scores, threshold, config.prevalence
            )
        else:
            current_benign = benign_features(rng_classifier, config.calibration_benign)
            current_benign_scores = detector.score(current_benign)
            detector_metrics = operating_point(
                positive_scores, current_benign_scores, threshold, config.prevalence
            )

        epoch_probe_budget = censor.probe_budget
        epoch_block_budget = censor.block_budget
        epoch_probes = 0
        epoch_blocks = 0
        epoch_burns = 0

        # Stable, non-permitted endpoints may be discovered without a
        # classifier (e.g., address publication or repeated observation).
        if (
            censor.endpoint_control
            and not architecture.domestically_permitted
            and epoch_block_budget
        ):
            for endpoint in endpoints:
                if epoch_block_budget <= 0:
                    break
                if not endpoint.available(epoch):
                    continue
                if rng_censor.random() < architecture.discovery_rate / max(len(endpoints), 1):
                    endpoint.blocked_until = epoch + censor.block_ttl
                    endpoint.reputation = 0
                    epoch_blocks += 1
                    epoch_burns += 1
                    epoch_block_budget -= 1
                    endpoint_events.append(
                        {
                            "event": "blocked_discovery",
                            "endpoint_id": endpoint.identifier,
                            "epoch": epoch,
                            "lifetime": epoch - endpoint.born_epoch,
                        }
                    )

        for workload in WORKLOADS.values():
            counts = {
                "attempts": config.operations_per_function,
                "successes": 0,
                "path_failures": 0,
                "endpoint_failures": 0,
                "platform_failures": 0,
                "network_failures": 0,
            }
            scores: list[float] = []
            completion_times: list[float] = []
            for _ in range(config.operations_per_function):
                available = [item for item in endpoints if item.available(epoch)]
                if not available:
                    counts["endpoint_failures"] += 1
                    continue
                endpoint = available[int(rng_endpoint.integers(0, len(available)))]
                endpoint.operations += 1
                feature = architecture_features(
                    rng_features, architecture, 1, generation, workload
                )
                score = float(detector.score(feature)[0])
                scores.append(score)
                per_segment_suspicion = score >= threshold
                path_detected = per_segment_suspicion and (
                    rng_censor.random()
                    < 1.0 - (1.0 - censor.path_enforcement) ** workload.segments
                )

                # Draw policy and network outcomes for every attempted
                # operation, even if an earlier censor layer later blocks it.
                # This keeps those exogenous draws paired across ablations.
                policy_event = rng_policy.random() < workload.policy_event_rate
                platform_draw = rng_policy.random()
                network_probability, completion_ms = _network_success_probability(
                    architecture, workload, network, rng_network
                )
                network_draw = rng_network.random()

                # A permitted platform represents collateral the network
                # censor is configured not to block. Platform control remains
                # a distinct decision below.
                if architecture.domestically_permitted:
                    path_detected = False

                if (
                    censor.endpoint_control
                    and not architecture.domestically_permitted
                    and per_segment_suspicion
                ):
                    endpoint.reputation += 1
                    if epoch_probe_budget > 0:
                        epoch_probe_budget -= 1
                        epoch_probes += 1
                        if (
                            rng_censor.random() < architecture.probe_confirmation
                            and epoch_block_budget > 0
                        ):
                            endpoint.blocked_until = epoch + censor.block_ttl
                            endpoint.reputation = 0
                            epoch_block_budget -= 1
                            epoch_blocks += 1
                            epoch_burns += 1
                            endpoint_events.append(
                                {
                                    "event": "blocked_probe",
                                    "endpoint_id": endpoint.identifier,
                                    "epoch": epoch,
                                    "lifetime": epoch - endpoint.born_epoch,
                                }
                            )
                    elif (
                        endpoint.reputation >= censor.reputation_threshold
                        and epoch_block_budget > 0
                    ):
                        endpoint.blocked_until = epoch + censor.block_ttl
                        endpoint.reputation = 0
                        epoch_block_budget -= 1
                        epoch_blocks += 1
                        epoch_burns += 1
                        endpoint_events.append(
                            {
                                "event": "blocked_reputation",
                                "endpoint_id": endpoint.identifier,
                                "epoch": epoch,
                                "lifetime": epoch - endpoint.born_epoch,
                            }
                        )

                if censor.path_control and path_detected:
                    counts["path_failures"] += 1
                    continue
                if not endpoint.available(epoch):
                    counts["endpoint_failures"] += 1
                    continue
                platform_blocked = (
                    censor.platform_control
                    and architecture.provider_controls_delivery
                    and policy_event
                    and platform_draw < censor.platform_filter_rate
                )
                if platform_blocked:
                    counts["platform_failures"] += 1
                    continue
                completion_times.append(completion_ms)
                if network_draw > network_probability:
                    counts["network_failures"] += 1
                    continue
                counts["successes"] += 1

            active_endpoints = sum(item.available(epoch) for item in endpoints)
            rows.append(
                {
                    "seed": seed,
                    "architecture": architecture.name,
                    "architecture_label": architecture.label,
                    "censor": censor.name,
                    "censor_label": censor.label,
                    "network": network.name,
                    "layer_mask": censor.layer_mask,
                    "epoch": epoch,
                    "function": workload.name,
                    **counts,
                    "availability": counts["successes"] / counts["attempts"],
                    "active_endpoints": active_endpoints,
                    "blocked_endpoints": len(endpoints) - active_endpoints,
                    "endpoint_pool": len(endpoints),
                    "endpoint_burns_epoch": epoch_burns,
                    "probes_epoch": epoch_probes,
                    "blocks_epoch": epoch_blocks,
                    "protocol_generation": generation,
                    "learned_generation": learned_generation,
                    "threshold": threshold,
                    "tpr": detector_metrics["tpr"],
                    "fpr": detector_metrics["fpr"],
                    "precision_at_prevalence": detector_metrics["precision"],
                    "mean_score": float(np.mean(scores)) if scores else math.nan,
                    "mean_completion_ms": (
                        float(np.mean(completion_times)) if completion_times else math.nan
                    ),
                }
            )

    manifest = {
        "schema_version": 1,
        "seed": seed,
        "architecture": asdict(architecture),
        "censor": asdict(censor),
        "network": asdict(network),
        "config": asdict(config),
        "synthetic_only": True,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return SimulationResult(rows, endpoint_events, manifest)


def overall_epoch_availability(rows: Iterable[dict[str, object]]) -> dict[int, float]:
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(int(row["epoch"]), []).append(float(row["availability"]))
    return {epoch: float(np.mean(values)) for epoch, values in grouped.items()}
