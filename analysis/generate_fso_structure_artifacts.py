#!/usr/bin/env python3
"""Generate the compact all-strategy table for the four-structure FSO replay."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "results" / "processed" / "fso" / "structure-replay"
OUTPUT = ROOT / "artifacts" / "generated"

STRUCTURES = (
    ("classifier_dominant", "Classifier"),
    ("endpoint_discovery_dominant", "Endpoint"),
    ("resource_bounded_composed", "Resource"),
    ("adaptive_composed", "Adaptive"),
)
STRATEGIES = (
    ("fso_no_feedback", "FSO"),
    ("deadline_cost_failover", "Deadline/cost"),
    ("session_failover", "Session failover"),
    ("generated_only", "Generated only"),
    ("fso", "Feedback enabled"),
    ("direct_only", "Direct only"),
    ("fixed_only", "Fixed only"),
    ("ephemeral_only", "Ephemeral only"),
    ("random_failover", "Random failover"),
    ("performance_only", "Performance only"),
    ("fso_fixed_code", "Fixed code"),
    ("fso_no_semantics", "No semantics"),
    ("fso_no_diversity", "No diversity"),
    ("fso_no_redundancy", "No redundancy"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_auac(path: Path) -> dict[str, float]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["strategy"]: float(row["auac"]) for row in csv.DictReader(handle)}


def main() -> int:
    inputs: dict[str, str] = {}
    by_structure: dict[str, dict[str, float]] = {}
    for structure, _ in STRUCTURES:
        path = PROCESSED / structure / "aggregate_metrics.csv"
        relative = str(path.relative_to(ROOT))
        inputs[relative] = sha256(path)
        by_structure[structure] = read_auac(path)

    expected = {strategy for strategy, _ in STRATEGIES}
    if any(set(rows) != expected for rows in by_structure.values()):
        raise ValueError("structure replay strategy set differs from the declared 14")

    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        "Strategy & " + " & ".join(label for _, label in STRUCTURES) + r" \\",
        r"\midrule",
    ]
    for strategy, label in STRATEGIES:
        values = " & ".join(
            f"{by_structure[structure][strategy]:.3f}"
            for structure, _ in STRUCTURES
        )
        lines.append(f"{label} & {values} \\\\")
    lines.extend((r"\bottomrule", r"\end{tabular}"))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    table = OUTPUT / "fso_structure_results.tex"
    table.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "inputs": inputs,
        "outputs": {"fso_structure_results.tex": sha256(table)},
    }
    manifest_path = OUTPUT / "fso_structure_generation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
