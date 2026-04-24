"""L0 Raw Evidence Layer - ingests and indexes raw chat exports."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from pydantic import BaseModel, Field


class RawMessage(BaseModel):
    msg_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str = ""
    conversation_id: str = ""
    platform: str = "unknown"


class RawTurn(BaseModel):
    turn_id: str
    conversation_id: str
    message_ids: list[str] = Field(default_factory=list)


def _parse_timestamp(value: object) -> Optional[datetime]:
    """Convert a raw timestamp (Unix float, int, or ISO string) to UTC datetime."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        s = str(value).strip()
        if not s:
            return None
        # ISO string
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


class RawConversation(BaseModel):
    conv_id: str
    platform: str
    title: str = ""
    messages: list[RawMessage]
    turns: list[RawTurn] = Field(default_factory=list)
    start_time: Optional[datetime] = None  # when the conversation began
    end_time: Optional[datetime] = None    # when the conversation last updated

    def model_post_init(self, __context: object) -> None:
        if not self.turns:
            self.turns = _build_turns(self.conv_id, self.messages)

    def user_messages(self) -> list[RawMessage]:
        return [m for m in self.messages if m.role == "user"]

    def assistant_messages(self) -> list[RawMessage]:
        return [m for m in self.messages if m.role == "assistant"]

    def full_text(self) -> str:
        return "\n\n".join(
            f"[{m.role.upper()}]: {m.content}" for m in self.messages
        )

    def word_count(self) -> int:
        return len(self.full_text().split())


def _build_turns(conv_id: str, messages: list[RawMessage]) -> list[RawTurn]:
    turns: list[RawTurn] = []
    current_message_ids: list[str] = []

    for idx, msg in enumerate(messages):
        role = str(msg.role or "").strip().lower()
        if role == "user" and current_message_ids:
            turns.append(
                RawTurn(
                    turn_id=f"{conv_id}:turn:{len(turns)}",
                    conversation_id=conv_id,
                    message_ids=current_message_ids[:],
                )
            )
            current_message_ids = [msg.msg_id or f"{conv_id}_{idx}"]
        else:
            current_message_ids.append(msg.msg_id or f"{conv_id}_{idx}")

    if current_message_ids:
        turns.append(
            RawTurn(
                turn_id=f"{conv_id}:turn:{len(turns)}",
                conversation_id=conv_id,
                message_ids=current_message_ids[:],
            )
        )

    return turns


