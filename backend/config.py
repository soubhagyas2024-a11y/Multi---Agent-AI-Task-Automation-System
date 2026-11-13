"""Central configuration. All secrets come from environment variables / .env."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _secret_key() -> str:
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    path = ROOT / "data" / ".secret_key"
    try:
        if path.exists():
            return path.read_text().strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_urlsafe(48)
        path.write_text(key)
        return key
    except OSError:
        return secrets.token_urlsafe(48)


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + (ROOT / "data" / "agentflow.db").as_posix()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    secret_key: str = ""
    token_minutes: int = _int("TOKEN_MINUTES", 480)
    database_url: str = ""
    generated_dir: Path = Path(os.getenv("GENERATED_DIR", str(ROOT / "generated_files"))).resolve()
    logs_dir: Path = Path(os.getenv("LOGS_DIR", str(ROOT / "logs"))).resolve()
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    max_upload_mb: int = _int("MAX_UPLOAD_MB", 10)
    max_retries: int = _int("MAX_RETRIES", 2)
    verify_rounds: int = _int("VERIFY_ROUNDS", 1)
    task_timeout_seconds: int = _int("TASK_TIMEOUT_SECONDS", 600)
    max_concurrent_tasks: int = _int("MAX_CONCURRENT_TASKS", 4)
    llm_timeout: int = _int("LLM_TIMEOUT", 60)
    python_exec_timeout: int = _int("PYTHON_EXEC_TIMEOUT", 10)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 30)
    scheduler_enabled: bool = os.getenv("DISABLE_SCHEDULER", "0") != "1"
    cors_origins: tuple = tuple(
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",") if o.strip()
    )


settings = Settings(secret_key=_secret_key(), database_url=_db_url())
