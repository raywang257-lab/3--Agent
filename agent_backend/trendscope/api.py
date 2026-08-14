from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .database import Database
from .deep_analysis_skill import DeepAnalysisSkill
from .mailer import build_email_brief, mask_email, send_email
from .models import AskRequest, DeepAnalysisRequest, EmailSendRequest, HealthResponse, ReportGenerateRequest, ReviewRequest, RunRequest
from .report_skill import AnalysisReportSkill, REPORT_SKILL_ROOT
from .runner import TrendAgentRunner
from .benchmark import evaluate_scoring_calibration
from .evaluation import human_dataset_status
from .enrichment import enrich_candidate


logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

db = Database(settings.database_path)
runner = TrendAgentRunner(db, settings)
report_skill = AnalysisReportSkill(db, settings)
deep_analysis_skill = DeepAnalysisSkill(db, settings)
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

SOURCE_CATALOG = {
    "github": {"name": "GitHub", "kind": "一手项目源", "role": "验证仓库创建、更新及开发者关注信号", "homepage": "https://github.com", "primary_capable": True},
    "hacker_news": {"name": "Hacker News", "kind": "开发者社区", "role": "发现技术社区讨论与早期采用信号", "homepage": "https://news.ycombinator.com", "primary_capable": False},
    "rss": {"name": "官方与媒体 RSS", "kind": "订阅源", "role": "确认官方事实并发现行业新闻", "homepage": None, "primary_capable": True},
    "google_news": {"name": "Google News", "kind": "新闻发现源", "role": "聚合跨媒体报道；不等同于官方确认", "homepage": "https://news.google.com", "primary_capable": False},
    "google_trends": {"name": "Google Trends", "kind": "搜索关注信号", "role": "观察公开搜索关注，不证明事件真实性", "homepage": "https://trends.google.com", "primary_capable": False},
    "arxiv": {"name": "arXiv", "kind": "学术一手源", "role": "发现论文发布与早期研究信号", "homepage": "https://arxiv.org", "primary_capable": True},
    "devto": {"name": "DEV Community", "kind": "开发者社区", "role": "观察开发实践、采用与观点讨论", "homepage": "https://dev.to", "primary_capable": False},
    "v2ex": {"name": "V2EX", "kind": "中文技术社区", "role": "发现中文开发者的早期讨论信号", "homepage": "https://www.v2ex.com", "primary_capable": False},
    "bilibili": {"name": "Bilibili", "kind": "中文内容平台", "role": "观察视频传播和中文内容关注", "homepage": "https://www.bilibili.com", "primary_capable": False},
    "chinanews": {"name": "中国新闻网", "kind": "权威中文新闻源", "role": "通过中新网官方 RSS 发现并核验国内行业新闻", "homepage": "https://www.chinanews.com.cn", "primary_capable": True},
    "cctv_news": {"name": "央视新闻", "kind": "权威中文新闻源", "role": "通过央视网公开新闻列表发现并核验科技、经济与健康新闻", "homepage": "https://news.cctv.com", "primary_capable": True},
}


async def scheduled_job() -> None:
    for task in db.list_tasks():
        if task["enabled"]:
            await runner.run(int(task["id"]))


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    db.recover_interrupted_runs()
    if settings.schedule_enabled:
        scheduler.add_job(
            scheduled_job,
            "interval",
            minutes=settings.schedule_minutes,
            id="trendscope-scheduled-run",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="TrendScope Agent API",
    description="真实采集、清洗、聚类、分析、存储和定时执行的热点发现 Agent。",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ai_mode=settings.effective_ai_mode,
        database=str(settings.database_path),
        scheduler_enabled=settings.schedule_enabled,
        email_configured=settings.email_configured,
        email_recipient_count=len(settings.email_recipients),
    )


@app.get("/api/tasks")
async def tasks():
    return {"items": db.list_tasks()}


