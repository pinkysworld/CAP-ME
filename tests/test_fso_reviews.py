from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from capme.fso.reviews import validate_review_set


class FSOReviewGateTests(unittest.TestCase):
    def _record(self, kind: str, reviewer: str, bundle_id: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "review_kind": kind,
            "status": "exempt" if kind == "ethics" else "approved",
            "reviewer_name": reviewer,
            "organization": f"Independent {kind} organization",
            "independent_of_development": True,
            "reviewer_is_not_author": True,
            "conflicts_disclosed": True,
            "reviewed_bundle_id": bundle_id,
            "scope": "Synthetic traffic between named researcher-owned hosts",
            "decision_reference": f"signed-{kind}-decision",
            "review_date": "2026-07-17",
            "valid_until": "2027-07-17",
            "findings_resolved": True,
            "unresolved_findings": [],
        }

    def test_three_distinct_current_reviews_are_required(self) -> None:
        bundle_id = "a" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records: dict[str, str] = {}
            for index, kind in enumerate(("security", "ethics", "legal")):
                relative = f"{kind}.json"
                records[kind] = relative
                (root / relative).write_text(
                    json.dumps(self._record(kind, f"Reviewer {index}", bundle_id)),
                    encoding="utf-8",
                )
            valid = validate_review_set(
                root,
                records,
                bundle_id=bundle_id,
                today=dt.date(2026, 7, 17),
            )
            self.assertTrue(valid["valid"], valid["failures"])

            legal = self._record("legal", "Reviewer 0", bundle_id)
            (root / "legal.json").write_text(
                json.dumps(legal), encoding="utf-8"
            )
            duplicate = validate_review_set(
                root,
                records,
                bundle_id=bundle_id,
                today=dt.date(2026, 7, 17),
            )
            self.assertFalse(duplicate["valid"])
            self.assertIn(
                "distinct reviewers", " ".join(duplicate["failures"])
            )


if __name__ == "__main__":
    unittest.main()
