"""L2 Managed MWiki - the formal memory layer owned by this system."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models import (
    EpisodicMemory,
    PreferenceMemory,
    ProfileMemory,
    ProjectMemory,
    WorkflowMemory,
)


class L2Wiki:
    """
    The authoritative memory store.
    Backed by the wiki/ directory: markdown for humans, JSON for machines.
    """

    def __init__(self, wiki_dir: Path) -> None:
        self.wiki_dir = wiki_dir
        self._ensure_dirs()
        self._migrate_legacy_layout()

    # ------------------------------------------------------------------
    # Directory layout
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for sub in (
            "profile",
            "preferences",
            "projects",
            "workflows",
            "episodes",
            "mappings",
            "metadata",
            "logs",
            "evidence",
        ):
            (self.wiki_dir / sub).mkdir(parents=True, exist_ok=True)

    def _migrate_legacy_layout(self) -> None:
        self._move_if_needed(self._legacy_profile_json, self._profile_json)
        self._move_if_needed(self._legacy_profile_md, self._profile_md)
        self._move_if_needed(self._legacy_preferences_json, self._preferences_json)
        self._move_if_needed(self._legacy_preferences_md, self._preferences_md)
        self._move_if_needed(self._legacy_workflows_json, self._workflows_json)
        self._move_if_needed(self._legacy_workflows_md, self._workflows_md)

        for legacy_json in (self.wiki_dir / "projects").glob("*.json"):
            stem = legacy_json.stem
            project_dir = (self.wiki_dir / "projects" / stem)
            project_dir.mkdir(parents=True, exist_ok=True)
            self._move_if_needed(legacy_json, project_dir / "project.json")
            legacy_md = legacy_json.with_suffix(".md")
            self._move_if_needed(legacy_md, project_dir / "project.md")

    @staticmethod
    def _move_if_needed(source: Path, target: Path) -> None:
        if not source.exists() or target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    @property
    def _profile_json(self) -> Path:
        return self.wiki_dir / "profile" / "profile.json"

    @property
    def _legacy_profile_json(self) -> Path:
        return self.wiki_dir / "profile.json"

    @property
    def _profile_md(self) -> Path:
        return self.wiki_dir / "profile" / "profile.md"

    @property
    def _legacy_profile_md(self) -> Path:
        return self.wiki_dir / "profile.md"

    @property
    def _preferences_json(self) -> Path:
        return self.wiki_dir / "preferences" / "preferences.json"

    @property
    def _legacy_preferences_json(self) -> Path:
        return self.wiki_dir / "preferences.json"

    @property
    def _preferences_md(self) -> Path:
        return self.wiki_dir / "preferences" / "preferences.md"

    @property
    def _legacy_preferences_md(self) -> Path:
        return self.wiki_dir / "preferences.md"

    @property
    def _workflows_json(self) -> Path:
        return self.wiki_dir / "workflows" / "workflows.json"

    @property
    def _legacy_workflows_json(self) -> Path:
        return self.wiki_dir / "workflows.json"

    @property
    def _workflows_md(self) -> Path:
        return self.wiki_dir / "workflows" / "workflows.md"

    @property
    def _legacy_workflows_md(self) -> Path:
        return self.wiki_dir / "workflows.md"

    @property
    def _index_json(self) -> Path:
        return self.wiki_dir / "metadata" / "index.json"

    @property
    def _root_readme(self) -> Path:
        return self.wiki_dir / "README.md"

    @property
    def _profile_index(self) -> Path:
        return self.wiki_dir / "profile" / "index.json"

    @property
    def _preferences_index(self) -> Path:
        return self.wiki_dir / "preferences" / "index.json"

    @property
    def _projects_index(self) -> Path:
        return self.wiki_dir / "projects" / "index.json"

    @property
    def _profile_readme(self) -> Path:
        return self.wiki_dir / "profile" / "README.md"

    @property
    def _preferences_readme(self) -> Path:
        return self.wiki_dir / "preferences" / "README.md"

    @property
    def _change_log(self) -> Path:
        return self.wiki_dir / "logs" / "change_log.jsonl"

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def load_profile(self) -> Optional[ProfileMemory]:
        source = self._profile_json if self._profile_json.exists() else self._legacy_profile_json
        if not source.exists():
            return None
        return ProfileMemory.model_validate_json(source.read_text())

    def save_profile(self, profile: ProfileMemory) -> None:
        profile.touch(profile.updated_at)
        self._profile_json.write_text(profile.model_dump_json(indent=2))
        self._profile_md.write_text(profile.to_markdown())
        self._write_profile_section_summary(profile)
        self._write_root_readme()
        self._log_change("profile", "update", profile.id)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def load_preferences(self) -> Optional[PreferenceMemory]:
        source = self._preferences_json if self._preferences_json.exists() else self._legacy_preferences_json
        if not source.exists():
            return None
        return PreferenceMemory.model_validate_json(source.read_text())

    def save_preferences(self, prefs: PreferenceMemory) -> None:
        prefs.touch(prefs.updated_at)
        self._preferences_json.write_text(prefs.model_dump_json(indent=2))
        self._preferences_md.write_text(prefs.to_markdown())
        self._write_preferences_section_summary(prefs)
        self._write_root_readme()
        self._log_change("preferences", "update", prefs.id)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def load_project(self, name: str) -> Optional[ProjectMemory]:
        p = self._project_path(name)
        legacy = self._legacy_project_path(name)
        source = p / "project.json" if (p / "project.json").exists() else legacy.with_suffix(".json")
        if not source.exists():
            return None
        return ProjectMemory.model_validate_json(source.read_text())

    def list_projects(self) -> list[ProjectMemory]:
        projects = []
        seen_paths: set[Path] = set()
        for f in (self.wiki_dir / "projects").glob("*/project.json"):
            try:
                projects.append(ProjectMemory.model_validate_json(f.read_text()))
                seen_paths.add(f)
            except Exception:
                pass
        for f in (self.wiki_dir / "projects").glob("*.json"):
            if f in seen_paths:
                continue
            try:
                projects.append(ProjectMemory.model_validate_json(f.read_text()))
            except Exception:
                pass
        return projects

    def save_project(self, project: ProjectMemory) -> None:
        project.touch(project.updated_at)
        p = self._project_path(project.project_name)
        p.mkdir(parents=True, exist_ok=True)
        (p / "project.json").write_text(project.model_dump_json(indent=2))
        (p / "project.md").write_text(project.to_markdown())
        self._write_projects_index()
        self._write_root_readme()
        self._log_change("project", "update", project.project_name)

    def _project_path(self, name: str) -> Path:
        safe_name = name.lower().replace(" ", "_").replace("/", "_")[:64]
        return self.wiki_dir / "projects" / safe_name

    def _legacy_project_path(self, name: str) -> Path:
        safe_name = name.lower().replace(" ", "_").replace("/", "_")[:64]
        return self.wiki_dir / "projects" / safe_name

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    def load_workflows(self) -> list[WorkflowMemory]:
        source = self._workflows_json if self._workflows_json.exists() else self._legacy_workflows_json
        if not source.exists():
            return []
        data = json.loads(source.read_text())
        return [WorkflowMemory.model_validate(w) for w in data]

    def save_workflows(self, workflows: list[WorkflowMemory]) -> None:
        for w in workflows:
            w.touch(w.updated_at)
        data = [w.model_dump() for w in workflows]
        self._workflows_json.write_text(json.dumps(data, indent=2, default=str))
        md_lines = [w.to_markdown() for w in workflows]
        self._workflows_md.write_text("\n\n---\n\n".join(md_lines))
        self._write_root_readme()
        self._log_change("workflows", "update", "all")

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def save_episode(self, episode: EpisodicMemory) -> None:
        episode.touch(episode.updated_at)
        if not episode.episode_id:
            episode.episode_id = str(uuid.uuid4())[:8]
        base = self.wiki_dir / "episodes" / episode.episode_id
        base.with_suffix(".json").write_text(episode.model_dump_json(indent=2, exclude=None))
        base.with_suffix(".md").write_text(episode.to_markdown())
        self._log_change("episode", "create", episode.episode_id)

    def list_episodes(self, project: str = "") -> list[EpisodicMemory]:
        episodes = []
        for f in (self.wiki_dir / "episodes").glob("*.json"):
            try:
                ep = EpisodicMemory.model_validate_json(f.read_text())
                if not project or ep.related_project == project:
                    episodes.append(ep)
            except Exception:
                pass
        episodes.sort(key=lambda e: e.created_at)
        return episodes

    # ------------------------------------------------------------------
    # Change log
    # ------------------------------------------------------------------

    def _log_change(self, entity_type: str, action: str, entity_id: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entity_type": entity_type,
            "action": action,
            "entity_id": entity_id,
        }
        with self._change_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def change_history(self, limit: int = 50) -> list[dict]:
        if not self._change_log.exists():
            return []
        lines = self._change_log.read_text().splitlines()
        entries = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return entries

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def rebuild_index(self) -> dict:
        index = {
            "last_indexed": datetime.now(timezone.utc).isoformat(),
            "has_profile": self._profile_json.exists(),
            "has_preferences": self._preferences_json.exists(),
            "projects": [p.project_name for p in self.list_projects()],
            "workflow_count": len(self.load_workflows()),
            "episode_count": len(list((self.wiki_dir / "episodes").glob("*.json"))),
        }
        self._index_json.write_text(json.dumps(index, indent=2))
        profile = self.load_profile()
        if profile:
            self._write_profile_section_summary(profile)
        prefs = self.load_preferences()
        if prefs:
            self._write_preferences_section_summary(prefs)
        self._write_projects_index()
        self._write_root_readme()
        return index

    def get_index(self) -> dict:
        if not self._index_json.exists():
            return self.rebuild_index()
        return json.loads(self._index_json.read_text())

    # ------------------------------------------------------------------
    # Human-facing summaries
    # ------------------------------------------------------------------

    def _write_profile_section_summary(self, profile: ProfileMemory) -> None:
        fields = {
            "name_or_alias": profile.name_or_alias,
            "role_identity": profile.role_identity,
            "domain_background": profile.domain_background,
            "organization_or_affiliation": profile.organization_or_affiliation,
            "common_languages": profile.common_languages,
            "long_term_research_or_work_focus": profile.long_term_research_or_work_focus,
        }
        summary = {
            "section": "profile",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "files": {
                "json": "profile.json",
                "markdown": "profile.md",
            },
            "fields": {
                key: value for key, value in fields.items()
                if value not in ("", [], None)
            },
        }
        self._profile_index.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self._profile_readme.write_text(
            "# 用户画像\n\n"
            "- `profile.json`: 机器可读版本\n"
            "- `profile.md`: 人类可读版本\n"
            "- `index.json`: 当前字段摘要与更新时间\n",
            encoding="utf-8",
        )

    def _write_preferences_section_summary(self, prefs: PreferenceMemory) -> None:
        fields = {
            "style_preference": prefs.style_preference,
            "terminology_preference": prefs.terminology_preference,
            "formatting_constraints": prefs.formatting_constraints,
            "forbidden_expressions": prefs.forbidden_expressions,
            "language_preference": prefs.language_preference,
            "revision_preference": prefs.revision_preference,
            "response_granularity": prefs.response_granularity,
            "primary_task_types": prefs.primary_task_types,
        }
        summary = {
            "section": "preferences",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "files": {
                "json": "preferences.json",
                "markdown": "preferences.md",
            },
            "fields": {
                key: value for key, value in fields.items()
                if value not in ("", [], None)
            },
        }
        self._preferences_index.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self._preferences_readme.write_text(
            "# 偏好设置\n\n"
            "- `preferences.json`: 机器可读版本\n"
            "- `preferences.md`: 人类可读版本\n"
            "- `index.json`: 当前字段摘要与更新时间\n",
            encoding="utf-8",
        )

    def _write_projects_index(self) -> None:
        items = []
        for project in self.list_projects():
            slug = self._project_path(project.project_name).name
            items.append(
                {
                    "project_name": project.project_name,
                    "folder": slug,
                    "files": {
                        "json": f"{slug}/project.json",
                        "markdown": f"{slug}/project.md",
                    },
                    "is_active": project.is_active,
                    "updated_at": project.updated_at.isoformat(),
                }
            )
        payload = {
            "section": "projects",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(items),
            "items": items,
        }
        self._projects_index.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_root_readme(self) -> None:
        content = """# Wiki Memory Store

这个目录是记忆系统的总入口。推荐从各子目录的 `README.md` 或 `index.json` 开始查看。

## 目录概览

- `profile/`: 用户画像
- `preferences/`: 偏好设置
- `projects/`: 项目记忆
- `workflows/`: 工作流 / SOP
- `skills/`: Skill 资产
- `episodes/`: 对话级 episodic 记忆
- `raw/`: 原始对话
- `platform_memory/`: 平台记忆快照
- `metadata/`: 索引、display 文案和整理状态
- `logs/`: 变更日志
- `evidence/`: 证据层
- `mappings/`: 映射与中间层
"""
        self._root_readme.write_text(content, encoding="utf-8")
