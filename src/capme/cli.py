"""Command-line interface for the artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_ablations, run_matrix


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capme")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("run", "run the configured benchmark matrix"),
        ("ablate", "run all path/endpoint/platform layer subsets"),
    ):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("--config", type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        manifest = run_matrix(args.config, args.output)
    else:
        manifest = run_ablations(args.config, args.output)
    print(json.dumps({"run_count": manifest["run_count"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
