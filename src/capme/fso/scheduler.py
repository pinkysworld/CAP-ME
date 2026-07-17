"""FSO and comparison schedulers."""

from __future__ import annotations

import itertools
import math
import random
from abc import ABC, abstractmethod

from .types import FUNCTIONS, LaneProfile, LaneState, Operation, ScheduleDecision

FUNCTION_PLAN = {
    "text": (1, 2, "parallel"),
    "presence": (1, 1, "opportunistic"),
    "media": (2, 3, "parallel"),
    "file": (3, 5, "parallel"),
    "realtime": (1, 2, "hot_standby"),
}

ADAPTIVE_PLANS = {
    "text": ((1, 1, "single"), (1, 2, "sequential"), (1, 2, "parallel")),
    "presence": ((1, 1, "opportunistic"), (1, 2, "sequential")),
    "media": (
        (1, 1, "single"),
        (1, 2, "sequential"),
        (1, 2, "parallel"),
        (2, 3, "parallel"),
    ),
    "file": (
        (1, 1, "single"),
        (1, 2, "sequential"),
        (2, 3, "parallel"),
        (3, 5, "parallel"),
    ),
    "realtime": (
        (1, 1, "single"),
        (1, 2, "hot_standby"),
        (1, 2, "parallel"),
    ),
}

COST_WEIGHT = {
    "text": 0.020,
    "presence": 0.090,
    "media": 0.035,
    "file": 0.045,
    "realtime": 0.015,
}

LATENCY_WEIGHT = {
    "text": 0.025,
    "presence": 0.040,
    "media": 0.030,
    "file": 0.020,
    "realtime": 0.180,
}


def _at_least_k(probabilities: list[float], threshold: int) -> float:
    distribution = [1.0] + [0.0] * len(probabilities)
    for probability in probabilities:
        updated = [0.0] * len(distribution)
        for successes in range(len(probabilities)):
            updated[successes] += distribution[successes] * (1.0 - probability)
            updated[successes + 1] += distribution[successes] * probability
        distribution = updated
    return sum(distribution[threshold:])


class Scheduler(ABC):
    def __init__(self, profiles: list[LaneProfile], *, strict_trust: bool, seed: int) -> None:
        self.states = {profile.name: LaneState(profile) for profile in profiles}
        self.strict_trust = strict_trust
        self.rng = random.Random(seed)

    def eligible(self, operation: Operation) -> list[LaneState]:
        strict = self.strict_trust or operation.strict_trust
        return [
            state
            for state in self.states.values()
            if not (strict and state.profile.provider_controls_delivery)
        ]

    def update(self, lane: str, function: str, *, success: bool, latency_ms: float) -> None:
        self.states[lane].update(function, success=success, latency_ms=latency_ms)

    @abstractmethod
    def plan(self, operation: Operation) -> ScheduleDecision:
        raise NotImplementedError


class StaticScheduler(Scheduler):
    def __init__(self, profiles: list[LaneProfile], *, architecture: str, strategy: str, strict_trust: bool, seed: int) -> None:
        super().__init__(profiles, strict_trust=strict_trust, seed=seed)
        self.architecture = architecture
        self.strategy = strategy

    def plan(self, operation: Operation) -> ScheduleDecision:
        candidates = [state for state in self.eligible(operation) if state.profile.architecture == self.architecture]
        if not candidates:
            raise ValueError(f"no eligible {self.architecture} lane")
        state = candidates[0]
        probability = state.predicted_success(operation.function)
        return ScheduleDecision(
            self.strategy,
            operation.function,
            1,
            1,
            (state.profile.name,),
            "single",
            probability,
            state.profile.byte_cost,
            f"single declared {self.architecture} baseline",
        )


class RandomFailoverScheduler(Scheduler):
    def plan(self, operation: Operation) -> ScheduleDecision:
        candidates = self.eligible(operation)
        count = min(2, len(candidates))
        chosen = self.rng.sample(candidates, count)
        probabilities = [state.predicted_success(operation.function) for state in chosen]
        return ScheduleDecision(
            "random_failover",
            operation.function,
            1,
            count,
            tuple(state.profile.name for state in chosen),
            "sequential",
            _at_least_k(probabilities, 1),
            sum(state.profile.byte_cost for state in chosen),
            "uniform random sequential carriers",
        )


class PerformanceScheduler(Scheduler):
    def plan(self, operation: Operation) -> ScheduleDecision:
        state = min(
            self.eligible(operation),
            key=lambda candidate: candidate.predicted_latency(operation.function),
        )
        return ScheduleDecision(
            "performance_only",
            operation.function,
            1,
            1,
            (state.profile.name,),
            "single",
            state.predicted_success(operation.function),
            state.profile.byte_cost,
            "lowest observed completion time without survival objective",
        )


