"""Portable memory package exporter."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bootstrap_generator import BootstrapGenerator
from .platform_mapping import BUILT_IN_MAPPINGS

PERSISTENT_SECTIONS = {"profile", "preferences", "projects", "workflows"}


class PackageExporter:
    """Bundle an L2-compatible wiki into a portable memory package."""

    def __init__(self, wiki: Any) -> None:
        self.wiki = wiki
        self.bootstrap_gen = BootstrapGenerator(wiki)

    def export(
        self,
        output_path: Path,
        target_platform: str = "generic",
        zip_output: bool = True,
        include_persistent: list[str] | None = None,
        include_episode_ids: list[str] | None = None,
    ) -> Path:
        if include_persistent is None:
            include_persistent = list(PERSISTENT_SECTIONS)
        include_persistent_set = {section.lower() for section in include_persistent}

        package_dir = (
            output_path.parent / f"_tmp_package_{output_path.stem}"
            if zip_output
            else output_path
        )
        package_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []
        all_episodes = self.wiki.list_episodes()
        if include_episode_ids is not None:
            selected_ids = set(include_episode_ids)
            episodes = [episode for episode in all_episodes if episode.episode_id in selected_ids]
        else:
            episodes = all_episodes

        if episodes:
            (package_dir / "episodes").mkdir(exist_ok=True)
            for episode in episodes:
                filename = f"episodes/{episode.episode_id}.json"
                self._write(package_dir / filename, episode.model_dump(mode="json"))
                files_written.append(filename)

        if "profile" in include_persistent_set:
            profile = self.wiki.load_profile()
            if profile:
                self._write(package_dir / "user_profile.json", profile.model_dump(mode="json"))
                files_written.append("user_profile.json")

        if "preferences" in include_persistent_set:
            prefs = self.wiki.load_preferences()
            if prefs:
                self._write(package_dir / "preferences.json", prefs.model_dump(mode="json"))
                files_written.append("preferences.json")

        if "projects" in include_persistent_set:
            projects = [project for project in self.wiki.list_projects() if project.is_active]
            if projects:
                self._write(
                    package_dir / "active_projects.json",
                    [project.model_dump(mode="json") for project in projects],
                )
                files_written.append("active_projects.json")

        if "workflows" in include_persistent_set:
            workflows = self.wiki.load_workflows()
            if workflows:
                self._write(
                    package_dir / "key_workflows.json",
                    [workflow.model_dump(mode="json") for workflow in workflows],
                )
                files_written.append("key_workflows.json")

        bootstrap = self.bootstrap_gen.generate(target_platform=target_platform)
        (package_dir / "minimal_bootstrap_prompt.txt").write_text(bootstrap, encoding="utf-8")
        files_written.append("minimal_bootstrap_prompt.txt")

        mapping = BUILT_IN_MAPPINGS.get(target_platform) or BUILT_IN_MAPPINGS["generic"]
        self._write(package_dir / "target_platform_mapping.json", {"platform": target_platform, **mapping})
        files_written.append("target_platform_mapping.json")

        manifest = self._build_manifest(target_platform, episodes, include_persistent_set, files_written)
        self._write(package_dir / "manifest.json", manifest)
        files_written.insert(0, "manifest.json")

        if zip_output:
            zip_path = output_path.with_suffix(".zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in package_dir.rglob("*"):
                    archive.write(path, path.relative_to(package_dir))
            shutil.rmtree(package_dir)
            return zip_path

        return package_dir

    def _build_manifest(
        self,
        target_platform: str,
        episodes: list[Any],
        included_persistent: set[str],
        files: list[str],
    ) -> dict[str, Any]:
        index = self.wiki.get_index()
        return {
            "format_version": "0.2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_platform": target_platform,
            "included_persistent": sorted(included_persistent),
            "stats": {
                "episodes_included": len(episodes),
                "has_profile": "user_profile.json" in files,
                "has_preferences": "preferences.json" in files,
                "active_projects": len(index.get("projects", []))
                if "projects" in included_persistent
                else 0,
                "workflows": index.get("workflow_count", 0)
                if "workflows" in included_persistent
                else 0,
            },
            "files": files,
        }

    def _write(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


__all__ = ["PERSISTENT_SECTIONS", "PackageExporter"]
