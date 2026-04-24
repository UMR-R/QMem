"""Memory Builder - Scenario 1: A-platform history → initial L2 MWiki.

Two-phase pipeline:
  Phase 1 — Build EpisodicMemory for every L0 conversation.
  Phase 2 — Derive persistent memory (profile, preferences, projects, workflows)
             from the aggregated episode digests.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from rich.console import Console

from ..layers.l0_raw import L0RawLayer, RawConversation
from ..layers.l1_signals import L1SignalLayer
from ..layers.l2_wiki import L2Wiki
from ..models import (
    EpisodicMemory,
    PreferenceMemory,
    ProfileMemory,
    ProjectEntry,
    ProjectMemory,
    WorkflowMemory,
)
from ..utils.llm_client import LLMClient
from .prompts import load_processor_prompts


class MemoryBuilder:
    """
    Scenario 1: Build initial L2 MWiki from A-platform history.

    Phase 1: one LLM call per conversation → EpisodicMemory with relation flags.
    Phase 2: aggregate episode digests → persistent memory objects, each
             back-linked to the episode IDs that contributed.
    """

    def __init__(self, llm: LLMClient, wiki: L2Wiki) -> None:
        self.llm = llm
        self.wiki = wiki
        self.console = Console(safe_box=True, emoji=False)
        self.prompts = load_processor_prompts()

    @staticmethod
    def _normalize_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.strip()
            return [value] if value else []
        if isinstance(value, list):
            normalized: list[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    normalized.append(text)
            return normalized
        text = str(value).strip()
        return [text] if text else []

    @classmethod
    def _coerce_model_field(cls, field_name: str, value: Any) -> Any:
        list_fields = {
            "domain_background",
            "common_languages",
            "primary_task_types",
            "long_term_research_or_work_focus",
            "style_preference",
            "terminology_preference",
            "formatting_constraints",
            "forbidden_expressions",
            "revision_preference",
        }
        if field_name in list_fields:
            return cls._normalize_str_list(value)
        return value

    @staticmethod
    def _canonical_memory_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"([a-z0-9])([\u4e00-\u9fff])", r"\1 \2", text)
        text = re.sub(r"([\u4e00-\u9fff])([a-z0-9])", r"\1 \2", text)
        text = re.sub(r"[\-_/]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _normalize_match_text(value: Any) -> str:
        return MemoryBuilder._canonical_memory_text(value)

    @classmethod
    def _memory_aliases(cls, value: Any) -> set[str]:
        base = cls._canonical_memory_text(value)
        if not base:
            return set()

        variants = {base}
        expanded = re.sub(r"(?<=[a-z])2(?=[a-z])", " to ", base)
        expanded = re.sub(r"\s+", " ", expanded).strip()
        if expanded:
            variants.add(expanded)

        aliases: set[str] = set()
        stopword_digits = {"to": "2", "for": "4"}
        for variant in variants:
            tokens = [token for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", variant) if token]
            if not tokens:
                continue
            aliases.add(" ".join(tokens))
            aliases.add("".join(tokens))
            if len(tokens) >= 2:
                acronym = "".join(stopword_digits.get(token, token[0]) for token in tokens if token)
                if acronym:
                    aliases.add(acronym)
        return {alias for alias in aliases if cls._is_meaningful_alias(alias)}

    @staticmethod
    def _is_meaningful_alias(alias: str) -> bool:
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(alias or "").lower())
        if not normalized:
            return False
        if len(normalized) >= 4:
            return True
        if any(ch.isdigit() for ch in normalized) and len(normalized) >= 3:
            return True
        if re.search(r"[\u4e00-\u9fff]", normalized) and len(normalized) >= 2:
            return True
        return False

    @classmethod
    def _memory_concept_terms(cls, value: Any) -> set[str]:
        generic_terms = {
            "project", "platform", "system", "framework", "prototype", "mvp", "repo", "repository",
            "项目", "平台", "系统", "框架", "原型", "代码库",
        }
        generic_suffixes = (
            "project", "platform", "system", "framework", "prototype",
            "项目", "平台", "系统", "框架", "原型",
        )

        terms: set[str] = set()
        for alias in cls._memory_aliases(value):
            pieces = [piece for piece in re.split(r"[^a-z0-9\u4e00-\u9fff]+", alias) if piece]
            for piece in pieces:
                normalized = piece.strip().lower()
                if not normalized or normalized in generic_terms:
                    continue
                terms.add(normalized)
                stripped = normalized
                changed = True
                while changed:
                    changed = False
                    for suffix in generic_suffixes:
                        if stripped.endswith(suffix) and len(stripped) > len(suffix) + 1:
                            stripped = stripped[:-len(suffix)]
                            stripped = stripped.strip()
                            changed = True
                if stripped and stripped not in generic_terms and stripped != normalized:
                    terms.add(stripped)
        return {
            term for term in terms
            if cls._is_meaningful_alias(term)
        }

    @classmethod
    def _infer_project_episode_ids(
        cls,
        item: dict[str, Any],
        episode_map: dict[str, list[str]],
        ep_by_id: dict[str, EpisodicMemory],
    ) -> list[str]:
        project_name = str(item.get("project_name") or "").strip()
        if not project_name:
            return []

        exact = list(dict.fromkeys(episode_map.get(project_name, [])))
        if exact:
            return exact

        project_goal = str(item.get("project_goal") or "").strip()
        current_stage = str(item.get("current_stage") or "").strip()
        relevant_entities = item.get("relevant_entities") or []
        next_actions = item.get("next_actions") or []
        unresolved = item.get("unresolved_questions") or []
        combined_text = " ".join(
            [
                project_name,
                project_goal,
                current_stage,
                *[str(entry) for entry in relevant_entities[:4]],
                *[str(entry) for entry in next_actions[:4]],
                *[str(entry) for entry in unresolved[:4]],
            ]
        )
        normalized_name = cls._normalize_match_text(project_name)
        normalized_text = cls._normalize_match_text(combined_text)
        name_aliases = cls._memory_aliases(project_name)
        text_aliases = cls._memory_aliases(combined_text)
        project_concepts = cls._memory_concept_terms(combined_text)
        match_tokens = [
            token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", " ".join(sorted(name_aliases)))
            if token and len(token) >= 2
        ]
        if not match_tokens:
            match_tokens = [
                token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", " ".join(sorted(text_aliases)))
                if token and len(token) >= 2
            ][:4]

        inferred: list[str] = []
        for episode_id, episode in ep_by_id.items():
            summary_haystack = cls._normalize_match_text(
                " ".join(
                    [
                        episode.summary,
                        " ".join(episode.key_decisions),
                        " ".join(episode.open_issues),
                        " ".join(episode.relates_to_projects),
                    ]
                )
            )
            topic_haystack = cls._normalize_match_text(
                " ".join(
                    [
                        episode.topic,
                        " ".join(episode.topics_covered),
                    ]
                )
            )
            haystack = " ".join(part for part in [summary_haystack, topic_haystack] if part).strip()
            haystack_aliases = cls._memory_aliases(haystack)
            summary_aliases = cls._memory_aliases(summary_haystack)
            summary_concepts = cls._memory_concept_terms(summary_haystack)
            if not haystack:
                continue
            if normalized_name and normalized_name in summary_haystack:
                inferred.append(episode_id)
                continue
            if any(
                alias in summary_haystack or alias in summary_aliases
                for alias in name_aliases
            ):
                inferred.append(episode_id)
                continue
            summary_overlap = sum(1 for token in match_tokens if token in summary_haystack)
            if summary_overlap >= max(2, min(3, len(match_tokens))):
                inferred.append(episode_id)
                continue
            concept_overlap = len(project_concepts & summary_concepts)
            if concept_overlap >= 2:
                inferred.append(episode_id)
                continue
            overlap = sum(1 for token in match_tokens if token in haystack)
            if overlap >= max(3, min(4, len(match_tokens))) and (summary_overlap >= 1 or concept_overlap >= 1):
                inferred.append(episode_id)
                continue
            explicit_project_intent = (
                ("项目" in summary_haystack or "platform" in summary_haystack or "平台" in summary_haystack or "system" in summary_haystack)
                and any(token in summary_haystack for token in ["想做", "希望做", "build", "develop", "构建", "搭建", "开发", "mvp"])
            )
            if explicit_project_intent and (overlap >= 1 or concept_overlap >= 1):
                inferred.append(episode_id)

        return list(dict.fromkeys(inferred))

    def build(
        self,
        conversations: list[RawConversation],
        l1_layer: L1SignalLayer,
        on_progress: Any = None,
    ) -> dict:
        """
        Full build pipeline. Returns a summary dict of what was built.
        on_progress: optional callable(step: str) for progress reporting.
        """

        def progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        results: dict[str, Any] = {}

        # Timestamp bounds across all conversations
        earliest_ts = min(
            (c.start_time for c in conversations if c.start_time is not None),
            default=None,
        )
        latest_ts = max(
            (c.end_time or c.start_time for c in conversations
             if (c.end_time or c.start_time) is not None),
            default=None,
        )

        l1_text = l1_layer.combined_text()

        # ------------------------------------------------------------------ #
        # Phase 1: Build episodic memory for every conversation               #
        # ------------------------------------------------------------------ #
        progress("Phase 1: Building episodic memory for each conversation...")
        episodes: list[EpisodicMemory] = []
        skipped_noise = 0
        for i, conv in enumerate(conversations):
            if conv.word_count() < 50:
                skipped_noise += 1
                continue
            progress(f"  Episode {i + 1}/{len(conversations)}: {conv.title or conv.conv_id}")
            ep = self._build_episode(conv)
            if ep is None:
                skipped_noise += 1  # LLM parse failure
            elif not ep.relates_to_profile and not ep.relates_to_preferences \
                    and not ep.relates_to_projects and not ep.relates_to_workflows:
                skipped_noise += 1  # no memory-relevant content
            else:
                self.wiki.save_episode(ep)
                episodes.append(ep)

        results["episodes"] = len(episodes)
        results["skipped_noise"] = skipped_noise

        # Print detected topics (first 10 unique across all episodes)
        all_topics: list[str] = []
        seen: set[str] = set()
        for ep in episodes:
            for t in ep.topics_covered:
                if t not in seen:
                    seen.add(t)
                    all_topics.append(t)
        results["topics_identified"] = len(all_topics)
        self.console.print(
            f"\nDetected topics ({len(all_topics)} unique across {len(episodes)} episodes):"
        )
        for i, t in enumerate(all_topics[:10], 1):
            self.console.print(f"  {i}. {t}")

        # ------------------------------------------------------------------ #
        # Phase 2: Derive persistent memory from episode digests              #
        # ------------------------------------------------------------------ #
        progress("Phase 2: Deriving persistent memory from episodes...")

        # Build a lookup from episode_id → episode for fast timestamp resolution
        ep_by_id: dict[str, EpisodicMemory] = {ep.episode_id: ep for ep in episodes}

        episode_digest = self._build_episode_digest(episodes, l1_text)

        # Episode IDs grouped by relation type — used to back-link persistent objects
        profile_ep_ids = [ep.episode_id for ep in episodes if ep.relates_to_profile]
        pref_ep_ids = [ep.episode_id for ep in episodes if ep.relates_to_preferences]
        project_ep_map: dict[str, list[str]] = {}
        workflow_ep_map: dict[str, list[str]] = {}
        for ep in episodes:
            for proj_name in ep.relates_to_projects:
                project_ep_map.setdefault(proj_name, []).append(ep.episode_id)
            for wf_name in ep.relates_to_workflows:
                workflow_ep_map.setdefault(wf_name, []).append(ep.episode_id)

        # Episode counts per type — used for CLI summary
        results["episodes_to_profile"] = len(profile_ep_ids)
        results["episodes_to_preferences"] = len(pref_ep_ids)
        results["episodes_to_projects"] = sum(len(v) for v in project_ep_map.values())
        results["episodes_to_workflows"] = sum(len(v) for v in workflow_ep_map.values())

        # --- Extract profile ---
        progress("Extracting profile from episodes...")
        profile_context = self._filter_digest(episodes, l1_text, "profile")
        profile_data = self.llm.extract_json(self.prompts["profile_system"], profile_context)
        profile = self._build_profile(profile_data, l1_text, earliest_ts,
                                      profile_ep_ids, ep_by_id)
        self.wiki.save_profile(profile)
        results["profile"] = bool(profile.name_or_alias or profile.role_identity)

        # --- Extract preferences ---
        progress("Extracting preferences from episodes...")
        pref_context = self._filter_digest(episodes, l1_text, "preferences")
        pref_data = self.llm.extract_json(self.prompts["preference_system"], pref_context)
        prefs = self._build_preferences(pref_data, l1_text, earliest_ts,
                                        pref_ep_ids, ep_by_id)
        if profile.primary_task_types:
            prefs.primary_task_types = list(
                dict.fromkeys(prefs.primary_task_types + profile.primary_task_types)
            )
            profile.primary_task_types = []
            self.wiki.save_profile(profile)
        self.wiki.save_preferences(prefs)
        results["preferences"] = bool(
            prefs.style_preference or prefs.language_preference or prefs.forbidden_expressions or prefs.primary_task_types
        )

        # --- Extract projects ---
        progress("Extracting projects from episodes...")
        project_context = self._filter_digest(episodes, l1_text, "projects")
        projects_data = self.llm.extract_json(self.prompts["projects_system"], project_context)
        projects = self._build_projects(projects_data, l1_text, earliest_ts,
                                        project_ep_map, ep_by_id)
        for proj in projects:
            self.wiki.save_project(proj)
        results["projects"] = len(projects)

        # --- Extract workflows ---
        progress("Extracting workflows from episodes...")
        workflow_context = self._filter_digest(episodes, l1_text, "workflows")
        workflows_data = self.llm.extract_json(self.prompts["workflows_system"], workflow_context)
        workflows = self._build_workflows(workflows_data, l1_text, earliest_ts,
                                          workflow_ep_map, ep_by_id)
        self.wiki.save_workflows(workflows)
        results["workflows"] = len(workflows)

        # --- Rebuild index ---
        progress("Rebuilding index...")
        index = self.wiki.rebuild_index()
        results["index"] = index

        return results

    # ------------------------------------------------------------------ #
    # Phase 1 helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_episode(self, conv: RawConversation) -> EpisodicMemory | None:
        text = conv.full_text()[:4000]
        user_prompt = (
            f"Conversation title: {conv.title or conv.conv_id}\n"
            f"Platform: {conv.platform}\n"
            f"Message count: {len(conv.messages)}\n\n"
            f"{text}"
        )
        data = self.llm.extract_json(self.prompts["episode_system"], user_prompt)
        if not data or not isinstance(data, dict):
            return None
        ep = EpisodicMemory(
            episode_id=str(uuid.uuid4())[:8],
            conv_id=conv.conv_id,
            platform=conv.platform,
            topic=data.get("topic") or conv.title or conv.conv_id,
            topics_covered=data.get("topics_covered") or [],
            summary=data.get("summary") or "",
            key_decisions=data.get("key_decisions") or [],
            open_issues=data.get("open_issues") or [],
            turn_refs=[turn.turn_id for turn in (conv.turns or []) if getattr(turn, "turn_id", "")],
            relates_to_profile=bool(data.get("relates_to_profile")),
            relates_to_preferences=bool(data.get("relates_to_preferences")),
            relates_to_projects=data.get("relates_to_projects") or [],
            relates_to_workflows=data.get("relates_to_workflows") or [],
            time_range_start=conv.start_time,
            time_range_end=conv.end_time,
        )
        if conv.start_time is not None:
            ep.created_at = conv.start_time
        if conv.end_time is not None:
            ep.updated_at = conv.end_time
        elif conv.start_time is not None:
            ep.updated_at = conv.start_time
        ep.add_evidence("l0_raw", conv.conv_id, conv.full_text()[:100])
        return ep

    # ------------------------------------------------------------------ #
    # Phase 2 helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_episode_digest(
        self, episodes: list[EpisodicMemory], l1_text: str, verbose: bool = False
    ) -> str:
        """Compact text summary of all episodes for LLM context."""
        lines: list[str] = []
        if l1_text:
            lines.append(f"PLATFORM MEMORY SIGNALS:\n{l1_text[:2000]}\n")
        lines.append(f"TOTAL EPISODES: {len(episodes)}\n")
        for ep in episodes:
            ts = ep.time_range_start.strftime("%Y-%m-%d") if ep.time_range_start else "unknown date"
            entry = (
                f"[{ep.episode_id}] {ts} — {ep.topic}\n"
                f"  Topics: {', '.join(ep.topics_covered)}\n"
                f"  Summary: {ep.summary}"
            )
            if verbose:
                if ep.key_decisions:
                    entry += f"\n  Decisions: {'; '.join(ep.key_decisions[:3])}"
                if ep.open_issues:
                    entry += f"\n  Open issues: {'; '.join(ep.open_issues[:3])}"
                entry += (
                    f"\n  Relates to: profile={ep.relates_to_profile}, "
                    f"prefs={ep.relates_to_preferences}, "
                    f"projects={ep.relates_to_projects}, "
                    f"workflows={ep.relates_to_workflows}"
                )
            lines.append(entry)
        return "\n".join(lines)

    def _filter_digest(
        self, episodes: list[EpisodicMemory], l1_text: str, filter_type: str
    ) -> str:
        """Build a digest filtered to episodes relevant to a specific memory type."""
        if filter_type == "profile":
            relevant = [ep for ep in episodes if ep.relates_to_profile] or episodes
            return self._build_episode_digest(relevant[:40], l1_text)[:6000]
        elif filter_type == "preferences":
            relevant = [ep for ep in episodes if ep.relates_to_preferences] or episodes
            return self._build_episode_digest(relevant[:40], l1_text)[:6000]
        elif filter_type == "projects":
            # Prefer episodes that already point to a project. Only add a small
            # amount of unflagged context as fallback, otherwise literature surveys
            # and comparison tables can inflate every referenced paper/algorithm
            # into a fake project.
            flagged = [ep for ep in episodes if ep.relates_to_projects]
            if flagged:
                backfill = max(0, min(8, 12 - len(flagged)))
                unflagged = [ep for ep in episodes if not ep.relates_to_projects][:backfill]
                relevant = (flagged + unflagged)[:40]
            else:
                relevant = episodes[:15]
            return self._build_episode_digest(relevant, l1_text, verbose=True)[:7000]
        elif filter_type == "workflows":
            relevant = [ep for ep in episodes if ep.relates_to_workflows] or episodes
            return self._build_episode_digest(relevant[:40], l1_text, verbose=True)[:6000]
        else:
            return self._build_episode_digest(episodes[:40], l1_text)[:6000]

    # ------------------------------------------------------------------ #
    # Timestamp helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ep_timestamps(
        ep_ids: list[str],
        ep_by_id: dict[str, EpisodicMemory],
        global_earliest: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Return (earliest, latest) timestamps from the given episode IDs.
        Falls back to global_earliest for created_at when no episodes are found.
        """
        times: list[datetime] = []
        for eid in ep_ids:
            ep = ep_by_id.get(eid)
            if ep:
                if ep.time_range_start:
                    times.append(ep.time_range_start)
                if ep.time_range_end:
                    times.append(ep.time_range_end)
        if times:
            return min(times), max(times)
        return global_earliest, None

    @staticmethod
    def _best_episode_ts(
        entry_text: str,
        ep_ids: list[str],
        ep_by_id: dict[str, EpisodicMemory],
        min_score: float = 0.25,
    ) -> datetime | None:
        """
        Return the time_range_end of the episode whose key_decisions / open_issues /
        topics_covered best match entry_text by word-set (Jaccard) overlap.
        Returns None if the best score is below min_score.
        """
        entry_words = set(re.sub(r"[^\w\s]", " ", entry_text.lower()).split())
        if not entry_words:
            return None
        best_ts: datetime | None = None
        best_score = 0.0
        for eid in ep_ids:
            ep = ep_by_id.get(eid)
            if not ep:
                continue
            ts = ep.time_range_end or ep.time_range_start
            if ts is None:
                continue
            candidates = ep.key_decisions + ep.open_issues + ep.topics_covered
            for candidate in candidates:
                cand_words = set(re.sub(r"[^\w\s]", " ", candidate.lower()).split())
                if not cand_words:
                    continue
                union = entry_words | cand_words
                score = len(entry_words & cand_words) / len(union)
                if score > best_score:
                    best_score = score
                    best_ts = ts
        return best_ts if best_score >= min_score else None

    # ------------------------------------------------------------------ #
    # Phase 2 build helpers                                                #
    # ------------------------------------------------------------------ #

    def _build_profile(
        self,
        data: dict,
        l1_text: str,
        global_earliest: datetime | None,
        episode_ids: list[str],
        ep_by_id: dict[str, EpisodicMemory],
    ) -> ProfileMemory:
        profile = self.wiki.load_profile() or ProfileMemory()
        if isinstance(data, dict):
            for field in ProfileMemory.model_fields:
                if field in data and data[field]:
                    setattr(profile, field, self._coerce_model_field(field, data[field]))
        if l1_text:
            profile.add_evidence("l1_signal", "platform_export", l1_text[:100])
        else:
            profile.add_evidence("l0_raw", "episode_digest", "derived from episodic memory")
        profile.source_episode_ids = list(dict.fromkeys(
            profile.source_episode_ids + episode_ids
        ))
        created, updated = self._ep_timestamps(episode_ids, ep_by_id, global_earliest)
        if created is not None:
            profile.created_at = created
        if updated is not None:
            profile.updated_at = updated
        return profile

    def _build_preferences(
        self,
        data: dict,
        l1_text: str,
        global_earliest: datetime | None,
        episode_ids: list[str],
        ep_by_id: dict[str, EpisodicMemory],
    ) -> PreferenceMemory:
        prefs = self.wiki.load_preferences() or PreferenceMemory()
        if isinstance(data, dict):
            for field in PreferenceMemory.model_fields:
                if field in data and data[field]:
                    setattr(prefs, field, self._coerce_model_field(field, data[field]))
        if l1_text:
            prefs.add_evidence("l1_signal", "platform_export", l1_text[:100])
        else:
            prefs.add_evidence("l0_raw", "episode_digest", "derived from episodic memory")
        prefs.source_episode_ids = list(dict.fromkeys(
            prefs.source_episode_ids + episode_ids
        ))
        created, updated = self._ep_timestamps(episode_ids, ep_by_id, global_earliest)
        if created is not None:
            prefs.created_at = created
        if updated is not None:
            prefs.updated_at = updated
        return prefs

    def _build_projects(
        self,
        data: Any,
        l1_text: str,
        global_earliest: datetime | None,
        episode_map: dict[str, list[str]],
        ep_by_id: dict[str, EpisodicMemory],
    ) -> list[ProjectMemory]:
        if not isinstance(data, list):
            return []
        source = "l1_signal" if l1_text else "l0_raw"
        source_id = "platform_export" if l1_text else "episode_digest"
        entry_fields = {
            "finished_decisions", "unresolved_questions", "relevant_entities",
            "important_constraints", "next_actions",
        }
        projects = []
        for item in data:
            if not isinstance(item, dict) or not item.get("project_name"):
                continue
            existing = self.wiki.load_project(item["project_name"])
            proj = existing or ProjectMemory(project_name=item["project_name"])
            ep_ids = self._infer_project_episode_ids(item, episode_map, ep_by_id)
            created, updated = self._ep_timestamps(ep_ids, ep_by_id, global_earliest)
            for field in ProjectMemory.model_fields:
                if field == "project_name":
                    continue
                if field not in item or item[field] is None:
                    continue
                if field in entry_fields:
                    raw = item[field]
                    if isinstance(raw, list):
                        existing_texts = {e.text for e in getattr(proj, field)}
                        new_entries = []
                        for s in raw:
                            if not isinstance(s, str) or s in existing_texts:
                                continue
                            ts = (
                                self._best_episode_ts(s, ep_ids, ep_by_id)
                                or updated
                            )
                            new_entries.append(ProjectEntry(text=s, timestamp=ts))
                        setattr(proj, field, getattr(proj, field) + new_entries)
                else:
                    setattr(proj, field, item[field])
            proj.add_evidence(source, source_id, "")
            proj.source_episode_ids = list(dict.fromkeys(
                proj.source_episode_ids + ep_ids
            ))
            if existing is None and created is not None:
                proj.created_at = created
            if updated is not None:
                proj.updated_at = updated
            projects.append(proj)
        return projects

    def _build_workflows(
        self,
        data: Any,
        l1_text: str,
        global_earliest: datetime | None,
        episode_map: dict[str, list[str]],
        ep_by_id: dict[str, EpisodicMemory],
    ) -> list[WorkflowMemory]:
        if not isinstance(data, list):
            return []
        source = "l1_signal" if l1_text else "l0_raw"
        source_id = "platform_export" if l1_text else "episode_digest"
        existing = {w.workflow_name: w for w in self.wiki.load_workflows()}
        workflows = list(existing.values())
        for item in data:
            if not isinstance(item, dict) or not item.get("workflow_name"):
                continue
            name = item["workflow_name"]
            ep_ids = episode_map.get(name, [])
            created, updated = self._ep_timestamps(ep_ids, ep_by_id, global_earliest)
            if name in existing:
                wf = existing[name]
                wf.occurrence_count += 1
            else:
                wf = WorkflowMemory(workflow_name=name)
                if created is not None:
                    wf.created_at = created
            if updated is not None:
                wf.updated_at = updated
            for field in WorkflowMemory.model_fields:
                if field in ("workflow_name", "occurrence_count"):
                    continue
                if field in item and item[field]:
                    setattr(wf, field, item[field])
            wf.add_evidence(source, source_id, "")
            wf.source_episode_ids = list(dict.fromkeys(
                wf.source_episode_ids + ep_ids
            ))
            if name not in existing:
                workflows.append(wf)
        return workflows
