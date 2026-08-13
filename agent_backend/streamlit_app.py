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


app = st.App(
    str(BACKEND_DIR / "streamlit_native.py"),
    routes=[
        Route("/", dashboard_index),
        Mount("/assets", app=StaticFiles(directory=STATIC_DIR / "assets")),
        Mount("/agent", app=agent_api),
    ],
)
