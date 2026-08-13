"use client";

import { useEffect, useState } from "react";

type Hotspot = {
  id: number;
  title: string;
  summary: string;
  action: string;
  actionTone: "urgent" | "watch" | "risk";
  analysisMode: "ai" | "rules";
  currentAction: string;
  discussions: string;
  metricLabel: string;
  growth: string;
  growthValue: number | null;
  growthLabel: string;
  platforms: string;
  percentile: string;
  why: string;
  debate: string;
  impact: string;
  advice: string;
  risk: string;
  business: string;
  truth: string;
  cluster: string;
  hotspotConfidence: string;
  eventState: string;
  contentType: string;
  evidenceTier: string;
  evidenceConfidence: number;
  evidenceGrade: "A" | "B" | "C" | "D" | "U";
  eventGatePassed: boolean;
  eventGateReason: string;
  decisionPriority: "未评估" | "低" | "中" | "高" | "紧急" | "不进入决策";
  decisionOwner: string;
  decisionDeadline: string;
  decisionTasks: string[];
  upgradeConditions: string[];
  valueScore: number;
  valueLevel: "high_value" | "watchlist" | "candidate";
  scoreBreakdown: Record<string, { weight: number; raw_value: number | null; contribution: number; reason: string }>;
  reviewStatus: "pending" | "approved" | "rejected";
  reviewNote: string;
  sources: {
    name: string;
    title: string;
    time: string;
    short: string;
    url: string;
    eventType?: string | null;
    createdAt?: string | null;
    updatedAt?: string | null;
    pushedAt?: string | null;
    claim?: string;
    canProve?: string;
    cannotProve?: string;
    excerpt?: string;
  }[];
  evidence: [string, string][];
};

const configuredAgentApi = typeof process !== "undefined"
  ? process.env.NEXT_PUBLIC_AGENT_API_URL
  : undefined;
const streamlitBasePath = typeof window !== "undefined"
  ? window.location.pathname.replace(/\/$/, "")
  : "";
const AGENT_API = configuredAgentApi || (
  typeof window !== "undefined" && window.location.port !== "3000"
    ? `${window.location.origin}${streamlitBasePath}/agent`
    : "http://127.0.0.1:8000"
);

const industries = [
  { id: "technology", taskId: 2, label: "科技", icon: "⌘", description: "芯片、机器人、量子计算、网络安全与开源技术" },
  { id: "ai", taskId: 5, label: "AI", icon: "✦", description: "模型、Agent、多模态、生成式 AI 与前沿研究" },
  { id: "finance", taskId: 3, label: "金融", icon: "￥", description: "金融科技、支付、数字银行、市场与区块链" },
  { id: "biology", taskId: 4, label: "生物", icon: "⌬", description: "基因组、药物发现、CRISPR、蛋白质与医疗 AI" },
] as const;

type IndustryId = typeof industries[number]["id"];

type IndustryTagDefinition = { label: string; detail: string; keywords: string[] };

const industryTagTaxonomies: Record<IndustryId, IndustryTagDefinition[]> = {
  technology: [
    { label: "具身智能", detail: "具身模型、人形系统与环境交互", keywords: ["具身", "embodied", "humanoid"] },
    { label: "机器人", detail: "工业、服务与自主机器人", keywords: ["机器人", "robot", "robotics", "autonomous machine"] },
    { label: "芯片与算力", detail: "半导体、GPU、加速器与算力基础设施", keywords: ["芯片", "半导体", "算力", "semiconductor", "chip", "gpu", "accelerator", "silicon"] },
    { label: "网络安全", detail: "漏洞、攻防、数据安全与供应链风险", keywords: ["网络安全", "漏洞", "勒索", "cybersecurity", "security", "vulnerability", "cve", "ransomware"] },
    { label: "量子技术", detail: "量子计算、量子通信与量子传感", keywords: ["量子", "quantum"] },
    { label: "通信与数字孪生", detail: "5G/6G、卫星通信、数字孪生与智能网络", keywords: ["5g", "6g", "wireless", "telecom", "satellite communication", "digital twin", "数字孪生", "通信网络"] },
    { label: "云与开发者工具", detail: "云计算、数据库、开源与工程工具", keywords: ["云计算", "开源", "数据库", "cloud", "database", "developer tool", "devtool", "open source"] },
    { label: "AI 与智能应用", detail: "AI 原生软件、数字内容、健康科技与智能服务", keywords: ["ai-native", "multi-agent", "autonomous", "telerehabilitation", "health tech", "smart application", "智能应用", "远程康复"] },
    { label: "待细分科技事件", detail: "未命中现有科技标签，下方列出具体事件", keywords: [] },
  ],
  ai: [
    { label: "智能体 / Agent", detail: "自主任务、工具调用与多智能体系统", keywords: ["智能体", "agent", "agentic", "tool use", "tool-use"] },
    { label: "基础模型", detail: "大语言模型、训练、推理与模型能力", keywords: ["大模型", "语言模型", "foundation model", "language model", "llm", "reasoning model"] },
    { label: "多模态与生成媒体", detail: "图像、视频、语音与跨模态生成", keywords: ["多模态", "图生视频", "文生图", "multimodal", "image-to-video", "text-to-image", "video generation"] },
    { label: "AI 基础设施", detail: "模型部署、数据、算力与开发工具链", keywords: ["inference", "serving", "training", "vector database", "rag", "retrieval-augmented", "ai infrastructure", "mlops"] },
    { label: "评测与安全", detail: "基准、可解释性、对齐与模型风险", keywords: ["评测", "基准", "安全", "可解释", "evaluation", "benchmark", "safety", "alignment", "explainable"] },
    { label: "AI 行业应用", detail: "科研、医疗、金融、制造与内容应用", keywords: ["diagnostic", "healthcare", "finance", "manufacturing", "scientific", "industry application", "行业应用"] },
    { label: "待细分 AI 事件", detail: "未命中现有 AI 标签，下方列出具体事件", keywords: [] },
  ],
  finance: [
    { label: "支付与数字银行", detail: "支付网络、数字银行与账户服务", keywords: ["支付", "数字银行", "payment", "digital bank", "neobank"] },
    { label: "资本市场", detail: "股票、债券、投资交易与资产管理", keywords: ["资本市场", "股票", "债券", "投资", "capital market", "stock", "bond", "trading", "asset management"] },
    { label: "区块链与数字资产", detail: "加密资产、稳定币、DeFi 与链上金融", keywords: ["区块链", "数字资产", "稳定币", "blockchain", "crypto", "stablecoin", "defi", "on-chain", "coin tracing"] },
    { label: "金融监管", detail: "货币政策、合规、反洗钱与机构监管", keywords: ["监管", "合规", "反洗钱", "货币政策", "regulation", "compliance", "anti-money", "central bank"] },
    { label: "风控与反欺诈", detail: "信用、风险定价、身份和欺诈检测", keywords: ["风控", "反欺诈", "信用", "risk control", "fraud", "credit scoring", "identity"] },
    { label: "金融 AI 与 Agent", detail: "智能投研、金融模型、Agent 与自动化决策", keywords: ["金融模型", "智能投研", "financial ai", "finance agent", "agentic ai", "llm agent", "autonomous ai", "algorithmic trading"] },
    { label: "消费金融与数字商业", detail: "预算、优惠券、分期、电商和消费决策", keywords: ["消费金融", "优惠券", "分期", "consumer finance", "coupon", "budget-constrained", "basket shopping", "buy now pay later"] },
    { label: "FinTech 产品与普惠教育", detail: "金融科技产品、个人理财与金融素养教育", keywords: ["kids-fintech", "kids fintech", "financial literacy", "personal finance", "金融素养", "个人理财"] },
    { label: "待细分金融事件", detail: "未命中现有金融标签，下方列出具体事件", keywords: [] },
  ],
  biology: [
    { label: "AI 药物发现", detail: "靶点、分子生成与药物研发智能化", keywords: ["药物发现", "分子生成", "drug discovery", "molecule", "therapeutic"] },
    { label: "基因组与 CRISPR", detail: "基因组、基因编辑与单细胞研究", keywords: ["基因组", "基因编辑", "genomics", "genome", "crispr", "single-cell"] },
    { label: "蛋白质与合成生物", detail: "蛋白质设计、结构预测与生物制造", keywords: ["蛋白质", "合成生物", "protein", "synthetic biology", "biomanufacturing"] },
    { label: "医疗 AI", detail: "医学影像、临床模型与医疗智能体", keywords: ["医疗 ai", "医学影像", "medical ai", "healthcare ai", "clinical model", "radiology"] },
    { label: "诊断与临床", detail: "疾病诊断、生物标志物与临床试验", keywords: ["诊断", "临床", "生物标志物", "diagnostic", "clinical", "biomarker", "trial"] },
    { label: "生物技术平台", detail: "实验自动化、生物信息与研发工具", keywords: ["生物信息", "实验自动化", "bioinformatics", "lab automation", "biotech platform"] },
    { label: "待细分生物事件", detail: "未命中现有生物标签，下方列出具体事件", keywords: [] },
  ],
};

