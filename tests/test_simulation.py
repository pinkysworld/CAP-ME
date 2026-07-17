import unittest

from capme.model import ARCHITECTURES, CENSOR_REGIMES, NETWORKS
from capme.simulation import SimulationConfig, run_simulation


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(
            epochs=4,
            operations_per_function=3,
            training_positive=30,
            training_benign=60,
            calibration_benign=1_000,
            evaluation_positive=40,
        )

    def test_run_is_reproducible(self):
        args = (
            ARCHITECTURES["fixed_proxy"],
            CENSOR_REGIMES["adaptive_cross_layer"],
            NETWORKS["mobile"],
            1234,
            self.config,
        )
        first = run_simulation(*args)
        second = run_simulation(*args)
        self.assertEqual(first.rows, second.rows)
        self.assertEqual(first.endpoint_events, second.endpoint_events)
        self.assertEqual(first.manifest, second.manifest)

    def test_output_conserves_attempts(self):
        result = run_simulation(
            ARCHITECTURES["generated_transport"],
            CENSOR_REGIMES["adaptive_cross_layer"],
            NETWORKS["stable"],
            9,
            self.config,
        )
        self.assertEqual(len(result.rows), self.config.epochs * 5)
        for row in result.rows:
            accounted = sum(
                int(row[key])
                for key in (
                    "successes",
                    "path_failures",
                    "endpoint_failures",
                    "platform_failures",
                    "network_failures",
                )
            )
            self.assertEqual(accounted, row["attempts"])
            self.assertGreaterEqual(row["availability"], 0.0)
            self.assertLessEqual(row["availability"], 1.0)


if __name__ == "__main__":
    unittest.main()
