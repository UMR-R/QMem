from __future__ import annotations

from pathlib import Path

from .episode_store import EpisodeStore
from .persistent_store import PersistentStore
from .raw_store import RawStore


class MemoryWorkspace:
    """Unified entry for the canonical local memory directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = RawStore(root / "raw")
        self.episodes = EpisodeStore(root / "episodes")
        self.persistent = PersistentStore(root)

    def ensure(self) -> None:
        self.raw.root.mkdir(parents=True, exist_ok=True)
        self.episodes.root.mkdir(parents=True, exist_ok=True)
        self.persistent.ensure()

