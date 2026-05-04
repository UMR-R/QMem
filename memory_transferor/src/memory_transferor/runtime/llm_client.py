"""LLM client wrapper for memory extraction tasks."""

from __future__ import annotations

import json
import os
import re
from typing import Any

_DEFAULTS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.4-nano",
    "openai_compat": "deepseek-chat",
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
    if os.environ.get("OPENAI_BASE_URL") or os.environ.get("MWIKI_API_KEY"):
        return "openai_compat"
    return "anthropic"


class _AnthropicBackend:
    def __init__(self, api_key: str | None, model: str) -> None:
        import anthropic  # noqa: PLC0415

        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model

    def complete(self, system: str, user: str, temperature: float) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()


class _OpenAIBackend:
    def __init__(self, api_key: str | None, model: str, base_url: str | None) -> None:
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for the openai / openai_compat backend. "
                "Install it with: pip install openai"
            ) from exc

        resolved_key = (
            api_key
            or os.environ.get("MWIKI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or "not-needed"
        )
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
        self.model = model or _DEFAULTS.get(self.backend_name, "claude-sonnet-4-6")

        if self.backend_name == "anthropic":
            self._backend: _AnthropicBackend | _OpenAIBackend = _AnthropicBackend(
                api_key,
                self.model,
            )
        elif self.backend_name in {"openai", "openai_compat"}:
            self._backend = _OpenAIBackend(api_key, self.model, base_url)
        else:
            raise ValueError(
                f"Unknown backend '{self.backend_name}'. "
                "Valid values: anthropic, openai, openai_compat"
            )

    def extract_json(self, system: str, user: str, temperature: float = 0.0) -> Any:
        """Call the LLM and parse the first JSON object from the response."""
        text = self._backend.complete(system, user, temperature)
        return self._parse_json(text)

    def summarize(self, system: str, user: str, temperature: float = 0.3) -> str:
        """Return a plain-text response."""
        return self._backend.complete(system, user, temperature)

    @staticmethod
    def _parse_json(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*(\{[\s\S]+?\}|\[[\s\S]+?\])\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}


__all__ = ["LLMClient", "_detect_backend"]
