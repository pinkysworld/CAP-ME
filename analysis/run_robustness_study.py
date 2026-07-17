from __future__ import annotations

import argparse
import json
from pathlib import Path

from capme.robustness import run_robustness_study


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = run_robustness_study(args.config, args.output)
    print(
        json.dumps(
            {
                "design_points": manifest["design_points"],
                "censor_models": len(manifest["censor_models"]),
                "runs": manifest["run_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
