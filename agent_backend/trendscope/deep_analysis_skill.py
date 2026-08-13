from __future__ import annotations

import json
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from .config import Settings
from .database import Database


DEEP_ANALYSIS_PROMPT = """
你是 TrendScope 的深度热点分析 Skill。你只能分析输入事件和已保存来源。

规则：
1. 先判断输入是否真的证明“爆发”。growth_percent 为空或不大于 0 时，必须明确写“没有证据证明爆发”，不得虚构触发点。
2. “社会背景、用户情绪、平台算法推动、身份利益冲突”只有原文明确支持时才可写为已验证，否则只能标记合理推断或证据不足。
3. 不得编造受害者、粉丝群体、监管介入、名誉损失、恢复周期或法律后果。
4. 场景用于条件推演，不是事实预测。没有统计模型时 probability_percent 必须为 null，并用 likelihood 表达低置信度相对可能性。
5. evidence_source_ids 只能使用输入提供的 source id；没有来源支撑时必须为空。
6. 每项结论都要给 evidence_status：已验证、合理推断或证据不足。
7. 输出严格符合 JSON Schema，不得包含 Markdown 代码块。
"""


class ReasonFinding(BaseModel):
    dimension: str
    conclusion: str
    evidence_status: Literal["已验证", "合理推断", "证据不足"]
    evidence_source_ids: list[int] = Field(default_factory=list)


class ImpactFinding(BaseModel):
    affected_party: str
    concrete_impact: str
    severity: Literal["高", "中", "低", "未知"]
    recovery_cycle: str
    evidence_status: Literal["已验证", "合理推断", "证据不足"]


class ScenarioFinding(BaseModel):
    name: str
    trigger: str
    development: str
    outcome: str
    likelihood: Literal["相对更可能", "可能", "低置信度"]
    probability_percent: float | None = None
    basis: str


class DeepAnalysisResult(BaseModel):
    event_id: int
    generation_mode: Literal["openai", "rules", "rules_fallback"]
    burst_status: Literal["已证明爆发", "出现升温信号", "未证明爆发"]
    cause_analysis: list[ReasonFinding] = Field(min_length=3, max_length=5)
    propagation_analysis: list[ReasonFinding] = Field(min_length=3, max_length=5)
    disagreement_analysis: list[ReasonFinding] = Field(min_length=2, max_length=5)
    impact_assessment: list[ImpactFinding] = Field(min_length=2, max_length=5)
    scenarios: list[ScenarioFinding] = Field(min_length=3, max_length=3)
    observation_points: list[str]
    recommendations: dict[str, str]
    limitations: list[str]
    citations: list[dict[str, Any]]


