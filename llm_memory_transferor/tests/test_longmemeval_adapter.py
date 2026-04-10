"""Tests for the LongMemEval adapter (no LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval.longmemeval.adapter import (
    entry_to_conversations,
    format_full_history,
    format_retrieved_context,
    load_benchmark,
    retrieve_for_entry,
    sessions_to_raw_conversations,
)
from eval.longmemeval.retrieval_runner import compute_retrieval_metrics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_SESSIONS = [
    [
        {"role": "user", "content": "I am a machine learning engineer working on NLP."},
        {"role": "assistant", "content": "That sounds fascinating! What kind of NLP tasks?"},
        {"role": "user", "content": "Mostly text classification and named entity recognition.", "has_answer": True},
    ],
    [
        {"role": "user", "content": "I prefer concise responses without bullet points."},
        {"role": "assistant", "content": "Understood, I'll keep things brief."},
    ],
    [
        {"role": "user", "content": "My project deadline is March 2025."},
        {"role": "assistant", "content": "I'll note that down."},
        {"role": "user", "content": "We need to ship the classification model by then.", "has_answer": True},
    ],
]

MOCK_ENTRY = {
    "question_id": "test_001",
    "question_type": "single-session-user",
    "question": "What kind of NLP tasks does the user work on?",
    "answer": "Text classification and named entity recognition.",
    "question_date": "2024-06-01",
    "haystack_session_ids": ["sess_a", "sess_b", "sess_c"],
    "haystack_sessions": MOCK_SESSIONS,
    "haystack_dates": ["2024-01-01", "2024-02-01", "2024-03-01"],
    "answer_session_ids": ["sess_a"],
}

MOCK_ABSTENTION_ENTRY = {
    **MOCK_ENTRY,
    "question_id": "test_002_abs",
    "question": "What is the user's favorite color?",
    "answer": "The answer is not in the history.",
    "answer_session_ids": [],
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def test_load_benchmark(tmp_path):
    p = tmp_path / "bench.json"
    p.write_text(json.dumps([MOCK_ENTRY, MOCK_ABSTENTION_ENTRY]))
    data = load_benchmark(p)
    assert len(data) == 2
    assert data[0]["question_id"] == "test_001"


def test_load_benchmark_invalid(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError, match="JSON array"):
        load_benchmark(p)


# ---------------------------------------------------------------------------
# Session conversion
# ---------------------------------------------------------------------------

def test_sessions_to_raw_conversations():
    session_ids = ["s1", "s2"]
    sessions = [
        [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}],
        [{"role": "user", "content": "How are you?"}],
    ]
    dates = ["2024-01-01", "2024-02-01"]
    convs = sessions_to_raw_conversations(session_ids, sessions, dates)
    assert len(convs) == 2
    assert convs[0].conv_id == "s1"
    assert len(convs[0].messages) == 2
    assert convs[0].messages[0].role == "user"
    assert convs[0].messages[0].timestamp == "2024-01-01"


def test_sessions_to_raw_conversations_skips_empty():
    sessions = [
        [{"role": "user", "content": ""}, {"role": "assistant", "content": "Hi"}],
    ]
    convs = sessions_to_raw_conversations(["s1"], sessions, ["2024-01-01"])
    # Should skip the empty-content user message
    assert all(m.content.strip() for conv in convs for m in conv.messages)


def test_entry_to_conversations():
    convs, sids = entry_to_conversations(MOCK_ENTRY)
    assert len(convs) == 3
    assert sids == ["sess_a", "sess_b", "sess_c"]
    assert convs[0].conv_id == "sess_a"


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def test_retrieve_for_entry_returns_ranked_items():
    items = retrieve_for_entry(MOCK_ENTRY, top_k=10)
    assert isinstance(items, list)
    assert len(items) > 0
    for item in items:
        assert "corpus_id" in item
        assert "text" in item
        assert "timestamp" in item


def test_retrieve_finds_relevant_session():
    """The question is about NLP tasks — sess_a should rank first."""
    items = retrieve_for_entry(MOCK_ENTRY, top_k=3)
    top_corpus_id = items[0]["corpus_id"]
    # sess_a contains "NLP" and "classification", most relevant to the question
    assert top_corpus_id == "sess_a"


def test_retrieve_turn_granularity():
    items = retrieve_for_entry(MOCK_ENTRY, top_k=10, granularity="turn")
    assert len(items) > 0
    # Turn-level corpus IDs have format {session_id}_{turn_index}
    assert "_" in items[0]["corpus_id"]


def test_retrieve_limits_results():
    items = retrieve_for_entry(MOCK_ENTRY, top_k=2)
    assert len(items) <= 2


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def test_retrieval_metrics_perfect():
    """When the correct session is ranked first, recall_any@1 = 1."""
    ranked_items = [
        {"corpus_id": "sess_a", "text": "...", "timestamp": ""},
        {"corpus_id": "sess_b", "text": "...", "timestamp": ""},
    ]
    metrics = compute_retrieval_metrics(ranked_items, ["sess_a"], MOCK_ENTRY)
    assert metrics["recall_any@1"] == 1.0
    assert metrics["recall_all@1"] == 1.0


def test_retrieval_metrics_miss():
    """When correct session is not in top-1, recall_any@1 = 0."""
    ranked_items = [
        {"corpus_id": "sess_b", "text": "...", "timestamp": ""},
        {"corpus_id": "sess_c", "text": "...", "timestamp": ""},
        {"corpus_id": "sess_a", "text": "...", "timestamp": ""},
    ]
    metrics = compute_retrieval_metrics(ranked_items, ["sess_a"], MOCK_ENTRY)
    assert metrics["recall_any@1"] == 0.0
    assert metrics["recall_any@3"] == 1.0  # found within top-3


def test_retrieval_metrics_multi_answer():
    """recall_all@k requires ALL answer sessions in top-k."""
    ranked_items = [
        {"corpus_id": "sess_a", "text": "", "timestamp": ""},
        {"corpus_id": "sess_b", "text": "", "timestamp": ""},
        {"corpus_id": "sess_c", "text": "", "timestamp": ""},
    ]
    metrics = compute_retrieval_metrics(
        ranked_items, ["sess_a", "sess_c"], MOCK_ENTRY
    )
    assert metrics["recall_any@1"] == 1.0   # sess_a is in top-1
    assert metrics["recall_all@1"] == 0.0   # sess_c is not
    assert metrics["recall_all@3"] == 1.0   # both in top-3


def test_retrieval_metrics_ndcg_perfect():
    """NDCG@1 = 1.0 when answer is ranked first."""
    ranked_items = [{"corpus_id": "sess_a", "text": "", "timestamp": ""}]
    metrics = compute_retrieval_metrics(ranked_items, ["sess_a"], MOCK_ENTRY)
    assert abs(metrics["ndcg@1"] - 1.0) < 1e-6


def test_retrieval_metrics_empty_answer():
    """No answer sessions → all metrics = 0.0."""
    ranked_items = [{"corpus_id": "sess_a", "text": "", "timestamp": ""}]
    metrics = compute_retrieval_metrics(ranked_items, [], MOCK_ENTRY)
    assert metrics["recall_any@1"] == 0.0
    assert metrics["ndcg@1"] == 0.0


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def test_format_retrieved_context():
    ranked_items = [
        {"corpus_id": "sess_a", "text": "NLP tasks...", "timestamp": "2024-01-01"},
        {"corpus_id": "sess_b", "text": "Preferences...", "timestamp": "2024-02-01"},
    ]
    ctx = format_retrieved_context(MOCK_ENTRY, ranked_items, top_k=2)
    assert "sess_a" in ctx
    assert "2024-01-01" in ctx
    assert "NLP" in ctx  # content from full session (not just ranked_items text)


def test_format_retrieved_context_limits_top_k():
    ranked_items = [
        {"corpus_id": f"sess_{i}", "text": f"text {i}", "timestamp": ""} for i in range(10)
    ]
    ctx = format_retrieved_context(MOCK_ENTRY, ranked_items, top_k=2)
    # Only first 2 should appear (within haystack)
    assert ctx.count("=== Session") <= 2


def test_format_full_history():
    ctx = format_full_history(MOCK_ENTRY)
    assert "sess_a" in ctx
    assert "sess_b" in ctx
    assert "sess_c" in ctx
    assert "machine learning engineer" in ctx
    assert "2024-01-01" in ctx


def test_format_full_history_json():
    ctx = format_full_history(MOCK_ENTRY, history_format="json")
    assert "role" in ctx  # JSON contains role field
    assert "content" in ctx


# ---------------------------------------------------------------------------
# Abstention handling
# ---------------------------------------------------------------------------

def test_abstention_entry_has_no_answer_sessions():
    assert MOCK_ABSTENTION_ENTRY["question_id"].endswith("_abs")
    assert MOCK_ABSTENTION_ENTRY["answer_session_ids"] == []


def test_retrieval_on_abstention_still_returns_items():
    """Retrieval should still run on abstention entries (no crash)."""
    items = retrieve_for_entry(MOCK_ABSTENTION_ENTRY, top_k=5)
    assert isinstance(items, list)
