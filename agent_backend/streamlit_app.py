from __future__ import annotations

import asyncio
import os
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="TrendScope 热点发现 Agent",
    page_icon=":material/radar:",
    layout="wide",
)


BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _apply_streamlit_secrets() -> None:
    """Expose scalar Streamlit secrets before importing settings."""
    try:
        values = dict(st.secrets)
    except FileNotFoundError:
        values = {}
    for key, value in values.items():
        if isinstance(value, (str, int, float, bool)):
            os.environ.setdefault(str(key), str(value))


_apply_streamlit_secrets()

from trendscope.config import settings  # noqa: E402
from trendscope.database import Database  # noqa: E402
from trendscope.report_skill import AnalysisReportSkill  # noqa: E402
from trendscope.runner import TrendAgentRunner  # noqa: E402


INDUSTRIES = {
    "人工智能": 5,
    "科技": 2,
    "金融": 3,
    "生物科技": 4,
}

TAG_TAXONOMY: dict[int, list[tuple[str, tuple[str, ...]]]] = {
    5: [
        ("智能体 / Agent", ("agent", "智能体", "agentic")),
        ("大模型与推理", ("llm", "language model", "大模型", "reasoning", "推理")),
        ("多模态", ("multimodal", "多模态", "vision", "语音")),
        ("AI 基础设施", ("gpu", "inference", "推理服务", "算力", "模型部署")),
        ("AI 安全与治理", ("safety", "governance", "alignment", "安全", "治理")),
    ],
    2: [
        ("具身智能与机器人", ("robot", "robotics", "机器人", "具身")),
        ("芯片与半导体", ("chip", "semiconductor", "芯片", "半导体")),
        ("量子计算", ("quantum", "量子")),
        ("网络安全", ("cybersecurity", "security", "网络安全", "漏洞")),
        ("云计算与开发者工具", ("cloud", "developer", "open source", "云计算", "开发者", "开源")),
    ],
    3: [
        ("支付与数字银行", ("payment", "digital bank", "支付", "数字银行")),
        ("市场与资产管理", ("market", "investment", "证券", "投资", "资产管理")),
        ("数字资产与稳定币", ("blockchain", "stablecoin", "crypto", "区块链", "稳定币")),
        ("货币政策与利率", ("interest rate", "inflation", "federal reserve", "利率", "通胀", "央行")),
        ("监管、风控与反欺诈", ("regulation", "fraud", "risk", "监管", "欺诈", "风控")),
    ],
    4: [
        ("AI 药物发现", ("drug discovery", "ai drug", "药物发现", "药物设计")),
        ("基因组与 CRISPR", ("genomics", "crispr", "gene", "基因组", "基因编辑")),
        ("蛋白质设计", ("protein", "蛋白质")),
        ("细胞与免疫治疗", ("cell therapy", "immunology", "细胞治疗", "免疫")),
        ("临床试验与监管", ("clinical trial", "fda", "临床试验", "监管")),
    ],
}

LEVEL_LABELS = {
    "high_value": "高价值热点",
    "watchlist": "持续观察",
    "candidate": "候选线索",
}


@st.cache_resource
def get_services() -> tuple[Database, TrendAgentRunner, AnalysisReportSkill]:
    database = Database(settings.database_path)
    database.initialize()
    database.recover_interrupted_runs()
    return (
        database,
        TrendAgentRunner(database, settings),
        AnalysisReportSkill(database, settings),
    )


@st.cache_resource
def get_run_lock() -> threading.Lock:
    return threading.Lock()


def classify_tag(event: dict[str, Any], task_id: int) -> str:
    searchable = " ".join(
        str(event.get(field) or "")
        for field in ("canonical_title", "category", "summary", "why_now")
    ).lower()
    for label, keywords in TAG_TAXONOMY[task_id]:
        if any(keyword.lower() in searchable for keyword in keywords):
            return label
    return f"待细分{INDUSTRY_SHORT[task_id]}事件"


INDUSTRY_SHORT = {5: "AI", 2: "科技", 3: "金融", 4: "生物科技"}


def tag_share_frame(events: list[dict[str, Any]], task_id: int) -> pd.DataFrame:
    counts = Counter(classify_tag(event, task_id) for event in events)
    total = max(1, sum(counts.values()))
    ordered = [label for label, _ in TAG_TAXONOMY[task_id]] + [f"待细分{INDUSTRY_SHORT[task_id]}事件"]
    return pd.DataFrame(
        [
            {"态势标签": label, "事件数": counts[label], "占比": round(counts[label] * 100 / total, 1)}
            for label in ordered
            if counts[label]
        ]
    )


def run_agent(task_id: int) -> str:
    _, runner, _ = get_services()
    lock = get_run_lock()
    if not lock.acquire(blocking=False):
        raise RuntimeError("已有用户正在运行热点采集，请稍后再试")
    try:
        return asyncio.run(runner.run(task_id))
    finally:
        lock.release()


