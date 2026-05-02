from __future__ import annotations

import hashlib
import re

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
                        keywords=_extract_keywords(text),
                        source_turn_text=text,
                    )
                )
        return episodes


def _extract_keywords(text: str) -> list[str]:
    """Extract lightweight entity/topic hints for linking and project naming."""

    keywords: list[str] = []
    normalized = text.replace("\n", " ")

    for pattern, flags in (
        (r"\b[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9][A-Za-z0-9-]*\b", 0),
        (r"\b[A-Z]{2,}(?:\s+[A-Z]{2,}){0,2}\b", 0),
        (
            r"\b[A-Za-z0-9][A-Za-z0-9-]{1,}\s+(?:binding|prediction|benchmark|proposal|schema|system|plugin|memory)\b",
            re.IGNORECASE,
        ),
        (
            r"\b(?:binding|prediction|benchmark|proposal|schema|system|plugin|memory)\s+[A-Za-z0-9][A-Za-z0-9-]{1,}\b",
            re.IGNORECASE,
        ),
    ):
        for match in re.findall(pattern, normalized, flags=flags):
            _append_keyword(keywords, " ".join(str(match).split()))

    for pattern in (
        r"把\s*([^，。；,.!?]{2,80}?)\s*(?:这个)?(?:项目|方向|主题|proposal|论文)\s*(?:写成|整理成|做成|设计成)",
        r"(?:围绕|关于)\s*([^，。；,.!?]{2,80}?)\s*(?:这个)?(?:项目|方向|主题|proposal|论文)",
    ):
        for match in re.findall(pattern, normalized, flags=re.IGNORECASE):
            _append_keyword(keywords, _clean_keyword(match))

    return keywords[:12]


def _append_keyword(keywords: list[str], keyword: str) -> None:
    keyword = _clean_keyword(keyword)
    if keyword.lower() in {"user", "assistant", "system"}:
        return
    if keyword and keyword.lower() not in {item.lower() for item in keywords}:
        keywords.append(keyword)


def _clean_keyword(keyword: str) -> str:
    keyword = re.sub(r"^(?:我想|我们想|想要|继续|上次那个)\s*", "", str(keyword).strip())
    keyword = re.sub(r"\s+", " ", keyword)
    return keyword.strip(" ：:，。；,.!?")
