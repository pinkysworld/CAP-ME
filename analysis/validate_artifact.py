"""Self-contained validation for the CAP-ME research artifact."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from capme.fso.deployment import validate_authorization
from capme.fso.multihost import is_closed_lab_address
from capme.fso.reviews import validate_review_bundle


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def row_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_processed() -> list[str]:
    messages: list[str] = []
    config = load_json(ROOT / "configs" / "study.json")
    processed = ROOT / "results" / "processed" / "study"
    manifest = load_json(processed / "analysis_manifest.json")
    expected_runs = (
        len(config["architectures"])
        * len(config["censors"])
        * len(config["networks"])
        * len(config["seeds"])
    )
    expected_ablations = (
        len(config["architectures"]) * 8 * len(config["ablation_seeds"])
    )
    assert manifest["synthetic_only"] is True
    assert manifest["counts"]["runs"] == expected_runs == 900
    assert manifest["counts"]["ablation_runs"] == expected_ablations == 320
    expected_rows = {
        "run_metrics.csv": 900,
        "aggregate_metrics.csv": 45,
        "paired_contrasts.csv": 15,
        "shapley_attribution.csv": 15,
        "shapley_seed_attribution.csv": 120,
        "survival_curves.csv": 180,
    }
    for name, count in expected_rows.items():
        path = processed / name
        assert row_count(path) == count, f"{name}: unexpected row count"
        assert sha256(path) == manifest["files"][name], f"{name}: hash mismatch"
    messages.append("processed result counts and SHA-256 digests")
    return messages


def validate_raw_if_present() -> list[str]:
    raw = ROOT / "results" / "raw" / "study"
    main_manifest_path = raw / "manifest.json"
    ablation_manifest_path = raw / "ablation_manifest.json"
    if not main_manifest_path.exists() or not ablation_manifest_path.exists():
        return ["raw matrices absent (allowed; deterministically regenerable)"]
    main_manifest = load_json(main_manifest_path)
    ablation_manifest = load_json(ablation_manifest_path)
    assert main_manifest["synthetic_only"] is True
    assert ablation_manifest["synthetic_only"] is True
    assert main_manifest["run_count"] == 900
    assert ablation_manifest["run_count"] == 320
    for filename in ("observations.csv", "ablation_observations.csv"):
        checked = 0
        with (raw / filename).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                outcomes = sum(
                    int(row[key])
                    for key in (
                        "successes",
                        "path_failures",
                        "endpoint_failures",
                        "platform_failures",
                        "network_failures",
                    )
                )
                assert outcomes == int(row["attempts"]), (
                    f"{filename}: operation conservation failure at row {checked + 2}"
                )
                checked += 1
        assert checked > 0
    return ["raw manifests, synthetic-only flags, and operation conservation"]


def validate_robustness() -> list[str]:
    config_path = ROOT / "configs" / "robustness.json"
    config = load_json(config_path)
    directory = ROOT / "results" / "processed" / "robustness"
    manifest = load_json(directory / "manifest.json")
    design_points = int(config["design_points"])
    family_count = len(config["censor_models"])
    architecture_count = len(config["architectures"])
    replicate_count = len(config["replicate_seeds"])
    parameter_count = len(config["parameters"])
    expected_runs = (
        design_points * family_count * architecture_count * replicate_count
    )
    expected_rows = {
        "design.csv": design_points,
        "effective_parameters.csv": design_points
        * family_count
        * architecture_count,
        "run_metrics.csv": expected_runs,
        "design_metrics.csv": design_points * family_count * architecture_count,
        "robustness_summary.csv": family_count * architecture_count,
        "pairwise_ordering.csv": family_count
        * architecture_count
        * (architecture_count - 1)
        // 2,
        "global_sensitivity_prcc.csv": family_count
        * architecture_count
        * parameter_count,
        "variance_components.csv": family_count * architecture_count,
    }
    assert manifest["synthetic_only"] is True
    assert manifest["design"] == "stratified_latin_hypercube"
    assert manifest["design_points"] == design_points == 72
    assert manifest["run_count"] == expected_runs == 4_320
    assert manifest["replicate_seeds"] == config["replicate_seeds"]
    assert manifest["config_sha256"] == sha256(config_path)
    for name, count in expected_rows.items():
        path = directory / name
        assert row_count(path) == count, f"robustness {name}: unexpected row count"
        assert sha256(path) == manifest["files"][name], (
            f"robustness {name}: hash mismatch"
        )

    design_ids = {
        row["design_id"] for row in read_csv_rows(directory / "design.csv")
    }
    assert len(design_ids) == design_points
    seeds = set(config["replicate_seeds"])
    for row in read_csv_rows(directory / "run_metrics.csv"):
        assert row["design_id"] in design_ids
        assert int(row["seed"]) in seeds
        outcomes = int(row["successes"]) + sum(
            int(row[name])
            for name in (
                "path_failures",
                "endpoint_failures",
                "platform_failures",
                "network_failures",
            )
        )
        assert outcomes == int(row["attempts"])

    for row in read_csv_rows(directory / "robustness_summary.csv"):
        assert (
            float(row["auac_q05"])
            <= float(row["auac_median"])
            <= float(row["auac_q95"])
        )
        assert 0.0 <= float(row["rank_first_fraction_all"]) <= 1.0
        eligible = row["rank_first_fraction_trust_eligible"]
        if eligible != "nan":
            assert 0.0 <= float(eligible) <= 1.0

    for row in read_csv_rows(directory / "global_sensitivity_prcc.csv"):
        value = float(row["prcc"])
        if int(row["structurally_active"]):
            assert -1.0 <= value <= 1.0
            assert int(row["bootstrap_valid"]) > 0
        else:
            assert value != value

    for row in read_csv_rows(directory / "variance_components.csv"):
        model_fraction = float(row["model_variance_fraction"])
        seed_fraction = float(row["seed_variance_fraction"])
        assert abs(model_fraction + seed_fraction - 1.0) < 1e-12

    generated_directory = ROOT / "artifacts" / "generated"
    generated_manifest = load_json(
        generated_directory / "robustness_generation_manifest.json"
    )
    assert generated_manifest["synthetic_only"] is True
    assert generated_manifest["source_manifest_sha256"] == sha256(
        directory / "manifest.json"
    )
    for name, digest in generated_manifest["files"].items():
        assert sha256(generated_directory / name) == digest, (
            f"robustness generated artifact {name}: hash mismatch"
        )
    headline = load_json(
        generated_directory / "robustness_headline_results.json"
    )
    assert headline["synthetic_only"] is True
    assert headline["run_count"] == expected_runs
    model_range = headline["model_variance_fraction_range"]
    assert 0.81 < float(model_range[0]) < float(model_range[1]) < 0.99
    generated = headline["generated_transport"]
    assert set(generated) == {
        item["name"] for item in config["censor_models"]
    }
    assert all(
        0.0 <= float(row["trust_eligible_first_fraction"]) <= 1.0
        for row in generated.values()
    )
    return [
        "four structural censor models, 72-point global uncertainty design, "
        "4,320 conserved runs, PRCC bounds, variance decomposition, generated figure, "
        "and exact hashes"
    ]


def _find_row(rows: list[dict[str, str]], key: str, value: str) -> dict[str, str]:
    matches = [row for row in rows if row[key] == value]
    assert len(matches) == 1, f"expected one {key}={value} row"
    return matches[0]


def validate_fso_processed() -> list[str]:
    processed = ROOT / "results" / "processed" / "fso" / "confirmation"
    manifest = load_json(processed / "study_manifest.json")
    assert manifest["synthetic_only"] is True
    assert manifest["strict_trust"] is True
    assert manifest["common_random_numbers"] is True
    assert manifest["primary_strategy"] == "fso_no_feedback"
    assert manifest["provider_controlled_attempts"] == 0
    assert manifest["counts"] == {
        "cell_rows": 46_800,
        "operation_decisions": 1_497_600,
        "strategy_seed_runs": 260,
        "trace_rows": 18_000,
    }
    expected_rows = {
        "aggregate_metrics.csv": 13,
        "run_metrics.csv": 260,
        "paired_contrasts.csv": 12,
        "survival_curves.csv": 468,
        "lane_selection.csv": 55,
    }
    for name, count in expected_rows.items():
        path = processed / name
        assert row_count(path) == count, f"FSO {name}: unexpected row count"
        assert sha256(path) == manifest["processed_files"][name], (
            f"FSO {name}: hash mismatch"
        )
    trace = ROOT / str(manifest["source_trace"])
    assert row_count(trace) == 18_000
    assert sha256(trace) == manifest["source_trace_sha256"]

    original_seeds = set(load_json(ROOT / "configs" / "study.json")["seeds"])
    confirmation_seeds = set(manifest["seeds"])
    assert len(confirmation_seeds) == 20
    assert original_seeds.isdisjoint(confirmation_seeds)

    aggregates = read_csv_rows(processed / "aggregate_metrics.csv")
    fso = _find_row(aggregates, "strategy", "fso_no_feedback")
    feedback_enabled = _find_row(aggregates, "strategy", "fso")
    session = _find_row(aggregates, "strategy", "session_failover")
    no_semantics = _find_row(aggregates, "strategy", "fso_no_semantics")
    assert abs(float(fso["auac"]) - 0.9147569444444443) < 1e-12
    assert abs(float(session["auac"]) - 0.8960677083333332) < 1e-12
    assert abs(float(fso["byte_overhead"]) - 1.2384499731322065) < 1e-12
    assert float(fso["auac"]) > float(feedback_enabled["auac"])
    assert abs(float(no_semantics["byte_overhead"]) - 2.000061214729795) < 1e-12
    contrasts = read_csv_rows(processed / "paired_contrasts.csv")
    session_contrast = _find_row(contrasts, "baseline", "session_failover")
    feedback_contrast = _find_row(contrasts, "baseline", "fso")
    assert abs(float(session_contrast["mean_difference"]) - 0.018689236111111108) < 1e-12
    assert float(session_contrast["ci_low"]) > 0
    assert float(feedback_contrast["mean_difference"]) > 0

    raw = ROOT / "results" / "raw" / "fso-confirmation" / "observations.csv"
    if raw.exists():
        assert sha256(raw) == manifest["raw_files"]["observations.csv"]
        raw_status = "including raw observation hash"
    else:
        raw_status = "raw observations absent but regenerable"
    return [
        "canonical feedback-off FSO counts, disjoint seeds, hashes, trust invariant, and headline values "
        f"({raw_status})"
    ]


def validate_fso_structure_replay() -> list[str]:
    config_path = ROOT / "configs" / "fso-structure-replay.json"
    config = load_json(config_path)
    directory = ROOT / "results" / "processed" / "fso" / "structure-replay"
    manifest = load_json(directory / "manifest.json")
    structures = [str(value) for value in config["censor_structures"]]
    assert manifest["synthetic_only"] is True
    assert manifest["config_sha256"] == sha256(config_path)
    assert manifest["structures"] == structures
    assert manifest["primary_strategy"] == "fso_no_feedback"
    assert manifest["traffic_volume_coupling"] is False
    assert manifest["counts"] == {
        "operation_decisions": 5_990_400,
        "source_simulation_runs": 400,
        "source_trace_rows": 72_000,
        "strategy_seed_runs": 1_040,
    }
    for name, digest in manifest["files"].items():
        path = directory / name
        assert path.is_file(), f"structure replay file missing: {name}"
        assert sha256(path) == digest, f"structure replay hash mismatch: {name}"

    summary = read_csv_rows(directory / "structure_summary.csv")
    assert len(summary) == len(structures) == 4
    assert {row["censor_structure"] for row in summary} == set(structures)
    for row in summary:
        assert int(row["seeds"]) == 20
        assert int(row["mean_ordering_fso_ge_session_ge_generated"]) == 1
        assert float(row["fso_minus_session_ci_low"]) > 0
        assert float(row["session_minus_generated_ci_low"]) > 0
        assert float(row["seed_ordering_fraction"]) >= 0.90
        structure = row["censor_structure"]
        trace = directory / structure / "lane_trace_probabilities.csv"
        assert row_count(trace) == 18_000
        study_manifest = load_json(directory / structure / "study_manifest.json")
        assert study_manifest["primary_strategy"] == "fso_no_feedback"
        assert study_manifest["counts"]["operation_decisions"] == 1_497_600
        assert row_count(directory / structure / "aggregate_metrics.csv") == 13
        assert row_count(directory / structure / "run_metrics.csv") == 260
        assert row_count(directory / structure / "paired_contrasts.csv") == 12
    generated = load_json(
        ROOT / "artifacts" / "generated" / "fso_structure_generation_manifest.json"
    )
    assert generated["synthetic_only"] is True
    for relative, digest in generated["inputs"].items():
        assert sha256(ROOT / relative) == digest
    for relative, digest in generated["outputs"].items():
        assert sha256(ROOT / "artifacts" / "generated" / relative) == digest
    return [
        "four-structure 13-strategy replay, 5,990,400 decisions, exact hashes, "
        "stable mean ordering, and explicit no-volume-coupling boundary"
    ]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_fso_loopback_and_gate() -> list[str]:
    directory = ROOT / "results" / "processed" / "fso" / "loopback"
    manifest = load_json(directory / "manifest.json")
    assert manifest["loopback_only"] is True
    assert manifest["synthetic_payloads"] is True
    assert manifest["external_destinations"] == 0
    assert manifest["provider_controlled_attempts"] == 0
    assert manifest["operations"] == 60
    assert manifest["successful_operations"] == 57
    assert abs(float(manifest["availability"]) - 0.95) < 1e-12
    assert sum(
        int(counters["auth_failures"])
        for counters in manifest["server_counters"].values()
    ) == 0
    assert sum(
        int(counters["ack_auth_failures"])
        for counters in manifest["server_counters"].values()
    ) == 0
    observations = directory / "observations.csv"
    assert row_count(observations) == 60
    assert sha256(observations) == manifest["observations_sha256"]

    pending = validate_authorization(
        ROOT / "field" / "authorization-template.json", today=dt.date(2026, 7, 17)
    )
    local = validate_authorization(
        ROOT / "field" / "loopback-authorization.json", today=dt.date(2026, 7, 17)
    )
    assert pending["authorization_complete"] is False
    assert pending["ready_for_external_implementation"] is False
    assert pending["review_gate"]["required"] is True
    assert pending["review_gate"]["valid"] is False
    assert local["authorization_complete"] is True
    assert local["scope"] == "loopback-only"
    assert local["ready_for_external_implementation"] is False
    assert local["review_gate"]["required"] is False
    return [
        "loopback packet counts, AEAD counters, no-external/no-provider invariants, "
        "and field-authorization gate"
    ]


def validate_fso_multihost() -> list[str]:
    directory = ROOT / "results" / "processed" / "fso" / "multihost"
    manifest = load_json(directory / "manifest.json")
    environment = load_json(directory / "environment.json")
    config = ROOT / "configs" / "fso-multihost.json"
    assert manifest["closed_world"] is True
    assert manifest["docker_internal_network"] is True
    assert manifest["docker_internal_network_required"] is True
    assert manifest["synthetic_payloads"] is True
    assert manifest["external_destinations"] == 0
    assert manifest["live_interfaces"] == 0
    assert manifest["strict_trust"] is True
    assert manifest["provider_controlled_attempts"] == 0
    assert manifest["published_ports"] == 0
    assert manifest["container_count"] == 8
    assert manifest["roles"] == {
        "sender": 1,
        "carrier_fault_adapters": 6,
        "receiver": 1,
    }
    assert manifest["operations"] == 90
    assert manifest["scheduler_strategy"] == "fso_no_feedback"
    assert manifest["successful_operations"] == 68
    assert manifest["receiver_completed_operations"] == 71
    assert abs(float(manifest["acknowledged_availability"]) - 68 / 90) < 1e-12
    assert abs(float(manifest["brier_score"]) - 0.05938247724716753) < 1e-12
    assert abs(float(manifest["phase_calibration_mae"]) - 0.07799695777824156) < 1e-12
    assert manifest["ack_auth_failures"] == 0
    assert manifest["control_auth_failures"] == 0
    assert manifest["config_sha256"] == sha256(config)
    observations = directory / "observations.csv"
    assert row_count(observations) == 90
    assert sha256(observations) == manifest["observations_sha256"]
    assert sha256(directory / "environment.json") == manifest["environment_sha256"]

    phases = manifest["phase_summaries"]
    assert [row["phase"] for row in phases] == [
        "clean_start",
        "fixed_endpoint_pressure",
        "generated_classifier_pressure",
        "relay_discovery_pressure",
        "congestion",
        "recovery",
    ]
    assert all(int(row["operations"]) == 15 for row in phases)
    assert all(int(row["reassembly_inflight_after_gc"]) == 0 for row in phases)
    assert all(int(row["coded_messages_inflight_after_gc"]) == 0 for row in phases)
    receiver = manifest["receiver_stats"]
    assert receiver["reassembly_inflight"] == 0
    assert receiver["coded_messages_inflight"] == 0
    assert receiver["expired_fragment_sets"] == 41
    assert receiver["envelope_auth_failures"] == 0
    assert receiver["fragment_failures"] == 0

    assert environment["closed_world"] is True
    assert environment["external_destinations"] == 0
    assert environment["live_interfaces"] == 0
    assert environment["published_ports"] == 0
    assert environment["container_count"] == 8
    network = environment["docker_network"]
    assert network["internal"] is True
    assert network["driver"] == "bridge"
    assert network["ingress"] is False
    containers = environment["containers"]
    assert len(containers) == 8
    for container in containers:
        assert container["published_ports"] == 0
        assert container["read_only_rootfs"] is True
        assert container["capabilities_dropped"] == ["ALL"]
        assert container["no_new_privileges"] is True
        assert container["addresses"]
        assert all(is_closed_lab_address(value) for value in container["addresses"])
    assert environment["image"]["id"] == manifest["container_image_id"]
    assert environment["image"]["config_sha256_label"] == sha256(config)
    assert environment["source_tree_dirty_at_run"] is False
    expected_sources = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "src").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and path.suffix not in {".pyc", ".pyo"}
    }
    expected_sources.update(
        {
            "analysis/run_fso_multihost.py",
            "configs/fso-multihost.json",
            "testbeds/multihost/Dockerfile",
            "testbeds/multihost/requirements.txt",
            ".dockerignore",
        }
    )
    assert set(environment["source_files"]) == expected_sources
    for relative, digest in environment["source_files"].items():
        assert sha256(ROOT / relative) == digest, f"multi-host source changed: {relative}"

    repeat_directory = ROOT / "results" / "processed" / "fso" / "multihost-repeat"
    repeat_manifest = load_json(repeat_directory / "manifest.json")
    repeat_environment = load_json(repeat_directory / "environment.json")
    repeatability = load_json(directory / "repeatability.json")
    assert repeat_manifest["successful_operations"] == manifest["successful_operations"]
    assert repeat_manifest["receiver_completed_operations"] == manifest[
        "receiver_completed_operations"
    ]
    assert repeat_manifest["proxy_stats"] == manifest["proxy_stats"]
    assert repeat_manifest["receiver_stats"] == manifest["receiver_stats"]
    assert repeat_manifest["lane_attempts"] == manifest["lane_attempts"]
    assert repeat_manifest["wire_bytes"] == manifest["wire_bytes"]
    assert repeat_environment["source_tree_dirty_at_run"] is False
    assert repeat_environment["image"]["id"] == environment["image"]["id"]
    assert repeatability["normalized_observations_equal"] is True
    assert repeatability["normalized_manifests_equal"] is True
    assert repeatability["repeatable_outcomes"] is True
    for run in repeatability["runs"]:
        run_directory = ROOT / str(run["path"])
        assert sha256(run_directory / "observations.csv") == run[
            "observations_sha256"
        ]
        assert sha256(run_directory / "manifest.json") == run["manifest_sha256"]
        assert sha256(run_directory / "environment.json") == run[
            "environment_sha256"
        ]
    return [
        "closed eight-container packet testbed, internal network, zero ports, "
        "private destinations, exact hashes, packet concordance, resource counters, "
        "deadline-bound recovery, and repeatable non-timing outcomes"
    ]


def validate_feedback_evaluation() -> list[str]:
    source_config = load_json(ROOT / "configs" / "fso-feedback-source.json")
    evaluation_config = load_json(
        ROOT / "configs" / "fso-feedback-evaluation.json"
    )
    seeds = [int(value) for value in source_config["seeds"]]
    development = set(load_json(ROOT / "configs" / "study.json")["seeds"])
    development.update(
        load_json(ROOT / "configs" / "fso-confirmation-source.json")["seeds"]
    )
    assert len(seeds) == len(set(seeds)) == 12
    assert not set(seeds) & development
    assert evaluation_config["strategies"] == ["fso", "fso_no_feedback"]
    assert evaluation_config["frozen_before_execution_utc"] == source_config[
        "frozen_before_execution_utc"
    ]
    plan = evaluation_config["frozen_analysis_plan"]
    assert "lower bound greater than zero" in plan["support_rule"]
    assert "disabled" in plan["default_rule"]

    directory = ROOT / "results" / "processed" / "fso" / "feedback-evaluation"
    audit_path = directory / "feedback_audit.json"
    if not audit_path.exists():
        return [
            "prospectively frozen 12-seed feedback plan is present; evaluation pending"
        ]
    manifest = load_json(directory / "study_manifest.json")
    audit = load_json(audit_path)
    assert manifest["synthetic_only"] is True
    assert manifest["strict_trust"] is True
    assert manifest["common_random_numbers"] is True
    assert manifest["provider_controlled_attempts"] == 0
    assert manifest["seeds"] == seeds
    assert manifest["strategies"] == ["fso", "fso_no_feedback"]
    assert manifest["counts"] == {
        "trace_rows": 10_800,
        "cell_rows": 4_320,
        "strategy_seed_runs": 24,
        "operation_decisions": 138_240,
    }
    assert "12 declared synthetic seeds" in manifest["interpretation"]
    expected_rows = {
        "lane_trace_probabilities.csv": 10_800,
        "aggregate_metrics.csv": 2,
        "run_metrics.csv": 24,
        "paired_contrasts.csv": 1,
        "survival_curves.csv": 72,
    }
    for name, expected in expected_rows.items():
        assert row_count(directory / name) == expected, f"feedback {name}: row count"
    for name, digest in manifest["processed_files"].items():
        assert sha256(directory / name) == digest, f"feedback {name}: hash mismatch"
    assert audit["prospectively_frozen"] is True
    assert audit["frozen_config_commit"] == (
        "f4ca7bdb909bdeabbb9b297004846449eab98aa0"
    )
    assert audit["development_and_evaluation_seeds_disjoint"] is True
    assert audit["seeds"] == seeds
    low, high = [float(value) for value in audit["confidence_interval_95"]]
    assert abs(float(audit["fso_minus_no_feedback_auac"]) - (-0.0018084490740740515)) < 1e-15
    assert abs(low - (-0.0033998842592592358)) < 1e-15
    assert abs(high - (-0.0002170138888888763)) < 1e-15
    if low > 0:
        assert audit["classification"] == "supported_benefit_in_declared_model"
        assert audit["recommended_feedback_default"] == "enabled"
    elif high < 0:
        assert audit["classification"] == "harm_in_declared_model"
        assert audit["recommended_feedback_default"] == "disabled"
    else:
        assert audit["classification"] == "inconclusive_no_benefit_claim"
        assert audit["recommended_feedback_default"] == "disabled"
    return [
        "precommitted feedback decision rule, 12 new disjoint seeds, exact hashes, "
        "and rule-consistent claim classification"
    ]


def validate_fso_scalability() -> list[str]:
    directory = ROOT / "results" / "processed" / "fso" / "scalability"
    manifest = load_json(directory / "manifest.json")
    config = ROOT / "configs" / "fso-scalability.json"
    assert manifest["synthetic_only"] is True
    assert manifest["network_used"] is False
    assert manifest["external_destinations"] == 0
    assert manifest["config"] == "configs/fso-scalability.json"
    assert manifest["config_sha256"] == sha256(config)
    assert manifest["measurement_rows"] == 20
    assert manifest["parallel_rows"] == 3
    assert manifest["payload_range_bytes"] == [64, 1_048_576]
    assert manifest["coding_width_range"] == [1, 5]
    assert manifest["recoveries_verified"] == 1_612
    assert manifest["parallel_recoveries_verified"] == 96
    assert manifest["environment"]["machine"] == "arm64"
    assert manifest["environment"]["cryptography"] == "49.0.0"
    expected = {"measurements.csv": 20, "parallel_scaling.csv": 3}
    for name, count in expected.items():
        assert row_count(directory / name) == count
        assert sha256(directory / name) == manifest["files"][name]
    measurements = read_csv_rows(directory / "measurements.csv")
    assert all(int(row["recoveries_verified"]) == int(row["iterations"]) for row in measurements)
    one_megabyte = [
        row for row in measurements if int(row["payload_bytes"]) == 1_048_576
    ]
    assert len(one_megabyte) == 4
    assert all(float(row["latency_p50_ms"]) > 0 for row in one_megabyte)
    assert all(float(row["peak_rss_kib"]) > 0 for row in one_megabyte)
    parallel = read_csv_rows(directory / "parallel_scaling.csv")
    assert [int(row["workers"]) for row in parallel] == [1, 2, 4]
    assert all(int(row["recoveries_verified"]) == 32 for row in parallel)
    assert float(parallel[-1]["speedup_vs_one_worker"]) > 1.0
    return [
        "64-byte to 1-MiB codec/envelope scaling, one-to-five-shard plans, "
        "1/2/4-worker throughput, CPU/RSS observations, exact hashes, and verified recovery"
    ]


def validate_fso_deterministic_lab() -> list[str]:
    directory = ROOT / "results" / "processed" / "fso" / "deterministic-lab"
    manifest = load_json(directory / "manifest.json")
    assert manifest["deterministic"] is True
    assert manifest["synthetic_only"] is True
    assert manifest["closed_world"] is True
    assert manifest["simulated_carrier_adapters"] is True
    assert manifest["external_destinations"] == 0
    assert manifest["provider_controlled_attempts"] == 0
    assert manifest["operations"] == 125
    assert manifest["successful_operations"] == 100
    assert abs(float(manifest["availability"]) - 0.8) < 1e-12
    assert manifest["envelopes"] == manifest["unique_nonces"] == 250
    assert manifest["message_ids"] == manifest["unique_message_ids"] == 125
    assert manifest["fragment_reassembly_evictions"] == 0
    assert manifest["fragment_reassembly_inflight_at_end"] == 0
    expected_faults = {
        "ack_auth_rejections": 6,
        "ack_drops": 2,
        "data_auth_rejections": 8,
        "dropped_fragments": 318,
        "duplicated_fragments": 57,
        "tampered_fragments": 39,
    }
    assert manifest["failure_injection"] == expected_faults
    observations = directory / "observations.csv"
    assert row_count(observations) == 125
    assert sha256(observations) == manifest["observations_sha256"]
    review_bundle = validate_review_bundle(
        ROOT, ROOT / "field" / "review-bundle-manifest.json"
    )
    assert review_bundle["valid"] is True, review_bundle["failures"]
    return [
        "deterministic encrypted carrier-adapter path, exact failure-injection "
        "counters, nonce uniqueness, state expiry, and review-bundle integrity"
    ]


def validate_censorlab_results() -> list[str]:
    expected = {
        "censorlab": {
            "backend_config": "demos/mega_gfw/censor.toml",
            "successful_operations": 60,
            "availability": 1.0,
            "censored_packets": 127,
            "function_availability": {
                "file": 1.0,
                "media": 1.0,
                "presence": 1.0,
                "realtime": 1.0,
                "text": 1.0,
            },
        },
        "censorlab-campaign": {
            "backend_config": "testbeds/censorlab/campaign/censor.toml",
            "successful_operations": 13,
            "availability": 13 / 60,
            "censored_packets": 436,
            "function_availability": {
                "file": 0.0,
                "media": 1 / 12,
                "presence": 1 / 4,
                "realtime": 1 / 12,
                "text": 2 / 3,
            },
        },
    }
    commit = "3eb5997face2d897ddb50771189057815880affc"
    for directory_name, values in expected.items():
        directory = ROOT / "results" / "processed" / "fso" / directory_name
        manifest = load_json(directory / "manifest.json")
        environment = load_json(directory / "environment.json")

        assert manifest["synthetic_only"] is True
        assert manifest["closed_world"] is True
        assert manifest["offline_pcap_only"] is True
        assert manifest["external_destinations"] == 0
        assert manifest["live_interfaces"] == 0
        assert manifest["provider_controlled_attempts"] == 0
        assert manifest["application_operations"] == 60
        assert manifest["probe_operations"] == 36
        assert manifest["epochs"] == 6
        assert manifest["packets"] == 654
        assert manifest["pcap_index_offsets"] == [1]
        assert manifest["successful_operations"] == values["successful_operations"]
        assert abs(float(manifest["availability"]) - values["availability"]) < 1e-12
        assert manifest["censored_packets"] == values["censored_packets"]
        assert abs(float(manifest["conditional_no_censor_availability"]) - 1.0) < 1e-12
        for function, expected_availability in values["function_availability"].items():
            assert abs(
                float(manifest["function_availability"][function])
                - expected_availability
            ) < 1e-12

        assert manifest["backend"]["commit"] == commit
        assert manifest["backend"]["config"] == values["backend_config"]
        assert environment["censorlab_commit"] == commit
        assert environment["image_build_hash"] == commit
        assert environment["censorlab_license"] == "GPL-3.0-only"
        assert environment["container_network"] == "none"
        assert environment["container_filesystem"] == "read-only"
        assert environment["container_capabilities"] == "all dropped"
        environment_sha256 = manifest["environment"]["environment_sha256"]
        assert sha256(directory / "environment.json") == environment_sha256
        expected_environment = dict(environment)
        expected_environment["environment_sha256"] = environment_sha256
        assert manifest["environment"] == expected_environment

        config = ROOT / str(manifest["config"])
        assert sha256(config) == manifest["config_sha256"]
        expected_files = {
            "operations.csv": (96, manifest["operations_sha256"]),
            "packet-decisions.csv": (654, manifest["packet_decisions_sha256"]),
            "epochs.csv": (6, manifest["epochs_sha256"]),
        }
        for filename, (count, digest) in expected_files.items():
            path = directory / filename
            assert row_count(path) == count, f"{directory_name}/{filename}: row count"
            assert sha256(path) == digest, f"{directory_name}/{filename}: hash mismatch"

        traces = manifest["traces"]
        assert len(traces) == 6
        for expected_epoch, trace in enumerate(traces):
            assert trace["epoch"] == expected_epoch
            for key in ("labels", "log", "pcap"):
                path = directory / str(trace[key])
                assert path.is_file()
                assert sha256(path) == trace[f"{key}_sha256"]

    return [
        "pinned CensorLab and transparent campaign results, exact file hashes, "
        "headline outcomes, and closed-world containment invariants"
    ]


def bib_keys(text: str) -> set[str]:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", text))


def validate_reference_audit() -> list[str]:
    bibliography = (ROOT / "artifacts" / "references.bib").read_text(
        encoding="utf-8"
    )
    available = bib_keys(bibliography)
    validation = load_json(ROOT / "artifacts" / "reference-validation.json")
    validated = {record["key"] for record in validation["records"]}
    assert available == validated, (
        "bibliography and validation log differ: "
        f"missing validation={sorted(available - validated)}, "
        f"missing bibliography={sorted(validated - available)}"
    )
    assert all(record["status"] == "verified" for record in validation["records"])
    return [f"{len(available)} bibliography keys independently logged"]


def validate_evidence_manifest() -> list[str]:
    path = ROOT / "artifacts" / "generated" / "tdsc_evidence_manifest.json"
    manifest = load_json(path)
    assert manifest["schema_version"] == 1
    assert manifest["synthetic_or_closed_lab_only"] is True
    assert manifest["artifact_repository"] == "https://github.com/pinkysworld/CAP-ME"
    assert "no manuscript" in str(manifest["artifact_boundary"])
    assert manifest["frozen_feedback_plan_commit"] == (
        "f4ca7bdb909bdeabbb9b297004846449eab98aa0"
    )
    files = manifest["files"]
    assert len(files) == 23
    for relative, digest in files.items():
        evidence = ROOT / str(relative)
        assert evidence.is_file(), f"evidence manifest file missing: {relative}"
        assert sha256(evidence) == digest, f"evidence manifest hash mismatch: {relative}"
    return [
        f"reviewer evidence index with {len(files)} exact SHA-256 links "
        f"(manifest digest {sha256(path)})"
    ]


def main() -> int:
    checks: list[str] = []
    checks.extend(validate_processed())
    checks.extend(validate_raw_if_present())
    checks.extend(validate_robustness())
    checks.extend(validate_fso_processed())
    checks.extend(validate_fso_structure_replay())
    checks.extend(validate_fso_deterministic_lab())
    checks.extend(validate_censorlab_results())
    checks.extend(validate_fso_loopback_and_gate())
    checks.extend(validate_fso_multihost())
    checks.extend(validate_feedback_evaluation())
    checks.extend(validate_fso_scalability())
    checks.extend(validate_reference_audit())
    checks.extend(validate_evidence_manifest())
    print(json.dumps({"status": "ok", "checks": checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
