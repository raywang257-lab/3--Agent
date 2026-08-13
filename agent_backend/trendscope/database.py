from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

from .models import MonitoringTask, SourceItem

SCHEMA_VERSION = 6
SCORING_MODEL_VERSION = "four-gate-decision-v8"
ANALYSIS_PROMPT_VERSION = "business-impact-gated-v5"

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS monitoring_tasks (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  topic TEXT NOT NULL,
  keywords_json TEXT NOT NULL,
  excluded_keywords_json TEXT NOT NULL,
  rss_feeds_json TEXT NOT NULL DEFAULT '[]',
  target_role TEXT NOT NULL,
  time_window_hours INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY,
  task_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  items_collected INTEGER NOT NULL DEFAULT 0,
  items_filtered INTEGER NOT NULL DEFAULT 0,
  candidates_created INTEGER NOT NULL DEFAULT 0,
  ai_rejected INTEGER NOT NULL DEFAULT 0,
  ai_irrelevant_count INTEGER NOT NULL DEFAULT 0,
  ai_parse_failure_count INTEGER NOT NULL DEFAULT 0,
  ai_success_count INTEGER NOT NULL DEFAULT 0,
  ai_fallback_count INTEGER NOT NULL DEFAULT 0,
  ai_duration_ms INTEGER NOT NULL DEFAULT 0,
  quality_gate_fallback_count INTEGER NOT NULL DEFAULT 0,
  schema_version INTEGER NOT NULL DEFAULT 6,
  scoring_model_version TEXT NOT NULL DEFAULT 'evidence-gated-value-v3',
  analysis_prompt_version TEXT NOT NULL DEFAULT 'claims-evidence-matrix-v3',
  invalid_items INTEGER NOT NULL DEFAULT 0,
  excluded_items INTEGER NOT NULL DEFAULT 0,
  duplicate_items INTEGER NOT NULL DEFAULT 0,
  relevance_filtered INTEGER NOT NULL DEFAULT 0,
  cluster_merged INTEGER NOT NULL DEFAULT 0,
  events_created INTEGER NOT NULL DEFAULT 0,
  ai_mode TEXT NOT NULL,
  error_message TEXT,
  FOREIGN KEY(task_id) REFERENCES monitoring_tasks(id)
);

CREATE TABLE IF NOT EXISTS run_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  stage TEXT NOT NULL,
  message TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT 'info',
  FOREIGN KEY(run_id) REFERENCES agent_runs(id)
);

CREATE TABLE IF NOT EXISTS source_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  discussion_url TEXT,
  author TEXT,
  content TEXT,
  published_at TEXT NOT NULL,
  created_at TEXT,
  updated_at TEXT,
  pushed_at TEXT,
  released_at TEXT,
  event_type TEXT,
  collected_at TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  is_primary_source INTEGER NOT NULL,
  evidence_role TEXT NOT NULL DEFAULT 'opinion',
  publisher_id TEXT NOT NULL DEFAULT '',
  publisher_type TEXT NOT NULL DEFAULT 'unknown',
  original_publisher_id TEXT,
  original_url TEXT,
  is_independent INTEGER NOT NULL DEFAULT 1,
  is_repost INTEGER NOT NULL DEFAULT 0,
  supports_claims_json TEXT NOT NULL DEFAULT '[]',
  contradicts_claims_json TEXT NOT NULL DEFAULT '[]',
  content_hash TEXT NOT NULL,
  UNIQUE(run_id, source, external_id),
  FOREIGN KEY(run_id) REFERENCES agent_runs(id)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  canonical_title TEXT NOT NULL,
  category TEXT NOT NULL,
  summary TEXT NOT NULL,
  why_now TEXT NOT NULL,
  debate TEXT NOT NULL,
  impact TEXT NOT NULL,
  recommended_action TEXT NOT NULL,
  risk TEXT NOT NULL,
  truth_status TEXT NOT NULL,
  cluster_confidence TEXT NOT NULL,
  action_level TEXT NOT NULL,
  analysis_mode TEXT NOT NULL DEFAULT 'rules',
  value_score REAL NOT NULL DEFAULT 0,
  value_level TEXT NOT NULL DEFAULT 'candidate',
  hotspot_confidence TEXT NOT NULL DEFAULT '证据不足',
  content_type TEXT NOT NULL DEFAULT '低置信度线索',
  score_breakdown_json TEXT NOT NULL DEFAULT '{}',
  claims_json TEXT NOT NULL DEFAULT '[]',
  business_impact_json TEXT NOT NULL DEFAULT '{}',
  relevance_score REAL NOT NULL,
  attention_signal REAL NOT NULL,
  growth_percent REAL,
  platform_count INTEGER NOT NULL,
  source_count INTEGER NOT NULL,
  metric_deltas_json TEXT NOT NULL DEFAULT '{}',
  event_signature_json TEXT NOT NULL DEFAULT '{}',
  evidence_tier TEXT NOT NULL DEFAULT 'unverified',
  event_state TEXT NOT NULL DEFAULT '未核验线索',
  evidence_confidence REAL NOT NULL DEFAULT 0,
  evidence_grade TEXT NOT NULL DEFAULT 'U',
  event_gate_passed INTEGER NOT NULL DEFAULT 0,
  event_gate_reason TEXT NOT NULL DEFAULT '尚未识别明确事件动作',
  decision_priority TEXT NOT NULL DEFAULT '不进入决策',
  current_action TEXT NOT NULL DEFAULT '补证',
  decision_owner TEXT NOT NULL DEFAULT '竞争情报分析师',
  decision_deadline TEXT NOT NULL DEFAULT '下一工作日',
  decision_tasks_json TEXT NOT NULL DEFAULT '[]',
  upgrade_conditions_json TEXT NOT NULL DEFAULT '[]',
  growth_label TEXT NOT NULL DEFAULT '无增长基线',
  lifecycle TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES agent_runs(id)
);

