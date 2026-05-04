"""Preference Memory - stable output style and interaction preferences."""

from __future__ import annotations

from pydantic import Field

from .base import MemoryBase


class PreferenceMemory(MemoryBase):
    """
    User's stable output and interaction preferences.
    Requires at least 2 consistent occurrences across different conversations
    before graduating to long-term preference.
    """

    style_preference: list[str] = Field(default_factory=list)
    terminology_preference: list[str] = Field(default_factory=list)
    formatting_constraints: list[str] = Field(default_factory=list)
    forbidden_expressions: list[str] = Field(default_factory=list)
    language_preference: str = ""
    primary_task_types: list[str] = Field(default_factory=list)
    revision_preference: list[str] = Field(default_factory=list)
    response_granularity: str = ""  # e.g. "concise", "detailed", "step-by-step"

    def to_markdown(self) -> str:
        lines = ["# Preference Memory\n"]
        if self.language_preference:
            lines.append(f"**Language:** {self.language_preference}")
        if self.primary_task_types:
            lines.append(f"**Primary Task Types:** {', '.join(self.primary_task_types)}")
        if self.response_granularity:
            lines.append(f"**Response Granularity:** {self.response_granularity}")
        if self.style_preference:
            items = "\n".join(f"- {s}" for s in self.style_preference)
            lines.append(f"\n**Style Preferences:**\n{items}")
        if self.terminology_preference:
            items = "\n".join(f"- {t}" for t in self.terminology_preference)
            lines.append(f"\n**Terminology Preferences:**\n{items}")
        if self.formatting_constraints:
            items = "\n".join(f"- {f}" for f in self.formatting_constraints)
            lines.append(f"\n**Formatting Constraints:**\n{items}")
        if self.forbidden_expressions:
            items = "\n".join(f"- {e}" for e in self.forbidden_expressions)
            lines.append(f"\n**Forbidden Expressions:**\n{items}")
        if self.revision_preference:
            items = "\n".join(f"- {r}" for r in self.revision_preference)
            lines.append(f"\n**Revision Preferences:**\n{items}")
        ts = self.updated_at.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n---\n*v{self.version} · updated {ts}*")
        return "\n".join(lines)
