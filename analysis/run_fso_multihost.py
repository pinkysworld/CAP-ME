#!/usr/bin/env python3
"""Build and run the closed FSO multi-host packet testbed in Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from capme.fso.multihost import is_closed_lab_address, validate_multihost_config
from capme.io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]
BASE_IMAGE = "python:3.12-slim-bookworm"
BASE_IMAGE_DIGEST = (
    "sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"
)
CONFIG_IN_IMAGE = "/app/configs/fso-multihost.json"


def _run(
    docker: str,
    arguments: list[str],
    *,
    check: bool = True,
    timeout: float | None = 120.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [docker, *arguments],
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_ready(docker: str, container: str, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        result = _run(docker, ["logs", container], check=False, timeout=5.0)
        latest = result.stdout + result.stderr
        if "CAPME_READY" in latest:
            return
        state = _run(
            docker,
            ["inspect", "--format", "{{.State.Status}}", container],
            check=False,
            timeout=5.0,
        )
        if state.stdout.strip() in {"exited", "dead"}:
            raise RuntimeError(f"container {container} exited before ready:\n{latest}")
        time.sleep(0.1)
    raise RuntimeError(f"container {container} did not become ready:\n{latest}")


def _hardened_run_arguments(name: str, network: str, alias: str) -> list[str]:
    return [
        "run",
        "-d",
        "--name",
        name,
        "--network",
        network,
        "--network-alias",
        alias,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "256m",
        "--cpus",
        "1.0",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m",
        "--label",
        "org.capme.testbed=multihost",
    ]


def _container_record(inspect: dict[str, Any], network: str, role: str) -> dict[str, object]:
    network_state = inspect["NetworkSettings"]["Networks"][network]
    ports = inspect["NetworkSettings"].get("Ports") or {}
    bindings = inspect["HostConfig"].get("PortBindings") or {}
    if ports or bindings:
        raise AssertionError(f"container {inspect['Name']} unexpectedly publishes ports")
    addresses = [
        value
        for value in (network_state.get("IPAddress"), network_state.get("GlobalIPv6Address"))
        if value
    ]
    if not addresses or any(not is_closed_lab_address(value) for value in addresses):
        raise AssertionError(
            f"container {inspect['Name']} has a non-laboratory address: {addresses}"
        )
    host_config = inspect["HostConfig"]
    security_options = host_config.get("SecurityOpt") or []
    if host_config.get("ReadonlyRootfs") is not True:
        raise AssertionError(f"container {inspect['Name']} root filesystem is writable")
    if host_config.get("CapDrop") != ["ALL"]:
        raise AssertionError(f"container {inspect['Name']} does not drop all capabilities")
    if "no-new-privileges" not in security_options:
        raise AssertionError(f"container {inspect['Name']} lacks no-new-privileges")
    return {
        "name": inspect["Name"].lstrip("/"),
        "role": role,
        "image": inspect["Image"],
        "addresses": addresses,
        "aliases": sorted(network_state.get("Aliases") or []),
        "published_ports": 0,
        "read_only_rootfs": True,
        "capabilities_dropped": ["ALL"],
        "no_new_privileges": True,
        "pids_limit": host_config.get("PidsLimit"),
        "memory_limit_bytes": host_config.get("Memory"),
        "nano_cpus": host_config.get("NanoCpus"),
    }


def _source_hashes() -> dict[str, str]:
    paths = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "src").rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and path.suffix not in {".pyc", ".pyo"}
    ]
    paths.extend(
        (
            "analysis/run_fso_multihost.py",
            "configs/fso-multihost.json",
            "testbeds/multihost/Dockerfile",
            "testbeds/multihost/requirements.txt",
            ".dockerignore",
        )
    )
    return {path: sha256_file(ROOT / path) for path in paths}


def run(config_path: Path, output_dir: Path, *, docker: str, rebuild: bool) -> dict[str, object]:
    config_path = config_path.resolve()
    output_dir = output_dir.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_multihost_config(config)
    if config_path != (ROOT / "configs" / "fso-multihost.json").resolve():
        raise ValueError(
            "the container image accepts only the reviewed configs/fso-multihost.json"
        )
    config_hash = sha256_file(config_path)
    source_commit = _run(
        "git", ["-C", str(ROOT), "rev-parse", "HEAD"], timeout=10.0
    ).stdout.strip()
    source_status = _run(
        "git", ["-C", str(ROOT), "status", "--porcelain"], timeout=10.0
    ).stdout
    suffix = f"{os.getpid()}-{config_hash[:8]}"
    image = f"capme-multihost:{config_hash[:12]}"
    network = f"capme-internal-{suffix}"
    volume = f"capme-output-{suffix}"
    receiver_name = f"capme-receiver-{suffix}"
    proxy_names = {
        str(row["name"]): f"capme-proxy-{row['name']}-{suffix}"
        for row in config["lanes"]
    }
    client_name = f"capme-client-{suffix}"
    containers: list[str] = []
    network_created = False
    volume_created = False

    docker_info = json.loads(
        _run(docker, ["info", "--format", "{{json .}}"], timeout=30.0).stdout
    )
    image_exists = (
        _run(docker, ["image", "inspect", image], check=False, timeout=30.0).returncode
        == 0
    )
    if rebuild or not image_exists:
        _run(
            docker,
            [
                "build",
                "--pull=false",
                "--label",
                "org.capme.testbed=multihost",
                "--label",
                f"org.capme.config.sha256={config_hash}",
                "--file",
                "testbeds/multihost/Dockerfile",
                "--tag",
                image,
                ".",
            ],
            timeout=600.0,
        )
    image_inspect = json.loads(_run(docker, ["image", "inspect", image]).stdout)[0]
    if image_inspect["Config"]["Labels"].get("org.capme.config.sha256") != config_hash:
        raise AssertionError("container image config label does not match reviewed config")

    try:
        _run(
            docker,
            [
                "network",
                "create",
                "--internal",
                "--driver",
                "bridge",
                "--label",
                "org.capme.testbed=multihost",
                network,
            ],
        )
        network_created = True
        _run(
            docker,
            ["volume", "create", "--label", "org.capme.testbed=multihost", volume],
        )
        volume_created = True
        _run(
            docker,
            [
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CHOWN",
                "--security-opt",
                "no-new-privileges",
                "--user",
                "0:0",
                "--mount",
                f"type=volume,source={volume},target=/output",
                "--entrypoint",
                "/bin/chown",
                image,
                "10001:10001",
                "/output",
            ],
        )

        receiver_args = _hardened_run_arguments(receiver_name, network, "receiver")
        receiver_args += [image, "receiver", "--config", CONFIG_IN_IMAGE]
        _run(docker, receiver_args)
        containers.append(receiver_name)
        _wait_ready(docker, receiver_name)

        for row in config["lanes"]:
            lane_name = str(row["name"])
            alias = str(row["proxy_host"])
            container = proxy_names[lane_name]
            proxy_args = _hardened_run_arguments(container, network, alias)
            proxy_args += [
                image,
                "proxy",
                "--config",
                CONFIG_IN_IMAGE,
                "--lane",
                lane_name,
            ]
            _run(docker, proxy_args)
            containers.append(container)
            _wait_ready(docker, container)

        client_args = _hardened_run_arguments(client_name, network, "client")
        client_args += [
            "--mount",
            f"type=volume,source={volume},target=/output",
            image,
            "client",
            "--config",
            CONFIG_IN_IMAGE,
            "--output",
            "/output",
        ]
        _run(docker, client_args)
        containers.append(client_name)

        network_inspect = json.loads(
            _run(docker, ["network", "inspect", network]).stdout
        )[0]
        if network_inspect.get("Internal") is not True:
            raise AssertionError("multi-host Docker network is not internal")
        if network_inspect.get("Driver") != "bridge":
            raise AssertionError("multi-host Docker network is not a bridge")

        roles = {receiver_name: "receiver", client_name: "sender"}
        roles.update({name: f"carrier:{lane}" for lane, name in proxy_names.items()})
        inspected = json.loads(_run(docker, ["inspect", *containers]).stdout)
        container_records = [
            _container_record(record, network, roles[record["Name"].lstrip("/")])
            for record in inspected
        ]

        client_wait = _run(
            docker,
            ["wait", client_name],
            check=False,
            timeout=300.0,
        )
        client_result = _run(
            docker,
            ["logs", client_name],
            check=False,
            timeout=30.0,
        )
        if client_wait.returncode != 0 or client_result.returncode != 0:
            raise RuntimeError(
                "multi-host client failed:\n"
                + client_result.stdout
                + "\n"
                + client_result.stderr
            )
        state = json.loads(_run(docker, ["inspect", client_name]).stdout)[0]["State"]
        if state.get("ExitCode") != 0 or client_wait.stdout.strip() != "0":
            raise RuntimeError(
                f"multi-host client exit state: {state}\n"
                + client_result.stdout
                + "\n"
                + client_result.stderr
            )

        output_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="capme-multihost-copy-", dir=output_dir.parent
        ) as staging_name:
            staging = Path(staging_name)
            _run(docker, ["cp", f"{client_name}:/output/.", str(staging)])
            manifest_path = staging / "manifest.json"
            observations_path = staging / "observations.csv"
            if not manifest_path.is_file() or not observations_path.is_file():
                raise RuntimeError("multi-host client did not produce the expected artifacts")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("external_destinations") != 0:
                raise AssertionError("multi-host client reported an external destination")
            if manifest.get("provider_controlled_attempts") != 0:
                raise AssertionError("multi-host client violated strict trust")

            environment = {
                "schema_version": 1,
                "closed_world": True,
                "external_destinations": 0,
                "live_interfaces": 0,
                "docker_network": {
                    "name": network,
                    "internal": True,
                    "driver": "bridge",
                    "attachable": bool(network_inspect.get("Attachable")),
                    "ingress": bool(network_inspect.get("Ingress")),
                    "ipam": network_inspect.get("IPAM", {}).get("Config", []),
                },
                "containers": container_records,
                "published_ports": 0,
                "container_count": len(container_records),
                "image": {
                    "tag": image,
                    "id": image_inspect["Id"],
                    "architecture": image_inspect["Architecture"],
                    "os": image_inspect["Os"],
                    "base": BASE_IMAGE,
                    "base_digest": BASE_IMAGE_DIGEST,
                    "config_sha256_label": image_inspect["Config"]["Labels"][
                        "org.capme.config.sha256"
                    ],
                },
                "docker": {
                    "server_version": docker_info.get("ServerVersion"),
                    "operating_system": docker_info.get("OperatingSystem"),
                    "architecture": docker_info.get("Architecture"),
                    "driver": docker_info.get("Driver"),
                    "security_options": docker_info.get("SecurityOptions"),
                },
                "config": str(config_path.relative_to(ROOT)),
                "config_sha256": config_hash,
                "source_commit_at_run": source_commit,
                "source_tree_dirty_at_run": bool(source_status.strip()),
                "source_files": _source_hashes(),
                "build_context_policy": (
                    "root .dockerignore allowlists only src, the reviewed config, "
                    "and testbeds/multihost build files"
                ),
                "client_stdout_sha256": hashlib.sha256(
                    client_result.stdout.encode()
                ).hexdigest(),
            }
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(observations_path, output_dir / "observations.csv")
            environment_hash = write_json(output_dir / "environment.json", environment)
            manifest["environment_sha256"] = environment_hash
            manifest["config_sha256"] = config_hash
            manifest["container_image_id"] = image_inspect["Id"]
            manifest["docker_internal_network"] = True
            manifest["published_ports"] = 0
            manifest["container_count"] = len(container_records)
            write_json(output_dir / "manifest.json", manifest)
            return manifest
    finally:
        for container in reversed(containers):
            _run(docker, ["rm", "--force", container], check=False, timeout=30.0)
        if volume_created:
            _run(docker, ["volume", "rm", "--force", volume], check=False, timeout=30.0)
        if network_created:
            _run(docker, ["network", "rm", network], check=False, timeout=30.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "fso-multihost.json"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "processed" / "fso" / "multihost",
    )
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args(argv)
    manifest = run(args.config, args.output, docker=args.docker, rebuild=args.rebuild)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
