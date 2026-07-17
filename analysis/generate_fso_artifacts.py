#!/usr/bin/env python3
"""Generate reviewable FSO figures, tables, and a hash manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from capme.fso.visuals import generate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--processed",
        type=Path,
        default=Path("results/processed/fso/confirmation"),
    )
    parser.add_argument(
        "--loopback",
        type=Path,
        default=Path("results/processed/fso/loopback/manifest.json"),
    )
    parser.add_argument(
        "--lab",
        type=Path,
        default=Path("results/processed/fso/deterministic-lab/manifest.json"),
    )
    parser.add_argument(
        "--artifact-generated",
        type=Path,
        default=Path("artifacts/generated"),
    )
    args = parser.parse_args()
    headline = generate(
        args.processed, args.loopback, args.lab, args.artifact_generated
    )
    print(json.dumps(headline, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
