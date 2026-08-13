from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    ai_mode: str = os.getenv("AI_MODE", "rules").strip().lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    openai_api_style: str = os.getenv("OPENAI_API_STYLE", "responses").strip().lower()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip()
    github_token: str = os.getenv("GITHUB_TOKEN", "").strip()
    rss_feeds_raw: str = os.getenv("RSS_FEEDS", "").strip()
    database_path_raw: str = os.getenv("DATABASE_PATH", "data/trendscope.db").strip()
    report_dir_raw: str = os.getenv("REPORT_DIR", "reports").strip()
    schedule_enabled: bool = _bool("SCHEDULE_ENABLED", False)
    schedule_minutes: int = max(5, int(os.getenv("SCHEDULE_MINUTES", "60")))
    max_items_per_source: int = max(5, min(50, int(os.getenv("MAX_ITEMS_PER_SOURCE", "20"))))
    request_timeout_seconds: float = max(5.0, float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")))
    llm_timeout_seconds: float = max(30.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "120")))
    smtp_host: str = os.getenv("SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password: str = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_use_tls: bool = _bool("SMTP_USE_TLS", True)
    smtp_use_ssl: bool = _bool("SMTP_USE_SSL", False)
    email_from: str = os.getenv("EMAIL_FROM", "").strip()
    email_recipients_raw: str = os.getenv("EMAIL_RECIPIENTS", "").strip()
    log_level: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    @property
    def database_path(self) -> Path:
        path = Path(self.database_path_raw)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def report_dir(self) -> Path:
        path = Path(self.report_dir_raw)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def rss_feeds(self) -> list[str]:
        return [item.strip() for item in self.rss_feeds_raw.split(",") if item.strip()]

    @property
    def effective_ai_mode(self) -> str:
        if self.ai_mode == "openai" and self.openai_api_key:
            return "openai"
        return "rules"

    @property
    def email_recipients(self) -> list[str]:
        return [item.strip() for item in self.email_recipients_raw.split(",") if item.strip()]

    @property
    def email_configured(self) -> bool:
        return bool(
            self.smtp_host and self.smtp_username and self.smtp_password
            and (self.email_from or self.smtp_username) and self.email_recipients
        )


settings = Settings()
