from __future__ import annotations

import argparse
import hashlib
import json
import platform
from io import BytesIO
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_hashed_model(path: Path) -> tuple[object, str]:
    artifact_bytes = path.read_bytes()
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    return joblib.load(BytesIO(artifact_bytes)), artifact_sha256


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


def evaluate_model(frame: pd.DataFrame, model: object) -> MetricSet:
    _, test = chronological_split(frame)
    probabilities = model.predict_proba(test[FEATURES])[:, 1]
    return binary_classification_metrics(
        test["home_win"].to_numpy(),
        probabilities,
    )


def select_promotable_candidate(
    results: dict[str, object],
    baseline_metrics: MetricSet,
    *,
    incumbent_metrics: MetricSet | None = None,
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
        ) and (
            incumbent_metrics is None
            or passes_promotion_gate(
                metrics,
                incumbent_metrics,
                max_expected_calibration_error=max_expected_calibration_error,
            )
        ):
            eligible[name] = raw_result

    if not eligible:
        comparison = (
            "the declared and incumbent baselines"
            if incumbent_metrics is not None
            else "the declared baseline"
        )
        raise RuntimeError(
            f"No candidate beat {comparison} on Brier score and log loss "
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
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--training-commit", default="uncommitted")
    parser.add_argument("--incumbent-artifact", type=Path)
    parser.add_argument("--incumbent-version")
    args = parser.parse_args()
    if bool(args.incumbent_artifact) != bool(args.incumbent_version):
        parser.error(
            "--incumbent-artifact and --incumbent-version must be provided together"
        )

    frame = pd.read_parquet(args.dataset)
    results = train_candidates(frame)
    baseline_metrics = declared_baseline_metrics(frame)
    incumbent = None
    incumbent_metrics = None
    if args.incumbent_artifact:
        incumbent_model, incumbent_sha256 = load_hashed_model(
            args.incumbent_artifact
        )
        incumbent_metrics = evaluate_model(frame, incumbent_model)
        incumbent = {
            "model_version": args.incumbent_version,
            "artifact_sha256": incumbent_sha256,
            "metrics": incumbent_metrics,
        }
    winner_name, winner = select_promotable_candidate(
        results,
        baseline_metrics,
        incumbent_metrics=incumbent_metrics,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    artifact_path = args.output / "model.joblib"
    joblib.dump(winner["model"], artifact_path)
    (args.output / "metadata.json").write_text(
        json.dumps(
            {
                "model_type": "pregame",
                "model_version": args.model_version,
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
                "artifact": {
                    "filename": artifact_path.name,
                    "sha256": sha256(artifact_path),
                },
                "calibration": {
                    "method": "sigmoid",
                    "artifact": "embedded",
                },
                "runtime": {
                    "python": ".".join(platform.python_version_tuple()[:2]),
                    "joblib": joblib.__version__,
                    "numpy": np.__version__,
                    "pandas": pd.__version__,
                    "scikit_learn": sklearn.__version__,
                },
                "incumbent": incumbent,
                "feature_schema_version": "pregame-v1",
                "training_commit": args.training_commit,
                "activation_status": "candidate",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
