from __future__ import annotations

from typing import Any

from memory_transferor.memory_models import Episode, PersistentMemoryItem


def episode_index_documents(episodes: list[Episode]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": f"episode:{episode.episode_id}",
            "doc_type": "episode",
            "source_layer": "L2",
            "session_id": episode.session_id,
            "episode_id": episode.episode_id,
            "turn_id": episode.turn_id,
            "timestamp": episode.timestamp.isoformat() if episode.timestamp else "",
            "text": episode.summary,
        }
        for episode in episodes
    ]


def persistent_index_documents(items: list[PersistentMemoryItem]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": f"persistent:{item.type}:{item.memory_id}",
            "doc_type": item.type,
            "source_layer": "L2",
            "memory_id": item.memory_id,
            "timestamp": "",
            "text": item.description,
        }
        for item in items
    ]

