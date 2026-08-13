from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class StreamlitAppTests(unittest.TestCase):
    def test_dashboard_smoke_renders(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        app = AppTest.from_file(app_path)
        app.run(timeout=20)

        self.assertEqual([], list(app.exception))
        self.assertEqual("TrendScope 热点发现 Agent", app.title[0].value)
        self.assertTrue(any(button.label == "更新分析" for button in app.button))
        self.assertTrue(any(control.label == "选择行业" for control in app.segmented_control))


if __name__ == "__main__":
    unittest.main()
