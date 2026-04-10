"""Tests for L1 External Memory Signals."""

import json
import tempfile
from pathlib import Path

import pytest
from llm_memory_transferor.layers.l1_signals import L1SignalLayer


@pytest.fixture
def l1():
    return L1SignalLayer()


def test_load_json_memory(l1, tmp_path):
    p = tmp_path / "memory.json"
    p.write_text(json.dumps({"memory": "I prefer concise responses."}))
    sigs = l1.load_file(p, platform="chatgpt")
    assert len(sigs) >= 1
    assert any(s.signal_type == "saved_memory" for s in sigs)


def test_load_json_profile(l1, tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps({"profile": "Alice is an ML engineer."}))
    sigs = l1.load_file(p, platform="chatgpt")
    assert any(s.signal_type == "profile" for s in sigs)


def test_load_markdown(l1, tmp_path):
    p = tmp_path / "memory.md"
    p.write_text("# Memory\nUser prefers bullet points.")
    sigs = l1.load_file(p, platform="claude")
    assert len(sigs) == 1
    assert sigs[0].signal_type == "saved_memory"


def test_combined_text(l1, tmp_path):
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"memory": "Prefers English.", "summary": "ML expert."}))
    l1.load_file(p, platform="gpt")
    text = l1.combined_text()
    assert "SAVED_MEMORY" in text.upper() or "saved_memory" in text.lower()


def test_by_type(l1, tmp_path):
    p = tmp_path / "data.json"
    p.write_text(json.dumps({
        "memory": "Remember this.",
        "preferences": {"style": "concise"},
    }))
    l1.load_file(p, platform="test")
    memories = l1.by_type("saved_memory")
    assert len(memories) >= 1
