"""Workflow Memory - recurring task patterns the user applies frequently."""

from __future__ import annotations

from pydantic import Field

from .base import MemoryBase


class WorkflowMemory(MemoryBase):
    """
    Captures recurring task modes and workflows.
    Only graduates to long-term when the same pattern appears 3+ times
    across different conversations.
    """

    workflow_name: str
    trigger_condition: str = ""
    typical_steps: list[str] = Field(default_factory=list)
    preferred_artifact_format: str = ""
    review_style: str = ""
    escalation_rule: str = ""
    reuse_frequency: str = ""  # "daily" | "weekly" | "per-project" | "ad-hoc"
    occurrence_count: int = 1

    def to_markdown(self) -> str:
        lines = [f"# Workflow: {self.workflow_name}\n"]
        if self.trigger_condition:
            lines.append(f"**Triggered when:** {self.trigger_condition}")
        if self.reuse_frequency:
            lines.append(f"**Frequency:** {self.reuse_frequency}")
        if self.typical_steps:
            items = "\n".join(f"{i+1}. {s}" for i, s in enumerate(self.typical_steps))
            lines.append(f"\n**Typical Steps:**\n{items}")
        if self.preferred_artifact_format:
            lines.append(f"\n**Artifact Format:** {self.preferred_artifact_format}")
        if self.review_style:
            lines.append(f"**Review Style:** {self.review_style}")
        if self.escalation_rule:
            lines.append(f"**Escalation Rule:** {self.escalation_rule}")
        ts = self.updated_at.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(
            f"\n---\n*Observed {self.occurrence_count}x · v{self.version} · updated {ts}*"
        )
        return "\n".join(lines)
