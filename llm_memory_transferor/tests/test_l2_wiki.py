"""Tests for L2 Managed MWiki."""

import pytest
from llm_memory_transferor.layers.l2_wiki import L2Wiki
from llm_memory_transferor.models import (
    EpisodicMemory,
    PreferenceMemory,
    ProfileMemory,
    ProjectMemory,
    WorkflowMemory,
)


@pytest.fixture
def wiki(tmp_path):
    return L2Wiki(tmp_path / "wiki")


def test_profile_roundtrip(wiki):
    profile = ProfileMemory(
        name_or_alias="Bob",
        role_identity="Product Manager",
        common_languages=["English", "Mandarin"],
    )
    wiki.save_profile(profile)
    loaded = wiki.load_profile()
    assert loaded is not None
    assert loaded.name_or_alias == "Bob"
    assert loaded.role_identity == "Product Manager"


def test_preferences_roundtrip(wiki):
    prefs = PreferenceMemory(
        language_preference="English",
        response_granularity="concise",
        forbidden_expressions=["As an AI"],
    )
    wiki.save_preferences(prefs)
    loaded = wiki.load_preferences()
    assert loaded is not None
    assert loaded.language_preference == "English"
    assert "As an AI" in loaded.forbidden_expressions


def test_project_roundtrip(wiki):
    proj = ProjectMemory(
        project_name="Alpha Project",
        project_goal="Ship by Q3",
        current_stage="Design",
        next_actions=["Write spec", "Review with team"],
    )
    wiki.save_project(proj)
    loaded = wiki.load_project("Alpha Project")
    assert loaded is not None
    assert loaded.project_goal == "Ship by Q3"
    assert "Write spec" in loaded.next_actions


def test_list_projects(wiki):
    for name in ["Project A", "Project B", "Project C"]:
        wiki.save_project(ProjectMemory(project_name=name))
    projects = wiki.list_projects()
    names = {p.project_name for p in projects}
    assert "Project A" in names
    assert "Project C" in names


def test_workflow_roundtrip(wiki):
    wfs = [
        WorkflowMemory(
            workflow_name="Code Review",
            typical_steps=["Read", "Comment", "Approve"],
            reuse_frequency="daily",
        )
    ]
    wiki.save_workflows(wfs)
    loaded = wiki.load_workflows()
    assert len(loaded) == 1
    assert loaded[0].workflow_name == "Code Review"
    assert loaded[0].reuse_frequency == "daily"


def test_episode_roundtrip(wiki):
    ep = EpisodicMemory(
        episode_id="ep001",
        topic="Planning session",
        summary="Agreed on Q3 deadline.",
        key_decisions=["Ship by Q3"],
        related_project="Alpha Project",
    )
    wiki.save_episode(ep)
    episodes = wiki.list_episodes()
    assert len(episodes) >= 1
    assert any(e.episode_id == "ep001" for e in episodes)


def test_episode_filter_by_project(wiki):
    wiki.save_episode(EpisodicMemory(episode_id="e1", topic="A", related_project="P1"))
    wiki.save_episode(EpisodicMemory(episode_id="e2", topic="B", related_project="P2"))
    p1_eps = wiki.list_episodes(project="P1")
    assert all(e.related_project == "P1" for e in p1_eps)


def test_rebuild_index(wiki):
    wiki.save_profile(ProfileMemory(name_or_alias="Alice"))
    wiki.save_project(ProjectMemory(project_name="MyProj"))
    index = wiki.rebuild_index()
    assert index["has_profile"] is True
    assert "MyProj" in index["projects"]


def test_change_log(wiki):
    wiki.save_profile(ProfileMemory(name_or_alias="Alice"))
    wiki.save_profile(ProfileMemory(name_or_alias="Alice Updated"))
    history = wiki.change_history()
    assert len(history) >= 2
    types = {h["entity_type"] for h in history}
    assert "profile" in types


def test_markdown_files_written(wiki):
    wiki.save_profile(ProfileMemory(name_or_alias="Alice"))
    assert (wiki.wiki_dir / "profile.md").exists()

    wiki.save_preferences(PreferenceMemory(language_preference="English"))
    assert (wiki.wiki_dir / "preferences.md").exists()

    wiki.save_project(ProjectMemory(project_name="TestProj"))
    assert (wiki.wiki_dir / "projects" / "testproj.md").exists()