CREATE TABLE IF NOT EXISTS event_sources (
  event_id INTEGER NOT NULL,
  source_item_id INTEGER NOT NULL,
  PRIMARY KEY(event_id, source_item_id),
  FOREIGN KEY(event_id) REFERENCES events(id),
  FOREIGN KEY(source_item_id) REFERENCES source_items(id)
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_key TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  captured_at TEXT NOT NULL,
  attention_signal REAL NOT NULL,
  platform_count INTEGER NOT NULL,
  source_count INTEGER NOT NULL,
  stars INTEGER NOT NULL DEFAULT 0,
  forks INTEGER NOT NULL DEFAULT 0,
  comments INTEGER NOT NULL DEFAULT 0,
  source_score INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS event_reviews (
  event_id INTEGER PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
  note TEXT NOT NULL DEFAULT '',
  reviewed_at TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS email_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  sent_at TEXT NOT NULL,
  recipient_count INTEGER NOT NULL,
  hotspot_count INTEGER NOT NULL,
  subject TEXT NOT NULL,
  status TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES monitoring_tasks(id)
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            task_columns = {row["name"] for row in conn.execute("PRAGMA table_info(monitoring_tasks)").fetchall()}
            if "rss_feeds_json" not in task_columns:
                conn.execute("ALTER TABLE monitoring_tasks ADD COLUMN rss_feeds_json TEXT NOT NULL DEFAULT '[]'")
            run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(agent_runs)").fetchall()}
            if "candidates_created" not in run_columns:
                conn.execute("ALTER TABLE agent_runs ADD COLUMN candidates_created INTEGER NOT NULL DEFAULT 0")
            if "ai_rejected" not in run_columns:
                conn.execute("ALTER TABLE agent_runs ADD COLUMN ai_rejected INTEGER NOT NULL DEFAULT 0")
            run_migrations = {
                "ai_irrelevant_count": "INTEGER NOT NULL DEFAULT 0",
                "ai_parse_failure_count": "INTEGER NOT NULL DEFAULT 0",
                "ai_success_count": "INTEGER NOT NULL DEFAULT 0",
                "ai_fallback_count": "INTEGER NOT NULL DEFAULT 0",
                "ai_duration_ms": "INTEGER NOT NULL DEFAULT 0",
                "quality_gate_fallback_count": "INTEGER NOT NULL DEFAULT 0",
                "schema_version": f"INTEGER NOT NULL DEFAULT {SCHEMA_VERSION}",
                "scoring_model_version": f"TEXT NOT NULL DEFAULT '{SCORING_MODEL_VERSION}'",
                "analysis_prompt_version": f"TEXT NOT NULL DEFAULT '{ANALYSIS_PROMPT_VERSION}'",
            }
            for name, ddl in run_migrations.items():
                if name not in run_columns:
                    conn.execute(f"ALTER TABLE agent_runs ADD COLUMN {name} {ddl}")
            version_marker = conn.execute(
                "SELECT value FROM system_metadata WHERE key='run_version_migration_v3'"
            ).fetchone()
            if not version_marker:
                conn.execute(
                    """UPDATE agent_runs SET schema_version=2,scoring_model_version='legacy-v1',
                       analysis_prompt_version='legacy-v1'"""
                )
                conn.execute(
                    "INSERT INTO system_metadata(key,value) VALUES('run_version_migration_v3',?)",
                    (datetime.now(timezone.utc).isoformat(),),
                )
            for name in ("invalid_items", "excluded_items", "duplicate_items", "relevance_filtered", "cluster_merged"):
                if name not in run_columns:
                    conn.execute(f"ALTER TABLE agent_runs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            source_columns = {row["name"] for row in conn.execute("PRAGMA table_info(source_items)").fetchall()}
            source_migrations = {
                "created_at": "TEXT", "updated_at": "TEXT", "pushed_at": "TEXT", "released_at": "TEXT", "event_type": "TEXT",
                "evidence_role": "TEXT NOT NULL DEFAULT 'opinion'", "publisher_id": "TEXT NOT NULL DEFAULT ''",
                "publisher_type": "TEXT NOT NULL DEFAULT 'unknown'", "original_publisher_id": "TEXT", "original_url": "TEXT",
                "is_independent": "INTEGER NOT NULL DEFAULT 1", "is_repost": "INTEGER NOT NULL DEFAULT 0",
                "supports_claims_json": "TEXT NOT NULL DEFAULT '[]'", "contradicts_claims_json": "TEXT NOT NULL DEFAULT '[]'",
            }
            for name, ddl in source_migrations.items():
                if name not in source_columns:
                    conn.execute(f"ALTER TABLE source_items ADD COLUMN {name} {ddl}")
            event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
            event_migrations = {
                "value_score": "REAL NOT NULL DEFAULT 0",
                "value_level": "TEXT NOT NULL DEFAULT 'candidate'",
                "hotspot_confidence": "TEXT NOT NULL DEFAULT '证据不足'",
                "content_type": "TEXT NOT NULL DEFAULT '低置信度线索'",
                "score_breakdown_json": "TEXT NOT NULL DEFAULT '{}'",
                "claims_json": "TEXT NOT NULL DEFAULT '[]'",
                "business_impact_json": "TEXT NOT NULL DEFAULT '{}'",
                "metric_deltas_json": "TEXT NOT NULL DEFAULT '{}'",
                "event_signature_json": "TEXT NOT NULL DEFAULT '{}'",
                "evidence_tier": "TEXT NOT NULL DEFAULT 'unverified'",
                "event_state": "TEXT NOT NULL DEFAULT '未核验线索'",
                "evidence_confidence": "REAL NOT NULL DEFAULT 0",
                "evidence_grade": "TEXT NOT NULL DEFAULT 'U'",
                "event_gate_passed": "INTEGER NOT NULL DEFAULT 0",
                "event_gate_reason": "TEXT NOT NULL DEFAULT '尚未识别明确事件动作'",
                "decision_priority": "TEXT NOT NULL DEFAULT '不进入决策'",
                "current_action": "TEXT NOT NULL DEFAULT '补证'",
                "analysis_mode": "TEXT NOT NULL DEFAULT 'rules'",
                "decision_owner": "TEXT NOT NULL DEFAULT '竞争情报分析师'",
                "decision_deadline": "TEXT NOT NULL DEFAULT '下一工作日'",
                "decision_tasks_json": "TEXT NOT NULL DEFAULT '[]'",
                "upgrade_conditions_json": "TEXT NOT NULL DEFAULT '[]'",
                "growth_label": "TEXT NOT NULL DEFAULT '无增长基线'",
            }
            for name, ddl in event_migrations.items():
                if name not in event_columns:
                    conn.execute(f"ALTER TABLE events ADD COLUMN {name} {ddl}")
            snapshot_columns = {row["name"] for row in conn.execute("PRAGMA table_info(metric_snapshots)").fetchall()}
            for name in ("stars", "forks", "comments", "source_score"):
                if name not in snapshot_columns:
                    conn.execute(f"ALTER TABLE metric_snapshots ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
        self.ensure_default_task()
        self.backfill_legacy_value_scores()

    def backfill_legacy_value_scores(self) -> int:
        """修复评分功能上线前写入、迁移后被默认成 0 分的历史事件。"""
        updated = 0
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id,relevance_score,attention_signal,growth_percent,platform_count,source_count
                   FROM events WHERE value_score=0 AND COALESCE(score_breakdown_json,'{}')='{}'"""
            ).fetchall()
            for row in rows:
                relevance_raw = max(0.0, min(100.0, float(row["relevance_score"] or 0)))
                growth_raw = 0.0 if row["growth_percent"] is None else max(0.0, min(100.0, float(row["growth_percent"])))
                cross_raw = min(100.0, max(0.0, float(row["platform_count"] or 0) - 1) * 50.0)
                source_raw = min(100.0, max(0.0, float(row["source_count"] or 0) - 1) * 35.0)
                attention_raw = min(100.0, float(row["attention_signal"] or 0))
                specs = {
                    "relevance": (25, relevance_raw, "历史事件：与监控主题的程序化匹配度"),
                    "growth": (25, growth_raw, "历史事件缺少快照" if row["growth_percent"] is None else f"历史记录增速 {row['growth_percent']:+.1f}%"),
                    "cross_platform": (20, cross_raw, f"覆盖 {row['platform_count']} 个平台"),
                    "source_strength": (15, source_raw, f"{row['source_count']} 个独立发布方"),
                    "attention": (15, attention_raw, f"关注信号 {float(row['attention_signal'] or 0):.1f}"),
                }
                breakdown = {
                    name: {
                        "weight": weight,
                        "raw_value": None if name == "growth" and row["growth_percent"] is None else round(raw, 1),
                        "contribution": round(raw * weight / 100.0, 1),
                        "reason": reason,
                    }
                    for name, (weight, raw, reason) in specs.items()
                }
                score = round(sum(item["contribution"] for item in breakdown.values()), 1)
                level = "high_value" if score >= 70 else "watchlist" if score >= 45 else "candidate"
                confidence = "较高" if level == "high_value" and row["platform_count"] >= 2 else "待观察" if level == "watchlist" else "证据不足"
                conn.execute(
                    """UPDATE events SET value_score=?,value_level=?,hotspot_confidence=?,score_breakdown_json=?
                       WHERE id=?""",
                    (score, level, confidence, json.dumps(breakdown, ensure_ascii=False), row["id"]),
                )
                updated += 1
        return updated

    def ensure_default_task(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        tasks = [
            MonitoringTask(),
            MonitoringTask(
                id=2,
                name="科技热点监控",
                topic="前沿科技",
                keywords=[
                    "technology", "semiconductor", "robotics", "quantum computing",
                    "cybersecurity", "cloud computing", "developer tools", "open source",
                    "芯片", "半导体", "机器人", "量子计算", "网络安全", "云计算", "开发者工具", "开源",
                ],
                excluded_keywords=["travel technology", "fashion technology"],
                rss_feeds=[
                    "https://github.blog/feed/",
                    "https://news.mit.edu/rss/feed",
                    "https://research.google/blog/rss/",
                    "https://developers.googleblog.com/feeds/posts/default",
                    "https://cloudblog.withgoogle.com/rss/",
                    "https://blog.cloudflare.com/rss/",
                    "https://blogs.nvidia.com/feed/",
                    "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
                    "https://www.microsoft.com/en-us/research/feed/",
                ],
                target_role="科技行业研究与产品负责人",
            ),
            MonitoringTask(
                id=3,
                name="金融热点监控",
                topic="金融与金融科技",
                keywords=[
                    "fintech", "digital banking", "payment", "financial markets",
                    "blockchain", "stablecoin", "banking AI", "investment technology",
                    "Federal Reserve", "interest rate", "monetary policy", "inflation",
                    "bank", "financial regulation", "securities", "fraud",
                    "金融科技", "支付", "数字银行", "金融市场", "区块链", "稳定币", "利率", "通胀", "证券监管",
                ],
                excluded_keywords=["game currency", "sports betting"],
                rss_feeds=[
                    "https://www.federalreserve.gov/feeds/press_all.xml",
                    "https://www.ecb.europa.eu/rss/press.html",
                    "https://www.bankofengland.co.uk/rss/news",
                    "https://www.sec.gov/news/pressreleases.rss",
                ],
                target_role="金融产品、投资研究与风险负责人",
            ),
            MonitoringTask(
                id=4,
                name="生物热点监控",
                topic="生物科技与生命科学",
                keywords=[
                    "biotechnology", "bioinformatics", "genomics", "drug discovery",
                    "CRISPR", "synthetic biology", "medical AI", "protein design",
                    "biotech", "clinical trial", "gene", "protein", "drug", "FDA",
                    "spatial proteomics", "cell therapy", "immunology",
                    "生物科技", "基因组", "药物发现", "临床试验", "蛋白质", "细胞治疗", "免疫",
                ],
                excluded_keywords=["beauty supplement", "fitness influencer"],
                rss_feeds=[
                    "https://www.nature.com/nbt.rss",
                    "https://connect.biorxiv.org/biorxiv_xml.php?subject=genomics+bioinformatics",
                    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
                    "https://www.who.int/rss-feeds/news-english.xml",
                ],
                target_role="生物科技研究、产品与战略负责人",
            ),
            MonitoringTask(
                id=5,
                name="AI 热点监控",
                topic="人工智能",
                keywords=[
                    "artificial intelligence", "AI model", "AI agent", "generative AI",
                    "large language model", "multimodal AI", "machine learning", "AI research",
                    "人工智能", "大模型", "智能体", "生成式AI", "多模态", "机器学习", "AI研究",
                ],
                excluded_keywords=["travel agent", "real estate agent"],
                rss_feeds=[
                    "https://openai.com/news/rss.xml",
                    "https://blog.google/innovation-and-ai/technology/ai/rss/",
                    "https://deepmind.google/blog/rss.xml",
                    "https://research.google/blog/rss/",
                    "https://developers.googleblog.com/feeds/posts/default",
                    "https://cloudblog.withgoogle.com/rss/",
                    "https://github.blog/feed/",
                    "https://huggingface.co/blog/feed.xml",
                    "https://techcrunch.com/feed/",
                    "https://venturebeat.com/category/ai/feed",
                    "https://feeds.arstechnica.com/arstechnica/index",
                    "https://feed.infoq.com/ai-ml-data-eng/",
                    "https://www.producthunt.com/feed",
                    "https://lobste.rs/rss",
                    "https://blog.cloudflare.com/rss/",
                    "https://blogs.nvidia.com/feed/",
                    "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
                    "https://www.microsoft.com/en-us/research/feed/",
                ],
                target_role="AI 产品、研究与竞争情报负责人",
            ),
        ]
        with self.connect() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO monitoring_tasks
                (id,name,topic,keywords_json,excluded_keywords_json,rss_feeds_json,target_role,time_window_hours,enabled,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name,topic=excluded.topic,keywords_json=excluded.keywords_json,
                  excluded_keywords_json=excluded.excluded_keywords_json,rss_feeds_json=excluded.rss_feeds_json,
                  target_role=excluded.target_role,time_window_hours=excluded.time_window_hours,
                  enabled=excluded.enabled,updated_at=excluded.updated_at""",
                [
                    (task.id, task.name, task.topic, json.dumps(task.keywords, ensure_ascii=False),
                     json.dumps(task.excluded_keywords, ensure_ascii=False),
                     json.dumps(task.rss_feeds, ensure_ascii=False), task.target_role,
                     task.time_window_hours, int(task.enabled), now, now)
                    for task in tasks
                ],
            )

    def get_task(self, task_id: int) -> MonitoringTask:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM monitoring_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(f"监控任务 {task_id} 不存在")
        return MonitoringTask(
            id=row["id"], name=row["name"], topic=row["topic"],
            keywords=json.loads(row["keywords_json"]),
            excluded_keywords=json.loads(row["excluded_keywords_json"]),
            rss_feeds=json.loads(row["rss_feeds_json"] or "[]"),
            target_role=row["target_role"], time_window_hours=row["time_window_hours"],
            enabled=bool(row["enabled"]),
        )

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM monitoring_tasks ORDER BY id").fetchall()
        return [dict(row) | {
            "keywords": json.loads(row["keywords_json"]),
            "excluded_keywords": json.loads(row["excluded_keywords_json"]),
            "rss_feeds": json.loads(row["rss_feeds_json"] or "[]"),
        } for row in rows]

    def create_run(self, run_id: str, task_id: int, ai_mode: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO agent_runs
                   (id,task_id,status,started_at,ai_mode,schema_version,scoring_model_version,analysis_prompt_version)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (run_id, task_id, "collecting", datetime.now(timezone.utc).isoformat(), ai_mode,
                 SCHEMA_VERSION, SCORING_MODEL_VERSION, ANALYSIS_PROMPT_VERSION),
            )

    def active_run_for_task(self, task_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM agent_runs WHERE task_id=? AND status IN
                   ('queued','collecting','filtering','clustering','analyzing')
                   ORDER BY started_at DESC LIMIT 1""",
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def recover_interrupted_runs(self) -> int:
        """服务重启后终止已失去执行进程的运行，避免页面永久显示 analyzing。"""
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """UPDATE agent_runs SET status='failed',completed_at=?,
                   error_message='服务重启导致任务中断，请重新运行'
                   WHERE status IN ('queued','collecting','filtering','clustering','analyzing')""",
                (now,),
            )
        return int(cursor.rowcount)

    def update_run(self, run_id: str, **fields: Any) -> None:
        allowed = {
            "status", "completed_at", "items_collected", "items_filtered", "candidates_created",
            "ai_rejected", "invalid_items", "excluded_items", "duplicate_items", "relevance_filtered",
            "cluster_merged", "events_created", "error_message", "ai_irrelevant_count",
            "ai_parse_failure_count", "quality_gate_fallback_count",
            "ai_success_count", "ai_fallback_count", "ai_duration_ms",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        sql = ", ".join(f"{key}=?" for key in values)
        with self.connect() as conn:
            conn.execute(f"UPDATE agent_runs SET {sql} WHERE id=?", (*values.values(), run_id))

    def log(self, run_id: str, stage: str, message: str, level: str = "info") -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO run_logs(run_id,created_at,stage,message,level) VALUES(?,?,?,?,?)",
                (run_id, datetime.now(timezone.utc).isoformat(), stage, message, level),
            )

    def save_source_item(self, run_id: str, item: SourceItem) -> int:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO source_items
                (run_id,source,external_id,title,url,discussion_url,author,content,published_at,created_at,updated_at,pushed_at,released_at,event_type,collected_at,metrics_json,is_primary_source,
                 evidence_role,publisher_id,publisher_type,original_publisher_id,original_url,is_independent,is_repost,supports_claims_json,contradicts_claims_json,content_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id,source,external_id) DO UPDATE SET
                  title=excluded.title,url=excluded.url,discussion_url=excluded.discussion_url,
                  author=excluded.author,content=excluded.content,published_at=excluded.published_at,
                  created_at=excluded.created_at,updated_at=excluded.updated_at,pushed_at=excluded.pushed_at,
                  released_at=excluded.released_at,event_type=excluded.event_type,
                  collected_at=excluded.collected_at,metrics_json=excluded.metrics_json,
                  is_primary_source=excluded.is_primary_source,evidence_role=excluded.evidence_role,
                  publisher_id=excluded.publisher_id,publisher_type=excluded.publisher_type,
                  original_publisher_id=excluded.original_publisher_id,original_url=excluded.original_url,
                  is_independent=excluded.is_independent,is_repost=excluded.is_repost,
                  supports_claims_json=excluded.supports_claims_json,contradicts_claims_json=excluded.contradicts_claims_json,
                  content_hash=excluded.content_hash""",
                (run_id, item.source, item.external_id, item.title, item.url, item.discussion_url,
                 item.author, item.content, item.published_at.isoformat(),
                 item.created_at.isoformat() if item.created_at else None,
                 item.updated_at.isoformat() if item.updated_at else None,
                 item.pushed_at.isoformat() if item.pushed_at else None,
                 item.released_at.isoformat() if item.released_at else None, item.event_type,
                 item.collected_at.isoformat(),
                 item.metrics.model_dump_json(), int(item.is_primary_source), item.evidence_role,
                 item.publisher_id, item.publisher_type, item.original_publisher_id, item.original_url,
                 int(item.is_independent), int(item.is_repost),
                 json.dumps(item.supports_claims, ensure_ascii=False),
                 json.dumps(item.contradicts_claims, ensure_ascii=False), item.content_hash),
            )
            row = conn.execute(
                "SELECT id FROM source_items WHERE run_id=? AND source=? AND external_id=?",
                (run_id, item.source, item.external_id),
            ).fetchone()
        return int(row["id"])

    def previous_attention(self, event_key: str) -> float | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT attention_signal FROM metric_snapshots WHERE event_key=? ORDER BY captured_at DESC LIMIT 1",
                (event_key,),
            ).fetchone()
        return float(row["attention_signal"]) if row else None

    def previous_metrics(self, event_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM metric_snapshots WHERE event_key=? ORDER BY captured_at DESC LIMIT 1", (event_key,),
            ).fetchone()
        return dict(row) if row else None

    def metric_history(self, event_key: str, limit: int = 3) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM metric_snapshots WHERE event_key=? ORDER BY captured_at DESC LIMIT ?",
                (event_key, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_event(self, run_id: str, candidate: Any, analysis: Any, source_ids: list[int], analysis_mode: str = "rules") -> int:
        first_seen = min(item.published_at for item in candidate.items).isoformat()
        last_seen = max(item.published_at for item in candidate.items).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO events
                (run_id,candidate_id,canonical_title,category,summary,why_now,debate,impact,recommended_action,risk,
                 truth_status,cluster_confidence,action_level,analysis_mode,value_score,value_level,hotspot_confidence,content_type,
                 score_breakdown_json,claims_json,business_impact_json,relevance_score,attention_signal,growth_percent,platform_count,source_count,
                 metric_deltas_json,event_signature_json,evidence_tier,event_state,evidence_confidence,evidence_grade,
                 event_gate_passed,event_gate_reason,decision_priority,current_action,decision_owner,decision_deadline,
                 decision_tasks_json,upgrade_conditions_json,growth_label,
                 lifecycle,first_seen_at,last_seen_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, candidate.candidate_id, analysis.canonical_title, analysis.category, analysis.summary,
                 analysis.why_now, analysis.debate, analysis.impact, analysis.recommended_action, analysis.risk,
                 candidate.truth_status, candidate.cluster_confidence, analysis.action_level, analysis_mode,
                 candidate.value_score, candidate.value_level, candidate.hotspot_confidence, candidate.content_type,
                 json.dumps(candidate.score_breakdown, ensure_ascii=False),
                 json.dumps([claim.model_dump() for claim in analysis.claims], ensure_ascii=False),
                 json.dumps({field: getattr(analysis, field) for field in (
                     "affected_product", "affected_user", "impact_mechanism", "urgency_reason",
                     "cost_of_inaction", "recommended_owner", "minimum_action", "deadline_reason",
                 )}, ensure_ascii=False),
                 candidate.relevance_score, candidate.attention_signal, candidate.growth_percent,
                 candidate.platform_count, candidate.source_count,
                 json.dumps(candidate.metric_deltas, ensure_ascii=False),
                 candidate.event_signature.model_dump_json(), candidate.evidence_tier, candidate.event_state,
                 candidate.evidence_confidence, candidate.evidence_grade, int(candidate.event_gate_passed),
                 candidate.event_gate_reason, candidate.decision_priority, candidate.current_action, candidate.decision_owner,
                 candidate.decision_deadline, json.dumps(candidate.decision_tasks, ensure_ascii=False),
                 json.dumps(candidate.upgrade_conditions, ensure_ascii=False), candidate.growth_label,
                 candidate.lifecycle, first_seen, last_seen, now),
            )
            event_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT INTO event_sources(event_id,source_item_id) VALUES(?,?)",
                [(event_id, source_id) for source_id in source_ids],
            )
            conn.execute(
                """INSERT INTO metric_snapshots
                   (event_key,event_id,captured_at,attention_signal,platform_count,source_count,stars,forks,comments,source_score)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (candidate.candidate_id, event_id, now, candidate.attention_signal,
                 candidate.platform_count, candidate.source_count,
                 sum(item.metrics.stars or 0 for item in candidate.items),
                 sum(item.metrics.forks or 0 for item in candidate.items),
                 sum(item.metrics.comments or 0 for item in candidate.items),
                 sum(item.metrics.score or 0 for item in candidate.items)),
            )
        return event_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            logs = conn.execute("SELECT * FROM run_logs WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        if not row:
            return None
        return dict(row) | {"logs": [dict(log) for log in logs]}

    def list_run_logs(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM run_logs WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def latest_run_summary(self, task_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            run = conn.execute(
                """SELECT * FROM agent_runs WHERE status='completed' AND task_id=?
                   AND scoring_model_version=? ORDER BY completed_at DESC LIMIT 1""",
                (task_id, SCORING_MODEL_VERSION),
            ).fetchone()
            if not run:
                return None
            run_id = run["id"]
            related_count = int(conn.execute(
                "SELECT COUNT(*) FROM source_items WHERE run_id=?", (run_id,)
            ).fetchone()[0])
            event_count = int(conn.execute(
                "SELECT COUNT(*) FROM events WHERE run_id=?", (run_id,)
            ).fetchone()[0])
            level_rows = conn.execute(
                "SELECT value_level,COUNT(*) AS count FROM events WHERE run_id=? GROUP BY value_level", (run_id,)
            ).fetchall()
            levels = {row["value_level"]: int(row["count"]) for row in level_rows}
            source_rows = conn.execute(
                "SELECT source, COUNT(*) AS count FROM source_items WHERE run_id=? GROUP BY source ORDER BY source",
                (run_id,),
            ).fetchall()
            warnings = conn.execute(
                "SELECT message FROM run_logs WHERE run_id=? AND level='warning' ORDER BY id",
                (run_id,),
            ).fetchall()
            coverage_rows = conn.execute(
                """SELECT evidence_tier,event_state,growth_label,platform_count FROM events WHERE run_id=?""",
                (run_id,),
            ).fetchall()
        coverage = [dict(row) for row in coverage_rows]
        return dict(run) | {
            "related_items": related_count,
            "independent_events": int(run["candidates_created"] or event_count),
            "candidate_events": event_count,
            "high_value_hotspots": levels.get("high_value", 0),
            "watchlist_events": levels.get("watchlist", 0),
            "low_confidence_candidates": levels.get("candidate", 0),
            "sources": [dict(row) for row in source_rows],
            "warnings": [row["message"] for row in warnings],
            "is_current_scoring_model": run["scoring_model_version"] == SCORING_MODEL_VERSION,
            "evidence_coverage": {
                "primary_or_verified": sum(row["evidence_tier"] in {"verified", "primary_only"} for row in coverage),
                "independent_confirmed": sum(row["evidence_tier"] in {"verified", "corroborated", "single_source"} for row in coverage),
                "single_source": sum(row["evidence_tier"] in {"single_source", "primary_only", "unverified"} for row in coverage),
                "with_growth_snapshots": sum(row["growth_label"] != "无增长基线" for row in coverage),
                "sustained_growth": sum(row["growth_label"] == "持续增长" for row in coverage),
                "no_growth_baseline": sum(row["growth_label"] == "无增长基线" for row in coverage),
                "cross_platform": sum(int(row["platform_count"]) >= 2 for row in coverage),
                "single_platform": sum(int(row["platform_count"]) < 2 for row in coverage),
            },
        }

    def attach_evidence_and_reassess(self, event_id: int, items: list[SourceItem]) -> dict[str, Any]:
        event = self.get_event_with_sources(event_id)
        if not event:
            raise KeyError(f"事件 {event_id} 不存在")
        attached = 0
        for item in items:
            source_id = self.save_source_item(event["run_id"], item)
            with self.connect() as conn:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO event_sources(event_id,source_item_id) VALUES(?,?)",
                    (event_id, source_id),
                )
            attached += int(cursor.rowcount > 0)
        refreshed = self.get_event_with_sources(event_id)
        if not refreshed:
            raise KeyError(f"事件 {event_id} 不存在")
        from .models import EventCandidate, EventSignature
        from .processing import apply_program_judgement, finalize_business_decision, independent_source_count, rule_analysis

        source_items = [SourceItem.model_validate(source) for source in refreshed["sources"]]
        task_id = int(self.get_run(refreshed["run_id"])["task_id"])
        task = self.get_task(task_id)
        candidate = EventCandidate(
            candidate_id=refreshed["candidate_id"], canonical_title=refreshed["canonical_title"], items=source_items,
            relevance_score=float(refreshed["relevance_score"]), attention_signal=float(refreshed["attention_signal"]),
            platform_count=len({item.source for item in source_items}), source_count=independent_source_count(source_items),
            growth_percent=refreshed.get("growth_percent"), lifecycle=refreshed.get("lifecycle") or "未知",
            metric_deltas=refreshed.get("metric_deltas") or {},
            event_signature=EventSignature.model_validate(refreshed.get("event_signature") or {}),
            growth_label=refreshed.get("growth_label") or "无增长基线",
        )
        candidate = apply_program_judgement(candidate, task)
        analysis = rule_analysis(candidate, task)
        if refreshed.get("analysis_mode") == "ai":
            business = refreshed.get("business_impact") or {}
            analysis = analysis.model_copy(update={
                "category": refreshed["category"], "summary": refreshed["summary"],
                "why_now": refreshed["why_now"], "debate": refreshed["debate"],
                "impact": refreshed["impact"], "recommended_action": refreshed["recommended_action"],
                "risk": refreshed["risk"],
                **{field: business.get(field) for field in (
                    "affected_product", "affected_user", "impact_mechanism", "urgency_reason",
                    "cost_of_inaction", "recommended_owner", "minimum_action", "deadline_reason",
                )},
            })
        candidate = finalize_business_decision(candidate, analysis)
        with self.connect() as conn:
            conn.execute(
                """UPDATE events SET category=?,summary=?,why_now=?,impact=?,recommended_action=?,risk=?,
                   truth_status=?,cluster_confidence=?,action_level=?,value_score=?,value_level=?,hotspot_confidence=?,
                   content_type=?,score_breakdown_json=?,claims_json=?,business_impact_json=?,platform_count=?,source_count=?,evidence_tier=?,
                   event_state=?,evidence_confidence=?,evidence_grade=?,event_gate_passed=?,event_gate_reason=?,
                   decision_priority=?,current_action=?,decision_owner=?,decision_deadline=?,decision_tasks_json=?,upgrade_conditions_json=?
                   WHERE id=?""",
                (analysis.category, analysis.summary, analysis.why_now, analysis.impact, analysis.recommended_action,
                 analysis.risk, candidate.truth_status, candidate.cluster_confidence, analysis.action_level,
                 candidate.value_score, candidate.value_level, candidate.hotspot_confidence, candidate.content_type,
                 json.dumps(candidate.score_breakdown, ensure_ascii=False),
                 json.dumps([claim.model_dump() for claim in analysis.claims], ensure_ascii=False),
                 json.dumps({field: getattr(analysis, field) for field in (
                     "affected_product", "affected_user", "impact_mechanism", "urgency_reason",
                     "cost_of_inaction", "recommended_owner", "minimum_action", "deadline_reason",
                 )}, ensure_ascii=False),
                 candidate.platform_count, candidate.source_count, candidate.evidence_tier, candidate.event_state,
                 candidate.evidence_confidence, candidate.evidence_grade, int(candidate.event_gate_passed),
                 candidate.event_gate_reason, candidate.decision_priority, candidate.current_action, candidate.decision_owner,
                 candidate.decision_deadline, json.dumps(candidate.decision_tasks, ensure_ascii=False),
                 json.dumps(candidate.upgrade_conditions, ensure_ascii=False), event_id),
            )
        return {
            "attached_count": attached, "evidence_tier": candidate.evidence_tier,
            "evidence_grade": candidate.evidence_grade, "event_state": candidate.event_state,
            "value_level": candidate.value_level, "value_score": candidate.value_score,
            "decision_priority": candidate.decision_priority,
        }

    def review_event(self, event_id: int, status: str, note: str = "") -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            event = conn.execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone()
            if not event:
                raise KeyError(f"热点事件 {event_id} 不存在")
            conn.execute(
                """INSERT INTO event_reviews(event_id,status,note,reviewed_at) VALUES(?,?,?,?)
                   ON CONFLICT(event_id) DO UPDATE SET
                     status=excluded.status,note=excluded.note,reviewed_at=excluded.reviewed_at""",
                (event_id, status, note.strip(), now),
            )
            row = conn.execute("SELECT * FROM event_reviews WHERE event_id=?", (event_id,)).fetchone()
        return dict(row)

    def list_latest_events(self, limit: int = 20, task_id: int = 1) -> list[dict[str, Any]]:
        with self.connect() as conn:
            latest_run = conn.execute(
                """SELECT id FROM agent_runs WHERE status='completed' AND task_id=?
                   AND scoring_model_version=? ORDER BY completed_at DESC LIMIT 1""",
                (task_id, SCORING_MODEL_VERSION),
            ).fetchone()
            if not latest_run:
                return []
            rows = conn.execute(
                # runner 已按跨源价值排序保存；此处保留入库顺序，
                # 避免再按 GitHub 高互动分重排后挤掉 Google News/RSS。
                """SELECT e.* FROM events e LEFT JOIN event_reviews r ON r.event_id=e.id
                   WHERE e.run_id=? AND COALESCE(r.status,'pending')!='rejected'
                   ORDER BY CASE COALESCE(r.status,'pending') WHEN 'approved' THEN 0 ELSE 1 END,
                            e.value_score DESC,e.id ASC""",
                (latest_run["id"],),
            ).fetchall()
            result = []
            for row in rows:
                sources = conn.execute(
                    """SELECT s.id,s.source,s.title,s.url,s.discussion_url,s.content,s.published_at,s.collected_at,
                              s.created_at,s.updated_at,s.pushed_at,s.released_at,s.event_type,
                              s.metrics_json,s.is_primary_source,s.evidence_role,s.publisher_id,s.publisher_type,
                              s.original_publisher_id,s.original_url,s.is_independent,s.is_repost,
                              s.supports_claims_json,s.contradicts_claims_json
                       FROM source_items s JOIN event_sources es ON es.source_item_id=s.id WHERE es.event_id=?""",
                    (row["id"],),
                ).fetchall()
                review = conn.execute(
                    "SELECT status,note,reviewed_at FROM event_reviews WHERE event_id=?", (row["id"],)
                ).fetchone()
                event = dict(row)
                event["score_breakdown"] = json.loads(event.pop("score_breakdown_json") or "{}")
                event["claims"] = json.loads(event.pop("claims_json") or "[]")
                event["business_impact"] = json.loads(event.pop("business_impact_json") or "{}")
                event["metric_deltas"] = json.loads(event.pop("metric_deltas_json") or "{}")
                event["event_signature"] = json.loads(event.pop("event_signature_json") or "{}")
                event["decision_tasks"] = json.loads(event.pop("decision_tasks_json") or "[]")
                event["upgrade_conditions"] = json.loads(event.pop("upgrade_conditions_json") or "[]")
                result.append(event | {
                    "sources": [self._source_payload(item) for item in sources],
                    "review": dict(review) if review else {"status": "pending", "note": "", "reviewed_at": None},
                })
        if task_id in {3, 4}:
            def domain_priority(event: dict[str, Any]) -> tuple[int, int, int, float]:
                source_quality = max(
                    (3 if source["source"] == "rss" and source["is_primary_source"] else
                     2 if source["source"] == "rss" else
                     1 if source["source"] == "hacker_news" else 0)
                    for source in event["sources"]
                )
                return (
                    source_quality,
                    int(event["platform_count"]),
                    int(event["source_count"]),
                    float(event["attention_signal"]),
                )

            result.sort(key=domain_priority, reverse=True)
        return result[:limit]

    @staticmethod
    def _source_payload(row: sqlite3.Row) -> dict[str, Any]:
        source = dict(row)
        source["metrics"] = json.loads(source.pop("metrics_json") or "{}")
        source["supports_claims"] = json.loads(source.pop("supports_claims_json", "[]") or "[]")
        source["contradicts_claims"] = json.loads(source.pop("contradicts_claims_json", "[]") or "[]")
        excerpt = (source.get("content") or "").strip()[:360]
        event_type = source.get("event_type")
        if event_type == "repository_updated":
            claim = "该仓库近期活跃"
            can_prove = "仓库存在且近期发生 push 或更新"
            cannot_prove = "项目在本周首次发布、已形成行业趋势"
        elif event_type == "repository_created":
            claim = "该 GitHub 仓库近期创建"
            can_prove = "仓库存在且创建时间可验证"
            cannot_prove = "项目已被广泛采用或具有高商业价值"
        else:
            claim = "该来源在标注时间发布了相关内容"
            can_prove = "原文标题、时间和来源可回溯"
            cannot_prove = "单一来源不能独立证明热点已成立"
        source.update({"excerpt": excerpt, "claim": claim, "can_prove": can_prove, "cannot_prove": cannot_prove})
        return source

    def get_event_with_sources(self, event_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            if not row:
                return None
            sources = conn.execute(
                """SELECT s.* FROM source_items s JOIN event_sources es ON es.source_item_id=s.id
                   WHERE es.event_id=? ORDER BY s.is_primary_source DESC,s.published_at""", (event_id,),
            ).fetchall()
        event = dict(row)
        event["score_breakdown"] = json.loads(event.pop("score_breakdown_json") or "{}")
        event["claims"] = json.loads(event.pop("claims_json") or "[]")
        event["business_impact"] = json.loads(event.pop("business_impact_json") or "{}")
        event["metric_deltas"] = json.loads(event.pop("metric_deltas_json") or "{}")
        event["event_signature"] = json.loads(event.pop("event_signature_json") or "{}")
        event["decision_tasks"] = json.loads(event.pop("decision_tasks_json") or "[]")
        event["upgrade_conditions"] = json.loads(event.pop("upgrade_conditions_json") or "[]")
        event["sources"] = [self._source_payload(source) for source in sources]
        return event

    def filtering_reasons(self, task_id: int) -> dict[str, Any] | None:
        summary = self.latest_run_summary(task_id)
        if not summary:
            return None
        return {
            "run_id": summary["id"], "raw": summary["items_collected"],
            "invalid": summary["invalid_items"], "excluded": summary["excluded_items"],
            "duplicates": summary["duplicate_items"], "relevance_filtered": summary["relevance_filtered"],
            "cluster_merged": summary["cluster_merged"], "high_value": summary["high_value_hotspots"],
            "watchlist": summary["watchlist_events"], "candidate": summary["low_confidence_candidates"],
        }

    def scoring_diagnostics(self, task_id: int) -> dict[str, Any] | None:
        summary = self.latest_run_summary(task_id)
        if not summary:
            return None
        with self.connect() as conn:
            events = conn.execute(
                "SELECT * FROM events WHERE run_id=? ORDER BY value_score DESC", (summary["id"],)
            ).fetchall()
            historical_zero = int(conn.execute(
                """SELECT COUNT(*) FROM events e JOIN agent_runs r ON r.id=e.run_id
                   WHERE r.task_id=? AND e.value_score=0""", (task_id,),
            ).fetchone()[0])
        component_zero = {name: 0 for name in ("relevance", "growth", "adoption", "cross_platform", "source_strength", "novelty")}
        for event in events:
            breakdown = json.loads(event["score_breakdown_json"] or "{}")
            for name in component_zero:
                if float((breakdown.get(name) or {}).get("contribution") or 0) == 0:
                    component_zero[name] += 1
        single_source = sum(int(event["source_count"] or 0) <= 1 for event in events)
        single_platform = sum(int(event["platform_count"] or 0) <= 1 for event in events)
        no_growth = sum(event["growth_percent"] is None or float(event["growth_percent"]) <= 0 for event in events)
        return {
            "run_id": summary["id"],
            "event_count": len(events),
            "average_value_score": round(sum(float(event["value_score"]) for event in events) / len(events), 1) if events else 0,
            "zero_value_events": sum(float(event["value_score"]) == 0 for event in events),
            "historical_zero_events_after_backfill": historical_zero,
            "single_source_events": single_source,
            "single_platform_events": single_platform,
            "no_positive_growth_events": no_growth,
            "component_zero_counts": component_zero,
            "source_distribution": summary["sources"],
            "assessment": [
                "旧版数据库中的 0 分来自新增评分字段的迁移默认值；系统现已按已保存指标回填。",
                f"最新一轮有 {single_source}/{len(events)} 个事件只有一个来源，跨源验证能力偏弱。",
                f"最新一轮有 {no_growth}/{len(events)} 个事件没有可证明的正增长，因此增长项不加分。",
                "数据源采集并未整体失效；主要瓶颈是同一事件难以跨平台聚合，以及历史快照不足。",
            ],
        }

    def data_source_overview(self, task_id: int) -> dict[str, Any] | None:
        """返回最新一轮真实来源明细，而不是前端写死的平台数量。"""
        summary = self.latest_run_summary(task_id)
        if not summary:
            return None
        task = self.get_task(task_id)
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT s.id,s.source,s.title,s.url,s.author,s.published_at,s.collected_at,
                          s.event_type,s.is_primary_source,s.metrics_json,
                          COUNT(DISTINCT es.event_id) AS used_by_events
                   FROM source_items s
                   LEFT JOIN event_sources es ON es.source_item_id=s.id
                   WHERE s.run_id=?
                   GROUP BY s.id
                   ORDER BY s.source,s.published_at DESC""",
                (summary["id"],),
            ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
            item["hostname"] = (urlsplit(item["url"]).hostname or "").removeprefix("www.")
            grouped.setdefault(item["source"], []).append(item)
        return {
            "run_id": summary["id"],
            "completed_at": summary["completed_at"],
            "task": {"id": task.id, "name": task.name, "topic": task.topic},
            "total_items": len(rows),
            "rss_feeds": task.rss_feeds,
            "groups": grouped,
        }

    def list_approved_events(self, task_id: int = 1, limit: int = 10) -> list[dict[str, Any]]:
        return [
            event for event in self.list_latest_events(limit=100, task_id=task_id)
            if event["review"]["status"] == "approved"
        ][:limit]

    def record_email_delivery(
        self, task_id: int, recipient_count: int, hotspot_count: int, subject: str, status: str = "sent",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO email_deliveries(task_id,sent_at,recipient_count,hotspot_count,subject,status)
                   VALUES(?,?,?,?,?,?)""",
                (task_id, datetime.now(timezone.utc).isoformat(), recipient_count, hotspot_count, subject, status),
            )
        return int(cursor.lastrowid)
