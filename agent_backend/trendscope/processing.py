from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from datetime import timedelta
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .database import Database
from .models import AnalysisClaim, EventAnalysis, EventCandidate, EventSignature, MonitoringTask, SourceItem


STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "new", "open", "using", "into",
    "ai", "artificial", "intelligence", "generative", "agent", "agents", "project", "projects",
    "发布", "推出", "支持", "一个", "功能", "工具", "项目", "最新", "近期", "活跃",
}

LOW_QUALITY_GITHUB_TERMS = {
    3: {"bypass", "otp bot", "telegram bot", "whatsapp", "payment demo", "tutorial", "template", "miniapp"},
    4: {"flutter", "navigation", "tutorial", "course", "template", "demo app"},
}

ENTITY_ALIASES = {
    "openai": ("openai", "chatgpt"),
    "gpt5": ("gpt 5", "gpt5", "gpt-5"),
    "google_gemini": ("google gemini", "gemini"),
    "anthropic_claude": ("anthropic", "claude"),
    "deepseek": ("deepseek", "深度求索"),
    "cursor": ("cursor",),
    "github_copilot": ("github copilot", "copilot"),
    "nvidia": ("nvidia", "英伟达"),
    "qwen": ("qwen", "通义千问"),
    "llama": ("llama",),
}
ACTION_ALIASES = {
    "release": ("release", "launch", "推出", "发布", "上线", "开源"),
    "funding": ("funding", "raises", "融资", "募资"),
    "security": ("security", "vulnerability", "漏洞", "安全"),
    "outage": ("outage", "downtime", "宕机", "中断"),
    "regulation": ("regulation", "regulator", "监管", "法规"),
    "acquisition": ("acquisition", "acquires", "收购", "并购"),
}

EVIDENCE_ROLE_BY_SOURCE = {
    "google_trends": "attention_signal",
    "hacker_news": "attention_signal",
    "devto": "opinion",
    "v2ex": "opinion",
    "bilibili": "attention_signal",
}

PUBLISHER_TYPE_BY_SOURCE = {
    "github": "project_owner", "arxiv": "research_authors", "google_news": "media",
    "hacker_news": "community", "google_trends": "search_platform", "rss": "publisher",
    "devto": "community", "v2ex": "community", "bilibili": "content_platform",
    "chinanews": "media", "cctv_news": "media",
}


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    clean_query = [(key, value) for key, value in parse_qsl(parts.query) if not key.lower().startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(clean_query), ""))


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value.lower()).strip()


def title_tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if len(token) > 1 and token not in STOPWORDS}


def source_identity(item: SourceItem) -> str:
    """近似识别独立发布方；Google News 的不同媒体不能被聚合域名压成一个来源。"""
    hostname = (urlsplit(item.url).hostname or "").lower().removeprefix("www.")
    if item.original_publisher_id:
        return item.original_publisher_id
    if item.publisher_id:
        return item.publisher_id
    if item.source == "google_news" and item.author:
        return f"publisher:{normalize_text(item.author)}"
    if hostname:
        return f"domain:{hostname}"
    return f"source:{item.source}:{item.external_id}"


def independent_source_count(items: list[SourceItem]) -> int:
    return len({source_identity(item) for item in items if item.is_independent and not item.is_repost})


def annotate_evidence(item: SourceItem) -> SourceItem:
    """规范化发布链和证据用途；平台名不再冒充发布方。"""
    hostname = (urlsplit(item.url).hostname or "").lower().removeprefix("www.")
    publisher_name = item.author if item.source == "google_news" and item.author else hostname or item.author or item.source
    publisher_id = f"publisher:{normalize_text(publisher_name)}"
    role = EVIDENCE_ROLE_BY_SOURCE.get(item.source)
    if not role:
        if item.source == "github":
            role = "primary_fact" if item.event_type in {"repository_created", "release_published"} else "attention_signal"
        elif item.source in {"google_news", "chinanews", "cctv_news"}:
            role = "independent_confirm"
        elif item.is_primary_source:
            role = "primary_fact"
        elif item.source in {"google_news", "chinanews", "cctv_news", "rss"}:
            role = "independent_confirm"
        else:
            role = "opinion"
    return item.model_copy(update={
        "evidence_role": role,
        "publisher_id": publisher_id,
        "publisher_type": PUBLISHER_TYPE_BY_SOURCE.get(item.source, "unknown"),
        "original_publisher_id": item.original_publisher_id or publisher_id,
        "original_url": item.original_url or item.url,
        "is_independent": not item.is_repost,
    })


def identify_repost_relationships(items: list[SourceItem]) -> list[SourceItem]:
    """只对高度近似新闻标题标转载，避免把一般主题相似误当成同一发布链。"""
    news_roles = {"independent_confirm", "primary_fact"}
    ordered = sorted(items, key=lambda item: item.published_at)
    originals: list[SourceItem] = []
    result_by_key: dict[tuple[str, str], SourceItem] = {}
    for item in ordered:
        matched = next((
            original for original in originals
            if item.evidence_role in news_roles
            and original.evidence_role in news_roles
            and source_identity(item) != source_identity(original)
            and SequenceMatcher(None, normalize_text(item.title), normalize_text(original.title)).ratio() >= 0.94
        ), None)
        if matched:
            item = item.model_copy(update={
                "original_publisher_id": matched.original_publisher_id or matched.publisher_id,
                "original_url": matched.original_url or matched.url,
                "is_independent": False,
                "is_repost": True,
                "evidence_role": "repost",
            })
        else:
            originals.append(item)
        result_by_key[(item.source, item.external_id)] = item
    return [result_by_key[(item.source, item.external_id)] for item in items]


