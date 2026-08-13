from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import EventCandidate, SourceItem, SourceMetrics
from .processing import apply_program_judgement


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    expected_level: str
    relevance: float
    growth: float | None
    platforms: int
    independent_publishers: int
    attention: float


def _cases() -> list[CalibrationCase]:
    """50 条固定校准样本；用于阈值回归，不冒充真实世界准确率评测。"""
    result: list[CalibrationCase] = []
    for index in range(10):
        result.append(CalibrationCase(
            f"high-{index + 1}", "high_value", 82 + index, 80 + index * 2,
            3 + index % 2, 3 + index % 3, 82 + index,
        ))
    for index in range(15):
        result.append(CalibrationCase(
            f"watch-{index + 1}", "watchlist", 68 + index % 8, 35 + index % 10,
            2, 2, 58 + index % 12,
        ))
    for index in range(15):
        result.append(CalibrationCase(
            f"candidate-{index + 1}", "candidate", 42 + index % 12, None,
            1, 1, 35 + index % 15,
        ))
    for index in range(10):
        result.append(CalibrationCase(
            f"noise-{index + 1}", "candidate", 2 + index, None, 1, 1, 2 + index,
        ))
    return result


CALIBRATION_CASES = tuple(_cases())


def evaluate_scoring_calibration() -> dict:
    confusion: Counter[tuple[str, str]] = Counter()
    rows = []
    for case in CALIBRATION_CASES:
        now = datetime.now(timezone.utc)
        items = [SourceItem(
            source="rss", external_id=f"{case.case_id}-primary", title=case.case_id,
            url=f"https://official.example/{case.case_id}", published_at=now,
            is_primary_source=True, evidence_role="primary_fact", publisher_id="publisher:official",
            event_type="release_published", released_at=now,
        )]
        if case.independent_publishers >= 2:
            items.append(SourceItem(
                source="google_news", external_id=f"{case.case_id}-confirm", title=case.case_id,
                url=f"https://media.example/{case.case_id}", published_at=now,
                evidence_role="independent_confirm", publisher_id="publisher:media",
            ))
        if case.expected_level == "high_value":
            items.append(SourceItem(
                source="github", external_id=f"{case.case_id}-adoption", title=case.case_id,
                url=f"https://github.com/example/{case.case_id}", published_at=now,
                metrics=SourceMetrics(stars=1000), is_primary_source=True,
                evidence_role="adoption_signal", publisher_id="publisher:github-example",
            ))
        candidate = EventCandidate(
            candidate_id=case.case_id, canonical_title=case.case_id, items=items,
            relevance_score=case.relevance, attention_signal=case.attention,
            platform_count=case.platforms, source_count=case.independent_publishers,
            growth_percent=case.growth, growth_label="持续增长" if case.expected_level == "high_value" else "初步增长信号" if case.expected_level == "watchlist" else "无增长基线",
            lifecycle="萌芽" if case.expected_level in {"high_value", "watchlist"} else "未知",
        )
        predicted = apply_program_judgement(candidate).value_level
        confusion[(case.expected_level, predicted)] += 1
        rows.append({"case_id": case.case_id, "expected": case.expected_level, "predicted": predicted})
    correct = sum(count for (expected, predicted), count in confusion.items() if expected == predicted)
    return {
        "dataset_type": "fixed_synthetic_calibration",
        "disclaimer": "验证阈值可达性与代码回归，不代表真实世界精确率或召回率。",
        "case_count": len(CALIBRATION_CASES),
        "accuracy": round(correct / len(CALIBRATION_CASES), 4),
        "confusion_matrix": {
            f"{expected}->{predicted}": count for (expected, predicted), count in sorted(confusion.items())
        },
        "rows": rows,
    }
