"""L1 External Memory Signals - platform-native memory/profile artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class L1Signal(BaseModel):
    """A single external memory artifact from a platform."""

    signal_type: str  # "saved_memory" | "summary" | "profile" | "preference" | "custom_instruction"
    platform: str
    raw_text: str = ""
    raw_json: dict[str, Any] = {}
    source_file: str = ""

    def text(self) -> str:
        if self.raw_text:
            return self.raw_text
        return json.dumps(self.raw_json, ensure_ascii=False, indent=2)


class L1SignalLayer:
    """
    Reads platform-provided memory signals.
    These are External Memory Signals - already processed once by the platform.
    Their role: fast high-level sketch, alignment/validation reference,
    health check, and migration acceleration — NOT the authoritative source.
    """

    def __init__(self) -> None:
        self.signals: list[L1Signal] = []

    def load_file(self, path: Path, platform: str = "unknown") -> list[L1Signal]:
        suffix = path.suffix.lower()
        signals: list[L1Signal] = []

        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            signals.extend(self._parse_json_signals(data, platform, str(path)))
        elif suffix in (".md", ".txt"):
            text = path.read_text(encoding="utf-8")
            signals.append(
                L1Signal(
                    signal_type=self._guess_type(path.stem),
                    platform=platform,
                    raw_text=text,
                    source_file=str(path),
                )
            )
        elif suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    signals.extend(self._parse_json_signals(item, platform, str(path)))
                except json.JSONDecodeError:
                    pass

        self.signals.extend(signals)
        return signals

    def _parse_json_signals(
        self, data: Any, platform: str, source_file: str
    ) -> list[L1Signal]:
        signals = []
        if isinstance(data, list):
            for item in data:
                signals.extend(self._parse_json_signals(item, platform, source_file))
            return signals

        if not isinstance(data, dict):
            return signals

        # Try to detect signal type from keys
        if "memory" in data or "memories" in data:
            content = data.get("memory") or data.get("memories") or ""
            signals.append(
                L1Signal(
                    signal_type="saved_memory",
                    platform=platform,
                    raw_text=content if isinstance(content, str) else "",
                    raw_json=data if isinstance(content, dict) else {},
                    source_file=source_file,
                )
            )
        if "summary" in data:
            signals.append(
                L1Signal(
                    signal_type="summary",
                    platform=platform,
                    raw_text=str(data["summary"]),
                    source_file=source_file,
                )
            )
        if "profile" in data:
            p = data["profile"]
            signals.append(
                L1Signal(
                    signal_type="profile",
                    platform=platform,
                    raw_text=p if isinstance(p, str) else "",
                    raw_json=p if isinstance(p, dict) else {},
                    source_file=source_file,
                )
            )
        if "preferences" in data or "custom_instructions" in data:
            pref = data.get("preferences") or data.get("custom_instructions") or {}
            signals.append(
                L1Signal(
                    signal_type="preference",
                    platform=platform,
                    raw_text=pref if isinstance(pref, str) else "",
                    raw_json=pref if isinstance(pref, dict) else {},
                    source_file=source_file,
                )
            )
        if "persona" in data or "instruction" in data:
            inst = data.get("persona") or data.get("instruction") or ""
            signals.append(
                L1Signal(
                    signal_type="custom_instruction",
                    platform=platform,
                    raw_text=str(inst),
                    source_file=source_file,
                )
            )
        # Fallback: treat whole object as a generic signal
        if not signals:
            signals.append(
                L1Signal(
                    signal_type="generic",
                    platform=platform,
                    raw_json=data,
                    source_file=source_file,
                )
            )
        return signals

    def _guess_type(self, stem: str) -> str:
        stem_lower = stem.lower()
        if "memory" in stem_lower:
            return "saved_memory"
        if "profile" in stem_lower:
            return "profile"
        if "preference" in stem_lower or "pref" in stem_lower:
            return "preference"
        if "instruction" in stem_lower or "persona" in stem_lower:
            return "custom_instruction"
        if "summary" in stem_lower:
            return "summary"
        return "generic"

    def combined_text(self) -> str:
        """All signal text joined for LLM consumption."""
        parts = []
        for sig in self.signals:
            parts.append(f"[{sig.signal_type.upper()} from {sig.platform}]\n{sig.text()}")
        return "\n\n---\n\n".join(parts)

    def by_type(self, signal_type: str) -> list[L1Signal]:
        return [s for s in self.signals if s.signal_type == signal_type]
