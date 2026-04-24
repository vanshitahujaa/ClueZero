"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field

# Resolve .env once: prefer backend/.env (dev/Docker) then repo root /.env.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_CANDIDATES = [_BACKEND_DIR / ".env", _BACKEND_DIR.parent / ".env"]
_ENV_FILES = [str(p) for p in _ENV_CANDIDATES if p.exists()]


class Settings(BaseSettings):
    """Central configuration for the ClueZero backend."""

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = Field(
        default="",
        description="Postgres URL. asyncpg driver is auto-applied.",
    )

    # ── Redis ──────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── LLM ────────────────────────────────────────────────────────────────
    llm_provider: str = Field(default="openai", description="'openai' or 'gemini'")
    llm_model: str = Field(default="gpt-4o", description="The explicit model to invoke")
    llm_api_keys: str = Field(default="", description="Comma separated list of API keys")
    llm_base_url: str | None = Field(default=None, description="Optional custom endpoint")

    # ── Pricing (per 1K tokens, USD) ───────────────────────────────────────
    llm_input_price_per_1k: float = Field(default=0.005)
    llm_output_price_per_1k: float = Field(default=0.015)

    # ── Admin ──────────────────────────────────────────────────────────────
    admin_user: str = Field(default="admin")
    admin_pass: str = Field(default="changeme")

    # ── Sessions / LIFO ────────────────────────────────────────────────────
    session_heartbeat_timeout: int = Field(
        default=90,
        description="Seconds without a ping before a session is considered dead",
    )

    # ── Server / public URL ────────────────────────────────────────────────
    server_public_url: str = Field(
        default="http://localhost:8000",
        description="Used when rendering per-user installers",
    )

    # ── Image processing ───────────────────────────────────────────────────
    max_image_size_kb: int = Field(default=512)
    image_quality: int = Field(default=65)
    image_max_resolution: int = Field(default=720)

    # ── Rate limiting ──────────────────────────────────────────────────────
    rate_limit_seconds: int = Field(default=15)

    # ── Job TTL ────────────────────────────────────────────────────────────
    job_ttl_seconds: int = Field(default=600)
    job_result_ttl_seconds: int = Field(default=300)

    # ── Server ─────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # ── Default prompt ─────────────────────────────────────────────────────
    default_prompt: str = Field(
        default="If there is a coding problem visible in the screenshot, provide ONLY the raw code solution in the language shown. Do NOT include any explanations, do NOT include markdown formatting (like ```), and do NOT include comments in the code. Output purely the code required. If it's not a coding problem, answer as concisely as possible."
    )

    # ── Agent ──────────────────────────────────────────────────────────────
    agent_hotkey: str = Field(default="shift+tab+q")

    model_config = {
        "env_file": _ENV_FILES or ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
