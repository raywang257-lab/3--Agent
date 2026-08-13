from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from .config import Settings
from .database import Database
from .deep_analysis_skill import DeepAnalysisResult


REPORT_SKILL_ROOT = Path(__file__).resolve().parents[2] / ".codex" / "skills" / "hotspot-analysis-report"
REPORT_CONTRACT_PATH = REPORT_SKILL_ROOT / "references" / "report-contract.md"


def _load_report_contract() -> str:
    if not REPORT_CONTRACT_PATH.exists():
        raise RuntimeError(f"分析报告 Skill 契约不存在：{REPORT_CONTRACT_PATH}")
    return REPORT_CONTRACT_PATH.read_text(encoding="utf-8")


REPORT_SYSTEM_PROMPT = """
你是 TrendScope 的分析报告 Skill。输入全部来自系统已保存的真实公开材料和程序指标。

硬性要求：
1. 不得补充输入中不存在的事实、数字、日期、人名、市场规模或因果关系。
2. 明确区分“热点已成立”“持续观察”和“候选线索”，不得把低分线索写成确定趋势。
3. 单一来源、缺少增速快照或缺少独立信源时，必须在 limitations 中写明。
4. executive_summary 面向输入中的 target_role，先结论后理由。
5. key_findings 只能引用输入事件标题；recommended_actions 必须具体但不得越过证据。
6. 输出严格为 JSON 对象，不得使用 Markdown 代码块。
7. executive_summary 第一句必须明确说明本轮是否发现达到高价值阈值的热点。
8. 候选线索只能建议核验、监控、补充独立信源或低成本内部测试。
""" + "\n\n以下项目 Skill 契约同样是硬性要求：\n" + _load_report_contract()


class ReportNarrative(BaseModel):
    executive_summary: str
    key_findings: list[str] = Field(default_factory=list, max_length=5)
    recommended_actions: list[str] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(default_factory=list, max_length=6)


@dataclass(frozen=True)
class GeneratedReport:
    report_id: str
    title: str
    report_type: str
    scope: str
    generation_mode: str
    generated_at: str
    event_count: int
    executive_summary: str
    key_findings: list[str]
    recommended_actions: list[str]
    limitations: list[str]
    markdown: str
    path: Path

    def api_payload(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "report_type": self.report_type,
            "scope": self.scope,
            "generation_mode": self.generation_mode,
            "generated_at": self.generated_at,
            "event_count": self.event_count,
            "executive_summary": self.executive_summary,
            "key_findings": self.key_findings,
            "recommended_actions": self.recommended_actions,
            "limitations": self.limitations,
            "markdown": self.markdown,
            "download_url": f"/api/reports/{self.report_id}/download",
        }


