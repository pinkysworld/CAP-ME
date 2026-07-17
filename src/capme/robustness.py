"""Global model-uncertainty study for the CAP-ME simulator.

This module deliberately separates two uncertainty sources:

* structurally different, author-declared censor models and parameter draws;
* Monte Carlo variation from common replicate seeds within each model draw.

The resulting intervals describe the declared model ensemble.  They are not
confidence intervals for a deployed national censor.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .io import sha256_file, write_csv, write_json
from .model import ARCHITECTURES, NETWORKS, Architecture, CensorRegime, NetworkCondition
from .simulation import SimulationConfig, run_simulation


@dataclass(frozen=True)
class ParameterRange:
    name: str
    low: float
    high: float
    scale: str = "linear"

    def sample(self, unit_value: float) -> float:
        if not 0.0 <= unit_value <= 1.0:
            raise ValueError(f"{self.name}: unit sample is outside [0, 1]")
        if self.scale == "linear":
            return self.low + (self.high - self.low) * unit_value
        if self.scale == "log":
            if self.low <= 0 or self.high <= 0:
                raise ValueError(f"{self.name}: logarithmic bounds must be positive")
            return math.exp(math.log(self.low) + (math.log(self.high) - math.log(self.low)) * unit_value)
        if self.scale == "integer":
            return float(round(self.low + (self.high - self.low) * unit_value))
        raise ValueError(f"{self.name}: unsupported scale {self.scale!r}")


def load_robustness_config(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    required = {
        "architectures",
        "base_network",
        "censor_models",
        "design_points",
        "design_seed",
        "parameters",
        "replicate_seeds",
        "simulation",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"robustness config is missing keys: {sorted(missing)}")
    if int(config["design_points"]) < 2:
        raise ValueError("design_points must be at least two")
    if not config["replicate_seeds"]:
        raise ValueError("replicate_seeds must not be empty")
    if len(set(config["replicate_seeds"])) != len(config["replicate_seeds"]):
        raise ValueError("replicate_seeds must be unique")
    parameters = [ParameterRange(**item) for item in config["parameters"]]
    if len({item.name for item in parameters}) != len(parameters):
        raise ValueError("uncertainty parameter names must be unique")
    known_parameters = {
        "architecture_passive_separability_multiplier",
        "architecture_discovery_rate_multiplier",
        "architecture_probe_confirmation_multiplier",
        "architecture_endpoint_pool_multiplier",
        "architecture_rotation_speed_multiplier",
        "architecture_protocol_diversity_multiplier",
        "architecture_transport_overhead_multiplier",
        "censor_false_positive_cap",
        "censor_path_enforcement",
        "censor_budget_multiplier",
        "censor_block_ttl_multiplier",
        "censor_retrain_interval",
        "censor_platform_filter_rate",
        "network_latency_multiplier",
        "network_loss_multiplier",
        "network_bandwidth_multiplier",
    }
    unknown = {item.name for item in parameters} - known_parameters
    if unknown:
        raise ValueError(f"unknown uncertainty parameters: {sorted(unknown)}")
    for architecture in config["architectures"]:
        if architecture not in ARCHITECTURES:
            raise ValueError(f"unknown architecture: {architecture}")
    if config["base_network"] not in NETWORKS:
        raise ValueError(f"unknown base network: {config['base_network']}")
    for item in config["censor_models"]:
        CensorRegime(**item)
    SimulationConfig(**config["simulation"]).validate()
    return config


def latin_hypercube(points: int, dimensions: int, seed: int) -> np.ndarray:
    """Return a deterministic stratified Latin-hypercube design."""

    if points < 2 or dimensions < 1:
        raise ValueError("Latin-hypercube design requires at least two points and one dimension")
    rng = np.random.default_rng(seed)
    design = np.empty((points, dimensions), dtype=float)
    for column in range(dimensions):
        strata = rng.permutation(points)
        design[:, column] = (strata + rng.random(points)) / points
    return design


def generate_design(config: Mapping[str, object]) -> list[dict[str, object]]:
    parameters = [ParameterRange(**item) for item in config["parameters"]]
    unit_design = latin_hypercube(
        int(config["design_points"]), len(parameters), int(config["design_seed"])
    )
    rows: list[dict[str, object]] = []
    for index, unit_row in enumerate(unit_design):
        row: dict[str, object] = {"design_id": f"design-{index:04d}"}
        for parameter, unit_value in zip(parameters, unit_row, strict=True):
            row[parameter.name] = parameter.sample(float(unit_value))
        rows.append(row)
    return rows


def _clip_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def apply_uncertainty(
    architecture: Architecture,
    censor: CensorRegime,
    network: NetworkCondition,
    values: Mapping[str, object],
) -> tuple[Architecture, CensorRegime, NetworkCondition]:
    """Apply one explicit uncertainty draw to a simulator scenario."""

    def value(name: str, default: float = 1.0) -> float:
        return float(values.get(name, default))

    rotation_period = architecture.endpoint_rotation_period
    if rotation_period > 0:
        rotation_period = max(
            1,
            round(
                rotation_period
                / max(value("architecture_rotation_speed_multiplier"), 1e-9)
            ),
        )
    adjusted_architecture = replace(
        architecture,
        endpoint_pool=max(
            1,
            round(
                architecture.endpoint_pool
                * value("architecture_endpoint_pool_multiplier")
            ),
        ),
        endpoint_rotation_period=rotation_period,
        passive_separability=_clip_probability(
            architecture.passive_separability
            * value("architecture_passive_separability_multiplier")
        ),
        discovery_rate=_clip_probability(
            architecture.discovery_rate
            * value("architecture_discovery_rate_multiplier")
        ),
        probe_confirmation=_clip_probability(
            architecture.probe_confirmation
            * value("architecture_probe_confirmation_multiplier")
        ),
        protocol_diversity=_clip_probability(
            architecture.protocol_diversity
            * value("architecture_protocol_diversity_multiplier")
        ),
        transport_overhead=max(
            0.01,
            architecture.transport_overhead
            * value("architecture_transport_overhead_multiplier"),
        ),
    )
    budget_multiplier = value("censor_budget_multiplier")
    adjusted_censor = replace(
        censor,
        false_positive_cap=value(
            "censor_false_positive_cap", censor.false_positive_cap
        ),
        path_enforcement=_clip_probability(
            value("censor_path_enforcement", censor.path_enforcement)
        ),
        probe_budget=max(0, round(censor.probe_budget * budget_multiplier)),
        block_budget=max(0, round(censor.block_budget * budget_multiplier)),
        block_ttl=max(
            1,
            round(censor.block_ttl * value("censor_block_ttl_multiplier")),
        ),
        retrain_interval=max(
            1,
            round(value("censor_retrain_interval", censor.retrain_interval)),
        ),
        platform_filter_rate=_clip_probability(
            value("censor_platform_filter_rate", censor.platform_filter_rate)
        ),
    )
    adjusted_network = replace(
        network,
        name=f"robustness-{network.name}",
        latency_ms=max(1.0, network.latency_ms * value("network_latency_multiplier")),
        jitter_ms=max(0.0, network.jitter_ms * value("network_latency_multiplier")),
        loss_rate=_clip_probability(network.loss_rate * value("network_loss_multiplier")),
        bandwidth_mbps=max(
            0.01, network.bandwidth_mbps * value("network_bandwidth_multiplier")
        ),
    )
    return adjusted_architecture, adjusted_censor, adjusted_network


def _t50(epoch_availability: Mapping[int, float], windows: int) -> tuple[int, bool]:
    epochs = sorted(epoch_availability)
    for index in range(len(epochs) - windows + 1):
        candidate = epochs[index : index + windows]
        if all(epoch_availability[epoch] < 0.5 for epoch in candidate):
            return candidate[0], True
    return (epochs[-1] + 1 if epochs else 0), False


def summarize_simulation(
    rows: Iterable[Mapping[str, object]], sustained_windows: int
) -> dict[str, object]:
    rows = list(rows)
    epoch_values: dict[int, list[float]] = defaultdict(list)
    function_values: dict[str, list[float]] = defaultdict(list)
    epoch_once: dict[int, Mapping[str, object]] = {}
    attempts = successes = 0
    failure_counts = {
        "path_failures": 0,
        "endpoint_failures": 0,
        "platform_failures": 0,
        "network_failures": 0,
    }
    completion_times: list[float] = []
    for row in rows:
        epoch = int(row["epoch"])
        availability = float(row["availability"])
        epoch_values[epoch].append(availability)
        function_values[str(row["function"])].append(availability)
        epoch_once.setdefault(epoch, row)
        attempts += int(row["attempts"])
        successes += int(row["successes"])
        for name in failure_counts:
            failure_counts[name] += int(row[name])
        completion = float(row["mean_completion_ms"])
        if math.isfinite(completion):
            completion_times.append(completion)
    per_epoch = {
        epoch: float(np.mean(values)) for epoch, values in epoch_values.items()
    }
    t50, t50_observed = _t50(per_epoch, sustained_windows)
    result: dict[str, object] = {
        "auac": float(np.mean(list(per_epoch.values()))),
        "t50": t50,
        "t50_observed": int(t50_observed),
        "attempts": attempts,
        "successes": successes,
        "mean_completion_ms": float(np.mean(completion_times)) if completion_times else math.nan,
        "endpoint_burn_rate": (
            sum(int(row["endpoint_burns_epoch"]) for row in epoch_once.values())
            / max(1, sum(int(row["endpoint_pool"]) for row in epoch_once.values()))
        ),
    }
    for name, count in failure_counts.items():
        result[name] = count
        result[f"{name}_fraction"] = count / attempts if attempts else 0.0
    for function, values in sorted(function_values.items()):
        result[f"auac_{function}"] = float(np.mean(values))
    return result


def _effective_row(
    design_id: str,
    family: str,
    architecture: Architecture,
    censor: CensorRegime,
    network: NetworkCondition,
) -> dict[str, object]:
    row: dict[str, object] = {
        "design_id": design_id,
        "censor_model": family,
        "architecture": architecture.name,
    }
    row.update({f"architecture_{key}": value for key, value in asdict(architecture).items()})
    row.update({f"censor_{key}": value for key, value in asdict(censor).items()})
    row.update({f"network_{key}": value for key, value in asdict(network).items()})
    return row


def run_robustness_study(config_path: Path, output_dir: Path) -> dict[str, object]:
    config = load_robustness_config(config_path)
    design = generate_design(config)
    simulation = SimulationConfig(**config["simulation"])
    base_network = NETWORKS[str(config["base_network"])]
    families = [CensorRegime(**item) for item in config["censor_models"]]
    run_rows: list[dict[str, object]] = []
    effective_rows: list[dict[str, object]] = []
    run_index = 0
    for design_row in design:
        design_id = str(design_row["design_id"])
        for family in families:
            for architecture_name in config["architectures"]:
                architecture, censor, network = apply_uncertainty(
                    ARCHITECTURES[str(architecture_name)], family, base_network, design_row
                )
                effective_rows.append(
                    _effective_row(design_id, family.name, architecture, censor, network)
                )
                for seed in config["replicate_seeds"]:
                    result = run_simulation(
                        architecture, censor, network, int(seed), simulation
                    )
                    metrics = summarize_simulation(
                        result.rows, sustained_windows=simulation.sustained_windows
                    )
                    run_rows.append(
                        {
                            "run_id": f"robustness-{run_index:06d}",
                            "design_id": design_id,
                            "censor_model": family.name,
                            "architecture": architecture.name,
                            "seed": int(seed),
                            **metrics,
                        }
                    )
                    run_index += 1
    design_hash = write_csv(output_dir / "design.csv", design)
    effective_hash = write_csv(output_dir / "effective_parameters.csv", effective_rows)
    run_hash = write_csv(output_dir / "run_metrics.csv", run_rows)
    analysis = analyze_robustness(
        design,
        run_rows,
        families,
        [str(item) for item in config["architectures"]],
        [ParameterRange(**item).name for item in config["parameters"]],
        output_dir,
        bootstrap_repetitions=int(config.get("bootstrap_repetitions", 100)),
    )
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "design": "stratified_latin_hypercube",
        "design_points": len(design),
        "censor_models": [item.name for item in families],
        "architectures": list(config["architectures"]),
        "replicate_seeds": list(config["replicate_seeds"]),
        "run_count": len(run_rows),
        "uncertainty_interpretation": (
            "Quantiles and sensitivities describe the declared synthetic model ensemble; "
            "they do not estimate uncertainty for a deployed national censor."
        ),
        "files": {
            "design.csv": design_hash,
            "effective_parameters.csv": effective_hash,
            "run_metrics.csv": run_hash,
            **analysis,
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def _mean_rows(run_rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in run_rows:
        groups[
            (str(row["design_id"]), str(row["censor_model"]), str(row["architecture"]))
        ].append(row)
    skip = {"run_id", "design_id", "censor_model", "architecture", "seed"}
    output: list[dict[str, object]] = []
    for key, rows in sorted(groups.items()):
        design_id, family, architecture = key
        record: dict[str, object] = {
            "design_id": design_id,
            "censor_model": family,
            "architecture": architecture,
            "replicates": len(rows),
        }
        for field in rows[0]:
            if field in skip:
                continue
            values = np.asarray([float(row[field]) for row in rows], dtype=float)
            record[field] = float(np.mean(values))
            if field == "auac":
                record["auac_seed_sd"] = (
                    float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
                )
        output.append(record)
    return output


def _quantile_summary(
    design_rows: list[dict[str, object]], families: list[str], architectures: list[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    by_cell = {
        (str(row["design_id"]), str(row["censor_model"]), str(row["architecture"])): row
        for row in design_rows
    }
    first_counts: dict[tuple[str, str], float] = defaultdict(float)
    rank_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    eligible_first_counts: dict[tuple[str, str], float] = defaultdict(float)
    eligible_rank_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    eligible_architectures = [
        architecture
        for architecture in architectures
        if not ARCHITECTURES[architecture].provider_controls_delivery
    ]
    design_ids = sorted({str(row["design_id"]) for row in design_rows})
    for family in families:
        for design_id in design_ids:
            cells = [by_cell[(design_id, family, architecture)] for architecture in architectures]
            scores = np.asarray([float(row["auac"]) for row in cells])
            maximum = float(np.max(scores))
            winners = np.flatnonzero(np.isclose(scores, maximum))
            for index, architecture in enumerate(architectures):
                rank = 1.0 + float(np.sum(scores > scores[index]))
                rank_values[(family, architecture)].append(rank)
                if index in winners:
                    first_counts[(family, architecture)] += 1.0 / len(winners)
            eligible_cells = [
                by_cell[(design_id, family, architecture)]
                for architecture in eligible_architectures
            ]
            eligible_scores = np.asarray(
                [float(row["auac"]) for row in eligible_cells]
            )
            eligible_maximum = float(np.max(eligible_scores))
            eligible_winners = np.flatnonzero(
                np.isclose(eligible_scores, eligible_maximum)
            )
            for index, architecture in enumerate(eligible_architectures):
                rank = 1.0 + float(
                    np.sum(eligible_scores > eligible_scores[index])
                )
                eligible_rank_values[(family, architecture)].append(rank)
                if index in eligible_winners:
                    eligible_first_counts[(family, architecture)] += (
                        1.0 / len(eligible_winners)
                    )
    for row in design_rows:
        grouped[(str(row["censor_model"]), str(row["architecture"]))].append(row)
    output: list[dict[str, object]] = []
    for family in families:
        for architecture in architectures:
            rows = grouped[(family, architecture)]
            values = np.asarray([float(row["auac"]) for row in rows], dtype=float)
            quantiles = np.quantile(values, [0.05, 0.25, 0.50, 0.75, 0.95])
            output.append(
                {
                    "censor_model": family,
                    "architecture": architecture,
                    "design_points": len(rows),
                    "auac_mean": float(np.mean(values)),
                    "auac_q05": float(quantiles[0]),
                    "auac_q25": float(quantiles[1]),
                    "auac_median": float(quantiles[2]),
                    "auac_q75": float(quantiles[3]),
                    "auac_q95": float(quantiles[4]),
                    "rank_first_fraction_all": first_counts[(family, architecture)]
                    / len(rows),
                    "median_rank_all": float(
                        np.median(rank_values[(family, architecture)])
                    ),
                    "rank_first_fraction_trust_eligible": (
                        eligible_first_counts[(family, architecture)] / len(rows)
                        if architecture in eligible_architectures
                        else math.nan
                    ),
                    "median_rank_trust_eligible": (
                        float(
                            np.median(
                                eligible_rank_values[(family, architecture)]
                            )
                        )
                        if architecture in eligible_architectures
                        else math.nan
                    ),
                }
            )
    return output


def _pairwise_ordering(
    design_rows: list[dict[str, object]], families: list[str], architectures: list[str]
) -> list[dict[str, object]]:
    lookup = {
        (str(row["design_id"]), str(row["censor_model"]), str(row["architecture"])): float(row["auac"])
        for row in design_rows
    }
    design_ids = sorted({str(row["design_id"]) for row in design_rows})
    output: list[dict[str, object]] = []
    for family in families:
        for left_index, left in enumerate(architectures):
            for right in architectures[left_index + 1 :]:
                differences = np.asarray(
                    [
                        lookup[(design_id, family, left)]
                        - lookup[(design_id, family, right)]
                        for design_id in design_ids
                    ]
                )
                output.append(
                    {
                        "censor_model": family,
                        "left_architecture": left,
                        "right_architecture": right,
                        "design_points": len(differences),
                        "probability_left_higher": float(np.mean(differences > 0)),
                        "probability_tie": float(np.mean(np.isclose(differences, 0))),
                        "median_difference": float(np.median(differences)),
                        "q05_difference": float(np.quantile(differences, 0.05)),
                        "q95_difference": float(np.quantile(differences, 0.95)),
                    }
                )
    return output


def _rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0 + 1.0
        start = end
    return ranks


def partial_rank_correlation(matrix: np.ndarray, outcome: np.ndarray, index: int) -> float:
    if matrix.ndim != 2 or outcome.ndim != 1 or len(matrix) != len(outcome):
        raise ValueError("invalid PRCC inputs")
    if len(outcome) <= matrix.shape[1] + 2:
        return math.nan
    ranked_x = np.column_stack([_rank(matrix[:, column]) for column in range(matrix.shape[1])])
    ranked_y = _rank(outcome)
    target = ranked_x[:, index]
    controls = np.delete(ranked_x, index, axis=1)
    controls = np.column_stack([np.ones(len(outcome)), controls])
    target_residual = target - controls @ np.linalg.lstsq(controls, target, rcond=None)[0]
    outcome_residual = ranked_y - controls @ np.linalg.lstsq(controls, ranked_y, rcond=None)[0]
    if np.std(target_residual) == 0 or np.std(outcome_residual) == 0:
        return math.nan
    return float(np.corrcoef(target_residual, outcome_residual)[0, 1])


def _parameter_active(parameter: str, family: CensorRegime, architecture: Architecture) -> bool:
    if parameter in {
        "architecture_discovery_rate_multiplier",
        "architecture_probe_confirmation_multiplier",
        "architecture_endpoint_pool_multiplier",
    }:
        return family.endpoint_control
    if parameter == "architecture_rotation_speed_multiplier":
        return (
            architecture.endpoint_rotation_period > 0
            and (family.path_control or family.endpoint_control)
        )
    if parameter in {
        "architecture_passive_separability_multiplier",
        "architecture_protocol_diversity_multiplier",
        "censor_false_positive_cap",
    }:
        return family.path_control or family.endpoint_control
    if parameter in {"censor_path_enforcement"}:
        return family.path_control
    if parameter in {"censor_budget_multiplier", "censor_block_ttl_multiplier"}:
        return family.endpoint_control
    if parameter == "censor_retrain_interval":
        return family.adaptive_training
    if parameter == "censor_platform_filter_rate":
        return family.platform_control and architecture.provider_controls_delivery
    return True


def _sensitivity_rows(
    design: list[dict[str, object]],
    design_rows: list[dict[str, object]],
    families: list[CensorRegime],
    architectures: list[str],
    parameters: list[str],
    bootstrap_repetitions: int,
) -> list[dict[str, object]]:
    design_ids = [str(row["design_id"]) for row in design]
    matrix = np.asarray(
        [[float(row[parameter]) for parameter in parameters] for row in design], dtype=float
    )
    lookup = {
        (str(row["design_id"]), str(row["censor_model"]), str(row["architecture"])): float(row["auac"])
        for row in design_rows
    }
    output: list[dict[str, object]] = []
    for family_index, family in enumerate(families):
        for architecture_index, architecture_name in enumerate(architectures):
            outcome = np.asarray(
                [lookup[(design_id, family.name, architecture_name)] for design_id in design_ids]
            )
            active_indices = [
                index
                for index, parameter in enumerate(parameters)
                if _parameter_active(
                    parameter, family, ARCHITECTURES[architecture_name]
                )
            ]
            active_matrix = matrix[:, active_indices]
            for parameter_index, parameter in enumerate(parameters):
                active = parameter_index in active_indices
                active_index = (
                    active_indices.index(parameter_index) if active else -1
                )
                estimate = (
                    partial_rank_correlation(active_matrix, outcome, active_index)
                    if active
                    else math.nan
                )
                boot: list[float] = []
                if math.isfinite(estimate) and bootstrap_repetitions > 0:
                    rng = np.random.default_rng(
                        910_000 + family_index * 10_000 + architecture_index * 100 + parameter_index
                    )
                    for _ in range(bootstrap_repetitions):
                        indices = rng.integers(0, len(outcome), size=len(outcome))
                        value = partial_rank_correlation(
                            active_matrix[indices], outcome[indices], active_index
                        )
                        if math.isfinite(value):
                            boot.append(value)
                if boot:
                    low, high = np.quantile(np.asarray(boot), [0.025, 0.975])
                else:
                    low = high = math.nan
                output.append(
                    {
                        "censor_model": family.name,
                        "architecture": architecture_name,
                        "parameter": parameter,
                        "structurally_active": int(active),
                        "prcc": estimate,
                        "bootstrap_ci_low": float(low),
                        "bootstrap_ci_high": float(high),
                        "bootstrap_valid": len(boot),
                    }
                )
    return output


def _variance_components(
    run_rows: list[dict[str, object]], families: list[str], architectures: list[str]
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in run_rows:
        grouped[(str(row["censor_model"]), str(row["architecture"]))][
            str(row["design_id"])
        ].append(float(row["auac"]))
    output: list[dict[str, object]] = []
    for family in families:
        for architecture in architectures:
            cells = grouped[(family, architecture)]
            means = np.asarray([np.mean(values) for values in cells.values()])
            within_values = [
                float(np.var(values, ddof=1)) for values in cells.values() if len(values) > 1
            ]
            within = float(np.mean(within_values)) if within_values else 0.0
            replicate_count = len(next(iter(cells.values())))
            observed_between = float(np.var(means, ddof=1)) if len(means) > 1 else 0.0
            model_component = max(0.0, observed_between - within / replicate_count)
            total = model_component + within
            output.append(
                {
                    "censor_model": family,
                    "architecture": architecture,
                    "design_points": len(cells),
                    "replicates_per_design": replicate_count,
                    "observed_variance_of_design_means": observed_between,
                    "within_design_seed_variance": within,
                    "model_variance_component": model_component,
                    "model_variance_fraction": model_component / total if total else 0.0,
                    "seed_variance_fraction": within / total if total else 0.0,
                }
            )
    return output


def analyze_robustness(
    design: list[dict[str, object]],
    run_rows: list[dict[str, object]],
    families: list[CensorRegime],
    architectures: list[str],
    parameters: list[str],
    output_dir: Path,
    *,
    bootstrap_repetitions: int,
) -> dict[str, str]:
    family_names = [family.name for family in families]
    design_metrics = _mean_rows(run_rows)
    summaries = _quantile_summary(design_metrics, family_names, architectures)
    orderings = _pairwise_ordering(design_metrics, family_names, architectures)
    sensitivities = _sensitivity_rows(
        design,
        design_metrics,
        families,
        architectures,
        parameters,
        bootstrap_repetitions,
    )
    variances = _variance_components(run_rows, family_names, architectures)
    return {
        "design_metrics.csv": write_csv(output_dir / "design_metrics.csv", design_metrics),
        "robustness_summary.csv": write_csv(
            output_dir / "robustness_summary.csv", summaries
        ),
        "pairwise_ordering.csv": write_csv(
            output_dir / "pairwise_ordering.csv", orderings
        ),
        "global_sensitivity_prcc.csv": write_csv(
            output_dir / "global_sensitivity_prcc.csv", sensitivities
        ),
        "variance_components.csv": write_csv(
            output_dir / "variance_components.csv", variances
        ),
    }