@app.get("/api/data-sources")
async def data_sources(task_id: int = Query(default=1, ge=1)):
    overview = db.data_source_overview(task_id)
    if not overview:
        raise HTTPException(status_code=404, detail="该任务还没有数据源运行记录")
    groups = overview.pop("groups")
    enabled_ids = [
        "github", "hacker_news", "google_news", "google_trends", "arxiv", "rss",
        "chinanews", "cctv_news",
    ]
    if task_id in {1, 2, 5}:
        enabled_ids.extend(["devto", "v2ex", "bilibili"])
    items = []
    for source_id in enabled_ids:
        records = groups.get(source_id, [])
        catalog = SOURCE_CATALOG[source_id]
        publisher_counts: dict[str, int] = {}
        for record in records:
            publisher = record.get("author") or record.get("hostname") or catalog["name"]
            publisher_counts[publisher] = publisher_counts.get(publisher, 0) + 1
        items.append({
            "id": source_id,
            **catalog,
            "status": "active" if records else "no_data",
            "collected_count": len(records),
            "primary_count": 0 if source_id == "google_trends" else sum(bool(record["is_primary_source"]) for record in records),
            "used_event_count": sum(int(record["used_by_events"] or 0) for record in records),
            "latest_published_at": records[0]["published_at"] if records else None,
            "time_label": {
                "github": "最近活跃", "google_trends": "快照时间", "arxiv": "论文提交",
                "hacker_news": "发帖时间", "devto": "发帖时间", "v2ex": "发帖时间",
                "bilibili": "视频发布时间",
            }.get(source_id, "发布时间"),
            "publishers": [
                {"name": name, "count": count}
                for name, count in sorted(publisher_counts.items(), key=lambda pair: pair[1], reverse=True)[:8]
            ],
            "samples": records[:5],
            "configured_feeds": overview["rss_feeds"] if source_id == "rss" else [],
        })
    return overview | {"items": items}


@app.get("/api/skills")
async def skills():
    return {"items": [{
        "id": "analysis_report",
        "name": "分析报告 Skill",
        "description": "基于真实入库热点、程序评分、审核状态和来源生成可审计报告。",
        "report_types": ["decision_brief", "full_analysis"],
        "scopes": ["qualified", "approved_only", "all_visible"],
        "ai_role": "只归纳报告文字，不改变程序评分、价值分层或来源。",
        "fallback": "LLM 不可用时自动生成规则报告。",
        "skill_file": str(REPORT_SKILL_ROOT / "SKILL.md"),
        "contract": ".codex/skills/hotspot-analysis-report/references/report-contract.md",
    }, {
        "id": "deep_hotspot_analysis",
        "name": "深层原因与发展预判 Skill",
        "description": "分析爆发原因、传播机制、分歧、影响和条件场景，并明确证据边界。",
        "guardrails": ["未证明爆发时禁止虚构触发点", "无预测模型时不输出伪精确概率", "每项判断标注证据状态"],
        "fallback": "LLM 不可用时使用确定性规则给出保守分析。",
    }]}


@app.post("/api/agent-runs", status_code=202)
async def start_run(request: RunRequest, background_tasks: BackgroundTasks):
    try:
        db.get_task(request.task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    active = db.active_run_for_task(request.task_id)
    if active:
        raise HTTPException(status_code=409, detail=f"该任务已有运行中的 Agent：{active['id']}")
    run_id = uuid.uuid4().hex
    db.create_run(run_id, request.task_id, settings.effective_ai_mode)
    db.update_run(run_id, status="queued")
    background_tasks.add_task(runner.run, request.task_id, run_id)
    return {"run_id": run_id, "status": "queued"}


@app.post("/api/agent-runs/sync")
async def start_run_sync(request: RunRequest):
    run_id = await runner.run(request.task_id)
    return db.get_run(run_id)


@app.get("/api/agent-runs/{run_id}")
async def get_run(run_id: str):
    result = db.get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return result


@app.get("/api/agent-runs/{run_id}/logs")
async def get_run_logs(run_id: str):
    if not db.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return {"items": db.list_run_logs(run_id)}


@app.get("/api/hotspots")
async def hotspots(
    limit: int = Query(default=20, ge=1, le=100),
    task_id: int = Query(default=1, ge=1),
):
    try:
        task = db.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "task": task.model_dump(),
        "run": db.latest_run_summary(task_id),
        "items": db.list_latest_events(limit, task_id=task_id),
    }


@app.get("/api/dashboard-summary")
async def dashboard_summary(task_id: int = Query(default=1, ge=1)):
    try:
        task = db.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"task": task.model_dump(), "run": db.latest_run_summary(task_id)}


