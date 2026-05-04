"""Project Memory - long-running project state and context."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, Field

from .base import MemoryBase


class ProjectEntry(BaseModel):
    """A single timestamped entry within a project (decision, question, action, etc.)."""

    text: str
    timestamp: Optional[datetime] = None  # when this point was discussed

    def _ts_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M UTC") if self.timestamp else ""


def _coerce_entry(v: Any) -> Any:
    """Accept plain strings from old JSON files and coerce them to ProjectEntry dicts."""
    if isinstance(v, str):
        return {"text": v, "timestamp": None}
    return v


EntryField = Annotated[ProjectEntry, BeforeValidator(_coerce_entry)]


class ProjectMemory(MemoryBase):
    """
    Tracks a specific long-running project.
    Requires traceable evidence to a specific conversation or file.
    Updated frequently as project evolves.
    """

    project_name: str
    project_goal: str = ""
    current_stage: str = ""
    key_terms: dict[str, str] = Field(default_factory=dict)  # term -> definition
    finished_decisions: list[EntryField] = Field(default_factory=list)
    unresolved_questions: list[EntryField] = Field(default_factory=list)
    relevant_entities: list[EntryField] = Field(default_factory=list)
    important_constraints: list[EntryField] = Field(default_factory=list)
    next_actions: list[EntryField] = Field(default_factory=list)
    is_active: bool = True

    def to_markdown(self) -> str:
        lines = [f"# Project: {self.project_name}\n"]
        if self.project_goal:
            lines.append(f"**Goal:** {self.project_goal}")
        if self.current_stage:
            lines.append(f"**Current Stage:** {self.current_stage}")
        if self.key_terms:
            terms = "\n".join(f"- **{k}**: {v}" for k, v in self.key_terms.items())
            lines.append(f"\n**Key Terms:**\n{terms}")
        if self.finished_decisions:
            items = "\n".join(
                f"- [x] {e.text}" + (f" *({e._ts_str()})*" if e.timestamp else "")
                for e in self.finished_decisions
            )
            lines.append(f"\n**Finished Decisions:**\n{items}")
        if self.unresolved_questions:
            items = "\n".join(
                f"- [ ] {e.text}" + (f" *({e._ts_str()})*" if e.timestamp else "")
                for e in self.unresolved_questions
            )
            lines.append(f"\n**Unresolved Questions:**\n{items}")
        if self.relevant_entities:
            items = "\n".join(
                f"- {e.text}" + (f" *({e._ts_str()})*" if e.timestamp else "")
                for e in self.relevant_entities
            )
            lines.append(f"\n**Relevant Entities:**\n{items}")
        if self.important_constraints:
            items = "\n".join(
                f"- {e.text}" + (f" *({e._ts_str()})*" if e.timestamp else "")
                for e in self.important_constraints
            )
            lines.append(f"\n**Constraints:**\n{items}")
        if self.next_actions:
            items = "\n".join(
                f"- {e.text}" + (f" *({e._ts_str()})*" if e.timestamp else "")
                for e in self.next_actions
            )
            lines.append(f"\n**Next Actions:**\n{items}")
        status = "Active" if self.is_active else "Inactive"
        ts = self.updated_at.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n---\n*{status} · v{self.version} · updated {ts}*")
        return "\n".join(lines)