def render_event(event: dict[str, Any], task_id: int) -> None:
    db, _, _ = get_services()
    level = LEVEL_LABELS.get(event.get("value_level"), "候选线索")
    title = event.get("canonical_title") or "未命名事件"
    with st.expander(f"{level} · {float(event.get('value_score') or 0):.1f} 分｜{title}"):
        badges = {
            "高价值热点": ":red-badge[高价值热点]",
            "持续观察": ":orange-badge[持续观察]",
            "候选线索": ":blue-badge[候选线索]",
        }
        st.markdown(
            f"{badges[level]} :gray-badge[{event.get('event_state', '状态未知')}] "
            f":gray-badge[{classify_tag(event, task_id)}]"
        )
        metrics = st.columns(4)
        metrics[0].metric("价值分", f"{float(event.get('value_score') or 0):.1f}")
        metrics[1].metric("独立来源", int(event.get("source_count") or 0))
        metrics[2].metric("平台", int(event.get("platform_count") or 0))
        metrics[3].metric("增长", event.get("growth_label") or "无增长基线")

        st.write(event.get("summary") or "暂无摘要。")
        st.caption(
            f"事实状态：{event.get('truth_status', '信息不足')}｜"
            f"业务优先级：{event.get('decision_priority', '不进入决策')}｜"
            f"当前动作：{event.get('current_action', '补证')}"
        )

        sources = event.get("sources") or []
        if sources:
            source_rows = [
                {
                    "来源": source.get("source"),
                    "标题": source.get("title"),
                    "发布时间": source.get("published_at"),
                    "原文": source.get("url"),
                    "证据角色": source.get("evidence_role"),
                }
                for source in sources
            ]
            st.dataframe(
                source_rows,
                hide_index=True,
                column_config={"原文": st.column_config.LinkColumn("原文")},
            )
        else:
            st.warning("该事件没有可回溯来源，不能进入正式报告。", icon=":material/warning:")

        claims = event.get("claims") or []
        if claims:
            st.markdown("**主张与证据状态**")
            st.dataframe(
                [
                    {
                        "状态": claim.get("status"),
                        "主张": claim.get("text"),
                        "来源引用": ", ".join(claim.get("evidence_source_refs") or []),
                    }
                    for claim in claims
                ],
                hide_index=True,
            )

        with st.form(f"review-{event['id']}", border=False):
            review_status = st.selectbox(
                "人工审核",
                options=["pending", "approved", "rejected"],
                index=["pending", "approved", "rejected"].index(event.get("review", {}).get("status", "pending")),
                format_func={"pending": "待确认", "approved": "确认通过", "rejected": "驳回"}.get,
                key=f"review-status-{event['id']}",
            )
            review_note = st.text_input(
                "审核理由",
                value=event.get("review", {}).get("note") or "",
                key=f"review-note-{event['id']}",
                max_chars=500,
            )
            if st.form_submit_button("保存审核", icon=":material/save:"):
                db.review_event(int(event["id"]), review_status, review_note)
                st.toast("审核结果已保存")
                st.rerun()


db, _, report_skill = get_services()

st.session_state.setdefault("last_run_id", None)
st.session_state.setdefault("report_markdown", "")
st.session_state.setdefault("report_name", "trendscope-report.md")

with st.sidebar:
    st.markdown("### :material/radar: TrendScope")
    st.caption("真实来源 → 清洗去重 → 事件聚类 → 价值判断 → 人工确认")
    st.markdown(f"**分析模式**：`{settings.effective_ai_mode}`")
    st.markdown("**数据存储**：本地 SQLite（云端重启后会重置）")
    st.markdown("**自动调度**：云端页面进程内不启用")
    if settings.effective_ai_mode == "rules":
        st.info("当前使用规则分析。配置 OPENAI_API_KEY 后可启用 AI 文字总结。", icon=":material/info:")

st.title("TrendScope 热点发现 Agent")
st.caption("自动发现公开来源中的行业信号，并把事实、趋势和业务动作拆开判断。")

industry_name = st.segmented_control(
    "选择行业",
    options=list(INDUSTRIES),
    default="人工智能",
    required=True,
    key="industry",
)
task_id = INDUSTRIES[str(industry_name)]

header_actions = st.columns([1, 3], vertical_alignment="center")
if header_actions[0].button("更新分析", type="primary", icon=":material/refresh:"):
    try:
        with st.status("Agent 正在采集和分析公开信息…", expanded=True) as status:
            status.write("连接 GitHub、Hacker News、新闻、RSS、arXiv 与行业来源")
            run_id = run_agent(task_id)
            status.write("完成清洗、相关性过滤、聚类、价值分层与证据入库")
            logs = db.list_run_logs(run_id)
            for log in logs[-10:]:
                status.write(log.get("message", ""))
            status.update(label="分析完成", state="complete", expanded=False)
        st.session_state.last_run_id = run_id
    except Exception as exc:
        st.error(f"运行失败：{type(exc).__name__}：{exc}", icon=":material/error:")

