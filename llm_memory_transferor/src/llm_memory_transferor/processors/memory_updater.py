"""Memory Updater - Scenario 2: incremental update from new conversations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..layers.l1_signals import L1SignalLayer
from ..layers.l2_wiki import L2Wiki
from ..layers.l3_schema import ConflictResolution, L3Schema
from ..models import (
    EpisodicMemory,
    PreferenceMemory,
    ProfileMemory,
    ProjectEntry,
    ProjectMemory,
    WorkflowMemory,
)
from ..utils.llm_client import LLMClient
from .prompts import _DELTA_SYSTEM


class MemoryUpdater:
    """
    Scenario 2: Incremental update for ongoing usage.
    Only processes what is affected by the current session.
    """

    def __init__(self, llm: LLMClient, wiki: L2Wiki, schema: L3Schema) -> None:
        self.llm = llm
        self.wiki = wiki
        self.schema = schema

    def update(
        self,
        new_conversation_text: str,
        l1_layer: L1SignalLayer | None = None,
        platform: str = "unknown",
        on_progress: Any = None,
    ) -> dict:
        def progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        # Build current state summary for context
        progress("Loading current memory state...")
        current_state = self._summarize_current_state()

        # Get L1 signals text
        l1_text = l1_layer.combined_text() if l1_layer else ""

        # --- Ask LLM what changed ---
        progress("Analyzing conversation for memory deltas...")
        prompt = (
            f"CURRENT MEMORY STATE:\n{current_state}\n\n"
            f"NEW CONVERSATION:\n{new_conversation_text[:4000]}"
            + (f"\n\nPLATFORM SIGNALS:\n{l1_text[:1000]}" if l1_text else "")
        )
        delta = self.llm.extract_json(_DELTA_SYSTEM, prompt)

        if not isinstance(delta, dict):
            return {"status": "no_changes"}

        if delta.get("is_noise"):
            progress("Conversation classified as noise - no memory updates.")
            return {"status": "noise"}

        results: dict[str, Any] = {}

        # --- Update profile ---
        profile_updates = delta.get("profile_updates") or {}
        if profile_updates:
            progress("Updating profile...")
            profile = self.wiki.load_profile() or ProfileMemory()
            for field, value in profile_updates.items():
                if not value or field not in ProfileMemory.model_fields:
                    continue
                old = getattr(profile, field, None)
                if old != value:
                    decision = self.schema.should_upgrade_profile_field(field)
                    from ..layers.l3_schema import UpgradeDecision
                    if decision == UpgradeDecision.USER_CONFIRM:
                        profile.record_conflict(field, old, value, "new_conversation")
                    else:
                        setattr(profile, field, value)
            profile.add_evidence("chat_history", platform, new_conversation_text[:80])
            self.wiki.save_profile(profile)
            results["profile_updated"] = True

        # --- Update preferences ---
        pref_updates = delta.get("preference_updates") or {}
        if any(pref_updates.values()):
            progress("Updating preferences...")
            prefs = self.wiki.load_preferences() or PreferenceMemory()
            if pref_updates.get("add_style"):
                prefs.style_preference = list(
                    set(prefs.style_preference + pref_updates["add_style"])
                )
            if pref_updates.get("add_forbidden"):
                prefs.forbidden_expressions = list(
                    set(prefs.forbidden_expressions + pref_updates["add_forbidden"])
                )
            if pref_updates.get("update_language"):
                prefs.language_preference = pref_updates["update_language"]
            if pref_updates.get("update_granularity"):
                prefs.response_granularity = pref_updates["update_granularity"]
            prefs.add_evidence("chat_history", platform, new_conversation_text[:80])
            self.wiki.save_preferences(prefs)
            results["preferences_updated"] = True

        # --- Update projects ---
        project_updates = delta.get("project_updates") or []
        updated_projects = []
        for pu in project_updates:
            if not isinstance(pu, dict) or not pu.get("project_name"):
                continue
            name = pu["project_name"]
            action = pu.get("action", "update")
            proj = self.wiki.load_project(name)
            if proj is None:
                if action == "create":
                    proj = ProjectMemory(project_name=name)
                else:
                    continue
            now = datetime.now(timezone.utc)
            if pu.get("stage_update"):
                proj.current_stage = pu["stage_update"]
            if pu.get("new_decisions"):
                existing_texts = {e.text for e in proj.finished_decisions}
                proj.finished_decisions += [
                    ProjectEntry(text=s, timestamp=now)
                    for s in pu["new_decisions"]
                    if s not in existing_texts
                ]
            if pu.get("new_questions"):
                existing_texts = {e.text for e in proj.unresolved_questions}
                proj.unresolved_questions += [
                    ProjectEntry(text=s, timestamp=now)
                    for s in pu["new_questions"]
                    if s not in existing_texts
                ]
            if pu.get("resolved_questions"):
                resolved = set(pu["resolved_questions"])
                proj.unresolved_questions = [
                    e for e in proj.unresolved_questions if e.text not in resolved
                ]
            if pu.get("new_next_actions"):
                proj.next_actions = [
                    ProjectEntry(text=s, timestamp=now)
                    for s in pu["new_next_actions"]
                ]
            proj.add_evidence("chat_history", platform, new_conversation_text[:80])
            self.wiki.save_project(proj)
            updated_projects.append(name)
        results["projects_updated"] = updated_projects

        # --- Update workflows ---
        workflow_updates = delta.get("workflow_updates") or []
        if workflow_updates:
            existing = {w.workflow_name: w for w in self.wiki.load_workflows()}
            changed = False
            for wu in workflow_updates:
                if not isinstance(wu, dict) or not wu.get("workflow_name"):
                    continue
                name = wu["workflow_name"]
                action = wu.get("action", "confirm")
                if name in existing:
                    wf = existing[name]
                    wf.occurrence_count += 1
                    if wu.get("steps_update"):
                        wf.typical_steps = wu["steps_update"]
                    changed = True
                elif action == "create":
                    wf = WorkflowMemory(
                        workflow_name=name,
                        typical_steps=wu.get("steps_update") or [],
                    )
                    existing[name] = wf
                    changed = True
            if changed:
                progress("Updating workflows...")
                self.wiki.save_workflows(list(existing.values()))
                results["workflows_updated"] = True

        # --- Create episode ---
        ep_data = delta.get("episode") or {}
        new_episode_id: str | None = None
        if ep_data and ep_data.get("topic"):
            progress("Creating episode record...")
            ep = EpisodicMemory(
                episode_id=str(uuid.uuid4())[:8],
                platform=platform,
                topic=ep_data.get("topic") or "",
                topics_covered=ep_data.get("topics_covered") or [],
                summary=ep_data.get("summary") or "",
                key_decisions=ep_data.get("key_decisions") or [],
                open_issues=ep_data.get("open_issues") or [],
                relates_to_profile=bool(ep_data.get("relates_to_profile")),
                relates_to_preferences=bool(ep_data.get("relates_to_preferences")),
                relates_to_projects=ep_data.get("relates_to_projects") or [],
                relates_to_workflows=ep_data.get("relates_to_workflows") or [],
            )
            ep.add_evidence("chat_history", platform, new_conversation_text[:80])
            self.wiki.save_episode(ep)
            new_episode_id = ep.episode_id
            results["episode_created"] = ep.episode_id

        # Back-link episode to affected persistent memory objects
        if new_episode_id:
            if profile_updates:
                profile = self.wiki.load_profile()
                if profile and new_episode_id not in profile.source_episode_ids:
                    profile.source_episode_ids.append(new_episode_id)
                    self.wiki.save_profile(profile)
            if any(pref_updates.values()):
                prefs = self.wiki.load_preferences()
                if prefs and new_episode_id not in prefs.source_episode_ids:
                    prefs.source_episode_ids.append(new_episode_id)
                    self.wiki.save_preferences(prefs)
            for name in updated_projects:
                proj = self.wiki.load_project(name)
                if proj and new_episode_id not in proj.source_episode_ids:
                    proj.source_episode_ids.append(new_episode_id)
                    self.wiki.save_project(proj)

        # --- Health check: detect L1 vs L2 divergence ---
        if l1_layer:
            self._check_divergence(l1_layer)

        self.wiki.rebuild_index()
        results["status"] = "updated"
        return results

    def _summarize_current_state(self) -> str:
        parts = []
        profile = self.wiki.load_profile()
        if profile:
            parts.append(profile.to_markdown())
        prefs = self.wiki.load_preferences()
        if prefs:
            parts.append(prefs.to_markdown())
        for proj in self.wiki.list_projects():
            if proj.is_active:
                parts.append(proj.to_markdown())
        return "\n\n---\n\n".join(parts)[:4000]

    def _check_divergence(self, l1_layer: L1SignalLayer) -> None:
        """Log if L1 signals diverge from L2 state (health check)."""
        l1_text = l1_layer.combined_text()
        profile = self.wiki.load_profile()
        if not profile or not l1_text:
            return
        # Simple heuristic: if name is in L2 but not mentioned in L1, flag it
        if (
            profile.name_or_alias
            and profile.name_or_alias not in l1_text
        ):
            self.wiki._log_change("health_check", "divergence_warning", "profile.name_or_alias")
