"""Stable prediction interface for persisted response-model bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .core import ModelingDataError, bounded_interval


@dataclass
class PredictionBundle:
    root: Path
    manifest: dict
    models: dict

    @property
    def interface_version(self):
        return self.manifest["interface_version"]

    def predict(self, records) -> pd.DataFrame:
        frame = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
        features = self.manifest["feature_columns"]
        missing = sorted(set(features).difference(frame.columns))
        if missing:
            raise ModelingDataError(f"prediction records are missing features: {missing}")
        numeric = frame[features].apply(pd.to_numeric, errors="coerce")
        if np.isinf(numeric.to_numpy(dtype=float)).any():
            raise ModelingDataError("prediction features must not contain infinite values")

        support = self.manifest["training_support"]
        outside_by_row = []
        for _, row in numeric.iterrows():
            bad = []
            for feature in features:
                value = row[feature]
                limits = support[feature]
                if pd.isna(value) or value < limits["minimum"] or value > limits["maximum"]:
                    bad.append(feature)
            outside_by_row.append(bad)

        result = pd.DataFrame(index=frame.index)
        result["out_of_support"] = [bool(items) for items in outside_by_row]
        result["out_of_support_features"] = [",".join(items) for items in outside_by_row]
        for target in self.manifest["target_columns"]:
            model = self.models[target]
            predicted = np.asarray(model.predict(numeric), dtype=float)
            bounds = self.manifest["target_bounds"][target]
            if bounds[0] is not None:
                predicted = np.maximum(predicted, bounds[0])
            if bounds[1] is not None:
                predicted = np.minimum(predicted, bounds[1])
            lower, upper = bounded_interval(
                predicted, self.manifest["conformal_radii"][target], bounds
            )
            result[f"prediction__{target}"] = predicted
            result[f"lower__{target}"] = lower
            result[f"upper__{target}"] = upper
        return result


def load_prediction_bundle(path: str | Path) -> PredictionBundle:
    root = Path(path)
    manifest = json.loads((root / "manifest.json").read_text())
    models = {
        target: joblib.load(root / details["model_file"])
        for target, details in manifest["selected_models"].items()
    }
    return PredictionBundle(root=root, manifest=manifest, models=models)
