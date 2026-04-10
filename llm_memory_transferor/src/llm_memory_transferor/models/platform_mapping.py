"""Platform Mapping Memory - field alignment between platforms."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import MemoryBase


class FieldMapping(MemoryBase):
    """Maps a single source field to a target platform field."""

    source_field: str
    target_field: str
    transform: str = "direct"  # "direct" | "truncate" | "split" | "merge" | "drop"
    notes: str = ""


class PlatformMappingMemory(MemoryBase):
    """
    Describes how to translate L2 Managed MWiki objects into a
    specific platform's memory/profile/instruction format.
    Maintained by the system; not auto-extracted from user conversations.
    """

    source_platform: str
    target_platform: str
    supported_field_types: list[str] = Field(default_factory=list)
    mapping_rules: list[FieldMapping] = Field(default_factory=list)
    injection_template: str = ""  # Jinja2 template or structured prompt template
    unsupported_items: list[str] = Field(default_factory=list)
    fallback_strategy: str = "prompt-based bootstrap"  # for unsupported fields
    max_bootstrap_tokens: int = 2000

    def to_markdown(self) -> str:
        lines = [f"# Platform Mapping: {self.source_platform} → {self.target_platform}\n"]
        if self.supported_field_types:
            lines.append(f"**Supported Fields:** {', '.join(self.supported_field_types)}")
        if self.fallback_strategy:
            lines.append(f"**Fallback:** {self.fallback_strategy}")
        if self.mapping_rules:
            rows = [
                f"| {r.source_field} | {r.target_field} | {r.transform} | {r.notes} |"
                for r in self.mapping_rules
            ]
            table = (
                "| Source Field | Target Field | Transform | Notes |\n"
                "|---|---|---|---|\n" + "\n".join(rows)
            )
            lines.append(f"\n## Mapping Rules\n{table}")
        if self.unsupported_items:
            items = "\n".join(f"- {i}" for i in self.unsupported_items)
            lines.append(f"\n## Unsupported Items\n{items}")
        if self.injection_template:
            lines.append(f"\n## Injection Template\n```\n{self.injection_template}\n```")
        lines.append(f"\n---\n*v{self.version} · updated {self.updated_at.date()}*")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in platform mappings (shipped with the system)
# ---------------------------------------------------------------------------

BUILT_IN_MAPPINGS: dict[str, dict[str, Any]] = {
    "chatgpt": {
        "supported_field_types": [
            "custom_instructions",
            "memory_items",
            "user_profile_prompt",
        ],
        "injection_template": (
            "# About the user\n{profile_summary}\n\n"
            "# User preferences\n{preferences_summary}\n\n"
            "# Active projects\n{projects_summary}"
        ),
        "fallback_strategy": "prompt-based bootstrap",
        "max_bootstrap_tokens": 1500,
    },
    "claude": {
        "supported_field_types": [
            "system_prompt",
            "project_instructions",
            "saved_memory",
        ],
        "injection_template": (
            "<user_profile>\n{profile_summary}\n</user_profile>\n\n"
            "<preferences>\n{preferences_summary}\n</preferences>\n\n"
            "<active_projects>\n{projects_summary}\n</active_projects>"
        ),
        "fallback_strategy": "prompt-based bootstrap",
        "max_bootstrap_tokens": 2000,
    },
    "deepseek": {
        "supported_field_types": ["system_prompt"],
        "injection_template": (
            "User background: {profile_summary}\n"
            "Preferences: {preferences_summary}\n"
            "Current projects: {projects_summary}"
        ),
        "fallback_strategy": "prompt-based bootstrap",
        "max_bootstrap_tokens": 1000,
    },
    "kimi": {
        "supported_field_types": ["system_prompt", "memory"],
        "injection_template": (
            "用户背景：{profile_summary}\n"
            "用户偏好：{preferences_summary}\n"
            "当前项目：{projects_summary}"
        ),
        "fallback_strategy": "prompt-based bootstrap",
        "max_bootstrap_tokens": 1200,
    },
    "generic": {
        "supported_field_types": ["system_prompt"],
        "injection_template": (
            "# User Memory Bootstrap\n\n"
            "## Who I am\n{profile_summary}\n\n"
            "## My preferences\n{preferences_summary}\n\n"
            "## My active projects\n{projects_summary}"
        ),
        "fallback_strategy": "prompt-based bootstrap",
        "max_bootstrap_tokens": 2000,
    },
}
