"""
Generation runner for LongMemEval.

Three modes:
  retrieval-augmented   Use L0 keyword retrieval to find relevant sessions,
                        then answer with Claude.

  full-history          Pass the entire haystack as context (truncated to
                        fit the model's context window).

  memory-wiki           Build an L2 MWiki from the haystack first, inject
                        the bootstrap prompt, then answer. This is the full
                        Portable Personal Memory Layer pipeline.

Output is a JSONL file where each line is:
  {"question_id": "...", "hypothesis": "..."}

Compatible with LongMemEval's evaluate_qa.py.

Usage:
  python generation_runner.py \\
    --data data/longmemeval_oracle.json \\
    --output results/hypothesis.jsonl \\
    --mode retrieval-augmented \\
    --top-k 5
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import click
from tqdm import tqdm

from llm_memory_transferor.layers.l2_wiki import L2Wiki
from llm_memory_transferor.models import EpisodicMemory
from llm_memory_transferor.processors.memory_builder import MemoryBuilder
from llm_memory_transferor.utils.llm_client import LLMClient

from .adapter import (
    entry_to_conversations,
    format_full_history,
    format_retrieved_context,
    load_benchmark,
    retrieve_for_entry,
)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_QA_SYSTEM = """You are a memory assistant with access to a user's conversation history.
Answer the user's question accurately and concisely based ONLY on what appears in the history.

Rules:
- If the answer is directly stated, give it precisely.
- If you need to reason across multiple sessions, do so step by step.
- If the information is not present in the provided history, say: "I don't have that information."
- Do not guess or fabricate details.
- Keep your answer brief — one to three sentences unless the question requires more."""

_QA_TEMPORAL_SYSTEM = """You are a memory assistant with access to a user's conversation history.
Answer the user's time-based question based ONLY on what appears in the history.

Rules:
- Pay careful attention to timestamps on sessions.
- Off-by-one errors in days/weeks/months are acceptable.
- If the information is not present in the provided history, say: "I don't have that information."
- Keep your answer brief."""

_QA_ABSTENTION_SYSTEM = """You are a memory assistant with access to a user's conversation history.
The user is asking a question. Determine whether the answer can be found in the provided history.

Rules:
- If the answer is present, provide it concisely.
- If the answer is NOT present in the provided history, respond: "I don't have that information."
- Do not guess or fabricate details."""

_WIKI_QA_SYSTEM_TEMPLATE = """You are a memory assistant. You have a structured memory profile of the user
and access to relevant conversation excerpts.

{wiki_context}

