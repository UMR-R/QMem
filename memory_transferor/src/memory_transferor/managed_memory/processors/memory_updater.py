"""Memory Updater - Scenario 2: incremental update from new conversations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from memory_transferor.managed_memory.l2_wiki import L2Wiki
from memory_transferor.managed_memory.models import (
    EpisodeConnection,
    EpisodicMemory,
    PreferenceMemory,
    ProfileMemory,
    ProjectEntry,
    ProjectMemory,
    WorkflowMemory,
)
from memory_transferor.memory_policy import ConflictResolution, L3Schema, UpgradeDecision
from memory_transferor.platform_memory import L1SignalLayer
from memory_transferor.prompt_loader import load_prompts as load_processor_prompts
from memory_transferor.runtime import LLMClient


class MemoryUpdater:
    """
    Scenario 2: Incremental update for ongoing usage.
    Only processes what is affected by the current session.
    """

    def __init__(self, llm: LLMClient, wiki: L2Wiki, schema: L3Schema) -> None:
        self.llm = llm
        self.wiki = wiki
        self.schema = schema
        self.prompts = load_processor_prompts()

    @staticmethod
    def _detect_primary_language(text: str) -> str:
        cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        ascii_alpha_count = sum(1 for ch in text if ("a" <= ch.lower() <= "z"))
        if cjk_count >= max(2, ascii_alpha_count // 3):
            return "zh"
        if ascii_alpha_count:
            return "en"
        return ""

    @staticmethod
    def _language_policy_context(language: str) -> str:
        if language == "zh":
            return (
                "TARGET DISPLAY LANGUAGE: zh\n"
                "Write all human-facing natural-language memory values in Chinese, "
                "while preserving necessary proper nouns, model names, paper titles, "
                "dataset names, code names, and technical terms in their original form.\n"
                "Ordinary role labels, job titles, task labels, and UI-facing summaries "
                "are not proper nouns; localize them into natural Chinese.\n"
                "Do not generate English role labels or English alternatives unless the exact English phrase "
                "appears in user-authored evidence as an official title or preferred wording.\n"
            )
        if language == "en":
            return (
                "TARGET DISPLAY LANGUAGE: en\n"
                "Write all human-facing natural-language memory values in English, "
                "while preserving necessary proper nouns and technical terms in their original form.\n"
            )
        return (
            "TARGET DISPLAY LANGUAGE: infer from the new conversation\n"
            "Write human-facing memory values in the dominant language of the new conversation, "
            "while preserving necessary proper nouns and technical terms in their original form.\n"
            "Ordinary role labels, job titles, task labels, and UI-facing summaries should follow that language. "
            "Do not invent English labels when the evidence is not English.\n"
        )

    @classmethod
    def _episode_display_payload(
        cls,
        ep_data: dict[str, Any],
        primary_language: str,
        title: str,
        summary: str,
    ) -> dict[str, dict[str, str]]:
        raw_display = ep_data.get("display") if isinstance(ep_data.get("display"), dict) else {}
        display: dict[str, dict[str, str]] = {}
        for lang in ["zh", "en"]:
            value = raw_display.get(lang) if isinstance(raw_display, dict) else None
            if isinstance(value, dict):
                display[lang] = {
                    "title": str(value.get("title") or "").strip(),
                    "summary": str(value.get("summary") or "").strip(),
                }
        lang = primary_language if primary_language in {"zh", "en"} else cls._detect_primary_language(
            f"{title}\n{summary}"
        )
        if lang in {"zh", "en"}:
            current = display.setdefault(lang, {"title": "", "summary": ""})
            current["title"] = current["title"] or title
            current["summary"] = current["summary"] or summary
        return display

    @staticmethod
    def _turn_index(ep: EpisodicMemory) -> int:
        if not ep.turn_refs:
            return 10**9
        try:
            return int(str(ep.turn_refs[0]).rsplit(":turn:", 1)[1])
        except (IndexError, ValueError):
            return 10**9

    @staticmethod
    def _add_episode_connection(
        ep: EpisodicMemory,
        target_id: str,
        relation: str,
        key: str = "",
        reason: str = "",
    ) -> bool:
        if not target_id or target_id == ep.episode_id:
            return False
        for existing in ep.connections:
            if (
                existing.episode_id == target_id
                and existing.relation == relation
                and existing.key == key
            ):
                return False
        ep.connections.append(
            EpisodeConnection(
                episode_id=target_id,
                relation=relation,
                key=key,
                reason=reason,
            )
        )
        return True

    def _connect_episode_group(
        self,
        ep_by_id: dict[str, EpisodicMemory],
        episode_ids: list[str],
        relation: str,
        key: str = "",
        reason: str = "",
    ) -> set[str]:
        changed: set[str] = set()
        clean_ids = [eid for eid in dict.fromkeys(episode_ids) if eid in ep_by_id]
        if len(clean_ids) < 2:
            return changed
        for eid in clean_ids:
            for other_id in clean_ids:
                if self._add_episode_connection(ep_by_id[eid], other_id, relation, key, reason):
                    changed.add(eid)
        return changed

    def _refresh_incremental_episode_connections(self, episode_id: str) -> None:
        episodes = self.wiki.list_episodes()
        ep_by_id = {ep.episode_id: ep for ep in episodes}
        episode = ep_by_id.get(episode_id)
        if not episode:
            return

        changed: set[str] = set()
        same_conv = sorted(
            [ep for ep in episodes if ep.conv_id and ep.conv_id == episode.conv_id],
            key=self._turn_index,
        )
        for index, ep in enumerate(same_conv):
            if ep.episode_id != episode_id:
                continue
            for neighbor in (same_conv[index - 1:index] + same_conv[index + 1:index + 2]):
                if self._add_episode_connection(
                    ep,
                    neighbor.episode_id,
                    "conversation_context",
                    ep.conv_id,
                    "adjacent turn in the same raw conversation",
                ):
                    changed.add(ep.episode_id)
                if self._add_episode_connection(
                    neighbor,
                    ep.episode_id,
                    "conversation_context",
                    ep.conv_id,
                    "adjacent turn in the same raw conversation",
                ):
                    changed.add(neighbor.episode_id)

        profile = self.wiki.load_profile()
        if profile and episode_id in profile.source_episode_ids:
            changed.update(self._connect_episode_group(
                ep_by_id,
                profile.source_episode_ids,
                "profile",
                reason="shared profile evidence",
            ))

        prefs = self.wiki.load_preferences()
        if prefs and episode_id in prefs.source_episode_ids:
            changed.update(self._connect_episode_group(
                ep_by_id,
                prefs.source_episode_ids,
                "preferences",
                reason="shared preference evidence",
            ))

        for project in self.wiki.list_projects():
            if episode_id in project.source_episode_ids:
                changed.update(self._connect_episode_group(
                    ep_by_id,
                    project.source_episode_ids,
                    "project",
                    project.project_name,
                    "same persistent project",
                ))

        for workflow in self.wiki.load_workflows():
            if episode_id in workflow.source_episode_ids:
                changed.update(self._connect_episode_group(
                    ep_by_id,
                    workflow.source_episode_ids,
                    "workflow",
                    workflow.workflow_name,
                    "same persistent workflow",
                ))

        for changed_id in changed:
            self.wiki.save_episode(ep_by_id[changed_id])

    def update(
        self,
        new_conversation_text: str,
        l1_layer: L1SignalLayer | None = None,
        platform: str = "unknown",
        conv_id: str = "",
        turn_refs: list[str] | None = None,
        on_progress: Any = None,
        conversation_end_time: datetime | None = None,
    ) -> dict:
        def progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        # Build current state summary for context
        progress("Loading current memory state...")
        current_state = self._summarize_current_state()
        target_language = self._detect_primary_language(new_conversation_text)
        language_context = self._language_policy_context(target_language)

        # Get L1 signals text
        l1_text = l1_layer.combined_text() if l1_layer else ""

        # --- Ask LLM what changed ---
        progress("Analyzing conversation for memory deltas...")
        prompt = (
            f"CURRENT MEMORY STATE:\n{current_state}\n\n"
            f"{language_context}\n"
            f"NEW CONVERSATION:\n{new_conversation_text[:4000]}"
            + (f"\n\nPLATFORM SIGNALS:\n{l1_text[:1000]}" if l1_text else "")
        )
        delta = self.llm.extract_json(self.prompts["delta_system"], prompt)

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
            if target_language:
                profile.primary_language = target_language
            for field, value in profile_updates.items():
                if not value or field not in ProfileMemory.model_fields:
                    continue
                old = getattr(profile, field, None)
                if old != value:
                    decision = self.schema.should_upgrade_profile_field(field)
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
            if target_language:
                prefs.primary_language = target_language
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
            if pref_updates.get("add_primary_task_types"):
                prefs.primary_task_types = list(
                    set(prefs.primary_task_types + pref_updates["add_primary_task_types"])
                )
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
            if target_language:
                proj.primary_language = target_language
            now = conversation_end_time or datetime.now(timezone.utc)
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
                    if target_language:
                        wf.primary_language = target_language
                    existing[name] = wf
                    changed = True
                if name in existing and target_language:
                    existing[name].primary_language = target_language
            if changed:
                progress("Updating workflows...")
                self.wiki.save_workflows(list(existing.values()))
                results["workflows_updated"] = True

        # --- Create episode ---
        ep_data = delta.get("episode") or {}
        new_episode_id: str | None = None
        if ep_data and ep_data.get("topic"):
            progress("Creating episode record...")
            episode_language = str(ep_data.get("primary_language") or "").strip().lower()
            if episode_language not in {"zh", "en"}:
                episode_language = target_language
            episode_title = ep_data.get("topic") or ep_data.get("title") or ""
            episode_summary = ep_data.get("summary") or ""
            ep = EpisodicMemory(
                episode_id=str(uuid.uuid4())[:8],
                conv_id=conv_id,
                platform=platform,
                topic=episode_title,
                primary_language=episode_language,
                display=self._episode_display_payload(ep_data, episode_language, episode_title, episode_summary),
                topics_covered=ep_data.get("topics_covered") or [],
                summary=episode_summary,
                key_decisions=ep_data.get("key_decisions") or [],
                open_issues=ep_data.get("open_issues") or [],
                granularity="turn" if turn_refs else "conversation",
                turn_refs=[str(turn_ref).strip() for turn_ref in (turn_refs or []) if str(turn_ref).strip()],
                relates_to_profile=bool(ep_data.get("relates_to_profile")),
                relates_to_preferences=bool(ep_data.get("relates_to_preferences")),
                relates_to_projects=ep_data.get("relates_to_projects") or [],
                relates_to_workflows=ep_data.get("relates_to_workflows") or [],
                related_project=str(ep_data.get("related_project") or "").strip(),
                time_range_start=conversation_end_time,
                time_range_end=conversation_end_time,
            )
            if conversation_end_time is not None:
                ep.created_at = conversation_end_time
                ep.updated_at = conversation_end_time
            if ep.related_project and ep.related_project not in ep.relates_to_projects:
                ep.relates_to_projects.append(ep.related_project)
            ep.add_evidence("chat_history", platform, ep.summary[:240] or ep.topic or new_conversation_text[:120])
            self.wiki.save_episode(ep)
            new_episode_id = ep.episode_id
            results["episode_created"] = ep.episode_id

        # Back-link episode to affected persistent memory objects
        if new_episode_id:
            new_turn_refs = [str(ref).strip() for ref in (turn_refs or []) if str(ref).strip()]
            if profile_updates:
                profile = self.wiki.load_profile()
                if profile:
                    if new_episode_id not in profile.source_episode_ids:
                        profile.source_episode_ids.append(new_episode_id)
                    profile.source_turn_refs = list(dict.fromkeys(profile.source_turn_refs + new_turn_refs))
                    self.wiki.save_profile(profile)
            if any(pref_updates.values()):
                prefs = self.wiki.load_preferences()
                if prefs:
                    if new_episode_id not in prefs.source_episode_ids:
                        prefs.source_episode_ids.append(new_episode_id)
                    prefs.source_turn_refs = list(dict.fromkeys(prefs.source_turn_refs + new_turn_refs))
                    self.wiki.save_preferences(prefs)
            for name in updated_projects:
                proj = self.wiki.load_project(name)
                if proj:
                    if new_episode_id not in proj.source_episode_ids:
                        proj.source_episode_ids.append(new_episode_id)
                    proj.source_turn_refs = list(dict.fromkeys(proj.source_turn_refs + new_turn_refs))
                    self.wiki.save_project(proj)
            if workflow_updates:
                workflows = self.wiki.load_workflows()
                changed = False
                touched_names = {
                    str(item.get("workflow_name") or "").strip()
                    for item in workflow_updates
                    if isinstance(item, dict) and str(item.get("workflow_name") or "").strip()
                }
                for workflow in workflows:
                    if workflow.workflow_name in touched_names:
                        if new_episode_id not in workflow.source_episode_ids:
                            workflow.source_episode_ids.append(new_episode_id)
                        workflow.source_turn_refs = list(dict.fromkeys(workflow.source_turn_refs + new_turn_refs))
                        changed = True
                if changed:
                    self.wiki.save_workflows(workflows)

            self._refresh_incremental_episode_connections(new_episode_id)

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
