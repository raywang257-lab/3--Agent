from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from starlette.responses import FileResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles


EMAIL_SECRET_KEYS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_USE_TLS",
    "SMTP_USE_SSL",
    "EMAIL_FROM",
    "EMAIL_RECIPIENTS",
)


def apply_streamlit_email_secrets() -> None:
    """Expose encrypted Streamlit email secrets before Settings is created."""
    try:
        for key in EMAIL_SECRET_KEYS:
            if key in st.secrets:
                os.environ[key] = str(st.secrets[key])
    except FileNotFoundError:
        # Local/PyCharm runs continue to use agent_backend/.env.
        return


apply_streamlit_email_secrets()

from trendscope.api import app as agent_api, lifespan as agent_lifespan


BACKEND_DIR = Path(__file__).resolve().parent
STATIC_DIR = BACKEND_DIR / "static_dashboard"
INDEX_FILE = STATIC_DIR / "index.html"


async def dashboard_index(request):
    return FileResponse(INDEX_FILE)


def dashboard_routes(base_path: str = ""):
    prefix = f"/{base_path.strip('/')}" if base_path.strip("/") else ""
    return [
        Route(f"{prefix}/dashboard/", dashboard_index),
        Mount(f"{prefix}/dashboard/assets", app=StaticFiles(directory=STATIC_DIR / "assets")),
        Mount(f"{prefix}/dashboard/agent", app=agent_api),
    ]


configured_base_path = str(st.get_option("server.baseUrlPath") or "")
routes = dashboard_routes(configured_base_path)
if configured_base_path:
    routes.extend(dashboard_routes())
if configured_base_path.strip("/") != "~/+":
    routes.extend(dashboard_routes("~/+"))

app = st.App(
    str(BACKEND_DIR / "streamlit_shell.py"),
    routes=routes,
    lifespan=agent_lifespan,
)
