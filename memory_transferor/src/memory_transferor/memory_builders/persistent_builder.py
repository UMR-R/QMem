from __future__ import annotations

import json
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
- Prefer recall usefulness over compression. Do not hide distinct reusable facts inside one broad description when they would be retrieved separately later.
- EPISODE_GROUPS are pre-persistent connection groups. Use them as grouping hints, not as proof that every episode in the group supports every item.
- Prefer evidence_episode_ids that directly support the item. Do not include a whole group by default.

Type boundaries:
- profile: identity, background, language mode, role, domain context, or durable communication context.
- preference: stable response style, terminology, formatting, language, revision, or interaction preference.
- topic: durable project theme, research/product direction, schema/design area, or active long-horizon interest.
- workflow: reusable procedure with a trigger and ordered steps.
- daily_note: reusable non-project daily context, personal choice context, taste, lifestyle, or small useful facts.
- skill: only when evidence explicitly says the user saved, created, selected, recommended, or wants to reuse a Skill asset.

Atomicity examples:
- A main project, its schema/design subarea, and its product/application direction must become separate topic items when each has distinct evidence.
- A final review/check procedure must become a separate workflow when the evidence presents it as a reusable final step or independently requested quality/risk check. Do not only bury that check inside the larger production workflow.
- A preferred explanation style is a preference/profile signal, not a skill, unless the user explicitly saves it as a Skill asset.
- Assistant-only suggestions are not user decisions or preferences unless the user accepts or repeats them.

Classification guardrails:
- Habitual working language, discussion language, domain background, and communication context are profile.
- Desired assistant output language for a task type is preference.
- Active research, writing, product, benchmark, or implementation work is topic/project memory, not profile.
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
