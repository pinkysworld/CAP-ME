"""Fail when the public Git history crosses the manuscript boundary."""

from __future__ import annotations

import json
from pathlib import Path

from capme.publication import scan_public_boundary


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan_public_boundary(root)
    result = {
        "status": "ok" if not findings else "failed",
        "scope": "index-and-all-reachable-commits",
        "findings": [finding.__dict__ for finding in findings],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
