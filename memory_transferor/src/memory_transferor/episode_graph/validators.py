from __future__ import annotations

from memory_transferor.memory_models import EpisodeGroup


class EpisodeGroupValidator:
    """Bound connection groups so one weak edge cannot absorb everything."""

    def __init__(self, *, max_semantic_group_size: int = 8, max_conversation_group_size: int = 30) -> None:
        self.max_semantic_group_size = max_semantic_group_size
        self.max_conversation_group_size = max_conversation_group_size

    def trim_group(self, group: EpisodeGroup) -> EpisodeGroup:
        max_size = (
            self.max_conversation_group_size
            if group.relation == "conversation_context"
            else self.max_semantic_group_size
        )
        if len(group.episode_ids) <= max_size:
            return group
        keep_ids = group.episode_ids[:max_size]
        return group.model_copy(update={"episode_ids": keep_ids})

    def should_keep_group(self, group: EpisodeGroup) -> bool:
        return len(set(group.episode_ids)) >= 2