class L0RawLayer:
    """Reads and indexes raw chat history from various formats."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_file(self, path: Path) -> list[RawConversation]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._parse_json(path)
        elif suffix == ".jsonl":
            return self._parse_jsonl(path)
        elif suffix in (".md", ".txt"):
            return self._parse_text(path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    def _parse_json(self, path: Path) -> list[RawConversation]:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Handle top-level list (e.g. ChatGPT export)
        if isinstance(data, list):
            return [self._normalize_conv(item, path.stem) for item in data]
        # Handle single conversation dict
        if isinstance(data, dict):
            return [self._normalize_conv(data, path.stem)]
        return []

    def _parse_jsonl(self, path: Path) -> list[RawConversation]:
        convs = []
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                convs.append(self._normalize_conv(json.loads(line), f"{path.stem}_{i}"))
            except json.JSONDecodeError:
                pass
        return convs

    def _normalize_conv(self, data: dict, fallback_id: str) -> RawConversation:
        """Normalize different platform JSON shapes into RawConversation."""
        conv_id = str(data.get("id") or data.get("conversation_id") or fallback_id)
        title = str(data.get("title") or data.get("name") or "")
        platform = str(data.get("platform") or "unknown")

        messages: list[RawMessage] = []
        raw_messages = data.get("messages") or data.get("mapping") or []

        # ChatGPT mapping format: dict of {node_id: node}, each node wraps a "message"
        is_mapping = isinstance(raw_messages, dict)
        if is_mapping:
            raw_messages = list(raw_messages.values())

        for i, item in enumerate(raw_messages):
            if not isinstance(item, dict):
                continue
            # Unwrap ChatGPT mapping node → actual message object
            msg = item.get("message") if is_mapping else item
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or msg.get("author", {}).get("role") or "unknown")
            content = msg.get("content") or ""
            if isinstance(content, dict):
                # ChatGPT nested content
                parts = content.get("parts") or []
                content = " ".join(str(p) for p in parts if isinstance(p, str))
            elif isinstance(content, list):
                content = " ".join(str(p) for p in content if isinstance(p, str))
            else:
                content = str(content)

            if not content.strip():
                continue

            messages.append(
                RawMessage(
                    msg_id=str(msg.get("id") or f"{conv_id}_{i}"),
                    role=role,
                    content=content,
                    timestamp=str(msg.get("create_time") or msg.get("timestamp") or ""),
                    conversation_id=conv_id,
                    platform=platform,
                )
            )

        start_time = _parse_timestamp(data.get("create_time"))
        end_time = _parse_timestamp(data.get("update_time"))
        # Fall back to first/last message timestamps if conv-level ones are missing
        if start_time is None and messages:
            start_time = _parse_timestamp(messages[0].timestamp)
        if end_time is None and messages:
            end_time = _parse_timestamp(messages[-1].timestamp)

        raw_turns = data.get("turns") or []
        turns: list[RawTurn] = []
        if isinstance(raw_turns, list):
            for item in raw_turns:
                if not isinstance(item, dict):
                    continue
                try:
                    turns.append(RawTurn.model_validate(item))
                except Exception:
                    continue
        if not turns:
            turns = _build_turns(conv_id, messages)

        return RawConversation(
            conv_id=conv_id,
            platform=platform,
            title=title,
            messages=messages,
            turns=turns,
            start_time=start_time,
            end_time=end_time,
        )

    def _parse_text(self, path: Path) -> list[RawConversation]:
        """Parse a plain text or markdown conversation export."""
        text = path.read_text(encoding="utf-8")
        messages: list[RawMessage] = []
        current_role = "user"
        current_lines: list[str] = []

        role_pattern = re.compile(
            r"^\s*[\*#]*\s*(user|human|assistant|claude|gpt|ai|system)\s*[\*#]*\s*[:\-]?\s*$",
            re.IGNORECASE,
        )

        for line in text.splitlines():
            m = role_pattern.match(line)
            if m:
                if current_lines:
                    messages.append(
                        RawMessage(
                            msg_id=f"{path.stem}_{len(messages)}",
                            role=current_role,
                            content="\n".join(current_lines).strip(),
                            conversation_id=path.stem,
                            platform="text_import",
                        )
                    )
                    current_lines = []
                raw_role = m.group(1).lower()
                current_role = "user" if raw_role in ("user", "human") else "assistant"
            else:
                current_lines.append(line)

        if current_lines:
            messages.append(
                RawMessage(
                    msg_id=f"{path.stem}_{len(messages)}",
                    role=current_role,
                    content="\n".join(current_lines).strip(),
                    conversation_id=path.stem,
                    platform="text_import",
                )
            )

        return [
            RawConversation(
                conv_id=path.stem,
                platform="text_import",
                title=path.stem,
                messages=messages,
                turns=_build_turns(path.stem, messages),
            )
        ]

    # ------------------------------------------------------------------
    # Search / retrieval
    # ------------------------------------------------------------------

    def search(
        self, conversations: list[RawConversation], query: str, limit: int = 10
    ) -> list[tuple[RawConversation, RawMessage]]:
        """Keyword search across all messages. Returns (conv, msg) pairs."""
        query_lower = query.lower()
        results: list[tuple[RawConversation, RawMessage, int]] = []
        for conv in conversations:
            for msg in conv.messages:
                content_lower = msg.content.lower()
                if query_lower in content_lower:
                    score = content_lower.count(query_lower)
                    results.append((conv, msg, score))
        results.sort(key=lambda x: x[2], reverse=True)
        return [(c, m) for c, m, _ in results[:limit]]

    def topic_chunks(
        self,
        conversations: list[RawConversation],
        topics: list[str],
        chunk_size: int = 8,
    ) -> Iterator[tuple[str, str]]:
        """
        Yield (topic, text_chunk) for targeted retrieval.
        Finds conversations most relevant to each topic and chunks them.
        """
        for topic in topics:
            hits = self.search(conversations, topic, limit=20)
            seen_convs: set[str] = set()
            for conv, _msg in hits:
                if conv.conv_id in seen_convs:
                    continue
                seen_convs.add(conv.conv_id)
                # Yield conversation in chunks
                msgs = conv.messages
                for start in range(0, len(msgs), chunk_size):
                    chunk = msgs[start : start + chunk_size]
                    text = "\n".join(
                        f"[{m.role.upper()}]: {m.content[:500]}" for m in chunk
                    )
                    yield topic, f"[Conv: {conv.title or conv.conv_id}]\n{text}"
