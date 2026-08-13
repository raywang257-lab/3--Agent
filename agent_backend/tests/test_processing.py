from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from trendscope.database import Database
from trendscope.models import MonitoringTask, SourceItem, SourceMetrics
from trendscope.processing import (
    actual_cluster_merge_count, canonical_url, cluster_items, compare_event_signatures, extract_event_signature,
    finalize_business_decision, passes_source_gate, prepare_items, relevance_score, rule_analysis,
)


def item(source: str, external_id: str, title: str, url: str) -> SourceItem:
    return SourceItem(
        source=source,
        external_id=external_id,
        title=title,
        url=url,
        published_at=datetime.now(timezone.utc),
        metrics=SourceMetrics(score=20, comments=10, stars=100),
    )


class ProcessingTests(TestCase):
    def test_canonical_url_removes_tracking(self):
        self.assertEqual(
            canonical_url("https://Example.com/news/?utm_source=x&id=2#top"),
            "https://example.com/news?id=2",
        )

    def test_prepare_items_deduplicates_url(self):
        task = MonitoringTask()
        items = [
            item("github", "1", "AI coding agent", "https://example.com/a?utm_source=x"),
            item("rss", "2", "AI coding agent release", "https://example.com/a"),
        ]
        cleaned, removed = prepare_items(items, task)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(removed["duplicate"], 1)

    def test_cluster_similar_titles(self):
        task = MonitoringTask()
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidates = cluster_items([
                item("github", "1", "Cursor AI coding agent release", "https://example.com/a"),
                item("hacker_news", "2", "Cursor releases new AI coding agent", "https://example.com/b"),
            ], task, db)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].platform_count, 2)
        self.assertEqual(actual_cluster_merge_count([
            item("github", "1", "Cursor AI coding agent release", "https://example.com/a"),
            item("hacker_news", "2", "Cursor releases new AI coding agent", "https://example.com/b"),
        ], task), 1)

    def test_generic_ai_words_do_not_merge_unrelated_cross_platform_events(self):
        task = MonitoringTask(keywords=["generative AI", "AI agent"])
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidates = cluster_items([
                item("github", "generic-1", "pranay/generative-ai-projects 近期活跃", "https://github.com/pranay/generative-ai-projects"),
                item("google_news", "generic-2", "Streamflow From Generative AI", "https://news.example.com/streamflow"),
            ], task, db)
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate.platform_count == 1 for candidate in candidates))

    def test_named_product_and_same_action_merge_across_platforms(self):
        task = MonitoringTask(keywords=["GPT-5", "OpenAI", "AI model"])
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidates = cluster_items([
                item("rss", "gpt5-official", "OpenAI releases GPT-5 model", "https://openai.com/gpt-5"),
                item("hacker_news", "gpt5-discussion", "GPT-5 release discussion", "https://news.ycombinator.com/item?id=5"),
            ], task, db)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].platform_count, 2)
        self.assertEqual(candidates[0].source_count, 2)

    def test_event_signature_explains_structured_cross_source_match(self):
        left = item("rss", "official", "OpenAI releases GPT-5 model", "https://openai.com/gpt-5")
        right = item("google_news", "media", "GPT-5 release announced by OpenAI", "https://example.com/gpt5")
        same, confidence, reasons = compare_event_signatures(
            extract_event_signature(left), extract_event_signature(right),
        )
        self.assertTrue(same)
        self.assertGreaterEqual(confidence, 0.7)
        self.assertTrue(any("共同实体" in reason for reason in reasons))

    def test_different_github_repositories_never_merge_on_release_word(self):
        left = item("github", "repo-a", "Acme Agent Release v1", "https://github.com/acme/agent/releases/tag/v1")
        right = item("github", "repo-b", "Palworld Tool Release v1", "https://github.com/example/palworld/releases/tag/v1")
        left.event_type = right.event_type = "release_published"
        same, confidence, reasons = compare_event_signatures(extract_event_signature(left), extract_event_signature(right))
        self.assertFalse(same)
        self.assertEqual(confidence, 0)
        self.assertIn("同类确定性标识符不同", reasons)

    def test_prepare_items_assigns_evidence_role_and_publisher_chain(self):
        task = MonitoringTask(keywords=["OpenAI", "GPT-5"])
        source = item("google_news", "media", "OpenAI releases GPT-5", "https://news.google.com/article")
        source.author = "Reuters"
        cleaned, _ = prepare_items([source], task)
        self.assertEqual(cleaned[0].evidence_role, "independent_confirm")
        self.assertEqual(cleaned[0].publisher_id, "publisher:reuters")
        self.assertEqual(cleaned[0].original_publisher_id, "publisher:reuters")

    def test_near_identical_news_titles_share_one_original_publication_chain(self):
        task = MonitoringTask(keywords=["OpenAI", "GPT-5"])
        first = item("google_news", "reuters", "OpenAI releases GPT-5 model today", "https://news.google.com/reuters")
        first.author = "Reuters"
        second = item("google_news", "portal", "OpenAI releases GPT-5 model today", "https://news.google.com/portal")
        second.author = "Example Portal"
        cleaned, _ = prepare_items([first, second], task)
        self.assertEqual(sum(source.is_repost for source in cleaned), 1)
        self.assertEqual(len({source.original_publisher_id for source in cleaned}), 1)

    def test_generic_guide_and_agent_words_do_not_create_false_cross_platform_cluster(self):
        task = MonitoringTask(keywords=["AI", "AI agent", "AI model", "artificial intelligence"])
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidates = cluster_items([
                item("github", "guide-repo", "kunfupen/ai-model-guide 近期活跃", "https://github.com/kunfupen/ai-model-guide"),
                item("devto", "agent-guide", "How to build an AI agent: A simple guide for anyone", "https://dev.to/agent-guide"),
                item("google_news", "retail-ai", "How Malachyte solves retail cold-start with managed real-time AI", "https://news.example.com/malachyte"),
            ], task, db)
        self.assertEqual(len(candidates), 3)
        self.assertTrue(all(candidate.platform_count == 1 for candidate in candidates))

    def test_finance_github_rejects_single_description_keyword(self):
        task = MonitoringTask(
            id=3,
            topic="金融与金融科技",
            keywords=["fintech", "payment", "bank"],
        )
        candidate = item("github", "3", "generic-commerce-demo", "https://example.com/c")
        candidate.content = "A tutorial project with a payment button"
        score = relevance_score(candidate, task)
        self.assertFalse(passes_source_gate(candidate, score, task))

    def test_finance_github_rejects_payment_demo_even_with_title_match(self):
        task = MonitoringTask(id=3, topic="金融", keywords=["payment", "fintech", "bank"])
        candidate = item("github", "5", "Fintech payment demo", "https://example.com/e")
        candidate.content = "A fintech payment template"
        score = relevance_score(candidate, task)
        self.assertFalse(passes_source_gate(candidate, score, task))

    def test_biology_github_accepts_strong_title_match(self):
        task = MonitoringTask(
            id=4,
            topic="生物科技与生命科学",
            keywords=["bioinformatics", "genomics", "protein design"],
        )
        candidate = item("github", "4", "Bioinformatics genomics toolkit", "https://example.com/d")
        score = relevance_score(candidate, task)
        self.assertTrue(passes_source_gate(candidate, score, task))

    def test_ordinary_repository_push_fails_event_gate_and_has_no_value(self):
        task = MonitoringTask()
        repository = item("github", "8:repository_updated", "AI coding agent 近期活跃", "https://github.com/acme/agent")
        repository.event_type = "repository_updated"
        repository.created_at = datetime(2022, 1, 1, tzinfo=timezone.utc)
        repository.pushed_at = datetime.now(timezone.utc)
        repository.metrics = SourceMetrics(stars=1, forks=0)
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidate = cluster_items([repository], task, db)[0]
        self.assertEqual(candidate.cluster_confidence, "不适用")
        self.assertEqual(candidate.value_level, "candidate")
        self.assertFalse(candidate.event_gate_passed)
        self.assertIn("普通仓库 push", candidate.event_gate_reason)
        self.assertEqual(candidate.value_score, 0)
        self.assertEqual(candidate.score_breakdown, {})
        self.assertEqual(candidate.decision_priority, "不进入决策")

    def test_cumulative_stars_are_not_current_adoption_growth(self):
        task = MonitoringTask()
        release = item("github", "release-1", "Acme AI coding agent releases version 2", "https://github.com/acme/agent/releases/tag/v2")
        release.event_type = "release_published"
        release.released_at = datetime.now(timezone.utc)
        release.metrics = SourceMetrics(stars=50000, forks=8000)
        prepared, _ = prepare_items([release], task)
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidate = cluster_items(prepared, task, db)[0]
        self.assertTrue(candidate.event_gate_passed)
        self.assertEqual(candidate.score_breakdown["adoption_growth"]["raw_value"], 0)
        self.assertGreater(candidate.score_breakdown["information_novelty"]["raw_value"], 0)

    def test_gibberish_bilibili_title_is_rejected(self):
        task = MonitoringTask(keywords=["AI", "AI agent"])
        video = item("bilibili", "noise", "AI AI AI agent model GPT Claude 大模型 教程 合集 2026", "https://www.bilibili.com/video/noise")
        score = relevance_score(video, task)
        self.assertFalse(passes_source_gate(video, score, task))

    def test_single_body_keyword_cannot_override_unrelated_news_title(self):
        task = MonitoringTask(id=5, keywords=["人工智能", "AI model", "AI agent"])
        news = item("chinanews", "off-topic", "市场监管总局公布公平竞争典型案例", "https://example.com/regulation")
        news.content = "某监测系统使用人工智能技术。"
        news.is_primary_source = True
        score = relevance_score(news, task)
        self.assertFalse(passes_source_gate(news, score, task))

    def test_attention_only_event_cannot_enter_business_decision(self):
        task = MonitoringTask()
        discussion = item("hacker_news", "launch-only", "Launch HN: Acme AI coding agent", "https://news.ycombinator.com/item?id=1")
        discussion.event_type = "discussion_created"
        discussion.evidence_role = "attention_signal"
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidate = cluster_items([discussion], task, db)[0]
        self.assertTrue(candidate.event_gate_passed)
        self.assertEqual(candidate.evidence_grade, "D")
        self.assertEqual(candidate.value_score, 0)
        self.assertEqual(candidate.decision_priority, "未评估")

    def test_paper_without_product_impact_stays_unassessed(self):
        task = MonitoringTask()
        paper = item("arxiv", "paper-1", "AI coding agent evaluation paper", "https://arxiv.org/abs/2608.1")
        paper.event_type = "paper_published"
        paper.is_primary_source = True
        prepared, _ = prepare_items([paper], task)
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            candidate = cluster_items(prepared, task, db)[0]
        candidate = finalize_business_decision(candidate, rule_analysis(candidate, task))
        self.assertEqual(candidate.decision_priority, "未评估")
        self.assertEqual(candidate.current_action, "技术初筛")

    def test_github_identity_is_stable_across_title_changes(self):
        task = MonitoringTask()
        first = item("github", "9:repository_updated", "AI coding agent 近期活跃", "https://github.com/acme/stable-agent")
        second = item("github", "9:repository_updated", "Stable Agent AI coding 工具更新", "https://github.com/acme/stable-agent")
        first.event_type = second.event_type = "repository_updated"
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            first_key = cluster_items([first], task, db)[0].candidate_id
            second_key = cluster_items([second], task, db)[0].candidate_id
        self.assertEqual(first_key, second_key)
