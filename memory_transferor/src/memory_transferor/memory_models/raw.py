from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class RawMessage(BaseModel):
    """Raw platform message used by importer adapters."""

    msg_id: str
    role: str
    content: str
    timestamp: str = ""
    conversation_id: str = ""
    platform: str = "unknown"


class RawTurn(BaseModel):
    """Compatibility turn: one user message and its following assistant messages."""

    turn_id: str
    conversation_id: str
    message_ids: list[str] = Field(default_factory=list)


def parse_raw_timestamp(value: object) -> datetime | None:
    """Convert a platform timestamp into UTC datetime when possible."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def build_raw_turns(conversation_id: str, messages: list[RawMessage]) -> list[RawTurn]:
    """Build turn refs from a message stream.

    Consecutive assistant messages stay with the previous user message. A new
    user message starts the next raw turn.
    """
    turns: list[RawTurn] = []
    current_message_ids: list[str] = []

    for index, message in enumerate(messages):
        role = str(message.role or "").strip().lower()
        message_id = message.msg_id or f"{conversation_id}_{index}"
        if role == "user" and current_message_ids:
            turns.append(
                RawTurn(
                    turn_id=f"{conversation_id}:turn:{len(turns)}",
                    conversation_id=conversation_id,
                    message_ids=current_message_ids[:],
                )
            )
            current_message_ids = [message_id]
        else:
            current_message_ids.append(message_id)

    if current_message_ids:
        turns.append(
            RawTurn(
                turn_id=f"{conversation_id}:turn:{len(turns)}",
                conversation_id=conversation_id,
                message_ids=current_message_ids[:],
            )
        )

    return turns


class RawConversation(BaseModel):
    """Imported raw conversation adapter used by the backend organize path."""

    conv_id: str
    platform: str
    title: str = ""
    messages: list[RawMessage]
    turns: list[RawTurn] = Field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        if not self.turns:
            self.turns = build_raw_turns(self.conv_id, self.messages)

    def user_messages(self) -> list[RawMessage]:
        return [message for message in self.messages if message.role == "user"]

    def assistant_messages(self) -> list[RawMessage]:
        return [message for message in self.messages if message.role == "assistant"]

    def full_text(self) -> str:
        return "\n\n".join(
            f"[{message.role.upper()}]: {message.content}" for message in self.messages
        )

    def word_count(self) -> int:
        return len(self.full_text().split())


class RawChatTurn(BaseModel):
    """Smallest raw evidence unit: one user-assistant exchange."""

    turn_id: str
    session_id: str
    timestamp: datetime | None = None
    user_text: str = ""
    assistant_text: str = ""
    status: str = "complete"

    def text(self) -> str:
        parts: list[str] = []
        if self.user_text:
            parts.append(f"USER: {self.user_text}")
        if self.assistant_text:
            parts.append(f"ASSISTANT: {self.assistant_text}")
        return "\n".join(parts)


class RawChatSession(BaseModel):
    """One captured chat page/session, grouping raw turns."""

    session_id: str
    platform: str = "unknown"
    title: str = ""
    url: str = ""
    timestamp: datetime | None = None
    turns: list[RawChatTurn] = Field(default_factory=list)
