from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from datetime import datetime, timezone

from trendscope.database import Database, SCORING_MODEL_VERSION
from trendscope.models import MonitoringTask, SourceItem
from trendscope.processing import cluster_items, prepare_items, rule_analysis


class DatabaseTests(TestCase):
    def test_default_task_is_created(self):
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            task = db.get_task(1)
            finance = db.get_task(3)
            biology = db.get_task(4)
        self.assertEqual(task.topic, "AI 编程工具")
        self.assertTrue(task.enabled)
        self.assertTrue(any("federalreserve.gov" in url for url in finance.rss_feeds))
        self.assertTrue(any("biorxiv.org" in url for url in biology.rss_feeds))

    def test_initialize_adds_truth_and_value_columns(self):
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            with db.connect() as conn:
                source_columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_items)")}
                event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
                run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(agent_runs)")}
        self.assertTrue({"created_at", "updated_at", "pushed_at", "event_type"} <= source_columns)
        self.assertTrue({"value_score", "value_level", "score_breakdown_json"} <= event_columns)
        self.assertTrue({"evidence_role", "publisher_id", "original_publisher_id", "is_repost"} <= source_columns)
        self.assertTrue({"event_signature_json", "evidence_tier", "event_state", "growth_label"} <= event_columns)
        self.assertTrue({"evidence_grade", "event_gate_passed", "decision_priority", "current_action", "analysis_mode", "decision_tasks_json"} <= event_columns)
        self.assertTrue({"ai_success_count", "ai_fallback_count", "ai_duration_ms"} <= run_columns)

    def test_new_runs_record_current_model_versions(self):
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            db.create_run("versioned-run", 1, "rules")
            run = db.get_run("versioned-run")
        self.assertEqual(run["scoring_model_version"], SCORING_MODEL_VERSION)
        self.assertEqual(run["schema_version"], 6)
        self.assertEqual(run["analysis_prompt_version"], "business-impact-gated-v5")

    def test_evidence_fields_survive_event_round_trip(self):
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.db")
            db.initialize()
            db.create_run("evidence-run", 1, "rules")
            task = MonitoringTask(keywords=["Cursor", "AI coding"])
            source = SourceItem(
                source="rss", external_id="cursor-release", title="Cursor AI coding release",
                url="https://cursor.example/releases/1", published_at=datetime.now(timezone.utc),
                is_primary_source=True,
            )
            cleaned, _ = prepare_items([source], task)
            source_id = db.save_source_item("evidence-run", cleaned[0])
            candidate = cluster_items(cleaned, task, db)[0]
            event_id = db.save_event("evidence-run", candidate, rule_analysis(candidate, task), [source_id])
            saved = db.get_event_with_sources(event_id)
            media = SourceItem(
                source="google_news", external_id="cursor-media", title="Cursor releases AI coding update",
                url="https://news.google.com/cursor-media", author="Reuters",
                published_at=datetime.now(timezone.utc),
            )
            media_cleaned, _ = prepare_items([media], task)
            reassessed = db.attach_evidence_and_reassess(event_id, media_cleaned)
        self.assertEqual(saved["evidence_tier"], "primary_only")
        self.assertEqual(saved["event_state"], "单一来源线索")
        self.assertEqual(saved["sources"][0]["evidence_role"], "primary_fact")
        self.assertTrue(saved["event_signature"]["entities"])
        self.assertEqual(reassessed["evidence_tier"], "verified")
        self.assertEqual(reassessed["event_state"], "已证实事件")
