"""
mwiki-lme: LongMemEval evaluation entry point.

Wraps retrieval_runner and generation_runner as a single CLI.

Usage:
  python -m eval.longmemeval.run retrieve  --data <benchmark.json> --output <out.jsonl>
  python -m eval.longmemeval.run generate  --data <benchmark.json> --output <hypothesis.jsonl>
  python -m eval.longmemeval.run full-eval --data <benchmark.json> --output-dir <results/>
"""

import click

from .generation_runner import run_generation
from .chroma_retrieval_runner import run_chroma_retrieval
from .retrieval_runner import run_retrieval
from .sample_episodic_cases import sample_episodic_cases


@click.group()
def cli() -> None:
    """LongMemEval evaluation runner for the Portable Personal Memory Layer."""


cli.add_command(run_retrieval, name="retrieve")
cli.add_command(run_chroma_retrieval, name="retrieve-chroma")
cli.add_command(run_generation, name="generate")
cli.add_command(sample_episodic_cases, name="sample-episodic")


@cli.command("full-eval")
@click.option("--data", required=True, type=click.Path(exists=True))
@click.option("--output-dir", required=True, type=click.Path())
@click.option("--mode", default="retrieval-augmented",
              type=click.Choice(["retrieval-augmented", "full-history", "episodic-memory", "memory-wiki", "popup-organize", "popup-organize-persistent", "popup-organize-episodic"]))
@click.option("--top-k", default=5)
@click.option("--model", default="claude-haiku-4-5-20251001")
@click.option("--limit", default=None, type=int)
@click.pass_context
def full_eval(ctx, data, output_dir, mode, top_k, model, limit):
    """
    Run retrieval + generation in sequence and print a summary.

    After this completes, run LongMemEval's evaluate_qa.py to get
    GPT-4o-judged QA accuracy scores.
    """
    from pathlib import Path
    import json

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    retrieval_out = out / "retrieval_output.jsonl"
    hypothesis_out = out / "hypothesis.jsonl"

    click.echo("=" * 60)
    click.echo("STEP 1: Retrieval")
    click.echo("=" * 60)
    ctx.invoke(
        run_retrieval,
        data=data,
        output=str(retrieval_out),
        top_k=top_k * 10,
        granularity="session",
        limit=limit,
        skip_abstention=True,
    )

    click.echo("\n" + "=" * 60)
    click.echo("STEP 2: Generation")
    click.echo("=" * 60)
    ctx.invoke(
        run_generation,
        data=data,
        output=str(hypothesis_out),
        mode=mode,
        top_k=top_k,
        model=model,
        max_context_chars=60_000,
        limit=limit,
        resume=True,
    )

    click.echo("\n" + "=" * 60)
    click.echo("DONE")
    click.echo("=" * 60)
    click.echo(f"Retrieval results : {retrieval_out}")
    click.echo(f"Hypothesis file   : {hypothesis_out}")
    click.echo("")
    click.echo("To compute QA accuracy, run LongMemEval's evaluator:")
    click.echo(f"  cd <longmemeval_repo>/src/evaluation")
    click.echo(f"  python evaluate_qa.py gpt-4o {hypothesis_out} {data}")


if __name__ == "__main__":
    cli()
