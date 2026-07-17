from __future__ import annotations

import unittest

from capme.fso.benchmark import run_case


class FSOBenchmarkTests(unittest.TestCase):
    def test_small_pipeline_case_recovers_every_payload(self) -> None:
        result = run_case(
            name="test-2-of-3",
            payload_bytes=257,
            iterations=2,
            threshold=2,
            total_shards=3,
            max_fragment_data=113,
            seed=77,
            label="unit-test",
        )
        self.assertEqual(result["recoveries_verified"], 2)
        self.assertGreater(result["wire_overhead"], 1.0)
        self.assertGreater(result["operations_per_second"], 0.0)


if __name__ == "__main__":
    unittest.main()
