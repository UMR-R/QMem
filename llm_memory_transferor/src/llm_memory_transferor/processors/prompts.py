"""Prompt loader for memory processors.

Processor prompts live in the repository-level ``prompts/`` directory so users can
customize them without editing Python code.
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
    "episode_system": "episode_system.txt",
    "delta_system": "delta_system.txt",
    "display_taxonomy_proposal": "display_taxonomy_proposal.txt",
}


def load_processor_prompts() -> dict[str, str]:
    """Load all processor prompts from ``prompts/``."""
    loaded: dict[str, str] = {}
    missing: list[str] = []
    for key, filename in PROMPT_FILES.items():
        path = PROMPTS_DIR / filename
        try:
            loaded[key] = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            missing.append(str(path))
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"Missing processor prompt file(s): {missing_text}")
    return loaded


def get_processor_prompt(name: str) -> str:
    """Load a single processor prompt by logical name."""
    if name not in PROMPT_FILES:
        raise KeyError(f"Unknown processor prompt: {name}")
    return load_processor_prompts()[name]


_PROFILE_SYSTEM = get_processor_prompt("profile_system")
_PREFERENCE_SYSTEM = get_processor_prompt("preference_system")
_PROJECTS_SYSTEM = get_processor_prompt("projects_system")
_WORKFLOWS_SYSTEM = get_processor_prompt("workflows_system")
_SKILLS_SYSTEM = get_processor_prompt("skills_system")
_EPISODE_SYSTEM = get_processor_prompt("episode_system")
_DELTA_SYSTEM = get_processor_prompt("delta_system")
_DISPLAY_TAXONOMY_PROPOSAL = get_processor_prompt("display_taxonomy_proposal")


__all__ = [
    "PROMPT_FILES",
    "PROMPTS_DIR",
    "get_processor_prompt",
    "load_processor_prompts",
    "_PROFILE_SYSTEM",
    "_PREFERENCE_SYSTEM",
    "_PROJECTS_SYSTEM",
    "_WORKFLOWS_SYSTEM",
    "_SKILLS_SYSTEM",
    "_EPISODE_SYSTEM",
    "_DELTA_SYSTEM",
    "_DISPLAY_TAXONOMY_PROPOSAL",
]
