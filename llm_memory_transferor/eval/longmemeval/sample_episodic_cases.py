"""
Sample and inspect LongMemEval cases from the command line.

Given a hypothesis JSONL and the benchmark ground-truth JSON, this tool:
  - groups questions by question_type
  - randomly samples N examples per type
  - prints the original question, GT answer, and model hypothesis
  - prints retrieved session ids and GT session ids
  - rebuilds episodic memories and prints title/summary grouped by session id
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click

from llm_memory_transferor.utils.llm_client import LLMClient

from .adapter import load_benchmark, retrieve_for_entry
from .generation_runner import _build_episodes_for_entry


def _load_hypotheses(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        qid = str(item.get("question_id") or "").strip()
        if not qid:
            continue
        rows[qid] = item
    return rows


def _load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _filter_entry_to_answer_sessions(entry: dict[str, Any]) -> dict[str, Any]:
    answer_session_ids = {
        str(session_id).strip()
        for session_id in entry.get("answer_session_ids", [])
        if str(session_id).strip()
    }
    if not answer_session_ids:
        return dict(entry)

    haystack_session_ids = entry.get("haystack_session_ids", [])
    haystack_sessions = entry.get("haystack_sessions", [])
    haystack_dates = entry.get("haystack_dates", []) or [""] * len(haystack_session_ids)

    filtered_session_ids: list[str] = []
    filtered_sessions: list[list[dict[str, Any]]] = []
    filtered_dates: list[str] = []

    for session_id, session_turns, session_date in zip(
        haystack_session_ids,
        haystack_sessions,
        haystack_dates,
    ):
        if str(session_id).strip() not in answer_session_ids:
            continue
        filtered_session_ids.append(session_id)
        filtered_sessions.append(session_turns)
        filtered_dates.append(session_date)

    filtered_entry = dict(entry)
    filtered_entry["haystack_session_ids"] = filtered_session_ids
    filtered_entry["haystack_sessions"] = filtered_sessions
    filtered_entry["haystack_dates"] = filtered_dates
    return filtered_entry


def _cache_key(entry: dict[str, Any], model: str | None, backend: str | None) -> str:
    payload = {
        "question_id": entry.get("question_id", ""),
        "answer_session_ids": entry.get("answer_session_ids", []),
        "model": model or "",
        "backend": backend or "",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _resolve_llm(
    backend: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    settings_json: Path,
) -> LLMClient:
    settings = _load_settings(settings_json)
    resolved_backend = backend
    resolved_model = model
    resolved_api_key = api_key
    resolved_base_url = base_url

    if settings:
        if not resolved_backend and settings.get("openaiBaseUrl"):
            resolved_backend = "openai_compat"
        if not resolved_model:
            resolved_model = settings.get("openaiChatModel") or settings.get("model")
        if not resolved_api_key:
            resolved_api_key = settings.get("apiKey")
        if not resolved_base_url:
            resolved_base_url = settings.get("openaiBaseUrl")

    return LLMClient(
        backend=resolved_backend,
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
    )


def _print_case(
    entry: dict[str, Any],
    hypothesis: str,
    retrieved_sessions: list[dict[str, Any]],
    session_to_episodes: dict[str, list[Any]],
) -> None:
    click.echo("=" * 100)
    click.echo(f"question_id   : {entry['question_id']}")
    click.echo(f"question_type : {entry.get('question_type', 'unknown')}")
    click.echo("")
    click.echo("Question")
    click.echo(f"  {entry['question']}")
    click.echo("")
    click.echo("Ground Truth")
    click.echo(f"  {entry.get('answer', '')}")
    click.echo("")
    click.echo("Prediction")
    click.echo(f"  {hypothesis}")
    click.echo("")
    click.echo("Retrieved Session IDs")
    click.echo(f"  {', '.join(item['corpus_id'] for item in retrieved_sessions) or '(none)'}")
    click.echo("")
    click.echo("GT Session IDs")
    click.echo(f"  {', '.join(entry.get('answer_session_ids', [])) or '(none)'}")
    click.echo("")
    all_session_ids: list[str] = []
    for sid in entry.get("answer_session_ids", []):
        if sid not in all_session_ids:
            all_session_ids.append(sid)
    for item in retrieved_sessions:
        sid = item["corpus_id"]
        if sid not in all_session_ids:
            all_session_ids.append(sid)

    click.echo("Session-Linked Episodic Memories")
    if not all_session_ids:
        click.echo("  (none)")
    for sid in all_session_ids:
        label_parts: list[str] = []
        if sid in set(entry.get("answer_session_ids", [])):
            label_parts.append("GT")
        if sid in {item["corpus_id"] for item in retrieved_sessions}:
            label_parts.append("retrieved")
        label = f" [{' + '.join(label_parts)}]" if label_parts else ""
        click.echo(f"  Session {sid}{label}")
        episodes = session_to_episodes.get(sid, [])
        if not episodes:
            click.echo("    (no episodic memories)")
            continue
        for idx, ep in enumerate(episodes, 1):
            click.echo(f"    [{idx}] title   : {ep.topic or '(empty)'}")
            click.echo(f"        summary : {ep.summary or '(empty)'}")
    click.echo("")


@click.command("sample-episodic")
@click.option("--predictions", required=True, type=click.Path(exists=True, path_type=Path),
              help="Hypothesis JSONL file with question_id and hypothesis.")
@click.option("--data", default=Path("llm_memory_transferor/data/longmemeval_s_cleaned_sub50.json"),
              show_default=True, type=click.Path(exists=True, path_type=Path),
              help="LongMemEval ground-truth JSON file.")
@click.option("--per-type", default=2, show_default=True, type=int,
              help="Random samples to print per question_type.")
@click.option("--top-k", default=5, show_default=True, type=int,
              help="Number of retrieved sessions to show.")
@click.option("--seed", default=7, show_default=True, type=int,
              help="Random seed for reproducible sampling.")
@click.option("--backend", default=None,
              type=click.Choice(["anthropic", "openai", "openai_compat"]),
              help="LLM backend for rebuilding episodic summaries.")
@click.option("--model", default=None,
              help="Model ID for rebuilding episodic summaries.")
@click.option("--api-key", default=None, help="Optional API key override.")
@click.option("--base-url", default=None, help="Optional base URL override.")
@click.option("--settings-json", default=Path("backend_service/.state/settings.json"),
              show_default=True, type=click.Path(path_type=Path),
              help="Fallback local settings file for backend/model/api key.")
@click.option("--cache-dir", default=Path("llm_memory_transferor/.cache/sample_episodic_cases"),
              show_default=True, type=click.Path(path_type=Path),
              help="Directory for cached episodic-memory rebuild results.")
def sample_episodic_cases(
    predictions: Path,
    data: Path,
    per_type: int,
    top_k: int,
    seed: int,
    backend: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    settings_json: Path,
    cache_dir: Path,
) -> None:
    """Print sampled LongMemEval inspection cases by question type."""
    hypothesis_map = _load_hypotheses(predictions)
    benchmark = load_benchmark(data)
    matched_entries = [entry for entry in benchmark if entry["question_id"] in hypothesis_map]

    if not matched_entries:
        raise click.ClickException("No overlapping question_id values found between predictions and data.")

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in matched_entries:
        by_type[entry.get("question_type", "unknown")].append(entry)

    llm = _resolve_llm(backend, model, api_key, base_url, settings_json)
    rng = random.Random(seed)
    cache_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Loaded {len(hypothesis_map)} predictions")
    click.echo(f"Matched {len(matched_entries)} benchmark entries")
    click.echo(f"Question types: {len(by_type)}")
    click.echo("")

    for question_type in sorted(by_type):
        entries = by_type[question_type]
        sample_size = min(per_type, len(entries))
        sampled = rng.sample(entries, sample_size)
        click.echo("#" * 100)
        click.echo(f"QUESTION TYPE: {question_type} (showing {sample_size}/{len(entries)})")
        click.echo("#" * 100)
        click.echo("")

        for entry in sampled:
            prediction_row = hypothesis_map[entry["question_id"]]
            hypothesis = str(prediction_row.get("hypothesis", "")).strip()
            retrieved_sessions = retrieve_for_entry(entry, top_k=top_k, granularity="session")
            if isinstance(prediction_row.get("episodic_memory"), list):
                episode_rows = prediction_row.get("episodic_memory", [])
            else:
                filtered_entry = _filter_entry_to_answer_sessions(entry)
                cache_path = cache_dir / f"{entry['question_id']}_{_cache_key(filtered_entry, llm.model, llm.backend_name)}.json"
                if cache_path.exists():
                    episode_rows = json.loads(cache_path.read_text(encoding="utf-8"))
                else:
                    episodes = _build_episodes_for_entry(filtered_entry, llm)
                    episode_rows = [ep.model_dump(mode="json") for ep in episodes]
                    cache_path.write_text(
                        json.dumps(episode_rows, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            session_to_episodes: dict[str, list[Any]] = defaultdict(list)
            for ep in episode_rows:
                session_to_episodes[str(ep.get("conv_id") or "")].append(
                    SimpleNamespace(
                        topic=ep.get("topic", ""),
                        summary=ep.get("summary", ""),
                    )
                )
            _print_case(entry, hypothesis, retrieved_sessions, session_to_episodes)


if __name__ == "__main__":
    sample_episodic_cases()
