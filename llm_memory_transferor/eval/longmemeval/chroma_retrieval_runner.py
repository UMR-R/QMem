"""ChromaDB-based retrieval benchmark runner for LongMemEval."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import click
from tqdm import tqdm

from llm_memory_transferor.retrieval import (
    ChromaRetrievalIndex,
    build_episode_documents,
    build_raw_session_documents,
    build_raw_turn_documents,
)
from llm_memory_transferor.utils.llm_client import LLMClient, _detect_backend

from .adapter import entry_to_conversations, load_benchmark
from .generation_runner import _build_episodes_for_entry
from .retrieval_runner import compute_retrieval_metrics


def _ensure_episode_backend_configured(
    *,
    backend: str | None,
    api_key: str | None,
    base_url: str | None,
) -> None:
    """Fail fast with a clear message when episode extraction has no LLM config."""
    if backend == "anthropic":
        if api_key or os.environ.get("ANTHROPIC_API_KEY"):
            return
    elif backend == "openai":
        if api_key or os.environ.get("OPENAI_API_KEY"):
            return
    elif backend == "openai_compat":
        if base_url or os.environ.get("OPENAI_BASE_URL"):
            return
    elif any(
        [
            api_key,
            base_url,
            os.environ.get("MWIKI_API_KEY"),
            os.environ.get("OPENAI_API_KEY"),
            os.environ.get("ANTHROPIC_API_KEY"),
            os.environ.get("OPENAI_BASE_URL"),
            os.environ.get("MWIKI_LLM_BACKEND"),
        ]
    ):
        return

    raise click.UsageError(
        "Episode mode requires an LLM backend for episode extraction. "
        "Set --backend plus the matching credentials, or configure "
        "ANTHROPIC_API_KEY / OPENAI_API_KEY / OPENAI_BASE_URL."
    )


def _rank_documents_to_sessions(
    rows: list[dict[str, Any]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """Deduplicate ranked Chroma results down to session-level corpus ids."""
    ranked_items: list[dict[str, Any]] = []
    seen_corpus_ids: set[str] = set()
    for row in rows:
        corpus_id = str(row.get("corpus_id") or row.get("conversation_id") or "").strip()
        if not corpus_id or corpus_id in seen_corpus_ids:
            continue
        seen_corpus_ids.add(corpus_id)
        ranked_items.append(
            {
                "corpus_id": corpus_id,
                "doc_id": row.get("doc_id", ""),
                "text": row.get("text", ""),
                "timestamp": row.get("timestamp", ""),
                "doc_type": row.get("doc_type", ""),
                "episode_id": row.get("episode_id", ""),
                "distance": row.get("distance"),
                "turn_refs": row.get("turn_refs", ""),
            }
        )
        if len(ranked_items) >= top_k:
            break
    return ranked_items


def _build_documents_for_entry(
    entry: dict[str, Any],
    *,
    mode: str,
    llm: LLMClient | None,
) -> list[dict[str, Any]]:
    conversations, _ = entry_to_conversations(entry)
    if mode == "raw-session":
        return build_raw_session_documents(conversations, user_only=True)
    if mode == "raw-turn":
        return build_raw_turn_documents(conversations, user_only=True)
    if mode == "episode":
        if llm is None:
            raise ValueError("Episode retrieval mode requires an LLM client for episode extraction.")
        episodes = _build_episodes_for_entry(entry, llm)
        return build_episode_documents(episodes)
    raise ValueError(f"Unknown retrieval mode: {mode}")


@click.command("retrieve-chroma")
@click.option("--data", required=True, type=click.Path(exists=True),
              help="Path to LongMemEval JSON benchmark file.")
@click.option("--output", required=True, type=click.Path(),
              help="Output JSONL path with Chroma retrieval results.")
@click.option("--mode", default="raw-session", show_default=True,
              type=click.Choice(["raw-session", "raw-turn", "episode"]),
              help="Document type to index in Chroma.")
@click.option("--top-k", default=50, show_default=True,
              help="Number of session-level ranked items to keep per query.")
@click.option("--fetch-k", default=200, show_default=True,
              help="Number of raw Chroma hits to fetch before session deduplication.")
@click.option("--limit", default=None, type=int,
              help="Evaluate only first N entries.")
@click.option("--skip-abstention/--no-skip-abstention", default=True, show_default=True,
              help="Skip abstention questions (no answer sessions to retrieve).")
@click.option("--resume/--no-resume", default=True, show_default=True,
              help="Skip question IDs already present in the output JSONL.")
@click.option("--persist-dir", default=None, type=click.Path(path_type=Path),
              help="Optional persistent Chroma directory. If omitted, uses an ephemeral DB per query.")
@click.option("--backend", default=None,
              type=click.Choice(["anthropic", "openai", "openai_compat"]),
              help="LLM backend for episode extraction mode.")
@click.option("--model", default=None,
              help="Model ID for episode extraction mode.")
@click.option("--api-key", default=None, envvar="MWIKI_API_KEY",
              help="API key for episode extraction mode.")
@click.option("--base-url", default=None, envvar="OPENAI_BASE_URL",
              help="Base URL for openai_compat backend.")
def run_chroma_retrieval(
    data: str,
    output: str,
    mode: str,
    top_k: int,
    fetch_k: int,
    limit: int | None,
    skip_abstention: bool,
    resume: bool,
    persist_dir: Path | None,
    backend: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
) -> None:
    """Run a ChromaDB retrieval benchmark aligned to LongMemEval metrics."""
    entries = load_benchmark(Path(data))
    if limit:
        entries = entries[:limit]

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    done_ids: set[str] = set()
    if resume and output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(line)["question_id"])
            except (json.JSONDecodeError, KeyError):
                continue

    llm: LLMClient | None = None
    if mode == "episode":
        _ensure_episode_backend_configured(
            backend=backend,
            api_key=api_key,
            base_url=base_url,
        )
        llm = LLMClient(
            api_key=api_key,
            model=model,
            backend=backend or _detect_backend(),
            base_url=base_url,
        )

    all_metrics: dict[str, list[float]] = {}
    skipped = 0
    scratch_root = output_path.parent / ".chroma_tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    model_cache_dir = scratch_root / ".model_cache"
    model_cache_dir.mkdir(parents=True, exist_ok=True)

    mode_flag = "a" if resume and output_path.exists() else "w"
    with output_path.open(mode_flag, encoding="utf-8") as out_f:
        for idx, entry in enumerate(tqdm(entries, desc=f"Chroma retrieval [{mode}]")):
            question_id = entry["question_id"]
            if question_id in done_ids:
                continue
            is_abstention = question_id.endswith("_abs")
            if skip_abstention and is_abstention:
                skipped += 1
                out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                continue

            answer_session_ids = entry.get("answer_session_ids") or []
            documents = _build_documents_for_entry(entry, mode=mode, llm=llm)

            if persist_dir is None:
                temp_dir = scratch_root / f"{mode}_{question_id}"
                index = ChromaRetrievalIndex(
                    collection_name=f"lme_{mode}_{idx}",
                    persist_dir=temp_dir,
                    model_cache_dir=model_cache_dir,
                )
                index.add_documents(documents)
                raw_hits = index.query(entry["question"], n_results=fetch_k)
            else:
                index = ChromaRetrievalIndex(
                    collection_name=f"lme_{mode}_{idx}",
                    persist_dir=persist_dir / f"{mode}_{question_id}",
                    model_cache_dir=model_cache_dir,
                )
                index.add_documents(documents)
                raw_hits = index.query(entry["question"], n_results=fetch_k)

            ranked_items = _rank_documents_to_sessions(raw_hits, top_k=top_k)

            entry_metrics: dict[str, float] = {}
            if answer_session_ids and not is_abstention:
                entry_metrics = compute_retrieval_metrics(
                    ranked_items,
                    answer_session_ids,
                    entry,
                    k_values=[1, 3, 5, 10, 30, 50],
                )
                for metric_name, value in entry_metrics.items():
                    all_metrics.setdefault(metric_name, []).append(value)

            augmented = dict(entry)
            augmented["retrieval_results"] = {
                "query": entry["question"],
                "granularity": "session",
                "retrieval_mode": mode,
                "ranked_items": ranked_items,
                "metrics": entry_metrics,
            }
            out_f.write(json.dumps(augmented, ensure_ascii=False) + "\n")

    click.echo(f"\n{'='*60}")
    click.echo(f"Chroma Retrieval Results [{mode}] ({len(entries) - skipped} questions evaluated)")
    click.echo(f"{'='*60}")
    for metric_name in sorted(all_metrics):
        values = all_metrics[metric_name]
        avg = sum(values) / len(values) if values else 0.0
        click.echo(f"  {metric_name:25s}: {avg:.4f}")
    click.echo(f"{'='*60}")
    click.echo(f"Output written to: {output_path}")
