from __future__ import annotations

import hashlib

from memory_transferor.memory_models import Episode, RawChatSession


class EpisodeBuilder:
    """Build turn-level episodes from canonical raw chat turns."""

    def build(self, sessions: list[RawChatSession]) -> list[Episode]:
        episodes: list[Episode] = []
        for session in sessions:
            for turn in session.turns:
                text = turn.text().strip()
                if not text:
                    continue
                episode_id = hashlib.sha1(turn.turn_id.encode("utf-8")).hexdigest()[:10]
                episodes.append(
                    Episode(
                        episode_id=episode_id,
                        session_id=session.session_id,
                        turn_id=turn.turn_id,
                        timestamp=turn.timestamp or session.timestamp,
                        summary=text,
                        source_turn_text=text,
                    )
                )
        return episodes

