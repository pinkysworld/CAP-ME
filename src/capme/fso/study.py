"""Trace preparation and deterministic FSO comparative study."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from capme.analysis import benjamini_hochberg, bootstrap_mean, sign_flip_pvalue
from capme.io import read_csv, sha256_file, write_csv, write_json
from capme.model import WORKLOADS

from .scheduler import Scheduler, build_scheduler
from .types import FUNCTIONS, LaneProfile, Operation, lane_profiles_from_config

TRACE_ARCHITECTURES = {
    "direct_e2ee",
    "fixed_proxy",
    "generated_transport",
    "ephemeral_relay",
    "platform_controlled",
}


def _interval_interpretation(seed_count: int) -> str:
    return (
        "Intervals cover replay and resampling variation across "
        f"the {seed_count} declared synthetic seeds. They are not population "
        "intervals for a deployed censor or country."
    )


def prepare_lane_traces(source: Path, output: Path) -> dict[str, object]:
    """Extract compact adaptive-mobile carrier traces from CAP-ME raw output."""

    rows: list[dict[str, object]] = []
    with source.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (
                row["censor"] != "adaptive_cross_layer"
                or row["network"] != "mobile"
                or row["architecture"] not in TRACE_ARCHITECTURES
            ):
                continue
            endpoint_pool = int(row["endpoint_pool"])
            rows.append(
                {
                    "seed": int(row["seed"]),
                    "architecture": row["architecture"],
                    "epoch": int(row["epoch"]),
                    "function": row["function"],
                    "availability": float(row["availability"]),
                    "mean_completion_ms": float(row["mean_completion_ms"]),
                    "blocked_fraction": (
                        int(row["blocked_endpoints"]) / endpoint_pool if endpoint_pool else 0.0
                    ),
                    "burns_epoch": int(row["endpoint_burns_epoch"]),
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
    seeds = sorted({int(row["seed"]) for row in rows})
    epochs = sorted({int(row["epoch"]) for row in rows})
    if not seeds or epochs != list(range(len(epochs))):
        raise ValueError("trace selection has no seeds or non-contiguous epochs")
    expected_keys = {
        (seed, architecture, epoch, function)
        for seed in seeds
        for architecture in TRACE_ARCHITECTURES
        for epoch in epochs
        for function in FUNCTIONS
    }
    actual_keys = {
        (
            int(row["seed"]),
            str(row["architecture"]),
            int(row["epoch"]),
            str(row["function"]),
        )
        for row in rows
    }
    if len(rows) != len(expected_keys) or actual_keys != expected_keys:
        raise ValueError(
            "trace selection is not an exact seed/architecture/epoch/function grid: "
            f"expected {len(expected_keys)} rows, found {len(rows)}"
        )
    digest = write_csv(output, rows)
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "source": str(source),
        "source_sha256": sha256_file(source),
        "output": str(output),
        "output_sha256": digest,
        "rows": len(rows),
        "seeds": seeds,
        "epochs": epochs,
        "selection": {
            "censor": "adaptive_cross_layer",
            "network": "mobile",
            "architectures": sorted(TRACE_ARCHITECTURES),
        },
    }
    write_json(output.with_name("lane_trace_manifest.json"), manifest)
    return manifest


def _unit_uniform(*parts: object) -> float:
    material = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return (value + 0.5) / 2**64


def _normal(*parts: object) -> float:
    seed = int.from_bytes(
        hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()[:8],
        "big",
    )
    return random.Random(seed).gauss(0.0, 1.0)


def _load_trace(path: Path) -> tuple[dict[tuple[int, str, int, str], dict[str, float]], list[int]]:
    lookup: dict[tuple[int, str, int, str], dict[str, float]] = {}
    seeds: set[int] = set()
    for row in read_csv(path):
        key = (int(row["seed"]), row["architecture"], int(row["epoch"]), row["function"])
        lookup[key] = {
            "availability": float(row["availability"]),
            "completion_ms": float(row["mean_completion_ms"]),
            "blocked_fraction": float(row["blocked_fraction"]),
            "burns_epoch": float(row["burns_epoch"]),
            "endpoint_pool": float(row["endpoint_pool"]),
        }
        seeds.add(int(row["seed"]))
    return lookup, sorted(seeds)


def _realized_lane_outcome(
    *,
    seed: int,
    epoch: int,
    function: str,
    operation_index: int,
    lane: LaneProfile,
    trace: Mapping[tuple[int, str, int, str], Mapping[str, float]],
    correlation_weight: float,
) -> tuple[bool, float, float]:
    row = trace[(seed, lane.architecture, epoch, function)]
    domain_draw = _unit_uniform(seed, epoch, function, operation_index, lane.failure_domain, "domain")
    lane_draw = _unit_uniform(seed, epoch, function, operation_index, lane.name, "lane")
    selector = _unit_uniform(seed, epoch, function, operation_index, lane.name, "mixture")
    outcome_draw = domain_draw if selector < correlation_weight else lane_draw
    success = outcome_draw < row["availability"]
    jitter = max(
        0.55,
        min(1.85, 1.0 + 0.16 * _normal(seed, epoch, function, operation_index, lane.name, "latency")),
    )
    completion = max(0.1, row["completion_ms"] * jitter)
    failure_timeout = max(lane.latency_prior_ms * 1.7, completion)
    return success, completion, failure_timeout


def _execute_plan(
    *,
    scheduler: Scheduler,
    operation: Operation,
    seed: int,
    epoch: int,
    operation_index: int,
    profiles: Mapping[str, LaneProfile],
    trace: Mapping[tuple[int, str, int, str], Mapping[str, float]],
    correlation_weight: float,
    outcome_cache: dict[tuple[int, int, str, int, str], tuple[bool, float, float]],
) -> dict[str, object]:
    decision = scheduler.plan(operation)
    outcomes: dict[str, tuple[bool, float, float]] = {}
    for lane_name in decision.lanes:
        key = (seed, epoch, operation.function, operation_index, lane_name)
        if key not in outcome_cache:
            outcome_cache[key] = _realized_lane_outcome(
                seed=seed,
                epoch=epoch,
                function=operation.function,
                operation_index=operation_index,
                lane=profiles[lane_name],
                trace=trace,
                correlation_weight=correlation_weight,
            )
        outcomes[lane_name] = outcome_cache[key]
    attempted: list[str] = []
    delivered: list[tuple[str, float]] = []
    if decision.dispatch_mode == "sequential":
        elapsed = 0.0
        for lane_name in decision.lanes:
            success, latency, timeout = outcomes[lane_name]
            attempted.append(lane_name)
            extra_survival = math.exp(-elapsed / operation.deadline_ms)
            fallback_draw = _unit_uniform(
                seed,
                epoch,
                operation.function,
                operation_index,
                lane_name,
                "fallback-delay",
            )
            if success and fallback_draw < extra_survival:
                delivered.append((lane_name, elapsed + latency))
                break
            elapsed += min(timeout, operation.deadline_ms * 0.45)
            if elapsed >= operation.deadline_ms:
                break
    elif decision.dispatch_mode == "hot_standby":
        primary = decision.lanes[0]
        primary_success, primary_latency, _ = outcomes[primary]
        attempted.append(primary)
        fallback_at = min(operation.deadline_ms * 0.22, profiles[primary].latency_prior_ms * 0.65)
        if primary_success and primary_latency <= fallback_at:
            delivered.append((primary, primary_latency))
        else:
            for lane_name in decision.lanes[1:]:
                attempted.append(lane_name)
                success, latency, _ = outcomes[lane_name]
                extra_survival = math.exp(-fallback_at / operation.deadline_ms)
                fallback_draw = _unit_uniform(
                    seed,
                    epoch,
                    operation.function,
                    operation_index,
                    lane_name,
                    "hot-standby-delay",
                )
                if success and fallback_draw < extra_survival:
                    delivered.append((lane_name, fallback_at + latency))
            if primary_success:
                delivered.append((primary, primary_latency))
    else:
        attempted.extend(decision.lanes)
        for lane_name in decision.lanes:
            success, latency, _ = outcomes[lane_name]
            if success:
                delivered.append((lane_name, latency))

    delivered.sort(key=lambda item: item[1])
    complete = len(delivered) >= decision.threshold
    completion_ms = delivered[decision.threshold - 1][1] if complete else operation.deadline_ms
    for lane_name in attempted:
        raw_success, latency, _ = outcomes[lane_name]
        scheduler.update(
            lane_name,
            operation.function,
            success=raw_success,
            latency_ms=latency,
        )

    payload_bytes = max(1, len(operation.payload))
    shard_plaintext = math.ceil((payload_bytes + 9) / decision.threshold)
    bytes_per_attempt = shard_plaintext + 55
    bytes_sent = bytes_per_attempt * len(attempted)
    endpoint_risk = sum(1.0 - profiles[name].endpoint_resilience for name in attempted)
    return {
        "success": int(complete),
        "completion_ms": completion_ms,
        "bytes_sent": bytes_sent,
        "payload_bytes": payload_bytes,
        "overhead_ratio": bytes_sent / payload_bytes,
        "attempted_lanes": tuple(attempted),
        "endpoint_risk_exposure": endpoint_risk,
        "provider_controlled_attempts": sum(
            int(profiles[name].provider_controls_delivery) for name in attempted
        ),
        "threshold": decision.threshold,
        "total_shards": decision.total_shards,
    }


def _t50(cells: list[dict[str, object]], sustained: int = 3) -> tuple[int, bool]:
    by_epoch: dict[int, list[float]] = defaultdict(list)
    for row in cells:
        by_epoch[int(row["epoch"])].append(float(row["availability"]))
    averages = {epoch: float(np.mean(values)) for epoch, values in by_epoch.items()}
    epochs = sorted(averages)
    for index in range(len(epochs) - sustained + 1):
        candidate = epochs[index : index + sustained]
        if all(averages[epoch] < 0.5 for epoch in candidate):
            return candidate[0], True
    return epochs[-1] + 1, False


def _compute_run_metrics(cells: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in cells:
        grouped[(str(row["strategy"]), int(row["seed"]))].append(row)
    output: list[dict[str, object]] = []
    for (strategy, seed), rows in sorted(grouped.items()):
        t50, observed = _t50(rows)
        payload = sum(int(row["payload_bytes"]) for row in rows)
        sent = sum(int(row["bytes_sent"]) for row in rows)
        successful_latencies = [
            float(row["mean_completion_ms"])
            for row in rows
            if float(row["availability"]) > 0
        ]
        metric: dict[str, object] = {
            "strategy": strategy,
            "seed": seed,
            "auac": float(np.mean([float(row["availability"]) for row in rows])),
            "t50": t50,
            "t50_observed": int(observed),
            "byte_overhead": sent / payload,
            "mean_completion_ms": float(np.mean(successful_latencies)),
            "endpoint_risk_exposure": sum(float(row["endpoint_risk_exposure"]) for row in rows),
            "provider_controlled_attempts": sum(int(row["provider_controlled_attempts"]) for row in rows),
        }
        for function in FUNCTIONS:
            selected = [row for row in rows if row["function"] == function]
            metric[f"auac_{function}"] = float(
                np.mean([float(row["availability"]) for row in selected])
            )
        output.append(metric)
    return output


def _aggregate_metrics(run_metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in run_metrics:
        grouped[str(row["strategy"])].append(row)
    output: list[dict[str, object]] = []
    for index, (strategy, rows) in enumerate(sorted(grouped.items())):
        result: dict[str, object] = {"strategy": strategy, "replicates": len(rows)}
        for metric_index, metric in enumerate(
            ("auac", "t50", "byte_overhead", "mean_completion_ms", "endpoint_risk_exposure")
        ):
            interval = bootstrap_mean(
                [float(row[metric]) for row in rows],
                seed=710_000 + index * 100 + metric_index,
            )
            result[metric] = interval.estimate
            result[f"{metric}_ci_low"] = interval.low
            result[f"{metric}_ci_high"] = interval.high
        result["t50_event_fraction"] = float(
            np.mean([float(row["t50_observed"]) for row in rows])
        )
        result["provider_controlled_attempts"] = sum(
            int(row["provider_controlled_attempts"]) for row in rows
        )
        for function_index, function in enumerate(FUNCTIONS):
            interval = bootstrap_mean(
                [float(row[f"auac_{function}"]) for row in rows],
                seed=720_000 + index * 100 + function_index,
            )
            result[f"auac_{function}"] = interval.estimate
            result[f"auac_{function}_ci_low"] = interval.low
            result[f"auac_{function}_ci_high"] = interval.high
        output.append(result)
    return output


def _paired_contrasts(run_metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    lookup = {
        (str(row["strategy"]), int(row["seed"])): row for row in run_metrics
    }
    strategies = sorted({strategy for strategy, _ in lookup if strategy != "fso"})
    rows: list[dict[str, object]] = []
    for index, strategy in enumerate(strategies):
        seeds = sorted(
            seed for candidate, seed in lookup if candidate == strategy and ("fso", seed) in lookup
        )
        differences = [
            float(lookup[("fso", seed)]["auac"]) - float(lookup[(strategy, seed)]["auac"])
            for seed in seeds
        ]
        interval = bootstrap_mean(differences, seed=730_000 + index)
        rows.append(
            {
                "comparison": f"fso-minus-{strategy}",
                "baseline": strategy,
                "paired_replicates": len(seeds),
                "mean_difference": interval.estimate,
                "ci_low": interval.low,
                "ci_high": interval.high,
                "p_value": sign_flip_pvalue(differences, seed=740_000 + index),
            }
        )
    adjusted = benjamini_hochberg([float(row["p_value"]) for row in rows])
    for row, value in zip(rows, adjusted, strict=True):
        row["p_value_bh"] = value
    return rows


def _survival_curves(cells: list[dict[str, object]]) -> list[dict[str, object]]:
    seed_epoch: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    for row in cells:
        seed_epoch[(str(row["strategy"]), int(row["seed"]), int(row["epoch"]))].append(
            float(row["availability"])
        )
    grouped: dict[tuple[str, int], list[float]] = defaultdict(list)
    for (strategy, _seed, epoch), values in seed_epoch.items():
        grouped[(strategy, epoch)].append(float(np.mean(values)))
    output: list[dict[str, object]] = []
    for index, ((strategy, epoch), values) in enumerate(sorted(grouped.items())):
        interval = bootstrap_mean(values, seed=750_000 + index)
        output.append(
            {
                "strategy": strategy,
                "epoch": epoch,
                "availability": interval.estimate,
                "ci_low": interval.low,
                "ci_high": interval.high,
            }
        )
    return output


def run_study(config_path: Path, raw_dir: Path, processed_dir: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    trace_path = Path(config["source_trace"])
    trace, seeds = _load_trace(trace_path)
    profiles_list = lane_profiles_from_config(config["lane_instances"])
    profiles = {profile.name: profile for profile in profiles_list}
    strategies = [str(value) for value in config["strategies"]]
    epochs = int(config["epochs"])
    operations_per_function = int(config["operations_per_function"])
    correlation_weight = float(config["correlation_weight"])
    strict_trust = bool(config["strict_trust"])
    payloads = {
        function: bytes(max(1, int(WORKLOADS[function].payload_mb * 1_000_000)))
        for function in FUNCTIONS
    }
    cells: list[dict[str, object]] = []
    lane_counts: Counter[tuple[str, str]] = Counter()
    outcome_cache: dict[
        tuple[int, int, str, int, str], tuple[bool, float, float]
    ] = {}
    for strategy in strategies:
        for seed in seeds:
            scheduler = build_scheduler(
                strategy,
                profiles_list,
                strict_trust=strict_trust,
                seed=seed + 91_000,
                correlation_weight=correlation_weight,
            )
            for epoch in range(epochs):
                for function in FUNCTIONS:
                    workload = WORKLOADS[function]
                    payload = payloads[function]
                    payload_bytes = len(payload)
                    successes = 0
                    bytes_sent = 0
                    endpoint_risk = 0.0
                    provider_attempts = 0
                    completion_times: list[float] = []
                    threshold_sum = 0
                    shard_sum = 0
                    for operation_index in range(operations_per_function):
                        operation = Operation(
                            function,
                            payload,
                            workload.deadline_ms,
                            strict_trust=strict_trust,
                        )
                        result = _execute_plan(
                            scheduler=scheduler,
                            operation=operation,
                            seed=seed,
                            epoch=epoch,
                            operation_index=operation_index,
                            profiles=profiles,
                            trace=trace,
                            correlation_weight=correlation_weight,
                            outcome_cache=outcome_cache,
                        )
                        successes += int(result["success"])
                        bytes_sent += int(result["bytes_sent"])
                        endpoint_risk += float(result["endpoint_risk_exposure"])
                        provider_attempts += int(result["provider_controlled_attempts"])
                        threshold_sum += int(result["threshold"])
                        shard_sum += int(result["total_shards"])
                        if result["success"]:
                            completion_times.append(float(result["completion_ms"]))
                        for lane in result["attempted_lanes"]:
                            lane_counts[(strategy, str(lane))] += 1
                    cells.append(
                        {
                            "strategy": strategy,
                            "seed": seed,
                            "epoch": epoch,
                            "function": function,
                            "attempts": operations_per_function,
                            "successes": successes,
                            "availability": successes / operations_per_function,
                            "payload_bytes": payload_bytes * operations_per_function,
                            "bytes_sent": bytes_sent,
                            "byte_overhead": bytes_sent / (payload_bytes * operations_per_function),
                            "mean_completion_ms": (
                                float(np.mean(completion_times))
                                if completion_times
                                else workload.deadline_ms
                            ),
                            "endpoint_risk_exposure": endpoint_risk,
                            "provider_controlled_attempts": provider_attempts,
                            "mean_threshold": threshold_sum / operations_per_function,
                            "mean_total_shards": shard_sum / operations_per_function,
                        }
                    )
    run_metrics = _compute_run_metrics(cells)
    aggregates = _aggregate_metrics(run_metrics)
    contrasts = _paired_contrasts(run_metrics)
    curves = _survival_curves(cells)
    selection_rows = [
        {"strategy": strategy, "lane": lane, "attempts": count}
        for (strategy, lane), count in sorted(lane_counts.items())
    ]
    raw_hashes = {
        "observations.csv": write_csv(raw_dir / "observations.csv", cells),
    }
    processed_hashes = {
        "run_metrics.csv": write_csv(processed_dir / "run_metrics.csv", run_metrics),
        "aggregate_metrics.csv": write_csv(processed_dir / "aggregate_metrics.csv", aggregates),
        "paired_contrasts.csv": write_csv(processed_dir / "paired_contrasts.csv", contrasts),
        "survival_curves.csv": write_csv(processed_dir / "survival_curves.csv", curves),
        "lane_selection.csv": write_csv(processed_dir / "lane_selection.csv", selection_rows),
    }
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "source_trace": str(trace_path),
        "source_trace_sha256": sha256_file(trace_path),
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "seeds": seeds,
        "strategies": strategies,
        "counts": {
            "trace_rows": len(trace),
            "cell_rows": len(cells),
            "strategy_seed_runs": len(run_metrics),
            "operation_decisions": len(strategies)
            * len(seeds)
            * epochs
            * len(FUNCTIONS)
            * operations_per_function,
        },
        "common_random_numbers": True,
        "strict_trust": strict_trust,
        "provider_controlled_attempts": int(
            sum(int(row["provider_controlled_attempts"]) for row in cells)
        ),
        "raw_files": raw_hashes,
        "processed_files": processed_hashes,
        "interpretation": _interval_interpretation(len(seeds)),
    }
    write_json(raw_dir / "manifest.json", manifest)
    write_json(processed_dir / "study_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare-traces")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    study = sub.add_parser("run")
    study.add_argument("--config", type=Path, required=True)
    study.add_argument("--raw", type=Path, required=True)
    study.add_argument("--processed", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare-traces":
        result = prepare_lane_traces(args.source, args.output)
        print(json.dumps({"rows": result["rows"], "output": str(args.output)}))
    else:
        result = run_study(args.config, args.raw, args.processed)
        print(json.dumps(result["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
