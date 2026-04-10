"""Tests for L3 Schema and Policy Layer."""

import pytest
from llm_memory_transferor.layers.l3_schema import (
    ConflictResolution,
    L3Schema,
    UpgradeDecision,
)
from llm_memory_transferor.models import PreferenceMemory


@pytest.fixture
def schema():
    return L3Schema()


def test_is_worth_extracting_noise(schema):
    assert not schema.is_worth_extracting("ok")
    assert not schema.is_worth_extracting("thanks")
    assert not schema.is_worth_extracting("")


def test_is_worth_extracting_content(schema):
    assert schema.is_worth_extracting("I prefer concise responses without bullet points.")
    assert schema.is_worth_extracting("Working on a new ML pipeline for recommendation systems.")


def test_preference_upgrade_insufficient_evidence(schema):
    prefs = PreferenceMemory()
    decision = schema.should_upgrade_preference("concise", prefs, occurrence_count=1)
    assert decision == UpgradeDecision.ACCUMULATE


def test_preference_upgrade_sufficient_evidence(schema):
    prefs = PreferenceMemory()
    decision = schema.should_upgrade_preference("concise", prefs, occurrence_count=2)
    assert decision == UpgradeDecision.UPGRADE


def test_preference_upgrade_forbidden(schema):
    prefs = PreferenceMemory(forbidden_expressions=["bullet points"])
    decision = schema.should_upgrade_preference("bullet points", prefs, occurrence_count=5)
    assert decision == UpgradeDecision.SKIP


def test_workflow_upgrade_threshold(schema):
    assert schema.should_upgrade_workflow("review", 2) == UpgradeDecision.ACCUMULATE
    assert schema.should_upgrade_workflow("review", 3) == UpgradeDecision.UPGRADE


def test_profile_field_upgrade_high_stakes(schema):
    assert schema.should_upgrade_profile_field("name_or_alias") == UpgradeDecision.USER_CONFIRM
    assert schema.should_upgrade_profile_field("role_identity") == UpgradeDecision.USER_CONFIRM


def test_profile_field_upgrade_normal(schema):
    assert schema.should_upgrade_profile_field("primary_task_types") == UpgradeDecision.UPGRADE


def test_conflict_resolution_list_merge(schema):
    result = schema.resolve_conflict("project", "key_terms", ["a"], ["b"], "user")
    assert result == ConflictResolution.MERGE


def test_conflict_resolution_preference_new(schema):
    result = schema.resolve_conflict("preference", "language_preference", "en", "zh", "user")
    assert result == ConflictResolution.USE_NEW


def test_conflict_resolution_project_stage(schema):
    result = schema.resolve_conflict("project", "current_stage", "design", "dev", "user")
    assert result == ConflictResolution.USE_NEW


def test_is_temporary(schema):
    assert schema.is_temporary("Just do this for now")
    assert schema.is_temporary("Tonight I need this format")
    assert not schema.is_temporary("I always prefer concise outputs")


def test_classify_episode(schema):
    from llm_memory_transferor.models import EpisodicMemory
    ep = EpisodicMemory(topic="x", summary="y", key_decisions=["decided something"])
    assert schema.classify_episode(ep) == "decision_record"

    ep2 = EpisodicMemory(topic="x", summary="y", related_project="MyProj")
    assert schema.classify_episode(ep2) == "project_update"

    ep3 = EpisodicMemory(topic="x", summary="")
    assert schema.classify_episode(ep3) == "noise"


def test_flag_sensitive(schema):
    flags = schema.flag_sensitive("My email is alice@example.com")
    assert "email" in flags

    flags2 = schema.flag_sensitive("The password is hunter2")
    assert "password_mention" in flags2

    flags3 = schema.flag_sensitive("Normal text about programming.")
    assert flags3 == []
