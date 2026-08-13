# TrendScope 人工标注评测集

`human_labeled_events.jsonl` 用于真实世界精确率、召回率和混淆矩阵评测。每行一个 JSON：

```json
{"event_id":"2026-001","title":"...","label":"high_value","evidence_urls":["https://..."],"labeler":"姓名","labeled_at":"2026-08-13","reason":"..."}
```

标签只能是 `high_value`、`watchlist`、`candidate`、`noise`。每条至少包含一个可访问证据链接、标注人、日期和理由。目标构成为：10 个高价值、15 个持续观察、15 个普通相关资讯、10 个噪声。

仓库不会预填虚构标签。未达到 50 条且类别配额不足时，接口必须返回 `ready=false`，不得宣称拥有真实世界准确率。

另有 `/api/benchmark/scoring` 的 50 条固定合成校准样本，只验证三档阈值可达和代码回归，不等于真实评测集。
