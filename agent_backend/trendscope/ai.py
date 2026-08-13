from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from openai import OpenAI

from .config import Settings
from .models import AnalysisBatch, EventAnalysis, EventCandidate, MonitoringTask
from .processing import rule_analysis


SYSTEM_PROMPT = """
你是 TrendScope 热点分析 Agent。你会收到程序已经采集、清洗、计算过的真实公开信息。

要求：
1. 只能使用输入材料，不得编造讨论量、日期、人名、融资金额、性能或来源。
2. canonical_title 必须是对事件的中性概括，不得用夸张标题。
3. 区分事件真实性与聚类置信度。
4. 多个平台转载同一内容不自动等于多个独立信源。
5. 信息不足时明确写“信息不足”。
6. recommended_action 必须针对目标用户，具体且可执行。
7. 如果候选内容其实不相关，is_relevant=false。
8. 输出必须严格符合结构化模型。
9. 仅输出 JSON 对象，不得包含 Markdown 代码块或额外说明。
10. 无论候选事件是 1 个还是多个，顶层必须始终是 {"events": [...]}，不得直接返回单个事件。
11. 只有 event_type=repository_created、release_published，或来源正文明确包含发布公告时，才能使用“发布、上线、推出、开源发布”。
12. pushed_at 或 updated_at 只代表仓库近期更新，不代表项目首次发布。
13. 无法判断事件类型时，标题使用“近期受到关注”或“近期更新”，不得推断发布。
14. 每个事件必须原样返回 candidate_id；不知道或缺失时不要输出该事件，禁止猜测。
15. claims 中每项重要主张必须标注证据来源引用和状态；无证据不得标记 verified。
16. 没有讨论来源时禁止写“社区认为、引发争议”；没有比较基准时禁止写“较高、领先、广泛采用、技术实力强”。
17. canonical_title 必须逐字复制输入的 rule_canonical_title，不得改写。
18. affected_product、affected_user、impact_mechanism、urgency_reason、cost_of_inaction、recommended_owner、minimum_action、deadline_reason 只能依据输入填写；证据不足必须返回 null，不得用通用模板补齐。
19. 研究论文的发布事实成立不等于技术结论成立；未提供产品路线上下文时，affected_product 和 cost_of_inaction 必须为 null。
"""


def _candidate_payload(candidate: EventCandidate) -> dict:
    return {
        "candidate_id": candidate.candidate_id,
        "rule_canonical_title": candidate.canonical_title,
        "program_metrics": {
            "relevance_score": candidate.relevance_score,
            "attention_signal": candidate.attention_signal,
            "growth_percent": candidate.growth_percent,
            "platform_count": candidate.platform_count,
            "source_count": candidate.source_count,
            "lifecycle": candidate.lifecycle,
            "value_score": candidate.value_score,
            "value_level": candidate.value_level,
            "truth_status": candidate.truth_status,
            "hotspot_confidence": candidate.hotspot_confidence,
            "cluster_confidence": candidate.cluster_confidence,
        },
        "allowed_action_scope": (
            ["核对原始来源", "寻找第二独立信源", "记录下一轮指标", "进行低成本内部测试"]
            if candidate.value_level == "candidate" else
            ["核对原始来源", "持续监控", "内部技术评估", "小范围试点"]
        ),
        "forbidden_actions": ["正式合作", "规模部署", "增加战略投入", "对外传播为确定趋势"],
        "sources": [
            {
                "source_ref": f"{item.source}:{item.external_id}",
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "published_at": item.published_at.isoformat(),
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "pushed_at": item.pushed_at.isoformat() if item.pushed_at else None,
                "released_at": item.released_at.isoformat() if item.released_at else None,
                "event_type": item.event_type,
                "content": item.content[:1200],
                "metrics": item.metrics.model_dump(),
                "is_primary_source": item.is_primary_source,
            }
            for item in candidate.items
        ],
    }


