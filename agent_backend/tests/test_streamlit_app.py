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
        self.assertTrue(any(status.label == "完整数据、报告与执行诊断" for status in app.get("status")))
        self.assertTrue(any(button.label == "生成报告" for button in app.button))
        self.assertEqual(["事件数据", "分析报告", "执行诊断"], [tab.label for tab in app.tabs])


if __name__ == "__main__":
    unittest.main()
