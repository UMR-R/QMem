from __future__ import annotations

import json
from pathlib import Path

from memory_transferor.memory_models import RawChatSession


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save_sessions(self, sessions: list[RawChatSession]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for session in sessions:
            path = self.root / f"{session.session_id}.json"
            path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def load_sessions(self) -> list[RawChatSession]:
        sessions: list[RawChatSession] = []
        for path in sorted(self.root.glob("*.json")):
            sessions.append(RawChatSession.model_validate_json(path.read_text(encoding="utf-8")))
        return sessions

