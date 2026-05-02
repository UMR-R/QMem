from __future__ import annotations

import json
import re
from hashlib import sha1
from typing import Any

from memory_transferor.memory_models import Episode, EpisodeGroup, PersistentMemoryItem
from memory_transferor.memory_policy import PersistentMemoryPolicy
from memory_transferor.runtime import LLMClient


_SYSTEM = """You extract stable long-term memory from turn-level episode evidence.

Return strict JSON only:
{
  "items": [
    {
      "type": "preference | profile | workflow | topic | daily_note | skill",
      "key": "snake_case_key",
      "description": "stable memory description",
      "evidence_episode_ids": ["..."],
      "evidence_turn_ids": ["..."],
      "confidence": "low | medium | high",
      "scope": "persistent",
      "export_priority": "low | medium | high",
      "steps": ["optional workflow steps"]
    }
  ]
}

Language policy:
- The rules are in English for precision.
- Write human-facing descriptions in the dominant language of the supporting evidence.
- If the output language is Chinese but an English term is clearer or is a proper noun, keep that term in English.
- Preserve paper/model/dataset/tool names, code names, and technical terms in their original form.

Core rules:
- Extract all stable preferences, profile facts, workflows, topics, daily notes, and skills supported by evidence.
- Do not invent facts not supported by the evidence.
- Preserve time-sensitive evidence ids so each memory can be traced back.
- Use timestamps and event order to resolve "current", "previous", "before", "after", "latest", and superseded facts.
- Keep each item atomic, but do not split merely because a sentence has multiple synonyms.
- Prefer recall usefulness over compression, but keep project/topic boundaries stable.
- For topic/project memory, default to one parent item per user-owned effort. Put components, schemas, tools, delivery surfaces, and implementation tracks inside the parent description unless evidence shows they have separate goals, state, decisions, or next actions.
- For writing, proposal, benchmark, planning, or guidance evidence, preserve the underlying subject/project object. Do not name a topic as generic writing guidance when the evidence contains a concrete research topic, system, dataset, paper, or project object.
- EPISODE_GROUPS are pre-persistent connection groups. Use them as grouping hints, not as proof that every episode in the group supports every item.
- Prefer evidence_episode_ids that directly support the item. Do not include a whole group by default.
- Do not hard-code or copy category labels from this prompt, examples, test cases, project names, tools, or evaluation artifact names. Infer names and groupings from evidence, existing memory, and user-confirmed edits.

Type boundaries:
- profile: identity, background, language mode, role, domain context, or durable communication context.
- preference: stable response style, terminology, formatting, language, revision, or interaction preference.
- topic: durable user-owned project theme, research/product direction, active long-horizon interest, or independently tracked subproject.
- workflow: reusable procedure with a trigger and ordered steps.
- daily_note: reusable non-project daily context, personal choice context, taste, lifestyle, or small useful facts.
- skill: only when evidence explicitly says the user saved, created, selected, recommended, or wants to reuse a Skill asset.

Display taxonomy boundary:
- Do not output frontend display groups as persistent memory items.
- Profile display groups are identity, knowledge_background, and long_term_focus.
- Preference display groups are language, expression_style, and main_task_types.
- common_languages can support language handling, but it is not knowledge_background.
- New display groups must be suggested through a display-taxonomy proposal flow, not stored as profile/preference/skill items.

Workflow and skill relationship:
- A workflow may reference a saved or recommended skill as one step, but the workflow must remain understandable without that skill.
- A skill is a reusable capability asset. A workflow is a reusable procedure that may call one or more skills.
- Do not invent skill names. If the evidence only shows a procedure and no reusable asset boundary, store workflow rather than skill.

Example policy:
- Examples are illustrative context, not a fixed taxonomy and not phrases to copy.
- A parent effort, a subarea, and a delivery/application direction should usually be one topic item when they serve the same user-owned effort.
- Create separate topic items only when the user treats the subarea as standalone work, or when it has its own goal, stage, decisions, unresolved questions, or next actions.
- Do not create sibling topic items that repeat the same evidence as their parent with labels like schema, retrieval, export, benchmark, product direction, plugin, or implementation track.
- A final review/check procedure may become a separate workflow when evidence presents it as a reusable final step or independently requested quality/risk check.
- A preferred explanation style is a preference/profile signal, not a skill, unless the user explicitly saves it as a Skill asset.
- Assistant-only suggestions are not user decisions or preferences unless the user accepts or repeats them.

Classification guardrails:
- Habitual working language, discussion language, domain background, and communication context are profile.
- Desired assistant output language for a task type is preference.
- Active user-owned work is topic/project memory, not profile, regardless of domain or artifact type.
- If an item could be both profile and topic, use profile only for the user's durable background and topic for the active work.
"""


