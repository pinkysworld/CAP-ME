"""Non-networking completeness validator for a future authorized field study."""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
from pathlib import Path

from .reviews import validate_review_bundle, validate_review_set

REQUIRED_TEXT = (
    "study_id",
    "principal_investigator",
    "institution",
    "ethics_review_reference",
    "legal_review_reference",
    "security_review_reference",
    "infrastructure_owner",
    "stop_contact",
)


def validate_authorization(path: Path, *, today: dt.date | None = None) -> dict[str, object]:
    today = today or dt.date.today()
    value = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    requested_scope = str(value.get("requested_scope", ""))
    if requested_scope not in {"loopback-only", "external-owned-hosts"}:
        failures.append("requested_scope must be loopback-only or external-owned-hosts")
    if value.get("status") != "approved":
        failures.append("status must be approved")
    if value.get("approvals_confirmed") is not True:
        failures.append("approvals_confirmed must be true")
    for key in REQUIRED_TEXT:
        text = str(value.get(key, "")).strip()
        if not text or "REPLACE-WITH" in text:
            failures.append(f"{key} is incomplete")
    hosts = value.get("approved_hosts", [])
    parsed_hosts: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    if not isinstance(hosts, list) or not hosts:
        failures.append("approved_hosts must contain named owned endpoints")
    else:
        for host in hosts:
            try:
                address = ipaddress.ip_address(str(host))
            except ValueError:
                failures.append(f"approved host must be a literal address: {host}")
                continue
            if address.is_multicast or address.is_unspecified:
                failures.append(f"unsafe approved host: {host}")
            else:
                parsed_hosts.append(address)
    for key in ("valid_from", "valid_until"):
        try:
            value[key] = dt.date.fromisoformat(str(value[key]))
        except (KeyError, ValueError):
            failures.append(f"{key} must be an ISO date")
    if isinstance(value.get("valid_from"), dt.date) and value["valid_from"] > today:
        failures.append("authorization is not yet valid")
    if isinstance(value.get("valid_until"), dt.date) and value["valid_until"] < today:
        failures.append("authorization has expired")
    if value.get("human_participants") is not False:
        failures.append("initial study must not include human participants")
    if value.get("third_party_traffic") is not False:
        failures.append("initial study must exclude third-party traffic")
    if value.get("active_probing") is not False:
        failures.append("initial study must prohibit active probing")
    if value.get("personal_data_categories") not in ([], None):
        failures.append("initial study must collect no personal-data categories")
    for key in ("maximum_operations", "maximum_duration_minutes"):
        if not isinstance(value.get(key), int) or int(value[key]) <= 0:
            failures.append(f"{key} must be a positive integer")
    review_gate: dict[str, object] = {
        "required": requested_scope == "external-owned-hosts",
        "valid": requested_scope != "external-owned-hosts",
        "failures": [],
    }
    if requested_scope == "loopback-only" and any(
        not address.is_loopback for address in parsed_hosts
    ):
        failures.append("loopback-only authorization contains an external host")
    if requested_scope == "external-owned-hosts":
        if not any(not address.is_loopback for address in parsed_hosts):
            failures.append("external deployment requires a named non-loopback owned host")
        root = path.resolve().parents[1]
        bundle_relative = str(value.get("review_bundle", "")).strip()
        if not bundle_relative or "REPLACE-WITH" in bundle_relative:
            failures.append("review_bundle is incomplete")
            review_gate = {
                "required": True,
                "valid": False,
                "failures": ["review_bundle is incomplete"],
            }
        else:
            bundle = validate_review_bundle(root, root / bundle_relative)
            review_failures = [str(item) for item in bundle["failures"]]
            records = value.get("review_records", {})
            if not isinstance(records, dict):
                records = {}
                review_failures.append("review_records must be an object")
            review_set = validate_review_set(
                root,
                records,
                bundle_id=str(bundle["bundle_id"]),
                today=today,
            )
            review_failures.extend(str(item) for item in review_set["failures"])
            failures.extend(review_failures)
            review_gate = {
                "required": True,
                "valid": not review_failures,
                "bundle_id": bundle["bundle_id"],
                "failures": review_failures,
            }
    complete = not failures
    external_scope = (
        complete
        and requested_scope == "external-owned-hosts"
        and any(not address.is_loopback for address in parsed_hosts)
    )
    return {
        "schema_version": 1,
        "manifest": str(path),
        "authorization_complete": complete,
        "scope": requested_scope or "invalid",
        "ready_for_external_implementation": external_scope,
        "review_gate": review_gate,
        "failures": failures,
        "notice": (
            "This validator checks document completeness only; it does not grant "
            "ethical, legal, security, infrastructure, or deployment authorization."
        ),
    }
