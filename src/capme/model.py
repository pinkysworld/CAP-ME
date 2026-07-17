"""Typed scenario definitions for the CAP-ME benchmark.

All numeric architecture parameters are explicit experimental assumptions.
They are not measurements of named commercial products or national censors.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

FEATURE_NAMES = (
    "first_flight_size",
    "size_variation",
    "timing_variation",
    "printable_fraction",
    "burst_asymmetry",
)


@dataclass(frozen=True)
class Workload:
    name: str
    payload_mb: float
    segments: int
    round_trips: float
    deadline_ms: float
    required_delivery: float
    policy_event_rate: float = 0.0


@dataclass(frozen=True)
class Architecture:
    name: str
    label: str
    description: str
    endpoint_pool: int
    endpoint_rotation_period: int
    endpoint_rotation_fraction: float
    protocol_rotation_period: int
    protocol_diversity: float
    passive_separability: float
    probe_confirmation: float
    discovery_rate: float
    collateral_weight: float
    transport_overhead: float
    provider_controls_plaintext: bool
    provider_controls_delivery: bool
    domestically_permitted: bool


@dataclass(frozen=True)
class CensorRegime:
    name: str
    label: str
    path_control: bool
    endpoint_control: bool
    platform_control: bool
    adaptive_training: bool
    false_positive_cap: float
    probe_budget: int
    block_budget: int
    retrain_interval: int
    block_ttl: int
    reputation_threshold: int
    path_enforcement: float
    platform_filter_rate: float

    @property
    def layer_mask(self) -> str:
        return "".join(
            (
                "P" if self.path_control else "-",
                "E" if self.endpoint_control else "-",
                "L" if self.platform_control else "-",
            )
        )

    def with_layers(self, *, path: bool, endpoint: bool, platform: bool) -> "CensorRegime":
        return replace(
            self,
            name=f"ablation_{int(path)}{int(endpoint)}{int(platform)}",
            label=f"layers={int(path)}{int(endpoint)}{int(platform)}",
            path_control=path,
            endpoint_control=endpoint,
            platform_control=platform,
        )


@dataclass(frozen=True)
class NetworkCondition:
    name: str
    label: str
    latency_ms: float
    jitter_ms: float
    loss_rate: float
    bandwidth_mbps: float


WORKLOADS: Mapping[str, Workload] = {
    "text": Workload("text", 0.004, 1, 1.5, 5_000, 1.0, 0.06),
    "media": Workload("media", 2.0, 5, 3.0, 15_000, 0.8, 0.06),
    "file": Workload("file", 8.0, 10, 4.0, 30_000, 0.9, 0.06),
    "presence": Workload("presence", 0.001, 1, 1.0, 1_500, 1.0, 0.0),
    "realtime": Workload("realtime", 0.45, 12, 2.0, 450, 0.85, 0.04),
}


ARCHITECTURES: Mapping[str, Architecture] = {
    "direct_e2ee": Architecture(
        "direct_e2ee",
        "Direct E2EE",
        "Stable foreign service endpoints with an end-to-end content boundary.",
        endpoint_pool=6,
        endpoint_rotation_period=0,
        endpoint_rotation_fraction=0.0,
        protocol_rotation_period=0,
        protocol_diversity=0.03,
        passive_separability=0.30,
        probe_confirmation=0.18,
        discovery_rate=0.55,
        collateral_weight=0.25,
        transport_overhead=1.00,
        provider_controls_plaintext=False,
        provider_controls_delivery=False,
        domestically_permitted=False,
    ),
    "fixed_proxy": Architecture(
        "fixed_proxy",
        "Fixed App Proxy",
        "Application-integrated E2EE proxy with a small, stable endpoint set.",
        endpoint_pool=10,
        endpoint_rotation_period=0,
        endpoint_rotation_fraction=0.0,
        protocol_rotation_period=0,
        protocol_diversity=0.04,
        passive_separability=0.35,
        probe_confirmation=0.72,
        discovery_rate=0.32,
        collateral_weight=0.08,
        transport_overhead=1.12,
        provider_controls_plaintext=False,
        provider_controls_delivery=False,
        domestically_permitted=False,
    ),
    "generated_transport": Architecture(
        "generated_transport",
        "Generated Transport",
        "Per-deployment structured protocol diversity with moderate endpoint churn.",
        endpoint_pool=28,
        endpoint_rotation_period=8,
        endpoint_rotation_fraction=0.25,
        protocol_rotation_period=4,
        protocol_diversity=0.30,
        passive_separability=0.20,
        probe_confirmation=0.30,
        discovery_rate=0.17,
        collateral_weight=0.22,
        transport_overhead=1.16,
        provider_controls_plaintext=False,
        provider_controls_delivery=False,
        domestically_permitted=False,
    ),
    "ephemeral_relay": Architecture(
        "ephemeral_relay",
        "Ephemeral Relay",
        "Large relay population with frequent endpoint replacement and session recovery.",
        endpoint_pool=120,
        endpoint_rotation_period=2,
        endpoint_rotation_fraction=0.35,
        protocol_rotation_period=0,
        protocol_diversity=0.08,
        passive_separability=0.32,
        probe_confirmation=0.44,
        discovery_rate=0.10,
        collateral_weight=0.18,
        transport_overhead=1.24,
        provider_controls_plaintext=False,
        provider_controls_delivery=False,
        domestically_permitted=False,
    ),
    "platform_controlled": Architecture(
        "platform_controlled",
        "Permitted Platform",
        "Domestically permitted service whose provider terminates confidentiality and controls delivery.",
        endpoint_pool=12,
        endpoint_rotation_period=0,
        endpoint_rotation_fraction=0.0,
        protocol_rotation_period=0,
        protocol_diversity=0.02,
        passive_separability=0.10,
        probe_confirmation=0.05,
        discovery_rate=0.03,
        collateral_weight=0.85,
        transport_overhead=0.96,
        provider_controls_plaintext=True,
        provider_controls_delivery=True,
        domestically_permitted=True,
    ),
}


CENSOR_REGIMES: Mapping[str, CensorRegime] = {
    "passive_only": CensorRegime(
        "passive_only",
        "Passive only",
        path_control=True,
        endpoint_control=False,
        platform_control=False,
        adaptive_training=False,
        false_positive_cap=0.001,
        probe_budget=0,
        block_budget=0,
        retrain_interval=8,
        block_ttl=6,
        reputation_threshold=4,
        path_enforcement=0.92,
        platform_filter_rate=0.0,
    ),
    "path_endpoint": CensorRegime(
        "path_endpoint",
        "Path + endpoint",
        path_control=True,
        endpoint_control=True,
        platform_control=False,
        adaptive_training=False,
        false_positive_cap=0.001,
        probe_budget=3,
        block_budget=6,
        retrain_interval=8,
        block_ttl=8,
        reputation_threshold=3,
        path_enforcement=0.95,
        platform_filter_rate=0.0,
    ),
    "adaptive_cross_layer": CensorRegime(
        "adaptive_cross_layer",
        "Adaptive cross-layer",
        path_control=True,
        endpoint_control=True,
        platform_control=True,
        adaptive_training=True,
        false_positive_cap=0.001,
        probe_budget=5,
        block_budget=10,
        retrain_interval=3,
        block_ttl=10,
        reputation_threshold=3,
        path_enforcement=0.97,
        platform_filter_rate=0.80,
    ),
}


NETWORKS: Mapping[str, NetworkCondition] = {
    "stable": NetworkCondition("stable", "Stable broadband", 45, 8, 0.003, 45),
    "mobile": NetworkCondition("mobile", "Mobile-like", 110, 35, 0.025, 12),
    "impaired": NetworkCondition("impaired", "Impaired", 220, 80, 0.060, 4),
}


def validate_catalogue() -> None:
    for architecture in ARCHITECTURES.values():
        if architecture.endpoint_pool <= 0:
            raise ValueError(f"{architecture.name}: endpoint_pool must be positive")
        for value in (
            architecture.endpoint_rotation_fraction,
            architecture.protocol_diversity,
            architecture.passive_separability,
            architecture.probe_confirmation,
            architecture.discovery_rate,
            architecture.collateral_weight,
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{architecture.name}: probability outside [0, 1]")
    for regime in CENSOR_REGIMES.values():
        if not 0 < regime.false_positive_cap < 1:
            raise ValueError(f"{regime.name}: invalid false_positive_cap")


validate_catalogue()
