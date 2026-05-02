from __future__ import annotations

from datetime import datetime

from memory_transferor.memory_models import Episode


class TemporalPolicy:
    """Utilities for source-time ordering."""

    def sort_episodes(self, episodes: list[Episode]) -> list[Episode]:
        return sorted(episodes, key=self.episode_order_key)

    def episode_order_key(self, episode: Episode) -> tuple[datetime, int]:
        timestamp = episode.timestamp or datetime.min
        return timestamp, self.turn_index(episode.turn_id)

    def turn_index(self, turn_id: str) -> int:
        try:
            return int(str(turn_id).rsplit(":turn:", 1)[1])
        except (IndexError, ValueError):
            return 10**9
