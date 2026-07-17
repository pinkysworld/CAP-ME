import tempfile
import unittest
from pathlib import Path

from capme.analysis import benjamini_hochberg, bootstrap_mean, compute_run_metrics
from capme.io import write_csv


class AnalysisTests(unittest.TestCase):
    def test_bootstrap_is_deterministic(self):
        first = bootstrap_mean([0.1, 0.2, 0.3], seed=11, repetitions=200)
        second = bootstrap_mean([0.1, 0.2, 0.3], seed=11, repetitions=200)
        self.assertEqual(first, second)

    def test_bh_is_monotone_in_sorted_order(self):
        raw = [0.04, 0.001, 0.02, 0.5]
        adjusted = benjamini_hochberg(raw)
        ordered = [adjusted[index] for index in sorted(range(len(raw)), key=raw.__getitem__)]
        self.assertEqual(ordered, sorted(ordered))
        self.assertTrue(all(0 <= value <= 1 for value in adjusted))

    def test_csv_serialization_uses_repository_canonical_lf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.csv"
            write_csv(path, [{"value": 1}, {"value": 2}])
            payload = path.read_bytes()
        self.assertNotIn(b"\r\n", payload)
        self.assertEqual(payload.count(b"\n"), 3)


if __name__ == "__main__":
    unittest.main()
