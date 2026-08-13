# TrendScope 独立热点 Agent（PyCharm 版）

这个目录是项目的 Python 后端。它已经完成以下真实链路：

```text
监控任务
→ GitHub / Hacker News / Google News / Google Trends / RSS 真实采集
→ 清洗与 URL 去重
→ 相关性计算
→ 同一事件聚类与跨轮次稳定身份
→ 历史指标比较
→ 程序价值打分与三层分类
→ OpenAI 结构化分析（可选）
→ SQLite 保存
→ Markdown 报告
→ FastAPI 输出
→ APScheduler 定时运行
```

## 1. 在 PyCharm 中打开

推荐直接将 `agent_backend` 作为 PyCharm 项目打开，而不是打开上层前端目录。

目录位置：

```text
作业3-热点Agent/agent_backend
```

## 2. 配置 Python Interpreter

本项目已经创建本地虚拟环境：

```text
agent_backend/.venv/bin/python
```

PyCharm 设置路径：

```text
Settings
→ Project: agent_backend
→ Python Interpreter
→ Add Interpreter
→ Add Local Interpreter
→ Existing
→ 选择 .venv/bin/python
```

Windows 用户应重新创建虚拟环境，不要复制 macOS 的 `.venv`：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. 配置环境变量

复制环境模板：

```text
.env.example → .env
```

### 无 Key 模式

第一次运行使用：

```dotenv
AI_MODE=rules
```

这种模式仍然使用真实公开数据、数据库、聚类、指标和报告，只是不调用大模型。

### OpenAI 模式

在 OpenAI 平台创建 API Key 后配置：

```dotenv
AI_MODE=openai
OPENAI_API_KEY=你的Key
OPENAI_MODEL=gpt-5.6-terra
```

Key 只能保存在 `.env` 或部署平台的 Secret 中，不要写进 Python 文件，也不要提交到 Git。

### GitHub Token

不配置 Token 也能运行，但匿名 GitHub API 限额较低。建议配置：

```dotenv
GITHUB_TOKEN=你的GitHubToken
```

只授予读取公开仓库所需的最小权限。

### RSS 来源

多个地址用英文逗号分隔：

```dotenv
RSS_FEEDS=https://example.com/feed.xml,https://example.org/rss
```

RSS 内容仍会经过关键词过滤，不是订阅源中的全部文章都会进入结果。

Google 数据源由程序自动生成：

- Google News RSS：根据每个监控任务的主题和关键词生成中英文新闻查询；
- Google Trends RSS：读取美国区实时搜索趋势，只有与监控主题相关时才进入候选；
- Google AI、DeepMind、Google Research、Google Developers、Google Cloud RSS：作为 Google 官方一手信源。

Google News 是新闻聚合源，不会被标记为 Google 官方公告。

## 4. 在 PyCharm 中执行一次 Agent

右键运行：

```text
run_once.py
```

正确结果会显示：

```text
status: completed
items_collected: 实际采集数量
events_created: 合并后的事件数量
```

结果同时保存在：

```text
data/trendscope.db
reports/trend-report-XXXXXXXX.md
```

## 5. 启动 API 服务

右键运行：

```text
run_api.py
```

然后访问：

```text
http://127.0.0.1:8000/docs
```

这是 FastAPI 自动生成的接口操作页面。

主要接口：

