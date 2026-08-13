from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="TrendScope 行业态势 Agent",
    page_icon=":material/radar:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.html(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        margin: 0 !important;
        padding: 0 !important;
        background: #f4f7fb !important;
      }
      header[data-testid="stHeader"], [data-testid="stToolbar"] {
        display: none !important;
      }
      [data-testid="stMainBlockContainer"] {
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
      }
      [data-testid="stElementContainer"], [data-testid="stIframe"] {
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        border: 0 !important;
      }
      [data-testid="stIframe"] iframe {
        display: block !important;
        width: 100% !important;
        border: 0 !important;
      }
    </style>
    """
)

st.iframe("/~/+/dashboard/", width="stretch", height=1200, tab_index=0)
