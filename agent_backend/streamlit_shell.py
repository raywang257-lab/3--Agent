from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="TrendScope 行业态势 Agent",
    page_icon=":material/radar:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.iframe("/~/+/dashboard/", width="stretch", height=1200, tab_index=0)
