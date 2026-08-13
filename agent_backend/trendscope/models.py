from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MonitoringTask(BaseModel):
    id: int = 1
    name: str = "AI 编程工具监控"
    topic: str = "AI 编程工具"
    keywords: list[str] = Field(default_factory=lambda: [
        "AI coding", "coding agent", "code assistant", "AI IDE",
        "developer agent", "code generation", "Copilot", "Cursor",
    ])
    excluded_keywords: list[str] = Field(default_factory=lambda: ["travel agent", "real estate agent"])
    rss_feeds: list[str] = Field(default_factory=list)
    target_role: str = "AI 产品与竞争情报负责人"
    time_window_hours: int = 14 * 24
    enabled: bool = True


class SourceMetrics(BaseModel):
    score: int | None = None
    comments: int | None = None
    stars: int | None = None
    forks: int | None = None


class SourceItem(BaseModel):
    source: Literal[
        "github", "hacker_news", "rss", "google_news", "google_trends",
        "arxiv", "devto", "v2ex", "bilibili", "chinanews", "cctv_news",
    ]
    external_id: str
    title: str
    url: str
    discussion_url: str | None = None
    author: str | None = None
    content: str = ""
    published_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    released_at: datetime | None = None
    event_type: Literal[
        "repository_created", "repository_updated", "release_published",
        "news_published", "discussion_created", "paper_published",
        "article_published", "video_published",
    ] | None = None
    collected_at: datetime = Field(default_factory=utc_now)
    metrics: SourceMetrics = Field(default_factory=SourceMetrics)
    is_primary_source: bool = False
    evidence_role: Literal[
        "primary_fact", "independent_confirm", "adoption_signal", "attention_signal",
        "counter_evidence", "repost", "opinion",
    ] = "opinion"
    publisher_id: str = ""
    publisher_type: str = "unknown"
    original_publisher_id: str | None = None
    original_url: str | None = None
    is_independent: bool = True
    is_repost: bool = False
    supports_claims: list[str] = Field(default_factory=list)
    contradicts_claims: list[str] = Field(default_factory=list)
    content_hash: str = ""


class EventSignature(BaseModel):
    entities: list[str] = Field(default_factory=list)
    action: str = "unknown"
    object: str | None = None
    event_time: datetime | None = None
    geography: str | None = None
    aliases: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)


class EventCandidate(BaseModel):
    candidate_id: str
    canonical_title: str
    items: list[SourceItem]
    relevance_score: float
    attention_signal: float
    platform_count: int
    source_count: int
    growth_percent: float | None = None
    lifecycle: Literal["萌芽", "爆发", "扩散", "衰退", "未知"] = "未知"
    value_score: float = 0
    value_level: Literal["high_value", "watchlist", "candidate"] = "candidate"
    truth_status: Literal["较高", "中等", "信息不足"] = "信息不足"
    hotspot_confidence: Literal["较高", "待观察", "证据不足"] = "证据不足"
    cluster_confidence: Literal["较高", "中等", "不适用"] = "不适用"
    content_type: str = "低置信度线索"
    score_breakdown: dict = Field(default_factory=dict)
    metric_deltas: dict = Field(default_factory=dict)
    event_signature: EventSignature = Field(default_factory=EventSignature)
    evidence_tier: Literal["verified", "corroborated", "primary_only", "single_source", "unverified"] = "unverified"
    event_state: Literal["资讯线索", "未核验线索", "单一来源线索", "已证实事件", "升温事件", "跨平台热点", "衰退/归档"] = "未核验线索"
    evidence_confidence: float = 0
    evidence_grade: Literal["A", "B", "C", "D", "U"] = "U"
    growth_label: str = "无增长基线"
    event_gate_passed: bool = False
    event_gate_reason: str = "尚未识别明确事件动作"
    decision_priority: Literal["未评估", "低", "中", "高", "紧急", "不进入决策"] = "未评估"
    current_action: Literal["忽略", "补证", "技术初筛", "观察", "业务评估", "立即行动"] = "补证"
    decision_owner: str = "竞争情报分析师"
    decision_deadline: str = "下一工作日"
    decision_tasks: list[str] = Field(default_factory=list)
    upgrade_conditions: list[str] = Field(default_factory=list)


class AnalysisClaim(BaseModel):
    type: Literal["verified_fact", "interpretation", "unknown"]
    text: str
    evidence_source_refs: list[str] = Field(default_factory=list)
    evidence_fields: list[str] = Field(default_factory=list)
    status: Literal["verified", "reasonable_inference", "insufficient_evidence"]


class EventAnalysis(BaseModel):
    candidate_id: str
    is_relevant: bool
    canonical_title: str
    category: str
    summary: str
    why_now: str
    debate: str
    impact: str
    recommended_action: str
    risk: str
    truth_status: Literal["较高", "中等", "较低", "信息不足"]
    cluster_confidence: Literal["较高", "中等", "较低", "不适用"]
    action_level: Literal["立即跟进", "持续观察", "暂不处理", "谨慎验证"]
    claims: list[AnalysisClaim] = Field(default_factory=list)
    affected_product: str | None = None
    affected_user: str | None = None
    impact_mechanism: str | None = None
    urgency_reason: str | None = None
    cost_of_inaction: str | None = None
    recommended_owner: str | None = None
    minimum_action: str | None = None
    deadline_reason: str | None = None


class AnalysisBatch(BaseModel):
    events: list[EventAnalysis]


class StoredEvent(BaseModel):
    id: int
    run_id: str
    canonical_title: str
    category: str
    summary: str
    why_now: str
    debate: str
    impact: str
    recommended_action: str
    risk: str
    truth_status: str
    cluster_confidence: str
    action_level: str
    relevance_score: float
    attention_signal: float
    growth_percent: float | None
    platform_count: int
    source_count: int
    lifecycle: str
    first_seen_at: datetime
    last_seen_at: datetime
    sources: list[dict] = Field(default_factory=list)


class RunStatus(BaseModel):
    id: str
    task_id: int
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    items_collected: int = 0
    items_filtered: int = 0
    events_created: int = 0
    ai_mode: str = "rules"
    error_message: str | None = None


class RunRequest(BaseModel):
    task_id: int = 1


class ReviewRequest(BaseModel):
    status: Literal["pending", "approved", "rejected"]
    note: str = Field(default="", max_length=500)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class DeepAnalysisRequest(BaseModel):
    audience: str | None = Field(default=None, max_length=200)
    horizon_days: int = Field(default=7, ge=1, le=90)


class EmailSendRequest(BaseModel):
    task_id: int = Field(default=1, ge=1)


class ReportGenerateRequest(BaseModel):
    task_id: int = Field(default=1, ge=1)
    report_type: Literal["decision_brief", "full_analysis"] = "full_analysis"
    scope: Literal["qualified", "all_visible", "approved_only"] = "qualified"
    max_events: int = Field(default=10, ge=1, le=30)


class HealthResponse(BaseModel):
    status: str
    ai_mode: str
    database: str
    scheduler_enabled: bool