def normalize_entity_aliases(value: str) -> list[str]:
    normalized = normalize_text(value)
    found = [key for key, aliases in ENTITY_ALIASES.items() if any(normalize_text(alias) in normalized for alias in aliases)]
    generic_named = {
        "ai", "agent", "agents", "release", "released", "version", "update", "updated",
        "new", "official", "github", "paper", "study", "research", "team", "tool", "system",
        "model", "models", "using", "with", "from", "for", "the", "and",
    }
    named = [
        token.lower() for token in re.findall(r"\b[A-Z][A-Za-z0-9.-]{2,}\b", value)
        if token.lower() not in generic_named
    ]
    return sorted(set(found + named))


def extract_event_signature(item: SourceItem) -> EventSignature:
    entities = normalize_entity_aliases(f"{item.title} {item.content[:500]}")
    actions = sorted(action_keys(item))
    identifiers: list[str] = []
    path = [part for part in urlsplit(item.url).path.split("/") if part]
    if item.source == "github" and len(path) >= 2:
        identifiers.append(f"github:{path[0].lower()}/{path[1].lower()}")
    if "arxiv.org" in (urlsplit(item.url).hostname or "") and path:
        identifiers.append(f"arxiv:{path[-1].lower()}")
    tokens = [token for token in title_tokens(item.title) if not token.startswith("named:")]
    object_text = " ".join(sorted(tokens)[:6]) or None
    return EventSignature(
        entities=entities, action=actions[0] if actions else "unknown", object=object_text,
        event_time=item.released_at or item.created_at or item.published_at,
        aliases=entities, identifiers=identifiers,
    )


def compare_event_signatures(left: EventSignature, right: EventSignature) -> tuple[bool, float, list[str]]:
    reasons: list[str] = []
    if set(left.identifiers) & set(right.identifiers):
        return True, 1.0, ["共享确定性标识符"]
    left_namespaces = {identifier.split(":", 1)[0] for identifier in left.identifiers}
    right_namespaces = {identifier.split(":", 1)[0] for identifier in right.identifiers}
    if left.identifiers and right.identifiers and left_namespaces & right_namespaces:
        return False, 0.0, ["同类确定性标识符不同"]
    common_entities = set(left.entities) & set(right.entities)
    if not common_entities:
        return False, 0.0, ["缺少共同核心实体"]
    reasons.append(f"共同实体：{'、'.join(sorted(common_entities))}")
    if left.action != "unknown" and right.action != "unknown" and left.action != right.action:
        return False, 0.25, reasons + ["动作不一致"]
    if left.event_time and right.event_time and abs((left.event_time - right.event_time).total_seconds()) > 14 * 86400:
        return False, 0.2, reasons + ["事件时间超出窗口"]
    object_ratio = SequenceMatcher(None, left.object or "", right.object or "").ratio()
    confidence = 0.65 + min(0.2, object_ratio * 0.2) + (0.1 if left.action == right.action != "unknown" else 0)
    if left.action == "unknown" or right.action == "unknown":
        return object_ratio >= 0.8, round(confidence, 2), reasons + ["缺少明确动作，要求对象高度一致"]
    return confidence >= 0.7, round(confidence, 2), reasons + (["动作一致"] if left.action == right.action != "unknown" else [])


def title_matches_sources(title: str, items: list[SourceItem]) -> bool:
    """阻止 LLM 标题和真实来源错配；中英文分别用词项与字符串相似度校验。"""
    normalized = normalize_text(title)
    if not normalized or not items:
        return False
    proposed_tokens = title_tokens(title)
    for item in items:
        source_title = normalize_text(item.title)
        if normalized in source_title or source_title in normalized:
            return True
        source_tokens = title_tokens(item.title)
        if proposed_tokens and source_tokens:
            overlap = len(proposed_tokens & source_tokens) / min(len(proposed_tokens), len(source_tokens))
            if overlap >= 0.4:
                return True
        if SequenceMatcher(None, normalized, source_title).ratio() >= 0.38:
            return True
    return False


def entity_keys(item: SourceItem) -> set[str]:
    normalized = normalize_text(item.title)
    entities = {
        key for key, aliases in ENTITY_ALIASES.items()
        if any(normalize_text(alias) in normalized for alias in aliases)
    }
    generic_named = {
        "how", "why", "what", "from", "using", "two", "one", "new", "giving",
        "ai", "agent", "agents", "artificial", "intelligence", "model", "models",
        "multi", "modal", "multimodal", "benchmark", "system", "systems",
    }
    entities.update(
        f"named:{token.lower()}"
        for token in re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", item.title)
        if token.lower() not in generic_named
    )
    return entities


def action_keys(item: SourceItem) -> set[str]:
    normalized = normalize_text(item.title)
    return {
        key for key, aliases in ACTION_ALIASES.items()
        if any(normalize_text(alias) in normalized for alias in aliases)
    }


def prepare_items(items: list[SourceItem], task: MonitoringTask) -> tuple[list[SourceItem], dict[str, int]]:
    kept: list[SourceItem] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    excluded = [word.lower() for word in task.excluded_keywords]
    counts = Counter()
    for item in items:
        if not item.title or not item.url:
            counts["invalid"] += 1
            continue
        haystack = f"{item.title} {item.content}".lower()
        if any(word in haystack for word in excluded):
            counts["excluded"] += 1
            continue
        url = canonical_url(item.url)
        digest = hashlib.sha256(f"{normalize_text(item.title)}|{url}".encode()).hexdigest()
        if url in seen_urls or digest in seen_hashes:
            counts["duplicate"] += 1
            continue
        item = annotate_evidence(item.model_copy(update={"url": url, "content_hash": digest}))
        seen_urls.add(url)
        seen_hashes.add(digest)
        kept.append(item)
    return identify_repost_relationships(kept), dict(counts)


