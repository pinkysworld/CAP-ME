#!/usr/bin/env python3
"""Create one reviewer-facing digest index for the public evidence bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "generated" / "tdsc_evidence_manifest.json"

EVIDENCE_FILES = (
    "configs/study.json",
    "configs/robustness.json",
    "configs/fso-confirmation.json",
    "configs/fso-structure-replay.json",
    "configs/fso-sensitivity.json",
    "configs/fso-independent-replay.json",
    "results/processed/study/analysis_manifest.json",
    "results/processed/study/shapley_seed_attribution.csv",
    "results/processed/robustness/manifest.json",
    "results/processed/fso/confirmation/study_manifest.json",
    "results/processed/fso/structure-replay/manifest.json",
    "results/processed/fso/structure-replay/structure_summary.csv",
    "results/processed/fso/sensitivity/manifest.json",
    "results/processed/fso/sensitivity/summary.json",
    "results/processed/fso/independent-replay/independent_manifest.json",
    "results/processed/fso/independent-replay/summary.json",
    "results/processed/fso/feedback-evaluation/study_manifest.json",
    "results/processed/fso/feedback-evaluation/feedback_audit.json",
    "results/processed/fso/deterministic-lab/manifest.json",
    "results/processed/fso/loopback/manifest.json",
    "results/processed/fso/multihost/manifest.json",
    "results/processed/fso/multihost/repeatability.json",
    "results/processed/fso/scalability/manifest.json",
    "results/processed/fso/censorlab/manifest.json",
    "results/processed/fso/censorlab-campaign/manifest.json",
    "artifacts/generated/generation_manifest.json",
    "artifacts/generated/fso_generation_manifest.json",
    "artifacts/generated/fso_structure_generation_manifest.json",
    "artifacts/generated/fso_robustness_generation_manifest.json",
    "artifacts/generated/robustness_generation_manifest.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    missing = [relative for relative in EVIDENCE_FILES if not (ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"missing evidence files: {missing}")
    payload = {
        "schema_version": 1,
        "artifact_repository": "https://github.com/pinkysworld/CAP-ME",
        "artifact_boundary": "public code and reproducibility evidence; no manuscript source or PDF",
        "synthetic_or_closed_lab_only": True,
        "frozen_feedback_plan_commit": "f4ca7bdb909bdeabbb9b297004846449eab98aa0",
        "files": {relative: sha256(ROOT / relative) for relative in EVIDENCE_FILES},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "sha256": sha256(OUTPUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
