import unittest

import numpy as np

from capme.detector import DiagonalGaussianDetector, calibrate_threshold, operating_point


class DetectorTests(unittest.TestCase):
    def test_calibration_respects_empirical_cap(self):
        scores = np.linspace(-2.0, 2.0, 10_000)
        threshold = calibrate_threshold(scores, 0.001)
        self.assertLessEqual(float(np.mean(scores >= threshold)), 0.001)

    def test_likelihood_detector_separates_shifted_class(self):
        rng = np.random.default_rng(7)
        benign = rng.normal(0.0, 1.0, size=(2_000, 5))
        positive = rng.normal(1.5, 1.0, size=(1_000, 5))
        detector = DiagonalGaussianDetector().fit(positive[:500], benign[:500])
        benign_scores = detector.score(benign[500:])
        threshold = calibrate_threshold(benign_scores, 0.01)
        metrics = operating_point(detector.score(positive[500:]), benign_scores, threshold)
        self.assertGreater(metrics["tpr"], 0.50)
        self.assertLessEqual(metrics["fpr"], 0.01)


if __name__ == "__main__":
    unittest.main()
