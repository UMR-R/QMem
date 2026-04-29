from __future__ import annotations

import re
from dataclasses import dataclass

from memory_transferor.memory_models import Episode


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "what",
    "when", "then", "than", "user", "assistant", "please", "should", "could",
    "用户", "助手", "这个", "那个", "我们", "你们", "他们", "一个", "一些", "可以",
    "需要", "进行", "关于", "现在", "然后", "就是", "什么",
}


@dataclass(frozen=True)
class ConnectionPolicyConfig:
    semantic_min_score: float = 0.24
    semantic_min_overlap: int = 3
    mutual_top_k: int = 3
    max_cross_session_edges_per_episode: int = 3


class ConnectionPolicy:
    """Deterministic validation policy for episode-to-episode links."""

    def __init__(self, config: ConnectionPolicyConfig | None = None) -> None:
        self.config = config or ConnectionPolicyConfig()

    def terms_for_episode(self, episode: Episode) -> set[str]:
        text = " ".join(
            [
                episode.summary,
                episode.source_turn_text,
                " ".join(episode.keywords),
            ]
        )
        return self._tokenize(text)

    def similarity(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        overlap = len(left & right)
        if overlap < self.config.semantic_min_overlap:
            return 0.0
        return overlap / max(1, min(len(left), len(right)))

    def semantic_candidates(
        self,
        episodes: list[Episode],
    ) -> dict[str, list[tuple[str, float]]]:
        terms = {episode.episode_id: self.terms_for_episode(episode) for episode in episodes}
        by_id = {episode.episode_id: episode for episode in episodes}
        candidates: dict[str, list[tuple[str, float]]] = {episode.episode_id: [] for episode in episodes}
        for index, left in enumerate(episodes):
            for right in episodes[index + 1:]:
                if left.session_id == right.session_id:
                    continue
                score = self.similarity(terms[left.episode_id], terms[right.episode_id])
                if score < self.config.semantic_min_score:
                    continue
                candidates[left.episode_id].append((right.episode_id, score))
                candidates[right.episode_id].append((left.episode_id, score))
        for episode_id in candidates:
            candidates[episode_id] = sorted(
                candidates[episode_id],
                key=lambda item: (
                    -item[1],
                    (by_id[item[0]].timestamp or by_id[episode_id].timestamp).isoformat()
                    if (by_id[item[0]].timestamp or by_id[episode_id].timestamp)
                    else "",
                    item[0],
                ),
            )[: self.config.max_cross_session_edges_per_episode]
        return candidates

    def verified_semantic_pairs(self, episodes: list[Episode]) -> list[tuple[str, str, float]]:
        candidates = self.semantic_candidates(episodes)
        top_sets = {
            episode_id: {target for target, _ in rows[: self.config.mutual_top_k]}
            for episode_id, rows in candidates.items()
        }
        pairs: list[tuple[str, str, float]] = []
        seen: set[tuple[str, str]] = set()
        for source, rows in candidates.items():
            for target, score in rows[: self.config.mutual_top_k]:
                key = tuple(sorted([source, target]))
                if key in seen:
                    continue
                if target in top_sets.get(source, set()) and source in top_sets.get(target, set()):
                    pairs.append((key[0], key[1], score))
                    seen.add(key)
        return pairs

    def confidence_for_score(self, score: float) -> str:
        if score >= 0.5:
            return "high"
        if score >= 0.32:
            return "medium"
        return "low"

    def _tokenize(self, text: str) -> set[str]:
        normalized = text.lower()
        tokens = {
            token
            for token in re.findall(r"[a-z0-9][a-z0-9_\-]{1,}", normalized)
            if token not in _STOPWORDS and len(token) >= 2
        }
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            if chunk in _STOPWORDS:
                continue
            if len(chunk) <= 6:
                tokens.add(chunk)
            for size in (2, 3, 4):
                if len(chunk) < size:
                    continue
                for index in range(0, len(chunk) - size + 1):
                    piece = chunk[index:index + size]
                    if piece not in _STOPWORDS:
                        tokens.add(piece)
        return tokens
