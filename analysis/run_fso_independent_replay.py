#!/usr/bin/env python3
"""Generate and replay a separately coded synthetic trace process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from capme.fso.independent import generate_independent_trace
from capme.fso.study import run_study
from capme.io import read_csv, sha256_file, write_csv, write_json


ROOT = Path(__file__).resolve().parents[1]


def _find(rows: list[dict[str, str]], strategy: str) -> dict[str, str]:
    matches = [row for row in rows if row["strategy"] == strategy]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one aggregate row for {strategy}")
    return matches[0]


def run(config_path: Path, raw_dir: Path, processed_dir: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base_path = ROOT / str(config["base_replay_config"])
    base = json.loads(base_path.read_text(encoding="utf-8"))
    seeds = [int(value) for value in config["seeds"]]
    previously_used: set[int] = set()
    for path in (
        ROOT / "configs" / "study.json",
        ROOT / "configs" / "fso-confirmation-source.json",
        ROOT / "configs" / "fso-feedback-source.json",
    ):
        previously_used.update(json.loads(path.read_text(encoding="utf-8"))["seeds"])
    if set(seeds) & previously_used:
        raise ValueError("independent replay seeds overlap an earlier study")

    processed_dir.mkdir(parents=True, exist_ok=True)
    trace_path = processed_dir / "independent_trace.csv"
    trace_rows = generate_independent_trace(config)
    trace_hash = write_csv(trace_path, trace_rows)
    expected_rows = len(seeds) * len(config["architectures"]) * int(config["epochs"]) * 5
    if len(trace_rows) != expected_rows:
        raise ValueError("independent trace is not a complete grid")

    replay = dict(base)
    replay["schema_version"] = 2
    replay["source_trace"] = str(trace_path)
    replay["independent_trace_model"] = str(config_path.relative_to(ROOT))
    generated_config = processed_dir / "replay_config.json"
    replay_hash = write_json(generated_config, replay)
    study_manifest = run_study(generated_config, raw_dir, processed_dir)

    aggregates = read_csv(processed_dir / "aggregate_metrics.csv")
    contrasts = read_csv(processed_dir / "paired_contrasts.csv")
    by_baseline = {row["baseline"]: row for row in contrasts}
    primary = str(replay["primary_strategy"])
    summary = {
        "schema_version": 1,
        "synthetic_only": True,
        "primary_strategy": primary,
        "primary_auac": float(_find(aggregates, primary)["auac"]),
        "deadline_cost_failover_auac": float(
            _find(aggregates, "deadline_cost_failover")["auac"]
        ),
        "session_failover_auac": float(_find(aggregates, "session_failover")["auac"]),
        "fso_minus_deadline_cost_failover": float(
            by_baseline["deadline_cost_failover"]["mean_difference"]
        ),
        "fso_minus_deadline_cost_failover_ci": [
            float(by_baseline["deadline_cost_failover"]["ci_low"]),
            float(by_baseline["deadline_cost_failover"]["ci_high"]),
        ],
        "fso_minus_session_failover": float(
            by_baseline["session_failover"]["mean_difference"]
        ),
        "fso_minus_session_failover_ci": [
            float(by_baseline["session_failover"]["ci_low"]),
            float(by_baseline["session_failover"]["ci_high"]),
        ],
        "fso_minus_no_diversity": float(
            by_baseline["fso_no_diversity"]["mean_difference"]
        ),
        "fso_minus_no_diversity_ci": [
            float(by_baseline["fso_no_diversity"]["ci_low"]),
            float(by_baseline["fso_no_diversity"]["ci_high"]),
        ],
        "interpretation": config["interpretation"],
    }
    summary_path = processed_dir / "summary.json"
    summary_hash = write_json(summary_path, summary)
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "separately_coded_trace_generator": True,
        "imports_original_simulator": False,
        "shares_fso_replay_and_analysis": True,
        "config": str(config_path.relative_to(ROOT)),
        "config_sha256": sha256_file(config_path),
        "base_replay_config": str(base_path.relative_to(ROOT)),
        "base_replay_config_sha256": sha256_file(base_path),
        "seeds": seeds,
        "earlier_seeds_disjoint": True,
        "counts": {
            "trace_rows": len(trace_rows),
            **study_manifest["counts"],
        },
        "files": {
            "independent_trace.csv": trace_hash,
            "replay_config.json": replay_hash,
            "study_manifest.json": sha256_file(processed_dir / "study_manifest.json"),
            "summary.json": summary_hash,
        },
        "interpretation": config["interpretation"],
    }
    write_json(processed_dir / "independent_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "fso-independent-replay.json",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=ROOT / "results" / "raw" / "fso-independent-replay",
    )
    parser.add_argument(
        "--processed",
        type=Path,
        default=ROOT / "results" / "processed" / "fso" / "independent-replay",
    )
    args = parser.parse_args()
    manifest = run(args.config.resolve(), args.raw.resolve(), args.processed.resolve())
    print(json.dumps(manifest["counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