function buildIndustryTagShare(industryId: IndustryId, hotspots: Hotspot[]) {
  const taxonomy = industryTagTaxonomies[industryId];
  const counts = taxonomy.map(() => 0);
  const eventsByTag = taxonomy.map(() => [] as Array<{ id: number; title: string }>);
  const fallbackIndex = taxonomy.length - 1;
  for (const hotspot of hotspots) {
    const title = hotspot.title.toLowerCase();
    const supportingText = `${hotspot.summary} ${hotspot.contentType} ${hotspot.sources.map((source) => source.title).join(" ")}`.toLowerCase();
    const scores = taxonomy.map((tag) => tag.keywords.reduce((score, keyword) => {
      const term = keyword.toLowerCase();
      return score + (title.includes(term) ? 3 : 0) + (supportingText.includes(term) ? 1 : 0);
    }, 0));
    const bestScore = Math.max(...scores);
    const bestIndex = bestScore > 0 ? scores.indexOf(bestScore) : fallbackIndex;
    counts[bestIndex] += 1;
    eventsByTag[bestIndex].push({ id: hotspot.id, title: hotspot.title });
  }
  const total = hotspots.length;
  const exact = counts.map((count) => total ? count * 100 / total : 0);
  const percentages = exact.map(Math.floor);
  let remainder = total ? 100 - percentages.reduce((sum, value) => sum + value, 0) : 0;
  exact.map((value, index) => ({ index, fraction: value - percentages[index] }))
    .sort((left, right) => right.fraction - left.fraction)
    .forEach(({ index }) => { if (remainder > 0) { percentages[index] += 1; remainder -= 1; } });
  return taxonomy.map((tag, index) => ({
    ...tag,
    count: counts[index],
    percentage: percentages[index],
    events: eventsByTag[index],
    isFallback: tag.keywords.length === 0,
  }))
    .sort((left, right) => right.count - left.count);
}

type ApiHotspot = {
  id: number;
  canonical_title: string;
  category: string;
  summary: string;
  action_level: string;
  analysis_mode: "ai" | "rules";
  attention_signal: number;
  growth_percent: number | null;
  growth_label: string;
  platform_count: number;
  source_count: number;
  lifecycle: string;
  why_now: string;
  debate: string;
  impact: string;
  recommended_action: string;
  risk: string;
  truth_status: string;
  cluster_confidence: string;
  hotspot_confidence: string;
  event_state: string;
  evidence_tier: string;
  evidence_confidence: number;
  evidence_grade: "A" | "B" | "C" | "D" | "U";
  event_gate_passed: number | boolean;
  event_gate_reason: string;
  decision_priority: "未评估" | "低" | "中" | "高" | "紧急" | "不进入决策";
  current_action: string;
  decision_owner: string;
  decision_deadline: string;
  decision_tasks: string[];
  upgrade_conditions: string[];
  value_score: number;
  value_level: "high_value" | "watchlist" | "candidate";
  score_breakdown: Record<string, { weight: number; raw_value: number | null; contribution: number; reason: string }>;
  review: {
    status: "pending" | "approved" | "rejected";
    note: string;
    reviewed_at: string | null;
  };
  sources: Array<{
    id: number;
    source: string;
    title: string;
    url: string;
    discussion_url: string | null;
    published_at: string;
    created_at: string | null;
    updated_at: string | null;
    pushed_at: string | null;
    event_type: string | null;
    claim: string;
    can_prove: string;
    cannot_prove: string;
    excerpt: string;
    is_primary_source: number;
    evidence_role: string;
    publisher_id: string;
    original_publisher_id: string | null;
    is_independent: number;
    is_repost: number;
  }>;
};

type ApiRunSummary = {
  id: string;
  completed_at: string | null;
  items_collected: number;
  items_filtered: number;
  related_items: number;
  independent_events: number;
  candidates_created: number;
  ai_rejected: number;
  ai_irrelevant_count: number;
  ai_parse_failure_count: number;
  ai_success_count: number;
  ai_fallback_count: number;
  ai_duration_ms: number;
  quality_gate_fallback_count: number;
  scoring_model_version: string;
  is_current_scoring_model: boolean;
  high_value_hotspots: number;
  watchlist_events: number;
  low_confidence_candidates: number;
  ai_mode: string;
  sources: Array<{ source: string; count: number }>;
  warnings: string[];
  relevance_filtered: number;
  cluster_merged: number;
  evidence_coverage: {
    primary_or_verified: number;
    independent_confirmed: number;
    single_source: number;
    with_growth_snapshots: number;
    sustained_growth: number;
    no_growth_baseline: number;
    cross_platform: number;
    single_platform: number;
  };
};

type EmailPreview = {
  subject: string;
  text: string;
  selected_count: number;
  configured: boolean;
  recipients: string[];
};

type RunLog = { id: number; created_at: string; stage: string; message: string; level: string };
type EvidencePayload = {
  title: string;
  event_state: string;
  evidence_tier: string;
  evidence_grade: string;
  event_gate_passed: boolean;
  event_gate_reason: string;
  decision_priority: string;
  current_action: string;
  decision_owner: string;
  decision_deadline: string;
  decision_tasks: string[];
  type_evidence_checklist: Array<{ label: string; status: string }>;
  sources: ApiHotspot["sources"];
  counter_evidence: Array<{ claim: string; source_title: string; source_url: string }>;
  counter_evidence_status: string | null;
  claims_matrix: {
    verified: Array<{ text: string }>;
    partial: Array<{ text: string }>;
    unverified: Array<{ text: string }>;
    missing_evidence: string[];
    upgrade_conditions: string[];
  };
};
type FilterPayload = { raw: number; invalid: number; excluded: number; duplicates: number; relevance_filtered: number; cluster_merged: number; high_value: number; watchlist: number; candidate: number };
type AskResult = { answer: string; citations: Array<{ source_id: number; title: string; url: string }>; unknowns: string[] };
type ReportPayload = {
  report_id: string;
  title: string;
  report_type: "decision_brief" | "full_analysis";
  scope: "qualified" | "all_visible" | "approved_only";
  generation_mode: string;
  generated_at: string;
  event_count: number;
  executive_summary: string;
  key_findings: string[];
  recommended_actions: string[];
  limitations: string[];
  markdown: string;
  download_url: string;
};
type EvidenceFinding = { dimension: string; conclusion: string; evidence_status: "已验证" | "合理推断" | "证据不足"; evidence_source_ids: number[] };
type DeepAnalysisPayload = {
  event_id: number;
  generation_mode: string;
  burst_status: string;
  cause_analysis: EvidenceFinding[];
  propagation_analysis: EvidenceFinding[];
  disagreement_analysis: EvidenceFinding[];
  impact_assessment: Array<{ affected_party: string; concrete_impact: string; severity: string; recovery_cycle: string; evidence_status: string }>;
  scenarios: Array<{ name: string; trigger: string; development: string; outcome: string; likelihood: string; probability_percent: number | null; basis: string }>;
  observation_points: string[];
  recommendations: Record<string, string>;
  limitations: string[];
  citations: Array<{ source_id: number; title: string; url: string }>;
};
type ScoringDiagnostics = {
  event_count: number;
  average_value_score: number;
  zero_value_events: number;
  historical_zero_events_after_backfill: number;
  single_source_events: number;
  single_platform_events: number;
  no_positive_growth_events: number;
  component_zero_counts: Record<string, number>;
  source_distribution: Array<{ source: string; count: number }>;
  assessment: string[];
};
type DataSourcePayload = {
  run_id: string;
  completed_at: string;
  total_items: number;
  task: { id: number; name: string; topic: string };
  items: Array<{
    id: string;
    name: string;
    kind: string;
    role: string;
    homepage: string | null;
    status: "active" | "no_data";
    collected_count: number;
    primary_count: number;
    used_event_count: number;
    latest_published_at: string | null;
    time_label: string;
    publishers: Array<{ name: string; count: number }>;
    configured_feeds: string[];
    samples: Array<{ id: number; title: string; url: string; author: string | null; hostname: string; published_at: string; event_type: string | null; is_primary_source: number }>;
  }>;
};

type AgentHealth = {
  status: string;
  ai_mode: string;
  scheduler_enabled: boolean;
};

type MainView = "overview" | "agent";

