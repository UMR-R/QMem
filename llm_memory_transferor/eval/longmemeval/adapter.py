"""
LongMemEval adapter.

Converts LongMemEval benchmark entries into our system's native formats
(RawConversation, L1SignalLayer) and drives retrieval + generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm_memory_transferor.layers.l0_raw import L0RawLayer, RawConversation, RawMessage


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_benchmark(path: Path) -> list[dict]:
    """Load a LongMemEval JSON file. Returns list of question entries."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data)}")
    return data


# ---------------------------------------------------------------------------
# Session conversion
# ---------------------------------------------------------------------------

def sessions_to_raw_conversations(
    session_ids: list[str],
    sessions: list[list[dict]],
    dates: list[str],
) -> list[RawConversation]:
    """
    Convert a LongMemEval haystack into RawConversation objects.

    Each 'session' in LongMemEval is a list of turns:
      [{"role": "user"|"assistant", "content": "..."}, ...]
    Optional turn-level field: has_answer: true (marks evidence turns).
    """
    convs = []
    for session_id, turns, date in zip(session_ids, sessions, dates):
        messages = []
        for i, turn in enumerate(turns):
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if not content.strip():
                continue
            messages.append(
                RawMessage(
                    msg_id=f"{session_id}_{i}",
                    role=role,
                    content=content,
                    timestamp=date,
                    conversation_id=session_id,
                    platform="longmemeval",
                )
            )
        if messages:
            convs.append(
                RawConversation(
                    conv_id=session_id,
                    platform="longmemeval",
                    title=f"session_{session_id}",
                    messages=messages,
                )
            )
    return convs


def entry_to_conversations(entry: dict) -> tuple[list[RawConversation], list[str]]:
    """
    Given a LongMemEval entry, return:
      - list of RawConversation (the haystack)
      - list of session_ids in the same order
    """
    session_ids: list[str] = entry["haystack_session_ids"]
    sessions: list[list[dict]] = entry["haystack_sessions"]
    dates: list[str] = entry.get("haystack_dates") or [""] * len(session_ids)
    convs = sessions_to_raw_conversations(session_ids, sessions, dates)
    return convs, session_ids


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve_for_entry(
    entry: dict,
    top_k: int = 10,
    granularity: str = "session",
) -> list[dict]:
    """
    Use L0 keyword search to retrieve relevant sessions/turns for a question.

    Returns a list of ranked_items dicts matching LongMemEval's format:
      {"corpus_id": ..., "text": ..., "timestamp": ...}

    granularity: "session" | "turn"
    """
    question = entry["question"]
    session_ids: list[str] = entry["haystack_session_ids"]
    sessions: list[list[dict]] = entry["haystack_sessions"]
    dates: list[str] = entry.get("haystack_dates") or [""] * len(session_ids)

    convs = sessions_to_raw_conversations(session_ids, sessions, dates)
    l0 = L0RawLayer(Path("/tmp/_lme_l0_index"))

    if granularity == "turn":
        return _retrieve_turn_level(convs, session_ids, dates, question, top_k)
    else:
        return _retrieve_session_level(l0, convs, session_ids, dates, question, top_k)


def _retrieve_session_level(
    l0: L0RawLayer,
    convs: list[RawConversation],
    session_ids: list[str],
    dates: list[str],
    question: str,
    top_k: int,
) -> list[dict]:
    """Keyword search at session granularity."""
    date_map = dict(zip(session_ids, dates))

    # Score each session by keyword overlap with question
    question_tokens = set(question.lower().split())
    scored: list[tuple[float, RawConversation]] = []

    for conv in convs:
        text = conv.full_text().lower()
        score = sum(1 for tok in question_tokens if tok in text)
        # Bonus for multi-word phrase match
        if question.lower() in text:
            score += len(question_tokens)
        scored.append((score, conv))

    scored.sort(key=lambda x: x[0], reverse=True)

    ranked_items = []
    seen: set[str] = set()
    for _score, conv in scored:
        if conv.conv_id in seen:
            continue
        seen.add(conv.conv_id)
        ranked_items.append({
            "corpus_id": conv.conv_id,
            "text": conv.full_text()[:2000],
            "timestamp": date_map.get(conv.conv_id, ""),
        })
        if len(ranked_items) >= top_k:
            break

    return ranked_items


def _retrieve_turn_level(
    convs: list[RawConversation],
    session_ids: list[str],
    dates: list[str],
    question: str,
    top_k: int,
) -> list[dict]:
    """Keyword search at turn granularity."""
    question_lower = question.lower()
    question_tokens = set(question_lower.split())
    date_map = dict(zip(session_ids, dates))

    scored: list[tuple[float, str, str, str]] = []
    for conv in convs:
        for i, msg in enumerate(conv.messages):
            text_lower = msg.content.lower()
            score = sum(1 for tok in question_tokens if tok in text_lower)
            if question_lower in text_lower:
                score += len(question_tokens)
            corpus_id = f"{conv.conv_id}_{i + 1}"
            scored.append((score, corpus_id, msg.content, date_map.get(conv.conv_id, "")))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"corpus_id": cid, "text": text[:500], "timestamp": ts}
        for _, cid, text, ts in scored[:top_k]
    ]


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def format_retrieved_context(
    entry: dict,
    ranked_items: list[dict],
    top_k: int = 5,
    history_format: str = "nl",
) -> str:
    """
    Format top-K retrieved items as a readable context string for the LLM.

    history_format: "nl" (natural language) | "json"
    """
    items = ranked_items[:top_k]
    parts = []

    session_ids: list[str] = entry["haystack_session_ids"]
    sessions: list[list[dict]] = entry["haystack_sessions"]
    dates: list[str] = entry.get("haystack_dates") or [""] * len(session_ids)

    session_map = {sid: (sess, date) for sid, sess, date in zip(session_ids, sessions, dates)}

    for item in items:
        corpus_id = item["corpus_id"]
        timestamp = item.get("timestamp", "")

        # Try to get full session text from original data
        base_session_id = corpus_id.split("_")[0] if "_" in corpus_id else corpus_id
        if base_session_id in session_map:
            sess_turns, date = session_map[base_session_id]
            if history_format == "json":
                text = json.dumps(sess_turns, ensure_ascii=False)
            else:
                turn_lines = []
                for turn in sess_turns:
                    role = turn.get("role", "user").capitalize()
                    turn_lines.append(f"{role}: {turn.get('content', '')}")
                text = "\n".join(turn_lines)
        else:
            text = item.get("text", "")

        date_str = f" [{timestamp}]" if timestamp else ""
        parts.append(f"=== Session {corpus_id}{date_str} ===\n{text}")

    return "\n\n".join(parts)


def format_full_history(entry: dict, history_format: str = "nl") -> str:
    """Format the entire haystack as context (full-history baseline)."""
    session_ids: list[str] = entry["haystack_session_ids"]
    sessions: list[list[dict]] = entry["haystack_sessions"]
    dates: list[str] = entry.get("haystack_dates") or [""] * len(session_ids)

    parts = []
    for sid, turns, date in zip(session_ids, sessions, dates):
        date_str = f" [{date}]" if date else ""
        if history_format == "json":
            text = json.dumps(turns, ensure_ascii=False)
        else:
            turn_lines = []
            for turn in turns:
                role = turn.get("role", "user").capitalize()
                turn_lines.append(f"{role}: {turn.get('content', '')}")
            text = "\n".join(turn_lines)
        parts.append(f"=== Session {sid}{date_str} ===\n{text}")

    return "\n\n".join(parts)
