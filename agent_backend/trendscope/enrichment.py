from __future__ import annotations

import asyncio

from .collectors import collect_arxiv, collect_github, collect_google_news, collect_hacker_news, collect_rss
from .config import Settings
from .database import Database
from .models import EventSignature, MonitoringTask
from .processing import compare_event_signatures, extract_event_signature, normalize_entity_aliases, prepare_items


async def enrich_candidate(event_id: int, db: Database, settings: Settings) -> dict:
    """只围绕一个候选补事实、独立确认和讨论证据，不扩大为新一轮广搜。"""
    event = db.get_event_with_sources(event_id)
    if not event:
        raise KeyError(f"事件 {event_id} 不存在")
    base_task = db.get_task(int(db.get_run(event["run_id"])["task_id"]))
    stored_signature = EventSignature.model_validate(event.get("event_signature") or {})
    entities = stored_signature.entities or normalize_entity_aliases(event["canonical_title"])
    focused_keywords = [event["canonical_title"], *entities]
    focused_task = MonitoringTask(
        id=base_task.id,
        name=f"{event['canonical_title']} 定向补证",
        topic=event["canonical_title"],
        keywords=list(dict.fromkeys(keyword for keyword in focused_keywords if keyword))[:8],
        excluded_keywords=base_task.excluded_keywords,
        rss_feeds=base_task.rss_feeds,
        target_role=base_task.target_role,
        time_window_hours=base_task.time_window_hours,
    )
    content_type = event.get("content_type") or ""
    if content_type in {"开源新项目", "产品发布", "持续活跃项目"}:
        collector_plan = [
            ("GitHub 项目与发布", collect_github),
            ("已配置正式 RSS", collect_rss),
            ("Google News 独立报道", collect_google_news),
            ("Hacker News 开发者讨论", collect_hacker_news),
        ]
    elif content_type == "研究论文":
        collector_plan = [
            ("arXiv 原论文", collect_arxiv),
            ("已配置机构 RSS", collect_rss),
            ("Google News 独立报道", collect_google_news),
        ]
    elif content_type == "权威公告":
        collector_plan = [
            ("已配置正式 RSS", collect_rss),
            ("Google News 独立报道", collect_google_news),
        ]
    else:
        collector_plan = [
            ("Google News 独立报道", collect_google_news),
            ("已配置 RSS", collect_rss),
            ("Hacker News 开发者讨论", collect_hacker_news),
        ]
    groups = await asyncio.gather(
        *(collector(focused_task, settings) for _, collector in collector_plan),
        return_exceptions=True,
    )
    collected = [item for group in groups if isinstance(group, list) for item in group]
    cleaned, _ = prepare_items(collected, focused_task)
    matched = []
    decisions = []
    for item in cleaned:
        same, confidence, reasons = compare_event_signatures(stored_signature, extract_event_signature(item))
        decisions.append({"title": item.title, "same_event": same, "confidence": confidence, "reasons": reasons})
        if same:
            matched.append(item)
    reassessment = db.attach_evidence_and_reassess(event_id, matched)
    return {
        "event_id": event_id,
        "enrichment_route": content_type or "通用事件",
        "searched_sources": [name for name, _ in collector_plan],
        "collected_count": len(collected),
        "matched_count": len(matched),
        "decisions": decisions[:20],
        **reassessment,
    }
