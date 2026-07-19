"""Separately coded synthetic availability-trace generator.

This module intentionally does not import the CAP-ME detector, simulation, or
architecture model.  It supplies a compact latent-pressure/state-recovery
process for implementation-dependence checks; it is not an empirical censor
model.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping

from .types import FUNCTIONS


def _normal(*parts: object) -> float:
    material = "|".join(str(part) for part in parts).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return random.Random(seed).gauss(0.0, 1.0)


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def generate_independent_trace(config: Mapping[str, object]) -> list[dict[str, object]]:
    epochs = int(config["epochs"])
    seeds = [int(value) for value in config["seeds"]]
    pressure_config = dict(config["pressure"])
    architectures = dict(config["architectures"])
    functions = dict(config["functions"])
    if set(functions) != set(FUNCTIONS):
        raise ValueError("independent trace must define all messaging functions")
    if epochs < 2 or not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("independent trace requires unique seeds and at least two epochs")

    rows: list[dict[str, object]] = []
    for seed in seeds:
        pressure = float(pressure_config["initial"])
        pressures: list[float] = []
        for epoch in range(epochs):
            progress = epoch / (epochs - 1)
            target = float(pressure_config["trend_initial"]) + progress * (
                float(pressure_config["trend_final"])
                - float(pressure_config["trend_initial"])
            )
            memory = float(pressure_config["memory"])
            innovation = float(pressure_config["innovation_sd"]) * _normal(
                "independent-pressure", seed, epoch
            )
            pressure = _clip(memory * pressure + (1.0 - memory) * target + innovation, 0.0, 1.0)
            pressures.append(pressure)

        for architecture_name, raw_architecture in sorted(architectures.items()):
            architecture = dict(raw_architecture)
            health = _clip(
                float(architecture["initial_health"])
                + 0.02 * _normal("independent-health", seed, architecture_name),
                0.05,
                0.995,
            )
            renewal_period = int(architecture["renewal_period"])
            endpoint_pool = int(architecture["endpoint_pool"])
            for epoch, epoch_pressure in enumerate(pressures):
                renewal = (
                    float(architecture["renewal_boost"])
                    if renewal_period > 0 and epoch > 0 and epoch % renewal_period == 0
                    else 0.0
                )
                state_noise = 0.012 * _normal(
                    "independent-state", seed, architecture_name, epoch
                )
                health = _clip(
                    health
                    - float(architecture["exposure"]) * epoch_pressure
                    + float(architecture["recovery"]) * (1.0 - health)
                    + renewal
                    + state_noise,
                    0.03,
                    0.995,
                )
                for function in FUNCTIONS:
                    function_config = dict(functions[function])
                    availability_noise = float(
                        config["cell_availability_noise_sd"]
                    ) * _normal(
                        "independent-cell-availability",
                        seed,
                        architecture_name,
                        epoch,
                        function,
                    )
                    availability = _clip(
                        health
                        * float(function_config["availability_multiplier"])
                        + availability_noise,
                        0.005,
                        0.995,
                    )
                    latency_noise = float(config["cell_latency_noise_sd"]) * _normal(
                        "independent-cell-latency",
                        seed,
                        architecture_name,
                        epoch,
                        function,
                    )
                    completion_ms = max(
                        1.0,
                        float(architecture["latency_ms"])
                        * float(function_config["latency_multiplier"])
                        * (1.0 + float(architecture["latency_pressure"]) * epoch_pressure)
                        * math.exp(latency_noise),
                    )
                    blocked_fraction = _clip(1.0 - health, 0.0, 1.0)
                    rows.append(
                        {
                            "seed": seed,
                            "architecture": architecture_name,
                            "epoch": epoch,
                            "function": function,
                            "availability": availability,
                            "mean_completion_ms": completion_ms,
                            "blocked_fraction": blocked_fraction,
                            "burns_epoch": round(blocked_fraction * endpoint_pool),
                            "endpoint_pool": endpoint_pool,
                        }
                    )
    rows.sort(
        key=lambda row: (
            int(row["seed"]),
            str(row["architecture"]),
            int(row["epoch"]),
            str(row["function"]),
        )
    )
    return rows