class SessionFailoverScheduler(Scheduler):
    def plan(self, operation: Operation) -> ScheduleDecision:
        chosen = sorted(
            self.eligible(operation),
            key=lambda state: (
                state.predicted_success(operation.function),
                -state.predicted_latency(operation.function),
            ),
            reverse=True,
        )[:2]
        probabilities = [state.predicted_success(operation.function) for state in chosen]
        return ScheduleDecision(
            "session_failover",
            operation.function,
            1,
            len(chosen),
            tuple(state.profile.name for state in chosen),
            "sequential",
            _at_least_k(probabilities, 1),
            sum(state.profile.byte_cost for state in chosen),
            "transport-independent session with delivery-ranked failover",
        )


class FSOScheduler(Scheduler):
    def __init__(
        self,
        profiles: list[LaneProfile],
        *,
        strict_trust: bool,
        seed: int,
        semantics: bool = True,
        diversity: bool = True,
        feedback: bool = True,
        redundancy: bool = True,
        adaptive_modes: bool = True,
        strategy: str = "fso",
        correlation_weight: float = 0.35,
    ) -> None:
        super().__init__(profiles, strict_trust=strict_trust, seed=seed)
        self.semantics = semantics
        self.diversity = diversity
        self.feedback = feedback
        self.redundancy = redundancy
        self.adaptive_modes = adaptive_modes
        self.strategy = strategy
        self.correlation_weight = correlation_weight

    def _dimensions(self, function: str, available: int) -> tuple[int, int, str]:
        if not self.redundancy:
            return 1, 1, "single"
        threshold, total, mode = FUNCTION_PLAN[function] if self.semantics else (1, 2, "parallel")
        total = min(total, available)
        threshold = min(threshold, total)
        return threshold, total, mode

    def _candidate_dimensions(self, function: str, available: int) -> list[tuple[int, int, str]]:
        if not self.redundancy:
            return [(1, 1, "single")]
        if not self.semantics:
            return [(1, min(2, available), "parallel")]
        if not self.adaptive_modes:
            return [self._dimensions(function, available)]
        output: list[tuple[int, int, str]] = []
        for threshold, total, mode in ADAPTIVE_PLANS[function]:
            total = min(total, available)
            threshold = min(threshold, total)
            candidate = (threshold, total, mode if total > 1 else "single")
            if candidate not in output:
                output.append(candidate)
        return output

    def _portfolio_score(
        self,
        operation: Operation,
        states: tuple[LaneState, ...],
        threshold: int,
        mode: str,
    ) -> tuple[float, float, float, float]:
        domains: dict[str, int] = {}
        probabilities: list[float] = []
        for state in states:
            domain = state.profile.failure_domain
            domains[domain] = domains.get(domain, 0) + 1
            probability = state.predicted_success(operation.function, use_feedback=self.feedback)
            repeats = domains[domain] - 1
            if self.diversity and repeats:
                probability *= max(0.2, 1.0 - self.correlation_weight * repeats)
            probabilities.append(probability)
        latencies = [
            state.predicted_latency(operation.function, use_feedback=self.feedback)
            for state in states
        ]
        if mode == "sequential":
            reach_probability = 1.0
            completion = 0.0
            expected_attempts = 0.0
            expected_latency = 0.0
            elapsed = 0.0
            for probability, latency in zip(probabilities, latencies, strict=True):
                expected_attempts += reach_probability
                arrival = elapsed + latency
                extra_survival = math.exp(-elapsed / operation.deadline_ms)
                effective_probability = probability * extra_survival
                first_success = reach_probability * effective_probability
                completion += first_success
                expected_latency += first_success * arrival
                reach_probability *= 1.0 - effective_probability
                elapsed += min(operation.deadline_ms * 0.45, latency * 1.7)
            predicted_latency = expected_latency / completion if completion else operation.deadline_ms
        elif mode == "hot_standby" and len(states) > 1:
            first_probability, second_probability = probabilities[:2]
            first_latency, second_latency = latencies[:2]
            fallback_at = min(operation.deadline_ms * 0.22, first_latency * 0.65)
            first_on_time = first_probability
            second_on_time = second_probability * math.exp(
                -fallback_at / operation.deadline_ms
            )
            completion = 1.0 - (1.0 - first_on_time) * (1.0 - second_on_time)
            expected_attempts = 1.0 + (
                1.0 - first_probability if first_latency <= fallback_at else 1.0
            )
            candidate_latencies = []
            if first_on_time:
                candidate_latencies.append(first_latency)
            if second_on_time:
                candidate_latencies.append(fallback_at + second_latency)
            predicted_latency = min(candidate_latencies) if candidate_latencies else operation.deadline_ms
        else:
            completion = _at_least_k(probabilities, threshold)
            expected_attempts = float(len(states))
            predicted_latency = sorted(latencies)[min(threshold, len(latencies)) - 1]
        mean_cost = sum(state.profile.byte_cost for state in states) / len(states)
        overhead = expected_attempts * mean_cost / threshold
        burn_risk = sum(
            (1.0 - state.profile.endpoint_resilience)
            * (state.failures / state.attempts if state.attempts else 0.0)
            for state in states
        ) / len(states)
        repeated = len(states) - len(domains)
        correlation_penalty = self.correlation_weight * repeated / max(1, len(states))
        latency_fraction = min(1.0, predicted_latency / operation.deadline_ms)
        utility = (
            completion
            - COST_WEIGHT[operation.function] * overhead
            - LATENCY_WEIGHT[operation.function] * latency_fraction
            - 0.16 * burn_risk
            - 0.10 * correlation_penalty
        )
        return utility, completion, overhead, predicted_latency

    def plan(self, operation: Operation) -> ScheduleDecision:
        candidates = self.eligible(operation)
        if not candidates:
            raise ValueError("no carrier satisfies the trust policy")
        ranked: list[
            tuple[tuple[float, float, float, float], tuple[LaneState, ...], int, int, str]
        ] = []
        for threshold, total, mode in self._candidate_dimensions(
            operation.function, len(candidates)
        ):
            portfolios = list(itertools.combinations(candidates, total))
            if not self.diversity:
                minimum_domains = min(
                    len({state.profile.failure_domain for state in states})
                    for states in portfolios
                )
                portfolios = [
                    states
                    for states in portfolios
                    if len({state.profile.failure_domain for state in states}) == minimum_domains
                ]
            for states in portfolios:
                if mode in {"sequential", "hot_standby"}:
                    states = tuple(
                        sorted(
                            states,
                            key=lambda state: (
                                state.predicted_success(
                                    operation.function, use_feedback=self.feedback
                                ),
                                -state.predicted_latency(
                                    operation.function, use_feedback=self.feedback
                                ),
                            ),
                            reverse=True,
                        )
                    )
                ranked.append(
                    (
                        self._portfolio_score(operation, states, threshold, mode),
                        states,
                        threshold,
                        total,
                        mode,
                    )
                )
        (utility, completion, overhead, predicted_latency), chosen, threshold, total, mode = max(
            ranked,
            key=lambda item: (
                item[0][0],
                len({state.profile.failure_domain for state in item[1]}),
                tuple(state.profile.name for state in item[1]),
            ),
        )
        return ScheduleDecision(
            self.strategy,
            operation.function,
            threshold,
            total,
            tuple(state.profile.name for state in chosen),
            mode,
            completion,
            overhead,
            (
                f"survival utility={utility:.4f}; semantics={int(self.semantics)}; "
                f"diversity={int(self.diversity)}; feedback={int(self.feedback)}; "
                f"redundancy={int(self.redundancy)}; adaptive_modes={int(self.adaptive_modes)}; "
                f"predicted_latency_ms={predicted_latency:.1f}"
            ),
        )


