from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from courtvision_ml.evaluation import (
    MetricSet,
    binary_classification_metrics,
    passes_promotion_gate,
)


FEATURES = [
    "home_offensive_rating",
    "away_offensive_rating",
    "home_defensive_rating",
    "away_defensive_rating",
    "home_pace",
    "away_pace",
    "home_rest_days",
    "away_rest_days",
]


def chronological_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    seasons = sorted(frame["season"].unique())
    if len(seasons) < 3:
        raise ValueError("At least three seasons are required for a chronological split")
    cutoff = seasons[-2]
    return frame[frame["season"] < cutoff], frame[frame["season"] >= cutoff]


def declared_baseline_metrics(frame: pd.DataFrame) -> MetricSet:
    train, test = chronological_split(frame)
    home_win_rate = float(train["home_win"].mean())
    probabilities = np.full(len(test), home_win_rate, dtype=float)
    return binary_classification_metrics(
        test["home_win"].to_numpy(),
        probabilities,
    )


def train_candidates(frame: pd.DataFrame) -> dict[str, object]:
    train, test = chronological_split(frame)
    candidates = {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_depth=4),
    }
    results: dict[str, object] = {}
    for name, model in candidates.items():
        calibrated = CalibratedClassifierCV(model, method="sigmoid", cv=3)
        calibrated.fit(train[FEATURES], train["home_win"])
        probabilities = calibrated.predict_proba(test[FEATURES])[:, 1]
        results[name] = {
            "model": calibrated,
            "metrics": binary_classification_metrics(
                test["home_win"].to_numpy(),
                probabilities,
            ),
        }
    return results


def select_promotable_candidate(
    results: dict[str, object],
    baseline_metrics: MetricSet,
    *,
    max_expected_calibration_error: float = 0.05,
) -> tuple[str, dict[str, object]]:
    eligible: dict[str, dict[str, object]] = {}
    for name, raw_result in results.items():
        if not isinstance(raw_result, dict):
            raise TypeError(f"Candidate {name} has an invalid result")
        metrics = raw_result.get("metrics")
        if not isinstance(metrics, dict):
            raise TypeError(f"Candidate {name} is missing metrics")
        if passes_promotion_gate(
            metrics,
            baseline_metrics,
            max_expected_calibration_error=max_expected_calibration_error,
        ):
            eligible[name] = raw_result

    if not eligible:
        raise RuntimeError(
            "No candidate beat the declared baseline on Brier score and log loss "
            "while passing the calibration gate"
        )

    return min(
        eligible.items(),
        key=lambda item: (
            item[1]["metrics"]["brier_score"],
            item[1]["metrics"]["log_loss"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("ml/artifacts/pregame"))
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--training-commit", default="uncommitted")
    args = parser.parse_args()

    frame = pd.read_parquet(args.dataset)
    results = train_candidates(frame)
    baseline_metrics = declared_baseline_metrics(frame)
    winner_name, winner = select_promotable_candidate(
        results,
        baseline_metrics,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    joblib.dump(winner["model"], args.output / "model.joblib")
    (args.output / "metadata.json").write_text(
        json.dumps(
            {
                "winner": winner_name,
                "features": FEATURES,
                "metrics": winner["metrics"],
                "baseline": {
                    "name": "training_home_win_prevalence",
                    "metrics": baseline_metrics,
                },
                "split": "chronological_last_two_seasons",
                "dataset": {
                    "path": str(args.dataset),
                    "version": args.dataset_version,
                },
                "feature_schema_version": "pregame-v1",
                "training_commit": args.training_commit,
                "activation_status": "candidate",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