def _parse_analysis_batch(
    content: str,
    candidates: list[EventCandidate],
    task: MonitoringTask,
) -> tuple[AnalysisBatch, int]:
    """兼容网关的 JSON 包装差异，并用规则结果补全模型遗漏字段。"""
    raw = json.loads(content)
    if isinstance(raw, dict) and "events" in raw:
        raw_events = raw["events"]
    elif isinstance(raw, list):
        raw_events = raw
    elif isinstance(raw, dict) and "candidate_id" in raw:
        raw_events = [raw]
    else:
        raise ValueError("LLM JSON 缺少 events 数组，也不是可识别的单事件对象")
    if not isinstance(raw_events, list):
        raise ValueError("LLM JSON 中的 events 必须是数组")

    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    allowed_fields = set(EventAnalysis.model_fields)
    optional_business_fields = {
        "affected_product", "affected_user", "impact_mechanism", "urgency_reason",
        "cost_of_inaction", "recommended_owner", "minimum_action", "deadline_reason",
    }
    events: list[EventAnalysis] = []
    repaired_fields = 0
    seen_candidate_ids: set[str] = set()
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        candidate_id = str(raw_event.get("candidate_id", ""))
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None or candidate_id in seen_candidate_ids:
            repaired_fields += 1
            continue
        seen_candidate_ids.add(candidate_id)

        defaults = rule_analysis(candidate, task).model_dump()
        repaired_fields += len((allowed_fields - {"claims"} - optional_business_fields) - set(raw_event))
        merged = dict(defaults)
        # 只接受通过完整 EventAnalysis 校验的模型字段；非法枚举保留规则值。
        for field, value in raw_event.items():
            if field not in allowed_fields or field == "candidate_id":
                continue
            trial = {**merged, field: value}
            try:
                EventAnalysis.model_validate(trial)
            except Exception:
                repaired_fields += 1
            else:
                merged[field] = value
        merged["candidate_id"] = candidate.candidate_id
        events.append(EventAnalysis.model_validate(merged))
    return AnalysisBatch(events=events), repaired_fields


