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
from memory_transferor.memory_models import RawConversation
from memory_transferor.memory_store import L0RawLayer
from memory_transferor.platform_memory import L1SignalLayer
from memory_transferor.prompt_loader import load_prompts as load_processor_prompts
from memory_transferor.runtime import LLMClient


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

        inferred: list[str] = list(exact)
        for episode_id, episode in ep_by_id.items():
            if episode_id in inferred:
                continue
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

    @classmethod
    def _episode_has_project_intent(cls, ep: EpisodicMemory) -> bool:
        text = cls._normalize_match_text(
            " ".join(
                [
                    ep.topic,
                    ep.summary,
                    " ".join(ep.key_decisions),
                    " ".join(ep.open_issues),
                    " ".join(ep.topics_covered),
                ]
            )
        )
        if not text:
            return False
        object_markers = {
            "project", "platform", "system", "framework", "prototype", "mvp",
            "项目", "平台", "系统", "框架", "原型",
        }
        action_markers = {
            "build", "develop", "implement", "launch", "submit", "design", "plan",
            "构建", "搭建", "开发", "实现", "设计", "规划", "推进", "投稿",
        }
        return any(marker in text for marker in object_markers) and any(
            marker in text for marker in action_markers
        )

    @classmethod
    def _episode_has_persistent_topic_signal(cls, ep: EpisodicMemory) -> bool:
        text = cls._normalize_match_text(
            " ".join(
                [
                    ep.topic,
                    ep.summary,
                    " ".join(ep.key_decisions),
                    " ".join(ep.open_issues),
                    " ".join(ep.topics_covered),
                ]
            )
        )
        if not text:
            return False
        user_markers = {"用户", "user"}
        durable_markers = {
            "prefers", "preference", "likes", "tends", "chooses", "choice", "criterion",
            "偏好", "喜欢", "倾向", "关注", "选择", "标准", "首选", "更适合",
        }
        return any(marker in text for marker in user_markers) and any(
            marker in text for marker in durable_markers
        )

    @classmethod
    def _episode_has_daily_memory_signal(cls, ep: EpisodicMemory) -> bool:
        text = cls._normalize_match_text(
            " ".join(
                [
                    ep.topic,
                    ep.summary,
                    " ".join(ep.key_decisions),
                    " ".join(ep.open_issues),
                    " ".join(ep.topics_covered),
                ]
            )
        )
        if not text:
            return False
        personal_choice_markers = {
            "用户", "user", "asks", "wants", "requested", "considering", "recommend", "choose",
            "preference", "criteria", "option", "compare", "plan",
            "用户询问", "想", "希望", "要求", "推荐", "选择", "比较", "偏好", "标准", "条件",
            "是否合适", "适合", "首选", "待确认",
        }
        project_markers = {
            "project", "platform", "system", "benchmark", "paper", "proposal", "workflow",
            "项目", "平台", "系统", "评测", "论文", "工作流",
        }
        profile_markers = {
            "身份", "背景", "职业", "机构", "研究方向", "role", "background", "affiliation",
        }
        return (
            any(marker in text for marker in personal_choice_markers)
            and not any(marker in text for marker in project_markers)
            and not any(marker in text for marker in profile_markers)
        )

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
        progress("Phase 1: Building episodic evidence chunks for each conversation...")
        episodes: list[EpisodicMemory] = []
        skipped_noise = 0
        for i, conv in enumerate(conversations):
            if len(conv.full_text().strip()) < 30:
                skipped_noise += 1
                continue
            progress(f"  Episodes {i + 1}/{len(conversations)}: {conv.title or conv.conv_id}")
            conv_episodes = self._build_episodes(conv)
            if not conv_episodes:
                skipped_noise += 1  # LLM parse failure
                continue
            for ep in conv_episodes:
                if self._episode_has_daily_memory_signal(ep):
                    ep.relates_to_preferences = True
                if not ep.relates_to_profile and not ep.relates_to_preferences \
                        and not ep.relates_to_projects and not ep.relates_to_workflows \
                        and not self._episode_has_persistent_topic_signal(ep):
                    skipped_noise += 1  # no memory-relevant content
                    continue
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
        target_language = self._dominant_episode_language(episodes)
        language_context = self._language_policy_context(target_language)

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
        self.maintain_episode_connections(
            episodes,
            profile_ep_ids,
            pref_ep_ids,
            project_ep_map,
            workflow_ep_map,
        )

        # Episode counts per type — used for CLI summary
        results["episodes_to_profile"] = len(profile_ep_ids)
        results["episodes_to_preferences"] = len(pref_ep_ids)
        results["episodes_to_projects"] = sum(len(v) for v in project_ep_map.values())
        results["episodes_to_workflows"] = sum(len(v) for v in workflow_ep_map.values())

        # --- Extract profile ---
        progress("Extracting profile from episodes...")
        profile_context = language_context + "\n" + self._filter_digest(episodes, l1_text, "profile")
        profile_data = self.llm.extract_json(self.prompts["profile_system"], profile_context)
        profile = self._build_profile(profile_data, l1_text, earliest_ts,
                                      profile_ep_ids, ep_by_id, target_language)
        self.wiki.save_profile(profile)
        results["profile"] = bool(profile.name_or_alias or profile.role_identity)

        # --- Extract preferences ---
        progress("Extracting preferences from episodes...")
        pref_context = language_context + "\n" + self._filter_digest(episodes, l1_text, "preferences")
        pref_data = self.llm.extract_json(self.prompts["preference_system"], pref_context)
        prefs = self._build_preferences(pref_data, l1_text, earliest_ts,
                                        pref_ep_ids, ep_by_id, target_language)
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
        project_context = language_context + "\n" + self._filter_digest(episodes, l1_text, "projects")
        projects_data = self.llm.extract_json(self.prompts["projects_system"], project_context)
        projects = self._build_projects(projects_data, l1_text, earliest_ts,
                                        project_ep_map, ep_by_id, target_language)
        for proj in projects:
            self.wiki.save_project(proj)
        results["projects"] = len(projects)

        # --- Extract workflows ---
        progress("Extracting workflows from episodes...")
        workflow_context = language_context + "\n" + self._filter_digest(episodes, l1_text, "workflows")
        workflows_data = self.llm.extract_json(self.prompts["workflows_system"], workflow_context)
        workflows = self._build_workflows(workflows_data, l1_text, earliest_ts,
                                          workflow_ep_map, ep_by_id, target_language)
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

    def _turn_text(self, conv: RawConversation, turn_id: str) -> str:
        id_to_message = {msg.msg_id: msg for msg in conv.messages}
        turn = next((item for item in conv.turns if item.turn_id == turn_id), None)
        if turn is None:
            return ""
        messages = [id_to_message[msg_id] for msg_id in turn.message_ids if msg_id in id_to_message]
        return "\n".join(f"[{msg.role.upper()}]: {msg.content}" for msg in messages)

    def _turns_text(self, conv: RawConversation) -> str:
        parts: list[str] = []
        for turn in conv.turns:
            text = self._turn_text(conv, turn.turn_id).strip()
            if text:
                parts.append(f"TURN {turn.turn_id}\n{text}")
        return "\n\n".join(parts)

    def _episode_items_from_response(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("episodes"), list):
                return [item for item in data["episodes"] if isinstance(item, dict)]
            return [data]
        return []

    def _normalize_episode_turn_refs(self, conv: RawConversation, item: dict[str, Any]) -> list[str]:
        valid_turn_ids = [turn.turn_id for turn in conv.turns if getattr(turn, "turn_id", "")]
        valid_set = set(valid_turn_ids)
        raw_refs = item.get("turn_refs")
        if isinstance(raw_refs, str):
            raw_refs = [raw_refs]
        refs = [str(ref).strip() for ref in (raw_refs or []) if str(ref).strip() in valid_set]
        if refs:
            return list(dict.fromkeys(refs))
        if len(valid_turn_ids) == 1:
            return valid_turn_ids
        return []

    def _episode_time_bounds(self, conv: RawConversation, turn_refs: list[str]) -> tuple[datetime | None, datetime | None]:
        id_to_message = {msg.msg_id: msg for msg in conv.messages}
        times: list[datetime] = []
        for turn_id in turn_refs:
            turn = next((item for item in conv.turns if item.turn_id == turn_id), None)
            if not turn:
                continue
            for msg_id in turn.message_ids:
                msg = id_to_message.get(msg_id)
                if not msg or not msg.timestamp:
                    continue
                try:
                    times.append(datetime.fromisoformat(str(msg.timestamp).replace("Z", "+00:00")))
                except ValueError:
                    continue
        if times:
            return min(times), max(times)
        return conv.start_time, conv.end_time or conv.start_time

    @staticmethod
    def _detect_primary_language(text: str) -> str:
        cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        ascii_alpha_count = sum(1 for ch in text if ("a" <= ch.lower() <= "z"))
        if cjk_count >= max(2, ascii_alpha_count // 3):
            return "zh"
        if ascii_alpha_count:
            return "en"
        return ""

    def _episode_display_payload(
        self,
        item: dict[str, Any],
        primary_language: str,
        title: str,
        summary: str,
    ) -> dict[str, dict[str, str]]:
        raw_display = item.get("display") if isinstance(item.get("display"), dict) else {}
        display: dict[str, dict[str, str]] = {}
        for lang in ["zh", "en"]:
            value = raw_display.get(lang) if isinstance(raw_display, dict) else None
            if isinstance(value, dict):
                display[lang] = {
                    "title": str(value.get("title") or "").strip(),
                    "summary": str(value.get("summary") or "").strip(),
                }
        lang = primary_language if primary_language in {"zh", "en"} else self._detect_primary_language(f"{title}\n{summary}")
        if lang in {"zh", "en"}:
            current = display.setdefault(lang, {"title": "", "summary": ""})
            current["title"] = current["title"] or title
            current["summary"] = current["summary"] or summary
        return display

    @staticmethod
    def _episode_display_text(ep: EpisodicMemory) -> tuple[str, str]:
        lang = ep.primary_language if ep.primary_language in {"zh", "en"} else ""
        display = ep.display.get(lang) if lang else None
        if display:
            title = display.title or ep.topic
            summary = display.summary or ep.summary
            return title, summary
        return ep.topic, ep.summary

    @classmethod
    def _dominant_episode_language(cls, episodes: list[EpisodicMemory]) -> str:
        scores = {"zh": 0, "en": 0}
        for ep in episodes:
            lang = ep.primary_language if ep.primary_language in scores else cls._detect_primary_language(
                " ".join([ep.topic, ep.summary, " ".join(ep.key_decisions), " ".join(ep.open_issues)])
            )
            if lang in scores:
                # Weight profile/project/workflow-bearing episodes slightly more
                # because persistent memory is built from durable evidence.
                weight = 2 if (
                    ep.relates_to_profile
                    or ep.relates_to_preferences
                    or ep.relates_to_projects
                    or ep.relates_to_workflows
                ) else 1
                scores[lang] += weight
        if scores["zh"] > scores["en"]:
            return "zh"
        if scores["en"] > scores["zh"]:
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
            )
        if language == "en":
            return (
                "TARGET DISPLAY LANGUAGE: en\n"
                "Write all human-facing natural-language memory values in English, "
                "while preserving necessary proper nouns and technical terms in their original form.\n"
            )
        return (
            "TARGET DISPLAY LANGUAGE: infer from the source evidence\n"
            "Write human-facing memory values in the dominant language of the supporting episodes, "
            "while preserving necessary proper nouns and technical terms in their original form.\n"
        )

    def _build_episodes(self, conv: RawConversation) -> list[EpisodicMemory]:
        text = self._turns_text(conv)[:7000] or conv.full_text()[:4000]
        user_prompt = (
            f"Conversation title: {conv.title or conv.conv_id}\n"
            f"Platform: {conv.platform}\n"
            f"Message count: {len(conv.messages)}\n\n"
            f"{text}"
        )
        data = self.llm.extract_json(self.prompts["episode_system"], user_prompt)
        items = self._episode_items_from_response(data)
        episodes: list[EpisodicMemory] = []
        for item in items:
            turn_refs = self._normalize_episode_turn_refs(conv, item)
            if not turn_refs:
                continue
            for turn_ref in turn_refs:
                turn_text = self._turn_text(conv, turn_ref)
                primary_language = str(item.get("primary_language") or "").strip().lower()
                if primary_language not in {"zh", "en"}:
                    primary_language = self._detect_primary_language(turn_text)
                title = str(item.get("topic") or item.get("title") or conv.title or conv.conv_id).strip()
                summary = str(item.get("summary") or "").strip()
                start_time, end_time = self._episode_time_bounds(conv, [turn_ref])
                ep = EpisodicMemory(
                    episode_id=str(uuid.uuid4())[:8],
                    conv_id=conv.conv_id,
                    platform=conv.platform,
                    topic=title,
                    primary_language=primary_language,
                    display=self._episode_display_payload(item, primary_language, title, summary),
                    topics_covered=item.get("topics_covered") or [],
                    summary=summary,
                    key_decisions=item.get("key_decisions") or [],
                    open_issues=item.get("open_issues") or [],
                    granularity="turn",
                    turn_refs=[turn_ref],
                    relates_to_profile=bool(item.get("relates_to_profile")),
                    relates_to_preferences=bool(item.get("relates_to_preferences")),
                    relates_to_projects=item.get("relates_to_projects") or [],
                    relates_to_workflows=item.get("relates_to_workflows") or [],
                    related_project=str(item.get("related_project") or "").strip(),
                    time_range_start=start_time,
                    time_range_end=end_time,
                )
                if ep.related_project and ep.related_project not in ep.relates_to_projects:
                    ep.relates_to_projects.append(ep.related_project)
                if start_time is not None:
                    ep.created_at = start_time
                if end_time is not None:
                    ep.updated_at = end_time
                elif start_time is not None:
                    ep.updated_at = start_time
                ep.add_evidence("l0_raw", conv.conv_id, ep.summary[:240] or conv.title or conv.conv_id)
                episodes.append(ep)
        return episodes

    def _build_episode(self, conv: RawConversation) -> EpisodicMemory | None:
        episodes = self._build_episodes(conv)
        return episodes[0] if episodes else None

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
            title, summary = self._episode_display_text(ep)
            entry = (
                f"[{ep.episode_id}] {ts} — {title}\n"
                f"  Language: {ep.primary_language or 'unknown'}\n"
                f"  Topics: {', '.join(ep.topics_covered)}\n"
                f"  Summary: {summary}"
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

    @staticmethod
    def _episode_digest_sort_key(ep: EpisodicMemory) -> tuple[str, int, str]:
        turn_index = 10**9
        if ep.turn_refs:
            try:
                turn_index = int(str(ep.turn_refs[0]).rsplit(":turn:", 1)[1])
            except (IndexError, ValueError):
                turn_index = 10**9
        ts = ep.time_range_start or ep.created_at
        return ts.isoformat() if ts else "9999", turn_index, ep.episode_id

    def _filter_digest(
        self, episodes: list[EpisodicMemory], l1_text: str, filter_type: str
    ) -> str:
        """Build a digest filtered to episodes relevant to a specific memory type."""
        if filter_type == "profile":
            relevant = sorted([ep for ep in episodes if ep.relates_to_profile] or episodes, key=self._episode_digest_sort_key)
            return self._build_episode_digest(relevant[:40], l1_text)[:6000]
        elif filter_type == "preferences":
            relevant = sorted([ep for ep in episodes if ep.relates_to_preferences], key=self._episode_digest_sort_key)
            return self._build_episode_digest(relevant[:40], l1_text)[:6000]
        elif filter_type == "projects":
            # Prefer episodes that already point to a project. Only add a small
            # amount of project-intent context as fallback, otherwise unrelated
            # advice episodes can leak their decisions into active projects.
            flagged = [ep for ep in episodes if ep.relates_to_projects]
            if flagged:
                backfill = max(0, min(6, 12 - len(flagged)))
                unflagged = [
                    ep for ep in episodes
                    if not ep.relates_to_projects and self._episode_has_project_intent(ep)
                ][:backfill]
                relevant = sorted(flagged + unflagged, key=self._episode_digest_sort_key)[:40]
            else:
                relevant = sorted(
                    [ep for ep in episodes if self._episode_has_project_intent(ep)],
                    key=self._episode_digest_sort_key,
                )[:15]
            return self._build_episode_digest(relevant, l1_text, verbose=True)[:7000]
        elif filter_type == "workflows":
            relevant = sorted([ep for ep in episodes if ep.relates_to_workflows] or episodes, key=self._episode_digest_sort_key)
            return self._build_episode_digest(relevant[:40], l1_text, verbose=True)[:6000]
        else:
            relevant = sorted(episodes, key=self._episode_digest_sort_key)
            return self._build_episode_digest(relevant[:40], l1_text)[:6000]

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
    def _episode_turn_refs(
        ep_ids: list[str],
        ep_by_id: dict[str, EpisodicMemory],
    ) -> list[str]:
        refs: list[str] = []
        for eid in ep_ids:
            ep = ep_by_id.get(str(eid or "").strip())
            if not ep:
                continue
            refs.extend(str(ref).strip() for ref in ep.turn_refs if str(ref).strip())
        return list(dict.fromkeys(refs))

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
    ) -> None:
        if not target_id or target_id == ep.episode_id:
            return
        candidate = EpisodeConnection(
            episode_id=target_id,
            relation=relation,
            key=key,
            reason=reason,
        )
        for existing in ep.connections:
            if (
                existing.episode_id == candidate.episode_id
                and existing.relation == candidate.relation
                and existing.key == candidate.key
            ):
                return
        ep.connections.append(candidate)

    def _connect_episode_group(
        self,
        ep_by_id: dict[str, EpisodicMemory],
        episode_ids: list[str],
        relation: str,
        key: str = "",
        reason: str = "",
        max_neighbors: int = 20,
    ) -> None:
        clean_ids = [eid for eid in dict.fromkeys(episode_ids) if eid in ep_by_id]
        if relation == "project" and key:
            for eid in clean_ids:
                if key not in ep_by_id[eid].relates_to_projects:
                    ep_by_id[eid].relates_to_projects.append(key)
        elif relation == "workflow" and key:
            for eid in clean_ids:
                if key not in ep_by_id[eid].relates_to_workflows:
                    ep_by_id[eid].relates_to_workflows.append(key)
        if len(clean_ids) < 2:
            return
        for eid in clean_ids:
            others = [other for other in clean_ids if other != eid][:max_neighbors]
            for other in others:
                self._add_episode_connection(ep_by_id[eid], other, relation, key, reason)

    def maintain_episode_connections(
        self,
        episodes: list[EpisodicMemory],
        profile_ep_ids: list[str],
        pref_ep_ids: list[str],
        project_ep_map: dict[str, list[str]],
        workflow_ep_map: dict[str, list[str]],
    ) -> None:
        """Refresh deterministic episode-to-episode links.

        Episode chunks stay turn-level. Connections provide two kinds of
        traversal: neighboring turns in the same raw conversation, and semantic
        grouping maintained by persistent memory categories.
        """
        ep_by_id = {ep.episode_id: ep for ep in episodes}
        for ep in episodes:
            ep.connections = []

        by_conversation: dict[str, list[EpisodicMemory]] = {}
        for ep in episodes:
            if ep.conv_id:
                by_conversation.setdefault(ep.conv_id, []).append(ep)
        for conv_eps in by_conversation.values():
            ordered = sorted(conv_eps, key=self._turn_index)
            for index, ep in enumerate(ordered):
                for neighbor in (ordered[index - 1:index] + ordered[index + 1:index + 2]):
                    self._add_episode_connection(
                        ep,
                        neighbor.episode_id,
                        "conversation_context",
                        ep.conv_id,
                        "adjacent turn in the same raw conversation",
                    )

        self._connect_episode_group(
            ep_by_id,
            profile_ep_ids,
            "profile",
            reason="shared profile evidence",
        )
        self._connect_episode_group(
            ep_by_id,
            pref_ep_ids,
            "preferences",
            reason="shared preference evidence",
        )
        for project_name, ep_ids in project_ep_map.items():
            self._connect_episode_group(
                ep_by_id,
                ep_ids,
                "project",
                project_name,
                "same persistent project",
            )
        for workflow_name, ep_ids in workflow_ep_map.items():
            self._connect_episode_group(
                ep_by_id,
                ep_ids,
                "workflow",
                workflow_name,
                "same persistent workflow",
            )

        for ep in episodes:
            if ep.connections:
                self.wiki.save_episode(ep)

    def _build_profile(
        self,
        data: dict,
        l1_text: str,
        global_earliest: datetime | None,
        episode_ids: list[str],
        ep_by_id: dict[str, EpisodicMemory],
        target_language: str = "",
    ) -> ProfileMemory:
        profile = self.wiki.load_profile() or ProfileMemory()
        if target_language:
            profile.primary_language = target_language
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
        profile.source_turn_refs = list(dict.fromkeys(
            profile.source_turn_refs + self._episode_turn_refs(episode_ids, ep_by_id)
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
        target_language: str = "",
    ) -> PreferenceMemory:
        prefs = self.wiki.load_preferences() or PreferenceMemory()
        if target_language:
            prefs.primary_language = target_language
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
        prefs.source_turn_refs = list(dict.fromkeys(
            prefs.source_turn_refs + self._episode_turn_refs(episode_ids, ep_by_id)
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
        target_language: str = "",
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
            if target_language:
                proj.primary_language = target_language
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
            proj.source_turn_refs = list(dict.fromkeys(
                proj.source_turn_refs + self._episode_turn_refs(ep_ids, ep_by_id)
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
        target_language: str = "",
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
            if target_language:
                wf.primary_language = target_language
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
            wf.source_turn_refs = list(dict.fromkeys(
                wf.source_turn_refs + self._episode_turn_refs(ep_ids, ep_by_id)
            ))
            if name not in existing:
                workflows.append(wf)
        return workflows
