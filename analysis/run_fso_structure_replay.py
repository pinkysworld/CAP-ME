#!/usr/bin/env python3
"""Replay all FSO strategies across the four declared censor structures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from capme.analysis import bootstrap_mean
from capme.fso.study import run_study
from capme.io import read_csv, sha256_file, write_csv, write_json
from capme.model import ARCHITECTURES, NETWORKS, CensorRegime
from capme.simulation import SimulationConfig, run_simulation


def _trace_row(row: dict[str, object]) -> dict[str, object]:
    endpoint_pool = int(row["endpoint_pool"])
    return {
        "seed": int(row["seed"]),
        "architecture": str(row["architecture"]),
        "epoch": int(row["epoch"]),
        "function": str(row["function"]),
        "availability": float(row["availability"]),
        "mean_completion_ms": float(row["mean_completion_ms"]),
        "blocked_fraction": (
            int(row["blocked_endpoints"]) / endpoint_pool if endpoint_pool else 0.0
        ),
        "burns_epoch": int(row["endpoint_burns_epoch"]),
        "endpoint_pool": endpoint_pool,
    }


def _find(rows: list[dict[str, str]], strategy: str) -> dict[str, str]:
    matches = [row for row in rows if row["strategy"] == strategy]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one aggregate row for {strategy}")
    return matches[0]


def run(config_path: Path, raw_dir: Path, processed_dir: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_path = Path(config["source_config"])
    replay_path = Path(config["replay_config"])
    robustness_path = Path(config["robustness_config"])
    source = json.loads(source_path.read_text(encoding="utf-8"))
    replay_template = json.loads(replay_path.read_text(encoding="utf-8"))
    robustness = json.loads(robustness_path.read_text(encoding="utf-8"))

    seeds = [int(value) for value in source["seeds"]]
    simulation = SimulationConfig(**source["simulation"])
    network = NETWORKS[str(robustness["base_network"])]
    architectures = [str(value) for value in robustness["architectures"]]
    families = {
        str(row["name"]): CensorRegime(**row)
        for row in robustness["censor_models"]
    }
    structures = [str(value) for value in config["censor_structures"]]
    primary = str(config["primary_strategy"])
    if primary not in replay_template["strategies"]:
        raise ValueError("primary strategy is absent from replay template")
    if any(name not in families for name in structures):
        raise ValueError("structure replay names an unknown censor structure")

    summary_rows: list[dict[str, object]] = []
    source_hashes: dict[str, str] = {}
    replay_manifest_hashes: dict[str, str] = {}
    replay_config_hashes: dict[str, str] = {}
    total_source_rows = 0
    total_source_runs = 0
    total_decisions = 0

    for structure_index, structure in enumerate(structures):
        family = families[structure]
        trace_rows: list[dict[str, object]] = []
        for architecture_name in architectures:
            architecture = ARCHITECTURES[architecture_name]
            for seed in seeds:
                result = run_simulation(
                    architecture, family, network, seed, simulation
                )
                trace_rows.extend(_trace_row(row) for row in result.rows)
                total_source_runs += 1
        trace_rows.sort(
            key=lambda row: (
                int(row["seed"]),
                str(row["architecture"]),
                int(row["epoch"]),
                str(row["function"]),
            )
        )
        trace_path = processed_dir / structure / "lane_trace_probabilities.csv"
        source_hashes[str(trace_path.relative_to(processed_dir))] = write_csv(
            trace_path, trace_rows
        )
        total_source_rows += len(trace_rows)

        replay_config = dict(replay_template)
        replay_config.update(
            {
                "source_trace": str(trace_path),
                "primary_strategy": primary,
                "censor_structure": structure,
                "traffic_volume_coupling": bool(config["traffic_volume_coupling"]),
            }
        )
        generated_config = processed_dir / structure / "replay_config.json"
        replay_config_hashes[
            str(generated_config.relative_to(processed_dir))
        ] = write_json(generated_config, replay_config)
        manifest = run_study(
            generated_config,
            raw_dir / structure,
            processed_dir / structure,
        )
        manifest_path = processed_dir / structure / "study_manifest.json"
        replay_manifest_hashes[
            str(manifest_path.relative_to(processed_dir))
        ] = sha256_file(manifest_path)
        total_decisions += int(manifest["counts"]["operation_decisions"])

        aggregates = read_csv(processed_dir / structure / "aggregate_metrics.csv")
        run_metrics = read_csv(processed_dir / structure / "run_metrics.csv")
        contrasts = read_csv(processed_dir / structure / "paired_contrasts.csv")
        fso = _find(aggregates, primary)
        session = _find(aggregates, "session_failover")
        generated = _find(aggregates, "generated_only")
        primary_contrast = next(
            row for row in contrasts if row["baseline"] == "session_failover"
        )
        by_seed = {
            (row["strategy"], int(row["seed"])): float(row["auac"])
            for row in run_metrics
        }
        session_minus_generated = [
            by_seed[("session_failover", seed)]
            - by_seed[("generated_only", seed)]
            for seed in seeds
        ]
        session_interval = bootstrap_mean(
            session_minus_generated, seed=880_000 + structure_index
        )
        ordering_fraction = sum(
            by_seed[(primary, seed)] >= by_seed[("session_failover", seed)]
            >= by_seed[("generated_only", seed)]
            for seed in seeds
        ) / len(seeds)
        summary_rows.append(
            {
                "censor_structure": structure,
                "structure_label": family.label,
                "seeds": len(seeds),
                "fso_auac": float(fso["auac"]),
                "fso_ci_low": float(fso["auac_ci_low"]),
                "fso_ci_high": float(fso["auac_ci_high"]),
                "session_failover_auac": float(session["auac"]),
                "session_failover_ci_low": float(session["auac_ci_low"]),
                "session_failover_ci_high": float(session["auac_ci_high"]),
                "generated_only_auac": float(generated["auac"]),
                "generated_only_ci_low": float(generated["auac_ci_low"]),
                "generated_only_ci_high": float(generated["auac_ci_high"]),
                "fso_minus_session": float(primary_contrast["mean_difference"]),
                "fso_minus_session_ci_low": float(primary_contrast["ci_low"]),
                "fso_minus_session_ci_high": float(primary_contrast["ci_high"]),
                "session_minus_generated": session_interval.estimate,
                "session_minus_generated_ci_low": session_interval.low,
                "session_minus_generated_ci_high": session_interval.high,
                "mean_ordering_fso_ge_session_ge_generated": int(
                    float(fso["auac"])
                    >= float(session["auac"])
                    >= float(generated["auac"])
                ),
                "seed_ordering_fraction": ordering_fraction,
            }
        )

    summary_path = processed_dir / "structure_summary.csv"
    summary_hash = write_csv(summary_path, summary_rows)
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "source_config": str(source_path),
        "source_config_sha256": sha256_file(source_path),
        "replay_config": str(replay_path),
        "replay_config_sha256": sha256_file(replay_path),
        "robustness_config": str(robustness_path),
        "robustness_config_sha256": sha256_file(robustness_path),
        "structures": structures,
        "architectures": architectures,
        "seeds": seeds,
        "primary_strategy": primary,
        "strategies": list(replay_template["strategies"]),
        "structure_parameterization": config["structure_parameterization"],
        "traffic_volume_coupling": bool(config["traffic_volume_coupling"]),
        "counts": {
            "source_simulation_runs": total_source_runs,
            "source_trace_rows": total_source_rows,
            "strategy_seed_runs": len(structures)
            * len(seeds)
            * len(replay_template["strategies"]),
            "operation_decisions": total_decisions,
        },
        "files": {
            "structure_summary.csv": summary_hash,
            **source_hashes,
            **replay_config_hashes,
            **replay_manifest_hashes,
        },
        "interpretation": config["interpretation"],
    }
    write_json(processed_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("configs/fso-structure-replay.json")
    )
    parser.add_argument(
        "--raw", type=Path, default=Path("results/raw/fso-structure-replay")
    )
    parser.add_argument(
        "--processed",
        type=Path,
        default=Path("results/processed/fso/structure-replay"),
    )
    args = parser.parse_args()
    manifest = run(args.config, args.raw, args.processed)
    print(json.dumps(manifest["counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
