# TrendScope 热点发现 Agent

TrendScope 从 GitHub、Hacker News、Google News、Google Trends、arXiv、DEV Community、V2EX、B站、中国新闻网、央视新闻和官方/媒体 RSS 采集公开信息，将“相关资讯”区分为高价值热点、持续观察和候选线索，并在人工确认后生成报告或邮件推送。

## 系统负责边界

程序计算：相关性、互动信号、来源数、平台数、增速、价值分、价值分层、事件真实性上限和聚类置信度。

AI 只负责：基于已保存材料生成摘要、影响、建议、风险表述和分析报告叙事。AI 不决定最终价值分，不能伪造来源、日期和互动量。

```text
真实采集 → 清洗去重 → 相关性过滤 → 事件聚类
→ 程序价值分层 → AI 文字总结 → 证据核查
→ 人工审核 → 报告/邮件
```

## GitHub 时间语义

- `repository_created`：使用 `created_at`，表示近期新建仓库。
- `repository_updated`：使用 `pushed_at`，只能表述为“近期活跃/近期更新”。
- 旧仓库的新 commit 不会被写成“今日发布”。

## 启动

```bash
cd agent_backend
python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp .env.example .env
./.venv/bin/python run_api.py
```

另一个终端：

```bash
npm install
npm run dev
```

访问 `http://localhost:3000`，API 文档为 `http://127.0.0.1:8000/docs`。

## Streamlit 单体部署

仓库同时提供 Streamlit Community Cloud 入口，直接复用 Python Agent 的真实采集、聚类、评分、人工审核和报告能力，不依赖 React 或单独启动 FastAPI。

本地运行：

```bash
cd agent_backend
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/streamlit run streamlit_app.py
```

Streamlit Community Cloud 创建应用时填写：

```text
Repository: raywang257-lab/-3--Agent
Branch: main
Main file path: agent_backend/streamlit_app.py
Python: 3.12
```

在 Advanced settings → Secrets 中配置 `OPENAI_API_KEY`、`AI_MODE`、`GITHUB_TOKEN` 和可选 SMTP 参数。不要提交 `.streamlit/secrets.toml`。云端本地 SQLite 只适合作业演示，容器重启后数据可能重置。

## AI 配置

```dotenv
AI_MODE=openai
OPENAI_API_KEY=你的Key
OPENAI_BASE_URL=https://api.exchangetoken.ai/v1
OPENAI_API_STYLE=chat_completions
OPENAI_MODEL=gpt-4.1-mini
```

未配置 Key 时设置 `AI_MODE=rules`，采集、去重、聚类、打分和入库仍会真实执行。

## 邮件配置

```dotenv
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USERNAME=发件邮箱
SMTP_PASSWORD=SMTP授权码
SMTP_USE_TLS=true
SMTP_USE_SSL=false
EMAIL_FROM=发件邮箱
EMAIL_RECIPIENTS=收件邮箱
```

邮件推送只读取“已人工确认”的热点，并必须先预览、再确认发送。

## 测试

```bash
cd agent_backend
./.venv/bin/python -m unittest discover -s tests -v
cd ..
npm test
```

## 完整 Demo

1. 选择 AI/科技/金融/生物行业。
2. 点击“更新分析”，在页面内查看实时日志。
3. 查看清洗、相关性过滤、聚类合并和价值分层数量。
4. 打开事件证据，核对 GitHub 创建/push 时间或新闻原文。
5. 对事件追问，查看程序分数、引用和未知项。
6. 填写审核理由后确认或驳回。
7. 下载报告，或预览并发送邮件。

## 分析报告 Skill

`AnalysisReportSkill` 是独立的后端能力，不是静态模板。它读取最新一轮真实事件、程序评分、人工审核状态和原始来源，可生成：

- `full_analysis`：执行摘要、关键发现、建议动作、逐事件证据和方法限制。
- `decision_brief`：面向管理层的短版决策简报。
- `all_visible`：全部未驳回事件。
- `approved_only`：仅人工确认事件；没有确认事件时拒绝生成。

LLM 可用时只归纳报告文字；网关异常时自动降级为规则报告。页面“分析报告”入口可预览、重新配置、复制 Markdown 和下载。

完整分析报告的逐事件正文直接由 `DeepAnalysisSkill` 生成，包括：爆发判断、深层原因、传播机制、分歧、影响表、三个条件场景、观察点、分角色建议、限制和引用。最高价值事件使用 LLM 深度归纳，其余事件使用同一 Skill 的确定性规则，避免一次报告产生大量模型调用；决策简报不运行逐事件深度分析。

```http
POST /api/reports/generate
Content-Type: application/json

{
  "task_id": 5,
  "report_type": "full_analysis",
  "scope": "all_visible",
  "max_events": 10
}
```

## 深层原因与发展预判 Skill

独立文件 `agent_backend/trendscope/deep_analysis_skill.py` 提供单事件深度分析：

- 先验证是否真的爆发，再分析直接触发、行业背景和用户情绪。
- 分析跨平台传播、平台推动证据和参与成本，但没有曝光数据时明确判为证据不足。
- 区分信息不对称、价值差异和身份利益；不从单篇新闻虚构群体冲突。
- 输出影响对象、具体影响、严重程度和恢复周期，并标记证据状态。
- 输出三个条件场景和关键观察点；没有预测模型时不编造 60%/25%/15% 概率。
- 每项判断标记“已验证 / 合理推断 / 证据不足”，引用编号只允许来自真实入库来源。

```http
POST /api/hotspots/{event_id}/deep-analysis
Content-Type: application/json

{
  "audience": "产品、研究、媒体与相关决策者",
  "horizon_days": 7
}
```

价值分诊断接口为 `GET /api/scoring-diagnostics?task_id=5`。旧版评分字段迁移产生的历史 0 分会在数据库初始化时按已保存指标自动回填；真正的低分仍会保留，并解释是缺少增速、跨平台覆盖、独立来源还是关注信号。

## 数据源分层

- 一手事实与研究：官方 RSS、GitHub、arXiv。
- 新闻发现：Google News、行业媒体 RSS。
- 开发者采用与讨论：Hacker News、DEV Community、V2EX。
- 中文内容传播：B站搜索。
- 中文权威新闻：中国新闻网官方主题搜索/RSS、央视网科技/经济/健康新闻接口。
- 搜索关注：Google Trends。

Reddit、X、小红书需要登录态或额外后端，当前环境未配置，因此没有伪装成默认可用来源。GDELT 实测受到 429 限流，也未加入生产链路。单个来源失败时只记录警告，不会拖垮整轮任务。

## 已知限制

- Google News RSS 是发现源，不等于 Google 官方公告。
- 首轮没有历史快照，增速贡献固定为 0。
- “反方材料”只从本轮已采集内容中提取；没有可回溯来源时会明确显示未发现。
- 本地 SQLite 和进程内调度器适合作业 Demo，不是分布式生产架构。
