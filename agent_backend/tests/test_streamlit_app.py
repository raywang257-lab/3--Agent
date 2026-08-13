from __future__ import annotations

import unittest
from pathlib import Path
from re import search

from starlette.testclient import TestClient
from streamlit.testing.v1 import AppTest


class StreamlitAppTests(unittest.TestCase):
    def test_asgi_root_serves_dashboard_and_agent_api(self) -> None:
        from streamlit_app import app

        with TestClient(app) as client:
            dashboard = client.get("/")
            health = client.get("/agent/health")

            asset_match = search(r'src="(\./assets/[^"]+\.js)"', dashboard.text)
            self.assertIsNotNone(asset_match)
            asset = client.get(asset_match.group(1).removeprefix("."))

        self.assertEqual(200, dashboard.status_code)
        self.assertIn("TrendScope 行业态势 Agent", dashboard.text)
        self.assertEqual(200, asset.status_code)
        self.assertIn("javascript", asset.headers["content-type"])
        self.assertEqual(200, health.status_code)
        self.assertEqual("ok", health.json()["status"])

    def test_dashboard_smoke_renders(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_native.py"
        app = AppTest.from_file(app_path)
        app.run(timeout=20)

        self.assertEqual([], list(app.exception))
        self.assertEqual("TrendScope 热点发现 Agent", app.title[0].value)
        self.assertTrue(any(button.label == "更新分析" for button in app.button))
        self.assertTrue(any(control.label == "选择行业" for control in app.segmented_control))


if __name__ == "__main__":
    unittest.main()