summary = db.latest_run_summary(task_id)
events = db.list_latest_events(limit=30, task_id=task_id)

if not summary:
    st.info("该行业还没有分析记录。点击“更新分析”运行第一轮真实采集。", icon=":material/play_arrow:")
    st.stop()

st.caption(f"最近运行：{summary.get('completed_at') or summary.get('started_at')}｜运行 ID：{summary.get('id')}")

with st.container(horizontal=True):
    st.metric("采集信息", int(summary.get("items_collected") or 0), border=True, icon=":material/database:")
    st.metric("形成事件", int(summary.get("candidate_events") or 0), border=True, icon=":material/hub:")
    st.metric("高价值", int(summary.get("high_value_hotspots") or 0), border=True, icon=":material/local_fire_department:")
    st.metric("持续观察", int(summary.get("watchlist_events") or 0), border=True, icon=":material/visibility:")

overview_tab, events_tab, report_tab, diagnostics_tab = st.tabs(
    ["行业态势", "事件与证据", "分析报告", "执行诊断"]
)

with overview_tab:
    left, right = st.columns([1.15, 0.85])
    with left.container(border=True):
        st.subheader("态势标签占比")
        st.caption("每个事件只计入一个最匹配的行业标签；待细分事件明确列出，不使用含糊的“其他”。")
        share = tag_share_frame(events, task_id)
        if share.empty:
            st.info("本轮没有可计算标签的事件。")
        else:
            st.bar_chart(share, x="态势标签", y="占比", horizontal=True)
            st.dataframe(
                share,
                hide_index=True,
                column_config={"占比": st.column_config.ProgressColumn("占比", min_value=0, max_value=100, format="%.1f%%")},
            )
    with right.container(border=True):
        st.subheader("本轮判断")
        high = int(summary.get("high_value_hotspots") or 0)
        watch = int(summary.get("watchlist_events") or 0)
        if high:
            st.error(f"发现 {high} 个高价值事件，需要立即核查来源并指定负责人。", icon=":material/priority_high:")
        elif watch:
            st.warning(f"没有高价值热点；有 {watch} 个事件进入持续观察。", icon=":material/visibility:")
        else:
            st.info("本轮没有事件达到热点或持续观察阈值，只保留候选线索。", icon=":material/info:")
        coverage = summary.get("evidence_coverage") or {}
        st.metric("跨平台事件", int(coverage.get("cross_platform") or 0))
        st.metric("有增长快照", int(coverage.get("with_growth_snapshots") or 0))
        st.metric("单一来源事件", int(coverage.get("single_source") or 0))

with events_tab:
    if not events:
        st.info("本轮没有通过事件门槛的候选。")
    for event in events:
        render_event(event, task_id)

with report_tab:
    st.subheader("生成可审计报告")
    report_type = st.segmented_control(
        "报告类型",
        options=["full_analysis", "decision_brief"],
        default="full_analysis",
        format_func={"full_analysis": "完整分析", "decision_brief": "决策简报"}.get,
        key="report-type",
    )
    report_scope = st.selectbox(
        "报告范围",
        options=["qualified", "all_visible", "approved_only"],
        format_func={"qualified": "合格事件优先", "all_visible": "全部可见事件", "approved_only": "仅人工确认"}.get,
        key="report-scope",
    )
    if st.button("生成报告", icon=":material/description:"):
        try:
            report = report_skill.generate(task_id, report_type or "full_analysis", report_scope, 10)
            st.session_state.report_markdown = report.markdown
            st.session_state.report_name = report.path.name
            st.success(f"已生成：{report.title}")
        except Exception as exc:
            st.error(f"报告生成失败：{exc}")
    if st.session_state.report_markdown:
        st.download_button(
            "下载 Markdown 报告",
            data=st.session_state.report_markdown,
            file_name=st.session_state.report_name,
            mime="text/markdown",
            icon=":material/download:",
        )
        with st.expander("查看报告正文", icon=":material/article:"):
            st.markdown(st.session_state.report_markdown)

with diagnostics_tab:
    reasons = db.filtering_reasons(task_id)
    diagnostics = db.scoring_diagnostics(task_id)
    if reasons:
        st.subheader("处理漏斗")
        st.dataframe(
            [
                {"阶段": "原始采集", "数量": reasons["raw"]},
                {"阶段": "无效信息", "数量": reasons["invalid"]},
                {"阶段": "排除词命中", "数量": reasons["excluded"]},
                {"阶段": "重复信息", "数量": reasons["duplicates"]},
                {"阶段": "相关性与事件门槛过滤", "数量": reasons["relevance_filtered"]},
                {"阶段": "聚类合并", "数量": reasons["cluster_merged"]},
            ],
            hide_index=True,
        )
    if diagnostics:
        st.subheader("评分诊断")
        for assessment in diagnostics.get("assessment") or []:
            st.write(f"- {assessment}")
    warnings = summary.get("warnings") or []
    if warnings:
        st.subheader("采集警告")
        for warning in warnings:
            st.warning(warning)
