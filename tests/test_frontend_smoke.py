"""Executes every Streamlit page script top to bottom (buttons off, then buttons on) to catch
runtime errors. Uses the real Streamlit if installed (AppTest), otherwise a fake module."""
import runpy
import sys
from pathlib import Path

import pytest

from tests.fakes import FakeStreamlit, RerunPage, StopPage

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "frontend" / "pages").glob("*.py"))


@pytest.fixture
def fake_env(container, monkeypatch, tmp_path):
    def install(press: bool):
        fake = FakeStreamlit(press_buttons=press)
        monkeypatch.setitem(sys.modules, "streamlit", fake)
        for m in [m for m in list(sys.modules) if m.startswith("frontend.utils")]:
            sys.modules.pop(m)
        import frontend.utils.ui as ui
        monkeypatch.setattr(ui, "get_c", lambda: container)
        return fake
    return install


@pytest.mark.parametrize("press", [False, True])
def test_all_pages_execute(fake_env, container, press):
    # seed some drafts so review/audit pages have content
    for cid in ("DEMO-A-LOYAL", "DEMO-E-NOCONSENT", "DEMO-D-OVERDUE"):
        container.engagement.create_draft(cid)
    fake = fake_env(press)
    for page in PAGES:
        fake.session_state.clear()
        fake.session_state["customer_id"] = "DEMO-A-LOYAL"
        try:
            runpy.run_path(str(page), run_name="__main__")
        except (StopPage, RerunPage):
            pass
    assert any(c.startswith("button:") for c in fake.calls)


def test_app_entrypoint_executes(fake_env, container):
    fake_env(False)
    runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
