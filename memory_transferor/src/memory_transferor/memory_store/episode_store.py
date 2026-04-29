from __future__ import annotations

from pathlib import Path

from memory_transferor.memory_models import Episode


class EpisodeStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, episodes: list[Episode]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        by_session: dict[str, list[Episode]] = {}
        for episode in episodes:
            by_session.setdefault(episode.session_id, []).append(episode)
        for session_id, rows in by_session.items():
            payload = {
                "session_id": session_id,
                "episode_count": len(rows),
                "episodes": [row.model_dump(mode="json") for row in rows],
            }
            (self.root / f"{session_id}.json").write_text(
                __import__("json").dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

