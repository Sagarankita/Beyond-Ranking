"""Train and validate the explicitly synthetic Phase 3 response-model track."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from department_optimizer.data.schemas import get_schema
from department_optimizer.data.validation import validate_dataframe

from .core import (
    bounded_interval,
    conformal_radius,
    deterministic_split,
    regression_metrics,
    residual_diagnostics,
    validate_modeling_frame,
)


def _sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_models(config: dict):
    seed = int(config["split"]["model_seed"])
    forest = config["random_forest"]
    return {
        "mean": Pipeline(
            [("imputer", SimpleImputer(strategy="median")), ("model", DummyRegressor(strategy="mean"))]
        ),
        "linear": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", LinearRegression()),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=int(forest["n_estimators"]),
                        min_samples_leaf=int(forest["min_samples_leaf"]),
                        max_features=forest["max_features"],
                        random_state=seed,
                        n_jobs=int(forest["n_jobs"]),
                    ),
                ),
            ]
        ),
    }


def train_from_config(config_path: Path, output_dir: Path):
    config = json.loads(config_path.read_text())
    data_path = Path(config["data_path"])
    frame = pd.read_csv(data_path)
    report = validate_dataframe(frame, get_schema(config["data_schema"]))
    if report.has_errors:
        raise ValueError(f"source data failed Phase 1 validation: {report.to_dict()}")
    numeric = validate_modeling_frame(frame, config)
    split = deterministic_split(len(frame), config["split"])
    features = config["feature_columns"]
    targets = config["target_columns"]
    x = numeric[features]

    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / "models"
    models_dir.mkdir(exist_ok=True)
    metric_rows = []
    diagnostic_rows = []
    test_rows = []
    selected_models = {}
    conformal_radii = {}
    test_evaluation = {}

    for target in targets:
        fitted = {}
        for name, model in _candidate_models(config).items():
            model.fit(x.iloc[split.train], numeric[target].iloc[split.train])
            fitted[name] = model
            for split_name, indices in (("validation", split.validation), ("test", split.test)):
                prediction = model.predict(x.iloc[indices])
                metric_rows.append(
                    {
                        "target": target,
                        "model": name,
                        "split": split_name,
                        **regression_metrics(numeric[target].iloc[indices], prediction),
                    }
                )
        validation_rows = [
            row for row in metric_rows if row["target"] == target and row["split"] == "validation"
        ]
        selected_name = min(validation_rows, key=lambda row: (row["rmse"], row["mae"], row["model"]))["model"]
        selected = fitted[selected_name]
        calibration_prediction = selected.predict(x.iloc[split.calibration])
        alpha = float(config["prediction_interval"]["miscoverage_alpha"])
        radius = conformal_radius(
            numeric[target].iloc[split.calibration], calibration_prediction, alpha
        )
        conformal_radii[target] = radius
        test_prediction = np.asarray(selected.predict(x.iloc[split.test]), dtype=float)
        target_bounds = config["target_bounds"][target]
        if target_bounds[0] is not None:
            test_prediction = np.maximum(test_prediction, target_bounds[0])
        if target_bounds[1] is not None:
            test_prediction = np.minimum(test_prediction, target_bounds[1])
        lower, upper = bounded_interval(test_prediction, radius, target_bounds)
        actual = numeric[target].iloc[split.test].to_numpy(dtype=float)
        coverage = float(np.mean((actual >= lower) & (actual <= upper)))
        selected_test_metrics = regression_metrics(actual, test_prediction)
        metric_rows.append(
            {
                "target": target,
                "model": selected_name,
                "split": "test_selected_with_interval",
                **selected_test_metrics,
                "interval_coverage": coverage,
                "interval_mean_width": float(np.mean(upper - lower)),
            }
        )
        diagnostic_rows.append(
            {
                "target": target,
                "model": selected_name,
                "split": "test",
                **residual_diagnostics(actual, test_prediction),
            }
        )
        for position, row_index in enumerate(split.test):
            test_rows.append(
                {
                    config["id_column"]: frame[config["id_column"]].iloc[row_index],
                    "target": target,
                    "actual": actual[position],
                    "prediction": test_prediction[position],
                    "lower": lower[position],
                    "upper": upper[position],
                    "covered": bool(lower[position] <= actual[position] <= upper[position]),
                    "residual": actual[position] - test_prediction[position],
                }
            )
        model_file = f"models/{target}.joblib"
        joblib.dump(selected, output_dir / model_file)
        selected_models[target] = {
            "model_name": selected_name,
            "selection_metric": config["selection_metric"],
            "model_file": model_file,
        }
        mean_test = next(
            row
            for row in metric_rows
            if row["target"] == target
            and row["model"] == "mean"
            and row["split"] == "test"
        )
        test_evaluation[target] = {
            "selected_model": selected_name,
            **selected_test_metrics,
            "mean_baseline_mae": mean_test["mae"],
            "mean_baseline_rmse": mean_test["rmse"],
            "interval_nominal_coverage": 1.0 - alpha,
            "interval_observed_coverage": coverage,
            "interval_mean_width": float(np.mean(upper - lower)),
            "coverage_below_nominal": bool(coverage < 1.0 - alpha),
        }

    split_rows = []
    for split_name, indices in split.items():
        for row_index in indices:
            split_rows.append(
                {
                    "row_index": int(row_index),
                    config["id_column"]: frame[config["id_column"]].iloc[row_index],
                    "split": split_name,
                }
            )
    pd.DataFrame(metric_rows).to_csv(output_dir / "metrics.csv", index=False)
    pd.DataFrame(diagnostic_rows).to_csv(output_dir / "residual_diagnostics.csv", index=False)
    pd.DataFrame(test_rows).to_csv(output_dir / "test_predictions.csv", index=False)
    pd.DataFrame(split_rows).sort_values("row_index").to_csv(output_dir / "splits.csv", index=False)
    unsupported = {
        "status": "unsupported_by_available_data",
        "outcomes": config["unsupported_outcomes"],
        "reason": "The available fixture contains no labels for these outcomes; no model was trained.",
    }
    (output_dir / "unsupported_outcomes.json").write_text(json.dumps(unsupported, indent=2) + "\n")
    (output_dir / "config_snapshot.json").write_text(json.dumps(config, indent=2) + "\n")
    support = {
        feature: {
            "minimum": float(numeric[feature].iloc[split.train].min()),
            "maximum": float(numeric[feature].iloc[split.train].max()),
        }
        for feature in features
    }
    manifest = {
        "model_track_id": config["model_track_id"],
        "interface_version": config["interface_version"],
        "evidence_status": config["evidence_status"],
        "interpretation": "Synthetic response-model pipeline evidence only; predictions are not causal intervention estimates.",
        "data_path": str(data_path),
        "data_sha256": _sha256(data_path),
        "config_path": str(config_path),
        "config_sha256": _sha256(config_path),
        "feature_columns": features,
        "target_columns": targets,
        "feature_schema": [
            {
                "name": feature,
                "kind": "number",
                "missing_handling": "training-fold median imputation",
            }
            for feature in features
        ],
        "target_schema": [
            {
                "name": target,
                "kind": "number",
                "bounds": config["target_bounds"][target],
                "missing_allowed": False,
            }
            for target in targets
        ],
        "target_bounds": config["target_bounds"],
        "forbidden_feature_columns": config["forbidden_feature_columns"],
        "split": {
            **config["split"],
            "counts": {name: int(len(indices)) for name, indices in split.items()},
            "limitation": "One synthetic period and unique row identifiers prevent meaningful time-aware or repeated-group splitting.",
        },
        "selected_models": selected_models,
        "prediction_interval": config["prediction_interval"],
        "conformal_radii": conformal_radii,
        "test_evaluation": test_evaluation,
        "training_support": support,
        "model_training_seed": int(config["split"]["model_seed"]),
        "optimization_randomness": config["optimization_randomness"],
        "library_versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "artifacts": {
            "metrics": "metrics.csv",
            "residual_diagnostics": "residual_diagnostics.csv",
            "test_predictions": "test_predictions.csv",
            "splits": "splits.csv",
            "unsupported_outcomes": "unsupported_outcomes.json",
            "config_snapshot": "config_snapshot.json",
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/models/legacy_synthetic_response_v1.json")
    parser.add_argument("--output-dir", default="artifacts/models/legacy_synthetic_response_v1")
    return parser.parse_args()


def main():
    args = parse_args()
    manifest = train_from_config(Path(args.config), Path(args.output_dir))
    print(f"Trained {len(manifest['selected_models'])} synthetic KPI models")
    for target, details in manifest["selected_models"].items():
        print(f"{target}: {details['model_name']}")
    print(f"Evidence status: {manifest['evidence_status']}")
    print(f"Outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
