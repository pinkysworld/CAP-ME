"""Self-contained validation for the CAP-ME research artifact."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from capme.fso.deployment import validate_authorization
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
    fso = _find_row(aggregates, "strategy", "fso")
    session = _find_row(aggregates, "strategy", "session_failover")
    no_semantics = _find_row(aggregates, "strategy", "fso_no_semantics")
    assert abs(float(fso["auac"]) - 0.9123177083333334) < 1e-12
    assert abs(float(session["auac"]) - 0.8960677083333332) < 1e-12
    assert abs(float(fso["byte_overhead"]) - 1.246435542835698) < 1e-12
    assert abs(float(no_semantics["byte_overhead"]) - 2.000061214729795) < 1e-12
    contrasts = read_csv_rows(processed / "paired_contrasts.csv")
    session_contrast = _find_row(contrasts, "baseline", "session_failover")
    feedback_contrast = _find_row(contrasts, "baseline", "fso_no_feedback")
    assert abs(float(session_contrast["mean_difference"]) - 0.01625) < 1e-12
    assert float(session_contrast["ci_low"]) > 0
    assert float(feedback_contrast["mean_difference"]) < 0

    raw = ROOT / "results" / "raw" / "fso-confirmation" / "observations.csv"
    if raw.exists():
        assert sha256(raw) == manifest["raw_files"]["observations.csv"]
        raw_status = "including raw observation hash"
    else:
        raw_status = "raw observations absent but regenerable"
    return [
        "FSO counts, disjoint seeds, hashes, trust invariant, and headline values "
        f"({raw_status})"
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


def main() -> int:
    checks: list[str] = []
    checks.extend(validate_processed())
    checks.extend(validate_raw_if_present())
    checks.extend(validate_fso_processed())
    checks.extend(validate_fso_deterministic_lab())
    checks.extend(validate_censorlab_results())
    checks.extend(validate_fso_loopback_and_gate())
    checks.extend(validate_reference_audit())
    print(json.dumps({"status": "ok", "checks": checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
