from unittest import TestCase

from trendscope.report_skill import AnalysisReportSkill, REPORT_CONTRACT_PATH, REPORT_SKILL_ROOT


class AnalysisReportSkillTests(TestCase):
    def test_project_skill_contract_is_loaded_from_codex_directory(self):
        self.assertTrue((REPORT_SKILL_ROOT / "SKILL.md").exists())
        self.assertTrue(REPORT_CONTRACT_PATH.exists())
        self.assertIn("Google Trends", REPORT_CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_rule_report_does_not_promote_candidates_to_hotspots(self):
        narrative = AnalysisReportSkill._rule_narrative(
            {"target_role": "产品负责人"},
            {"warnings": [], "items_collected": 8, "candidates_created": 1},
            [{
                "canonical_title": "测试候选事件", "value_level": "candidate", "value_score": 32.0,
                "action_level": "谨慎验证", "why_now": "只有单一来源。",
                "recommended_action": "等待第二信源。", "source_count": 1, "growth_percent": None,
            }],
        )
        self.assertIn("没有达到高价值阈值", narrative.executive_summary)
        self.assertTrue(any("一个来源" in item for item in narrative.limitations))
        self.assertTrue(any("无法证明真实增速" in item for item in narrative.limitations))

    def test_event_payload_keeps_citations_and_program_judgment(self):
        payload = AnalysisReportSkill._event_payload({
            "canonical_title": "事件", "summary": "摘要", "why_now": "原因", "impact": "影响",
            "recommended_action": "观察", "risk": "单一来源", "value_score": 51.0,
            "value_level": "watchlist", "action_level": "持续观察", "truth_status": "中等",
            "cluster_confidence": "不适用", "growth_percent": None, "source_count": 1,
            "platform_count": 1,
            "sources": [{"title": "原文", "url": "https://example.com/source", "source": "rss"}],
        })
        self.assertEqual(payload["value_level"], "watchlist")
        self.assertEqual(payload["sources"][0]["url"], "https://example.com/source")

    def test_quality_gate_downgrades_multi_source_event_without_fact_qualification(self):
        events, warnings = AnalysisReportSkill._quality_gate([{
            "id": 7, "canonical_title": "OpenAI releases model", "value_level": "watchlist",
            "action_level": "持续观察", "source_count": 2, "cluster_confidence": "中等",
            "evidence_tier": "single_source",
            "sources": [{"title": "OpenAI releases model", "url": "https://example.com/source"}],
        }])
        self.assertEqual(events[0]["value_level"], "candidate")
        self.assertEqual(events[0]["action_level"], "谨慎验证")
        self.assertTrue(any("事实证据门槛" in warning for warning in warnings))
