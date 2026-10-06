"""Runtime configuration. Everything comes from environment variables so the
same image runs locally (docker compose), in CI and on Fly.io."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _database_url() -> str:
    """DATABASE_URL, or the content of DATABASE_URL_FILE (Fly --file-secret for
    scheduled Machines). Normalised to the psycopg 3 driver for SQLAlchemy."""
    url = os.environ.get("DATABASE_URL")
    path = os.environ.get("DATABASE_URL_FILE")
    if not url and path and Path(path).exists():
        url = Path(path).read_text().strip()
    url = url or "postgresql+psycopg://aletheia@localhost:5432/aletheia"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    return url


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=_database_url)
    # Anthropic. The key is read only on the server and never sent to the client.
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY") or None)
    # Provider: "anthropic" (default) or "openai_compatible" (e.g. Kimi/Moonshot at https://api.moonshot.ai/v1).
    chat_provider: str = field(default_factory=lambda: os.environ.get("CHAT_PROVIDER", "anthropic"))
    chat_base_url: str = field(default_factory=lambda: os.environ.get("CHAT_BASE_URL", "https://api.moonshot.ai/v1"))
    chat_api_key: str | None = field(default_factory=lambda: os.environ.get("CHAT_API_KEY") or None)
    chat_model: str = field(default_factory=lambda: os.environ.get("CHAT_MODEL", "claude-sonnet-5-5"))
    # Reasoning models on OpenAI-compatible APIs (Kimi) spend tokens thinking before answering.
    chat_max_tokens: int = field(default_factory=lambda: _int(
        "CHAT_MAX_TOKENS", 4000 if os.environ.get("CHAT_PROVIDER", "anthropic") == "openai_compatible" else 1200))

    @property
    def chat_key(self) -> str | None:
        return self.anthropic_api_key if self.chat_provider == "anthropic" else self.chat_api_key
    # Abuse and cost controls.
    chat_rate_per_ip_per_hour: int = field(default_factory=lambda: _int("CHAT_RATE_PER_IP_PER_HOUR", 30))
    chat_daily_budget_usd_cents: int = field(default_factory=lambda: _int("CHAT_DAILY_BUDGET_CENTS", 2000))
    # Approximate prices used only for the daily budget guard (cents per million tokens).
    chat_price_in_cents_per_mtok: int = field(default_factory=lambda: _int("CHAT_PRICE_IN_CENTS_PER_MTOK", 300))
    chat_price_out_cents_per_mtok: int = field(default_factory=lambda: _int("CHAT_PRICE_OUT_CENTS_PER_MTOK", 1500))
    # LGPD: conversations are kept only for quality audit, then purged.
    chat_retention_days: int = field(default_factory=lambda: _int("CHAT_RETENTION_DAYS", 30))
    # Editorial panel (HTTP Basic over TLS in production).
    admin_user: str = field(default_factory=lambda: os.environ.get("ADMIN_USER", "editor"))
    admin_password: str | None = field(default_factory=lambda: os.environ.get("ADMIN_PASSWORD") or None)
    # Where the generated static site lives.
    site_dir: Path = field(default_factory=lambda: Path(os.environ.get("SITE_DIR", str(ROOT / "build" / "site"))))
    # Render sets RENDER_EXTERNAL_URL automatically; PUBLIC_BASE_URL overrides it (custom domain).
    public_base_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_BASE_URL")
                                 or os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:8080")
    country_code: str = field(default_factory=lambda: os.environ.get("COUNTRY", "BR"))


LANGS = ("pt", "es", "en")
DEFAULT_LANG = "pt"


def get_settings() -> Settings:
    return Settings()