class AnalysisReportSkill:
    """把已入库热点转换为可审计报告；LLM 只负责归纳，不改变程序判断。"""

    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def generate(
        self,
        task_id: int,
        report_type: Literal["decision_brief", "full_analysis"] = "full_analysis",
        scope: Literal["qualified", "all_visible", "approved_only"] = "qualified",
        max_events: int = 10,
        run_id: str | None = None,
    ) -> GeneratedReport:
        task = self.db.get_task(task_id)
        run = self.db.get_run(run_id) if run_id else self.db.latest_run_summary(task_id)
        if not run or run.get("status") != "completed":
            raise ValueError("该任务还没有可生成报告的已完成分析")

        raw_events = self.db.list_latest_events(limit=max(max_events, 30), task_id=task_id)
        if scope == "approved_only":
            events = self.db.list_approved_events(task_id=task_id, limit=max_events)
            if not events:
                raise ValueError("没有已人工确认的热点，无法生成仅含已确认事件的报告")
        elif scope == "qualified":
            events = [
                event for event in raw_events
                if event.get("review", {}).get("status") == "approved"
                or (
                    event["value_level"] in {"high_value", "watchlist"}
                    and event.get("evidence_tier") in {"verified", "corroborated"}
                )
            ][:max_events]
            if not events:
                events = raw_events[:min(3, max_events)]
        else:
            events = raw_events[:max_events]
        if not events:
            raise ValueError("本轮没有可写入报告的事件")

        events, quality_warnings = self._quality_gate(events)
        if not events:
            raise ValueError("报告质量闸门拒绝了全部事件：事件没有可回溯来源")

        narrative, generation_mode = self._build_narrative(task.model_dump(), run, events)
        narrative.limitations.extend(item for item in quality_warnings if item not in narrative.limitations)
        # 本报告只整理已存在的主张与证据，不自动扩写深层原因、恢复周期或概率场景。
        deep_analyses: dict[int, DeepAnalysisResult] = {}
        diagnostics = self.db.scoring_diagnostics(task_id)
        if diagnostics and diagnostics["single_source_events"]:
            note = (
                f"评分诊断：最新一轮 {diagnostics['single_source_events']}/{diagnostics['event_count']} 个事件只有一个来源，"
                f"{diagnostics['no_positive_growth_events']}/{diagnostics['event_count']} 个事件没有正增长证据。"
            )
            if note not in narrative.limitations:
                narrative.limitations.append(note)
        generated_at = datetime.now(timezone.utc).isoformat()
        report_id = f"{str(run['id'])[:8]}-{report_type}-{scope}"
        has_qualified_hotspot = any(event["value_level"] in {"high_value", "watchlist"} for event in events)
        title = (
            f"TrendScope｜{task.topic}{'决策简报' if report_type == 'decision_brief' else '热点分析报告'}"
            if has_qualified_hotspot else f"TrendScope｜{task.topic}候选线索监测简报"
        )
        markdown = self._render_markdown(
            title, task.model_dump(), run, events, narrative, generated_at, report_type, scope,
            diagnostics, deep_analyses,
        )
        self.settings.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.report_dir / f"{report_id}.md"
        path.write_text(markdown, encoding="utf-8")

        # 保留旧下载地址，兼容已经打开的前端和文档。
        if report_type == "full_analysis" and scope == "qualified":
            legacy = self.settings.report_dir / f"trend-report-{str(run['id'])[:8]}.md"
            legacy.write_text(markdown, encoding="utf-8")

        return GeneratedReport(
            report_id=report_id, title=title, report_type=report_type, scope=scope,
            generation_mode=generation_mode, generated_at=generated_at, event_count=len(events),
            executive_summary=narrative.executive_summary,
            key_findings=narrative.key_findings,
            recommended_actions=narrative.recommended_actions,
            limitations=narrative.limitations, markdown=markdown, path=path,
        )

    @staticmethod
    def _quality_gate(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        safe_events: list[dict[str, Any]] = []
        warnings: list[str] = []
        for original in events:
            if not original.get("sources"):
                warnings.append(f"事件 {original.get('id')} 没有来源，已从报告排除。")
                continue
            event = dict(original)
            sources = event["sources"]
            title = " ".join(str(event.get("canonical_title", "")).lower().split())
            matched = any(
                title in " ".join(str(source.get("title", "")).lower().split())
                or " ".join(str(source.get("title", "")).lower().split()) in title
                or SequenceMatcher(None, title, str(source.get("title", "")).lower()).ratio() >= 0.38
                for source in sources
            )
            if not matched:
                event["canonical_title"] = max(sources, key=lambda source: len(source.get("title", "")))["title"]
                warnings.append(f"事件 {event['id']} 标题与来源语义不一致，报告已回退使用原始来源标题。")
            if event["cluster_confidence"] == "不适用" and event["source_count"] > 1:
                event["cluster_confidence"] = "中等"
                warnings.append(f"事件 {event['id']} 的聚类状态与独立来源数冲突，报告已使用保守状态。")
            if event["value_level"] in {"high_value", "watchlist"} and event.get("evidence_tier") not in {"verified", "corroborated"}:
                event["value_level"] = "candidate"
                event["action_level"] = "谨慎验证"
                warnings.append(f"事件 {event['id']} 未通过事实证据门槛，报告已降级为候选线索。")
            safe_events.append(event)
        return safe_events, warnings

    def resolve_report_path(self, report_id: str) -> Path | None:
        if not report_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in report_id):
            return None
        path = self.settings.report_dir / f"{report_id}.md"
        return path if path.exists() else None

    def _build_narrative(
        self, task: dict[str, Any], run: dict[str, Any], events: list[dict[str, Any]],
    ) -> tuple[ReportNarrative, str]:
        fallback = self._rule_narrative(task, run, events)
        # 全部只是候选线索时，LLM 没有资格扩写“潜力、趋势、合作”等判断。
        if all(event["value_level"] == "candidate" for event in events):
            return fallback, "rules_evidence_gate"
        if self.settings.effective_ai_mode != "openai":
            return fallback, "rules"

        payload = {
            "topic": task["topic"],
            "target_role": task["target_role"],
            "run": {
                "completed_at": run.get("completed_at"),
                "items_collected": run.get("items_collected", 0),
                "candidates_created": run.get("candidates_created", 0),
                "events_created": run.get("events_created", 0),
            },
            "events": [self._event_payload(event) for event in events],
            "required_schema": ReportNarrative.model_json_schema(),
        }
        try:
            client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=1,
            )
            messages = [
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            if self.settings.openai_api_style == "chat_completions":
                response = client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("模型未返回报告内容")
                return self._sanitize_narrative(
                    ReportNarrative.model_validate(json.loads(content)), fallback, events,
                ), "openai"
            response = client.responses.parse(
                model=self.settings.openai_model,
                input=messages,
                text_format=ReportNarrative,
            )
            if response.output_parsed is None:
                raise ValueError("模型未返回结构化报告")
            return self._sanitize_narrative(response.output_parsed, fallback, events), "openai"
        except Exception:
            # 报告生成不能因网关格式或网络失败而中断；降级结果仍只来自真实数据库。
            return fallback, "rules_fallback"

    @staticmethod
    def _sanitize_narrative(
        narrative: ReportNarrative, fallback: ReportNarrative, events: list[dict[str, Any]],
    ) -> ReportNarrative:
        """报告层最后一道动作边界，防止候选线索被包装为投入或合作建议。"""
        forbidden = ("合作", "部署", "投资", "战略投入", "公开传播", "加快投入")
        candidate_titles = {
            event["canonical_title"] for event in events if event["value_level"] == "candidate"
        }
        actions = [
            action for action in narrative.recommended_actions
            if not any(term in action for term in forbidden)
            and not any(title in action for title in candidate_titles)
        ]
        if not actions:
            actions = fallback.recommended_actions
        return narrative.model_copy(update={"recommended_actions": actions})

    @staticmethod
    def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": event["canonical_title"],
            "summary": event["summary"],
            "why_now": event["why_now"],
            "impact": event["impact"],
            "recommended_action": event["recommended_action"],
            "risk": event["risk"],
            "value_score": event["value_score"],
            "value_level": event["value_level"],
            "action_level": event["action_level"],
            "truth_status": event["truth_status"],
            "cluster_confidence": event["cluster_confidence"],
            "growth_percent": event["growth_percent"],
            "source_count": event["source_count"],
            "platform_count": event["platform_count"],
            "sources": [
                {"title": source["title"], "url": source["url"], "source": source["source"]}
                for source in event["sources"][:4]
            ],
        }

    @staticmethod
    def _rule_narrative(
        task: dict[str, Any], run: dict[str, Any], events: list[dict[str, Any]],
    ) -> ReportNarrative:
        high = [event for event in events if event["value_level"] == "high_value"]
        watch = [event for event in events if event["value_level"] == "watchlist"]
        candidates = [event for event in events if event["value_level"] == "candidate"]
        executive = (
            f"本轮发现 {len(high)} 个达到高价值阈值的热点。"
            if high else "本轮没有达到高价值阈值的热点。"
        )
        executive += (
            f"面向{task['target_role']}，当前报告包含 {len(high)} 个高价值热点、"
            f"{len(watch)} 个持续观察事件和 {len(candidates)} 个候选线索。"
        )
        if high:
            executive += f"当前优先事项是“{high[0]['canonical_title']}”，程序价值分 {high[0]['value_score']:.1f}。"
        else:
            executive += "当前不应形成外部趋势判断或资源投入结论。"
        findings = [
            (
                f"{event['canonical_title']}：{event['value_score']:.1f} 分，候选线索；"
                f"覆盖 {event.get('platform_count', 1)} 个平台、{event['source_count']} 个独立发布方，尚不能证明热点成立。"
                if event["value_level"] == "candidate" else
                f"{event['canonical_title']}：{event['value_score']:.1f} 分，{event['action_level']}；{event['why_now']}"
            )
            for event in events[:5]
        ]
        actions = [
            (
                f"谨慎验证“{event['canonical_title']}”：核对原文、补充第二独立发布方并记录下一轮指标。"
                if event["value_level"] == "candidate" else
                f"{event['action_level']}“{event['canonical_title']}”：{event['recommended_action']}"
            )
            for event in events[:3]
        ]
        limitations: list[str] = []
        if any(event["source_count"] <= 1 for event in events):
            limitations.append("部分事件只有一个来源，不能视为已被多个独立信源交叉验证。")
        if any(event["growth_percent"] is None for event in events):
            limitations.append("部分事件缺少跨轮次快照，当前无法证明真实增速。")
        if not high:
            limitations.append("本轮没有事件达到高价值阈值，报告结论以线索整理和持续观察为主。")
        if run.get("warnings"):
            limitations.append(f"本轮存在 {len(run['warnings'])} 个采集或分析警告，详见执行日志。")
        return ReportNarrative(
            executive_summary=executive,
            key_findings=findings,
            recommended_actions=actions,
            limitations=limitations or ["未发现额外方法限制；仍应通过原始链接核对关键事实。"],
        )

    @staticmethod
    def _render_markdown(
        title: str,
        task: dict[str, Any],
        run: dict[str, Any],
        events: list[dict[str, Any]],
        narrative: ReportNarrative,
        generated_at: str,
        report_type: str,
        scope: str,
        diagnostics: dict[str, Any] | None = None,
        deep_analyses: dict[int, DeepAnalysisResult] | None = None,
    ) -> str:
        lines = [
            f"# {title}", "",
            f"> 生成时间：{generated_at[:19].replace('T', ' ')} UTC｜数据运行：`{run['id']}`｜范围：{'仅人工确认' if scope == 'approved_only' else '合格事件优先' if scope == 'qualified' else '全部可见事件'}",
            "", "## 执行摘要", "", narrative.executive_summary, "",
            "## 关键发现", "",
            *[f"- {item}" for item in narrative.key_findings], "",
            "## 建议动作", "",
            *[f"- {item}" for item in narrative.recommended_actions], "",
        ]
        if report_type == "full_analysis":
            lines.extend(["## 事件明细", ""])
            for index, event in enumerate(events, start=1):
                deep = (deep_analyses or {}).get(event["id"])
                source_refs = {source["id"]: f"S{position}" for position, source in enumerate(event["sources"], start=1)}
                if event["value_level"] == "candidate":
                    first_source = event["sources"][0]
                    first_ref = source_refs[first_source["id"]]
                    latest_time = first_source.get("pushed_at") or first_source.get("released_at") or first_source.get("published_at")
                    why_candidate = (
                        f"本轮采集到该信息；最新可验证时间为 {latest_time}。"
                        + (f"同一指标已形成持续增长，较上一轮变化 {event['growth_percent']:.1f}%。" if event.get("growth_label") == "持续增长" and event["growth_percent"] is not None else "当前没有达到持续增长门槛。")
                        + f"覆盖 {event['platform_count']} 个平台、{event['source_count']} 个独立发布方。"
                    )
                    lines.extend([
                        f"### 候选 {index}. {event['canonical_title']}", "",
                        f"- 当前分层：候选线索，{event['value_score']:.1f} 分。",
                        f"- 为什么进入候选：{why_candidate}",
                        f"- 已证实：系统采集到原始来源《{first_source['title']}》。[{first_ref}]",
                        "- 尚未证实：跨平台传播、持续增长和广泛采用。",
                        "- 升级条件：补齐官方或第二独立发布方，并获得至少三轮同指标快照且绝对增量达到门槛；跨平台热点还需两个非转载平台。",
                        "- 当前允许动作：核对原文、持续监控、补充独立来源或进行低成本内部测试。",
                        "- 禁止结论：不得称为已经形成的行业热点，不得据此建议合作、部署或资源投入。",
                        "", "#### 主张级来源", "",
                        *[f"- [{source_refs[source['id']]}] [{source['title']}]({source['url']})（{source['source']}）" for source in event["sources"]],
                        "",
                    ])
                    continue
                lines.extend([
                    f"### {index}. {event['canonical_title']}", "",
                    f"- 程序判断：**{event['action_level']}**｜{event['value_level']}｜{event['value_score']:.1f} 分",
                    f"- 真实性 / 聚类：{event['truth_status']} / {event['cluster_confidence']}",
                    f"- 摘要：{event['summary']}",
                    f"- 为什么现在：{event['why_now']}",
                    f"- 争议：{event['debate']}",
                    f"- 影响：{event['impact']}",
                    f"- 建议：{event['recommended_action']}",
                    f"- 风险：{event['risk']}",
                ])
                if deep:
                    lines.extend([
                        "",
                        f"#### 深层原因分析（{deep.generation_mode}）",
                        "",
                        f"- 爆发判断：**{deep.burst_status}**",
                        *[f"- {item.dimension}：{item.conclusion}（{item.evidence_status}）" for item in deep.cause_analysis],
                        "",
                        "#### 传播与分歧",
                        "",
                        *[f"- 传播｜{item.dimension}：{item.conclusion}（{item.evidence_status}）" for item in deep.propagation_analysis],
                        *[f"- 分歧｜{item.dimension}：{item.conclusion}（{item.evidence_status}）" for item in deep.disagreement_analysis],
                        "",
                        "#### 影响评估",
                        "",
                        "| 影响对象 | 具体影响 | 严重程度 | 恢复周期 | 证据状态 |",
                        "|---|---|---|---|---|",
                        *[
                            f"| {item.affected_party} | {item.concrete_impact} | {item.severity} | {item.recovery_cycle} | {item.evidence_status} |"
                            for item in deep.impact_assessment
                        ],
                        "",
                        "#### 三种条件场景",
                        "",
                    ])
                    for scenario in deep.scenarios:
                        lines.extend([
                            f"- **{scenario.name}**（{scenario.likelihood}；不提供无模型概率）",
                            f"  - 触发：{scenario.trigger}",
                            f"  - 过程：{scenario.development}",
                            f"  - 结果：{scenario.outcome}",
                            f"  - 依据：{scenario.basis}",
                        ])
                    lines.extend([
                        "",
                        "#### 关键观察点",
                        "",
                        *[f"- {item}" for item in deep.observation_points],
                        "",
                        "#### 分角色建议",
                        "",
                        *[f"- **{role}**：{advice}" for role, advice in deep.recommendations.items()],
                        "",
                        "#### 深度分析限制",
                        "",
                        *[f"- {item}" for item in deep.limitations],
                    ])
                lines.extend([
                    "",
                    "#### 主张级来源",
                    "",
                    *[f"- [{source_refs[source['id']]}] [{source['title']}]({source['url']})（{source['source']}）" for source in event["sources"]],
                    "",
                ])
            if not deep_analyses:
                lines.extend(["### 深度分析资格", "", "本轮无事件满足“持续观察或高价值，且至少两个独立发布方”的深度分析条件。", ""])
        candidate_count = int(run.get("candidates_created") or run.get("events_created") or len(events))
        lines.extend([
            "## 限制与未知项", "",
            *[f"- {item}" for item in narrative.limitations], "",
            "## 方法说明", "",
            f"监控主题：{task['topic']}；目标用户：{task['target_role']}。",
            f"本轮从 {run.get('items_collected', 0)} 条原始信息中形成 {candidate_count} 个候选事件。",
            "价值分由相关性、增速、跨平台覆盖、来源强度和关注信号共同计算；LLM 只归纳文字，不修改程序评分、分层或来源。",
        ])
        if diagnostics:
            lines.extend([
                "",
                "### 评分诊断补充",
                "",
                f"- 最新一轮平均价值分：{diagnostics['average_value_score']}；真实 0 分事件：{diagnostics['zero_value_events']}。",
                f"- 单一来源事件：{diagnostics['single_source_events']}/{diagnostics['event_count']}；单平台事件：{diagnostics['single_platform_events']}/{diagnostics['event_count']}。",
                f"- 没有正增长证据：{diagnostics['no_positive_growth_events']}/{diagnostics['event_count']}。",
                "- 历史 0 分来自旧评分字段迁移默认值，现已按已保存指标回填；当前低分主要代表证据不足，不等于采集器完全失效。",
            ])
        return "\n".join(lines)
