"""LLM provider abstraction (shared infrastructure, owned by Person 3).

* AnthropicProvider: Claude Messages API (official SDK if installed, otherwise HTTPS via urllib).
* OpenAICompatibleProvider: any /chat/completions endpoint (OPENAI_BASE_URL + OPENAI_API_KEY).
* NoLLMProvider: used when no credentials exist; callers fall back to static templates.
Credentials only come from environment variables.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import Settings


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class LLMProvider:
    name = "base"
    model = "none"
    available = False

    def complete(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        raise NotImplementedError


class NoLLMProvider(LLMProvider):
    name = "none"
    model = "static-template"
    available = False

    def complete(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        raise LLMError("No LLM provider configured")


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"content-type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")[:500]
        raise LLMError(f"HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LLMError(f"Network error: {exc}") from exc


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    available = True

    def __init__(self, api_key: str, model: str, timeout: int = 60):
        self.api_key, self.model, self.timeout = api_key, model, timeout
        try:
            import anthropic  # type: ignore

            self._sdk = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        except Exception:
            self._sdk = None

    def complete(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        start = time.perf_counter()
        if self._sdk is not None:
            try:
                msg = self._sdk.messages.create(model=self.model, system=system, max_tokens=max_tokens,
                                                temperature=temperature, messages=[{"role": "user", "content": user}])
            except Exception as exc:
                raise LLMError(str(exc)) from exc
            text = "".join(getattr(b, "text", "") for b in msg.content)
            usage = getattr(msg, "usage", None)
            return LLMResponse(text, self.model, getattr(usage, "input_tokens", 0) or 0,
                               getattr(usage, "output_tokens", 0) or 0, int((time.perf_counter() - start) * 1000))
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {"model": self.model, "system": system, "max_tokens": max_tokens, "temperature": temperature,
             "messages": [{"role": "user", "content": user}]},
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, self.timeout)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        return LLMResponse(text, self.model, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                           int((time.perf_counter() - start) * 1000))


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"
    available = True

    def __init__(self, base_url: str, api_key: str | None, model: str, timeout: int = 60):
        self.base_url, self.api_key, self.model, self.timeout = base_url.rstrip("/"), api_key, model, timeout

    def complete(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        start = time.perf_counter()
        headers = {"authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post_json(f"{self.base_url}/chat/completions",
                          {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                          headers, self.timeout)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response: {str(data)[:300]}") from exc
        usage = data.get("usage", {})
        return LLMResponse(text, self.model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                           int((time.perf_counter() - start) * 1000))


def get_provider(settings: Settings, purpose: str = "generation") -> LLMProvider:
    choice = settings.llm_provider
    if choice in ("auto", "anthropic") and settings.anthropic_api_key:
        model = settings.judge_model if purpose == "judge" else settings.anthropic_model
        return AnthropicProvider(settings.anthropic_api_key, model, settings.llm_timeout_s)
    if choice in ("auto", "openai_compatible") and settings.openai_base_url:
        return OpenAICompatibleProvider(settings.openai_base_url, settings.openai_api_key, settings.openai_model,
                                        settings.llm_timeout_s)
    return NoLLMProvider()


def extract_json(text: str) -> dict:
    """Parse the first JSON object in an LLM reply (tolerates code fences and prose)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else t
    start = t.find("{")
    if start < 0:
        raise ValueError("No JSON object found in model output")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("Unbalanced JSON object in model output")
