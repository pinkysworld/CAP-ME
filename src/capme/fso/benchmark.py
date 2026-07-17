"""Local codec/envelope scalability and resource benchmark for FSO."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import multiprocessing
import os
import platform
import resource
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import cryptography

from capme.io import sha256_file, write_csv, write_json

from .crypto import EnvelopeCipher
from .framing import FragmentReassembler, fragment_envelope
from .lab import DeterministicLabEntropy
from .protocol import FSOReceiver, FSOSender
from .types import Operation, ScheduleDecision

LANES = ("generated-0", "ephemeral-0", "ephemeral-1", "direct-0", "fixed-0")


def _peak_rss_kib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value / 1024.0 if sys.platform == "darwin" else value


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _payload(size: int) -> bytes:
    block = bytes(range(251))
    return (block * (size // len(block) + 1))[:size]


def run_case(
    *,
    name: str,
    payload_bytes: int,
    iterations: int,
    threshold: int,
    total_shards: int,
    max_fragment_data: int,
    seed: int,
    label: str = "sequential",
) -> dict[str, object]:
    if not 1 <= threshold <= total_shards <= len(LANES):
        raise ValueError("invalid benchmark coding plan")
    if payload_bytes <= 0 or iterations <= 0:
        raise ValueError("benchmark payload and iterations must be positive")
    key = hashlib.sha256(f"capme-benchmark|{seed}|{label}".encode()).digest()
    cipher = EnvelopeCipher(
        key,
        nonce_source=DeterministicLabEntropy(seed, f"{label}-nonce"),
    )
    sender = FSOSender(
        cipher,
        message_id_source=DeterministicLabEntropy(seed, f"{label}-message"),
    )
    receiver = FSOReceiver(cipher)
    reassembler = FragmentReassembler(max_inflight=8192, completed_window=8192)
    decision = ScheduleDecision(
        "benchmark",
        "file",
        threshold,
        total_shards,
        LANES[:total_shards],
        "parallel" if total_shards > 1 else "single",
        1.0,
        float(total_shards) / threshold,
        "forced local scalability plan",
    )
    payload = _payload(payload_bytes)
    operation = Operation("file", payload, 60_000.0, strict_trust=True)
    latencies: list[float] = []
    wire_bytes = 0
    fragments = 0
    cpu_started = time.process_time()
    wall_started = time.perf_counter()
    for iteration in range(iterations):
        started = time.perf_counter()
        prepared = sender.prepare(operation, decision)
        for lane_index, packet in enumerate(prepared.packets):
            datagrams = fragment_envelope(
                packet, max_fragment_data=max_fragment_data
            )
            fragments += len(datagrams)
            wire_bytes += sum(len(datagram) for datagram in datagrams)
            result = None
            peer = f"{label}-{lane_index}"
            for datagram in datagrams:
                result = reassembler.ingest(datagram, peer=peer)
            if result is None or result.packet is None:
                raise AssertionError("benchmark fragment set did not complete")
            receiver.ingest(result.packet)
        recovered = receiver.completed.get(prepared.message_id)
        if recovered is None or recovered.payload != payload:
            raise AssertionError("benchmark payload recovery failed")
        latencies.append((time.perf_counter() - started) * 1000.0)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    total_payload = payload_bytes * iterations
    return {
        "plan": name,
        "payload_bytes": payload_bytes,
        "iterations": iterations,
        "threshold": threshold,
        "total_shards": total_shards,
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "operations_per_second": iterations / wall_seconds,
        "payload_throughput_mbps": total_payload * 8.0 / wall_seconds / 1_000_000,
        "wire_bytes": wire_bytes,
        "wire_overhead": wire_bytes / total_payload,
        "fragments": fragments,
        "peak_rss_kib": _peak_rss_kib(),
        "recoveries_verified": iterations,
    }


def _parallel_worker(arguments: tuple[int, int, int, int, int, int, int]) -> dict[str, object]:
    worker, operations, payload, threshold, total, fragment, seed = arguments
    return run_case(
        name="parallel-coded-2-of-3",
        payload_bytes=payload,
        iterations=operations,
        threshold=threshold,
        total_shards=total,
        max_fragment_data=fragment,
        seed=seed + worker * 1009,
        label=f"worker-{worker}",
    )


def _parallel_scaling(config: dict[str, Any], max_fragment_data: int, seed: int) -> list[dict[str, object]]:
    spec = config["parallel_scaling"]
    output: list[dict[str, object]] = []
    for workers in [int(value) for value in spec["workers"]]:
        total_operations = int(spec["total_operations"])
        base, extra = divmod(total_operations, workers)
        tasks = [
            (
                worker,
                base + int(worker < extra),
                int(spec["payload_bytes"]),
                int(spec["threshold"]),
                int(spec["total_shards"]),
                max_fragment_data,
                seed,
            )
            for worker in range(workers)
        ]
        wall_started = time.perf_counter()
        context = multiprocessing.get_context("spawn")
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=workers, mp_context=context
        ) as executor:
            rows = list(executor.map(_parallel_worker, tasks))
        wall_seconds = time.perf_counter() - wall_started
        total_payload = int(spec["payload_bytes"]) * total_operations
        output.append(
            {
                "workers": workers,
                "payload_bytes": int(spec["payload_bytes"]),
                "operations": total_operations,
                "threshold": int(spec["threshold"]),
                "total_shards": int(spec["total_shards"]),
                "wall_seconds": wall_seconds,
                "summed_worker_cpu_seconds": sum(float(row["cpu_seconds"]) for row in rows),
                "operations_per_second": total_operations / wall_seconds,
                "payload_throughput_mbps": total_payload
                * 8.0
                / wall_seconds
                / 1_000_000,
                "wire_overhead": sum(int(row["wire_bytes"]) for row in rows)
                / total_payload,
                "max_worker_peak_rss_kib": max(float(row["peak_rss_kib"]) for row in rows),
                "recoveries_verified": sum(int(row["recoveries_verified"]) for row in rows),
            }
        )
    baseline = float(output[0]["operations_per_second"])
    for row in output:
        row["speedup_vs_one_worker"] = float(row["operations_per_second"]) / baseline
        row["parallel_efficiency"] = float(row["speedup_vs_one_worker"]) / int(
            row["workers"]
        )
    return output


def run_benchmark(config_path: Path, output_dir: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("synthetic_only") is not True or config.get("schema_version") != 1:
        raise ValueError("invalid scalability benchmark config")
    max_fragment_data = int(config["max_fragment_data"])
    seed = int(config["seed"])
    measurements: list[dict[str, object]] = []
    for case_index, case in enumerate(config["cases"]):
        for plan_index, plan in enumerate(config["plans"]):
            measurements.append(
                run_case(
                    name=str(plan["name"]),
                    payload_bytes=int(case["payload_bytes"]),
                    iterations=int(case["iterations"]),
                    threshold=int(plan["threshold"]),
                    total_shards=int(plan["total_shards"]),
                    max_fragment_data=max_fragment_data,
                    seed=seed + case_index * 101 + plan_index * 10_007,
                    label=f"case-{case_index}-plan-{plan_index}",
                )
            )
    parallel = _parallel_scaling(config, max_fragment_data, seed + 900_000)
    measurement_hash = write_csv(output_dir / "measurements.csv", measurements)
    parallel_hash = write_csv(output_dir / "parallel_scaling.csv", parallel)
    root = Path(__file__).resolve().parents[3]
    try:
        config_label = str(config_path.relative_to(root))
    except ValueError:
        config_label = config_path.name
    manifest: dict[str, object] = {
        "schema_version": 1,
        "synthetic_only": True,
        "network_used": False,
        "external_destinations": 0,
        "benchmark_scope": (
            "local pure-Python FSO coding, ChaCha20-Poly1305 envelope, fragmentation, "
            "reassembly, authentication, and recovery pipeline"
        ),
        "config": config_label,
        "config_sha256": sha256_file(config_path),
        "measurement_rows": len(measurements),
        "parallel_rows": len(parallel),
        "payload_range_bytes": [
            min(int(row["payload_bytes"]) for row in measurements),
            max(int(row["payload_bytes"]) for row in measurements),
        ],
        "coding_width_range": [
            min(int(row["total_shards"]) for row in measurements),
            max(int(row["total_shards"]) for row in measurements),
        ],
        "recoveries_verified": sum(int(row["recoveries_verified"]) for row in measurements),
        "parallel_recoveries_verified": sum(
            int(row["recoveries_verified"]) for row in parallel
        ),
        "environment": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "cryptography": cryptography.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
        },
        "files": {
            "measurements.csv": measurement_hash,
            "parallel_scaling.csv": parallel_hash,
        },
        "interpretation": (
            "Timing and memory are system observations from one host. Payload and worker "
            "scaling are descriptive and are not censorship-resistance measurements."
        ),
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = run_benchmark(args.config.resolve(), args.output.resolve())
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
