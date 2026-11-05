from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from streamlit_app.data.contracts import ArtifactContractError, resolve_allowlisted_path
from streamlit_app.data.loaders import load_artifact, load_catalog, load_snapshot


class LoaderTests(unittest.TestCase):
    def test_every_allowlisted_snapshot_validates(self) -> None:
        catalog = load_catalog()
        self.assertEqual(3, len(catalog.snapshots))
        for definition in catalog.snapshots:
            with self.subTest(snapshot=definition.id):
                loaded = load_snapshot(definition.id, catalog)
                self.assertEqual(len(definition.files), len(loaded.artifacts))

    def test_hash_mismatch_is_rejected(self) -> None:
        definition = load_catalog().snapshots[0].files[0]
        with self.assertRaisesRegex(ArtifactContractError, "failed SHA-256"):
            load_artifact(replace(definition, sha256="0" * 64))

    def test_path_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ArtifactContractError, "escapes the repository"):
                resolve_allowlisted_path(Path(directory), "../outside.csv")


if __name__ == "__main__":
    unittest.main()
