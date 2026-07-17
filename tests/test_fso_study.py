from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from capme.fso.study import (
    TRACE_ARCHITECTURES,
    _interval_interpretation,
    _unit_uniform,
    prepare_lane_traces,
)
from capme.fso.types import FUNCTIONS


class FSOStudyTests(unittest.TestCase):
    def test_interval_scope_uses_declared_seed_count(self) -> None:
        interpretation = _interval_interpretation(12)
        self.assertIn("12 declared synthetic seeds", interpretation)
        self.assertNotIn("20", interpretation)

    def test_common_random_draw_is_stable_and_scoped(self) -> None:
        first = _unit_uniform(4001, 3, "text", 7, "generated-0", "lane")
        second = _unit_uniform(4001, 3, "text", 7, "generated-0", "lane")
        other = _unit_uniform(4001, 3, "text", 7, "ephemeral-0", "lane")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertGreater(first, 0.0)
        self.assertLess(first, 1.0)

    def test_trace_preparation_accepts_an_exact_non_twenty_seed_grid(self) -> None:
        fields = (
            "seed",
            "architecture",
            "epoch",
            "function",
            "censor",
            "network",
            "endpoint_pool",
            "availability",
            "mean_completion_ms",
            "blocked_endpoints",
            "endpoint_burns_epoch",
        )
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            source = directory / "source.csv"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                for seed in (71, 73):
                    for architecture in sorted(TRACE_ARCHITECTURES):
                        for epoch in range(2):
                            for function in FUNCTIONS:
                                writer.writerow(
                                    {
                                        "seed": seed,
                                        "architecture": architecture,
                                        "epoch": epoch,
                                        "function": function,
                                        "censor": "adaptive_cross_layer",
                                        "network": "mobile",
                                        "endpoint_pool": 10,
                                        "availability": 0.75,
                                        "mean_completion_ms": 100,
                                        "blocked_endpoints": 2,
                                        "endpoint_burns_epoch": 1,
                                    }
                                )
            output = directory / "trace.csv"
            manifest = prepare_lane_traces(source, output)
            self.assertEqual(manifest["rows"], 100)
            self.assertEqual(manifest["seeds"], [71, 73])
            self.assertEqual(manifest["epochs"], [0, 1])


if __name__ == "__main__":
    unittest.main()
