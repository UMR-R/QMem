from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from memory_transferor.memory_models import Episode, EpisodeGroup

from .connection import make_connection, make_group
from .connection_policy import ConnectionPolicy
from .validators import EpisodeGroupValidator


class EpisodeGraph(BaseModel):
    episodes: list[Episode] = Field(default_factory=list)
    groups: list[EpisodeGroup] = Field(default_factory=list)


class EpisodeGraphBuilder:
    """Build bounded connection groups before persistent-memory extraction."""

    def __init__(
        self,
        policy: ConnectionPolicy | None = None,
        validator: EpisodeGroupValidator | None = None,
    ) -> None:
        self.policy = policy or ConnectionPolicy()
        self.validator = validator or EpisodeGroupValidator()

    def build(self, episodes: list[Episode]) -> EpisodeGraph:
        cloned = [
            episode.model_copy(deep=True, update={"connections": [], "connection_group_ids": []})
            for episode in episodes
        ]
        by_id = {episode.episode_id: episode for episode in cloned}
        groups: list[EpisodeGroup] = []

        for group in self._conversation_groups(cloned):
            groups.append(group)
            self._connect_group(
                by_id,
                group,
                relation="conversation_context",
                confidence="high",
                score=1.0,
                bidirectional_verified=True,
                reason="adjacent turns in the same raw conversation",
            )

        semantic_pairs = self.policy.verified_semantic_pairs(cloned)
        pair_map: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for left_id, right_id, score in semantic_pairs:
            pair_map[left_id].append((right_id, score))
            pair_map[right_id].append((left_id, score))
            confidence = self.policy.confidence_for_score(score)
            self._add_directed(
                by_id[left_id],
                right_id,
                "semantic",
                confidence=confidence,
                score=score,
                bidirectional_verified=True,
                reason="mutual top-k semantic overlap",
            )
            self._add_directed(
                by_id[right_id],
                left_id,
                "semantic",
                confidence=confidence,
                score=score,
                bidirectional_verified=True,
                reason="mutual top-k semantic overlap",
            )

        groups.extend(self._semantic_groups(pair_map))
        for group in groups:
            for episode_id in group.episode_ids:
                episode = by_id.get(episode_id)
                if episode and group.group_id not in episode.connection_group_ids:
                    episode.connection_group_ids.append(group.group_id)

        return EpisodeGraph(episodes=cloned, groups=groups)

    def _conversation_groups(self, episodes: list[Episode]) -> list[EpisodeGroup]:
        by_session: dict[str, list[Episode]] = defaultdict(list)
        for episode in episodes:
            by_session[episode.session_id].append(episode)
        groups: list[EpisodeGroup] = []
        for session_id, rows in by_session.items():
            ordered = sorted(rows, key=self._episode_order_key)
            if len(ordered) < 2:
                continue
            group = make_group(
                "conversation_context",
                [episode.episode_id for episode in ordered],
                seed_episode_id=ordered[0].episode_id,
                confidence="high",
                reason=f"same raw conversation: {session_id}",
            )
            group = self.validator.trim_group(group)
            if self.validator.should_keep_group(group):
                groups.append(group)
        return groups

    def _semantic_groups(self, pair_map: dict[str, list[tuple[str, float]]]) -> list[EpisodeGroup]:
        groups: list[EpisodeGroup] = []
        seen: set[tuple[str, ...]] = set()
        for seed_id, neighbors in sorted(pair_map.items()):
            ordered_neighbors = [target for target, _ in sorted(neighbors, key=lambda item: -item[1])]
            episode_ids = [seed_id] + ordered_neighbors
            group = make_group(
                "semantic",
                episode_ids,
                seed_episode_id=seed_id,
                confidence="medium",
                reason="direct mutual semantic neighbors only; no transitive expansion",
            )
            group = self.validator.trim_group(group)
            key = tuple(sorted(group.episode_ids))
            if key in seen or not self.validator.should_keep_group(group):
                continue
            groups.append(group)
            seen.add(key)
        return groups

    def _connect_group(
        self,
        by_id: dict[str, Episode],
        group: EpisodeGroup,
        *,
        relation: str,
        confidence: str,
        score: float,
        bidirectional_verified: bool,
        reason: str,
    ) -> None:
        ordered = group.episode_ids
        if relation == "conversation_context":
            pairs = zip(ordered, ordered[1:])
        else:
            seed = group.seed_episode_id or ordered[0]
            pairs = ((seed, other) for other in ordered if other != seed)
        for left_id, right_id in pairs:
            left = by_id.get(left_id)
            right = by_id.get(right_id)
            if not left or not right:
                continue
            self._add_directed(
                left,
                right_id,
                relation,
                confidence=confidence,
                score=score,
                bidirectional_verified=bidirectional_verified,
                reason=reason,
            )
            self._add_directed(
                right,
                left_id,
                relation,
                confidence=confidence,
                score=score,
                bidirectional_verified=bidirectional_verified,
                reason=reason,
            )

    def _add_directed(
        self,
        episode: Episode,
        target_episode_id: str,
        relation: str,
        *,
        confidence: str,
        score: float,
        bidirectional_verified: bool,
        reason: str,
    ) -> None:
        if target_episode_id == episode.episode_id:
            return
        for existing in episode.connections:
            if existing.target_episode_id == target_episode_id and existing.relation == relation:
                return
        episode.connections.append(
            make_connection(
                target_episode_id,
                relation,
                confidence=confidence,
                score=score,
                reason=reason,
                bidirectional_verified=bidirectional_verified,
            )
        )

    def _episode_order_key(self, episode: Episode) -> tuple[str, int]:
        return (
            episode.timestamp.isoformat() if episode.timestamp else "",
            self._turn_index(episode.turn_id),
        )

    def _turn_index(self, turn_id: str) -> int:
        try:
            return int(str(turn_id).rsplit(":turn:", 1)[1])
        except (IndexError, ValueError):
            return 10**9
