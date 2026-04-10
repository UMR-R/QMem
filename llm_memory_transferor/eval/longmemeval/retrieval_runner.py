"""
Retrieval runner for LongMemEval.

Produces a JSONL file with `retrieval_results` added to each entry,
compatible with LongMemEval's existing eval_utils.py.

Usage:
  python retrieval_runner.py \
    --data data/longmemeval_oracle.json \
    --output results/retrieval_output.jsonl \
    --top-k 50 \
    --granularity session
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
from tqdm import tqdm

from .adapter import load_benchmark, retrieve_for_entry


def compute_retrieval_metrics(
    ranked_items: list[dict],
    answer_session_ids: list[str],
    entry: dict,
    k_values: list[int] | None = None,
) -> dict:
    """
    Compute recall@K metrics against ground-truth answer sessions.
    Mirrors the metric computation in LongMemEval's eval_utils.py.
    """
    if k_values is None:
        k_values = [1, 3, 5, 10, 30, 50]

    answer_set = set(answer_session_ids)
    ranked_corpus_ids = [item["corpus_id"] for item in ranked_items]

    metrics: dict[str, float] = {}
    for k in k_values:
        top_k_ids = set(ranked_corpus_ids[:k])

        # recall_any@k: at least one answer session in top-k
        recall_any = float(bool(top_k_ids & answer_set))

        # recall_all@k: all answer sessions in top-k
        recall_all = float(answer_set.issubset(top_k_ids)) if answer_set else 0.0

        metrics[f"recall_any@{k}"] = recall_any
        metrics[f"recall_all@{k}"] = recall_all

    # NDCG@K: relevance-weighted ranking quality
    import math
    for k in k_values:
        dcg = 0.0
        for rank, cid in enumerate(ranked_corpus_ids[:k], start=1):
            if cid in answer_set:
                dcg += 1.0 / math.log2(rank + 1)

        # Ideal DCG: answer sessions ranked first
        idcg = sum(
            1.0 / math.log2(rank + 1)
            for rank in range(1, len(answer_set) + 1)
            if rank <= k
        )
        metrics[f"ndcg@{k}"] = dcg / idcg if idcg > 0 else 0.0

    return metrics


@click.command()
@click.option("--data", required=True, type=click.Path(exists=True),
              help="Path to LongMemEval JSON benchmark file.")
@click.option("--output", required=True, type=click.Path(),
              help="Output JSONL path with retrieval_results added.")
@click.option("--top-k", default=50, show_default=True,
              help="Number of items to retrieve per question.")
@click.option("--granularity", default="session", show_default=True,
              type=click.Choice(["session", "turn"]),
              help="Retrieval granularity.")
@click.option("--limit", default=None, type=int,
              help="Evaluate only first N entries (for debugging).")
@click.option("--skip-abstention/--no-skip-abstention", default=True, show_default=True,
              help="Skip abstention questions (no answer sessions to retrieve).")
def run_retrieval(
    data: str,
    output: str,
    top_k: int,
    granularity: str,
    limit: int | None,
    skip_abstention: bool,
) -> None:
    """Run L0 keyword retrieval on LongMemEval and produce ranked results."""
    entries = load_benchmark(Path(data))
    if limit:
        entries = entries[:limit]

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_metrics: dict[str, list[float]] = {}
    skipped = 0

    with output_path.open("w", encoding="utf-8") as out_f:
        for entry in tqdm(entries, desc="Retrieving"):
            question_id: str = entry["question_id"]
            is_abstention = question_id.endswith("_abs")

            if skip_abstention and is_abstention:
                skipped += 1
                out_f.write(json.dumps(entry) + "\n")
                continue

            answer_session_ids: list[str] = entry.get("answer_session_ids") or []

            # Run retrieval
            ranked_items = retrieve_for_entry(entry, top_k=top_k, granularity=granularity)

            # Compute metrics if we have ground truth
            entry_metrics: dict = {}
            if answer_session_ids and not is_abstention:
                entry_metrics = compute_retrieval_metrics(
                    ranked_items, answer_session_ids, entry
                )
                for k, v in entry_metrics.items():
                    all_metrics.setdefault(k, []).append(v)

            # Write augmented entry
            augmented = dict(entry)
            augmented["retrieval_results"] = {
                "query": entry["question"],
                "granularity": granularity,
                "ranked_items": ranked_items,
                "metrics": entry_metrics,
            }
            out_f.write(json.dumps(augmented, ensure_ascii=False) + "\n")

    # Aggregate and print metrics
    click.echo(f"\n{'='*60}")
    click.echo(f"Retrieval Results ({len(entries) - skipped} questions evaluated)")
    click.echo(f"{'='*60}")
    for metric_name in sorted(all_metrics.keys()):
        vals = all_metrics[metric_name]
        avg = sum(vals) / len(vals) if vals else 0.0
        click.echo(f"  {metric_name:25s}: {avg:.4f}")
    click.echo(f"{'='*60}")
    click.echo(f"Output written to: {output_path}")


if __name__ == "__main__":
    run_retrieval()
