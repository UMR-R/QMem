"""Chunk builders for retrieval-only benchmarks.

These helpers are additive and do not modify the canonical raw/episode storage.
"""

from __future__ import annotations

from typing import Any

from llm_memory_transferor.layers.l0_raw import RawConversation
from llm_memory_transferor.models import EpisodicMemory


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


def build_raw_session_documents(
    conversations: list[RawConversation],
    *,
    user_only: bool = True,
) -> list[dict[str, Any]]:
    """Build one retrieval document per raw session.

    MemPalace-style default is to concatenate user turns only.
    """
    documents: list[dict[str, Any]] = []
    for idx, conv in enumerate(conversations):
        messages = conv.user_messages() if user_only else conv.messages
        text = "\n".join(_normalize_text(msg.content) for msg in messages if msg.content.strip())
        if not text.strip():
            continue
        turn_refs = [turn.turn_id for turn in conv.turns]
        documents.append(
            {
                "doc_id": f"raw_session:{conv.conv_id}:{idx}",
                "doc_type": "raw_session",
                "corpus_id": conv.conv_id,
                "conversation_id": conv.conv_id,
                "timestamp": conv.end_time.isoformat() if conv.end_time else "",
                "role_scope": "user_only" if user_only else "all_turns",
                "text": text,
                "turn_refs": turn_refs,
            }
        )
    return documents


def build_raw_turn_documents(
    conversations: list[RawConversation],
    *,
    user_only: bool = True,
) -> list[dict[str, Any]]:
    """Build one retrieval document per raw message/turn candidate.

    MemPalace-style default keeps user turns only for QA retrieval.
    """
    documents: list[dict[str, Any]] = []
    for conv_idx, conv in enumerate(conversations):
        for idx, msg in enumerate(conv.messages):
            if user_only and str(msg.role or "").strip().lower() != "user":
                continue
            text = _normalize_text(msg.content)
            if not text:
                continue
            documents.append(
                {
                    "doc_id": f"raw_turn:{conv.conv_id}:{conv_idx}:{idx}",
                    "doc_type": "raw_turn",
                    "corpus_id": conv.conv_id,
                    "conversation_id": conv.conv_id,
                    "timestamp": msg.timestamp,
                    "role_scope": "user_only" if user_only else "all_turns",
                    "text": text,
                    "turn_refs": [f"{conv.conv_id}:turn:{idx}"],
                }
            )
    return documents


def build_episode_documents(episodes: list[EpisodicMemory]) -> list[dict[str, Any]]:
    """Build one retrieval document per episode."""
    documents: list[dict[str, Any]] = []
    for episode in episodes:
        pieces = [
            episode.topic,
            episode.summary,
            " ".join(episode.topics_covered),
            " ".join(episode.key_decisions),
            " ".join(episode.open_issues),
        ]
        text = "\n".join(_normalize_text(piece) for piece in pieces if _normalize_text(piece))
        if not text:
            continue
        documents.append(
            {
                "doc_id": f"episode:{episode.episode_id}",
                "doc_type": "episode",
                "corpus_id": episode.conv_id,
                "conversation_id": episode.conv_id,
                "episode_id": episode.episode_id,
                "timestamp": episode.time_range_end.isoformat() if episode.time_range_end else (
                    episode.time_range_start.isoformat() if episode.time_range_start else ""
                ),
                "text": text,
                "turn_refs": list(episode.turn_refs),
                "topic": episode.topic,
                "summary": episode.summary,
                "related_project": episode.related_project,
            }
        )
    return documents
