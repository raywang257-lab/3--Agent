from __future__ import annotations

import unittest
from pathlib import Path
from re import search

from starlette.testclient import TestClient
from streamlit.testing.v1 import AppTest


class StreamlitAppTests(unittest.TestCase):
    def test_asgi_serves_streamlit_shell_dashboard_and_agent_api(self) -> None:
        from streamlit_app import app, dashboard_routes

        with TestClient(app) as client:
            streamlit_shell = client.get("/")
            dashboard = client.get("/dashboard/")
            health = client.get("/dashboard/agent/health")
            tasks = client.get("/dashboard/agent/api/tasks")
            cloud_dashboard = client.get("/~/+/dashboard/")
            cloud_health = client.get("/~/+/dashboard/agent/health")
            cloud_tasks = client.get("/~/+/dashboard/agent/api/tasks")

            asset_match = search(r'src="(\./assets/[^"]+\.js)"', dashboard.text)
            self.assertIsNotNone(asset_match)
            asset = client.get(f"/dashboard/{asset_match.group(1).removeprefix('./')}")

        self.assertEqual(200, streamlit_shell.status_code)
        self.assertEqual(200, dashboard.status_code)
        self.assertIn("TrendScope 行业态势 Agent", dashboard.text)
        self.assertEqual(200, asset.status_code)
        self.assertIn("javascript", asset.headers["content-type"])
        self.assertEqual(200, health.status_code)
        self.assertEqual("ok", health.json()["status"])
        self.assertEqual(200, tasks.status_code)
        self.assertEqual(14 * 24, tasks.json()["items"][0]["time_window_hours"])
        self.assertIn("TrendScope 行业态势 Agent", cloud_dashboard.text)
        self.assertEqual("ok", cloud_health.json()["status"])
        self.assertEqual(200, cloud_tasks.status_code)
        self.assertEqual(14 * 24, cloud_tasks.json()["items"][0]["time_window_hours"])

        prefixed_paths = [route.path for route in dashboard_routes("cloud/base")]
        self.assertEqual(
            [
                "/cloud/base/dashboard/",
                "/cloud/base/dashboard/assets",
                "/cloud/base/dashboard/agent",
            ],
            prefixed_paths,
        )

    def test_streamlit_shell_renders_dashboard_iframe(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_shell.py"
        app = AppTest.from_file(app_path)
        app.run(timeout=20)

        self.assertEqual([], list(app.exception))


if __name__ == "__main__":
    unittest.main()
