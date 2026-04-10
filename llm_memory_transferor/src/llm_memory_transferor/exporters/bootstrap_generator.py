"""Bootstrap prompt generator - creates minimal platform startup prompts."""

from __future__ import annotations

from ..layers.l2_wiki import L2Wiki
from ..models.platform_mapping import BUILT_IN_MAPPINGS


class BootstrapGenerator:
    """
    Generates minimal bootstrap prompts for target platforms.
    The bootstrap is what gets injected into a new platform session
    so the user feels immediately understood.
    """

    def __init__(self, wiki: L2Wiki) -> None:
        self.wiki = wiki

    def generate(
        self,
        target_platform: str = "generic",
        max_tokens: int | None = None,
        include_projects: int = 3,
    ) -> str:
        """
        Generate a minimal bootstrap prompt for the target platform.
        Returns a string ready to paste as system prompt / custom instructions.
        """
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

        # Trim to token budget (rough: 1 token ≈ 4 chars)
        char_limit = effective_max * 4
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
        if profile.primary_task_types:
            parts.append(f"Typically asks help with: {', '.join(profile.primary_task_types)}")
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
        projects = [p for p in self.wiki.list_projects() if p.is_active]
        if not projects:
            return "(No active projects)"
        parts = []
        for proj in projects[:limit]:
            lines = [f"**{proj.project_name}**"]
            if proj.project_goal:
                lines.append(f"Goal: {proj.project_goal}")
            if proj.current_stage:
                lines.append(f"Stage: {proj.current_stage}")
            if proj.next_actions:
                lines.append(f"Next: {proj.next_actions[0]}")
            if proj.unresolved_questions:
                lines.append(f"Open: {proj.unresolved_questions[0]}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)