def relevance_score(item: SourceItem, task: MonitoringTask) -> float:
    haystack = normalize_text(f"{item.title} {item.content}")
    matches = sum(1 for keyword in task.keywords if normalize_text(keyword) in haystack)
    title_matches = sum(1 for keyword in task.keywords if normalize_text(keyword) in normalize_text(item.title))
    score = min(100.0, matches * 18 + title_matches * 20)
    if item.source == "github" and (item.metrics.stars or 0) >= 100:
        score += 5
    if item.is_primary_source:
        score += 8
    return min(100.0, score)


def passes_source_gate(item: SourceItem, score: float, task: MonitoringTask) -> bool:
    """金融和生物的 GitHub 只作补充信号，禁止单关键词描述命中直接入榜。"""
    normalized_title = normalize_text(item.title)
    normalized_body = normalize_text(item.content)
    title_matches = sum(1 for keyword in task.keywords if normalize_text(keyword) in normalized_title)
    body_matches = sum(1 for keyword in task.keywords if normalize_text(keyword) in normalized_body)
    if item.source in {"rss", "google_news", "chinanews", "cctv_news", "devto", "v2ex"}:
        # 只在正文角落出现一次宽泛关键词，不足以证明文章的核心事件属于监控主题。
        if title_matches == 0 and body_matches < 2:
            return False
    # 社区视频必须能识别主体或事件动作；长串关键词标题不再进入候选池。
    if item.source == "bilibili":
        signature = extract_event_signature(item)
        if score < 40 or signature.action == "unknown" or not signature.entities:
            return False
        if len(item.title) > 72 and signature.action == "unknown":
            return False
    if item.source != "github" or task.id not in {3, 4}:
        return score >= 20
    title = normalize_text(item.title)
    haystack = normalize_text(f"{item.title} {item.content}")
    if any(normalize_text(term) in haystack for term in LOW_QUALITY_GITHUB_TERMS[task.id]):
        return False
    title_matches = sum(1 for keyword in task.keywords if normalize_text(keyword) in title)
    total_matches = sum(1 for keyword in task.keywords if normalize_text(keyword) in haystack)
    if title_matches == 0 and total_matches < 2:
        return False
    return score >= 40


def attention_signal(item: SourceItem) -> float:
    metrics = item.metrics
    if item.source == "hacker_news":
        return float((metrics.score or 0) + 1.8 * (metrics.comments or 0))
    if item.source == "github":
        return 12.0 * math.log1p(metrics.stars or 0) + 4.0 * math.log1p(metrics.forks or 0)
    if item.source == "google_trends":
        return max(8.0, float(metrics.score or 0) ** 0.5)
    if item.source == "google_news":
        return 10.0
    if item.source in {"chinanews", "cctv_news"}:
        return 12.0
    if item.source == "devto":
        return 3.0 * math.log1p(item.metrics.score or 0) + 4.0 * math.log1p(item.metrics.comments or 0)
    if item.source == "v2ex":
        return 5.0 * math.log1p(item.metrics.comments or 0)
    if item.source == "bilibili":
        return 7.0 * math.log1p(item.metrics.score or 0) + 3.0 * math.log1p(item.metrics.comments or 0)
    if item.source == "arxiv":
        return 9.0
    return 8.0


def stable_event_key(items: list[SourceItem], title: str) -> str:
    """优先使用稳定实体身份，避免标题改写导致跨轮次断裂。"""
    github = next((item for item in items if item.source == "github"), None)
    if github:
        parts = [part for part in urlsplit(github.url).path.split("/") if part]
        repo = "/".join(parts[:2]).lower() if len(parts) >= 2 else normalize_text(github.title)
        identity = f"github|{repo}|{github.event_type or 'repository_updated'}"
    else:
        primary = next((item for item in items if item.is_primary_source), items[0])
        identity = f"{primary.source}|{canonical_url(primary.url)}|{primary.event_type or 'news_published'}"
    return hashlib.sha1(identity.encode()).hexdigest()[:16]


def candidate_truth_status(candidate: EventCandidate) -> str:
    primary_sources = sum(item.evidence_role == "primary_fact" for item in candidate.items)
    independent_confirms = len({
        source_identity(item) for item in candidate.items
        if item.evidence_role == "independent_confirm" and item.is_independent and not item.is_repost
    })
    if primary_sources >= 1 and independent_confirms >= 1:
        return "较高"
    if primary_sources >= 1 or independent_confirms >= 2:
        return "中等"
    return "信息不足"


def evidence_tier(candidate: EventCandidate) -> str:
    has_primary = any(item.evidence_role == "primary_fact" for item in candidate.items)
    independent = len({source_identity(item) for item in candidate.items if item.evidence_role == "independent_confirm" and item.is_independent and not item.is_repost})
    if has_primary and independent >= 1:
        return "verified"
    if independent >= 2:
        return "corroborated"
    if has_primary:
        return "primary_only"
    if independent == 1:
        return "single_source"
    return "unverified"