class PersistentBuilder:
    """Distill persistent memory from episodes."""

    def __init__(self, llm: LLMClient, policy: PersistentMemoryPolicy | None = None) -> None:
        self.llm = llm
        self.policy = policy or PersistentMemoryPolicy()

    def build(
        self,
        episodes: list[Episode],
        episode_groups: list[EpisodeGroup] | None = None,
    ) -> list[PersistentMemoryItem]:
        evidence = []
        for ep in episodes:
            evidence.append(
                {
                    "episode_id": ep.episode_id,
                    "turn_id": ep.turn_id,
                    "timestamp": ep.timestamp.isoformat() if ep.timestamp else "",
                    "summary": ep.summary,
                    "keywords": ep.keywords,
                    "connection_group_ids": ep.connection_group_ids,
                    "connections": [
                        {
                            "target_episode_id": connection.target_episode_id,
                            "relation": connection.relation,
                            "confidence": connection.confidence,
                            "score": connection.score,
                            "bidirectional_verified": connection.bidirectional_verified,
                        }
                        for connection in ep.connections
                    ],
                }
            )
        groups = [
            group.model_dump(mode="json")
            for group in (episode_groups or [])
        ]
        payload = self.llm.extract_json(
            _SYSTEM,
            "EPISODE_GROUPS:\n"
            + json.dumps(groups, ensure_ascii=False, indent=2)
            + "\n\nEVIDENCE:\n"
            + json.dumps(evidence, ensure_ascii=False, indent=2),
        )
        if isinstance(payload, dict):
            items = payload.get("items", [])
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        persistent_items = [
            PersistentMemoryItem.model_validate(self._normalize_item(item))
            for item in items
            if isinstance(item, dict)
        ]
        persistent_items = self._repair_generic_project_topics(persistent_items, episodes)
        return self.policy.apply(persistent_items)

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        item = dict(item)
        item.setdefault("type", "daily_note")
        item.setdefault("key", "memory")
        item.setdefault("description", "")
        item.setdefault("evidence_episode_ids", [])
        item.setdefault("evidence_turn_ids", [])
        item.setdefault("confidence", "medium")
        item.setdefault("scope", "persistent")
        item.setdefault("export_priority", "medium")
        item.setdefault("steps", [])

        for field in ("evidence_episode_ids", "evidence_turn_ids", "steps"):
            value = item.get(field)
            if isinstance(value, str):
                item[field] = [value]
            elif not isinstance(value, list):
                item[field] = []

        if not item.get("memory_id"):
            seed = json.dumps(
                {
                    "type": item["type"],
                    "key": item["key"],
                    "description": item["description"],
                    "episodes": item["evidence_episode_ids"],
                    "turns": item["evidence_turn_ids"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            item["memory_id"] = f"{item['type']}_{sha1(seed.encode('utf-8')).hexdigest()[:10]}"

        return item

    def _repair_generic_project_topics(
        self,
        items: list[PersistentMemoryItem],
        episodes: list[Episode],
    ) -> list[PersistentMemoryItem]:
        by_id = {episode.episode_id: episode for episode in episodes}
        repaired: list[PersistentMemoryItem] = []
        for item in items:
            if item.type != "topic" or not self._looks_like_generic_project_topic(item):
                repaired.append(item)
                continue
            evidence_text = self._evidence_text(item, by_id)
            subject = self._project_subject_from_text(evidence_text)
            if not subject:
                repaired.append(item)
                continue
            if subject.lower() in f"{item.key} {item.description}".lower():
                repaired.append(item)
                continue
            key = self._slug(f"{subject} proposal project")
            description = f"用户正在围绕 {subject} 准备 proposal 或项目材料；当前需要组织 benchmark、任务定义、数据划分、baseline 和评价指标等内容。"
            repaired.append(
                item.model_copy(
                    update={
                        "memory_id": self._stable_id("topic", key, description, item.evidence_episode_ids),
                        "key": key,
                        "description": description,
                    }
                )
            )
        return repaired

    def _looks_like_generic_project_topic(self, item: PersistentMemoryItem) -> bool:
        text = f"{item.key} {item.description}".lower()
        process_markers = ("proposal", "writing", "guidance", "benchmark", "写作", "写法", "组织")
        subject_markers = (
            r"[a-z][a-z0-9]*-[a-z0-9][a-z0-9-]*",
            r"\b[a-z0-9-]+\s+binding\s+prediction\b",
            r"\b[a-z0-9-]+\s+system\b",
        )
        return any(marker in text for marker in process_markers) and not any(
            re.search(pattern, text) for pattern in subject_markers
        )

    def _evidence_text(self, item: PersistentMemoryItem, by_id: dict[str, Episode]) -> str:
        rows: list[str] = []
        seen: set[str] = set()
        queue = list(item.evidence_episode_ids)
        for episode_id in queue:
            if episode_id in seen:
                continue
            seen.add(episode_id)
            episode = by_id.get(episode_id)
            if not episode:
                continue
            rows.extend([episode.summary, episode.source_turn_text, " ".join(episode.keywords)])
            for connection in episode.connections:
                if connection.relation == "semantic" and connection.bidirectional_verified:
                    target = by_id.get(connection.target_episode_id)
                    if target:
                        rows.extend([target.summary, target.source_turn_text, " ".join(target.keywords)])
        return "\n".join(row for row in rows if row)

    def _project_subject_from_text(self, text: str) -> str:
        for pattern in (
            r"\b([A-Za-z][A-Za-z0-9]*-[A-Za-z0-9][A-Za-z0-9-]*\s+binding\s+prediction)\b",
            r"把\s*([^，。；,.!?]{2,80}?)\s*(?:这个)?(?:项目|方向|主题|proposal|论文)\s*(?:写成|整理成|做成|设计成)",
            r"(?:围绕|关于)\s*([^，。；,.!?]{2,80}?)\s*(?:这个)?(?:项目|方向|主题|proposal|论文)",
            r"\b([A-Za-z][A-Za-z0-9]*-[A-Za-z0-9][A-Za-z0-9-]*(?:\s+binding\s+prediction)?)\b",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._clean_subject(match.group(1))
        return ""

    def _clean_subject(self, subject: str) -> str:
        subject = re.sub(r"^(?:我想|我们想|想要|继续|上次那个)\s*", "", str(subject).strip())
        subject = re.sub(r"\s+", " ", subject)
        return subject.strip(" ：:，。；,.!?")

    def _slug(self, text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return slug or "project"

    def _stable_id(self, memory_type: str, key: str, description: str, episode_ids: list[str]) -> str:
        seed = json.dumps(
            {
                "type": memory_type,
                "key": key,
                "description": description,
                "episodes": episode_ids,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return f"{memory_type}_{sha1(seed.encode('utf-8')).hexdigest()[:10]}"