def analyze_candidates(
    candidates: list[EventCandidate],
    task: MonitoringTask,
    settings: Settings,
) -> tuple[list[EventAnalysis], str | None, dict[str, Any]]:
    started_at = time.perf_counter()
    stats: dict[str, Any] = {
        "ai_irrelevant_count": 0, "ai_parse_failure_count": 0, "ai_repaired_fields": 0,
        "ai_success_count": 0, "ai_fallback_count": 0, "ai_duration_ms": 0,
        "ai_success_candidate_ids": [], "ai_error_summaries": [],
    }
    if settings.effective_ai_mode != "openai":
        stats["ai_fallback_count"] = len(candidates)
        return [rule_analysis(candidate, task) for candidate in candidates], None, stats

    try:
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=min(settings.llm_timeout_seconds, 45.0),
            max_retries=1,
        )
        def request_batch(batch: list[EventCandidate]) -> tuple[AnalysisBatch, int]:
            payload = {
                "monitoring_topic": task.topic,
                "target_role": task.target_role,
                "candidates": [_candidate_payload(candidate) for candidate in batch],
                "required_output_schema": AnalysisBatch.model_json_schema(),
            }
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            if settings.openai_api_style == "chat_completions":
                stream = client.chat.completions.create(
                    model=settings.openai_model, messages=messages,
                    response_format={"type": "json_object"},
                    stream=True,
                )
                content = "".join(
                    chunk.choices[0].delta.content or ""
                    for chunk in stream if chunk.choices
                )
                if not content:
                    raise ValueError("模型未返回内容")
                return _parse_analysis_batch(content, batch, task)
            if settings.openai_api_style == "responses":
                response = client.responses.parse(
                    model=settings.openai_model, input=messages, text_format=AnalysisBatch,
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise ValueError("模型未返回结构化结果")
                return parsed, 0
            raise ValueError(
                f"不支持的 OPENAI_API_STYLE={settings.openai_api_style!r}，可选 responses 或 chat_completions"
            )

        by_id: dict[str, EventAnalysis] = {}
        warnings: list[str] = []
        # AI 只处理排序前 10 条；尾部低分线索保留规则分析，避免 Demo 被网关延迟拖垮。
        target_candidates = candidates[:10]
        # 两条一批降低跨候选串扰和网关请求体过大风险；缺失项再单独重试。
        batches = [target_candidates[offset:offset + 2] for offset in range(0, len(target_candidates), 2)]
        retry_candidates: list[EventCandidate] = []
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as pool:
            futures = {pool.submit(request_batch, batch): (index, batch) for index, batch in enumerate(batches, start=1)}
            for future in as_completed(futures):
                index, batch = futures[future]
                try:
                    parsed, repaired_fields = future.result()
                    stats["ai_repaired_fields"] += repaired_fields
                    by_id.update({analysis.candidate_id: analysis for analysis in parsed.events})
                    retry_candidates.extend(
                        candidate for candidate in batch if candidate.candidate_id not in by_id
                    )
                except Exception as exc:
                    status = getattr(exc, "status_code", None)
                    body = getattr(exc, "body", None)
                    detail = str(body or exc).replace(settings.openai_api_key, "***")[:240]
                    summary = f"批次 {index} 失败：{type(exc).__name__} HTTP {status or '未知'} · {detail}"
                    warnings.append(summary)
                    stats["ai_error_summaries"].append(summary)
                    retry_candidates.extend(batch)

        missing = list({candidate.candidate_id: candidate for candidate in retry_candidates}.values())
        if missing:
            with ThreadPoolExecutor(max_workers=min(5, len(missing))) as pool:
                retries = {pool.submit(request_batch, [candidate]): candidate for candidate in missing}
                for future in as_completed(retries):
                    candidate = retries[future]
                    try:
                        parsed, repaired_fields = future.result()
                        stats["ai_repaired_fields"] += repaired_fields
                        matched = next(
                            (item for item in parsed.events if item.candidate_id == candidate.candidate_id), None,
                        )
                        if matched:
                            by_id[candidate.candidate_id] = matched
                        else:
                            stats["ai_parse_failure_count"] += 1
                    except Exception as exc:
                        stats["ai_parse_failure_count"] += 1
                        status = getattr(exc, "status_code", None)
                        body = getattr(exc, "body", None)
                        detail = str(body or exc).replace(settings.openai_api_key, "***")[:240]
                        stats["ai_error_summaries"].append(
                            f"单项 {candidate.candidate_id} 失败：{type(exc).__name__} HTTP {status or '未知'} · {detail}"
                        )

        analyses = [by_id.get(candidate.candidate_id) or rule_analysis(candidate, task) for candidate in candidates]
        stats["ai_irrelevant_count"] = sum(not analysis.is_relevant for analysis in by_id.values())
        stats["ai_success_candidate_ids"] = list(by_id)
        stats["ai_success_count"] = len(by_id)
        stats["ai_fallback_count"] = len(candidates) - len(by_id)
        stats["ai_duration_ms"] = round((time.perf_counter() - started_at) * 1000)
        if stats["ai_repaired_fields"]:
            warnings.append(f"已用程序指标补全 {stats['ai_repaired_fields']} 个缺失或无效字段")
        if stats["ai_parse_failure_count"]:
            warnings.append(f"{stats['ai_parse_failure_count']} 个候选在单项重试后仍使用规则降级")
        return analyses, "；".join(warnings) or None, stats
    except Exception as exc:
        fallback = [rule_analysis(candidate, task) for candidate in candidates]
        stats["ai_parse_failure_count"] = len(candidates)
        stats["ai_fallback_count"] = len(candidates)
        stats["ai_duration_ms"] = round((time.perf_counter() - started_at) * 1000)
        status = getattr(exc, "status_code", None)
        body = getattr(exc, "body", None)
        detail = str(body or exc).replace(settings.openai_api_key, "***")[:240]
        stats["ai_error_summaries"] = [f"{type(exc).__name__} HTTP {status or '未知'} · {detail}"]
        return fallback, f"LLM 分析失败，已降级为规则模式：{stats['ai_error_summaries'][0]}", stats
