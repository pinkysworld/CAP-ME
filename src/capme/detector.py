"""A transparent diagonal-Gaussian likelihood-ratio detector.

This deliberately simple model makes the classifier assumptions inspectable.
It is not presented as a replica of a deployed national classifier.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DiagonalGaussianDetector:
    positive_mean: np.ndarray | None = None
    negative_mean: np.ndarray | None = None
    positive_var: np.ndarray | None = None
    negative_var: np.ndarray | None = None

    def fit(self, positive: np.ndarray, negative: np.ndarray) -> "DiagonalGaussianDetector":
        if positive.ndim != 2 or negative.ndim != 2:
            raise ValueError("training arrays must be two-dimensional")
        if positive.shape[1] != negative.shape[1]:
            raise ValueError("positive and negative feature counts differ")
        if len(positive) < 2 or len(negative) < 2:
            raise ValueError("each class needs at least two observations")
        floor = 1e-4
        self.positive_mean = positive.mean(axis=0)
        self.negative_mean = negative.mean(axis=0)
        self.positive_var = np.maximum(positive.var(axis=0, ddof=1), floor)
        self.negative_var = np.maximum(negative.var(axis=0, ddof=1), floor)
        return self

    def score(self, samples: np.ndarray) -> np.ndarray:
        if self.positive_mean is None or self.negative_mean is None:
            raise RuntimeError("detector has not been fitted")
        samples = np.atleast_2d(samples)
        pos = -0.5 * np.sum(
            np.log(self.positive_var)
            + ((samples - self.positive_mean) ** 2) / self.positive_var,
            axis=1,
        )
        neg = -0.5 * np.sum(
            np.log(self.negative_var)
            + ((samples - self.negative_mean) ** 2) / self.negative_var,
            axis=1,
        )
        return pos - neg


def calibrate_threshold(benign_scores: np.ndarray, false_positive_cap: float) -> float:
    """Return a conservative empirical threshold for the requested FPR cap."""
    if benign_scores.ndim != 1 or len(benign_scores) == 0:
        raise ValueError("benign_scores must be a non-empty vector")
    if not 0 < false_positive_cap < 1:
        raise ValueError("false_positive_cap must lie in (0, 1)")
    ordered = np.sort(benign_scores)
    allowed = int(np.floor(false_positive_cap * len(ordered)))
    if allowed == 0:
        return float(np.nextafter(ordered[-1], np.inf))
    index = max(0, len(ordered) - allowed)
    return float(np.nextafter(ordered[index], np.inf))


def operating_point(
    positive_scores: np.ndarray,
    benign_scores: np.ndarray,
    threshold: float,
    prevalence: float = 0.001,
) -> dict[str, float]:
    if not 0 < prevalence < 1:
        raise ValueError("prevalence must lie in (0, 1)")
    tpr = float(np.mean(positive_scores >= threshold))
    fpr = float(np.mean(benign_scores >= threshold))
    denominator = prevalence * tpr + (1.0 - prevalence) * fpr
    precision = float(prevalence * tpr / denominator) if denominator else 1.0
    return {"tpr": tpr, "fpr": fpr, "precision": precision}
