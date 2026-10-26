import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from data.datagen import generate_legacy_synthetic
from department_optimizer.modeling.core import (
    ModelingDataError,
    conformal_radius,
    deterministic_split,
    validate_modeling_frame,
)
from department_optimizer.modeling.predict import load_prediction_bundle
from department_optimizer.modeling.train import train_from_config


REPO_ROOT = Path(__file__).resolve().parents[1]


def base_config(data_path):
    config = json.loads(
        (REPO_ROOT / "configs/models/legacy_synthetic_response_v1.json").read_text()
    )
    config["data_path"] = str(data_path)
    config["random_forest"]["n_estimators"] = 20
    return config


class ModelingUnitTests(unittest.TestCase):
    def test_split_is_complete_disjoint_and_reproducible(self):
        config = base_config("unused")["split"]
        first = deterministic_split(101, config)
        second = deterministic_split(101, config)
        combined = np.concatenate([indices for _, indices in first.items()])
        self.assertEqual(sorted(combined.tolist()), list(range(101)))
        self.assertEqual(len(set(combined.tolist())), 101)
        for (name_a, a), (name_b, b) in zip(first.items(), second.items()):
            self.assertEqual(name_a, name_b)
            np.testing.assert_array_equal(a, b)

    def test_leakage_and_small_samples_are_rejected(self):
        frame = generate_legacy_synthetic(25, seed=4, include_metadata=False)
        config = base_config("unused")
        config["feature_columns"].append("overall_rank")
        with self.assertRaisesRegex(ModelingDataError, "leakage|forbidden"):
            validate_modeling_frame(frame, config)
        with self.assertRaisesRegex(ModelingDataError, "at least 20"):
            deterministic_split(19, config["split"])

    def test_finite_sample_conformal_quantile(self):
        actual = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 10.0])
        predicted = np.zeros(6)
        self.assertEqual(conformal_radius(actual, predicted, 0.2), 10.0)


class ModelingIntegrationTests(unittest.TestCase):
    def test_train_persist_load_predict_and_flag_support(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "fixture.csv"
            generate_legacy_synthetic(120, seed=17, include_metadata=False).to_csv(
                data_path, index=False
            )
            config = base_config(data_path)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            output = root / "model"
            manifest = train_from_config(config_path, output)

            self.assertEqual(manifest["interface_version"], "1.0")
            self.assertEqual(set(manifest["selected_models"]), set(config["target_columns"]))
            self.assertNotIn("overall_rank", manifest["feature_columns"])
            self.assertEqual(sum(manifest["split"]["counts"].values()), 120)
            self.assertEqual(set(manifest["test_evaluation"]), set(config["target_columns"]))
            for name in (
                "manifest.json",
                "metrics.csv",
                "residual_diagnostics.csv",
                "test_predictions.csv",
                "splits.csv",
                "unsupported_outcomes.json",
                "config_snapshot.json",
            ):
                self.assertTrue((output / name).is_file(), name)

            metrics = pd.read_csv(output / "metrics.csv")
            for target in config["target_columns"]:
                validation = metrics[
                    (metrics["target"] == target) & (metrics["split"] == "validation")
                ]
                expected = validation.sort_values(["rmse", "mae", "model"]).iloc[0]["model"]
                self.assertEqual(manifest["selected_models"][target]["model_name"], expected)

            bundle = load_prediction_bundle(output)
            records = pd.read_csv(data_path).iloc[:2].copy()
            in_support = bundle.predict(records)
            self.assertFalse(in_support.iloc[0]["out_of_support"])
            for target in config["target_columns"]:
                self.assertTrue((in_support[f"lower__{target}"] <= in_support[f"prediction__{target}"]).all())
                self.assertTrue((in_support[f"prediction__{target}"] <= in_support[f"upper__{target}"]).all())

            records.loc[records.index[0], "research_budget"] = 1e15
            outside = bundle.predict(records)
            self.assertTrue(outside.iloc[0]["out_of_support"])
            self.assertIn("research_budget", outside.iloc[0]["out_of_support_features"])


if __name__ == "__main__":
    unittest.main()
