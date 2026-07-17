from __future__ import annotations

import unittest

import numpy as np

from capme.model import ARCHITECTURES, CENSOR_REGIMES, NETWORKS
from capme.robustness import (
    apply_uncertainty,
    latin_hypercube,
    partial_rank_correlation,
)


class RobustnessTests(unittest.TestCase):
    def test_latin_hypercube_is_deterministic_and_stratified(self) -> None:
        left = latin_hypercube(12, 4, 771)
        right = latin_hypercube(12, 4, 771)
        np.testing.assert_array_equal(left, right)
        for column in range(left.shape[1]):
            strata = np.floor(left[:, column] * len(left)).astype(int)
            self.assertEqual(sorted(strata.tolist()), list(range(len(left))))

    def test_uncertainty_application_preserves_bounds(self) -> None:
        architecture, censor, network = apply_uncertainty(
            ARCHITECTURES["generated_transport"],
            CENSOR_REGIMES["adaptive_cross_layer"],
            NETWORKS["mobile"],
            {
                "architecture_endpoint_pool_multiplier": 0.01,
                "architecture_passive_separability_multiplier": 10.0,
                "censor_path_enforcement": 2.0,
                "network_loss_multiplier": 100.0,
            },
        )
        self.assertGreaterEqual(architecture.endpoint_pool, 1)
        self.assertLessEqual(architecture.passive_separability, 1.0)
        self.assertLessEqual(censor.path_enforcement, 1.0)
        self.assertLessEqual(network.loss_rate, 1.0)

    def test_prcc_recovers_monotone_parameter(self) -> None:
        rng = np.random.default_rng(91)
        matrix = rng.random((200, 4))
        outcome = 3.0 * matrix[:, 0] + 0.05 * rng.normal(size=200)
        self.assertGreater(partial_rank_correlation(matrix, outcome, 0), 0.95)


if __name__ == "__main__":
    unittest.main()