def build_scheduler(
    strategy: str,
    profiles: list[LaneProfile],
    *,
    strict_trust: bool,
    seed: int,
    correlation_weight: float = 0.35,
) -> Scheduler:
    static = {
        "direct_only": "direct_e2ee",
        "fixed_only": "fixed_proxy",
        "generated_only": "generated_transport",
        "ephemeral_only": "ephemeral_relay",
    }
    if strategy in static:
        return StaticScheduler(
            profiles,
            architecture=static[strategy],
            strategy=strategy,
            strict_trust=strict_trust,
            seed=seed,
        )
    if strategy == "random_failover":
        return RandomFailoverScheduler(profiles, strict_trust=strict_trust, seed=seed)
    if strategy == "performance_only":
        return PerformanceScheduler(profiles, strict_trust=strict_trust, seed=seed)
    if strategy == "session_failover":
        return SessionFailoverScheduler(profiles, strict_trust=strict_trust, seed=seed)
    options = {
        "fso": {},
        "fso_fixed_code": {"adaptive_modes": False},
        "fso_no_semantics": {"semantics": False},
        "fso_no_diversity": {"diversity": False},
        "fso_no_feedback": {"feedback": False},
        "fso_no_redundancy": {"redundancy": False},
    }
    if strategy not in options:
        raise ValueError(f"unknown FSO strategy: {strategy}")
    return FSOScheduler(
        profiles,
        strict_trust=strict_trust,
        seed=seed,
        strategy=strategy,
        correlation_weight=correlation_weight,
        **options[strategy],
    )
