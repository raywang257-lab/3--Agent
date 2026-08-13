from unittest import TestCase

from trendscope.deep_analysis_skill import DeepAnalysisSkill


class DeepAnalysisSkillTests(TestCase):
    def test_does_not_invent_burst_or_probabilities_without_growth(self):
        event = {
            "id": 8, "growth_percent": None, "platform_count": 1, "source_count": 1,
            "why_now": "价值分较低", "impact": "产品团队", "debate": "信息不足",
            "recommended_action": "等待更多来源。",
            "sources": [{"id": 3, "title": "原文", "url": "https://example.com", "source": "rss"}],
        }
        result = DeepAnalysisSkill._rule_result(event, None, 7)
        self.assertEqual(result.burst_status, "未证明爆发")
        self.assertTrue(all(scenario.probability_percent is None for scenario in result.scenarios))
        self.assertEqual(result.cause_analysis[0].evidence_status, "证据不足")

    def test_sanitizer_removes_hallucinated_source_ids(self):
        event = {
            "growth_percent": None,
            "sources": [{"id": 3, "title": "原文", "url": "https://example.com"}],
        }
        result = DeepAnalysisSkill._rule_result({
            "id": 8, "growth_percent": None, "platform_count": 1, "source_count": 1,
            "why_now": "信息不足", "impact": "产品团队", "debate": "信息不足",
            "recommended_action": "观察", "sources": [{"id": 3, "title": "原文", "url": "https://example.com", "source": "rss"}],
        }, None, 7)
        result.propagation_analysis[0].evidence_source_ids.append(999)
        cleaned = DeepAnalysisSkill._sanitize(result, event)
        self.assertNotIn(999, cleaned.propagation_analysis[0].evidence_source_ids)
