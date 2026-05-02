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
            "metadata",
            "logs",
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
            if legacy_json.name == "index.json":
                continue
            stem = legacy_json.stem
            project_dir = (self.wiki_dir / "projects" / stem)
            project_dir.mkdir(parents=True, exist_ok=True)
            self._move_if_needed(legacy_json, project_dir / "project.json")
            legacy_md = legacy_json.with_suffix(".md")
            self._move_if_needed(legacy_md, project_dir / "project.md")
        self._migrate_legacy_episode_layout()

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
        return ProfileMemory.model_validate_json(source.read_text(encoding="utf-8"))

    def save_profile(self, profile: ProfileMemory) -> None:
        profile.touch(profile.updated_at)
        self._profile_json.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        self._profile_md.write_text(profile.to_markdown(), encoding="utf-8")
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
        return PreferenceMemory.model_validate_json(source.read_text(encoding="utf-8"))

    def save_preferences(self, prefs: PreferenceMemory) -> None:
        prefs.touch(prefs.updated_at)
        self._preferences_json.write_text(prefs.model_dump_json(indent=2), encoding="utf-8")
        self._preferences_md.write_text(prefs.to_markdown(), encoding="utf-8")
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
        return ProjectMemory.model_validate_json(source.read_text(encoding="utf-8"))

    def list_projects(self) -> list[ProjectMemory]:
        projects = []
        seen_paths: set[Path] = set()
        for f in (self.wiki_dir / "projects").glob("*/project.json"):
            try:
                projects.append(ProjectMemory.model_validate_json(f.read_text(encoding="utf-8")))
                seen_paths.add(f)
            except Exception:
                pass
        for f in (self.wiki_dir / "projects").glob("*.json"):
            if f in seen_paths:
                continue
            try:
                projects.append(ProjectMemory.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        return projects

    def save_project(self, project: ProjectMemory) -> None:
        project.touch(project.updated_at)
        p = self._project_path(project.project_name)
        p.mkdir(parents=True, exist_ok=True)
        (p / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")
        (p / "project.md").write_text(project.to_markdown(), encoding="utf-8")
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
        data = json.loads(source.read_text(encoding="utf-8"))
        return [WorkflowMemory.model_validate(w) for w in data]

    def save_workflows(self, workflows: list[WorkflowMemory]) -> None:
        for w in workflows:
            w.touch(w.updated_at)
        data = [w.model_dump() for w in workflows]
        self._workflows_json.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        md_lines = [w.to_markdown() for w in workflows]
        self._workflows_md.write_text("\n\n---\n\n".join(md_lines), encoding="utf-8")
        self._write_root_readme()
        self._log_change("workflows", "update", "all")

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def save_episode(self, episode: EpisodicMemory) -> None:
        episode.touch(episode.updated_at)
        if not episode.episode_id:
            episode.episode_id = str(uuid.uuid4())[:8]
        conv_id = episode.conv_id or episode.episode_id
        path = self._episode_container_path(conv_id)
        episodes = [
            existing
            for existing in self._read_episode_container(path)
            if existing.episode_id != episode.episode_id
        ]
        episodes.append(episode)
        self._write_episode_container(conv_id, episodes)
        self._log_change("episode", "create", episode.episode_id)

    def save_conversation_episode_index(self, conv_id: str) -> None:
        """Compatibility shim.

        Canonical episode storage is now `episodes/<conversation_id>.json`,
        where each file contains all turn-level episodes for that chat.
        """
        return

    def load_episode(self, episode_id: str) -> Optional[EpisodicMemory]:
        episode_id = str(episode_id or "").strip()
        if not episode_id:
            return None
        direct = self.wiki_dir / "episodes" / f"{episode_id}.json"
        for episode in self._read_episode_container(direct):
            if episode.episode_id == episode_id:
                return episode
        for f in (self.wiki_dir / "episodes").glob("*.json"):
            try:
                for episode in self._read_episode_container(f):
                    if episode.episode_id == episode_id:
                        return episode
            except Exception:
                continue
        return None

    def list_episodes(self, project: str = "") -> list[EpisodicMemory]:
        episodes = []
        for f in (self.wiki_dir / "episodes").glob("*.json"):
            try:
                for ep in self._read_episode_container(f):
                    project_refs = set(ep.relates_to_projects or [])
                    if ep.related_project:
                        project_refs.add(ep.related_project)
                    if not project or project in project_refs:
                        episodes.append(ep)
            except Exception:
                pass
        episodes.sort(key=self._episode_sort_key)
        return episodes

    def _episode_container_path(self, conv_id: str) -> Path:
        safe_name = str(conv_id or "unknown_conversation").replace("/", "_")[:160]
        return self.wiki_dir / "episodes" / f"{safe_name}.json"

    @staticmethod
    def _episode_sort_key(ep: EpisodicMemory) -> tuple[str, int, str]:
        turn_index = 10**9
        if ep.turn_refs:
            try:
                turn_index = int(str(ep.turn_refs[0]).rsplit(":turn:", 1)[1])
            except (IndexError, ValueError):
                turn_index = 10**9
        created = ep.created_at.isoformat() if ep.created_at else ""
        return created, turn_index, ep.episode_id

    def _read_episode_container(self, path: Path) -> list[EpisodicMemory]:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("episodes"), list):
            return [
                EpisodicMemory.model_validate(item)
                for item in data.get("episodes", [])
                if isinstance(item, dict)
            ]
        if isinstance(data, dict):
            return [EpisodicMemory.model_validate(data)]
        return []

    def _write_episode_container(self, conv_id: str, episodes: list[EpisodicMemory]) -> None:
        clean = sorted(episodes, key=self._episode_sort_key)
        path = self._episode_container_path(conv_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "conversation_id": conv_id,
            "episode_count": len(clean),
            "episodes": [episode.model_dump(mode="json") for episode in clean],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        md_path = path.with_suffix(".md")
        md_path.write_text(
            "\n\n---\n\n".join(episode.to_markdown() for episode in clean),
            encoding="utf-8",
        )

    def _migrate_legacy_episode_layout(self) -> None:
        episode_dir = self.wiki_dir / "episodes"
        grouped: dict[str, list[EpisodicMemory]] = {}
        legacy_paths: list[Path] = []
        for path in episode_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and isinstance(data.get("episodes"), list):
                continue
            try:
                episode = EpisodicMemory.model_validate(data)
            except Exception:
                continue
            conv_id = episode.conv_id or episode.episode_id
            grouped.setdefault(conv_id, []).append(episode)
            legacy_paths.append(path)
        for conv_id, episodes in grouped.items():
            target = self._episode_container_path(conv_id)
            existing = self._read_episode_container(target) if target.exists() else []
            by_id = {episode.episode_id: episode for episode in existing}
            for episode in episodes:
                by_id[episode.episode_id] = episode
            self._write_episode_container(conv_id, list(by_id.values()))
        for path in legacy_paths:
            target_names = {self._episode_container_path(ep.conv_id or ep.episode_id).name for ep in grouped.get(path.stem, [])}
            if path.name in target_names:
                continue
            try:
                path.unlink()
                md_path = path.with_suffix(".md")
                if md_path.exists():
                    md_path.unlink()
            except OSError:
                pass

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
        lines = self._change_log.read_text(encoding="utf-8").splitlines()
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
            "episode_count": len(self.list_episodes()),
        }
        self._index_json.write_text(json.dumps(index, indent=2), encoding="utf-8")
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
        return json.loads(self._index_json.read_text(encoding="utf-8"))

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
"""
        self._root_readme.write_text(content, encoding="utf-8")
