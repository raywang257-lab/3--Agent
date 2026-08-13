import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../app/page.tsx", import.meta.url);
const layoutUrl = new URL("../app/layout.tsx", import.meta.url);

test("TrendScope page exposes the real agent workflow", async () => {
  const [page, layout] = await Promise.all([
    readFile(pageUrl, "utf8"),
    readFile(layoutUrl, "utf8"),
  ]);
  assert.match(layout, /TrendScope 热点决策台/);
  assert.match(page, /更新分析/);
  assert.match(page, /查看执行日志/);
  assert.match(page, /查看矩阵/);
  assert.match(page, /补充证据并重新判断/);
  assert.match(page, /尚未形成传播路径/);
  assert.doesNotMatch(page, /AI 热点已载入/);
  assert.match(page, /industries\.map/);
  assert.match(page, /Python Agent 未连接/);
  assert.match(page, /行业态势/);
  assert.match(page, /热点发现 Agent 工作流/);
  assert.match(page, /真实来源 → 清洗去重 → 合并事件 → AI总结 → 价值判断 → 人工确认 → 报告与邮件/);
  assert.match(page, /候选事件平均价值分，不等同市场规模/);
  assert.match(page, /态势标签占比/);
  assert.match(page, /具身智能/);
  assert.match(page, /智能体 \/ Agent/);
  assert.match(page, /支付与数字银行/);
  assert.match(page, /AI 药物发现/);
  assert.match(page, /每个事件只计入一个最匹配的主标签/);
  assert.match(page, /待细分科技事件/);
  assert.match(page, /待细分金融事件/);
  assert.match(page, /tag-event-list/);
  assert.doesNotMatch(page, /其他前沿科技/);
  assert.doesNotMatch(page, /其他金融科技/);
  assert.doesNotMatch(page, /战略相关性/);
  assert.match(page, /发布事实可核验/);
  assert.match(page, /事实状态/);
  assert.match(page, /趋势状态/);
  assert.match(page, /业务优先级/);
  assert.match(page, /当前动作/);
  assert.match(page, /规则摘要/);
  assert.match(page, /事件类型证据清单/);
  assert.doesNotMatch(page, /达到事实门槛/);
});

test("page does not ship hard-coded demo hotspots or fake features", async () => {
  const page = await readFile(pageUrl, "utf8");
  assert.doesNotMatch(page, /demoHotspots/);
  assert.doesNotMatch(page, /Cursor 发布新版本/);
  assert.doesNotMatch(page, /专题分析/);
  assert.doesNotMatch(page, /设置预警/);
  assert.doesNotMatch(page, /详情为演示入口/);
  assert.doesNotMatch(page, /const series24/);
  assert.doesNotMatch(page, /const series7/);
});