def evidence_grade(candidate: EventCandidate) -> str:
    """离散证据等级；未经人工标注集校准前不展示伪精确百分数。"""
    tier = evidence_tier(candidate)
    return {
        "verified": "A",
        "corroborated": "B",
        "primary_only": "C",
        "single_source": "C",
        "unverified": "D" if any(item.evidence_role in {"adoption_signal", "attention_signal", "opinion"} for item in candidate.items) else "U",
    }[tier]


def evidence_confidence_score(candidate: EventCandidate) -> float:
    """仅保留兼容字段，不再作为用户可见测量值。"""
    return 0.0


def candidate_cluster_confidence(candidate: EventCandidate) -> str:
    if candidate.source_count <= 1:
        return "不适用"
    if candidate.source_count >= 3 and candidate.platform_count >= 2:
        return "较高"
    return "中等"


def classify_content_type(candidate: EventCandidate) -> str:
    types = {item.event_type for item in candidate.items}
    if "release_published" in types:
        return "产品发布"
    if "repository_created" in types:
        return "开源新项目"
    if "repository_updated" in types:
        return "持续活跃项目"
    if "paper_published" in types:
        return "研究论文"
    if "video_published" in types:
        return "视频传播"
    if any(item.is_primary_source and item.source == "rss" for item in candidate.items):
        return "权威公告"
    if candidate.platform_count >= 2:
        return "行业事件"
    if any(item.source in {"hacker_news", "google_trends"} for item in candidate.items):
        return "社区讨论"
    return "低置信度线索"


def event_gate(candidate: EventCandidate) -> tuple[bool, str]:
    """第一关：只有明确主体、动作、对象和时间的事件才进入热点候选。"""
    types = {item.event_type for item in candidate.items}
    explicit_types = {"repository_created", "release_published", "paper_published"}
    if types & explicit_types:
        return True, "已识别明确的创建、发布或研究事件"
    if candidate.event_signature.action != "unknown" and candidate.event_signature.entities:
        return True, f"已识别主体与动作：{candidate.event_signature.action}"
    if "repository_updated" in types:
        return False, "仅检测到普通仓库 push，未检测到 Release、重大功能发布或公告"
    if "video_published" in types:
        return False, "只有内容传播记录，尚未抽取出可核验事件动作"
    return False, "未抽取出明确的主体、动作、对象和事件时间"


def source_authority(candidate: EventCandidate) -> float:
    """来源权威性与主张适配度，不再用来源数量冒充质量。"""
    values = []
    for item in candidate.items:
        if item.evidence_role == "primary_fact":
            values.append(100.0)
        elif item.evidence_role == "independent_confirm":
            values.append(75.0 if item.source in {"chinanews", "cctv_news", "rss"} else 65.0)
        elif item.evidence_role == "adoption_signal":
            values.append(45.0)
        elif item.evidence_role == "attention_signal":
            values.append(30.0)
        elif item.evidence_role == "opinion":
            values.append(20.0)
        else:
            values.append(0.0)
    return max(values, default=0.0)


def explicit_novelty(candidate: EventCandidate) -> float:
    """普通 push 不具有新颖性；只认可明确事件的首次发生时间。"""
    eligible = [
        item for item in candidate.items
        if item.event_type in {"repository_created", "release_published", "paper_published", "news_published"}
        and item.event_type != "repository_updated"
    ]
    if not eligible:
        return 0.0
    newest = max(item.released_at or item.created_at or item.published_at for item in eligible)
    age_hours = max(0.0, (max(item.collected_at for item in candidate.items) - newest).total_seconds() / 3600)
    return 100.0 if age_hours <= 24 else 70.0 if age_hours <= 72 else 35.0 if age_hours <= 168 else 0.0


def decision_plan(candidate: EventCandidate, task: MonitoringTask) -> tuple[str, str, str, list[str], list[str]]:
    kind = classify_content_type(candidate)
    plans = {
        "产品发布": ("产品经理", "24 小时内", ["核对官方发布说明与变更日志", "与我方产品能力清单做功能重叠分析", "安排 30 分钟低成本试用并记录差异"]),
        "开源新项目": ("技术产品经理", "下一工作日", ["检查 README、Release、许可证与维护者活跃度", "验证是否可集成及是否替代现有能力", "下一轮记录 stars、forks、contributors 的绝对增量"]),
        "研究论文": ("技术研究员", "3 个工作日内", ["核对原论文、作者机构和实验设置", "检查是否有公开代码、数据与独立复现", "判断是否值得安排最小技术复现实验"]),
        "权威公告": ("竞争情报分析师", "24 小时内", ["定位正式公告与生效时间", "识别受影响产品、客户和地区", "形成一页影响清单并交产品负责人确认"]),
        "行业事件": ("竞争情报分析师", "下一工作日", ["核对核心事实与独立发布链", "分析对产品路线和竞争格局的具体影响", "明确是否升级为产品评估或风险预警"]),
    }
    owner, deadline, tasks = plans.get(kind, ("竞争情报分析师", "下一工作日", ["核对核心事实", "寻找第二独立来源", "下一轮获取同口径指标快照"]))
    fact_gate_passed = candidate.evidence_grade in {"A", "B", "C"}
    priority = "未评估" if candidate.event_gate_passed else "不进入决策"
    if not candidate.event_gate_passed:
        tasks = ["归入资讯池，不进入热点榜", "等待出现明确 Release、公告或其他事件动作", "如持续观察，下一轮只记录可比较的增量指标"]
    elif not fact_gate_passed:
        tasks = ["暂不进入业务决策", "定位官方原文或事件主体的一手说明", "获得第二独立来源后重新评估"]
    upgrades = [
        "出现明确产品发布、融资、监管、漏洞或研究事件",
        "核心事实获得一手材料或第二独立来源支持",
        "同一指标连续至少三轮正增长且超过自身历史基线",
    ]
    return priority, owner, deadline, tasks, upgrades


