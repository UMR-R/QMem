"""Built-in target platform bootstrap mappings."""

from __future__ import annotations

from typing import Any


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


__all__ = ["BUILT_IN_MAPPINGS"]
