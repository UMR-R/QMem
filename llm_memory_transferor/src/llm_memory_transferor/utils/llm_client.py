"""LLM client wrapper for memory extraction tasks.

Supports three backends, selected via the ``backend`` parameter or the
``MWIKI_LLM_BACKEND`` environment variable:

* ``anthropic``   – Anthropic Claude API (default when ANTHROPIC_API_KEY is set)
* ``openai``      – OpenAI API (GPT-4o, etc.)
* ``openai_compat`` – Any OpenAI-compatible server: Ollama, LM Studio,
                       vLLM, llama.cpp, etc.  Set OPENAI_BASE_URL to point
                       at your local server.

Backend selection order (first match wins):
1. Explicit ``backend=`` argument passed to LLMClient()
2. ``MWIKI_LLM_BACKEND`` env var
3. ``ANTHROPIC_API_KEY`` present  → ``anthropic``
4. ``OPENAI_API_KEY`` present     → ``openai``
5. ``OPENAI_BASE_URL`` present    → ``openai_compat``
6. Falls back to ``anthropic`` and lets the API call fail with a clear error.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

# ---------------------------------------------------------------------------
# Default models per backend
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    # "openai": "gpt-4o",
    "openai": "gpt-5.4-nano",
    "openai_compat": "llama3",  # sensible default; users override with --model
}

MAX_TOKENS = 4096


def _detect_backend() -> str:
    explicit = os.environ.get("MWIKI_LLM_BACKEND", "").strip().lower()
    if explicit:
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("OPENAI_BASE_URL"):
        return "openai_compat"
    return "anthropic"


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

class _AnthropicBackend:
    def __init__(self, api_key: str | None, model: str) -> None:
        import anthropic  # noqa: PLC0415
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model

    def complete(self, system: str, user: str, temperature: float) -> str:
        import anthropic  # noqa: PLC0415
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()


class _OpenAIBackend:
    """Handles both the real OpenAI API and any OpenAI-compatible server."""

    def __init__(self, api_key: str | None, model: str, base_url: str | None) -> None:
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for the openai / openai_compat backend. "
                "Install it with: pip install openai"
            ) from exc

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY") or "not-needed"
        resolved_url = base_url or os.environ.get("OPENAI_BASE_URL")

        kwargs: dict[str, Any] = {"api_key": resolved_key}
        if resolved_url:
            kwargs["base_url"] = resolved_url

        self.client = OpenAI(**kwargs)
        self.model = model

    def complete(self, system: str, user: str, temperature: float) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=MAX_TOKENS,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (response.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Public client
# ---------------------------------------------------------------------------

class LLMClient:
    """Backend-agnostic LLM wrapper for structured memory extraction."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        backend: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.backend_name = (backend or _detect_backend()).lower()
        default_model = _DEFAULTS.get(self.backend_name, "claude-sonnet-4-6")
        self.model = model or default_model

        if self.backend_name == "anthropic":
            self._backend: _AnthropicBackend | _OpenAIBackend = _AnthropicBackend(api_key, self.model)
        elif self.backend_name in ("openai", "openai_compat"):
            self._backend = _OpenAIBackend(api_key, self.model, base_url)
        else:
            raise ValueError(
                f"Unknown backend '{self.backend_name}'. "
                "Valid values: anthropic, openai, openai_compat"
            )

    # ------------------------------------------------------------------
    # Public interface (unchanged from original)
    # ------------------------------------------------------------------

    def extract_json(self, system: str, user: str, temperature: float = 0.0) -> Any:
        """Call the LLM and parse the first JSON object from the response."""
        text = self._backend.complete(system, user, temperature)
        return self._parse_json(text)

    def summarize(self, system: str, user: str, temperature: float = 0.3) -> str:
        """Return a plain-text response."""
        return self._backend.complete(system, user, temperature)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"```(?:json)?\s*(\{[\s\S]+?\}|\[[\s\S]+?\])\s*```", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return {}
