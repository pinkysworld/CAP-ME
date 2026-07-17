"""Typed protocol and scheduler records for FSO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

FUNCTIONS = ("text", "presence", "media", "file", "realtime")
FUNCTION_CODES = {name: index + 1 for index, name in enumerate(FUNCTIONS)}
CODE_FUNCTIONS = {value: key for key, value in FUNCTION_CODES.items()}


@dataclass(frozen=True)
class Operation:
    """One application operation; semantics remain inside encrypted payloads."""

    function: str
    payload: bytes
    deadline_ms: float
    strict_trust: bool = True

    def __post_init__(self) -> None:
        if self.function not in FUNCTIONS:
            raise ValueError(f"unsupported function: {self.function}")
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")
        if self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive")


@dataclass(frozen=True)
class LaneProfile:
    """Declared properties of one replaceable carrier instance."""

    name: str
    architecture: str
    failure_domain: str
    latency_prior_ms: float
    survival_prior: float
    endpoint_resilience: float
    provider_controls_delivery: bool
    byte_cost: float = 1.0

    def __post_init__(self) -> None:
        if not self.name or not self.failure_domain:
            raise ValueError("lane name and failure domain are required")
        if self.latency_prior_ms <= 0:
            raise ValueError("latency prior must be positive")
        for value in (self.survival_prior, self.endpoint_resilience):
            if not 0.0 <= value <= 1.0:
                raise ValueError("probabilities must lie in [0, 1]")


@dataclass
class LaneState:
    """Sender-local observations; no censor-internal labels are available."""

    profile: LaneProfile
    observations: dict[str, list[float]] = field(default_factory=dict)
    latency_ms: dict[str, float] = field(default_factory=dict)
    attempts: int = 0
    failures: int = 0

    def __post_init__(self) -> None:
        strength = 6.0
        self.observations = {
            function: [1.0 + strength * self.profile.survival_prior,
                       1.0 + strength * (1.0 - self.profile.survival_prior)]
            for function in FUNCTIONS
        }
        self.latency_ms = {
            function: self.profile.latency_prior_ms for function in FUNCTIONS
        }

    def predicted_success(self, function: str, *, use_feedback: bool = True) -> float:
        if use_feedback:
            alpha, beta = self.observations[function]
            delivery = alpha / (alpha + beta)
        else:
            delivery = self.profile.survival_prior
        failure_rate = self.failures / self.attempts if self.attempts else 0.0
        burn_discount = 1.0 - 0.35 * failure_rate * (1.0 - self.profile.endpoint_resilience)
        return max(0.001, min(0.999, delivery * burn_discount))

    def predicted_latency(self, function: str, *, use_feedback: bool = True) -> float:
        return self.latency_ms[function] if use_feedback else self.profile.latency_prior_ms

    def update(self, function: str, *, success: bool, latency_ms: float) -> None:
        self.attempts += 1
        if success:
            self.observations[function][0] += 1.0
        else:
            self.observations[function][1] += 1.0
            self.failures += 1
        if latency_ms > 0:
            prior = self.latency_ms[function]
            self.latency_ms[function] = 0.82 * prior + 0.18 * latency_ms


@dataclass(frozen=True)
class ScheduleDecision:
    strategy: str
    function: str
    threshold: int
    total_shards: int
    lanes: tuple[str, ...]
    dispatch_mode: str
    estimated_completion: float
    predicted_overhead: float
    rationale: str

    def __post_init__(self) -> None:
        if not 1 <= self.threshold <= self.total_shards:
            raise ValueError("invalid coding dimensions")
        if len(self.lanes) != self.total_shards:
            raise ValueError("one carrier instance is required per shard")
        if len(set(self.lanes)) != len(self.lanes):
            raise ValueError("a carrier instance cannot receive two shards in one plan")


def lane_profiles_from_config(rows: list[Mapping[str, object]]) -> list[LaneProfile]:
    return [
        LaneProfile(
            name=str(row["name"]),
            architecture=str(row["architecture"]),
            failure_domain=str(row["failure_domain"]),
            latency_prior_ms=float(row["latency_prior_ms"]),
            survival_prior=float(row["survival_prior"]),
            endpoint_resilience=float(row["endpoint_resilience"]),
            provider_controls_delivery=bool(row["provider_controls_delivery"]),
            byte_cost=float(row.get("byte_cost", 1.0)),
        )
        for row in rows
    ]
