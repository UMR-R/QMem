"""L1 External Memory Signals - platform-native memory/profile artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class L1Signal(BaseModel):
    """A single external memory artifact from a platform."""

    signal_type: str  # "saved_memory" | "summary" | "profile" | "preference" | "custom_instruction" | "agent_config" | "platform_skill"
    platform: str
    raw_text: str = ""
    raw_json: dict[str, Any] = {}
    source_file: str = ""

    def text(self) -> str:
        if self.raw_text:
            return self.raw_text
        return json.dumps(self.raw_json, ensure_ascii=False, indent=2)

    def is_meaningful(self) -> bool:
        text = self.text().strip()
        normalized = text.lower()
        if self.signal_type == "generic":
            return False
        if not text or normalized in {"{}", "[]", "null", "\"\""}:
            return False
        if self.signal_type == "saved_memory" and normalized in {"{}", "[]"}:
            return False
        if self.platform == "unknown" and self.signal_type == "summary" and normalized in {
            "chat history",
            "conversation history",
            "history",
        }:
            return False
        if self.platform == "unknown" and self.signal_type == "saved_memory" and normalized in {
            "{}",
            "[]",
            "null",
        }:
            return False
        return True


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

        actual_platform = str(data.get("platform") or platform or "unknown").strip() or "unknown"
        source_type = str(data.get("source_type") or "").strip().lower()
        page_type = str(data.get("page_type") or "").strip().lower()
        raw_record_types = data.get("record_types")
        if raw_record_types is None:
            raw_record_types = data.get("recordTypes") or []
        record_types = {
            str(item).strip().lower()
            for item in raw_record_types
            if str(item).strip()
        }
        if source_type == "platform_memory_snapshot" or (
            page_type == "platform_context" and not record_types
        ):
            return signals

        # Try to detect signal type from keys
        if "memory" in data or "memories" in data:
            content = data.get("memory") or data.get("memories") or ""
            signals.append(
                L1Signal(
                    signal_type="saved_memory",
                    platform=actual_platform,
                    raw_text=content if isinstance(content, str) else "",
                    raw_json=data if isinstance(content, dict) else {},
                    source_file=source_file,
                )
            )
        if "saved_memory" in data or "savedMemoryItems" in data:
            content = data.get("saved_memory")
            if content is None:
                content = data.get("savedMemoryItems") or []
            signals.append(
                L1Signal(
                    signal_type="saved_memory",
                    platform=actual_platform,
                    raw_text="\n".join(str(item).strip() for item in content if str(item).strip()) if isinstance(content, list) else str(content),
                    raw_json={"saved_memory": content} if isinstance(content, (list, dict)) else {},
                    source_file=source_file,
                )
            )
        if "summary" in data:
            signals.append(
                L1Signal(
                    signal_type="summary",
                    platform=actual_platform,
                    raw_text=str(data["summary"]),
                    source_file=source_file,
                )
            )
        if "profile" in data:
            p = data["profile"]
            signals.append(
                L1Signal(
                    signal_type="profile",
                    platform=actual_platform,
                    raw_text=p if isinstance(p, str) else "",
                    raw_json=p if isinstance(p, dict) else {},
                    source_file=source_file,
                )
            )
        if "preferences" in data:
            pref = data.get("preferences") or {}
            signals.append(
                L1Signal(
                    signal_type="preference",
                    platform=actual_platform,
                    raw_text=pref if isinstance(pref, str) else "",
                    raw_json=pref if isinstance(pref, dict) else {},
                    source_file=source_file,
                )
            )
        if "custom_instructions" in data or "customInstructions" in data:
            inst = data.get("custom_instructions")
            if inst is None:
                inst = data.get("customInstructions") or []
            signals.append(
                L1Signal(
                    signal_type="custom_instruction",
                    platform=actual_platform,
                    raw_text="\n".join(
                        str(item.get("content") if isinstance(item, dict) else item).strip()
                        for item in inst
                        if str(item.get("content") if isinstance(item, dict) else item).strip()
                    ) if isinstance(inst, list) else str(inst),
                    raw_json={"custom_instructions": inst} if isinstance(inst, (list, dict)) else {},
                    source_file=source_file,
                )
            )
        if "persona" in data or "instruction" in data:
            inst = data.get("persona") or data.get("instruction") or ""
            signals.append(
                L1Signal(
                    signal_type="custom_instruction",
                    platform=actual_platform,
                    raw_text=str(inst),
                    source_file=source_file,
                )
            )
        if "agent_config" in data or "agentConfig" in data:
            agent = data.get("agent_config")
            if agent is None:
                agent = data.get("agentConfig") or {}
            if isinstance(agent, dict):
                raw_instructions = agent.get("instructions") or []
                if isinstance(raw_instructions, list):
                    instruction_text = "\n".join(
                        str(item).strip() for item in raw_instructions if str(item).strip()
                    )
                else:
                    instruction_text = str(raw_instructions or "").strip()
                raw_text = (
                    instruction_text
                    or str(agent.get("description") or agent.get("goal") or "").strip()
                )
            else:
                raw_text = str(agent or "")
            signals.append(
                L1Signal(
                    signal_type="agent_config",
                    platform=actual_platform,
                    raw_text=raw_text,
                    raw_json=agent if isinstance(agent, dict) else {},
                    source_file=source_file,
                )
            )
        if "platform_skills" in data or "platformSkills" in data:
            skills = data.get("platform_skills")
            if skills is None:
                skills = data.get("platformSkills") or []
            signals.append(
                L1Signal(
                    signal_type="platform_skill",
                    platform=actual_platform,
                    raw_text="\n".join(
                        str(item.get("name") or item.get("title") or "").strip()
                        for item in skills
                        if isinstance(item, dict) and str(item.get("name") or item.get("title") or "").strip()
                    ) if isinstance(skills, list) else str(skills),
                    raw_json={"platform_skills": skills} if isinstance(skills, (list, dict)) else {},
                    source_file=source_file,
                )
            )
        # Fallback: treat whole object as a generic signal
        if not signals:
            signals.append(
                L1Signal(
                    signal_type="generic",
                    platform=actual_platform,
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
            if not sig.is_meaningful():
                continue
            parts.append(f"[{sig.signal_type.upper()} from {sig.platform}]\n{sig.text()}")
        return "\n\n---\n\n".join(parts)

    def by_type(self, signal_type: str) -> list[L1Signal]:
        return [s for s in self.signals if s.signal_type == signal_type]
