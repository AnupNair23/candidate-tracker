"""Environment-driven settings (`.env` at the repo root or in backend/)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]  # app/core/config.py → backend/
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    # Claude. LLM_MODE=stub swaps in a deterministic keyword assessor (dev only, labelled in the UI).
    llm_mode: Literal["claude", "stub"] = "claude"
    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort_intent: str = "low"
    claude_effort_assess: str = "low"
    claude_fallbacks_enabled: bool = True
    claude_timeout_s: float = 90.0
    claude_max_retries: int = 1

    # JobDiva (API v1)
    jobdiva_base_url: str = "https://api.jobdiva.com"
    jobdiva_client_id: str | None = None
    jobdiva_username: str | None = None
    jobdiva_password: SecretStr | None = None
    jobdiva_page_size: int = 30
    jobdiva_max_concurrency: int = 2
    jobdiva_min_interval_s: float = 0.25
    jobdiva_max_retries: int = 3
    jobdiva_backoff_base_s: float = 2.0
    jobdiva_timeout_s: float = 60.0
    jobdiva_jobs_cache_ttl_s: float = 60.0
    # Optional /api/bi/* calls (notes, resume text, work history). Off: only /api/jobdiva/* is used.
    jobdiva_use_bi: bool = False
    # JOBDIVA_MOCK=true serves a synthetic dataset through an in-process transport (dev/tests only).
    jobdiva_mock: bool = False

    # Search pipeline
    search_call_budget: int = 300
    pool_target: int = 200
    stage2_top_n: int = 40
    assess_batch_size: int = 8
    assess_concurrency: int = 5
    shortlist_size: int = 30
    search_deadline_s: float = 180.0
    resume_char_cap: int = 16000

    # Snapshot (overwritten on every search)
    snapshot_path: Path = BACKEND_DIR / ".cache" / "search_snapshot.json"
    snapshot_replay: bool = False

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Deploy. HTTP basic auth guards everything (except GET /healthz) when both are set; unset = open (local dev).
    basic_auth_user: str | None = None
    basic_auth_password: SecretStr | None = None
    # Built frontend (Vite `dist/`) served by FastAPI with SPA fallback. Unset in local dev (Vite proxies /api).
    frontend_dist: Path | None = None

    @property
    def basic_auth_enabled(self) -> bool:
        return bool(self.basic_auth_user and self.basic_auth_password and self.basic_auth_password.get_secret_value())

    @property
    def jobdiva_configured(self) -> bool:
        if self.jobdiva_mock:
            return True
        return bool(self.jobdiva_client_id and self.jobdiva_username and self.jobdiva_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