| 方法 | 地址 | 用途 |
|---|---|---|
| GET | `/health` | 检查服务、AI模式和定时器 |
| GET | `/api/tasks` | 查看监控任务 |
| POST | `/api/agent-runs` | 异步启动一轮 Agent |
| POST | `/api/agent-runs/sync` | 同步执行一轮，适合调试 |
| GET | `/api/agent-runs/{run_id}` | 查询状态和完整日志 |
| GET | `/api/agent-runs/{run_id}/logs` | 查询页面实时执行日志 |
| GET | `/api/hotspots` | 获取最近一轮热点 |
| GET | `/api/hotspots/{event_id}/evidence` | 查看来源字段与证据边界 |
| POST | `/api/hotspots/{event_id}/ask` | 基于已保存证据追问 |
| GET | `/api/filtering-reasons` | 查看清洗、相关性、聚类和价值分层口径 |
| GET | `/api/dashboard-summary` | 获取真实处理漏斗、来源覆盖和运行警告 |
| POST | `/api/hotspots/{event_id}/review` | 人工确认、驳回或恢复待审热点 |
| GET | `/api/reports/latest` | 下载指定任务的最新 Markdown 报告 |
| POST | `/api/scheduler/run-now` | 立即执行所有启用任务 |

异步启动请求体：

```json
{
  "task_id": 1
}
```

## 6. 开启自动运行

编辑 `.env`：

```dotenv
SCHEDULE_ENABLED=true
SCHEDULE_MINUTES=60
```

只要 `run_api.py` 服务持续运行，Agent 就会每60分钟执行一次。

注意：关闭 PyCharm 或停止 Python 进程后，本地定时器也会停止。真正全天运行需要把这个后端部署到持续在线的服务器、容器或云 Worker。

## 7. 修改监控主题

第一版默认任务由 `trendscope/models.py` 中的 `MonitoringTask` 定义。

修改关键词后，如果数据库已经创建，需要：

1. 通过数据库工具修改 `monitoring_tasks` 表；或
2. 删除本地测试数据库 `data/trendscope.db` 后重新启动，让程序重建默认任务。

正式版本应该增加监控任务的创建和修改 API，而不是长期依赖修改源码。

## 8. 对接现有 TrendScope 面板

前端运行在 `http://localhost:3000`，Python API 运行在 `http://127.0.0.1:8000`。

前端已经直接读取：

```ts
const response = await fetch("http://127.0.0.1:8000/api/hotspots");
const data = await response.json();
```

点击“更新分析”时调用：

```ts
await fetch("http://127.0.0.1:8000/api/agent-runs", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ task_id: 1 }),
});
```

当前 Python API 已允许 `localhost:3000` 跨域访问。

## 9. 生产部署前必须补充

当前版本适合作业 Demo 和本地验证。生产化还需要：

1. 用户认证；
2. API访问控制；
3. PostgreSQL 等服务器数据库；
4. 真正的任务队列；
5. 分布式锁，避免重复运行；
6. Secret 管理；
7. 速率限制和成本上限；
8. Webhook签名验证；
9. 人工审批和推送渠道；
10. 评测集与回归测试。

## 10. 故障判断

### GitHub 为0条

- 检查网络；
- 检查关键词是否过窄；
- 检查匿名API是否触发限额；
- 配置 `GITHUB_TOKEN`。

### AI_MODE 显示 rules

说明以下至少一项未满足：

- `AI_MODE=openai`；
- `.env` 位于 `agent_backend` 根目录；
- `OPENAI_API_KEY` 非空；
- 重启了 Python 服务。

### 一个来源失败

Agent 会记录 warning 并继续处理其他来源。查看：

```text
GET /api/agent-runs/{run_id}
```

不要把失败来源写入最终“已覆盖来源”统计。
# 当前能力边界与评测

- 产品定位是“多源热点候选雷达”，不是未经验证的自动热点决策系统。
- `/api/benchmark/scoring` 使用 50 条固定合成样本验证三档阈值可达性，不代表真实世界准确率。
- `/api/evaluation/human-dataset` 展示人工标注真实评测集是否达到 50 条和类别配额；未就绪时禁止报告精确率、召回率。
- 当前评分模型版本：`evidence-zero-baseline-v2`。历史版本运行不会混入新版首页。
- AI 每批最多分析 5 条，只处理前 10 个候选；其余候选使用确定性规则，避免网关延迟拖垮现场 Demo。
- 跨平台聚类要求共享明确产品、公司或模型实体，泛化的 AI/Agent/Model 等词不能形成跨平台证据。
