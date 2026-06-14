from __future__ import annotations

import numpy as np
from sklearn.metrics import brier_score_loss, log_loss


MetricSet = dict[str, float]


def expected_calibration_error(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    bins: int = 10,
) -> float:
    if bins < 1:
        raise ValueError("bins must be at least 1")
    if y_true.shape != probabilities.shape:
        raise ValueError("labels and probabilities must have matching shapes")

    boundaries = np.linspace(0, 1, bins + 1)
    error = 0.0
    for lower, upper in zip(boundaries[:-1], boundaries[1:], strict=True):
        inclusive = probabilities <= upper if upper == 1 else probabilities < upper
        mask = (probabilities >= lower) & inclusive
        if not np.any(mask):
            continue
        accuracy = float(np.mean(y_true[mask]))
        confidence = float(np.mean(probabilities[mask]))
        error += float(np.mean(mask)) * abs(accuracy - confidence)
    return error


def binary_classification_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    *,
    bins: int = 10,
) -> MetricSet:
    return {
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "log_loss": float(log_loss(y_true, probabilities, labels=[0, 1])),
        "expected_calibration_error": expected_calibration_error(
            y_true,
            probabilities,
            bins=bins,
        ),
    }


def passes_promotion_gate(
    candidate: MetricSet,
    baseline: MetricSet,
    *,
    max_expected_calibration_error: float = 0.05,
) -> bool:
    return (
        candidate["brier_score"] < baseline["brier_score"]
        and candidate["log_loss"] < baseline["log_loss"]
        and candidate["expected_calibration_error"]
        <= max_expected_calibration_error
    )
