from __future__ import annotations

import unittest

import pandas as pd

from streamlit_app.data.contracts import ArtifactContractError, parse_boolean, validate_dataframe
from streamlit_app.data.types import CatalogFile


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = CatalogFile(
            id="fixture",
            source_path="fixture.csv",
            format="csv",
            sha256="0" * 64,
            bytes=1,
            required_columns=("name", "value"),
            numeric_columns=("value",),
        )

    def test_missing_column_and_value_are_rejected(self) -> None:
        with self.assertRaisesRegex(ArtifactContractError, "required column"):
            validate_dataframe(self.definition, pd.DataFrame([{"name": "alpha"}]))
        with self.assertRaisesRegex(ArtifactContractError, "missing name value"):
            validate_dataframe(self.definition, pd.DataFrame([{"name": "", "value": "1"}]))

    def test_non_finite_value_is_rejected(self) -> None:
        for invalid in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ArtifactContractError, "non-finite value"):
                validate_dataframe(self.definition, pd.DataFrame([{"name": "alpha", "value": invalid}]))

    def test_explicit_booleans(self) -> None:
        self.assertTrue(parse_boolean("True"))
        self.assertFalse(parse_boolean("0"))
        with self.assertRaisesRegex(ArtifactContractError, "Expected a boolean"):
            parse_boolean("maybe")


if __name__ == "__main__":
    unittest.main()
