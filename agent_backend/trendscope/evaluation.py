from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


EXPECTED = {"high_value": 10, "watchlist": 15, "candidate": 15, "noise": 10}


def human_dataset_status(path: Path) -> dict:
    rows = []
    errors = []
    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"第 {line_number} 行不是合法 JSON：{exc.msg}")
                continue
            missing = {"event_id", "title", "label", "evidence_urls", "labeler", "labeled_at", "reason"} - set(row)
            if missing:
                errors.append(f"第 {line_number} 行缺少字段：{', '.join(sorted(missing))}")
                continue
            if row["label"] not in EXPECTED:
                errors.append(f"第 {line_number} 行标签无效：{row['label']}")
                continue
            if not row["evidence_urls"]:
                errors.append(f"第 {line_number} 行没有证据链接")
                continue
            rows.append(row)
    distribution = Counter(row["label"] for row in rows)
    deficits = {label: max(0, count - distribution[label]) for label, count in EXPECTED.items()}
    return {
        "ready": not errors and not any(deficits.values()),
        "dataset_type": "human_labeled_real_events",
        "row_count": len(rows),
        "distribution": dict(distribution),
        "required_distribution": EXPECTED,
        "deficits": deficits,
        "errors": errors,
        "message": "评测集已就绪" if not errors and not any(deficits.values()) else "真实评测集尚未完成，禁止报告精确率或召回率。",
    }
