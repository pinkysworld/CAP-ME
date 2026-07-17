"""Analysis routines with deterministic uncertainty estimates.

The artifact treats seeds as independent simulation replicates. Confidence
intervals therefore quantify Monte Carlo variation under the declared model;
they are not confidence intervals for real national networks.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .io import read_csv, write_csv, write_json
from .model import ARCHITECTURES, WORKLOADS


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float


def _f(row: Mapping[str, str], key: str) -> float:
    return float(row[key])


def _i(row: Mapping[str, str], key: str) -> int:
    return int(row[key])


def bootstrap_mean(
    values: Iterable[float], *, seed: int = 73_051, repetitions: int = 2_000
) -> Interval:
    vector = np.asarray(list(values), dtype=float)
    if not len(vector):
        return Interval(math.nan, math.nan, math.nan)
    estimate = float(np.mean(vector))
    if len(vector) == 1:
        return Interval(estimate, estimate, estimate)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(vector), size=(repetitions, len(vector)))
    means = vector[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return Interval(estimate, float(low), float(high))


def _t50(epoch_availability: Mapping[int, float], windows: int = 3) -> tuple[int, bool]:
    epochs = sorted(epoch_availability)
    for index in range(0, len(epochs) - windows + 1):
        candidate = epochs[index : index + windows]
        if all(epoch_availability[epoch] < 0.5 for epoch in candidate):
            return candidate[0], True
    return (epochs[-1] + 1 if epochs else 0), False


def compute_run_metrics(rows: list[dict[str, str]], sustained_windows: int = 3) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["run_id"]].append(row)
    output: list[dict[str, object]] = []
    for run_id, run_rows in grouped.items():
        first = run_rows[0]
        epoch_function: dict[int, list[float]] = defaultdict(list)
        function_values: dict[str, list[float]] = defaultdict(list)
        epoch_once: dict[int, dict[str, str]] = {}
        for row in run_rows:
            epoch = _i(row, "epoch")
            availability = _f(row, "availability")
            epoch_function[epoch].append(availability)
            function_values[row["function"]].append(availability)
            epoch_once.setdefault(epoch, row)
        epoch_availability = {
            epoch: float(np.mean(values)) for epoch, values in epoch_function.items()
        }
        t50, failed = _t50(epoch_availability, sustained_windows)
        burns = sum(_i(row, "endpoint_burns_epoch") for row in epoch_once.values())
        endpoint_exposure = sum(_i(row, "endpoint_pool") for row in epoch_once.values())
        metric: dict[str, object] = {
            "run_id": run_id,
            "seed": _i(first, "seed"),
            "architecture": first["architecture"],
            "censor": first["censor"],
            "network": first["network"],
            "layer_mask": first["layer_mask"],
            "auac": float(np.mean(list(epoch_availability.values()))),
            "t50": t50,
            "t50_observed": int(failed),
            "endpoint_burns": burns,
            "endpoint_exposure_epochs": endpoint_exposure,
            "endpoint_burn_rate": burns / endpoint_exposure if endpoint_exposure else 0.0,
            "mean_tpr": float(np.mean([_f(row, "tpr") for row in epoch_once.values()])),
            "mean_fpr": float(np.mean([_f(row, "fpr") for row in epoch_once.values()])),
            "mean_precision": float(
                np.mean([_f(row, "precision_at_prevalence") for row in epoch_once.values()])
            ),
        }
        for function in WORKLOADS:
            metric[f"auac_{function}"] = float(np.mean(function_values[function]))
        output.append(metric)
    return sorted(output, key=lambda row: str(row["run_id"]))


def aggregate_run_metrics(run_metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in run_metrics:
        grouped[(str(row["architecture"]), str(row["censor"]), str(row["network"]))].append(row)
    output: list[dict[str, object]] = []
    for index, (key, rows) in enumerate(sorted(grouped.items())):
        architecture, censor, network = key
        auac = bootstrap_mean((float(row["auac"]) for row in rows), seed=10_000 + index)
        t50 = bootstrap_mean((float(row["t50"]) for row in rows), seed=20_000 + index)
        burn = bootstrap_mean(
            (float(row["endpoint_burn_rate"]) for row in rows), seed=30_000 + index
        )
        aggregate: dict[str, object] = {
            "architecture": architecture,
            "architecture_label": ARCHITECTURES[architecture].label,
            "censor": censor,
            "network": network,
            "replicates": len(rows),
            "auac": auac.estimate,
            "auac_ci_low": auac.low,
            "auac_ci_high": auac.high,
            "t50": t50.estimate,
            "t50_ci_low": t50.low,
            "t50_ci_high": t50.high,
            "t50_event_fraction": float(np.mean([float(row["t50_observed"]) for row in rows])),
            "endpoint_burn_rate": burn.estimate,
            "endpoint_burn_rate_ci_low": burn.low,
            "endpoint_burn_rate_ci_high": burn.high,
            "mean_tpr": float(np.mean([float(row["mean_tpr"]) for row in rows])),
            "mean_fpr": float(np.mean([float(row["mean_fpr"]) for row in rows])),
            "mean_precision": float(np.mean([float(row["mean_precision"]) for row in rows])),
        }
        for function_index, function in enumerate(WORKLOADS):
            interval = bootstrap_mean(
                (float(row[f"auac_{function}"]) for row in rows),
                seed=40_000 + index * 10 + function_index,
            )
            aggregate[f"auac_{function}"] = interval.estimate
            aggregate[f"auac_{function}_ci_low"] = interval.low
            aggregate[f"auac_{function}_ci_high"] = interval.high
        output.append(aggregate)
    return output


def sign_flip_pvalue(differences: Iterable[float], *, seed: int, repetitions: int = 30_000) -> float:
    vector = np.asarray(list(differences), dtype=float)
    if not len(vector):
        return math.nan
    observed = abs(float(np.mean(vector)))
    if np.allclose(vector, 0):
        return 1.0
    rng = np.random.default_rng(seed)
    exceed = 0
    batch = 2_000
    complete = 0
    while complete < repetitions:
        count = min(batch, repetitions - complete)
        signs = rng.choice(np.array([-1.0, 1.0]), size=(count, len(vector)))
        statistics = np.abs((signs * vector).mean(axis=1))
        exceed += int(np.sum(statistics >= observed))
        complete += count
    return (exceed + 1) / (repetitions + 1)


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    count = len(pvalues)
    order = sorted(range(count), key=lambda index: pvalues[index])
    adjusted = [math.nan] * count
    running = 1.0
    for reverse_rank, index in enumerate(reversed(order), start=1):
        rank = count - reverse_rank + 1
        candidate = min(1.0, pvalues[index] * count / rank)
        running = min(running, candidate)
        adjusted[index] = running
    return adjusted


def paired_contrasts(run_metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    lookup: dict[tuple[str, str, int, str], dict[str, object]] = {}
    for row in run_metrics:
        lookup[
            (
                str(row["architecture"]),
                str(row["network"]),
                int(row["seed"]),
                str(row["censor"]),
            )
        ] = row
    contrasts: list[dict[str, object]] = []
    for index, architecture in enumerate(ARCHITECTURES):
        for network in ("stable", "mobile", "impaired"):
            differences: list[float] = []
            seeds = sorted(
                {
                    seed
                    for arch, net, seed, censor in lookup
                    if arch == architecture
                    and net == network
                    and censor == "adaptive_cross_layer"
                }
            )
            for seed in seeds:
                passive = lookup.get((architecture, network, seed, "passive_only"))
                adaptive = lookup.get((architecture, network, seed, "adaptive_cross_layer"))
                if passive is not None and adaptive is not None:
                    differences.append(float(adaptive["auac"]) - float(passive["auac"]))
            if not differences:
                continue
            interval = bootstrap_mean(differences, seed=50_000 + index)
            contrasts.append(
                {
                    "architecture": architecture,
                    "network": network,
                    "contrast": "adaptive_cross_layer_minus_passive_only",
                    "pairs": len(differences),
                    "mean_difference": interval.estimate,
                    "ci_low": interval.low,
                    "ci_high": interval.high,
                    "p_value": sign_flip_pvalue(
                        differences, seed=60_000 + len(contrasts)
                    ),
                }
            )
    adjusted = benjamini_hochberg([float(row["p_value"]) for row in contrasts])
    for row, value in zip(contrasts, adjusted, strict=True):
        row["p_value_bh"] = value
    return contrasts


def _mask_to_set(mask: str) -> frozenset[str]:
    return frozenset(
        layer
        for character, layer in zip(mask, ("path", "endpoint", "platform"), strict=True)
        if character != "-"
    )


def shapley_attribution(ablation_run_metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    by_unit: dict[tuple[str, int], dict[frozenset[str], float]] = defaultdict(dict)
    for row in ablation_run_metrics:
        by_unit[(str(row["architecture"]), int(row["seed"]))][
            _mask_to_set(str(row["layer_mask"]))
        ] = float(row["auac"])
    layers = ("path", "endpoint", "platform")
    records: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (architecture, _seed), values in by_unit.items():
        if len(values) != 8 or frozenset() not in values:
            continue
        baseline = values[frozenset()]
        loss = {mask: baseline - availability for mask, availability in values.items()}
        for layer in layers:
            contribution = 0.0
            others = [item for item in layers if item != layer]
            for size in range(len(others) + 1):
                for subset_tuple in itertools.combinations(others, size):
                    subset = frozenset(subset_tuple)
                    weight = (
                        math.factorial(size)
                        * math.factorial(len(layers) - size - 1)
                        / math.factorial(len(layers))
                    )
                    contribution += weight * (
                        loss[subset | {layer}] - loss[subset]
                    )
            records[(architecture, layer)].append(contribution)
    output: list[dict[str, object]] = []
    for index, ((architecture, layer), values) in enumerate(sorted(records.items())):
        interval = bootstrap_mean(values, seed=70_000 + index)
        output.append(
            {
                "architecture": architecture,
                "architecture_label": ARCHITECTURES[architecture].label,
                "layer": layer,
                "replicates": len(values),
                "auac_loss_contribution": interval.estimate,
                "ci_low": interval.low,
                "ci_high": interval.high,
            }
        )
    return output


def aggregate_survival_curves(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    selected = [
        row
        for row in rows
        if row["censor"] == "adaptive_cross_layer" and row["network"] == "mobile"
    ]
    per_run_epoch: dict[tuple[str, int, str], list[float]] = defaultdict(list)
    for row in selected:
        per_run_epoch[
            (row["architecture"], _i(row, "epoch"), row["run_id"])
        ].append(_f(row, "availability"))
    grouped: dict[tuple[str, int], list[float]] = defaultdict(list)
    for (architecture, epoch, _run_id), values in per_run_epoch.items():
        grouped[(architecture, epoch)].append(float(np.mean(values)))
    output: list[dict[str, object]] = []
    for index, ((architecture, epoch), values) in enumerate(sorted(grouped.items())):
        interval = bootstrap_mean(values, seed=80_000 + index, repetitions=1_000)
        output.append(
            {
                "architecture": architecture,
                "architecture_label": ARCHITECTURES[architecture].label,
                "epoch": epoch,
                "availability": interval.estimate,
                "ci_low": interval.low,
                "ci_high": interval.high,
            }
        )
    return output


def analyze(raw_dir: Path, processed_dir: Path) -> dict[str, object]:
    observations = read_csv(raw_dir / "observations.csv")
    ablation_observations = read_csv(raw_dir / "ablation_observations.csv")
    run_metrics = compute_run_metrics(observations)
    ablation_run_metrics = compute_run_metrics(ablation_observations)
    aggregates = aggregate_run_metrics(run_metrics)
    contrasts = paired_contrasts(run_metrics)
    shapley = shapley_attribution(ablation_run_metrics)
    curves = aggregate_survival_curves(observations)
    hashes = {
        "run_metrics.csv": write_csv(processed_dir / "run_metrics.csv", run_metrics),
        "aggregate_metrics.csv": write_csv(
            processed_dir / "aggregate_metrics.csv", aggregates
        ),
        "paired_contrasts.csv": write_csv(
            processed_dir / "paired_contrasts.csv", contrasts
        ),
        "shapley_attribution.csv": write_csv(
            processed_dir / "shapley_attribution.csv", shapley
        ),
        "survival_curves.csv": write_csv(
            processed_dir / "survival_curves.csv", curves
        ),
    }
    summary = {
        "schema_version": 1,
        "synthetic_only": True,
        "uncertainty_interpretation": (
            "Intervals quantify simulation-seed variation under declared assumptions, "
            "not uncertainty about any real censor."
        ),
        "counts": {
            "runs": len(run_metrics),
            "ablation_runs": len(ablation_run_metrics),
            "aggregate_cells": len(aggregates),
            "paired_contrasts": len(contrasts),
        },
        "files": hashes,
    }
    write_json(processed_dir / "analysis_manifest.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(args.raw, args.processed)
    print(json.dumps(result["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