@app.post("/api/hotspots/{event_id}/review")
async def review_hotspot(event_id: int, request: ReviewRequest):
    try:
        return db.review_event(event_id, request.status, request.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/hotspots/{event_id}/evidence")
async def hotspot_evidence(event_id: int):
    event = db.get_event_with_sources(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="热点事件不存在")
    counter_terms = ("否认", "纠错", "未能复现", "复现失败", "与结论冲突", "denies", "correction", "failed replication", "contradicts")
    supporting_source_refs = {
        ref for claim in event["claims"] if claim.get("status") == "verified"
        for ref in claim.get("evidence_source_refs", [])
    }
    counter_evidence = [
        {"claim": source["excerpt"], "source_title": source["title"], "source_url": source["url"]}
        for source in event["sources"]
        if source.get("evidence_role") == "counter_evidence"
        and source.get("contradicts_claims")
        and f"{source['source']}:{source['external_id']}" not in supporting_source_refs
        and source["excerpt"] and any(term in source["excerpt"].lower() for term in counter_terms)
    ]
    verified_claims = [claim for claim in event["claims"] if claim.get("status") == "verified"]
    inferred_claims = [claim for claim in event["claims"] if claim.get("status") == "reasonable_inference"]
    unverified_claims = [claim for claim in event["claims"] if claim.get("status") == "insufficient_evidence"]
    has_primary = any(source.get("evidence_role") == "primary_fact" for source in event["sources"])
    independent_confirmations = {
        source.get("original_publisher_id") or source.get("publisher_id") for source in event["sources"]
        if source.get("evidence_role") == "independent_confirm" and source.get("is_independent") and not source.get("is_repost")
    }
    missing_evidence = []
    if not has_primary:
        missing_evidence.append("原始公告或一手文件")
    if len(independent_confirmations) < 1:
        missing_evidence.append("第二独立发布方")
    if event.get("growth_label") == "无增长基线":
        missing_evidence.append("下一轮同指标快照")
    if not counter_evidence:
        missing_evidence.append("反方、否认或纠错材料")
    upgrade_conditions = [
        condition for condition in (
            "出现官方或一手确认" if not has_primary else None,
            "出现第二独立发布方" if len(independent_confirmations) < 1 else None,
            "连续至少三轮同指标增长且绝对增量达到门槛" if event.get("growth_label") != "持续增长" else None,
            "形成至少两个非转载平台的传播证据" if int(event["platform_count"]) < 2 else None,
        ) if condition
    ]
    content_type = event.get("content_type") or event.get("category") or ""
    source_types = {source.get("source") for source in event["sources"]}
    has_code = "github" in source_types
    has_independent = bool(independent_confirmations)
    if content_type == "研究论文":
        type_evidence_checklist = [
            {"label": "原论文与作者", "status": "已获取" if "arxiv" in source_types else "缺失"},
            {"label": "作者机构", "status": "待抽取"},
            {"label": "核心主张与实验数据", "status": "作者主张，待核验"},
            {"label": "公开代码", "status": "已找到" if has_code else "未找到"},
            {"label": "公开数据集", "status": "未确认"},
            {"label": "同行评审", "status": "未确认"},
            {"label": "独立复现", "status": "已找到" if has_independent else "未找到"},
            {"label": "产品适用环节", "status": "未评估"},
        ]
    elif content_type in {"产品发布", "开源新项目"}:
        type_evidence_checklist = [
            {"label": "官方公告 / Release", "status": "已获取" if any(source.get("event_type") in {"release_published", "repository_created"} for source in event["sources"]) else "缺失"},
            {"label": "Changelog 与功能变化", "status": "待抽取"},
            {"label": "价格与可用地区", "status": "未确认"},
            {"label": "用户反馈", "status": "已找到" if any(source in {"hacker_news", "devto", "v2ex", "bilibili"} for source in source_types) else "未找到"},
            {"label": "竞品对比与路线影响", "status": "未评估"},
        ]
    else:
        type_evidence_checklist = [
            {"label": "一手文件", "status": "已获取" if has_primary else "缺失"},
            {"label": "生效时间与适用范围", "status": "待核验"},
            {"label": "严重程度与产品影响", "status": "未评估"},
            {"label": "必须动作与法定截止时间", "status": "未评估"},
        ]
    return {
        "event_id": event_id, "title": event["canonical_title"], "sources": event["sources"],
        "counter_evidence": counter_evidence,
        "counter_evidence_status": None if counter_evidence else "本轮未找到可验证的反方、否认、纠错或独立复现材料。这不代表不存在反方证据。",
        "event_state": event.get("event_state", "未核验线索"),
        "evidence_tier": event.get("evidence_tier", "unverified"),
        "evidence_grade": event.get("evidence_grade", "U"),
        "event_gate_passed": bool(event.get("event_gate_passed")),
        "event_gate_reason": event.get("event_gate_reason", "尚未识别明确事件动作"),
        "decision_priority": event.get("decision_priority", "不进入决策"),
        "current_action": event.get("current_action", "补证"),
        "decision_owner": event.get("decision_owner", "竞争情报分析师"),
        "decision_deadline": event.get("decision_deadline", "下一工作日"),
        "decision_tasks": event.get("decision_tasks", []),
        "type_evidence_checklist": type_evidence_checklist,
        "claims_matrix": {
            "verified": verified_claims,
            "partial": inferred_claims,
            "unverified": unverified_claims,
            "missing_evidence": missing_evidence,
            "upgrade_conditions": upgrade_conditions,
        },
    }


@app.post("/api/hotspots/{event_id}/enrich")
async def enrich_hotspot(event_id: int):
    try:
        return await enrich_candidate(event_id, db, settings)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/hotspots/{event_id}/ask")
async def ask_hotspot(event_id: int, request: AskRequest):
    event = db.get_event_with_sources(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="热点事件不存在")
    cited = event["sources"][:3]
    unknowns: list[str] = []
    if event["source_count"] <= 1:
        unknowns.append("缺少第二个独立信源")
    if event["growth_percent"] is None:
        unknowns.append("缺少足够的跨轮次快照，暂无法证明实际增速")
    answer = (
        f"事件门槛：{'通过' if event.get('event_gate_passed') else '未通过'}，原因是“{event.get('event_gate_reason')}”。"
        f"证据等级为 {event.get('evidence_grade', 'U')}，当前决策优先级为“{event.get('decision_priority', '不进入决策')}”。"
        f"覆盖 {event['platform_count']} 个平台、{event['source_count']} 个独立发布链。"
        + (f"尚存在：{'；'.join(unknowns)}。" if unknowns else "当前核心事实已达到基本核验门槛。")
    )
    return {
        "question": request.question, "answer": answer,
        "citations": [{"source_id": item["id"], "title": item["title"], "url": item["url"]} for item in cited],
        "unknowns": unknowns,
    }


@app.post("/api/hotspots/{event_id}/deep-analysis")
async def deep_analyze_hotspot(event_id: int, request: DeepAnalysisRequest):
    try:
        result = await asyncio.to_thread(
            deep_analysis_skill.analyze, event_id, request.audience, request.horizon_days,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump()


@app.get("/api/filtering-reasons")
async def filtering_reasons(task_id: int = Query(default=1, ge=1)):
    result = db.filtering_reasons(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="该任务还没有完成记录")
    return result


@app.get("/api/scoring-diagnostics")
async def scoring_diagnostics(task_id: int = Query(default=1, ge=1)):
    result = db.scoring_diagnostics(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="该任务还没有评分记录")
    return result


@app.get("/api/benchmark/scoring")
async def scoring_benchmark():
    return evaluate_scoring_calibration()


@app.get("/api/evaluation/human-dataset")
async def human_evaluation_dataset():
    return human_dataset_status(settings.database_path.parent.parent / "evaluation" / "human_labeled_events.jsonl")


@app.get("/api/reports/latest")
async def latest_report(task_id: int = Query(default=1, ge=1)):
    summary = db.latest_run_summary(task_id)
    if not summary:
        raise HTTPException(status_code=404, detail="该任务还没有完成的分析报告")
    path = settings.report_dir / f"trend-report-{summary['id'][:8]}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)


@app.post("/api/reports/generate")
async def generate_report(request: ReportGenerateRequest):
    try:
        report = await asyncio.to_thread(
            report_skill.generate,
            request.task_id,
            request.report_type,
            request.scope,
            request.max_events,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return report.api_payload()


@app.get("/api/reports/{report_id}/download")
async def download_generated_report(report_id: str):
    path = report_skill.resolve_report_path(report_id)
    if not path:
        raise HTTPException(status_code=404, detail="分析报告不存在")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)


def _email_preview(task_id: int) -> dict:
    try:
        task = db.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary = db.latest_run_summary(task_id)
    if not summary:
        raise HTTPException(status_code=404, detail="该任务还没有完成的分析")
    events = db.list_approved_events(task_id=task_id, limit=10)
    try:
        brief = build_email_brief(task, summary, events)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return brief | {
        "configured": settings.email_configured,
        "recipients": [mask_email(item) for item in settings.email_recipients],
    }


@app.get("/api/email/preview")
async def email_preview(task_id: int = Query(default=1, ge=1)):
    return _email_preview(task_id)


@app.post("/api/email/send")
async def email_send(request: EmailSendRequest):
    preview = _email_preview(request.task_id)
    if not settings.email_configured:
        raise HTTPException(status_code=503, detail="邮件 SMTP 尚未配置，请先填写 .env 中的 SMTP 参数")
    try:
        sent_count = await asyncio.to_thread(send_email, settings, preview)
    except Exception as exc:
        logging.getLogger(__name__).exception("Email delivery failed")
        raise HTTPException(status_code=502, detail=f"邮件发送失败：{type(exc).__name__}") from exc
    delivery_id = db.record_email_delivery(
        request.task_id, sent_count, preview["selected_count"], preview["subject"], "sent",
    )
    return {
        "status": "sent", "delivery_id": delivery_id,
        "recipient_count": sent_count, "hotspot_count": preview["selected_count"],
    }


@app.post("/api/scheduler/run-now")
async def run_scheduler_now():
    await scheduled_job()
    return {"status": "completed"}
