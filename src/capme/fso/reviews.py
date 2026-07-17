"""Deterministic review bundle and independent-review record validation."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Mapping

from capme.io import sha256_file, write_json

REVIEW_KINDS = ("security", "ethics", "legal")
CRITICAL_REVIEW_FILES = (
    "pyproject.toml",
    "artifacts/reference-environment.json",
    "src/capme/io.py",
    "src/capme/fso/coding.py",
    "src/capme/fso/crypto.py",
    "src/capme/fso/framing.py",
    "src/capme/fso/protocol.py",
    "src/capme/fso/scheduler.py",
    "src/capme/fso/lab.py",
    "src/capme/fso/testbed.py",
    "src/capme/fso/multihost.py",
    "src/capme/fso/censorlab.py",
    "src/capme/fso/deployment.py",
    "src/capme/fso/reviews.py",
    "analysis/run_censorlab_study.py",
    "analysis/run_fso_multihost.py",
    "configs/fso-deterministic-lab.json",
    "configs/fso-censorlab.json",
    "configs/fso-censorlab-campaign.json",
    "configs/fso-multihost.json",
    "testbeds/censorlab/Dockerfile.pcap",
    "testbeds/censorlab/README.md",
    "testbeds/censorlab/campaign/censor.toml",
    "testbeds/censorlab/campaign/campaign_censor.py",
    ".dockerignore",
    "testbeds/multihost/Dockerfile",
    "testbeds/multihost/requirements.txt",
    "testbeds/multihost/README.md",
    "results/processed/fso/deterministic-lab/manifest.json",
    "results/processed/fso/censorlab/manifest.json",
    "results/processed/fso/censorlab-campaign/manifest.json",
    "results/processed/fso/multihost/manifest.json",
    "results/processed/fso/multihost/environment.json",
    "docs/fso-protocol.md",
    "docs/ethics.md",
    "field/study-protocol.md",
    "field/stop-rules.md",
)


def _bundle_id(files: Mapping[str, str]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def build_review_bundle(root: Path, output: Path) -> dict[str, object]:
    files: dict[str, str] = {}
    missing: list[str] = []
    for relative in CRITICAL_REVIEW_FILES:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
        else:
            files[relative] = sha256_file(path)
    if missing:
        raise FileNotFoundError(f"review bundle inputs missing: {missing}")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact": "CAP-ME FSO",
        "artifact_version": "0.3.0",
        "bundle_id": _bundle_id(files),
        "files": files,
        "scope": (
            "Exact source, deterministic-lab evidence, offline CensorLab "
            "bridge, protocol, ethics, study protocol, and stop rules "
            "proposed for independent review"
        ),
    }
    write_json(output, manifest)
    return manifest


def validate_review_bundle(root: Path, path: Path) -> dict[str, object]:
    failures: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"valid": False, "bundle_id": "", "failures": [str(error)]}
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return {
            "valid": False,
            "bundle_id": "",
            "failures": ["review bundle must contain file hashes"],
        }
    normalized = {str(key): str(value) for key, value in files.items()}
    declared_paths = set(normalized)
    required_paths = set(CRITICAL_REVIEW_FILES)
    for relative in sorted(required_paths - declared_paths):
        failures.append(f"review bundle omits required file: {relative}")
    for relative in sorted(declared_paths - required_paths):
        failures.append(f"review bundle contains unexpected file: {relative}")
    for relative, expected in normalized.items():
        candidate = root / relative
        if not candidate.is_file():
            failures.append(f"review bundle file is missing: {relative}")
        elif sha256_file(candidate) != expected:
            failures.append(f"review bundle file changed: {relative}")
    computed = _bundle_id(normalized)
    declared = str(manifest.get("bundle_id", ""))
    if computed != declared:
        failures.append("review bundle ID does not match its file hashes")
    return {
        "valid": not failures,
        "bundle_id": declared,
        "failures": failures,
    }


def validate_review_record(
    path: Path,
    *,
    expected_kind: str,
    expected_bundle_id: str,
    today: dt.date,
) -> dict[str, object]:
    failures: list[str] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "valid": False,
            "review_kind": expected_kind,
            "reviewer_name": "",
            "organization": "",
            "failures": [str(error)],
        }
    if value.get("review_kind") != expected_kind:
        failures.append(f"review_kind must be {expected_kind}")
    allowed_status = {"approved", "exempt"} if expected_kind == "ethics" else {"approved"}
    if value.get("status") not in allowed_status:
        failures.append(
            f"{expected_kind} review status must be one of {sorted(allowed_status)}"
        )
    required_text = (
        "reviewer_name",
        "organization",
        "scope",
        "decision_reference",
    )
    for key in required_text:
        text = str(value.get(key, "")).strip()
        if not text or "REPLACE-WITH" in text:
            failures.append(f"{expected_kind} review {key} is incomplete")
    for key in (
        "independent_of_development",
        "reviewer_is_not_author",
        "conflicts_disclosed",
        "findings_resolved",
    ):
        if value.get(key) is not True:
            failures.append(f"{expected_kind} review {key} must be true")
    if value.get("reviewed_bundle_id") != expected_bundle_id:
        failures.append(f"{expected_kind} review covers the wrong bundle")
    dates: dict[str, dt.date] = {}
    for key in ("review_date", "valid_until"):
        try:
            dates[key] = dt.date.fromisoformat(str(value[key]))
        except (KeyError, ValueError):
            failures.append(f"{expected_kind} review {key} must be an ISO date")
    if dates.get("review_date", today) > today:
        failures.append(f"{expected_kind} review date is in the future")
    if dates.get("valid_until", today) < today:
        failures.append(f"{expected_kind} review has expired")
    unresolved = value.get("unresolved_findings")
    if unresolved not in ([], None):
        failures.append(f"{expected_kind} review has unresolved findings")
    return {
        "valid": not failures,
        "review_kind": expected_kind,
        "reviewer_name": str(value.get("reviewer_name", "")).strip(),
        "organization": str(value.get("organization", "")).strip(),
        "failures": failures,
    }


def validate_review_set(
    root: Path,
    records: Mapping[str, object],
    *,
    bundle_id: str,
    today: dt.date,
) -> dict[str, object]:
    failures: list[str] = []
    reviews: list[dict[str, object]] = []
    for kind in REVIEW_KINDS:
        relative = str(records.get(kind, "")).strip()
        if not relative or "REPLACE-WITH" in relative:
            failures.append(f"{kind} review record path is incomplete")
            continue
        review = validate_review_record(
            root / relative,
            expected_kind=kind,
            expected_bundle_id=bundle_id,
            today=today,
        )
        reviews.append(review)
        failures.extend(str(value) for value in review["failures"])
    identities = {
        str(review["reviewer_name"]).casefold()
        for review in reviews
        if review["reviewer_name"]
    }
    if len(reviews) == len(REVIEW_KINDS) and len(identities) != len(REVIEW_KINDS):
        failures.append("security, ethics, and legal reviews require distinct reviewers")
    return {"valid": not failures, "reviews": reviews, "failures": failures}
