#!/usr/bin/env python3
"""Run deterministic global sensitivity for FSO and its matched baseline."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from capme.fso.study import run_study
from capme.io import read_csv, sha256_file, write_csv, write_json
from capme.robustness import ParameterRange, latin_hypercube, partial_rank_correlation


ROOT = Path(__file__).resolve().parents[1]


def _find(rows: list[dict[str, str]], strategy: str) -> dict[str, str]:
    matches = [row for row in rows if row["strategy"] == strategy]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one aggregate row for {strategy}")
    return matches[0]


def _shift_probability(value: float, logit_shift: float) -> float:
    clipped = min(1.0 - 1e-9, max(1e-9, value))
    logit = math.log(clipped / (1.0 - clipped)) + logit_shift
    return 1.0 / (1.0 + math.exp(-logit))


def _design_rows(config: dict[str, object]) -> list[dict[str, object]]:
    parameters = [ParameterRange(**row) for row in config["parameters"]]
    unit = latin_hypercube(
        int(config["design_points"]), len(parameters), int(config["design_seed"])
    )
    rows: list[dict[str, object]] = []
    if bool(config["include_declared_base_point"]):
        rows.append(
            {
                "design_id": "design-base",
                "is_declared_base": 1,
                "cost_scale": 1.0,
                "latency_scale": 1.0,
                "burn_weight": 0.16,
                "correlation_penalty_weight": 0.10,
                "scheduler_correlation_weight": 0.35,
                "outcome_correlation_weight": 0.35,
                "survival_prior_logit_shift": 0.0,
                "latency_prior_scale": 1.0,
            }
        )
    for index, unit_row in enumerate(unit):
        row: dict[str, object] = {
            "design_id": f"design-{index:04d}",
            "is_declared_base": 0,
        }
        for parameter, unit_value in zip(parameters, unit_row, strict=True):
            row[parameter.name] = parameter.sample(float(unit_value))
        rows.append(row)
    return rows


def _replay_config(
    base: dict[str, object],
    sensitivity: dict[str, object],
    design: dict[str, object],
    trace_path: Path,
) -> dict[str, object]:
    replay = dict(base)
    replay["schema_version"] = 2
    replay["source_trace"] = str(trace_path)
    replay["strategies"] = list(sensitivity["strategies"])
    replay["primary_strategy"] = str(sensitivity["primary_strategy"])
    replay["outcome_correlation_weight"] = float(
        design["outcome_correlation_weight"]
    )
    replay["scheduler_correlation_weight"] = float(
        design["scheduler_correlation_weight"]
    )
    replay.pop("correlation_weight", None)

    base_parameters = dict(base["scheduler_parameters"])
    replay["scheduler_parameters"] = {
        "cost_weights": {
            function: float(value) * float(design["cost_scale"])
            for function, value in dict(base_parameters["cost_weights"]).items()
        },
        "latency_weights": {
            function: float(value) * float(design["latency_scale"])
            for function, value in dict(base_parameters["latency_weights"]).items()
        },
        "burn_weight": float(design["burn_weight"]),
        "correlation_penalty_weight": float(
            design["correlation_penalty_weight"]
        ),
    }
    replay["lane_instances"] = [
        {
            **dict(lane),
            "survival_prior": _shift_probability(
                float(lane["survival_prior"]),
                float(design["survival_prior_logit_shift"]),
            ),
            "latency_prior_ms": float(lane["latency_prior_ms"])
            * float(design["latency_prior_scale"]),
        }
        for lane in base["lane_instances"]
    ]
    replay["sensitivity_design_id"] = str(design["design_id"])
    return replay


def _seed_ordering_fraction(
    path: Path, primary: str, comparison: str
) -> float:
    rows = read_csv(path)
    lookup = {
        (row["strategy"], int(row["seed"])): float(row["auac"])
        for row in rows
    }
    seeds = sorted(seed for strategy, seed in lookup if strategy == primary)
    return sum(
        lookup[(primary, seed)] > lookup[(comparison, seed)] for seed in seeds
    ) / len(seeds)


def run(config_path: Path, raw_dir: Path, processed_dir: Path) -> dict[str, object]:
    sensitivity = json.loads(config_path.read_text(encoding="utf-8"))
    base_path = ROOT / str(sensitivity["base_replay_config"])
    base = json.loads(base_path.read_text(encoding="utf-8"))
    trace_path = ROOT / str(sensitivity["source_trace"])
    trace_seed_count = len({int(row["seed"]) for row in read_csv(trace_path)})
    primary = str(sensitivity["primary_strategy"])
    comparison = str(sensitivity["comparison_strategy"])
    designs = _design_rows(sensitivity)

    processed_dir.mkdir(parents=True, exist_ok=True)
    design_path = processed_dir / "design.csv"
    design_hash = write_csv(design_path, designs)
    result_rows: list[dict[str, object]] = []
    replay_hashes: dict[str, str] = {}
    manifest_hashes: dict[str, str] = {}
    total_decisions = 0

    for design in designs:
        design_id = str(design["design_id"])
        design_directory = processed_dir / design_id
        generated_config = design_directory / "replay_config.json"
        replay = _replay_config(base, sensitivity, design, trace_path)
        replay_hashes[str(generated_config.relative_to(processed_dir))] = write_json(
            generated_config, replay
        )
        study_manifest = run_study(
            generated_config,
            raw_dir / design_id,
            design_directory,
        )
        total_decisions += int(study_manifest["counts"]["operation_decisions"])
        manifest_path = design_directory / "study_manifest.json"
        manifest_hashes[str(manifest_path.relative_to(processed_dir))] = sha256_file(
            manifest_path
        )

        aggregates = read_csv(design_directory / "aggregate_metrics.csv")
        contrasts = read_csv(design_directory / "paired_contrasts.csv")
        primary_row = _find(aggregates, primary)
        comparison_row = _find(aggregates, comparison)
        contrast = next(row for row in contrasts if row["baseline"] == comparison)
        row: dict[str, object] = dict(design)
        row.update(
            {
                "primary_auac": float(primary_row["auac"]),
                "comparison_auac": float(comparison_row["auac"]),
                "mean_difference": float(contrast["mean_difference"]),
                "difference_ci_low": float(contrast["ci_low"]),
                "difference_ci_high": float(contrast["ci_high"]),
                "primary_byte_overhead": float(primary_row["byte_overhead"]),
                "comparison_byte_overhead": float(comparison_row["byte_overhead"]),
                "byte_overhead_difference": float(primary_row["byte_overhead"])
                - float(comparison_row["byte_overhead"]),
                "seed_ordering_fraction": _seed_ordering_fraction(
                    design_directory / "run_metrics.csv", primary, comparison
                ),
            }
        )
        for function in ("text", "presence", "media", "file", "realtime"):
            row[f"difference_{function}"] = float(primary_row[f"auac_{function}"]) - float(
                comparison_row[f"auac_{function}"]
            )
        result_rows.append(row)

    results_path = processed_dir / "sensitivity_results.csv"
    results_hash = write_csv(results_path, result_rows)
    parameter_names = [str(row["name"]) for row in sensitivity["parameters"]]
    lhs_rows = [row for row in result_rows if not int(row["is_declared_base"])]
    matrix = np.asarray(
        [[float(row[name]) for name in parameter_names] for row in lhs_rows]
    )
    outcome = np.asarray([float(row["mean_difference"]) for row in lhs_rows])
    prcc_rows = [
        {
            "parameter": name,
            "design_points": len(lhs_rows),
            "prcc_with_fso_minus_baseline": partial_rank_correlation(
                matrix, outcome, index
            ),
        }
        for index, name in enumerate(parameter_names)
    ]
    prcc_path = processed_dir / "sensitivity_prcc.csv"
    prcc_hash = write_csv(prcc_path, prcc_rows)

    differences = np.asarray([float(row["mean_difference"]) for row in result_rows])
    base_result = next(row for row in result_rows if int(row["is_declared_base"]))
    summary = {
        "schema_version": 1,
        "synthetic_only": True,
        "design_points_including_base": len(result_rows),
        "latin_hypercube_points": len(lhs_rows),
        "base_mean_difference": float(base_result["mean_difference"]),
        "mean_difference_min": float(np.min(differences)),
        "mean_difference_median": float(np.median(differences)),
        "mean_difference_max": float(np.max(differences)),
        "fraction_mean_difference_positive": float(np.mean(differences > 0.0)),
        "fraction_ci_excludes_zero_positive": float(
            np.mean([float(row["difference_ci_low"]) > 0.0 for row in result_rows])
        ),
        "fraction_ci_excludes_zero_negative": float(
            np.mean([float(row["difference_ci_high"]) < 0.0 for row in result_rows])
        ),
        "interpretation": sensitivity["interpretation"],
    }
    summary_path = processed_dir / "summary.json"
    summary_hash = write_json(summary_path, summary)
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "config": str(config_path.relative_to(ROOT)),
        "config_sha256": sha256_file(config_path),
        "base_replay_config": str(base_path.relative_to(ROOT)),
        "base_replay_config_sha256": sha256_file(base_path),
        "source_trace": str(trace_path.relative_to(ROOT)),
        "source_trace_sha256": sha256_file(trace_path),
        "primary_strategy": primary,
        "comparison_strategy": comparison,
        "parameter_names": parameter_names,
        "counts": {
            "design_points_including_base": len(result_rows),
            "latin_hypercube_points": len(lhs_rows),
            "strategy_seed_runs": len(result_rows)
            * len(sensitivity["strategies"])
            * trace_seed_count,
            "operation_decisions": total_decisions,
        },
        "files": {
            "design.csv": design_hash,
            "sensitivity_results.csv": results_hash,
            "sensitivity_prcc.csv": prcc_hash,
            "summary.json": summary_hash,
            **replay_hashes,
            **manifest_hashes,
        },
        "interpretation": sensitivity["interpretation"],
    }
    write_json(processed_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "fso-sensitivity.json"
    )
    parser.add_argument(
        "--raw", type=Path, default=ROOT / "results" / "raw" / "fso-sensitivity"
    )
    parser.add_argument(
        "--processed",
        type=Path,
        default=ROOT / "results" / "processed" / "fso" / "sensitivity",
    )
    args = parser.parse_args()
    manifest = run(args.config.resolve(), args.raw.resolve(), args.processed.resolve())
    print(json.dumps(manifest["counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
