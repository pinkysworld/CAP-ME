from __future__ import annotations

import json
import unittest
from pathlib import Path

from capme.fso.independent import generate_independent_trace


ROOT = Path(__file__).resolve().parents[1]


class IndependentTraceTests(unittest.TestCase):
    def test_trace_is_deterministic_and_complete(self) -> None:
        config = json.loads(
            (ROOT / "configs" / "fso-independent-replay.json").read_text(
                encoding="utf-8"
            )
        )
        config["seeds"] = config["seeds"][:2]
        config["epochs"] = 3
        first = generate_independent_trace(config)
        second = generate_independent_trace(config)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2 * 5 * 3 * 5)
        self.assertTrue(all(0.0 < float(row["availability"]) < 1.0 for row in first))
        self.assertTrue(all(float(row["mean_completion_ms"]) > 0.0 for row in first))


if __name__ == "__main__":
    unittest.main()
