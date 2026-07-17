from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from capme.fso.deployment import validate_authorization
from capme.fso.reviews import validate_review_bundle
from capme.fso.testbed import require_loopback


ROOT = Path(__file__).resolve().parents[1]


class FSOSafetyTests(unittest.TestCase):
    def test_loopback_guard_rejects_external_address(self) -> None:
        require_loopback("127.0.0.1")
        require_loopback("::1")
        with self.assertRaisesRegex(ValueError, "external destination"):
            require_loopback("8.8.8.8")

    def test_pending_field_template_is_not_authorized(self) -> None:
        result = validate_authorization(
            ROOT / "field" / "authorization-template.json",
            today=dt.date(2026, 7, 17),
        )
        self.assertFalse(result["authorization_complete"])
        self.assertFalse(result["ready_for_external_implementation"])
        self.assertGreater(len(result["failures"]), 5)
        self.assertTrue(result["review_gate"]["required"])
        self.assertFalse(result["review_gate"]["valid"])

    def test_local_synthetic_manifest_is_complete(self) -> None:
        result = validate_authorization(
            ROOT / "field" / "loopback-authorization.json",
            today=dt.date(2026, 7, 17),
        )
        self.assertTrue(result["authorization_complete"])
        self.assertFalse(result["ready_for_external_implementation"])
        self.assertEqual(result["scope"], "loopback-only")
        self.assertEqual(result["failures"], [])
        self.assertFalse(result["review_gate"]["required"])

    def test_review_bundle_matches_exact_security_relevant_files(self) -> None:
        result = validate_review_bundle(
            ROOT, ROOT / "field" / "review-bundle-manifest.json"
        )
        self.assertTrue(result["valid"], result["failures"])
        self.assertEqual(len(result["bundle_id"]), 64)

    def test_review_bundle_cannot_omit_a_required_file(self) -> None:
        source = ROOT / "field" / "review-bundle-manifest.json"
        manifest = json.loads(source.read_text(encoding="utf-8"))
        omitted = next(iter(manifest["files"]))
        del manifest["files"][omitted]
        payload = json.dumps(
            manifest["files"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        manifest["bundle_id"] = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truncated-bundle.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result = validate_review_bundle(ROOT, path)
        self.assertFalse(result["valid"])
        self.assertIn(
            f"review bundle omits required file: {omitted}",
            result["failures"],
        )


if __name__ == "__main__":
    unittest.main()