function mapApiHotspots(items: ApiHotspot[]): Hotspot[] {
  const sourceIdentity = (source: ApiHotspot["sources"][number]) => {
    if (source.source === "google_news") return { name: "Google News", short: "GN" };
    if (source.source === "google_trends") return { name: "Google Trends", short: "GT" };
    if (source.source === "hacker_news") return { name: "Hacker News", short: "HN" };
    if (source.source === "github") return { name: "GitHub", short: "GH" };
    if (source.source === "arxiv") return { name: "arXiv", short: "AX" };
    if (source.source === "devto") return { name: "DEV Community", short: "DEV" };
    if (source.source === "v2ex") return { name: "V2EX", short: "V2" };
    if (source.source === "bilibili") return { name: "Bilibili", short: "B站" };
    if (source.source === "chinanews") return { name: "中国新闻网", short: "中新" };
    if (source.source === "cctv_news") return { name: "央视新闻", short: "央视" };
    const hostname = new URL(source.url).hostname.replace(/^www\./, "");
    if (hostname.endsWith("federalreserve.gov")) return { name: "Federal Reserve", short: "FED" };
    if (hostname.endsWith("ecb.europa.eu")) return { name: "ECB", short: "ECB" };
    if (hostname.endsWith("bankofengland.co.uk")) return { name: "Bank of England", short: "BOE" };
    if (hostname.endsWith("sec.gov")) return { name: "SEC", short: "SEC" };
    if (hostname.endsWith("fda.gov")) return { name: "FDA", short: "FDA" };
    if (hostname.endsWith("nature.com")) return { name: "Nature Biotechnology", short: "NBT" };
    if (hostname.endsWith("biorxiv.org")) return { name: "bioRxiv", short: "BRX" };
    return { name: hostname, short: "RSS" };
  };
  return items.slice(0, 6).map((event) => {
    const actionTone: Hotspot["actionTone"] = event.action_level === "立即跟进"
      ? "urgent"
      : event.action_level === "持续观察" ? "watch" : "risk";
    return {
      id: event.id,
      title: event.canonical_title,
      summary: event.summary,
      action: event.action_level,
      actionTone,
      analysisMode: event.analysis_mode || "rules",
      currentAction: event.current_action || "补证",
      metricLabel: "关注信号",
      discussions: Math.round(event.attention_signal).toLocaleString("zh-CN"),
      growth: event.growth_label === "低基数变化" ? "低基数变化" : event.growth_label === "无增长基线" ? "待积累" : event.growth_label || "待积累",
      growthValue: event.growth_percent,
      growthLabel: event.growth_label,
      platforms: `${event.platform_count} 个平台`,
      percentile: event.lifecycle,
      why: event.why_now,
      debate: event.debate,
      impact: event.impact,
      advice: event.recommended_action,
      risk: event.risk,
      business: `${event.action_level} · 基于真实采集信号`,
      truth: event.truth_status,
      cluster: event.cluster_confidence,
      hotspotConfidence: event.hotspot_confidence,
      eventState: event.event_state,
      contentType: event.category || "未分类事件",
      evidenceTier: event.evidence_tier,
      evidenceConfidence: event.evidence_confidence,
      evidenceGrade: event.evidence_grade || "U",
      eventGatePassed: Boolean(event.event_gate_passed),
      eventGateReason: event.event_gate_reason || "尚未识别明确事件动作",
      decisionPriority: event.decision_priority || "未评估",
      decisionOwner: event.decision_owner || "竞争情报分析师",
      decisionDeadline: event.decision_deadline || "下一工作日",
      decisionTasks: event.decision_tasks || [],
      upgradeConditions: event.upgrade_conditions || [],
      valueScore: event.value_score,
      valueLevel: event.value_level,
      scoreBreakdown: event.score_breakdown || {},
      reviewStatus: event.review?.status || "pending",
      reviewNote: event.review?.note || "",
      sources: event.sources.map((source) => ({
        ...sourceIdentity(source),
        title: source.title,
        time: new Date(source.published_at).toLocaleString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }),
        url: source.discussion_url || source.url,
        eventType: source.event_type,
        createdAt: source.created_at,
        updatedAt: source.updated_at,
        pushedAt: source.pushed_at,
        claim: source.claim,
        canProve: source.can_prove,
        cannotProve: source.cannot_prove,
        excerpt: source.excerpt,
      })),
      evidence: [
        ["支持证据", `关联 ${event.source_count} 条真实公开信息`],
        ["反方证据", event.debate],
        ["风险提示", event.risk],
      ],
    };
  });
}

const navItems = [
  { id: "overview", label: "行业态势", icon: "⌁" },
  { id: "agent", label: "热点发现", icon: "⌖" },
  { id: "report", label: "报告中心", icon: "▥" },
  { id: "sources", label: "数据源", icon: "◫" },
] as const;

