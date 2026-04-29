from __future__ import annotations

import json
from hashlib import sha1
from typing import Any

from memory_transferor.memory_models import Episode, PersistentMemoryItem
from memory_transferor.runtime import LLMClient


_SYSTEM = """You extract stable long-term memory from chat evidence.

Return strict JSON only:
{
  "items": [
    {
      "type": "preference | profile | workflow | topic | daily_note | skill",
      "key": "snake_case_key",
      "description": "stable memory in Chinese",
      "evidence_episode_ids": ["..."],
      "evidence_turn_ids": ["..."],
      "confidence": "low | medium | high",
      "scope": "persistent",
      "export_priority": "low | medium | high",
      "steps": ["optional workflow steps"]
    }
  ]
}

Rules:
- Extract all stable preferences, profile facts, workflows, topics, daily notes, and skills supported by evidence.
- Keep each item atomic. If one cluster contains a main project, its schema design, and a product direction, return three topic items.
- Do not merge a final review/check step into a larger workflow when it can be reused independently.
- Split product direction, plugin/app direction, schema design, and core research/project theme into separate topic items when each has its own evidence.
- Classify identity, background, language mode, and durable communication context as profile.
- Classify style constraints, output preferences, and repeated desired assistant behavior as preference.
- Only output skill when the evidence explicitly says the user saved, created, selected, recommended, or wants to reuse a Skill asset. Do not infer skill from a preferred explanation style.
- Do not invent facts not supported by the evidence.
- Preserve time-sensitive evidence ids so each memory can be traced back.
- A workflow is a repeated or explicitly requested procedure.
- A topic is a durable project/theme/interest, not just a one-off mention.
- Use concise Chinese descriptions.
"""


class PersistentBuilder:
    """Distill persistent memory from episodes."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def build(self, episodes: list[Episode]) -> list[PersistentMemoryItem]:
        evidence = []
        for ep in episodes:
            evidence.append(
                {
                    "episode_id": ep.episode_id,
                    "turn_id": ep.turn_id,
                    "timestamp": ep.timestamp.isoformat() if ep.timestamp else "",
                    "summary": ep.summary,
                }
            )
        payload = self.llm.extract_json(
            _SYSTEM,
            "EVIDENCE:\n" + json.dumps(evidence, ensure_ascii=False, indent=2),
        )
        if isinstance(payload, dict):
            items = payload.get("items", [])
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        return [
            PersistentMemoryItem.model_validate(self._normalize_item(item))
            for item in items
            if isinstance(item, dict)
        ]

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
