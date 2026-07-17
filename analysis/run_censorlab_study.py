"""Run the CAP-ME packet study against a pinned external CensorLab checkout."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from capme.fso.censorlab import (
    docker_backend,
    run_study,
    verify_external_censorlab,
)
from capme.io import sha256_file, write_json


def _docker_image_environment(image: str) -> dict[str, object]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(completed.stdout)
    if len(rows) != 1:
        raise ValueError(f"expected one Docker image inspection row for {image}")
    row = rows[0]
    labels = row.get("Config", {}).get("Labels") or {}
    return {
        "image": image,
        "image_id": row["Id"],
        "image_os": row["Os"],
        "image_architecture": row["Architecture"],
        "image_build_hash": labels.get("censorlab.build_hash", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate deterministic FSO packet traces in CensorLab PCAP mode "
            "inside a no-network container"
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--censorlab-repo", type=Path, required=True)
    parser.add_argument("--image", default=None)
    args = parser.parse_args(argv)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    backend_config = config["backend"]
    expected_commit = str(backend_config["commit"])
    actual_commit = verify_external_censorlab(args.censorlab_repo, expected_commit)
    license_path = args.censorlab_repo / "LICENSE"
    license_text = license_path.read_text(encoding="utf-8", errors="replace")
    if "GNU GENERAL PUBLIC LICENSE" not in license_text or "Version 3" not in license_text[:200]:
        raise ValueError("the external CensorLab checkout does not expose the expected GPL-3.0 license")

    image = args.image or str(backend_config["image"])
    environment = _docker_image_environment(image)
    environment.update(
        {
            "censorlab_repository": str(backend_config["repository"]),
            "censorlab_commit": actual_commit,
            "censorlab_license": "GPL-3.0-only",
            "censorlab_license_sha256": sha256_file(license_path),
            "container_network": "none",
            "container_filesystem": "read-only",
            "container_capabilities": "all dropped",
        }
    )
    if environment["image_build_hash"] != expected_commit:
        raise ValueError(
            "CensorLab image label does not match the pinned source commit: "
            f"{environment['image_build_hash']} != {expected_commit}"
        )

    args.output.mkdir(parents=True, exist_ok=True)
    environment_hash = write_json(args.output / "environment.json", environment)
    environment["environment_sha256"] = environment_hash
    backend = docker_backend(
        image=image,
        censorlab_repo=args.censorlab_repo,
        config_relative=Path(str(backend_config["config"])),
        output_root=args.output,
        client_ip=str(config["client_ip"]),
        config_origin=str(backend_config.get("config_origin", "image")),
        artifact_root=Path(__file__).resolve().parents[1],
    )
    manifest = run_study(
        args.config,
        args.output,
        backend,
        environment=environment,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
