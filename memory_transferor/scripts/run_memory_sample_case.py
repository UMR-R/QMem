from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from memory_transferor.memory_builders import EpisodeBuilder, PersistentBuilder
from memory_transferor.episode_graph import EpisodeGraphBuilder
from memory_transferor.memory_models import RawChatSession, RawChatTurn
from memory_transferor.memory_store import MemoryWorkspace
from memory_transferor.runtime import LLMClient, parse_timestamp


def _turns_from_messages(session: dict) -> list[RawChatTurn]:
    turns: list[RawChatTurn] = []
    pending_user: str | None = None
    turn_index = 0
    session_id = str(session.get("session_id") or "session")
    timestamp = parse_timestamp(session.get("time"))
    for msg in session.get("messages", []):
        role = str(msg.get("role") or "").lower()
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if role in {"user", "human"}:
            if pending_user is not None:
                turns.append(
                    RawChatTurn(
                        turn_id=f"{session_id}:turn:{turn_index}",
                        session_id=session_id,
                        timestamp=timestamp,
                        user_text=pending_user,
                        status="missing_assistant",
                    )
                )
                turn_index += 1
            pending_user = content
        elif role in {"assistant", "ai", "gpt"}:
            turns.append(
                RawChatTurn(
                    turn_id=f"{session_id}:turn:{turn_index}",
                    session_id=session_id,
                    timestamp=timestamp,
                    user_text=pending_user or "",
                    assistant_text=content,
                    status="complete" if pending_user else "missing_user",
                )
            )
            turn_index += 1
            pending_user = None
    if pending_user is not None:
        turns.append(
            RawChatTurn(
                turn_id=f"{session_id}:turn:{turn_index}",
                session_id=session_id,
                timestamp=timestamp,
                user_text=pending_user,
                status="missing_assistant",
            )
        )
    return turns


def load_sample_sessions(path: Path) -> tuple[list[RawChatSession], dict[str, list[str]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sessions: list[RawChatSession] = []
    expected: dict[str, list[str]] = {}
    for case in data.get("cases", []):
        case_id = str(case.get("case_id") or "case")
        expected[case_id] = [
            str(item.get("type") or "")
            for item in case.get("expected_memory_items", [])
            if item.get("type")
        ]
        for raw_session in case.get("sessions", []):
            session_id = str(raw_session.get("session_id") or case_id)
            sessions.append(
                RawChatSession(
                    session_id=session_id,
                    platform=str(raw_session.get("platform") or "unknown"),
                    title=f"{case_id} / {session_id}",
                    timestamp=parse_timestamp(raw_session.get("time")),
                    turns=_turns_from_messages(raw_session),
                )
            )
    return sessions, expected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--graph-only", action="store_true", help="Stop after raw -> episodes -> episode graph.")
    args = parser.parse_args()

    sessions, expected = load_sample_sessions(args.sample)
    output = args.output or Path(tempfile.mkdtemp(prefix="memory_transferor_sample_"))
    workspace = MemoryWorkspace(output / "memory")
    workspace.ensure()
    workspace.raw.save_sessions(sessions)

    raw_episodes = EpisodeBuilder().build(sessions)
    episode_graph = EpisodeGraphBuilder().build(raw_episodes)
    episodes = episode_graph.episodes
    workspace.episodes.save(episodes, episode_graph.groups)

    print(f"OUTPUT_DIR={output}")
    print(f"SESSIONS={len(sessions)}")
    print(f"TURNS={sum(len(session.turns) for session in sessions)}")
    print(f"EPISODES={len(episodes)}")
    print(f"CONNECTION_GROUPS={len(episode_graph.groups)}")
    if args.graph_only:
        group_types: dict[str, int] = {}
        for group in episode_graph.groups:
            group_types[group.relation] = group_types.get(group.relation, 0) + 1
        print("GROUP_TYPES=" + json.dumps(group_types, ensure_ascii=False, sort_keys=True))
        print(
            "GROUP_SIZES="
            + json.dumps(
                sorted([len(group.episode_ids) for group in episode_graph.groups], reverse=True)
            )
        )
        return

    llm = LLMClient(api_key=args.api_key, base_url=args.base_url, model=args.model)
    persistent_items = PersistentBuilder(llm).build(episodes, episode_graph.groups)
    workspace.persistent.save_items(persistent_items)

    actual_types: dict[str, int] = {}
    for item in persistent_items:
        actual_types[item.type] = actual_types.get(item.type, 0) + 1

    print(f"PERSISTENT_ITEMS={len(persistent_items)}")
    print("ACTUAL_TYPES=" + json.dumps(actual_types, ensure_ascii=False, sort_keys=True))
    print("EXPECTED_TYPES=" + json.dumps(expected, ensure_ascii=False, sort_keys=True))
    print("ITEMS=")
    print(json.dumps([item.model_dump(mode="json") for item in persistent_items], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
