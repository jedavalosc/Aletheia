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


def _default_verifier_model() -> str:
    agent = os.environ.get("AGENT_MODEL") or os.environ.get("CHAT_MODEL", "claude-sonnet-5-5")
    alternatives = {"kimi-k3": "kimi-k2.6", "kimi-k2.6": "kimi-k3"}
    return alternatives.get(agent, agent)


def _thinking(env: str, provider: str, model: str) -> str | None:
    """Kimi reasoning mode for agent and verifier calls: 'disabled', 'enabled', or None (send nothing).
    Defaults to 'disabled' for Kimi models: with reasoning on, kimi-k3 spends ~10k tokens and ~5 minutes
    per extraction; with it off, ~2k tokens and ~45 s, and the claims still pass the code gates (D40)."""
    v = os.environ.get(env)
    if v is not None:
        return v.strip().lower() or None
    return "disabled" if provider == "openai_compatible" and model.startswith("kimi-") else None


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
    # Agents (docs/agentes.md). Default to the chat provider unless overridden.
    agent_provider: str = field(default_factory=lambda: os.environ.get("AGENT_PROVIDER")
                                or os.environ.get("CHAT_PROVIDER", "anthropic"))
    agent_model: str = field(default_factory=lambda: os.environ.get("AGENT_MODEL")
                             or os.environ.get("CHAT_MODEL", "claude-sonnet-5-5"))
    agent_base_url: str = field(default_factory=lambda: os.environ.get("AGENT_BASE_URL")
                                or os.environ.get("CHAT_BASE_URL", "https://api.moonshot.ai/v1"))
    agent_api_key: str | None = field(default_factory=lambda: os.environ.get("AGENT_API_KEY")
                                      or os.environ.get("CHAT_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or None)
    agent_max_tokens: int = field(default_factory=lambda: _int("AGENT_MAX_TOKENS", 4000))
    agent_budget_cents_per_run: int = field(default_factory=lambda: _int("AGENT_BUDGET_CENTS_PER_RUN", 100))
    # Drafting makes ~5 calls per event (draft, faithfulness check, repairs, two translations).
    agent_budget_cents_draft: int = field(default_factory=lambda: _int("AGENT_BUDGET_CENTS_DRAFT", 300))
    agent_price_in_cents_per_mtok: int = field(default_factory=lambda: _int("AGENT_PRICE_IN_CENTS_PER_MTOK",
                                                                            _int("CHAT_PRICE_IN_CENTS_PER_MTOK", 300)))
    agent_price_out_cents_per_mtok: int = field(default_factory=lambda: _int("AGENT_PRICE_OUT_CENTS_PER_MTOK",
                                                                             _int("CHAT_PRICE_OUT_CENTS_PER_MTOK", 1500)))
    # Independent checker for agent output (step 3). Ideally a different provider; defaults to a
    # different model on the same provider when only one key is available (docs/decisiones.md D36).
    verifier_provider: str = field(default_factory=lambda: os.environ.get("VERIFIER_PROVIDER")
                                   or os.environ.get("AGENT_PROVIDER") or os.environ.get("CHAT_PROVIDER", "anthropic"))
    verifier_model: str = field(default_factory=lambda: os.environ.get("VERIFIER_MODEL") or _default_verifier_model())
    verifier_base_url: str = field(default_factory=lambda: os.environ.get("VERIFIER_BASE_URL")
                                   or os.environ.get("AGENT_BASE_URL") or os.environ.get("CHAT_BASE_URL", "https://api.moonshot.ai/v1"))
    verifier_api_key: str | None = field(default_factory=lambda: os.environ.get("VERIFIER_API_KEY")
                                         or os.environ.get("AGENT_API_KEY") or os.environ.get("CHAT_API_KEY")
                                         or os.environ.get("ANTHROPIC_API_KEY") or None)
    @property
    def agent_thinking(self) -> str | None:
        return _thinking("AGENT_THINKING", self.agent_provider, self.agent_model)

    @property
    def verifier_thinking(self) -> str | None:
        return _thinking("VERIFIER_THINKING", self.verifier_provider, self.verifier_model)

    collector_user_agent: str = field(default_factory=lambda: os.environ.get(
        "COLLECTOR_USER_AGENT", "AletheiaNewsBot/0.1 (+https://aletheia-news.org/pt/metodologia.html)"))


LANGS = ("pt", "es", "en")
DEFAULT_LANG = "pt"


def get_settings() -> Settings:
    return Settings()
