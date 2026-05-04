"""Bootstrap prompt generator for selected target platforms."""

from __future__ import annotations

from typing import Any

from .platform_mapping import BUILT_IN_MAPPINGS


class BootstrapGenerator:
    """Generate a compact startup prompt from an L2-compatible wiki object."""

    def __init__(self, wiki: Any) -> None:
        self.wiki = wiki

    def generate(
        self,
        target_platform: str = "generic",
        max_tokens: int | None = None,
        include_projects: int = 3,
    ) -> str:
        mapping = BUILT_IN_MAPPINGS.get(target_platform) or BUILT_IN_MAPPINGS["generic"]
        effective_max = max_tokens or mapping.get("max_bootstrap_tokens", 2000)
        template: str = mapping.get("injection_template", "")

        profile_summary = self._profile_summary()
        preferences_summary = self._preferences_summary()
        projects_summary = self._projects_summary(limit=include_projects)

        if template:
            result = template.format(
                profile_summary=profile_summary,
                preferences_summary=preferences_summary,
                projects_summary=projects_summary,
            )
        else:
            result = (
                f"## Who I am\n{profile_summary}\n\n"
                f"## My preferences\n{preferences_summary}\n\n"
                f"## My active projects\n{projects_summary}"
            )

        char_limit = int(effective_max) * 4
        if len(result) > char_limit:
            result = result[:char_limit].rsplit("\n", 1)[0] + "\n[...trimmed for length]"
        return result

    def _profile_summary(self) -> str:
        profile = self.wiki.load_profile()
        if not profile:
            return "(No profile available)"
        parts = []
        if profile.name_or_alias:
            parts.append(f"Name: {profile.name_or_alias}")
        if profile.role_identity:
            parts.append(f"Role: {profile.role_identity}")
        if profile.domain_background:
            parts.append(f"Background: {', '.join(profile.domain_background)}")
        if profile.common_languages:
            parts.append(f"Languages: {', '.join(profile.common_languages)}")
        if profile.long_term_research_or_work_focus:
            foci = "; ".join(profile.long_term_research_or_work_focus)
            parts.append(f"Long-term focus: {foci}")
        return "\n".join(parts) if parts else "(No profile data)"

    def _preferences_summary(self) -> str:
        prefs = self.wiki.load_preferences()
        if not prefs:
            return "(No preferences available)"
        parts = []
        if prefs.language_preference:
            parts.append(f"Communicate in: {prefs.language_preference}")
        if prefs.primary_task_types:
            parts.append(f"Typically asks help with: {', '.join(prefs.primary_task_types)}")
        if prefs.response_granularity:
            parts.append(f"Response style: {prefs.response_granularity}")
        if prefs.style_preference:
            parts.append(f"Style: {'; '.join(prefs.style_preference)}")
        if prefs.forbidden_expressions:
            parts.append(f"Avoid: {'; '.join(prefs.forbidden_expressions)}")
        if prefs.formatting_constraints:
            parts.append(f"Formatting: {'; '.join(prefs.formatting_constraints)}")
        if prefs.terminology_preference:
            parts.append(f"Preferred terms: {'; '.join(prefs.terminology_preference)}")
        return "\n".join(parts) if parts else "(No preference data)"

    def _projects_summary(self, limit: int = 3) -> str:
        projects = [project for project in self.wiki.list_projects() if project.is_active]
        if not projects:
            return "(No active projects)"
        parts = []
        for project in projects[:limit]:
            lines = [f"**{project.project_name}**"]
            if project.project_goal:
                lines.append(f"Goal: {project.project_goal}")
            if project.current_stage:
                lines.append(f"Stage: {project.current_stage}")
            if project.next_actions:
                lines.append(f"Next: {project.next_actions[0]}")
            if project.unresolved_questions:
                lines.append(f"Open: {project.unresolved_questions[0]}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)


__all__ = ["BootstrapGenerator"]
