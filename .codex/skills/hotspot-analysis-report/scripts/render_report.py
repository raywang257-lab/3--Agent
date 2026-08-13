#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def eligible(event: dict) -> bool:
    return event.get("review", {}).get("status") == "approved" or (
        event.get("value_level") in {"high_value", "watchlist"}
        and int(event.get("source_count") or 0) >= 2
    )


def render(payload: dict) -> str:
    events = payload.get("events") or []
    if not events:
        raise ValueError("events 不能为空")
    qualified = [event for event in events if eligible(event)]
    selected = qualified or sorted(events, key=lambda event: float(event.get("value_score") or 0), reverse=True)[:3]
    high = [event for event in qualified if event.get("value_level") == "high_value"]
    topic = payload.get("topic") or "热点"
    title = f"{topic}热点分析报告" if qualified else f"{topic}候选线索监测简报"
    outcome = (
        f"本轮发现 {len(high)} 个达到高价值阈值的热点。"
        if high else "本轮没有发现达到高价值阈值的热点。"
    )
    if not qualified:
        outcome += " 当前不应形成外部趋势判断或资源投入结论。"

    sources: list[str] = []
    cards: list[str] = []
    source_index = 1
    for position, event in enumerate(selected, start=1):
        refs = []
        for source in event.get("sources") or []:
            ref = f"S{source_index}"
            source_index += 1
            refs.append(ref)
            sources.append(f"- [{ref}] [{source['title']}]({source['url']})（{source.get('source', 'unknown')}）")
        if not refs:
            raise ValueError(f"事件 {event.get('id', position)} 没有来源")
        if event.get("value_level") == "candidate":
            cards.extend([
                f"### 候选 {position}. {event['canonical_title']}", "",
                f"- 当前分层：候选线索，{float(event.get('value_score') or 0):.1f} 分。",
                f"- 已证实：存在可回溯来源。[{refs[0]}]",
                "- 尚未证实：跨平台传播、持续增长和广泛采用。",
                "- 升级条件：出现第二独立发布方或下一轮可验证正增长。",
                "- 当前允许动作：核对原文、持续监控、补充来源或低成本内部测试。",
                "- 禁止结论：不得称为行业热点，不得建议合作、部署或投入。", "",
            ])
        else:
            cards.extend([
                f"### {position}. {event['canonical_title']}", "",
                f"- 程序判断：{event.get('action_level')}｜{event.get('value_level')}｜{float(event.get('value_score') or 0):.1f} 分",
                f"- 证据引用：{', '.join(f'[{ref}]' for ref in refs)}", "",
            ])

    run = payload.get("run") or {}
    diagnostics = [
        f"- 原始信息：{run.get('items_collected', 0)} 条",
        f"- 候选事件：{run.get('candidates_created', len(events))} 个",
        f"- 报告事件：{len(selected)} 个",
    ]
    actions = ["- 为候选补充第二独立发布方并记录下一轮快照。"] if not qualified else ["- 按程序分层执行核验和跟进。"]
    limitations = payload.get("limitations") or ["当前来源和历史快照不足以支持更强结论。"]
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# {title}", "",
        f"> 生成时间：{generated_at}｜数据运行：`{run.get('id', 'unknown')}`", "",
        "## 本轮结论", "", outcome, "",
        "## 数据质量", "", *diagnostics, "",
        "## 关键事件或候选线索", "", *cards,
        "## 建议动作", "", *actions, "",
        "## 限制与未知项", "", *[f"- {item}" for item in limitations], "",
        "## 方法与版本", "",
        f"- 评分模型：{run.get('scoring_model_version', 'unknown')}",
        f"- 分析提示词：{run.get('analysis_prompt_version', 'unknown')}", "",
        "## 来源", "", *sources, "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an evidence-bounded TrendScope report")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
