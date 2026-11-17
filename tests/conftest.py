import os
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AS_OF_DATE", "2026-11-17")
os.environ["LLM_PROVIDER"] = "none"           # tests never call a paid API
os.environ["EMBEDDING_BACKEND"] = "tfidf"      # deterministic, offline
os.environ["VECTOR_BACKEND"] = "local"
os.environ["TONE_JUDGE_ENABLED"] = "false"

from backend.services.bootstrap import load_demo_customers  # noqa: E402
from backend.services.container import build_container  # noqa: E402
from config import Settings  # noqa: E402

AS_OF = date(2026, 11, 17)


def make_settings(tmp: Path, **overrides) -> Settings:
    base = Settings()
    return base.model_copy(update={"db_path": tmp / "test.db", "vector_store_dir": tmp / "vs", "as_of_date": AS_OF,
                                   "llm_provider": "none", "tone_judge_enabled": False, "reports_dir": tmp / "reports",
                                   **overrides})


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def container(tmp_path):
    c = build_container(make_settings(tmp_path))
    c.labels = load_demo_customers(c)
    return c


@pytest.fixture
def sim_container(tmp_path):
    """Container whose 'LLM' is the clearly-labelled offline simulator (exercises the LLM code path)."""
    c = build_container(make_settings(tmp_path, llm_provider="offline_simulator"))
    c.labels = load_demo_customers(c)
    return c
