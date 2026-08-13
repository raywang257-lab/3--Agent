from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from .ai import analyze_candidates
from .collectors import collect_all
from .config import Settings
from .database import Database
from .enrichment import enrich_candidate
from .processing import actual_cluster_merge_count, cluster_items, finalize_business_decision, passes_source_gate, prepare_items, relevance_score, sanitize_analysis
from .report_skill import AnalysisReportSkill


logger = logging.getLogger(__name__)


class TrendAgentRunner:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    async def run(self, task_id: int = 1, run_id: str | None = None) -> str:
        run_id = run_id or uuid.uuid4().hex
        task = self.db.get_task(task_id)
        if self.db.get_run(run_id) is None:
            self.db.create_run(run_id, task_id, self.settings.effective_ai_mode)
        else:
            self.db.update_run(run_id, status="collecting")
        self.db.log(run_id, "start", f"启动监控任务：{task.name}")
        try:
            self.db.update_run(run_id, status="collecting")

            def on_source(name: str, count: int, error: str | None) -> None:
                if error:
                    self.db.log(run_id, "collecting", f"{name} 采集失败：{error}", "warning")
                else:
                    self.db.log(run_id, "collecting", f"{name} 获取 {count} 条公开信息")

            items = await collect_all(task, self.settings, on_source)
            self.db.update_run(run_id, items_collected=len(items), status="filtering")
            self.db.log(run_id, "filtering", f"共获取 {len(items)} 条，开始清洗与去重")

            cleaned, removed = prepare_items(items, task)
            removed_count = len(items) - len(cleaned)
            self.db.update_run(
                run_id, items_filtered=removed_count,
                invalid_items=removed.get("invalid", 0), excluded_items=removed.get("excluded", 0),
                duplicate_items=removed.get("duplicate", 0),
            )
            self.db.log(run_id, "filtering", f"清洗后保留 {len(cleaned)} 条；移除明细：{removed}")

            source_id_by_key: dict[tuple[str, str], int] = {}
            for item in cleaned:
                source_id_by_key[(item.source, item.external_id)] = self.db.save_source_item(run_id, item)

            self.db.update_run(run_id, status="clustering")
            discovered = cluster_items(cleaned, task, self.db)
            candidates = [candidate for candidate in discovered if candidate.event_gate_passed]
            information_only = len(discovered) - len(candidates)
            relevant_item_count = sum(
                passes_source_gate(item, relevance_score(item, task), task) for item in cleaned
            )
            relevance_filtered = len(cleaned) - relevant_item_count
            cluster_merged = actual_cluster_merge_count(cleaned, task)
            self.db.update_run(
                run_id, candidates_created=len(candidates), relevance_filtered=relevance_filtered + information_only,
                cluster_merged=cluster_merged,
            )
            self.db.log(
                run_id, "clustering",
                f"形成 {len(candidates)} 个可判断事件；{information_only} 条仅为资讯线索，过滤出榜",
            )

            self.db.update_run(run_id, status="analyzing")
            analyses, warning, ai_stats = await asyncio.to_thread(
                analyze_candidates, candidates, task, self.settings
            )
            if warning:
                self.db.log(run_id, "analyzing", warning, "warning")
            else:
                self.db.log(run_id, "analyzing", f"使用 {self.settings.effective_ai_mode} 模式完成结构化分析")

            analysis_by_id = {analysis.candidate_id: analysis for analysis in analyses}
            low_count = sum(candidate.value_level == "candidate" for candidate in candidates)
            watch_count = sum(candidate.value_level == "watchlist" for candidate in candidates)
            high_count = sum(candidate.value_level == "high_value" for candidate in candidates)
            self.db.update_run(
                run_id,
                # 兼容旧字段但不再写入；AI 不相关只是辅助统计，不能推翻程序候选。
                ai_rejected=0,
                ai_irrelevant_count=ai_stats["ai_irrelevant_count"],
                ai_parse_failure_count=ai_stats["ai_parse_failure_count"],
                ai_success_count=ai_stats["ai_success_count"],
                ai_fallback_count=ai_stats["ai_fallback_count"],
                ai_duration_ms=ai_stats["ai_duration_ms"],
            )
            self.db.log(
                run_id, "analyzing",
                f"AI 分析：{ai_stats['ai_success_count']}/{len(candidates)} 成功；"
                f"规则降级：{ai_stats['ai_fallback_count']}/{len(candidates)}；"
                f"模型耗时：{ai_stats['ai_duration_ms']} ms",
                "warning" if ai_stats["ai_fallback_count"] else "info",
            )
            self.db.log(
                run_id,
                "analyzing",
                f"程序价值分层：{high_count} 个高价值、{watch_count} 个持续观察、{low_count} 个候选线索",
            )
            event_count = 0
            event_ids: list[int] = []
            quality_gate_fallback_count = 0
            for candidate in candidates:
                analysis = analysis_by_id.get(candidate.candidate_id)
                if not analysis:
                    continue
                analysis, consistency_warnings = sanitize_analysis(analysis, candidate, task)
                candidate = finalize_business_decision(candidate, analysis)
                quality_gate_fallback_count += len(consistency_warnings)
                for consistency_warning in consistency_warnings:
                    self.db.log(run_id, "quality_gate", consistency_warning, "warning")
                program_action = {
                    "忽略": "暂不处理", "补证": "谨慎验证", "技术初筛": "谨慎验证",
                    "观察": "持续观察", "业务评估": "谨慎验证", "立即行动": "立即跟进",
                }[candidate.current_action]
                title = analysis.canonical_title
                if any(item.event_type == "repository_updated" for item in candidate.items):
                    forbidden = ("发布", "上线", "推出", "开源发布")
                    if any(word in title for word in forbidden):
                        title = candidate.canonical_title
                analysis = analysis.model_copy(update={
                    "canonical_title": title,
                    "category": candidate.content_type,
                    "truth_status": candidate.truth_status,
                    "cluster_confidence": candidate.cluster_confidence,
                    "action_level": program_action,
                })
                source_ids = [source_id_by_key[(item.source, item.external_id)] for item in candidate.items]
                analysis_mode = "ai" if candidate.candidate_id in ai_stats["ai_success_candidate_ids"] else "rules"
                event_ids.append(self.db.save_event(run_id, candidate, analysis, source_ids, analysis_mode=analysis_mode))
                event_count += 1

            # 对最多 3 个单源事件自动走类型化补证，而不是等用户点击“补充证据”。
            enrich_targets = event_ids[:3]
            if enrich_targets:
                self.db.log(run_id, "enriching", f"自动启动 {len(enrich_targets)} 个事件的类型化补证")
                enrichment_results = await asyncio.gather(
                    *(enrich_candidate(event_id, self.db, self.settings) for event_id in enrich_targets),
                    return_exceptions=True,
                )
                for event_id, result in zip(enrich_targets, enrichment_results):
                    if isinstance(result, Exception):
                        self.db.log(run_id, "enriching", f"事件 {event_id} 自动补证失败：{type(result).__name__}: {str(result)[:180]}", "warning")
                    else:
                        self.db.log(
                            run_id, "enriching",
                            f"事件 {event_id} 按{result['enrichment_route']}路由检索，"
                            f"命中 {result['matched_count']} 条同事件线索，新增关联 {result['attached_count']} 条证据并已重新评估",
                        )

            self.db.update_run(
                run_id,
                status="completed",
                completed_at=datetime.now(timezone.utc).isoformat(),
                events_created=event_count,
                quality_gate_fallback_count=quality_gate_fallback_count,
            )
            self.db.log(run_id, "completed", f"任务完成，保存 {event_count} 个候选事件，其中 {high_count} 个高价值热点")
            report = AnalysisReportSkill(self.db, self.settings).generate(
                task_id=task_id, report_type="full_analysis", scope="qualified", run_id=run_id,
            )
            self.db.log(run_id, "report", f"分析报告 Skill 已生成 {report.path.name}")
            return run_id
        except Exception as exc:
            logger.exception("Agent run failed")
            self.db.update_run(
                run_id,
                status="failed",
                completed_at=datetime.now(timezone.utc).isoformat(),
                error_message=f"{type(exc).__name__}: {exc}",
            )
            self.db.log(run_id, "failed", f"任务失败：{type(exc).__name__}: {exc}", "error")
            return run_id
