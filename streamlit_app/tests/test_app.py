from __future__ import annotations

import unittest
from pathlib import Path


class AppSmokeTests(unittest.TestCase):
    def test_streamlit_app_renders_without_exceptions(self) -> None:
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_path), default_timeout=15).run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any("Snapshot" in select.label for select in app.selectbox))


if __name__ == "__main__":
    unittest.main()
