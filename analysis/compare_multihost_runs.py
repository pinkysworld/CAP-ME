#!/usr/bin/env python3
"""Compare two multi-host runs while excluding measured system timing fields."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from capme.io import sha256_file, write_json

OBSERVATION_TIMING_FIELDS = {
    "elapsed_ms",
    "client_cpu_ms",
    "client_peak_rss_kib",
}
MANIFEST_SYSTEM_FIELDS = {
    "wall_time_seconds",
    "client_cpu_seconds",
    "client_peak_rss_kib",
    "environment_sha256",
    "observations_sha256",
}


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _normalized_observations(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {
                key: value
                for key, value in row.items()
                if key not in OBSERVATION_TIMING_FIELDS
            }
            for row in csv.DictReader(handle)
        ]


def _normalized_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    normalized = {
        key: value
        for key, value in manifest.items()
        if key not in MANIFEST_SYSTEM_FIELDS
    }
    normalized["phase_summaries"] = [
        {key: value for key, value in row.items() if key != "mean_elapsed_ms"}
        for row in manifest["phase_summaries"]
    ]
    return normalized


def compare(first: Path, second: Path, output: Path) -> dict[str, object]:
    first_observations = _normalized_observations(first / "observations.csv")
    second_observations = _normalized_observations(second / "observations.csv")
    first_manifest = _normalized_manifest(first / "manifest.json")
    second_manifest = _normalized_manifest(second / "manifest.json")
    observation_equal = first_observations == second_observations
    manifest_equal = first_manifest == second_manifest
    record: dict[str, object] = {
        "schema_version": 1,
        "comparison_scope": (
            "delivery decisions, lane plans, wire counts, impairment counters, "
            "concordance values, and recovery state"
        ),
        "excluded_measured_fields": {
            "observations": sorted(OBSERVATION_TIMING_FIELDS),
            "manifest": sorted(MANIFEST_SYSTEM_FIELDS | {"phase_summaries.mean_elapsed_ms"}),
        },
        "runs": [
            {
                "path": str(first),
                "observations_sha256": sha256_file(first / "observations.csv"),
                "manifest_sha256": sha256_file(first / "manifest.json"),
                "environment_sha256": sha256_file(first / "environment.json"),
                "normalized_observations_sha256": _canonical_hash(first_observations),
                "normalized_manifest_sha256": _canonical_hash(first_manifest),
            },
            {
                "path": str(second),
                "observations_sha256": sha256_file(second / "observations.csv"),
                "manifest_sha256": sha256_file(second / "manifest.json"),
                "environment_sha256": sha256_file(second / "environment.json"),
                "normalized_observations_sha256": _canonical_hash(second_observations),
                "normalized_manifest_sha256": _canonical_hash(second_manifest),
            },
        ],
        "normalized_observations_equal": observation_equal,
        "normalized_manifests_equal": manifest_equal,
        "repeatable_outcomes": observation_equal and manifest_equal,
        "interpretation": (
            "OS timing, CPU, RSS, transient environment identity, and raw-file hashes "
            "are observations and are not expected to be byte-identical."
        ),
    }
    if not record["repeatable_outcomes"]:
        raise AssertionError("multi-host outcome repeatability check failed")
    write_json(output, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = compare(args.first, args.second, args.output)
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
