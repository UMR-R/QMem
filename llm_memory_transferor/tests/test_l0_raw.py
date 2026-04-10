"""Tests for L0 Raw Evidence Layer."""

import json
import tempfile
from pathlib import Path

import pytest
from llm_memory_transferor.layers.l0_raw import L0RawLayer, RawConversation


@pytest.fixture
def l0(tmp_path):
    return L0RawLayer(tmp_path / "raw_index")


def make_chatgpt_json(path: Path) -> None:
    data = [
        {
            "id": "conv1",
            "title": "Test conversation",
            "platform": "chatgpt",
            "messages": [
                {"id": "m1", "role": "user", "content": "Hello, I am an ML engineer."},
                {"id": "m2", "role": "assistant", "content": "Nice to meet you!"},
            ],
        }
    ]
    path.write_text(json.dumps(data), encoding="utf-8")


def make_text_conversation(path: Path) -> None:
    path.write_text(
        "User:\nHello world.\n\nAssistant:\nHi there!\n\nUser:\nI work on NLP projects.\n",
        encoding="utf-8",
    )


def test_parse_json(l0, tmp_path):
    p = tmp_path / "export.json"
    make_chatgpt_json(p)
    convs = l0.ingest_file(p)
    assert len(convs) == 1
    assert convs[0].conv_id == "conv1"
    assert len(convs[0].messages) == 2
    assert convs[0].messages[0].role == "user"
    assert "ML engineer" in convs[0].messages[0].content


def test_parse_text(l0, tmp_path):
    p = tmp_path / "chat.txt"
    make_text_conversation(p)
    convs = l0.ingest_file(p)
    assert len(convs) == 1
    msgs = convs[0].messages
    assert any("NLP" in m.content for m in msgs)


def test_parse_jsonl(l0, tmp_path):
    p = tmp_path / "export.jsonl"
    lines = [
        json.dumps({"id": f"c{i}", "messages": [
            {"id": f"m{i}", "role": "user", "content": f"Message {i}"}
        ]})
        for i in range(3)
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    convs = l0.ingest_file(p)
    assert len(convs) == 3


def test_search(l0, tmp_path):
    p = tmp_path / "export.json"
    make_chatgpt_json(p)
    convs = l0.ingest_file(p)
    results = l0.search(convs, "ML engineer")
    assert len(results) == 1
    conv, msg = results[0]
    assert "ML engineer" in msg.content


def test_word_count(l0, tmp_path):
    p = tmp_path / "export.json"
    make_chatgpt_json(p)
    convs = l0.ingest_file(p)
    assert convs[0].word_count() > 0


def test_topic_chunks(l0, tmp_path):
    p = tmp_path / "export.json"
    make_chatgpt_json(p)
    convs = l0.ingest_file(p)
    chunks = list(l0.topic_chunks(convs, ["ML engineer"]))
    assert len(chunks) >= 1
    topic, text = chunks[0]
    assert topic == "ML engineer"
    assert "ML engineer" in text


def test_unsupported_format(l0, tmp_path):
    p = tmp_path / "file.csv"
    p.write_text("col1,col2\nval1,val2")
    with pytest.raises(ValueError, match="Unsupported"):
        l0.ingest_file(p)
