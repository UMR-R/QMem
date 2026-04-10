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

    # ------------------------------------------------------------------
    # Directory layout
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for sub in ("projects", "episodes", "mappings", "metadata", "logs", "evidence"):
            (self.wiki_dir / sub).mkdir(parents=True, exist_ok=True)

    @property
    def _profile_json(self) -> Path:
        return self.wiki_dir / "profile.json"

    @property
    def _preferences_json(self) -> Path:
        return self.wiki_dir / "preferences.json"

    @property
    def _workflows_json(self) -> Path:
        return self.wiki_dir / "workflows.json"

    @property
    def _index_json(self) -> Path:
        return self.wiki_dir / "metadata" / "index.json"

    @property
    def _change_log(self) -> Path:
        return self.wiki_dir / "logs" / "change_log.jsonl"

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def load_profile(self) -> Optional[ProfileMemory]:
        if not self._profile_json.exists():
            return None
        return ProfileMemory.model_validate_json(self._profile_json.read_text())

    def save_profile(self, profile: ProfileMemory) -> None:
        profile.touch(profile.updated_at)
        self._profile_json.write_text(profile.model_dump_json(indent=2))
        (self.wiki_dir / "profile.md").write_text(profile.to_markdown())
        self._log_change("profile", "update", profile.id)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def load_preferences(self) -> Optional[PreferenceMemory]:
        if not self._preferences_json.exists():
            return None
        return PreferenceMemory.model_validate_json(self._preferences_json.read_text())

    def save_preferences(self, prefs: PreferenceMemory) -> None:
        prefs.touch(prefs.updated_at)
        self._preferences_json.write_text(prefs.model_dump_json(indent=2))
        (self.wiki_dir / "preferences.md").write_text(prefs.to_markdown())
        self._log_change("preferences", "update", prefs.id)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def load_project(self, name: str) -> Optional[ProjectMemory]:
        p = self._project_path(name)
        if not p.with_suffix(".json").exists():
            return None
        return ProjectMemory.model_validate_json(p.with_suffix(".json").read_text())

    def list_projects(self) -> list[ProjectMemory]:
        projects = []
        for f in (self.wiki_dir / "projects").glob("*.json"):
            try:
                projects.append(ProjectMemory.model_validate_json(f.read_text()))
            except Exception:
                pass
        return projects

    def save_project(self, project: ProjectMemory) -> None:
        project.touch(project.updated_at)
        p = self._project_path(project.project_name)
        p.with_suffix(".json").write_text(project.model_dump_json(indent=2))
        p.with_suffix(".md").write_text(project.to_markdown())
        self._log_change("project", "update", project.project_name)

    def _project_path(self, name: str) -> Path:
        safe_name = name.lower().replace(" ", "_").replace("/", "_")[:64]
        return self.wiki_dir / "projects" / safe_name

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    def load_workflows(self) -> list[WorkflowMemory]:
        if not self._workflows_json.exists():
            return []
        data = json.loads(self._workflows_json.read_text())
        return [WorkflowMemory.model_validate(w) for w in data]

    def save_workflows(self, workflows: list[WorkflowMemory]) -> None:
        for w in workflows:
            w.touch(w.updated_at)
        data = [w.model_dump() for w in workflows]
        self._workflows_json.write_text(json.dumps(data, indent=2, default=str))
        md_lines = [w.to_markdown() for w in workflows]
        (self.wiki_dir / "workflows.md").write_text("\n\n---\n\n".join(md_lines))
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
        return index

    def get_index(self) -> dict:
        if not self._index_json.exists():
            return self.rebuild_index()
        return json.loads(self._index_json.read_text())
