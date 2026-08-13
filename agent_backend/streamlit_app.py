from __future__ import annotations

from pathlib import Path

import streamlit as st
from starlette.responses import FileResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from trendscope.api import app as agent_api


BACKEND_DIR = Path(__file__).resolve().parent
STATIC_DIR = BACKEND_DIR / "static_dashboard"
INDEX_FILE = STATIC_DIR / "index.html"


async def dashboard_index(request):
    return FileResponse(INDEX_FILE)


def dashboard_routes(base_path: str = ""):
    prefix = f"/{base_path.strip('/')}" if base_path.strip("/") else ""
    return [
        Route(f"{prefix}/", dashboard_index),
        Mount(f"{prefix}/assets", app=StaticFiles(directory=STATIC_DIR / "assets")),
        Mount(f"{prefix}/agent", app=agent_api),
    ]


configured_base_path = str(st.get_option("server.baseUrlPath") or "")
routes = dashboard_routes(configured_base_path)
if configured_base_path:
    routes.extend(dashboard_routes())
if configured_base_path.strip("/") != "~/+":
    routes.extend(dashboard_routes("~/+"))

app = st.App(
    str(BACKEND_DIR / "streamlit_native.py"),
    routes=routes,
)