def finalize_business_decision(candidate: EventCandidate, analysis: EventAnalysis) -> EventCandidate:
    """只有业务影响链完整时才输出优先级；否则保留“未评估”。"""
    required = [
        analysis.affected_product, analysis.affected_user, analysis.impact_mechanism,
        analysis.urgency_reason, analysis.cost_of_inaction, analysis.recommended_owner,
        analysis.minimum_action, analysis.deadline_reason,
    ]
    if not candidate.event_gate_passed:
        candidate.decision_priority = "不进入决策"
        candidate.current_action = "忽略"
        return candidate
    if candidate.evidence_grade not in {"A", "B", "C"}:
        candidate.decision_priority = "未评估"
        candidate.current_action = "补证"
        return candidate
    if not all(value and value.strip() for value in required):
        candidate.decision_priority = "未评估"
        candidate.current_action = "技术初筛" if candidate.content_type == "研究论文" else "业务评估"
        return candidate
    urgency = (analysis.urgency_reason or "").lower()
    candidate.decision_priority = "紧急" if any(term in urgency for term in ("立即", "24 小时", "24小时", "critical", "immediate")) else "高" if candidate.event_signature.action in {"security", "regulation", "outage"} else "中"
    candidate.current_action = "立即行动" if candidate.decision_priority in {"紧急", "高"} else "观察"
    candidate.decision_owner = analysis.recommended_owner or candidate.decision_owner
    candidate.decision_tasks = [analysis.minimum_action or candidate.decision_tasks[0]]
    return candidate


def score_business_value(candidate: EventCandidate) -> tuple[float, dict]:
    if not candidate.event_gate_passed or candidate.evidence_grade not in {"A", "B", "C"}:
        return 0.0, {}
    kind = classify_content_type(candidate)
    impact_raw = 90.0 if candidate.event_signature.action in {"security", "regulation", "acquisition"} else 75.0 if kind in {"产品发布", "权威公告", "行业事件"} else 55.0
    urgency_raw = 100.0 if candidate.event_signature.action in {"security", "outage", "regulation"} else 70.0 if kind in {"产品发布", "权威公告"} else 40.0
    actionability_raw = 90.0 if kind in {"产品发布", "权威公告", "开源新项目"} else 65.0 if kind == "研究论文" else 50.0
    specs = {
        "strategic_relevance": (30, max(0.0, min(100.0, candidate.relevance_score)), "与目标角色和监控主题的关系"),
        "potential_impact": (25, impact_raw, f"事件类型：{kind}"),
        "urgency": (20, urgency_raw, f"事件动作：{candidate.event_signature.action}"),
        "actionability": (15, actionability_raw, "能否转化为明确的核验、试用或风险任务"),
        "information_novelty": (10, explicit_novelty(candidate), "基于明确发布、论文、公告或创建时间；普通 push 不计分"),
        "source_authority": (0, source_authority(candidate), "只表达来源权威性和主张适配度，不因来源数量重复加分"),
        "adoption_growth": (
            0,
            max(0.0, min(100.0, float(candidate.metric_deltas.get("growth_evidence", {}).get("absolute_delta", 0)) * 5))
            if candidate.metric_deltas.get("growth_evidence", {}).get("metric") == "github_stars" else 0.0,
            "只使用跨轮次绝对增量；累计 stars、forks 不计为当前采用趋势",
        ),
    }
    breakdown = {
        name: {
            "weight": weight,
            "raw_value": None if name == "growth" and candidate.growth_percent is None else round(raw, 1),
            "contribution": round(raw * weight / 100.0, 1),
            "reason": reason,
        }
        for name, (weight, raw, reason) in specs.items()
    }
    return round(sum(item["contribution"] for item in breakdown.values()), 1), breakdown


def score_candidate(candidate: EventCandidate) -> tuple[float, dict]:
    return score_business_value(candidate)


def determine_event_state(candidate: EventCandidate) -> str:
    tier = evidence_tier(candidate)
    positive_growth = candidate.growth_label == "持续增长"
    cross_platform = candidate.platform_count >= 2 and candidate.source_count >= 2
    if tier in {"verified", "corroborated"} and positive_growth and cross_platform:
        return "跨平台热点"
    if tier in {"verified", "corroborated"} and positive_growth:
        return "升温事件"
    if tier in {"verified", "corroborated"}:
        return "已证实事件"
    if tier in {"primary_only", "single_source"}:
        return "单一来源线索"
    return "未核验线索"


def classify_candidate(candidate: EventCandidate) -> str:
    if candidate.value_score >= 70:
        return "high_value"
    if candidate.value_score >= 45:
        return "watchlist"
    return "candidate"


