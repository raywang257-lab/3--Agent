from __future__ import annotations

import asyncio
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st


st.set_page_config(
    page_title="TrendScope 热点决策台",
    page_icon=":material/radar:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _apply_streamlit_secrets() -> None:
    try:
        values = dict(st.secrets)
    except FileNotFoundError:
        values = {}
    for key, value in values.items():
        if isinstance(value, (str, int, float, bool)):
            os.environ.setdefault(str(key), str(value))


_apply_streamlit_secrets()

from trendscope.config import settings  # noqa: E402
from trendscope.dashboard_component import dashboard  # noqa: E402
from trendscope.database import Database  # noqa: E402
from trendscope.report_skill import AnalysisReportSkill  # noqa: E402
from trendscope.runner import TrendAgentRunner  # noqa: E402


TASK_ID = 1
SOURCE_LABELS = {
    "github": ("GitHub", "GH"),
    "hacker_news": ("Hacker News", "HN"),
    "rss": ("RSS", "RSS"),
    "google_news": ("Google News", "GN"),
    "google_trends": ("Google Trends", "GT"),
    "arxiv": ("arXiv", "AX"),
    "devto": ("DEV", "DEV"),
    "v2ex": ("V2EX", "V2"),
    "bilibili": ("Bilibili", "B"),
    "chinanews": ("中新网", "中"),
    "cctv_news": ("央视新闻", "央"),
}


@st.cache_resource
def get_services() -> tuple[Database, TrendAgentRunner, AnalysisReportSkill]:
    database = Database(settings.database_path)
    database.initialize()
    database.recover_interrupted_runs()
    return database, TrendAgentRunner(database, settings), AnalysisReportSkill(database, settings)


@st.cache_resource
def get_run_lock() -> threading.Lock:
    return threading.Lock()


def run_agent(task_id: int = TASK_ID) -> str:
    _, runner, _ = get_services()
    lock = get_run_lock()
    if not lock.acquire(blocking=False):
        raise RuntimeError("已有用户正在运行热点采集，请稍后再试")
    try:
        return asyncio.run(runner.run(task_id))
    finally:
        lock.release()


def _time_label(value: Any) -> str:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return text[11:16] if len(text) >= 16 else "--:--"


def _tone(event: dict[str, Any]) -> str:
    if event.get("action_level") == "立即跟进" or event.get("value_level") == "high_value":
        return "urgent"
    if event.get("action_level") == "持续观察" or event.get("value_level") == "watchlist":
        return "watch"
    return "risk"


def _breakdown(event: dict[str, Any]) -> dict[str, int]:
    raw = event.get("score_breakdown") or {}

    def contribution(name: str, fallback: int) -> int:
        value = raw.get(name) or {}
        number = value.get("contribution") if isinstance(value, dict) else value
        try:
            return max(0, min(100, round(float(number))))
        except (TypeError, ValueError):
            return fallback

    return {
        "relevance": contribution("relevance", 35),
        "crossPlatform": contribution("cross_platform", 25),
        "sourceStrength": contribution("source_strength", 20),
        "growth": contribution("growth", 20),
    }


def _evidence_rows(event: dict[str, Any]) -> list[dict[str, str]]:
    claims = event.get("claims") or []
    verified = next((c for c in claims if c.get("status") == "verified"), None)
    uncertain = next((c for c in claims if c.get("status") == "insufficient_evidence"), None)
    return [
        {
            "label": "支持证据",
            "text": (verified or {}).get("text") or event.get("why_now") or "来源标题与时间可回溯",
        },
        {
            "label": "反方证据",
            "text": (uncertain or {}).get("text") or event.get("debate") or "尚缺少跨平台独立验证",
        },
        {
            "label": "风险提示",
            "text": event.get("risk") or "单一来源不能独立证明热点成立",
        },
    ]


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for source in event.get("sources") or []:
        label, short = SOURCE_LABELS.get(
            str(source.get("source") or ""),
            (str(source.get("source") or "未知来源"), "源"),
        )
        sources.append(
            {
                "name": label,
                "short": short,
                "time": _time_label(source.get("published_at")),
                "url": source.get("url") or "",
            }
        )
    growth = event.get("growth_percent")
    growth_label = f"{float(growth):+.0f}%" if growth is not None else event.get("growth_label") or "无基线"
    action = event.get("action_level") or event.get("current_action") or "谨慎验证"
    title = event.get("canonical_title") or "未命名事件"
    return {
        "id": int(event.get("id") or 0),
        "title": title,
        "shortTitle": title[:18],
        "action": action,
        "tone": _tone(event),
        "score": f"{float(event.get('value_score') or 0):.1f}",
        "growth": growth_label,
        "platforms": f"{int(event.get('platform_count') or 0)}/6 平台",
        "sourceCount": int(event.get("source_count") or len(sources)),
        "why": event.get("why_now") or event.get("summary") or "等待更多证据",
        "advice": event.get("recommended_action") or event.get("current_action") or "继续补证",
        "debate": event.get("debate") or "暂无明确争议信息",
        "risk": event.get("risk") or "来源独立性需继续核验",
        "impact": event.get("impact") or "AI 开发者工具与产品团队",
        "truth": event.get("truth_status") or "信息不足",
        "cluster": event.get("cluster_confidence") or "不适用",
        "priority": event.get("decision_priority") or "待评估",
        "sources": sources,
        "evidence": _evidence_rows(event),
        "breakdown": _breakdown(event),
    }


def demo_events() -> list[dict[str, Any]]:
    common_breakdown = {"relevance": 35, "crossPlatform": 25, "sourceStrength": 20, "growth": 20}
    return [
        {
            "id": 1,
            "title": "Cursor 发布新版本，跨平台讨论 4 小时增长 280%",
            "shortTitle": "Cursor 新版本",
            "action": "立即跟进",
            "tone": "urgent",
            "score": "92.0",
            "growth": "+216%",
            "platforms": "4/6 平台",
            "sourceCount": 3,
            "why": "官方发布与开发者实测集中出现",
            "advice": "今日发布竞品快讯，并安排功能拆解",
            "debate": "能力提升明显，但成本与代码隐私仍有争议",
            "risk": "部分传播来自二次转载",
            "impact": "AI IDE、开发者工具、模型厂商",
            "truth": "较高",
            "cluster": "中等",
            "priority": "高",
            "sources": [
                {"name": "官方博客", "short": "官", "time": "08:20", "url": "#"},
                {"name": "GitHub", "short": "GH", "time": "10:40", "url": "#"},
                {"name": "Hacker News", "short": "HN", "time": "12:10", "url": "#"},
                {"name": "Reddit", "short": "R", "time": "13:30", "url": "#"},
            ],
            "evidence": [
                {"label": "支持证据", "text": "官方 Release 可验证功能变化"},
                {"label": "反方证据", "text": "暂无独立性能评测"},
                {"label": "风险提示", "text": "Reddit 内容存在重复转载"},
            ],
            "breakdown": common_breakdown,
        },
        {
            "id": 2,
            "title": "GitHub Copilot 企业安全功能升温",
            "shortTitle": "Copilot 安全功能",
            "action": "持续观察",
            "tone": "watch",
            "score": "78.0",
            "growth": "+88%",
            "platforms": "3/6 平台",
            "sourceCount": 3,
            "why": "企业客户集中讨论合规与数据边界",
            "advice": "追踪企业版实际部署反馈，48 小时后复评",
            "debate": "安全控制增强，但配置复杂度可能上升",
            "risk": "当前讨论集中在少数技术社区",
            "impact": "企业研发团队、安全与合规负责人",
            "truth": "较高",
            "cluster": "较高",
            "priority": "中高",
            "sources": [{"name": "GitHub", "short": "GH", "time": "09:10", "url": "#"}, {"name": "Hacker News", "short": "HN", "time": "11:25", "url": "#"}, {"name": "技术 RSS", "short": "RSS", "time": "14:10", "url": "#"}],
            "evidence": [{"label": "支持证据", "text": "官方文档列出新的策略控制项"}, {"label": "反方证据", "text": "尚无大规模企业落地案例"}, {"label": "风险提示", "text": "媒体报道多引用同一官方材料"}],
            "breakdown": common_breakdown,
        },
        {
            "id": 3,
            "title": "Continue 融资消息扩散，但独立信源不足",
            "shortTitle": "Continue 融资",
            "action": "谨慎验证",
            "tone": "risk",
            "score": "61.0",
            "growth": "+47%",
            "platforms": "2/6 平台",
            "sourceCount": 2,
            "why": "融资数字被多个聚合账号短时间转载",
            "advice": "暂不对外引用，等待公司或投资方确认",
            "debate": "商业关注上升，但关键金额缺少官方确认",
            "risk": "疑似同源转载形成虚假跨平台热度",
            "impact": "投资研究、开发者工具赛道观察者",
            "truth": "信息不足",
            "cluster": "较低",
            "priority": "中等",
            "sources": [{"name": "行业媒体", "short": "媒", "time": "10:05", "url": "#"}, {"name": "Reddit", "short": "R", "time": "12:40", "url": "#"}],
            "evidence": [{"label": "支持证据", "text": "多个账号出现相同融资描述"}, {"label": "反方证据", "text": "公司与投资方均未发布公告"}, {"label": "风险提示", "text": "高度疑似单一稿源重复传播"}],
            "breakdown": common_breakdown,
        },
    ]


def build_dashboard_data(
    summary: dict[str, Any] | None,
    events: list[dict[str, Any]],
    reasons: dict[str, Any] | None,
    notice: str = "",
) -> dict[str, Any]:
    summary = summary or {}
    reasons = reasons or {}
    is_demo = not summary
    normalized = demo_events() if is_demo else [normalize_event(event) for event in events]
    urgent = sum(event["tone"] == "urgent" for event in normalized)
    watch = sum(event["tone"] == "watch" for event in normalized)
    risk = sum(event["tone"] == "risk" for event in normalized)
    source_count = len(summary.get("sources") or [])
    warning_count = len(summary.get("warnings") or [])
    lead = normalized[0] if normalized else None
    headline = (
        "今天有 3 个热点值得立即关注，2 个正在快速升温，1 个疑似虚假热度。"
        if is_demo
        else f"今天有 {urgent} 个热点值得立即关注，{watch} 个正在持续升温，{risk} 个需谨慎验证。"
    )
    subline = (
        "Cursor 新版本在 4 小时内跨平台扩散，建议产品与内容团队立即跟进。"
        if is_demo
        else f"{lead['shortTitle']}当前排名最高，建议产品与内容团队按证据等级跟进。"
        if lead
        else "当前没有事件达到热点门槛，请点击更新分析。"
    )
    completed_at = summary.get("completed_at") or summary.get("started_at")
    updated_at = str(completed_at or "等待首次分析").replace("T", " ")[:16]
    return {
        "industry": "AI 编程工具",
        "demo": is_demo,
        "totalEvents": 6 if is_demo else len(normalized),
        "summary": {"updatedAt": "2026-08-12 10:30" if is_demo else updated_at},
        "counts": {
            "headline": headline,
            "subline": subline,
            "urgent": 3 if is_demo else urgent,
            "watch": 2 if is_demo else watch,
            "risk": 1 if is_demo else risk,
        },
        "funnel": {
            "raw": 126 if is_demo else int(summary.get("items_collected") or 0),
            "duplicates": 56 if is_demo else int(reasons.get("duplicates") or 0),
            "related": 42 if is_demo else int(summary.get("related_items") or 0),
            "filtered": 19 if is_demo else int(reasons.get("relevance_filtered") or 0),
            "events": 18 if is_demo else int(summary.get("candidate_events") or len(events)),
            "candidates": 9 if is_demo else int(summary.get("low_confidence_candidates") or 0),
            "high": 6 if is_demo else int(summary.get("high_value_hotspots") or 0),
            "sources": 6 if is_demo else source_count,
            "warnings": 1 if is_demo else warning_count,
        },
        "events": normalized,
        "notice": notice,
    }


def _on_update() -> None:
    try:
        run_id = run_agent(TASK_ID)
        st.session_state.dashboard_notice = f"分析已更新，运行 ID：{run_id[:8]}"
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        st.session_state.dashboard_notice = f"更新失败：{type(exc).__name__}：{exc}"


db, _, report_skill = get_services()
summary = db.latest_run_summary(TASK_ID)
events = db.list_latest_events(limit=12, task_id=TASK_ID)
reasons = db.filtering_reasons(TASK_ID)

st.html(
    """
    <style>
    header[data-testid="stHeader"], [data-testid="stSidebar"], footer {display:none !important;}
    .stApp {background:#f7f9fc;}
    .block-container {padding:0 !important; max-width:none !important;}
    [data-testid="stCustomComponentV2"] {margin:0 !important;}
    </style>
    """
)

dashboard_data = build_dashboard_data(
    summary,
    events,
    reasons,
    st.session_state.get("dashboard_notice", ""),
)
dashboard(dashboard_data, on_update_change=_on_update)

with st.expander("完整数据、报告与执行诊断", icon=":material/database:"):
    data_tab, report_tab, diagnostics_tab = st.tabs(["事件数据", "分析报告", "执行诊断"])
    with data_tab:
        if not events:
            st.info("本轮没有通过事件门槛的候选。")
        else:
            st.dataframe(
                [
                    {
                        "事件": event.get("canonical_title"),
                        "价值分": event.get("value_score"),
                        "行动": event.get("action_level") or event.get("current_action"),
                        "来源数": event.get("source_count"),
                        "平台数": event.get("platform_count"),
                        "事实状态": event.get("truth_status"),
                    }
                    for event in events
                ],
                hide_index=True,
            )
    with report_tab:
        report_type = st.segmented_control(
            "报告类型",
            ["full_analysis", "decision_brief"],
            default="full_analysis",
            format_func={"full_analysis": "完整分析", "decision_brief": "决策简报"}.get,
        )
        if st.button("生成报告", icon=":material/description:"):
            report = report_skill.generate(TASK_ID, report_type or "full_analysis", "qualified", 10)
            st.session_state.report_markdown = report.markdown
            st.session_state.report_name = report.path.name
        if st.session_state.get("report_markdown"):
            st.download_button(
                "下载 Markdown 报告",
                st.session_state.report_markdown,
                file_name=st.session_state.get("report_name", "trendscope-report.md"),
                mime="text/markdown",
                icon=":material/download:",
            )
    with diagnostics_tab:
        diagnostics = db.scoring_diagnostics(TASK_ID)
        if reasons:
            st.json(reasons)
        if diagnostics:
            for assessment in diagnostics.get("assessment") or []:
                st.write(f"- {assessment}")
