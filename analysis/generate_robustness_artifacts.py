#!/usr/bin/env python3
"""Generate the public figure and compact evidence table for robustness results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from capme.io import read_csv, sha256_file, write_json
from capme.visuals import robustness_interval_figure


FAMILY_LABELS = {
    "classifier_dominant": "Classifier-dominant",
    "endpoint_discovery_dominant": "Endpoint discovery",
    "resource_bounded_composed": "Resource-bounded composed",
    "adaptive_composed": "Adaptive composed",
}


def generate(processed: Path, artifact_generated: Path) -> dict[str, object]:
    summaries = read_csv(processed / "robustness_summary.csv")
    variances = read_csv(processed / "variance_components.csv")
    with (processed / "manifest.json").open(encoding="utf-8") as handle:
        source_manifest = json.load(handle)
    figure = artifact_generated / "figures" / "robustness_intervals.pdf"
    robustness_interval_figure(summaries, figure)
    generated = {
        row["censor_model"]: row
        for row in summaries
        if row["architecture"] == "generated_transport"
    }
    variance_values = [float(row["model_variance_fraction"]) for row in variances]
    headline = {
        "schema_version": 1,
        "synthetic_only": True,
        "design_points": int(source_manifest["design_points"]),
        "censor_models": len(source_manifest["censor_models"]),
        "architectures": len(source_manifest["architectures"]),
        "replicate_seeds": len(source_manifest["replicate_seeds"]),
        "run_count": int(source_manifest["run_count"]),
        "model_variance_fraction_range": [
            min(variance_values),
            max(variance_values),
        ],
        "generated_transport": {
            family: {
                "auac_median": float(row["auac_median"]),
                "auac_q05": float(row["auac_q05"]),
                "auac_q95": float(row["auac_q95"]),
                "trust_eligible_first_fraction": float(
                    row["rank_first_fraction_trust_eligible"]
                ),
            }
            for family, row in generated.items()
        },
    }
    headline_path = artifact_generated / "robustness_headline_results.json"
    write_json(headline_path, headline)
    table_lines = [
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Censor model & Median AUAC & 5--95\\% range & First among trust-eligible \\\\",
        "\\midrule",
    ]
    for family in FAMILY_LABELS:
        row = generated[family]
        table_lines.append(
            f"{FAMILY_LABELS[family]} & {float(row['auac_median']):.3f} & "
            f"[{float(row['auac_q05']):.3f}, {float(row['auac_q95']):.3f}] & "
            f"{float(row['rank_first_fraction_trust_eligible']):.3f} \\\\"
        )
    table_lines.extend(["\\bottomrule", "\\end{tabular}"])
    table_path = artifact_generated / "robustness_headline_results.tex"
    table_path.write_text("\n".join(table_lines) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "source_manifest_sha256": sha256_file(processed / "manifest.json"),
        "files": {
            "figures/robustness_intervals.pdf": sha256_file(figure),
            "robustness_headline_results.json": sha256_file(headline_path),
            "robustness_headline_results.tex": sha256_file(table_path),
        },
    }
    write_json(artifact_generated / "robustness_generation_manifest.json", manifest)
    return headline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--processed",
        type=Path,
        default=Path("results/processed/robustness"),
    )
    parser.add_argument(
        "--artifact-generated",
        type=Path,
        default=Path("artifacts/generated"),
    )
    args = parser.parse_args()
    headline = generate(args.processed, args.artifact_generated)
    print(json.dumps(headline, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
