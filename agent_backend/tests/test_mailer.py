import unittest
from types import SimpleNamespace

from trendscope.mailer import build_email_brief, mask_email


class MailerTests(unittest.TestCase):
    def test_builds_brief_from_approved_event_payload(self):
        task = SimpleNamespace(topic="人工智能")
        run = {
            "completed_at": "2026-08-12T10:00:00+00:00",
            "candidates_created": 8,
            "events_created": 3,
        }
        events = [{
            "canonical_title": "AI Agent 新闻",
            "summary": "AI 生成的事件摘要",
            "why_now": "官方发布后升温",
            "recommended_action": "立即跟进",
            "risk": "尚缺独立评测",
            "truth_status": "较高",
            "sources": [{"title": "官方公告", "url": "https://example.com", "source": "rss"}],
        }]

        brief = build_email_brief(task, run, events)

        self.assertEqual(brief["selected_count"], 1)
        self.assertIn("AI 生成的事件摘要", brief["text"])
        self.assertIn("8 个候选 → 3 个入选", brief["html"])

    def test_refuses_empty_approved_list(self):
        with self.assertRaises(ValueError):
            build_email_brief(SimpleNamespace(topic="AI"), {}, [])

    def test_masks_recipient(self):
        self.assertEqual(mask_email("person@example.com"), "pe***@example.com")


if __name__ == "__main__":
    unittest.main()