class DeepAnalysisSkill:
    """对单个事件做有证据边界的原因、传播、分歧、影响和情景分析。"""

    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def analyze(
        self, event_id: int, audience: str | None = None, horizon_days: int = 7,
        allow_llm: bool = True,
    ) -> DeepAnalysisResult:
        event = self.db.get_event_with_sources(event_id)
        if not event:
            raise KeyError(f"热点事件 {event_id} 不存在")
        fallback = self._rule_result(event, audience, horizon_days)
        if not allow_llm or self.settings.effective_ai_mode != "openai":
            return fallback
        try:
            result = self._analyze_with_llm(event, audience, horizon_days)
            return self._sanitize(result, event)
        except Exception:
            return fallback.model_copy(update={"generation_mode": "rules_fallback"})

    def _analyze_with_llm(self, event: dict[str, Any], audience: str | None, horizon_days: int) -> DeepAnalysisResult:
        source_payload = [{
            "id": source["id"], "source": source["source"], "title": source["title"],
            "published_at": source["published_at"], "event_type": source["event_type"],
            "is_primary_source": bool(source["is_primary_source"]), "excerpt": source["excerpt"],
            "metrics": source["metrics"],
        } for source in event["sources"]]
        payload = {
            "event": {
                "event_id": event["id"], "title": event["canonical_title"], "summary": event["summary"],
                "why_now": event["why_now"], "debate": event["debate"], "impact": event["impact"],
                "risk": event["risk"], "value_score": event["value_score"],
                "value_level": event["value_level"], "growth_percent": event["growth_percent"],
                "platform_count": event["platform_count"], "source_count": event["source_count"],
                "truth_status": event["truth_status"], "cluster_confidence": event["cluster_confidence"],
                "metric_deltas": event["metric_deltas"],
            },
            "sources": source_payload,
            "audience": audience or "产品、研究、媒体与相关决策者",
            "forecast_horizon_days": horizon_days,
            "required_schema": DeepAnalysisResult.model_json_schema(),
        }
        client = OpenAI(
            api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url,
            timeout=self.settings.llm_timeout_seconds, max_retries=1,
        )
        messages = [
            {"role": "system", "content": DEEP_ANALYSIS_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        if self.settings.openai_api_style == "chat_completions":
            response = client.chat.completions.create(
                model=self.settings.openai_model, messages=messages,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("模型未返回深度分析")
            raw = json.loads(content)
            raw["event_id"] = event["id"]
            raw["generation_mode"] = "openai"
            return DeepAnalysisResult.model_validate(raw)
        response = client.responses.parse(
            model=self.settings.openai_model, input=messages, text_format=DeepAnalysisResult,
        )
        if response.output_parsed is None:
            raise ValueError("模型未返回结构化深度分析")
        return response.output_parsed.model_copy(update={"event_id": event["id"], "generation_mode": "openai"})

    @staticmethod
    def _sanitize(result: DeepAnalysisResult, event: dict[str, Any]) -> DeepAnalysisResult:
        allowed_ids = {int(source["id"]) for source in event["sources"]}
        groups = (result.cause_analysis, result.propagation_analysis, result.disagreement_analysis)
        for group in groups:
            for finding in group:
                finding.evidence_source_ids = [item for item in finding.evidence_source_ids if item in allowed_ids]
                if finding.evidence_status == "已验证" and not finding.evidence_source_ids:
                    finding.evidence_status = "证据不足"
        # 当前系统没有预测概率模型，禁止把语言模型估计伪装成统计概率。
        for scenario in result.scenarios:
            scenario.probability_percent = None
        result.citations = [
            {"source_id": source["id"], "title": source["title"], "url": source["url"]}
            for source in event["sources"]
        ]
        if event["growth_percent"] is None or float(event["growth_percent"]) <= 0:
            result.burst_status = "未证明爆发"
        return result

    @staticmethod
    def _rule_result(event: dict[str, Any], audience: str | None, horizon_days: int) -> DeepAnalysisResult:
        growth = event["growth_percent"]
        burst_status: Literal["已证明爆发", "出现升温信号", "未证明爆发"]
        if growth is not None and float(growth) >= 100 and event["platform_count"] >= 2:
            burst_status = "已证明爆发"
        elif growth is not None and float(growth) > 0:
            burst_status = "出现升温信号"
        else:
            burst_status = "未证明爆发"
        source_ids = [int(source["id"]) for source in event["sources"]]
        verified_ids = source_ids[:1]
        target = audience or event["impact"] or "相关产品、研究与内容团队"
        return DeepAnalysisResult(
            event_id=event["id"], generation_mode="rules", burst_status=burst_status,
            cause_analysis=[
                ReasonFinding(
                    dimension="直接触发点",
                    conclusion=event["why_now"] if burst_status != "未证明爆发" else "当前数据没有证明该事件已经爆发；只能确认系统在本轮发现了该信息。",
                    evidence_status="已验证" if burst_status != "未证明爆发" else "证据不足",
                    evidence_source_ids=verified_ids if burst_status != "未证明爆发" else [],
                ),
                ReasonFinding(dimension="社会或行业背景", conclusion="现有来源不足以证明更广泛的行业背景是直接原因。", evidence_status="证据不足"),
                ReasonFinding(dimension="用户心理或情绪", conclusion="数据源未提供可验证的情绪样本，不能推断公众情绪。", evidence_status="证据不足"),
            ],
            propagation_analysis=[
                ReasonFinding(
                    dimension="跨平台扩散", conclusion=f"当前覆盖 {event['platform_count']} 个平台、{event['source_count']} 条来源。",
                    evidence_status="已验证", evidence_source_ids=source_ids,
                ),
                ReasonFinding(dimension="平台算法推动", conclusion="系统没有平台推荐曝光数据，无法判断算法是否推动传播。", evidence_status="证据不足"),
                ReasonFinding(dimension="参与成本与话题特性", conclusion="缺少用户评论语料和传播链路数据，无法可靠判断。", evidence_status="证据不足"),
            ],
            disagreement_analysis=[
                ReasonFinding(
                    dimension="已观察争议", conclusion=event["debate"],
                    evidence_status="合理推断" if event["debate"] and "信息不足" not in event["debate"] else "证据不足",
                    evidence_source_ids=verified_ids if event["debate"] and "信息不足" not in event["debate"] else [],
                ),
                ReasonFinding(dimension="价值观或身份利益", conclusion="没有足够的群体身份、立场和利益关系数据。", evidence_status="证据不足"),
            ],
            impact_assessment=[
                ImpactFinding(
                    affected_party=target, concrete_impact=event["impact"],
                    severity="未知", recovery_cycle="无法从当前来源判断", evidence_status="合理推断",
                ),
                ImpactFinding(
                    affected_party="相关机构或项目", concrete_impact="可能获得关注，也可能因未经验证的传播产生误判。",
                    severity="未知", recovery_cycle="需观察后续信号", evidence_status="合理推断",
                ),
            ],
            scenarios=[
                ScenarioFinding(
                    name="场景 A：出现权威确认", trigger="官方公告、发布说明或第二个独立信源出现",
                    development="真实性和跨源证据增强，价值分可能上升", outcome="进入持续观察或高价值层",
                    likelihood="可能", probability_percent=None, basis="条件推演；当前没有统计概率模型",
                ),
                ScenarioFinding(
                    name="场景 B：讨论继续但证据不增加", trigger="社区转载或互动增加，但没有新的一手材料",
                    development="关注信号上升，事实可信度保持不变", outcome="维持观察，不升级为确定热点",
                    likelihood="相对更可能" if event["source_count"] <= 1 else "可能", probability_percent=None,
                    basis="当前来源数量和真实性状态",
                ),
                ScenarioFinding(
                    name="场景 C：热度衰减", trigger=f"未来 {horizon_days} 天没有新增来源或指标增长",
                    development="事件被新信息替代", outcome="降级为历史线索",
                    likelihood="可能", probability_percent=None, basis="条件推演；需要后续快照验证",
                ),
            ],
            observation_points=[
                "是否出现官方公告或第二个独立信源？",
                "下一轮星标、评论、新闻数量或搜索指标是否真实增长？",
                "不同来源是否只是转载同一篇内容？",
                "是否出现可回溯的反方证据或纠错信息？",
            ],
            recommendations={
                "媒体或内容团队": "先引用原始来源并标注未知项，不把单一线索写成确定趋势。",
                "相关机构或项目方": "补充可核验事实、时间线和原始材料，避免只给宣传性结论。",
                "产品与研究团队": event["recommended_action"],
                "普通读者": "优先查看原文和时间字段，区分项目存在、近期活跃与真正形成热点。",
            },
            limitations=[
                "没有平台曝光、转发网络和完整评论语料，无法证明算法推动或群体情绪。",
                "没有预测模型，三个场景不提供伪精确概率。",
                "影响严重程度和恢复周期只有来源明确提供时才能下结论。",
            ],
            citations=[{"source_id": source["id"], "title": source["title"], "url": source["url"]} for source in event["sources"]],
        )
