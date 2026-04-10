"""Tests for exporters."""

import json
from pathlib import Path

import pytest
from llm_memory_transferor.exporters.bootstrap_generator import BootstrapGenerator
from llm_memory_transferor.exporters.package_exporter import PackageExporter
from llm_memory_transferor.layers.l2_wiki import L2Wiki
from llm_memory_transferor.models import (
    PreferenceMemory,
    ProfileMemory,
    ProjectMemory,
    WorkflowMemory,
)


@pytest.fixture
def populated_wiki(tmp_path):
    wiki = L2Wiki(tmp_path / "wiki")
    wiki.save_profile(ProfileMemory(
        name_or_alias="Alice",
        role_identity="ML Engineer",
        domain_background=["machine learning", "NLP"],
        common_languages=["English", "Python"],
        primary_task_types=["code review", "architecture design"],
    ))
    wiki.save_preferences(PreferenceMemory(
        language_preference="English",
        response_granularity="concise",
        forbidden_expressions=["As an AI", "Certainly!"],
        style_preference=["no emojis", "use numbered lists"],
    ))
    wiki.save_project(ProjectMemory(
        project_name="Memory Transferor",
        project_goal="Build portable memory layer",
        current_stage="Implementation",
        next_actions=["Write tests", "Add CLI"],
        unresolved_questions=["Which storage backend?"],
    ))
    wiki.save_workflows([
        WorkflowMemory(
            workflow_name="Code Review",
            trigger_condition="PR opened",
            typical_steps=["Read diff", "Check tests", "Approve"],
            reuse_frequency="daily",
            occurrence_count=5,
        )
    ])
    return wiki


def test_bootstrap_generic(populated_wiki):
    gen = BootstrapGenerator(populated_wiki)
    result = gen.generate(target_platform="generic")
    assert "Alice" in result
    assert "ML Engineer" in result
    assert "Memory Transferor" in result


def test_bootstrap_claude(populated_wiki):
    gen = BootstrapGenerator(populated_wiki)
    result = gen.generate(target_platform="claude")
    assert "<user_profile>" in result
    assert "Alice" in result


def test_bootstrap_chatgpt(populated_wiki):
    gen = BootstrapGenerator(populated_wiki)
    result = gen.generate(target_platform="chatgpt")
    assert "Alice" in result
    assert "About the user" in result


def test_bootstrap_kimi(populated_wiki):
    gen = BootstrapGenerator(populated_wiki)
    result = gen.generate(target_platform="kimi")
    assert "用户背景" in result


def test_bootstrap_max_tokens(populated_wiki):
    gen = BootstrapGenerator(populated_wiki)
    result = gen.generate(target_platform="generic", max_tokens=50)
    # 50 tokens ≈ 200 chars
    assert len(result) <= 500  # generous check


def test_bootstrap_empty_wiki(tmp_path):
    wiki = L2Wiki(tmp_path / "wiki")
    gen = BootstrapGenerator(wiki)
    result = gen.generate(target_platform="generic")
    assert "No profile" in result or len(result) > 0  # Should not crash


def test_package_export_zip(populated_wiki, tmp_path):
    exporter = PackageExporter(wiki=populated_wiki)
    output_path = tmp_path / "test_package"
    result = exporter.export(output_path=output_path, target_platform="generic", zip_output=True)
    assert result.exists()
    assert result.suffix == ".zip"

    import zipfile
    with zipfile.ZipFile(result) as zf:
        names = zf.namelist()
    assert "manifest.json" in names
    assert "minimal_bootstrap_prompt.txt" in names
    assert "user_profile.json" in names
    assert "preferences.json" in names
    assert "active_projects.json" in names


def test_package_export_dir(populated_wiki, tmp_path):
    exporter = PackageExporter(wiki=populated_wiki)
    output_path = tmp_path / "pkg_dir"
    result = exporter.export(output_path=output_path, target_platform="claude", zip_output=False)
    assert result.is_dir()
    assert (result / "manifest.json").exists()
    assert (result / "minimal_bootstrap_prompt.txt").exists()

    manifest = json.loads((result / "manifest.json").read_text())
    assert manifest["target_platform"] == "claude"
    assert manifest["format_version"] == "0.1"


def test_manifest_stats(populated_wiki, tmp_path):
    exporter = PackageExporter(wiki=populated_wiki)
    output_path = tmp_path / "pkg"
    result = exporter.export(output_path=output_path, target_platform="generic", zip_output=False)
    manifest = json.loads((result / "manifest.json").read_text())
    assert manifest["stats"]["has_profile"] is True
    assert manifest["stats"]["has_preferences"] is True
    assert manifest["stats"]["active_projects"] >= 1
