from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from courtvision_ml.evaluation import (
    binary_classification_metrics,
    expected_calibration_error,
    passes_promotion_gate,
)
from courtvision_ml.train import (
    chronological_split,
    declared_baseline_metrics,
    load_hashed_model,
    select_promotable_candidate,
    sha256,
)


def test_perfect_calibration_has_zero_error():
    labels = np.array([0, 0, 1, 1])
    probabilities = np.array([0, 0, 1, 1], dtype=float)
    assert expected_calibration_error(labels, probabilities) == 0


def test_metric_inputs_must_have_matching_shapes():
    with pytest.raises(ValueError, match="matching shapes"):
        expected_calibration_error(
            np.array([0, 1]),
            np.array([0.25]),
        )


def test_promotion_requires_both_loss_metrics_and_calibration():
    baseline = {
        "brier_score": 0.25,
        "log_loss": 0.69,
        "expected_calibration_error": 0.1,
    }

    assert passes_promotion_gate(
        {
            "brier_score": 0.24,
            "log_loss": 0.68,
            "expected_calibration_error": 0.05,
        },
        baseline,
    )
    assert not passes_promotion_gate(
        {
            "brier_score": 0.24,
            "log_loss": 0.70,
            "expected_calibration_error": 0.01,
        },
        baseline,
    )
    assert not passes_promotion_gate(
        {
            "brier_score": 0.24,
            "log_loss": 0.68,
            "expected_calibration_error": 0.051,
        },
        baseline,
    )


def test_select_promotable_candidate_uses_best_brier_then_log_loss():
    baseline = {
        "brier_score": 0.25,
        "log_loss": 0.69,
        "expected_calibration_error": 0.1,
    }
    results = {
        "candidate_a": {
            "model": object(),
            "metrics": {
                "brier_score": 0.23,
                "log_loss": 0.66,
                "expected_calibration_error": 0.04,
            },
        },
        "candidate_b": {
            "model": object(),
            "metrics": {
                "brier_score": 0.22,
                "log_loss": 0.67,
                "expected_calibration_error": 0.03,
            },
        },
    }

    winner_name, _ = select_promotable_candidate(results, baseline)
    assert winner_name == "candidate_b"


def test_select_promotable_candidate_rejects_calibrated_non_improvement():
    baseline = {
        "brier_score": 0.25,
        "log_loss": 0.69,
        "expected_calibration_error": 0.1,
    }
    results = {
        "well_calibrated_but_worse": {
            "model": object(),
            "metrics": {
                "brier_score": 0.26,
                "log_loss": 0.70,
                "expected_calibration_error": 0.01,
            },
        },
    }

    with pytest.raises(RuntimeError, match="declared baseline"):
        select_promotable_candidate(results, baseline)


def test_select_promotable_candidate_must_beat_incumbent():
    declared_baseline = {
        "brier_score": 0.25,
        "log_loss": 0.69,
        "expected_calibration_error": 0.1,
    }
    incumbent = {
        "brier_score": 0.20,
        "log_loss": 0.60,
        "expected_calibration_error": 0.03,
    }
    results = {
        "candidate": {
            "model": object(),
            "metrics": {
                "brier_score": 0.21,
                "log_loss": 0.61,
                "expected_calibration_error": 0.02,
            },
        },
    }

    with pytest.raises(RuntimeError, match="incumbent"):
        select_promotable_candidate(
            results,
            declared_baseline,
            incumbent_metrics=incumbent,
        )


def test_chronological_split_holds_out_last_two_seasons():
    frame = pd.DataFrame(
        {
            "season": [2021, 2022, 2023, 2024],
            "home_win": [0, 1, 0, 1],
        }
    )

    train, test = chronological_split(frame)

    assert train["season"].tolist() == [2021, 2022]
    assert test["season"].tolist() == [2023, 2024]


def test_declared_baseline_uses_training_prevalence_only():
    frame = pd.DataFrame(
        {
            "season": [2021, 2021, 2022, 2022, 2023, 2024],
            "home_win": [1, 0, 1, 0, 1, 1],
        }
    )

    metrics = declared_baseline_metrics(frame)
    expected = binary_classification_metrics(
        np.array([1, 1]),
        np.array([0.5, 0.5]),
    )

    assert metrics == expected


def test_artifact_hash_changes_with_artifact_bytes(tmp_path):
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"candidate-one")
    first_hash = sha256(artifact)

    artifact.write_bytes(b"candidate-two")

    assert first_hash != sha256(artifact)


def test_load_hashed_model_hashes_the_loaded_bytes(tmp_path):
    import joblib

    artifact = tmp_path / "model.joblib"
    expected_model = {"coefficient": 0.25}
    joblib.dump(expected_model, artifact)

    loaded_model, artifact_hash = load_hashed_model(artifact)

    assert loaded_model == expected_model
    assert artifact_hash == sha256(artifact)
