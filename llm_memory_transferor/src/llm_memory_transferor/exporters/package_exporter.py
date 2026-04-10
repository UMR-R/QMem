"""Package exporter - bundles L2 MWiki into a portable memory package."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..exporters.bootstrap_generator import BootstrapGenerator
from ..layers.l2_wiki import L2Wiki
from ..models.platform_mapping import BUILT_IN_MAPPINGS

# Valid persistent memory section names
PERSISTENT_SECTIONS = {"profile", "preferences", "projects", "workflows"}


class PackageExporter:
    """
    Exports a portable memory package ready for importing to any target platform.

    Callers can choose which persistent memory sections and which episodes to include.

    Package structure:
      manifest.json
      episodes/                         (selected episodes)
      user_profile.json                 (if selected)
      preferences.json                  (if selected)
      active_projects.json              (if selected)
      key_workflows.json                (if selected)
      minimal_bootstrap_prompt.txt
      target_platform_mapping.json
    """

    def __init__(self, wiki: L2Wiki) -> None:
        self.wiki = wiki
        self.bootstrap_gen = BootstrapGenerator(wiki)

    def export(
        self,
        output_path: Path,
        target_platform: str = "generic",
        zip_output: bool = True,
        include_persistent: Optional[list[str]] = None,
        include_episode_ids: Optional[list[str]] = None,
    ) -> Path:
        """
        Export memory package to output_path directory (or zip).

        Args:
            include_persistent: which persistent sections to include.
                Defaults to all: ["profile", "preferences", "projects", "workflows"].
            include_episode_ids: specific episode IDs to include.
                Defaults to None (all episodes).

        Returns path to the created package.
        """
        if include_persistent is None:
            include_persistent = list(PERSISTENT_SECTIONS)
        include_persistent_set = {s.lower() for s in include_persistent}

        if zip_output:
            package_dir = output_path.parent / f"_tmp_package_{output_path.stem}"
        else:
            package_dir = output_path
        package_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []

        # episodes/
        all_episodes = self.wiki.list_episodes()
        if include_episode_ids is not None:
            selected_ids = set(include_episode_ids)
            episodes = [ep for ep in all_episodes if ep.episode_id in selected_ids]
        else:
            episodes = all_episodes

        if episodes:
            ep_dir = package_dir / "episodes"
            ep_dir.mkdir(exist_ok=True)
            for ep in episodes:
                fname = f"episodes/{ep.episode_id}.json"
                self._write(package_dir / fname, ep.model_dump(mode="json"))
                files_written.append(fname)

        # user_profile.json
        if "profile" in include_persistent_set:
            profile = self.wiki.load_profile()
            if profile:
                self._write(package_dir / "user_profile.json", profile.model_dump(mode="json"))
                files_written.append("user_profile.json")

        # preferences.json
        if "preferences" in include_persistent_set:
            prefs = self.wiki.load_preferences()
            if prefs:
                self._write(package_dir / "preferences.json", prefs.model_dump(mode="json"))
                files_written.append("preferences.json")

        # active_projects.json
        if "projects" in include_persistent_set:
            projects = [p for p in self.wiki.list_projects() if p.is_active]
            if projects:
                self._write(
                    package_dir / "active_projects.json",
                    [p.model_dump(mode="json") for p in projects],
                )
                files_written.append("active_projects.json")

        # key_workflows.json
        if "workflows" in include_persistent_set:
            workflows = self.wiki.load_workflows()
            if workflows:
                self._write(
                    package_dir / "key_workflows.json",
                    [w.model_dump(mode="json") for w in workflows],
                )
                files_written.append("key_workflows.json")

        # minimal_bootstrap_prompt.txt (uses whatever persistent memory is present)
        bootstrap = self.bootstrap_gen.generate(target_platform=target_platform)
        (package_dir / "minimal_bootstrap_prompt.txt").write_text(bootstrap, encoding="utf-8")
        files_written.append("minimal_bootstrap_prompt.txt")

        # target_platform_mapping.json
        mapping = BUILT_IN_MAPPINGS.get(target_platform) or BUILT_IN_MAPPINGS["generic"]
        self._write(
            package_dir / "target_platform_mapping.json",
            {"platform": target_platform, **mapping},
        )
        files_written.append("target_platform_mapping.json")

        # manifest.json
        manifest = self._build_manifest(
            target_platform, episodes, include_persistent_set, files_written
        )
        self._write(package_dir / "manifest.json", manifest)
        files_written.insert(0, "manifest.json")

        if zip_output:
            zip_path = output_path.with_suffix(".zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in package_dir.rglob("*"):
                    zf.write(f, f.relative_to(package_dir))
            import shutil
            shutil.rmtree(package_dir)
            return zip_path

        return package_dir

    def _build_manifest(
        self,
        target_platform: str,
        episodes: list,
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
                "active_projects": len(index.get("projects", [])) if "projects" in included_persistent else 0,
                "workflows": index.get("workflow_count", 0) if "workflows" in included_persistent else 0,
            },
            "files": files,
        }

    def _write(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