def apply_program_judgement(candidate: EventCandidate, task: MonitoringTask | None = None) -> EventCandidate:
    candidate.event_gate_passed, candidate.event_gate_reason = event_gate(candidate)
    candidate.evidence_tier = evidence_tier(candidate)
    candidate.evidence_confidence = evidence_confidence_score(candidate)
    candidate.evidence_grade = evidence_grade(candidate)
    score, breakdown = score_candidate(candidate)
    candidate.value_score = score
    candidate.event_state = determine_event_state(candidate)
    evidence_qualified = candidate.evidence_tier in {"verified", "corroborated"}
    trend_qualified = candidate.growth_label == "持续增长"
    spread_qualified = candidate.platform_count >= 2 and candidate.source_count >= 2
    candidate.value_level = (
        "high_value" if score >= 70 and evidence_qualified and trend_qualified and spread_qualified
        else "watchlist" if candidate.event_gate_passed and score >= 45 and evidence_qualified else "candidate"
    )
    candidate.truth_status = candidate_truth_status(candidate)
    candidate.cluster_confidence = candidate_cluster_confidence(candidate)
    candidate.hotspot_confidence = (
        "较高" if candidate.value_level == "high_value" and candidate.platform_count >= 2
        else "待观察" if candidate.value_level == "watchlist" else "证据不足"
    )
    candidate.content_type = classify_content_type(candidate) if candidate.event_gate_passed else "资讯线索"
    candidate.score_breakdown = breakdown
    candidate.decision_priority, candidate.decision_owner, candidate.decision_deadline, candidate.decision_tasks, candidate.upgrade_conditions = decision_plan(candidate, task or MonitoringTask())
    candidate.current_action = "忽略" if not candidate.event_gate_passed else "补证" if candidate.evidence_grade not in {"A", "B", "C"} else "技术初筛" if candidate.content_type == "研究论文" else "业务评估"
    if not candidate.event_gate_passed:
        candidate.event_state = "资讯线索"
        candidate.hotspot_confidence = "证据不足"
    return candidate


def _similar(left: SourceItem, right: SourceItem) -> bool:
    if canonical_url(left.url) == canonical_url(right.url):
        return True
    if left.source != right.source:
        same, confidence, _ = compare_event_signatures(extract_event_signature(left), extract_event_signature(right))
        return same and confidence >= 0.7

    left_tokens, right_tokens = title_tokens(left.title), title_tokens(right.title)
    shared = len(left_tokens & right_tokens)
    if left_tokens and right_tokens:
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        if jaccard >= 0.42:
            return True
        overlap = shared / min(len(left_tokens), len(right_tokens))
    ratio = SequenceMatcher(None, normalize_text(left.title), normalize_text(right.title)).ratio()
    return ratio >= 0.64


def _balanced_candidates(candidates: list[EventCandidate], limit: int = 20) -> list[EventCandidate]:
    """防止 GitHub 等高互动单一来源垄断候选位，保留真实的跨源发现能力。"""
    ordered = sorted(candidates, key=lambda item: (item.platform_count, item.attention_signal), reverse=True)
    selected: list[EventCandidate] = []
    selected_ids: set[str] = set()

    # 跨平台事件最先入选，因为它们更接近“热点”而非单条资讯。
    for candidate in ordered:
        if candidate.platform_count >= 2 and len(selected) < limit:
            selected.append(candidate)
            selected_ids.add(candidate.candidate_id)

    quotas = {
        "rss": 6,
        "google_news": 6,
        "github": 6,
        "hacker_news": 3,
        "google_trends": 2,
        "arxiv": 4,
        "devto": 3,
        "v2ex": 3,
        "bilibili": 3,
        "chinanews": 4,
        "cctv_news": 4,
    }
    counts = Counter()
    source_order = [
        "rss", "google_news", "arxiv", "github", "hacker_news",
        "chinanews", "cctv_news", "devto", "v2ex", "bilibili", "google_trends",
    ]
    buckets = {
        source: [
            candidate for candidate in ordered
            if candidate.candidate_id not in selected_ids and candidate.items[0].source == source
        ]
        for source in source_order
    }
    made_progress = True
    while len(selected) < limit and made_progress:
        made_progress = False
        for source in source_order:
            if len(selected) >= limit or counts[source] >= quotas[source] or not buckets[source]:
                continue
            candidate = buckets[source].pop(0)
            if candidate.candidate_id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(candidate.candidate_id)
            counts[source] += 1
            made_progress = True

    for candidate in ordered:
        if candidate.candidate_id not in selected_ids and len(selected) < limit:
            selected.append(candidate)
            selected_ids.add(candidate.candidate_id)
    return selected


def _cluster_groups(items: list[SourceItem], task: MonitoringTask) -> tuple[list[list[tuple[SourceItem, float]]], int]:
    scored = [(item, relevance_score(item, task)) for item in items]
    relevant = [(item, score) for item, score in scored if passes_source_gate(item, score, task)]
    groups: list[list[tuple[SourceItem, float]]] = []
    for item, score in sorted(relevant, key=lambda pair: attention_signal(pair[0]), reverse=True):
        match = next((group for group in groups if any(_similar(item, other) for other, _ in group)), None)
        if match is None:
            groups.append([(item, score)])
        else:
            match.append((item, score))
    return groups, len(relevant)


def actual_cluster_merge_count(items: list[SourceItem], task: MonitoringTask) -> int:
    groups, relevant_count = _cluster_groups(items, task)
    return max(0, relevant_count - len(groups))