function IndustryOverview({
  industryId,
  industryLabel,
  industryIcon,
  hotspots,
  runSummary,
  dataMode,
  updatedAt,
  health,
  onOpenAgent,
  onGenerateReport,
  onOpenSources,
}: {
  industryId: IndustryId;
  industryLabel: string;
  industryIcon: string;
  hotspots: Hotspot[];
  runSummary: ApiRunSummary | null;
  dataMode: "loading" | "live" | "empty" | "offline";
  updatedAt: string;
  health: AgentHealth | null;
  onOpenAgent: () => void;
  onGenerateReport: () => void;
  onOpenSources: () => void;
}) {
  const average = (values: number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  const signalIndex = average(hotspots.map((item) => item.valueScore));
  const evidenceQualified = hotspots.filter((item) => ["A", "B", "C"].includes(item.evidenceGrade)).length;
  const rising = hotspots.filter((item) => item.growthLabel === "持续增长");
  const crossPlatform = runSummary?.evidence_coverage?.cross_platform ?? 0;
  const hasBaseline = (runSummary?.evidence_coverage?.sustained_growth ?? 0) > 0;
  const status = crossPlatform > 0 && hasBaseline ? "出现可验证升温信号" : "基线建立中";
  const statusTone = crossPlatform > 0 && hasBaseline ? "warming" : "building";
  const industryTags = buildIndustryTagShare(industryId, hotspots);
  const priority = hotspots[0];
  const brief = dataMode === "offline"
    ? "Python Agent 当前未连接，行业态势无法更新。"
    : !runSummary
      ? "尚未形成真实运行记录。运行 Agent 后，这里将汇总行业状态、升温主题和证据缺口。"
      : crossPlatform === 0
        ? `本轮采集 ${runSummary.items_collected} 条公开信息，形成 ${runSummary.candidates_created} 个候选事件，但尚无跨平台事件。当前结果适合建立观察清单，不足以证明${industryLabel}行业整体升温。`
        : `本轮形成 ${runSummary.candidates_created} 个候选事件，其中 ${crossPlatform} 个获得跨平台信号。建议优先核验增长持续性和独立来源后再采取行动。`;

  return <div className="overview-page">
    <section className="overview-hero">
      <div className="overview-hero-copy">
        <span className="eyebrow">INDUSTRY PULSE / 行业态势</span>
        <h2><i>{industryIcon}</i>{industryLabel}<br/><em>实时态势总览</em></h2>
        <p>把公开事件聚合为可追溯的行业信号。先看状态，再看原因，最后回到原始证据。</p>
      </div>
      <div className={`overview-status ${statusTone}`}>
        <span>当前判断</span><strong>{status}</strong>
        <p>数据截至 {updatedAt}<br/>最近 14 天 · {dataMode === "live" ? "真实公开数据" : dataMode === "loading" ? "正在加载" : "等待数据"}</p>
      </div>
    </section>

    <section className="overview-metrics" aria-label="行业态势核心指标">
      <article><span>探索态势指数</span><strong>{signalIndex.toFixed(1)}</strong><small>候选事件平均价值分，不等同市场规模</small></article>
      <article><span>可验证升温主题</span><strong>{rising.length}</strong><small>{rising.length ? "已出现正增长主题" : "当前没有可验证的正增长主题"}</small></article>
      <article><span>发布事实可核验</span><strong>{evidenceQualified}<i>/{hotspots.length}</i></strong><small>只证明发布或事件存在；不代表技术结论、行业影响或产品价值成立</small></article>
      <article><span>跨平台事件</span><strong>{crossPlatform}</strong><small>{runSummary ? `${runSummary.evidence_coverage.independent_confirmed} 个获得独立确认` : "等待首次运行"}</small></article>
    </section>

    <div className="overview-grid">
      <section className="overview-panel dimension-panel">
        <header><div><span>01</span><h3>{industryLabel}态势标签占比</h3></div><small>{hotspots.length ? `基于本轮 ${hotspots.length} 个真实候选事件` : "等待真实候选事件"}</small></header>
        <div className="dimension-list tag-share-list">{industryTags.map((item) => <div key={item.label} className={`tag-share-item ${item.count ? "active" : "empty"} ${item.isFallback ? "unclassified" : ""}`}><div className="dimension-row"><div><b>{item.label}</b><small>{item.count ? `${item.count} 个事件 · ${item.detail}` : item.detail}</small></div><span><i style={{width:`${item.percentage}%`}}/></span><strong>{item.percentage}%</strong></div>{item.events.length > 0 && <ul className="tag-event-list" aria-label={`${item.label}包含的事件`}>{item.events.map((event) => <li key={event.id}><span>{event.title}</span></li>)}</ul>}</div>)}</div>
        <p className="tag-share-note">每个事件只计入一个最匹配的主标签；占比反映当前候选事件结构，不等同于行业市场份额。</p>
      </section>

      <section className="overview-panel brief-panel">
        <header><div><span>02</span><h3>Agent 行业判断</h3></div><small>证据约束摘要</small></header>
        <div className="brief-content"><span className="brief-mark">✦</span><p>{brief}</p>{priority && <div><small>当前首项可判断事件</small><b>{priority.title}</b><em>证据 {priority.evidenceGrade} 级 · 决策优先级 {priority.decisionPriority}</em></div>}</div>
        <button onClick={onOpenAgent}>查看判断依据与原始来源 →</button>
      </section>

      <section className="overview-panel topics-panel">
        <header><div><span>03</span><h3>主题态势榜</h3></div><small>只展示通过明确事件门槛的结果</small></header>
        <div className="topic-table"><div className="topic-head"><span>主题 / 事件</span><span>处理状态</span><span>增长</span><span>证据</span><span>优先级</span></div>{hotspots.length ? hotspots.slice(0,5).map((item,index) => <button key={item.id} onClick={onOpenAgent}><span><i>{String(index+1).padStart(2,"0")}</i><b>{item.title}</b></span><span>{item.eventState}</span><span className={item.growthLabel === "持续增长" ? "positive" : "muted"}>{item.growth}</span><span>{item.evidenceGrade}</span><strong>{item.decisionPriority}</strong></button>) : <p className="overview-empty">等待 Agent 形成真实候选事件。</p>}</div>
      </section>

      <section className="overview-panel agent-pulse">
        <header><div><span>04</span><h3>热点发现 Agent</h3></div><small>{health?.scheduler_enabled ? "自动定时运行" : "当前为手动运行"}</small></header>
        <div className="agent-flow">{[
          ["公开采集", runSummary?.items_collected ?? 0],
          ["相关信息", runSummary?.related_items ?? 0],
          ["候选事件", runSummary?.candidates_created ?? 0],
          ["高价值热点", runSummary?.high_value_hotspots ?? 0],
        ].map(([label,value],index) => <div key={String(label)}><span>{index+1}</span><b>{value}</b><small>{label}</small></div>)}</div>
        <p>真实来源 → 清洗去重 → 合并事件 → AI总结 → 价值判断 → 人工确认 → 报告与邮件</p>
        <div className="agent-pulse-actions"><button onClick={onOpenAgent}>打开 Agent 工作台</button><button onClick={onGenerateReport}>生成报告</button><button onClick={onOpenSources}>查看数据源</button></div>
      </section>
    </div>
  </div>;
}

export default function Home() {
  const [view, setView] = useState<MainView>("overview");
  const [industryId, setIndustryId] = useState<IndustryId>("ai");
  const [selectedId, setSelectedId] = useState(1);
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [runSummary, setRunSummary] = useState<ApiRunSummary | null>(null);
  const [dataMode, setDataMode] = useState<"loading" | "live" | "empty" | "offline">("loading");
  const [isUpdating, setIsUpdating] = useState(false);
  const [range, setRange] = useState<"24h" | "14d">("24h");
  const [question, setQuestion] = useState("");
  const [toast, setToast] = useState("");
  const [emailPreview, setEmailPreview] = useState<EmailPreview | null>(null);
  const [isSendingEmail, setIsSendingEmail] = useState(false);
  const [runLogs, setRunLogs] = useState<RunLog[] | null>(null);
  const [evidencePayload, setEvidencePayload] = useState<EvidencePayload | null>(null);
  const [filterPayload, setFilterPayload] = useState<FilterPayload | null>(null);
  const [askResult, setAskResult] = useState<AskResult | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [reportPreview, setReportPreview] = useState<ReportPayload | null>(null);
  const [reportType, setReportType] = useState<"decision_brief" | "full_analysis">("full_analysis");
  const [reportScope, setReportScope] = useState<"qualified" | "all_visible" | "approved_only">("qualified");
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [deepAnalysis, setDeepAnalysis] = useState<DeepAnalysisPayload | null>(null);
  const [isDeepAnalyzing, setIsDeepAnalyzing] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [scoringDiagnostics, setScoringDiagnostics] = useState<ScoringDiagnostics | null>(null);
  const [dataSources, setDataSources] = useState<DataSourcePayload | null>(null);
  const [agentHealth, setAgentHealth] = useState<AgentHealth | null>(null);
  const [updatedAt, setUpdatedAt] = useState("2026-08-12 10:30");
  const industry = industries.find((item) => item.id === industryId) ?? industries[1];
  const selected = hotspots.find((item) => item.id === selectedId) ?? hotspots[0];
  const actionGroups = {
    "补证": hotspots.filter((item) => item.currentAction === "补证"),
    "技术初筛": hotspots.filter((item) => item.currentAction === "技术初筛"),
    "业务评估": hotspots.filter((item) => item.currentAction === "业务评估"),
    "观察/行动": hotspots.filter((item) => ["观察", "立即行动"].includes(item.currentAction)),
  };
  const priorityHotspot = hotspots[0];

  const selectFirst = (items: Hotspot[]) => {
    if (items[0]) setSelectedId(items[0].id);
  };

  const loadLiveHotspots = async (taskId: number, silent = false) => {
    setDataMode("loading");
    try {
      const response = await fetch(`${AGENT_API}/api/hotspots?task_id=${taskId}&limit=6`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json() as { items: ApiHotspot[]; run: ApiRunSummary | null };
      const mapped = mapApiHotspots(payload.items || []);
      setHotspots(mapped);
      setRunSummary(payload.run || null);
      setSelectedId(mapped[0]?.id ?? 0);
      setDataMode(mapped.length ? "live" : "empty");
      const completedAt = payload.run?.completed_at ? new Date(payload.run.completed_at) : new Date();
      setUpdatedAt(completedAt.toLocaleString("zh-CN", { hour12: false }).replaceAll("/", "-"));
      if (!silent) notify(mapped.length ? `已加载 ${mapped.length} 个候选线索` : "该行业还没有运行记录，请点击更新分析");
    } catch {
      setHotspots([]);
      setRunSummary(null);
      setDataMode("offline");
      if (!silent) notify("Python Agent 未启动，暂时无法加载真实数据");
    }
  };

  useEffect(() => {
    void loadLiveHotspots(industry.taskId, true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [industry.taskId]);

  useEffect(() => {
    fetch(`${AGENT_API}/health`)
      .then((response) => response.ok ? response.json() as Promise<AgentHealth> : Promise.reject())
      .then(setAgentHealth)
      .catch(() => setAgentHealth(null));
  }, []);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  };

  const updateAnalysis = async () => {
    if (isUpdating) return;
    setIsUpdating(true);
    try {
      const response = await fetch(`${AGENT_API}/api/agent-runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: industry.taskId }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const { run_id } = await response.json() as { run_id: string };
      setRunLogs([]);
      notify("Agent 已启动：正在采集和分析真实公开信息");
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const statusResponse = await fetch(`${AGENT_API}/api/agent-runs/${run_id}`);
        if (!statusResponse.ok) continue;
        const run = await statusResponse.json() as { status: string; error_message?: string };
        const logsResponse = await fetch(`${AGENT_API}/api/agent-runs/${run_id}/logs`);
        if (logsResponse.ok) setRunLogs(((await logsResponse.json()) as { items: RunLog[] }).items);
        if (run.status === "completed") {
          await loadLiveHotspots(industry.taskId, true);
          notify("候选线索分析已完成");
          return;
        }
        if (run.status === "failed") throw new Error(run.error_message || "Agent 运行失败");
      }
      notify("Agent 仍在后台运行，请稍后刷新");
    } catch {
      notify("无法连接 Python Agent，请先运行 run_api.py");
    } finally {
      setIsUpdating(false);
    }
  };

  const reviewSelected = async (status: "approved" | "rejected" | "pending") => {
    if (!selected) return;
    if (status !== "pending" && !reviewNote.trim()) {
      notify("请先选择或填写审核理由");
      return;
    }
    try {
      const response = await fetch(`${AGENT_API}/api/hotspots/${selected.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note: reviewNote }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setHotspots((items) => items.map((item) => item.id === selected.id ? { ...item, reviewStatus: status } : item));
      if (status === "rejected") setHotspots((items) => items.filter((item) => item.id !== selected.id));
      notify(status === "approved" ? "已人工确认该热点" : status === "rejected" ? "已驳回该热点" : "已恢复为待确认");
    } catch {
      notify("审核保存失败，请检查 Python Agent");
    }
  };

  const openLogs = async () => {
    if (!runSummary?.id) return notify("当前还没有运行记录");
    const response = await fetch(`${AGENT_API}/api/agent-runs/${runSummary.id}/logs`);
    if (!response.ok) return notify("无法读取执行日志");
    setRunLogs(((await response.json()) as { items: RunLog[] }).items);
  };

  const openEvidence = async () => {
    if (!selected) return;
    const response = await fetch(`${AGENT_API}/api/hotspots/${selected.id}/evidence`);
    if (!response.ok) return notify("无法读取证据");
    setEvidencePayload(await response.json() as EvidencePayload);
  };

  const openFiltering = async () => {
    const response = await fetch(`${AGENT_API}/api/filtering-reasons?task_id=${industry.taskId}`);
    if (!response.ok) return notify("当前还没有筛选记录");
    setFilterPayload(await response.json() as FilterPayload);
  };

  const openScoringDiagnostics = async () => {
    const response = await fetch(`${AGENT_API}/api/scoring-diagnostics?task_id=${industry.taskId}`);
    if (!response.ok) return notify("当前还没有评分诊断记录");
    setScoringDiagnostics(await response.json() as ScoringDiagnostics);
  };

  const openDataSources = async () => {
    try {
      const response = await fetch(`${AGENT_API}/api/data-sources?task_id=${industry.taskId}`);
      const payload = await response.json() as DataSourcePayload & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      setDataSources(payload);
    } catch (error) {
      notify(error instanceof Error ? error.message : "无法读取数据源明细");
    }
  };

  const analyzeSelectedDeeply = async () => {
    if (!selected || isDeepAnalyzing) return;
    setIsDeepAnalyzing(true);
    try {
      const response = await fetch(`${AGENT_API}/api/hotspots/${selected.id}/deep-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audience: "产品、研究、媒体与相关决策者", horizon_days: 7 }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setDeepAnalysis(await response.json() as DeepAnalysisPayload);
    } catch {
      notify("深度分析失败，请检查 Python Agent");
    } finally {
      setIsDeepAnalyzing(false);
    }
  };

  const enrichSelected = async () => {
    if (!selected || isEnriching) return;
    setIsEnriching(true);
    try {
      const response = await fetch(`${AGENT_API}/api/hotspots/${selected.id}/enrich`, { method: "POST" });
      const payload = await response.json() as { matched_count?: number; event_state?: string; detail?: string };
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      await loadLiveHotspots(industry.taskId, true);
      notify(`补证完成：匹配 ${payload.matched_count || 0} 条，当前状态为 ${payload.event_state || "候选线索"}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "补充证据失败");
    } finally {
      setIsEnriching(false);
    }
  };

  const askSelected = async () => {
    if (!selected || !question.trim()) return;
    const submitted = question.trim();
    const response = await fetch(`${AGENT_API}/api/hotspots/${selected.id}/ask`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: submitted }),
    });
    if (!response.ok) return notify("追问失败");
    setAskResult(await response.json() as AskResult);
    setQuestion("");
  };

  const generateReport = async (
    requestedType = reportType,
    requestedScope = reportScope,
  ) => {
    if (isGeneratingReport) return;
    setIsGeneratingReport(true);
    try {
      const response = await fetch(`${AGENT_API}/api/reports/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: industry.taskId, report_type: requestedType, scope: requestedScope, max_events: 10 }),
      });
      const payload = await response.json() as ReportPayload & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      setReportPreview(payload);
      notify(`分析报告已生成：${payload.event_count} 个事件`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "分析报告生成失败");
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const previewEmail = async () => {
    try {
      const response = await fetch(`${AGENT_API}/api/email/preview?task_id=${industry.taskId}`);
      const payload = await response.json() as EmailPreview & { detail?: string };
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      setEmailPreview(payload);
    } catch (error) {
      notify(error instanceof Error ? error.message : "无法生成邮件预览");
    }
  };

  const confirmSendEmail = async () => {
    if (!emailPreview || isSendingEmail) return;
    if (!emailPreview.configured) {
      notify("请先在 agent_backend/.env 配置 SMTP 邮箱参数");
      return;
    }
    setIsSendingEmail(true);
    try {
      const response = await fetch(`${AGENT_API}/api/email/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: industry.taskId }),
      });
      const payload = await response.json() as { recipient_count?: number; detail?: string };
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      setEmailPreview(null);
      notify(`邮件已发送给 ${payload.recipient_count || 0} 个收件人`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "邮件发送失败");
    } finally {
      setIsSendingEmail(false);
    }
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">◎</span><span><strong>TrendScope</strong><small>行业态势 Agent</small></span></div>
        <nav aria-label="主导航">
          {navItems.map((item) => <button key={item.id} className={item.id === view ? "active" : ""} onClick={() => item.id === "report" ? void generateReport() : item.id === "sources" ? void openDataSources() : setView(item.id)}><span>{item.icon}</span>{item.label}</button>)}
        </nav>
        <div className="sidebar-agent-state"><i className={dataMode === "live" ? "online" : ""}/><span><b>{dataMode === "live" ? "Agent 已连接" : "Agent 未连接"}</b><small>{agentHealth?.scheduler_enabled ? "定时任务已开启" : "手动运行模式"}</small></span></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><h1>{industry.label} <i /> {view === "overview" ? "行业态势" : "热点发现 Agent"}</h1><p>公开渠道监控　·　数据截至 {updatedAt}　·　最近 14 天　·　{dataMode === "live" ? "真实数据" : dataMode === "loading" ? "加载中" : dataMode === "empty" ? "等待首次运行" : "Agent 未连接"}　<span className="info-dot">i</span></p></div>
          <div className="top-actions"><span className="role-chip">♙　AI 产品与竞争情报</span><button className="ghost" onClick={() => void openLogs()}>▤　查看执行日志</button><button className="primary" disabled={isUpdating} onClick={updateAnalysis}>↻　{isUpdating ? "分析中…" : "更新分析"}</button></div>
        </header>

        <section className="industry-selector" aria-label="选择热点行业">
          {industries.map((item) => <button key={item.id} className={industryId === item.id ? "active" : ""} onClick={() => setIndustryId(item.id)}><i>{item.icon}</i><span><b>{item.label}</b><small>{item.description}</small></span></button>)}
        </section>

        {view === "overview" ? <IndustryOverview
          industryId={industryId}
          industryLabel={industry.label}
          industryIcon={industry.icon}
          hotspots={hotspots}
          runSummary={runSummary}
          dataMode={dataMode}
          updatedAt={updatedAt}
          health={agentHealth}
          onOpenAgent={() => setView("agent")}
          onGenerateReport={() => void generateReport()}
          onOpenSources={() => void openDataSources()}
        /> : <>
        <section className="agent-workflow-strip" aria-label="热点发现 Agent 工作流">
          <div><span>01</span><b>公开采集</b><small>新闻 · RSS · GitHub · 社区</small></div><i>→</i>
          <div><span>02</span><b>清洗与聚类</b><small>去重 · 合并同一事件</small></div><i>→</i>
          <div><span>03</span><b>AI 分析</b><small>筛选 · 总结 · 可信度</small></div><i>→</i>
          <div><span>04</span><b>人工确认</b><small>核验证据与判断</small></div><i>→</i>
          <div><span>05</span><b>报告推送</b><small>报告 · 邮件</small></div>
        </section>

        <section className="decision-banner">
          <span className="alert-icon">!</span>
          <div className="decision-copy">
            <h2>本轮形成 {runSummary?.candidates_created ?? hotspots.length} 个可判断事件；未通过明确事件门槛的普通 push、教程和噪声内容已过滤出榜。</h2>
            <p>{priorityHotspot ? `当前首项：${priorityHotspot.title}。证据等级 ${priorityHotspot.evidenceGrade}，业务优先级“${priorityHotspot.decisionPriority}”。` : "当前没有通过事件门槛的候选，请运行 Agent 获取最新结果。"}{runSummary && ` AI 分析 ${runSummary.ai_success_count}/${runSummary.candidates_created} 成功，规则降级 ${runSummary.ai_fallback_count}，模型耗时 ${(runSummary.ai_duration_ms / 1000).toFixed(1)} 秒。`}</p>
          </div>
          <div className="decision-actions">
            {Object.entries(actionGroups).map(([label, items]) => <button key={label} className={label === "观察/行动" ? "urgent" : label === "业务评估" ? "watch" : ""} disabled={!items.length} onClick={() => selectFirst(items)}>{label}　<b>{items.length}</b></button>)}
          </div>
        </section>

        <section className="funnel" aria-label="信息处理漏斗">
          {[
            ["▤","原始信息",`${runSummary?.items_collected ?? 0} 条`, runSummary ? `移除 ${runSummary.items_filtered} 条` : "等待运行"],
            ["▽","清洗信息",`${runSummary?.related_items ?? 0} 条`,"真实公开数据"],
            ["⌁","候选事件",`${runSummary?.candidates_created || runSummary?.independent_events || 0} 个`, runSummary ? `实际聚类合并 ${runSummary.cluster_merged} 条` : "等待运行"],
            ["☆","高价值热点",`${runSummary?.high_value_hotspots ?? 0} 个`, runSummary ? `观察 ${runSummary.watchlist_events ?? 0} · 线索 ${runSummary.low_confidence_candidates ?? 0}` : "程序阈值分层"]
          ].map((stage, index) => <div className="funnel-stage" key={stage[1]} onClick={() => notify(`查看${stage[1]}明细`)}><span className={`stage-icon c${index}`}>{stage[0]}</span><div><small>{stage[1]}</small><strong>{stage[2]}</strong><em>{stage[3]}</em></div>{index < 3 && <b className="arrow">→</b>}</div>)}
          <div className="coverage"><p>证据覆盖：一手 {runSummary?.evidence_coverage?.primary_or_verified ?? 0}　·　独立确认 {runSummary?.evidence_coverage?.independent_confirmed ?? 0}　·　跨平台 {runSummary?.evidence_coverage?.cross_platform ?? 0}　·　无增长基线 <strong>{runSummary?.evidence_coverage?.no_growth_baseline ?? 0}</strong></p><button onClick={() => void openFiltering()}>查看筛选原因　›</button><button onClick={() => void openScoringDiagnostics()}>诊断价值分　›</button></div>
        </section>

        <div className="analysis-grid">
          <div className="left-column">
            <section className="panel trend-panel">
              <div className="panel-head"><div className="title-tabs"><h2>趋势与爆发信号</h2><button className={range === "24h" ? "selected" : ""} onClick={() => setRange("24h")}>24 小时</button><button className={range === "14d" ? "selected" : ""} onClick={() => setRange("14d")}>14 天</button></div><p>生命周期：萌芽　→　爆发　→　<b>扩散</b>　→　衰退</p></div>
              {hotspots.length ? <><div className="legend">{hotspots.slice(0, 3).map((item, index) => <span key={item.id}><i className={["blue", "green", "amber"][index]} />{item.title}</span>)}<em>完成至少三轮同指标采集后确认持续增长</em></div><div className="trend-waiting"><b>{industry.label}候选线索已载入</b><p>当前只展示真实快照结论；低基数变化不会标成爆发，也不会绘制虚构折线。</p></div></> : <div className="trend-waiting"><b>{dataMode === "loading" ? "正在加载候选线索…" : dataMode === "offline" ? "Python Agent 未连接" : `${industry.label}行业暂无候选线索`}</b><p>{dataMode === "empty" ? "点击右上角“更新分析”，Agent 将从已配置的公开来源发现事件种子。" : "等待真实数据后再展示趋势和判断结果。"}</p></div>}
            </section>

            <section className="hotspots-section">
              <div className="section-head"><h2>可判断事件 <span>（共 {hotspots.length} 个，已通过明确事件门槛）</span></h2></div>
              {hotspots.map((item, index) => (
                <article key={item.id} className={`hotspot-card ${selectedId === item.id ? "selected" : ""}`} onClick={() => setSelectedId(item.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelectedId(item.id)}>
                  <span className="rank">{index + 1}</span>
                  <div className="hotspot-main">
                    <div className="hotspot-title"><h3>{item.title}</h3><div className="card-badges"><span className={`review-badge ${item.reviewStatus}`}>{item.reviewStatus === "approved" ? "已人工确认" : item.reviewStatus === "rejected" ? "已驳回" : "待人工确认"}</span><span className={`action-badge ${item.actionTone}`}>{item.currentAction}</span></div></div>
                    <div className="signal-chips"><span>事实状态　<b>{item.evidenceGrade} · {item.truth}</b></span><span>趋势状态　<b>{item.growth}</b></span><span>业务优先级　<b>{item.decisionPriority}</b></span><span>当前动作　<b>{item.currentAction}</b></span></div>
                    {selectedId === item.id && <><p className="ai-summary"><b>✦ {item.analysisMode === "ai" ? "AI 分析" : "规则摘要"}：</b>{item.summary}</p><div className="insight-grid"><p><b>为何上榜：</b>{item.why}</p><p><b>建议动作：</b>{item.advice}</p><p><b>争议焦点：</b>{item.debate}</p><p><b>风险：</b>{item.risk}</p><p><b>影响对象：</b>{item.impact}</p></div><div className="source-links">{item.sources.slice(0, 3).map((source) => source.url ? <a key={`${source.name}-${source.url}`} href={source.url} target="_blank" rel="noreferrer" title={source.title} onClick={(event) => event.stopPropagation()}><i>{source.short}</i>{source.name} ↗</a> : <span className="source-unavailable" key={`${source.name}-${source.title}`} title="样板数据没有可验证链接"><i>{source.short}</i>{source.name}</span>)}<span className="source-count">{item.sources.length} 条来源记录</span></div></>}
                  </div>
                </article>
              ))}
              <button className="view-all" onClick={() => dataMode === "live" ? window.open(`${AGENT_API}/api/hotspots?task_id=${industry.taskId}&limit=100`, "_blank", "noopener,noreferrer") : notify("启动 Python Agent 后加载真实热点")}>{dataMode === "live" ? "查看完整真实数据" : "连接 Python Agent"}　↓</button>
            </section>
          </div>

          {selected ? <aside className="right-column">
            <section className="panel decision-gates">
              <div className="panel-head"><h2>四关卡判断 <span>｜从事件事实到执行任务</span></h2></div>
              <div className="gate-list">
                <article className={selected.eventGatePassed ? "pass" : "blocked"}><span>01</span><div><b>是否为明确事件</b><p>{selected.eventGatePassed ? "通过事件门槛" : "过滤出榜"}：{selected.eventGateReason}</p></div><em>{selected.eventGatePassed ? "通过" : "未通过"}</em></article>
                <article className={["A","B","C"].includes(selected.evidenceGrade) ? "pass" : "waiting"}><span>02</span><div><b>发布事实是否可核验</b><p>证据等级 {selected.evidenceGrade} · {selected.truth} · {selected.sources.length} 条来源；技术结论、独立复现和产品影响需另行验证</p></div><em>{selected.evidenceGrade}</em></article>
                <article className={selected.growthLabel === "持续增长" ? "pass" : "waiting"}><span>03</span><div><b>是否真的升温</b><p>{selected.growthLabel === "持续增长" ? `当前记录到 ${selected.growth}` : "缺少连续三轮、超过自身历史基线的同指标增长"}</p></div><em>{selected.growthLabel === "持续增长" ? "升温" : "未知"}</em></article>
                <article className={["紧急","高","中"].includes(selected.decisionPriority) ? "pass" : "waiting"}><span>04</span><div><b>是否值得目标用户行动</b><p>业务优先级：{selected.decisionPriority}；当前动作：{selected.currentAction}。产品、用户、影响机制与不行动成本不完整时不强行分级</p></div><em>{selected.decisionPriority}</em></article>
              </div>
              <div className="execution-card"><header><div><small>责任角色</small><b>{selected.decisionOwner}</b></div><div><small>完成时限</small><b>{selected.decisionDeadline}</b></div></header><h3>下一步任务</h3><ol>{selected.decisionTasks.map((task) => <li key={task}>{task}</li>)}</ol></div>
            </section>

            <section className="panel propagation">
              <div className="panel-head"><h2>{selected.sources.length > 1 ? "证据发布链" : "传播路径"}</h2></div>
              {selected.sources.length > 1 ? <><div className="source-path">{selected.sources.map((source, index) => <div className="source-node" key={`${source.name}-${source.url}`}><i>{source.short}</i><b>{source.name}</b><small>{source.time}</small>{index < selected.sources.length - 1 && <span>→</span>}</div>)}</div><p>首个可回溯来源：<b>{selected.sources[0].name}</b>；箭头仅表示时间顺序，不证明转载或因果。</p></> : <div className="trend-waiting compact"><b>尚未形成传播路径</b><p>当前只覆盖一个平台，不能推断跨平台扩散。</p></div>}
            </section>

            <section className="panel key-evidence">
              <div className="panel-head"><h2>主张—证据矩阵</h2></div>
              <div className="evidence-row"><i>✓</i><b>当前状态</b><span>{selected.eventState}；{selected.sources.length} 条记录可回溯</span><button onClick={() => void openEvidence()}>查看矩阵　›</button></div>
              <div className="evidence-row e1"><i>?</i><b>证据缺口</b><span>检查一手、独立确认、增长和反方材料</span><button onClick={() => void openEvidence()}>查看缺口　›</button></div>
            </section>

            <section className="agent-box">
              <div className="ask-row"><span>≡</span><input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => {if (e.key === "Enter") void askSelected();}} placeholder="解释程序判断：为什么它不能算高价值热点？"/><button aria-label="解释程序判断" onClick={() => void askSelected()}>➤</button></div>
              {askResult && <div className="ask-answer"><b>程序判断解释</b><p>{askResult.answer}</p>{askResult.citations.map((citation) => <a key={citation.source_id} href={citation.url} target="_blank" rel="noreferrer">[{citation.source_id}] {citation.title}</a>)}</div>}
              <div className="review-note"><select value={reviewNote} onChange={(event) => setReviewNote(event.target.value)}><option value="">选择审核理由</option><option>确认有效</option><option>来源不足</option><option>时间不准确</option><option>与主题无关</option><option>影响被夸大</option><option>重复事件</option><option>营销内容</option></select><input value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="可补充审核备注" /></div>
              <div className="review-actions"><button className={selected.reviewStatus === "approved" ? "active approve" : "approve"} onClick={() => void reviewSelected("approved")}>✓　人工确认</button><button className={selected.reviewStatus === "rejected" ? "active reject" : "reject"} onClick={() => void reviewSelected("rejected")}>×　驳回热点</button><button onClick={() => void reviewSelected("pending")}>↺　恢复待审</button></div>
              <div className="quick-actions"><button disabled={isGeneratingReport} onClick={() => void generateReport()}>▤　{isGeneratingReport ? "报告生成中…" : "生成分析报告"}</button><button disabled={isDeepAnalyzing} onClick={() => void analyzeSelectedDeeply()}>◇　{isDeepAnalyzing ? "分析中…" : "深层原因分析"}</button><button disabled={isEnriching} onClick={() => void enrichSelected()}>⌁　{isEnriching ? "正在补充证据…" : "补充证据并重新判断"}</button><button className="email-action" onClick={() => void previewEmail()}>✉　邮件推送</button></div>
            </section>
          </aside> : <aside className="right-column"><section className="panel empty-detail"><span>{industry.icon}</span><h2>选择 {industry.label} 行业热点</h2><p>{dataMode === "empty" ? "该行业还没有真实运行结果。点击右上角“更新分析”，完成采集后可查看热点摘要、判断依据、传播来源和风险。" : dataMode === "offline" ? "请先启动 Python Agent，再加载该行业的真实热点。" : "正在读取最新一轮热点结果。"}</p></section></aside>}
        </div>
        </>}
      </section>
      {runLogs && <div className="drawer-backdrop" onMouseDown={() => setRunLogs(null)}><aside className="detail-drawer" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>真实运行记录</small><h2>Agent 执行日志</h2></div><button onClick={() => setRunLogs(null)}>×</button></div><div className="drawer-body log-list">{runLogs.length ? runLogs.map((log) => <div key={log.id} className={log.level}><time>{new Date(log.created_at).toLocaleTimeString("zh-CN", {hour12:false})}</time><b>{log.stage}</b><p>{log.message}</p></div>) : <p>等待 Agent 生成日志…</p>}</div></aside></div>}
      {evidencePayload && <div className="drawer-backdrop" onMouseDown={() => setEvidencePayload(null)}><aside className="detail-drawer evidence-drawer" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>事件状态：{evidencePayload.event_state} · 证据等级：{evidencePayload.evidence_grade} · 业务优先级：{evidencePayload.decision_priority}</small><h2>主张—证据矩阵｜{evidencePayload.title}</h2></div><button onClick={() => setEvidencePayload(null)}>×</button></div><div className="drawer-body"><section className="evidence-gate-summary"><b>{evidencePayload.event_gate_passed ? "已通过明确事件门槛" : "未通过明确事件门槛"}</b><p>{evidencePayload.event_gate_reason}</p><small>当前动作：{evidencePayload.current_action} · 责任角色：{evidencePayload.decision_owner}</small></section><section className="type-evidence-checklist"><h3>事件类型证据清单</h3>{evidencePayload.type_evidence_checklist.map((item) => <p key={item.label}><b>{item.label}</b><span>{item.status}</span></p>)}</section><section className="claim-matrix"><h3>已证实</h3>{evidencePayload.claims_matrix.verified.length ? evidencePayload.claims_matrix.verified.map((claim, index) => <p className="verified" key={`verified-${index}`}>✓ {claim.text}</p>) : <p>尚无达到“已证实”的原子主张。</p>}<h3>部分支持</h3>{evidencePayload.claims_matrix.partial.length ? evidencePayload.claims_matrix.partial.map((claim, index) => <p className="partial" key={`partial-${index}`}>△ {claim.text}</p>) : <p>尚无可标记为合理推断的主张。</p>}<h3>尚未证实</h3>{evidencePayload.claims_matrix.unverified.map((claim, index) => <p className="unverified" key={`unknown-${index}`}>? {claim.text}</p>)}<h3>缺失证据</h3>{evidencePayload.claims_matrix.missing_evidence.map((item) => <p key={item}>□ {item}</p>)}<h3>升级条件</h3><ol>{evidencePayload.claims_matrix.upgrade_conditions.map((item) => <li key={item}>{item}</li>)}</ol></section>{evidencePayload.sources.map((source) => <article className="source-evidence" key={`${source.source}-${source.url}`}><header><b>{source.title}</b><span>{source.evidence_role === "primary_fact" ? "一手事实" : source.evidence_role === "independent_confirm" ? "独立确认" : source.evidence_role === "adoption_signal" ? "采用信号" : source.evidence_role === "attention_signal" ? "关注信号" : source.evidence_role}</span></header><p><strong>发布链：</strong>{source.original_publisher_id || source.publisher_id || "未识别"}{source.is_repost ? "（转载）" : ""}</p><p><strong>可证明：</strong>{source.can_prove}</p><p><strong>不可证明：</strong>{source.cannot_prove}</p><p className="excerpt">{source.excerpt || "该来源没有可用的正文片段。"}</p><a href={source.url} target="_blank" rel="noreferrer">打开原文 ↗</a></article>)}<section className="counter-box"><h3>反方证据</h3>{evidencePayload.counter_evidence.length ? evidencePayload.counter_evidence.map((item) => <p key={item.source_url}>{item.claim} <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_title}</a></p>) : <p>{evidencePayload.counter_evidence_status}</p>}</section></div></aside></div>}
      {filterPayload && <div className="drawer-backdrop" onMouseDown={() => setFilterPayload(null)}><aside className="detail-drawer" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>口径分开：清洗、相关性、聚类、价值分层</small><h2>本轮筛选原因</h2></div><button onClick={() => setFilterPayload(null)}>×</button></div><div className="drawer-body filter-tree"><p><b>原始信息</b><strong>{filterPayload.raw}</strong></p><p>├─ 无效记录 <strong>{filterPayload.invalid}</strong></p><p>├─ 排除关键词 <strong>{filterPayload.excluded}</strong></p><p>├─ 精确重复 <strong>{filterPayload.duplicates}</strong></p><p>├─ 低相关性 <strong>{filterPayload.relevance_filtered}</strong></p><p>├─ 聚类合并 <strong>{filterPayload.cluster_merged}</strong></p><p>├─ 持续观察 <strong>{filterPayload.watchlist}</strong></p><p>├─ 候选线索 <strong>{filterPayload.candidate}</strong></p><p className="final">└─ 高价值热点 <strong>{filterPayload.high_value}</strong></p></div></aside></div>}
      {dataSources && <div className="drawer-backdrop" onMouseDown={() => setDataSources(null)}><aside className="detail-drawer source-drawer" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>只展示最新一轮真实采集结果</small><h2>{dataSources.task.topic}｜数据来源平台</h2></div><button onClick={() => setDataSources(null)}>×</button></div><div className="drawer-body source-overview"><div className="source-overview-summary"><p><b>{dataSources.items.filter((item) => item.status === "active").length}</b><span>有数据的平台</span></p><p><b>{dataSources.total_items}</b><span>本轮公开信息</span></p><p><b>{new Date(dataSources.completed_at).toLocaleString("zh-CN", {hour12:false})}</b><span>数据截止时间</span></p></div>{dataSources.items.map((source) => <article className={`source-platform-card ${source.status}`} key={source.id}><header><div><span className="source-platform-icon">{source.name.slice(0,2)}</span><div><h3>{source.name}</h3><small>{source.kind}</small></div></div><span className="source-state">{source.status === "active" ? `已采集 ${source.collected_count} 条` : "本轮 0 条"}</span></header><p className="source-role">{source.role}</p><div className="source-platform-metrics"><span>一手来源 <b>{source.primary_count}</b></span><span>进入候选事件 <b>{source.used_event_count}</b></span><span>{source.time_label} <b>{source.latest_published_at ? new Date(source.latest_published_at).toLocaleDateString("zh-CN") : "无"}</b></span></div>{source.publishers.length > 0 && <div className="publisher-list"><b>具体发布方</b>{source.publishers.map((publisher) => <span key={publisher.name}>{publisher.name} · {publisher.count}</span>)}</div>}{source.samples.length > 0 && <details><summary>查看本轮样本</summary><div className="source-samples">{source.samples.map((sample) => <a href={sample.url} target="_blank" rel="noreferrer" key={sample.id}><span>{sample.is_primary_source ? "一手" : "发现/讨论"}</span><div><b>{sample.title}</b><small>{sample.author || sample.hostname} · {new Date(sample.published_at).toLocaleString("zh-CN", {hour12:false})}</small></div>↗</a>)}</div></details>}{source.configured_feeds.length > 0 && <details><summary>查看已配置 RSS 地址（{source.configured_feeds.length}）</summary><div className="feed-list">{source.configured_feeds.map((feed) => <a href={feed} target="_blank" rel="noreferrer" key={feed}>{new URL(feed).hostname.replace(/^www\./, "")} ↗</a>)}</div></details>}{source.homepage && <a className="platform-home" href={source.homepage} target="_blank" rel="noreferrer">打开平台主页 ↗</a>}</article>)}</div></aside></div>}
      {scoringDiagnostics && <div className="drawer-backdrop" onMouseDown={() => setScoringDiagnostics(null)}><aside className="detail-drawer" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>区分历史迁移、数据缺失和真实低分</small><h2>价值分诊断</h2></div><button onClick={() => setScoringDiagnostics(null)}>×</button></div><div className="drawer-body scoring-diagnostics"><div className="diagnostic-stats"><p><b>{scoringDiagnostics.average_value_score}</b><span>平均价值分</span></p><p><b>{scoringDiagnostics.zero_value_events}</b><span>最新 0 分</span></p><p><b>{scoringDiagnostics.single_source_events}/{scoringDiagnostics.event_count}</b><span>单一来源</span></p><p><b>{scoringDiagnostics.no_positive_growth_events}/{scoringDiagnostics.event_count}</b><span>无正增长</span></p></div><h3>数据源分布</h3><div className="source-distribution">{scoringDiagnostics.source_distribution.map((item) => <p key={item.source}><span>{item.source}</span><b>{item.count} 条</b></p>)}</div><h3>诊断结论</h3><ul>{scoringDiagnostics.assessment.map((item) => <li key={item}>{item}</li>)}</ul><h3>各评分项为 0 的事件数</h3><div className="source-distribution">{Object.entries(scoringDiagnostics.component_zero_counts).map(([name,count]) => <p key={name}><span>{name}</span><b>{count}</b></p>)}</div></div></aside></div>}
      {deepAnalysis && <div className="drawer-backdrop" onMouseDown={() => setDeepAnalysis(null)}><aside className="detail-drawer deep-analysis-drawer" onMouseDown={(event) => event.stopPropagation()}><div className="drawer-head"><div><small>DeepAnalysisSkill · {deepAnalysis.generation_mode}</small><h2>深层原因、影响与发展预判</h2></div><button onClick={() => setDeepAnalysis(null)}>×</button></div><div className="drawer-body deep-analysis-body"><div className={`burst-status ${deepAnalysis.burst_status === "未证明爆发" ? "unproven" : ""}`}><b>{deepAnalysis.burst_status}</b><span>先判断是否真的爆发，再分析原因</span></div>{[["为什么爆发？",deepAnalysis.cause_analysis],["为什么传播？",deepAnalysis.propagation_analysis],["为什么有分歧？",deepAnalysis.disagreement_analysis]].map(([title,items]) => <section key={title as string}><h3>{title as string}</h3>{(items as EvidenceFinding[]).map((item) => <article className="reason-finding" key={`${title}-${item.dimension}`}><header><b>{item.dimension}</b><span className={`evidence-status ${item.evidence_status}`}>{item.evidence_status}</span></header><p>{item.conclusion}</p>{item.evidence_source_ids.length > 0 && <small>来源编号：{item.evidence_source_ids.join("、")}</small>}</article>)}</section>)}<section><h3>影响评估</h3><div className="impact-table"><div><b>影响对象</b><b>具体影响</b><b>程度</b><b>恢复周期</b></div>{deepAnalysis.impact_assessment.map((item) => <div key={item.affected_party}><span>{item.affected_party}</span><span>{item.concrete_impact}<small>{item.evidence_status}</small></span><span>{item.severity}</span><span>{item.recovery_cycle}</span></div>)}</div></section><section><h3>条件场景预判</h3>{deepAnalysis.scenarios.map((scenario) => <article className="scenario-card" key={scenario.name}><header><b>{scenario.name}</b><span>{scenario.likelihood}{scenario.probability_percent == null ? " · 不提供伪概率" : ` · ${scenario.probability_percent}%`}</span></header><p><strong>触发：</strong>{scenario.trigger}</p><p><strong>过程：</strong>{scenario.development}</p><p><strong>结果：</strong>{scenario.outcome}</p><small>依据：{scenario.basis}</small></article>)}</section><section><h3>关键观察点</h3><ul>{deepAnalysis.observation_points.map((item) => <li key={item}>{item}</li>)}</ul></section><section><h3>分角色建议</h3>{Object.entries(deepAnalysis.recommendations).map(([role,advice]) => <p key={role}><b>{role}：</b>{advice}</p>)}</section><section className="deep-limitations"><h3>数据限制</h3><ul>{deepAnalysis.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section><section><h3>引用来源</h3>{deepAnalysis.citations.map((item) => <a key={item.source_id} href={item.url} target="_blank" rel="noreferrer">[{item.source_id}] {item.title} ↗</a>)}</section></div></aside></div>}
      {emailPreview && <div className="modal-backdrop" role="presentation" onMouseDown={() => setEmailPreview(null)}>
        <section className="email-modal" role="dialog" aria-modal="true" aria-labelledby="email-title" onMouseDown={(event) => event.stopPropagation()}>
          <div className="email-modal-head"><div><small>AI 总结 → 人工确认 → 邮件</small><h2 id="email-title">邮件简报预览</h2></div><button onClick={() => setEmailPreview(null)} aria-label="关闭">×</button></div>
          <div className="email-meta"><p><b>主题</b>{emailPreview.subject}</p><p><b>收件人</b>{emailPreview.recipients.length ? emailPreview.recipients.join("、") : "尚未配置"}</p><p><b>入选热点</b>{emailPreview.selected_count} 个（均已人工确认）</p></div>
          <pre>{emailPreview.text}</pre>
          {!emailPreview.configured && <p className="email-warning">需要先在 agent_backend/.env 配置 SMTP_HOST、SMTP_USERNAME、SMTP_PASSWORD、EMAIL_RECIPIENTS。</p>}
          <div className="email-modal-actions"><button onClick={() => setEmailPreview(null)}>取消</button><button className="send" disabled={!emailPreview.configured || isSendingEmail} onClick={() => void confirmSendEmail()}>{isSendingEmail ? "发送中…" : "确认发送邮件"}</button></div>
        </section>
      </div>}
      {reportPreview && <div className="modal-backdrop" role="presentation" onMouseDown={() => setReportPreview(null)}>
        <section className="report-modal" role="dialog" aria-modal="true" aria-labelledby="report-title" onMouseDown={(event) => event.stopPropagation()}>
          <div className="email-modal-head"><div><small>AnalysisReportSkill · {reportPreview.generation_mode === "openai" ? "AI 归纳" : reportPreview.generation_mode === "rules_fallback" ? "AI 失败后规则降级" : "规则归纳"}</small><h2 id="report-title">{reportPreview.title}</h2></div><button onClick={() => setReportPreview(null)} aria-label="关闭">×</button></div>
          <div className="report-controls">
            <label>报告类型<select value={reportType} onChange={(event) => setReportType(event.target.value as "decision_brief" | "full_analysis")}><option value="full_analysis">完整分析报告</option><option value="decision_brief">管理层决策简报</option></select></label>
            <label>事件范围<select value={reportScope} onChange={(event) => setReportScope(event.target.value as "qualified" | "all_visible" | "approved_only")}><option value="qualified">合格事件优先（默认）</option><option value="approved_only">仅人工确认事件</option><option value="all_visible">全部可见事件（审计）</option></select></label>
            <button disabled={isGeneratingReport} onClick={() => void generateReport(reportType, reportScope)}>{isGeneratingReport ? "生成中…" : "按此配置重新生成"}</button>
          </div>
          <div className="report-body">
            <div className="report-meta"><span>{reportPreview.event_count} 个事件</span><span>{reportPreview.report_type === "full_analysis" ? "完整分析" : "决策简报"}</span><span>{reportPreview.scope === "approved_only" ? "仅人工确认" : reportPreview.scope === "qualified" ? "合格事件优先" : "全部可见审计"}</span></div>
            <section><h3>执行摘要</h3><p>{reportPreview.executive_summary}</p></section>
            <div className="report-columns"><section><h3>关键发现</h3><ol>{reportPreview.key_findings.map((item) => <li key={item}>{item}</li>)}</ol></section><section><h3>建议动作</h3><ol>{reportPreview.recommended_actions.map((item) => <li key={item}>{item}</li>)}</ol></section></div>
            <section className="report-limitations"><h3>限制与未知项</h3><ul>{reportPreview.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>
            <details className="report-markdown"><summary>查看 Skill 生成的完整报告正文</summary><pre>{reportPreview.markdown}</pre></details>
          </div>
          <div className="email-modal-actions"><button onClick={() => navigator.clipboard.writeText(reportPreview.markdown).then(() => notify("报告 Markdown 已复制"))}>复制 Markdown</button><button className="send" onClick={() => window.open(`${AGENT_API}${reportPreview.download_url}`, "_blank", "noopener,noreferrer")}>下载报告</button></div>
        </section>
      </div>}
      {toast && <div className="toast" role="status">{toast}</div>}
    </main>
  );
}
