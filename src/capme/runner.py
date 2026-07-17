"""Matrix execution and exact layer-ablation orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .io import write_csv, write_json
from .model import ARCHITECTURES, CENSOR_REGIMES, NETWORKS
from .simulation import SimulationConfig, run_simulation


def load_experiment(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    required = {"architectures", "censors", "networks", "seeds", "simulation"}
    missing = required - set(value)
    if missing:
        raise ValueError(f"experiment is missing keys: {sorted(missing)}")
    return value


def _simulation_config(value: dict[str, object]) -> SimulationConfig:
    return SimulationConfig(**value)


def run_matrix(experiment_path: Path, output_dir: Path) -> dict[str, object]:
    experiment = load_experiment(experiment_path)
    config = _simulation_config(experiment["simulation"])
    rows: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    run_manifests: list[dict[str, object]] = []
    run_index = 0
    for architecture_name in experiment["architectures"]:
        architecture = ARCHITECTURES[architecture_name]
        for censor_name in experiment["censors"]:
            censor = CENSOR_REGIMES[censor_name]
            for network_name in experiment["networks"]:
                network = NETWORKS[network_name]
                for seed in experiment["seeds"]:
                    result = run_simulation(architecture, censor, network, int(seed), config)
                    run_id = f"run-{run_index:05d}"
                    for row in result.rows:
                        row["run_id"] = run_id
                    for event in result.endpoint_events:
                        event.update(
                            {
                                "run_id": run_id,
                                "seed": seed,
                                "architecture": architecture_name,
                                "censor": censor_name,
                                "network": network_name,
                                "layer_mask": censor.layer_mask,
                            }
                        )
                    result.manifest["run_id"] = run_id
                    rows.extend(result.rows)
                    events.extend(result.endpoint_events)
                    run_manifests.append(result.manifest)
                    run_index += 1
    row_hash = write_csv(output_dir / "observations.csv", rows)
    event_hash = write_csv(output_dir / "endpoint_events.csv", events)
    manifest = {
        "schema_version": 1,
        "experiment": experiment,
        "simulation_config": asdict(config),
        "run_count": run_index,
        "observation_count": len(rows),
        "endpoint_event_count": len(events),
        "files": {
            "observations.csv": row_hash,
            "endpoint_events.csv": event_hash,
        },
        "runs": run_manifests,
        "synthetic_only": True,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest

def run_ablations(experiment_path: Path, output_dir: Path) -> dict[str, object]:
    experiment = load_experiment(experiment_path)
    config = _simulation_config(experiment["simulation"])
    base = CENSOR_REGIMES["adaptive_cross_layer"]
    rows: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    run_index = 0
    masks = [
        (path, endpoint, platform)
        for path in (False, True)
        for endpoint in (False, True)
        for platform in (False, True)
    ]
    ablation_seeds = experiment.get("ablation_seeds", experiment["seeds"][:8])
    ablation_network = NETWORKS[experiment.get("ablation_network", "mobile")]
    for architecture_name in experiment["architectures"]:
        architecture = ARCHITECTURES[architecture_name]
        for path, endpoint, platform in masks:
            censor = base.with_layers(path=path, endpoint=endpoint, platform=platform)
            for seed in ablation_seeds:
                result = run_simulation(architecture, censor, ablation_network, int(seed), config)
                run_id = f"ablation-{run_index:05d}"
                for row in result.rows:
                    row["run_id"] = run_id
                for event in result.endpoint_events:
                    event.update(
                        {
                            "run_id": run_id,
                            "seed": seed,
                            "architecture": architecture_name,
                            "censor": censor.name,
                            "network": ablation_network.name,
                            "layer_mask": censor.layer_mask,
                        }
                    )
                rows.extend(result.rows)
                events.extend(result.endpoint_events)
                run_index += 1
    row_hash = write_csv(output_dir / "ablation_observations.csv", rows)
    event_hash = write_csv(output_dir / "ablation_endpoint_events.csv", events)
    manifest = {
        "schema_version": 1,
        "run_count": run_index,
        "observation_count": len(rows),
        "masks": [f"{int(p)}{int(e)}{int(l)}" for p, e, l in masks],
        "network": ablation_network.name,
        "seeds": ablation_seeds,
        "files": {
            "ablation_observations.csv": row_hash,
            "ablation_endpoint_events.csv": event_hash,
        },
        "synthetic_only": True,
    }
    write_json(output_dir / "ablation_manifest.json", manifest)
    return manifest
