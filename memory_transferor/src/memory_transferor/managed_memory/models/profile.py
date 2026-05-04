"""Profile Memory - stable user identity and background."""

from __future__ import annotations

from pydantic import Field

from .base import MemoryBase


class ProfileMemory(MemoryBase):
    """
    Long-lived user identity. Changes infrequently.
    Requires multi-turn evidence or explicit user statement to update.
    """

    name_or_alias: str = ""
    role_identity: str = ""
    domain_background: list[str] = Field(default_factory=list)
    organization_or_affiliation: str = ""
    common_languages: list[str] = Field(default_factory=list)
    primary_task_types: list[str] = Field(default_factory=list)
    long_term_research_or_work_focus: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        lines = ["# Profile Memory\n"]
        if self.name_or_alias:
            lines.append(f"**Name / Alias:** {self.name_or_alias}")
        if self.role_identity:
            lines.append(f"**Role:** {self.role_identity}")
        if self.organization_or_affiliation:
            lines.append(f"**Organization:** {self.organization_or_affiliation}")
        if self.domain_background:
            lines.append(f"**Domain Background:** {', '.join(self.domain_background)}")
        if self.common_languages:
            lines.append(f"**Languages:** {', '.join(self.common_languages)}")
        if self.primary_task_types:
            lines.append(f"**Primary Task Types:** {', '.join(self.primary_task_types)}")
        if self.long_term_research_or_work_focus:
            focus = "\n".join(f"- {f}" for f in self.long_term_research_or_work_focus)
            lines.append(f"\n**Long-term Focus:**\n{focus}")
        ts = self.updated_at.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n---\n*v{self.version} · updated {ts}*")
        return "\n".join(lines)