def cluster_items(items: list[SourceItem], task: MonitoringTask, db: Database) -> list[EventCandidate]:
    groups, _ = _cluster_groups(items, task)

    candidates: list[EventCandidate] = []
    for group in groups:
        source_items = [item for item, _ in group]
        title = max(source_items, key=lambda item: len(item.title)).title
        event_key = stable_event_key(source_items, title)
        signal = round(sum(attention_signal(item) for item in source_items), 2)
        history = db.metric_history(event_key, limit=3)
        previous = history[0] if history else None
        current_metrics = {
            "stars": sum(item.metrics.stars or 0 for item in source_items),
            "forks": sum(item.metrics.forks or 0 for item in source_items),
            "comments": sum(item.metrics.comments or 0 for item in source_items),
            "source_score": sum(item.metrics.score or 0 for item in source_items),
            "source_count": independent_source_count(source_items),
            "platform_count": len({item.source for item in source_items}),
            "attention_signal": signal,
        }
        metric_deltas = {}
        if previous:
            for key, value in current_metrics.items():
                previous_value = float(previous.get(key, 0))
                # 迁移前的快照没有 stars/forks/comments 基线，默认 0 不能当成真实上轮值。
                if key in {"stars", "forks", "comments", "source_score"} and previous_value <= 0 < float(value):
                    continue
                metric_deltas[key] = round(float(value) - previous_value, 2)
        metric_name = None
        previous_value = 0.0
        current_value = 0.0
        minimum_baseline = 10.0
        minimum_delta = 5.0
        if previous and current_metrics["stars"] and previous.get("stars", 0) > 0:
            metric_name, previous_value, current_value, minimum_baseline, minimum_delta = "github_stars", float(previous["stars"]), float(current_metrics["stars"]), 20.0, 10.0
        elif previous and current_metrics["source_score"] and previous.get("source_score", 0) > 0:
            metric_name, previous_value, current_value, minimum_baseline, minimum_delta = "platform_score", float(previous["source_score"]), float(current_metrics["source_score"]), 10.0, 5.0
        elif previous and previous.get("attention_signal", 0) > 0:
            metric_name, previous_value, current_value, minimum_baseline, minimum_delta = "attention_signal", float(previous["attention_signal"]), float(current_metrics["attention_signal"]), 20.0, 10.0
        if metric_name:
            growth = round((current_value - previous_value) / previous_value * 100, 1)
            absolute_delta = round(current_value - previous_value, 2)
            if previous_value < minimum_baseline:
                growth_label = "低基数变化"
            elif len(history) < 2:
                growth_label = "初步增长信号" if absolute_delta >= minimum_delta else "小幅变化"
            else:
                growth_label = "持续增长" if absolute_delta >= minimum_delta else "小幅变化"
            metric_deltas["growth_evidence"] = {
                "metric": metric_name, "previous_value": previous_value, "current_value": current_value,
                "absolute_delta": absolute_delta, "relative_growth": growth,
                "snapshots": len(history) + 1, "baseline_quality": "low" if previous_value < minimum_baseline else "sufficient",
                "minimum_absolute_delta": minimum_delta, "label": growth_label,
            }
        else:
            growth = None
            growth_label = "无增长基线"
        age = max(item.collected_at for item in source_items) - min(item.published_at for item in source_items)
        if growth_label == "持续增长":
            lifecycle = "爆发"
        elif len({item.source for item in source_items}) >= 2:
            lifecycle = "扩散"
        elif age <= timedelta(hours=24):
            lifecycle = "萌芽"
        else:
            lifecycle = "未知"
        candidate = EventCandidate(
            candidate_id=event_key,
            canonical_title=title,
            items=source_items,
            relevance_score=round(max(score for _, score in group), 1),
            attention_signal=signal,
            platform_count=len({item.source for item in source_items}),
            source_count=independent_source_count(source_items),
            growth_percent=growth,
            lifecycle=lifecycle,
            metric_deltas=metric_deltas,
            event_signature=extract_event_signature(source_items[0]),
            growth_label=growth_label,
        )
        candidates.append(apply_program_judgement(candidate, task))
    candidates = _balanced_candidates(candidates, limit=20)
    if task.id in {3, 4}:
        def domain_priority(candidate: EventCandidate) -> tuple[int, int, int, float]:
            # 金融/生物的专业信息源优先；GitHub 只作为项目侧补充信号。
            source_quality = max(
                (3 if item.source == "rss" and item.is_primary_source else
                 2 if item.source == "rss" else
                 1 if item.source == "hacker_news" else 0)
                for item in candidate.items
            )
            return source_quality, candidate.platform_count, candidate.source_count, candidate.attention_signal

        return sorted(candidates, key=domain_priority, reverse=True)
    return candidates


