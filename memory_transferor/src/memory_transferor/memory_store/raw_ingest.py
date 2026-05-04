"""Raw evidence importer for platform chat exports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from memory_transferor.memory_models import (
    RawConversation,
    RawMessage,
    RawTurn,
    build_raw_turns,
    parse_raw_timestamp,
)


class L0RawLayer:
    """Reads and indexes raw chat history from common export formats."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def ingest_file(self, path: Path) -> list[RawConversation]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._parse_json(path)
        if suffix == ".jsonl":
            return self._parse_jsonl(path)
        if suffix in (".md", ".txt"):
            return self._parse_text(path)
        raise ValueError(f"Unsupported file format: {suffix}")

    def _parse_json(self, path: Path) -> list[RawConversation]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [self._normalize_conv(item, path.stem) for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [self._normalize_conv(data, path.stem)]
        return []

    def _parse_jsonl(self, path: Path) -> list[RawConversation]:
        conversations: list[RawConversation] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                conversations.append(self._normalize_conv(payload, f"{path.stem}_{index}"))
        return conversations

    def _normalize_conv(self, data: dict, fallback_id: str) -> RawConversation:
        conv_id = str(data.get("id") or data.get("conversation_id") or fallback_id)
        title = str(data.get("title") or data.get("name") or "")
        platform = str(data.get("platform") or "unknown")

        messages: list[RawMessage] = []
        raw_messages = data.get("messages") or data.get("mapping") or []
        is_mapping = isinstance(raw_messages, dict)
        if is_mapping:
            raw_messages = list(raw_messages.values())

        for index, item in enumerate(raw_messages):
            if not isinstance(item, dict):
                continue
            msg = item.get("message") if is_mapping else item
            if not isinstance(msg, dict):
                continue

            role = str(msg.get("role") or msg.get("author", {}).get("role") or "unknown")
            content = msg.get("content") or ""
            if isinstance(content, dict):
                parts = content.get("parts") or []
                content = " ".join(str(part) for part in parts if isinstance(part, str))
            elif isinstance(content, list):
                content = " ".join(str(part) for part in content if isinstance(part, str))
            else:
                content = str(content)

            if not content.strip():
                continue

            messages.append(
                RawMessage(
                    msg_id=str(msg.get("id") or f"{conv_id}_{index}"),
                    role=role,
                    content=content,
                    timestamp=str(msg.get("create_time") or msg.get("timestamp") or ""),
                    conversation_id=conv_id,
                    platform=platform,
                )
            )

        start_time = parse_raw_timestamp(data.get("create_time"))
        end_time = parse_raw_timestamp(data.get("update_time"))
        if start_time is None and messages:
            start_time = parse_raw_timestamp(messages[0].timestamp)
        if end_time is None and messages:
            end_time = parse_raw_timestamp(messages[-1].timestamp)

        turns: list[RawTurn] = []
        raw_turns = data.get("turns") or []
        if isinstance(raw_turns, list):
            for item in raw_turns:
                if not isinstance(item, dict):
                    continue
                try:
                    turns.append(RawTurn.model_validate(item))
                except Exception:
                    continue
        if not turns:
            turns = build_raw_turns(conv_id, messages)

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
        text = path.read_text(encoding="utf-8")
        messages: list[RawMessage] = []
        current_role = "user"
        current_lines: list[str] = []

        role_pattern = re.compile(
            r"^\s*[*#]*\s*(user|human|assistant|claude|gpt|ai|system)\s*[*#]*\s*[:-]?\s*$",
            re.IGNORECASE,
        )

        for line in text.splitlines():
            match = role_pattern.match(line)
            if match:
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
                raw_role = match.group(1).lower()
                current_role = "user" if raw_role in {"user", "human"} else "assistant"
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
                turns=build_raw_turns(path.stem, messages),
            )
        ]

    def search(
        self,
        conversations: list[RawConversation],
        query: str,
        limit: int = 10,
    ) -> list[tuple[RawConversation, RawMessage]]:
        """Keyword search across all messages."""
        query_lower = query.lower()
        results: list[tuple[RawConversation, RawMessage, int]] = []
        for conv in conversations:
            for msg in conv.messages:
                content_lower = msg.content.lower()
                if query_lower in content_lower:
                    score = content_lower.count(query_lower)
                    results.append((conv, msg, score))
        results.sort(key=lambda row: row[2], reverse=True)
        return [(conv, msg) for conv, msg, _score in results[:limit]]

    def topic_chunks(
        self,
        conversations: list[RawConversation],
        topics: list[str],
        chunk_size: int = 8,
    ) -> Iterator[tuple[str, str]]:
        """Yield retrieval chunks for topic-focused keyword search."""
        for topic in topics:
            hits = self.search(conversations, topic, limit=20)
            seen_convs: set[str] = set()
            for conv, _msg in hits:
                if conv.conv_id in seen_convs:
                    continue
                seen_convs.add(conv.conv_id)
                messages = conv.messages
                for start in range(0, len(messages), chunk_size):
                    chunk = messages[start : start + chunk_size]
                    text = "\n".join(
                        f"[{message.role.upper()}]: {message.content[:500]}"
                        for message in chunk
                    )
                    yield topic, f"[Conv: {conv.title or conv.conv_id}]\n{text}"


__all__ = ["L0RawLayer"]
