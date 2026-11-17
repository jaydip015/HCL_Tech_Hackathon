"""Central configuration for the Customer Loyalty and Engagement Assistant.

Settings come from environment variables (see .env.example). Business rules live in
YAML files under ./policies so they can be changed without code changes.
"""
from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
_YAML_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (avoids a python-dotenv dependency). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


class Settings(BaseModel):
    base_dir: Path = BASE_DIR
    db_path: Path = Field(default_factory=lambda: Path(_env("DB_PATH", str(BASE_DIR / "data" / "cea.db"))))
    data_dir: Path = BASE_DIR / "data"
    policies_dir: Path = BASE_DIR / "policies"
    config_dir: Path = BASE_DIR / "config"
    knowledge_base_dir: Path = BASE_DIR / "knowledge_base"
    prompts_dir: Path = BASE_DIR / "prompts"
    reports_dir: Path = BASE_DIR / "reports"
    logs_dir: Path = BASE_DIR / "logs"
    vector_store_dir: Path = Field(
        default_factory=lambda: Path(_env("VECTOR_STORE_DIR", str(BASE_DIR / "data" / "vector_store")))
    )

    # Reference date for every "days since" calculation. Fixed dates make runs reproducible.
    as_of_date: date = Field(default_factory=lambda: date.fromisoformat(_env("AS_OF_DATE", date.today().isoformat())))
    synthetic_seed: int = Field(default_factory=lambda: int(_env("SYNTHETIC_SEED", "42")))

    # LLM configuration. Provider "none" means static templates only (fully offline).
    llm_provider: str = Field(default_factory=lambda: _env("LLM_PROVIDER", "auto"))  # auto|anthropic|openai_compatible|none
    anthropic_api_key: str | None = Field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = Field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    judge_model: str = Field(default_factory=lambda: _env("JUDGE_MODEL", "claude-haiku-5-5"))
    openai_base_url: str | None = Field(default_factory=lambda: _env("OPENAI_BASE_URL"))
    openai_api_key: str | None = Field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_model: str = Field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4o-mini"))
    llm_timeout_s: int = Field(default_factory=lambda: int(_env("LLM_TIMEOUT_S", "60")))
    tone_judge_enabled: bool = Field(default_factory=lambda: _env("TONE_JUDGE_ENABLED", "true").lower() == "true")

    # RAG configuration
    embedding_backend: str = Field(default_factory=lambda: _env("EMBEDDING_BACKEND", "auto"))  # auto|sentence_transformers|tfidf
    embedding_model: str = Field(default_factory=lambda: _env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    vector_backend: str = Field(default_factory=lambda: _env("VECTOR_BACKEND", "auto"))  # auto|chroma|local

    # Pricing used only for the cost estimate on the dashboard (USD per million tokens).
    price_input_per_mtok: float = Field(default_factory=lambda: float(_env("PRICE_INPUT_PER_MTOK", "3.0")))
    price_output_per_mtok: float = Field(default_factory=lambda: float(_env("PRICE_OUTPUT_PER_MTOK", "15.0")))

    model_config = {"arbitrary_types_allowed": True}

    # ---- YAML policy/config access -------------------------------------------------
    def load_yaml(self, name: str) -> dict[str, Any]:
        """Load a YAML file from ./policies (business rules) or ./config (technical config).
        Parsed files are cached and re-read only when the file's modification time changes."""
        for folder in (self.policies_dir, self.config_dir):
            path = folder / name
            if path.exists():
                mtime = path.stat().st_mtime
                cached = _YAML_CACHE.get(str(path))
                if cached and cached[0] == mtime:
                    return cached[1]
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                _YAML_CACHE[str(path)] = (mtime, data)
                return data
        raise FileNotFoundError(f"Config file not found: {name}")

    @property
    def segmentation(self) -> dict[str, Any]:
        return self.load_yaml("segmentation.yaml")

    @property
    def communication(self) -> dict[str, Any]:
        return self.load_yaml("communication.yaml")

    @property
    def reminders(self) -> dict[str, Any]:
        return self.load_yaml("payment_reminders.yaml")

    @property
    def offers_config(self) -> dict[str, Any]:
        return self.load_yaml("offers.yaml")

    @property
    def privacy(self) -> dict[str, Any]:
        return self.load_yaml("privacy.yaml")

    @property
    def data_mapping(self) -> dict[str, Any]:
        return self.load_yaml("data_mapping.yaml")

    @property
    def policy_version(self) -> str:
        """Combined version tag of all policy files, recorded on every decision."""
        parts = [
            self.segmentation.get("version", "?"),
            self.communication.get("version", "?"),
            self.reminders.get("version", "?"),
            self.offers_config.get("version", "?"),
            self.privacy.get("version", "?"),
        ]
        return "|".join(parts)

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.reports_dir, self.logs_dir, self.vector_store_dir, self.db_path.parent):
            Path(p).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
