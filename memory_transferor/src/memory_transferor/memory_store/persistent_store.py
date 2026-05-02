from __future__ import annotations

import json
from pathlib import Path

from memory_transferor.memory_models import PersistentMemoryItem


class PersistentStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure(self) -> None:
        for folder in ("profile", "preferences", "projects", "workflows", "daily_notes", "skills"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)

    def save_items(self, items: list[PersistentMemoryItem]) -> None:
        self.ensure()
        by_type: dict[str, list[dict]] = {}
        for item in items:
            by_type.setdefault(item.type, []).append(item.model_dump(mode="json"))
        mapping = {
            "profile": "profile/items.json",
            "preference": "preferences/items.json",
            "workflow": "workflows/items.json",
            "topic": "projects/topics.json",
            "daily_note": "daily_notes/items.json",
            "skill": "skills/items.json",
        }
        for item_type, rows in by_type.items():
            path = self.root / mapping.get(item_type, f"daily_notes/{item_type}.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
