"""Prompt loading helpers.

Prompt text remains in the repository-level ``prompts/`` directory so the old
backend path and the new canonical ``memory_transferor`` path share the same
node definitions.
"""

from __future__ import annotations

from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parents[4] / "prompts"

PROMPT_FILES = {
    "profile_system": "profile_system.txt",
    "preference_system": "preference_system.txt",
    "projects_system": "projects_system.txt",
    "workflows_system": "workflows_system.txt",
    "skills_system": "skills_system.txt",
    "daily_notes_system": "persistent_node_distill_bg.txt",
    "episode_system": "episode_system.txt",
    "delta_system": "delta_system.txt",
    "display_taxonomy_proposal": "display_taxonomy_proposal.txt",
    "platform_memory_collect": "platform_memory_collect.txt",
    "cold_start": "cold_start.txt",
    "schema": "schema.txt",
}


def load_prompt(name: str) -> str:
    if name not in PROMPT_FILES:
        raise KeyError(f"Unknown prompt: {name}")
    return (PROMPTS_DIR / PROMPT_FILES[name]).read_text(encoding="utf-8").strip()


def load_prompts() -> dict[str, str]:
    return {name: load_prompt(name) for name in PROMPT_FILES}


__all__ = ["PROMPTS_DIR", "PROMPT_FILES", "load_prompt", "load_prompts"]
