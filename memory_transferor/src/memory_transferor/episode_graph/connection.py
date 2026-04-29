from __future__ import annotations

from hashlib import sha1

from memory_transferor.memory_models import EpisodeConnection, EpisodeGroup


def make_connection(
    target_episode_id: str,
    relation: str,
    *,
    confidence: str = "medium",
    score: float = 0.0,
    reason: str = "",
    bidirectional_verified: bool = False,
) -> EpisodeConnection:
    return EpisodeConnection(
        target_episode_id=target_episode_id,
        relation=relation,
        confidence=confidence,
        score=round(float(score), 4),
        reason=reason,
        bidirectional_verified=bidirectional_verified,
    )


def stable_group_id(relation: str, episode_ids: list[str]) -> str:
    seed = relation + ":" + "|".join(sorted(dict.fromkeys(episode_ids)))
    return f"grp_{sha1(seed.encode('utf-8')).hexdigest()[:10]}"


def make_group(
    relation: str,
    episode_ids: list[str],
    *,
    seed_episode_id: str = "",
    confidence: str = "medium",
    reason: str = "",
) -> EpisodeGroup:
    clean_ids = list(dict.fromkeys(episode_ids))
    return EpisodeGroup(
        group_id=stable_group_id(relation, clean_ids),
        relation=relation,
        episode_ids=clean_ids,
        seed_episode_id=seed_episode_id,
        confidence=confidence,
        reason=reason,
    )
