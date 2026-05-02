from __future__ import annotations

import json
import os
import re
from typing import Any


class LLMClient:
    """Small OpenAI-compatible client used by the new memory path."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "deepseek-chat",
    ) -> None:
        from openai import OpenAI

        self.client = OpenAI(
            api_key=api_key or os.environ.get("MWIKI_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com/v1",
        )
        self.model = model

    def complete(self, system: str, user: str, *, temperature: float = 0.0) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def extract_json(self, system: str, user: str, *, temperature: float = 0.0) -> Any:
        text = self.complete(system, user, temperature=temperature)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise

