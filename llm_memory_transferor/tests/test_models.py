"""Tests for memory models."""

import pytest
from llm_memory_transferor.models import (
    EpisodicMemory,
    PreferenceMemory,
    ProfileMemory,
    ProjectMemory,
    WorkflowMemory,
)


def test_profile_memory_defaults():
    p = ProfileMemory()
    assert p.version == 1
    assert p.name_or_alias == ""
    assert p.domain_background == []
    assert p.evidence_links == []


def test_profile_memory_touch():
    p = ProfileMemory()
    v0 = p.version
    updated_before = p.updated_at
    p.touch()
    assert p.version == v0 + 1
    assert p.updated_at >= updated_before


def test_profile_memory_markdown():
    p = ProfileMemory(
        name_or_alias="Alice",
        role_identity="ML Engineer",
        domain_background=["machine learning", "NLP"],
        common_languages=["Python", "English"],
    )
    md = p.to_markdown()
    assert "Alice" in md
    assert "ML Engineer" in md
    assert "machine learning" in md


def test_preference_memory_markdown():
    pref = PreferenceMemory(
        language_preference="English",
        response_granularity="concise",
        forbidden_expressions=["As an AI", "Certainly!"],
    )
    md = pref.to_markdown()
    assert "English" in md
    assert "concise" in md
    assert "As an AI" in md


def test_project_memory_markdown():
    proj = ProjectMemory(
        project_name="Test Project",
        project_goal="Build something great",
        current_stage="MVP",
        next_actions=["Write tests", "Deploy"],
    )
    md = proj.to_markdown()
    assert "Test Project" in md
    assert "MVP" in md
    assert "Write tests" in md


def test_workflow_memory_markdown():
    wf = WorkflowMemory(
        workflow_name="Code Review",
        trigger_condition="When PR is ready",
        typical_steps=["Read diff", "Check tests", "Leave comments"],
        reuse_frequency="daily",
    )
    md = wf.to_markdown()
    assert "Code Review" in md
    assert "Read diff" in md


def test_episodic_memory_markdown():
    ep = EpisodicMemory(
        episode_id="abc123",
        topic="Discussion about testing strategy",
        summary="Agreed to use pytest with real database.",
        key_decisions=["Use pytest", "No mocking DB"],
        open_issues=["Coverage threshold TBD"],
        related_project="Test Project",
    )
    md = ep.to_markdown()
    assert "Discussion about testing strategy" in md
    assert "Use pytest" in md
    assert "Coverage threshold TBD" in md


def test_evidence_link():
    p = ProfileMemory()
    p.add_evidence("chat_history", "conv_001", "User said they work at Acme Corp")
    assert len(p.evidence_links) == 1
    assert p.evidence_links[0].source_type == "chat_history"
    assert p.evidence_links[0].source_id == "conv_001"


def test_conflict_log():
    p = ProfileMemory(name_or_alias="Alice")
    p.record_conflict("name_or_alias", "Alice", "Alicia", "l1_signal")
    assert len(p.conflict_log) == 1
    assert p.conflict_log[0]["field"] == "name_or_alias"
    assert p.conflict_log[0]["old_value"] == "Alice"
