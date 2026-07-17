#!/usr/bin/env python3
"""Apply the prospectively frozen decision rule to the feedback evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

from capme.io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _added_commit(path: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--reverse",
            "--",
            str(path.relative_to(ROOT)),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    commits = [line for line in result.stdout.splitlines() if line]
    if not commits:
        raise ValueError("feedback evaluation config must be committed before execution")
    return commits[0]


def analyze(
    processed: Path, source_config: Path, evaluation_config: Path
) -> dict[str, object]:
    source = json.loads(source_config.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_config.read_text(encoding="utf-8"))
    earlier = set(json.loads((ROOT / "configs" / "study.json").read_text())["seeds"])
    earlier.update(
        json.loads(
            (ROOT / "configs" / "fso-confirmation-source.json").read_text()
        )["seeds"]
    )
    seeds = [int(seed) for seed in source["seeds"]]
    if len(seeds) != 12 or len(set(seeds)) != len(seeds):
        raise ValueError("feedback audit requires 12 unique frozen seeds")
    if set(seeds) & earlier:
        raise ValueError("feedback audit seeds overlap development or confirmation seeds")
    if evaluation["strategies"] != ["fso", "fso_no_feedback"]:
        raise ValueError("feedback audit strategies changed after freezing")

    manifest = json.loads((processed / "study_manifest.json").read_text())
    if manifest["seeds"] != seeds:
        raise ValueError("feedback result seeds do not match the frozen source config")
    if manifest["strategies"] != evaluation["strategies"]:
        raise ValueError("feedback result strategies do not match the frozen plan")
    if manifest["source_trace_sha256"] != sha256_file(
        processed / "lane_trace_probabilities.csv"
    ):
        raise ValueError("feedback source trace hash mismatch")

    aggregates = {row["strategy"]: row for row in _rows(processed / "aggregate_metrics.csv")}
    contrasts = {
        row["baseline"]: row for row in _rows(processed / "paired_contrasts.csv")
    }
    contrast = contrasts["fso_no_feedback"]
    difference = float(contrast["mean_difference"])
    low = float(contrast["ci_low"])
    high = float(contrast["ci_high"])
    if low > 0.0:
        classification = "supported_benefit_in_declared_model"
        recommendation = "enabled"
    elif high < 0.0:
        classification = "harm_in_declared_model"
        recommendation = "disabled"
    else:
        classification = "inconclusive_no_benefit_claim"
        recommendation = "disabled"

    record: dict[str, object] = {
        "schema_version": 1,
        "synthetic_only": True,
        "prospectively_frozen": True,
        "frozen_config_commit": _added_commit(evaluation_config.resolve()),
        "frozen_before_execution_utc": evaluation["frozen_before_execution_utc"],
        "source_config": str(source_config.relative_to(ROOT)),
        "source_config_sha256": sha256_file(source_config),
        "evaluation_config": str(evaluation_config.relative_to(ROOT)),
        "evaluation_config_sha256": sha256_file(evaluation_config),
        "seeds": seeds,
        "development_and_evaluation_seeds_disjoint": True,
        "paired_replicates": int(contrast["paired_replicates"]),
        "primary_estimand": evaluation["frozen_analysis_plan"]["primary_estimand"],
        "fso_minus_no_feedback_auac": difference,
        "confidence_interval_95": [low, high],
        "p_value": float(contrast["p_value"]),
        "classification": classification,
        "recommended_feedback_default": recommendation,
        "auac": {
            name: float(aggregates[name]["auac"])
            for name in ("fso", "fso_no_feedback")
        },
        "byte_overhead": {
            name: float(aggregates[name]["byte_overhead"])
            for name in ("fso", "fso_no_feedback")
        },
        "interpretation": (
            "This decision applies only to the declared synthetic trace model. "
            "It is not evidence about a deployed censor or population."
        ),
    }
    write_json(processed / "feedback_audit.json", record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--processed",
        type=Path,
        default=ROOT / "results" / "processed" / "fso" / "feedback-evaluation",
    )
    parser.add_argument(
        "--source-config",
        type=Path,
        default=ROOT / "configs" / "fso-feedback-source.json",
    )
    parser.add_argument(
        "--evaluation-config",
        type=Path,
        default=ROOT / "configs" / "fso-feedback-evaluation.json",
    )
    args = parser.parse_args()
    record = analyze(
        args.processed.resolve(),
        args.source_config.resolve(),
        args.evaluation_config.resolve(),
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
