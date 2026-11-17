"""Minimal stand-ins for `streamlit` and `fastapi`, used ONLY when the real packages are not
installed, so page scripts and route functions can still be executed by the test suite.
With the real packages installed, tests use them instead (see test_api.py / test_frontend_smoke.py)."""
from __future__ import annotations

import types
from typing import Any


# ------------------------------------------------------------------ streamlit
class StopPage(Exception):
    pass


class RerunPage(Exception):
    pass


class _SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as exc:
            raise AttributeError(k) from exc

    def __setattr__(self, k, v):
        self[k] = v


class _Ctx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)

    def progress(self, *a, **k):
        return self


def _noop(*a, **k):
    return None


class FakeStreamlit(types.ModuleType):
    def __init__(self, press_buttons: bool = False):
        super().__init__("streamlit")
        self.__version__ = "1.50.0"
        self.press = press_buttons
        self.session_state = _SessionState()
        self.calls: list[str] = []
        self.sidebar = _Ctx(self)
        self._cache: dict[Any, Any] = {}

    def __getattr__(self, name):  # any API not modelled below is a no-op
        if name.startswith("__"):
            raise AttributeError(name)
        return _noop

    # caching decorators (with or without arguments)
    def cache_resource(self, func=None, **_):
        def deco(f):
            def wrapper(*a, **k):
                key = (f.__qualname__, a, tuple(sorted(k.items())))
                if key not in self._cache:
                    self._cache[key] = f(*a, **k)
                return self._cache[key]
            return wrapper
        return deco(func) if callable(func) else deco

    cache_data = cache_resource

    # layout
    def columns(self, spec, **_):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx(self) for _ in range(n)]

    def tabs(self, labels):
        return [_Ctx(self) for _ in labels]

    def expander(self, *a, **k):
        return _Ctx(self)

    container = form = spinner = status = empty = expander

    def progress(self, *a, **k):
        return _Ctx(self)

    # widgets
    def selectbox(self, label, options, index=0, format_func=str, **_):
        opts = list(options)
        for o in opts:
            format_func(o)
        return opts[index] if opts else None

    def multiselect(self, label, options, default=None, **_):
        return list(default or [])

    def radio(self, label, options, index=0, **_):
        return list(options)[index]

    def text_input(self, label, value="", **_):
        return value

    text_area = text_input

    def number_input(self, label, min_value=None, max_value=None, value=None, step=None, **_):
        return value if value is not None else (min_value or 0)

    def checkbox(self, label, value=False, **_):
        return value

    toggle = checkbox

    def button(self, label, *a, **k):
        self.calls.append(f"button:{label}")
        return self.press and not k.get("disabled", False)

    def form_submit_button(self, label="Submit", *a, **k):
        self.calls.append(f"submit:{label}")
        return self.press

    def file_uploader(self, *a, **k):
        return None

    def download_button(self, *a, **k):
        return False

    # navigation
    def Page(self, path, title=None, icon=None, default=False):  # noqa: N802
        return types.SimpleNamespace(path=path, title=title)

    def navigation(self, pages):
        return types.SimpleNamespace(run=lambda: None, pages=pages)

    def stop(self):
        raise StopPage()

    def rerun(self):
        raise RerunPage()


# ------------------------------------------------------------------ fastapi
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any = None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


def _passthrough(default=None, *a, **k):
    return default


class _Router:
    def __init__(self, *a, **k):
        self.routes: list[tuple[str, str, Any]] = []

    def _add(self, method, path, **_):
        def deco(f):
            self.routes.append((method, path, f))
            return f
        return deco

    def get(self, path, **k):
        return self._add("GET", path, **k)

    def post(self, path, **k):
        return self._add("POST", path, **k)

    def include_router(self, r, **_):
        self.routes += r.routes


def make_fake_fastapi() -> types.ModuleType:
    m = types.ModuleType("fastapi")
    m.APIRouter = _Router
    m.FastAPI = _Router
    m.HTTPException = HTTPException
    m.Depends = lambda dep=None: None
    m.Query = _passthrough
    m.File = _passthrough
    m.UploadFile = object
    return m
