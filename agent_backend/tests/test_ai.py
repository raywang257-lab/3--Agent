import json
from unittest import TestCase

from trendscope.ai import _parse_analysis_batch
from trendscope.models import EventCandidate, MonitoringTask, SourceItem, SourceMetrics
from datetime import datetime, timezone


EVENT = {
    "candidate_id": "event-1",
    "is_relevant": True,
    "canonical_title": "AI 编程工具发布新版本",
    "category": "AI 开发工具",
    "summary": "官方发布了新版本。",
    "why_now": "新版本刚发布。",
    "debate": "信息不足",
    "impact": "影响开发者工作流。",
    "recommended_action": "核对官方公告并继续观察。",
    "risk": "缺少独立测评。",
    "truth_status": "较高",
    "cluster_confidence": "较高",
    "action_level": "持续观察",
}


class AnalysisParsingTests(TestCase):
    def setUp(self):
        self.task = MonitoringTask()
        item = SourceItem(
            source="github",
            external_id="1",
            title="AI coding tool release",
            url="https://example.com/release",
            published_at=datetime.now(timezone.utc),
            metrics=SourceMetrics(stars=100),
        )
        self.candidates = [EventCandidate(
            candidate_id="event-1",
            canonical_title=item.title,
            items=[item],
            relevance_score=0.9,
            attention_signal=100,
            platform_count=1,
            source_count=1,
        )]

    def make_candidate(self, candidate_id: str, title: str) -> EventCandidate:
        source = SourceItem(
            source="rss", external_id=candidate_id, title=title,
            url=f"https://example.com/{candidate_id}", published_at=datetime.now(timezone.utc),
        )
        return EventCandidate(
            candidate_id=candidate_id, canonical_title=title, items=[source],
            relevance_score=50, attention_signal=8, platform_count=1, source_count=1,
        )

    def test_parses_standard_batch(self):
        parsed, repaired = _parse_analysis_batch(
            json.dumps({"events": [EVENT]}), self.candidates, self.task
        )
        self.assertEqual(parsed.events[0].candidate_id, "event-1")
        self.assertEqual(repaired, 0)

    def test_wraps_single_event(self):
        parsed, _ = _parse_analysis_batch(json.dumps(EVENT), self.candidates, self.task)
        self.assertEqual(len(parsed.events), 1)

    def test_wraps_event_list(self):
        parsed, _ = _parse_analysis_batch(json.dumps([EVENT]), self.candidates, self.task)
        self.assertEqual(len(parsed.events), 1)

    def test_missing_candidate_id_is_rejected_instead_of_bound_by_position(self):
        partial = {
            "canonical_title": "AI 编程工具发布新版本",
            "summary": "只返回了部分字段。",
            "recommended_action": "继续观察。",
        }
        parsed, repaired = _parse_analysis_batch(
            json.dumps({"events": [partial]}), self.candidates, self.task
        )
        self.assertEqual(parsed.events, [])
        self.assertGreater(repaired, 0)

    def test_reordered_events_stay_bound_by_candidate_id(self):
        first = self.make_candidate("first", "First source title")
        second = self.make_candidate("second", "Second source title")
        event_one = EVENT | {"candidate_id": "first", "canonical_title": "First source title", "summary": "first"}
        event_two = EVENT | {"candidate_id": "second", "canonical_title": "Second source title", "summary": "second"}
        parsed, _ = _parse_analysis_batch(
            json.dumps({"events": [event_two, event_one]}), [first, second], self.task,
        )
        by_id = {event.candidate_id: event for event in parsed.events}
        self.assertEqual(by_id["first"].summary, "first")
        self.assertEqual(by_id["second"].summary, "second")

    def test_unknown_candidate_id_is_discarded(self):
        parsed, repaired = _parse_analysis_batch(
            json.dumps({"events": [EVENT | {"candidate_id": "unknown"}]}), self.candidates, self.task,
        )
        self.assertEqual(parsed.events, [])
        self.assertGreater(repaired, 0)