def rule_analysis(candidate: EventCandidate, task: MonitoringTask) -> EventAnalysis:
    truth = candidate.truth_status
    if not candidate.event_gate_passed:
        action = "暂不处理"
    else:
        action = "谨慎验证"
    why = deterministic_why_now(candidate)
    source_names = "、".join(sorted({item.source for item in candidate.items}))
    metric_facts = []
    first = candidate.items[0]
    if first.metrics.stars is not None:
        metric_facts.append(f"{first.metrics.stars} stars")
    if first.metrics.forks is not None:
        metric_facts.append(f"{first.metrics.forks} forks")
    fact_suffix = f"；当前记录到 {('、'.join(metric_facts))}" if metric_facts else ""
    claims: list[AnalysisClaim] = []
    for item in candidate.items:
        ref = f"{item.source}:{item.external_id}"
        if item.source == "github":
            repo_name = "/".join(part for part in urlsplit(item.url).path.split("/") if part)[:120]
            claims.append(AnalysisClaim(
                type="verified_fact", text=f"GitHub 仓库 {repo_name or item.title} 存在。",
                evidence_source_refs=[ref], evidence_fields=["url"], status="verified",
            ))
            metrics = []
            if item.metrics.stars is not None:
                metrics.append(f"{item.metrics.stars} stars")
            if item.metrics.forks is not None:
                metrics.append(f"{item.metrics.forks} forks")
            if metrics:
                claims.append(AnalysisClaim(
                    type="verified_fact", text=f"本轮快照记录到 {'、'.join(metrics)}，快照时间为 {item.collected_at.isoformat()}。",
                    evidence_source_refs=[ref], evidence_fields=["metrics", "collected_at"], status="verified",
                ))
            if item.pushed_at:
                claims.append(AnalysisClaim(
                    type="verified_fact", text=f"仓库最近 push 时间为 {item.pushed_at.isoformat()}。",
                    evidence_source_refs=[ref], evidence_fields=["pushed_at"], status="verified",
                ))
        else:
            claims.append(AnalysisClaim(
                type="verified_fact", text=f"来源“{item.title}”在 {item.published_at.isoformat()} 发布。",
                evidence_source_refs=[ref], evidence_fields=["title", "url", "published_at"], status="verified",
            ))
    unknowns = [
        "现有证据不能证明该事件已经形成跨平台行业热点。",
        "尚未完成该事件与目标产品功能、路线图或风险面的具体影响分析。",
    ]
    if candidate.growth_label != "持续增长":
        unknowns.append("缺少连续至少三轮、超过自身历史基线的同指标增长证据。")
    if any(item.event_type == "repository_updated" for item in candidate.items):
        unknowns.extend(["普通 push 是否包含重大产品能力尚未证实。", "是否存在新版本发布或新的企业采用尚未证实。"])
    claims.extend(AnalysisClaim(type="unknown", text=text, status="insufficient_evidence") for text in unknowns)
    task_text = "；".join(f"{index + 1}. {item}" for index, item in enumerate(candidate.decision_tasks))
    return EventAnalysis(
        candidate_id=candidate.candidate_id,
        is_relevant=True,
        canonical_title=candidate.canonical_title,
        category=candidate.content_type,
        summary=f"该线索来自 {source_names}，包含 {len(candidate.items)} 条公开信息、{candidate.source_count} 个独立发布方{fact_suffix}。",
        why_now=why,
        debate="本轮未发现可验证的社区争议或反方材料；相关问题只能列为待验证项。",
        impact=task.target_role,
        recommended_action=f"责任角色：{candidate.decision_owner}；完成时限：{candidate.decision_deadline}；下一步：{task_text}",
        risk="首次运行没有历史基线；热度信号不等同于事实价值。" if candidate.growth_percent is None else "需确认多个来源是否相互独立。",
        truth_status=truth,
        cluster_confidence=candidate.cluster_confidence,
        action_level=action,
        claims=claims,
    )


def deterministic_why_now(candidate: EventCandidate) -> str:
    recent = max(candidate.items, key=lambda item: item.pushed_at or item.released_at or item.published_at)
    timestamp = recent.pushed_at or recent.released_at or recent.published_at
    signal = f"本轮发现该信息；最新可验证时间为 {timestamp.isoformat()}"
    if candidate.growth_label == "持续增长" and candidate.growth_percent is not None:
        signal += f"，同一指标已形成持续增长，较上一轮变化 {candidate.growth_percent:.1f}%"
    elif candidate.growth_label == "低基数变化":
        signal += "，当前只观察到低基数变化，不能解释为爆发"
    elif candidate.growth_label == "初步增长信号":
        signal += "，当前只有初步增长信号，尚未达到持续增长门槛"
    else:
        signal += "，当前没有可验证的正增长证据"
    signal += f"；覆盖 {candidate.platform_count} 个平台、{candidate.source_count} 个独立发布方。"
    return signal


FORBIDDEN_LOW_EVIDENCE_ACTIONS = (
    "合作", "正式部署", "规模部署", "战略布局", "加快投入", "增加投入", "投资", "对外传播", "公开发布",
)


def sanitize_analysis(analysis: EventAnalysis, candidate: EventCandidate, task: MonitoringTask) -> tuple[EventAnalysis, list[str]]:
    """让 AI 只能在程序证据边界内表达，任何越界内容都回退为确定性文字。"""
    warnings: list[str] = []
    title = candidate.canonical_title
    if analysis.canonical_title != candidate.canonical_title:
        warnings.append(f"候选 {candidate.candidate_id} 的 AI 标题未逐字复制规则标题，已忽略 AI 标题")

    debate = analysis.debate
    has_discussion = any(
        item.source in {"hacker_news", "devto", "v2ex", "bilibili"}
        and ((item.metrics.comments or 0) > 0 or bool(item.discussion_url))
        for item in candidate.items
    )
    if not has_discussion:
        debate = "本轮未发现可验证的社区争议或反方材料；相关问题只能列为待验证项。"

    recommended_action = analysis.recommended_action
    if candidate.value_level == "candidate" or any(term in recommended_action for term in FORBIDDEN_LOW_EVIDENCE_ACTIONS):
        recommended_action = rule_analysis(candidate, task).recommended_action

    summary = analysis.summary
    if candidate.value_level == "candidate":
        summary = rule_analysis(candidate, task).summary

    valid_refs = {f"{item.source}:{item.external_id}" for item in candidate.items}
    claims = []
    for claim in analysis.claims:
        refs = [ref for ref in claim.evidence_source_refs if ref in valid_refs]
        status = claim.status
        if status == "verified" and not refs:
            status = "insufficient_evidence"
        claims.append(claim.model_copy(update={"evidence_source_refs": refs, "status": status}))
    if not claims:
        claims = rule_analysis(candidate, task).claims

    return analysis.model_copy(update={
        "canonical_title": title,
        "summary": summary,
        "why_now": deterministic_why_now(candidate),
        "debate": debate,
        "recommended_action": recommended_action,
        "claims": claims,
    }), warnings