Answer questions accurately and concisely based on this memory. If the answer is not in your
memory or the conversation excerpts, say: "I don't have that information." """


def _get_system_prompt(question_type: str, wiki_context: str = "") -> str:
    if wiki_context:
        return _WIKI_QA_SYSTEM_TEMPLATE.format(wiki_context=wiki_context)
    if "temporal" in question_type:
        return _QA_TEMPORAL_SYSTEM
    if "abstention" in question_type or question_type.endswith("abs"):
        return _QA_ABSTENTION_SYSTEM
    return _QA_SYSTEM


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def answer_retrieval_augmented(
    entry: dict, llm: LLMClient, top_k: int, max_context_chars: int
) -> str:
    """Retrieve relevant sessions, then answer."""
    ranked_items = retrieve_for_entry(entry, top_k=top_k * 3, granularity="session")
    context = format_retrieved_context(entry, ranked_items, top_k=top_k)

    # Truncate to budget
    context = context[:max_context_chars]

    question = entry["question"]
    question_date = entry.get("question_date", "")
    date_suffix = f"\n\nQuestion date: {question_date}" if question_date else ""

    system = _get_system_prompt(entry.get("question_type", ""))
    user_msg = f"CONVERSATION HISTORY:\n{context}{date_suffix}\n\nQUESTION: {question}"

    return llm.summarize(system, user_msg, temperature=0.0)


def answer_full_history(
    entry: dict, llm: LLMClient, max_context_chars: int
) -> str:
    """Pass truncated full haystack as context, then answer."""
    context = format_full_history(entry, history_format="nl")
    context = context[:max_context_chars]

    question = entry["question"]
    question_date = entry.get("question_date", "")
    date_suffix = f"\n\nQuestion date: {question_date}" if question_date else ""

    system = _get_system_prompt(entry.get("question_type", ""))
    user_msg = f"CONVERSATION HISTORY:\n{context}{date_suffix}\n\nQUESTION: {question}"

    return llm.summarize(system, user_msg, temperature=0.0)


def answer_memory_wiki(
    entry: dict, llm: LLMClient, top_k: int, max_context_chars: int
) -> str:
    """
    Full pipeline: build L2 MWiki from haystack, generate bootstrap,
    then answer using wiki context + retrieved sessions.
    """
    from llm_memory_transferor.exporters.bootstrap_generator import BootstrapGenerator
    from llm_memory_transferor.layers.l1_signals import L1SignalLayer
    from llm_memory_transferor.layers.l2_wiki import L2Wiki
    from llm_memory_transferor.processors.memory_builder import MemoryBuilder

    convs, _ = entry_to_conversations(entry)

    # Build wiki in a temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        wiki = L2Wiki(Path(tmpdir) / "wiki")
        builder = MemoryBuilder(llm=llm, wiki=wiki)
        l1 = L1SignalLayer()  # No external signals for benchmark

        try:
            builder.build(convs, l1, on_progress=None)
        except Exception:
            # Fall back to retrieval-augmented if wiki build fails
            return answer_retrieval_augmented(entry, llm, top_k, max_context_chars)

        bootstrap = BootstrapGenerator(wiki).generate(
            target_platform="generic", max_tokens=400
        )

    # Retrieve relevant sessions
    ranked_items = retrieve_for_entry(entry, top_k=top_k * 3, granularity="session")
    retrieved_context = format_retrieved_context(entry, ranked_items, top_k=top_k)
    retrieved_context = retrieved_context[:max_context_chars]

    question = entry["question"]
    question_date = entry.get("question_date", "")
    date_suffix = f"\n\nQuestion date: {question_date}" if question_date else ""

    system = _get_system_prompt(entry.get("question_type", ""), wiki_context=bootstrap)
    user_msg = f"RELEVANT CONVERSATION EXCERPTS:\n{retrieved_context}{date_suffix}\n\nQUESTION: {question}"

    return llm.summarize(system, user_msg, temperature=0.0)


def _build_popup_memory_payload_for_entry(
    entry: dict,
    llm: LLMClient,
    model: str | None,
    backend: str | None,
    api_key: str | None,
    base_url: str | None,
) -> dict:
    """Simulate the backend organize flow triggered by the popup."""
    from backend_service import app as backend_app

    convs, _ = entry_to_conversations(entry)

    with tempfile.TemporaryDirectory() as tmpdir:
        storage_root = Path(tmpdir) / "storage"
        settings = {
            "api_provider": backend or llm.backend_name,
            "api_key": api_key or "",
            "api_base_url": base_url or "",
            "api_model": model or llm.model,
            "storage_path": str(storage_root),
            "keep_updated": True,
            "realtime_update": False,
            "detailed_injection": False,
            "last_sync_at": None,
            "backend_url": "",
            "saved_skill_ids": [],
            "dismissed_skill_ids": [],
        }

        backend_app.persist_raw_conversations(storage_root, convs, platform_hint="longmemeval")
        job = backend_app.create_job("memory_organize", status="running")
        backend_app._run_organize_job(job["id"], settings)
        final_job = backend_app.JOB_REGISTRY.get(job["id"], {})
        if final_job.get("status") != "completed":
            raise RuntimeError(final_job.get("error") or "Popup organize flow failed")

        selected_ids = [
            "profile:default",
            "preferences:default",
            "projects:default",
            "workflows:default",
            "persistent:default",
        ]
        return backend_app.build_selected_memory_payload(
            settings,
            selected_ids,
            include_episodic_evidence=True,
            detailed_injection=False,
        )


def answer_popup_organized_memory(
    entry: dict,
    llm: LLMClient,
    top_k: int,
    max_context_chars: int,
    model: str | None,
    backend: str | None,
    api_key: str | None,
    base_url: str | None,
) -> str:
    """
    Simulate clicking "Organize Memory" in the popup, then answer using the
    organized memory package plus retrieved conversation evidence.
    """
    try:
        memory_payload = _build_popup_memory_payload_for_entry(
            entry, llm, model, backend, api_key, base_url
        )
    except Exception:
        return answer_memory_wiki(entry, llm, top_k, max_context_chars)

    ranked_items = retrieve_for_entry(entry, top_k=top_k * 3, granularity="session")
    retrieved_context = format_retrieved_context(entry, ranked_items, top_k=top_k)
    retrieved_context = retrieved_context[:max_context_chars]

    memory_context = json.dumps(memory_payload, ensure_ascii=False, indent=2)
    memory_context = memory_context[:max_context_chars]

    question = entry["question"]
    question_date = entry.get("question_date", "")
    date_suffix = f"\n\nQuestion date: {question_date}" if question_date else ""

    system = _get_system_prompt(
        entry.get("question_type", ""),
        wiki_context=f"ORGANIZED MEMORY PACKAGE:\n{memory_context}",
    )
    user_msg = (
        f"RELEVANT CONVERSATION EXCERPTS:\n{retrieved_context}"
        f"{date_suffix}\n\nQUESTION: {question}"
    )
    return llm.summarize(system, user_msg, temperature=0.0)


def _build_episodes_for_entry(entry: dict, llm: LLMClient) -> list[EpisodicMemory]:
    """Build episodic memories directly from the haystack without deriving L2 memory."""
    convs, _ = entry_to_conversations(entry)

    with tempfile.TemporaryDirectory() as tmpdir:
        builder = MemoryBuilder(llm=llm, wiki=L2Wiki(Path(tmpdir) / "wiki"))
        episodes: list[EpisodicMemory] = []
        for conv in convs:
            if len(conv.full_text().strip()) < 30:
                continue
            episodes.extend(builder._build_episodes(conv))
        return episodes


def _retrieve_episode_summaries(
    episodes: list[EpisodicMemory],
    question: str,
    top_k: int,
) -> list[EpisodicMemory]:
    """Simple keyword retrieval over episode summaries and metadata."""
    question_lower = question.lower()
    question_tokens = set(question_lower.split())

    scored: list[tuple[float, EpisodicMemory]] = []
    for ep in episodes:
        haystack = " ".join(
            part for part in [
                ep.topic,
                ep.summary,
                " ".join(ep.key_decisions),
                " ".join(ep.open_issues),
                " ".join(ep.topics_covered),
                " ".join(ep.relates_to_projects),
                " ".join(ep.relates_to_workflows),
            ] if part
        ).lower()
        if not haystack.strip():
            continue
        score = sum(1 for tok in question_tokens if tok in haystack)
        if question_lower and question_lower in haystack:
            score += len(question_tokens)
        if ep.related_project and ep.related_project.lower() in question_lower:
            score += 2
        scored.append((score, ep))

    scored.sort(
        key=lambda item: (
            item[0],
            item[1].time_range_end or item[1].time_range_start or item[1].created_at,
        ),
        reverse=True,
    )
    return [ep for _, ep in scored[:top_k]]


def _format_episodic_context(episodes: list[EpisodicMemory]) -> str:
    parts: list[str] = []
    for ep in episodes:
        ts = ep.time_range_start.strftime("%Y-%m-%d") if ep.time_range_start else "unknown date"
        lines = [
            f"=== Episode {ep.episode_id} [{ts}] ===",
            f"Session: {ep.conv_id or 'unknown'}",
            f"Title: {ep.topic or 'untitled'}",
            f"Summary: {ep.summary or 'N/A'}",
        ]
        if ep.topics_covered:
            lines.append(f"Topics: {', '.join(ep.topics_covered[:8])}")
        if ep.key_decisions:
            lines.append(f"Key decisions: {'; '.join(ep.key_decisions[:4])}")
        if ep.open_issues:
            lines.append(f"Open issues: {'; '.join(ep.open_issues[:4])}")
        if ep.relates_to_projects:
            lines.append(f"Projects: {', '.join(ep.relates_to_projects[:4])}")
        if ep.relates_to_workflows:
            lines.append(f"Workflows: {', '.join(ep.relates_to_workflows[:4])}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def answer_episodic_memory(
    entry: dict, llm: LLMClient, top_k: int, max_context_chars: int
) -> str:
    """Answer from retrieved episodic memories only, without L2 aggregation."""
    episodes = _build_episodes_for_entry(entry, llm)
    if not episodes:
        return answer_retrieval_augmented(entry, llm, top_k, max_context_chars)

    retrieved = _retrieve_episode_summaries(episodes, entry["question"], top_k=top_k)
    if not retrieved:
        return answer_retrieval_augmented(entry, llm, top_k, max_context_chars)

    context = _format_episodic_context(retrieved)[:max_context_chars]
    question = entry["question"]
    question_date = entry.get("question_date", "")
    date_suffix = f"\n\nQuestion date: {question_date}" if question_date else ""

    system = _get_system_prompt(entry.get("question_type", ""))
    user_msg = f"EPISODIC MEMORY:\n{context}{date_suffix}\n\nQUESTION: {question}"
    return llm.summarize(system, user_msg, temperature=0.0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--data", required=True, type=click.Path(exists=True),
              help="Path to LongMemEval JSON benchmark file.")
@click.option("--output", required=True, type=click.Path(),
              help="Output JSONL path with hypotheses.")
@click.option("--mode", default="retrieval-augmented", show_default=True,
              type=click.Choice(["retrieval-augmented", "full-history", "episodic-memory", "memory-wiki", "popup-organize"]),
              help="Answering mode.")
@click.option("--top-k", default=5, show_default=True,
              help="Number of retrieved sessions to use as context (retrieval modes).")
@click.option("--model", default=None, show_default=True,
              help="Model ID to use (overrides backend default).")
@click.option("--backend", default=None,
              type=click.Choice(["anthropic", "openai", "openai_compat"]),
              help="LLM backend. Auto-detected from env vars if omitted.")
@click.option("--api-key", default=None, envvar="MWIKI_API_KEY",
              help="API key (overrides ANTHROPIC_API_KEY / OPENAI_API_KEY).")
@click.option("--base-url", default=None, envvar="OPENAI_BASE_URL",
              help="Base URL for openai_compat backend (e.g. http://localhost:11434/v1).")
@click.option("--max-context-chars", default=60_000, show_default=True,
              help="Maximum characters of conversation history to pass to LLM.")
@click.option("--limit", default=None, type=int,
              help="Evaluate only first N entries.")
@click.option("--resume/--no-resume", default=True, show_default=True,
              help="Skip question IDs already in output file.")
def run_generation(
    data: str,
    output: str,
    mode: str,
    top_k: int,
    model: str | None,
    backend: str | None,
    api_key: str | None,
    base_url: str | None,
    max_context_chars: int,
    limit: int | None,
    resume: bool,
) -> None:
    """Generate answers for LongMemEval questions and write hypothesis JSONL."""
    from llm_memory_transferor.utils.llm_client import _detect_backend
    entries = load_benchmark(Path(data))
    if limit:
        entries = entries[:limit]

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load already-answered question IDs for resuming
    done_ids: set[str] = set()
    if resume and output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(line)["question_id"])
            except (json.JSONDecodeError, KeyError):
                pass
        click.echo(f"Resuming: {len(done_ids)} questions already answered.")

    llm = LLMClient(api_key=api_key, model=model, backend=backend or _detect_backend(), base_url=base_url)

    with output_path.open("a", encoding="utf-8") as out_f:
        for entry in tqdm(entries, desc=f"Generating [{mode}]"):
            qid: str = entry["question_id"]
            if qid in done_ids:
                continue

            try:
                if mode == "retrieval-augmented":
                    hypothesis = answer_retrieval_augmented(
                        entry, llm, top_k, max_context_chars
                    )
                elif mode == "full-history":
                    hypothesis = answer_full_history(entry, llm, max_context_chars)
                elif mode == "episodic-memory":
                    hypothesis = answer_episodic_memory(
                        entry, llm, top_k, max_context_chars
                    )
                elif mode == "memory-wiki":
                    hypothesis = answer_memory_wiki(entry, llm, top_k, max_context_chars)
                elif mode == "popup-organize":
                    hypothesis = answer_popup_organized_memory(
                        entry,
                        llm,
                        top_k,
                        max_context_chars,
                        model,
                        backend,
                        api_key,
                        base_url,
                    )
                else:
                    raise ValueError(f"Unknown mode: {mode}")
            except Exception as e:
                hypothesis = f"[ERROR: {e}]"

            out_f.write(
                json.dumps({"question_id": qid, "hypothesis": hypothesis}, ensure_ascii=False)
                + "\n"
            )
            out_f.flush()

    click.echo(f"\nHypotheses written to: {output_path}")
    click.echo("Next step: run LongMemEval's evaluate_qa.py to score with GPT-4o.")


if __name__ == "__main__":
    run_generation()
