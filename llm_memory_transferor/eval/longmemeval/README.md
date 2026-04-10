# LongMemEval Evaluation

Tests the Portable Personal Memory Layer against the [LongMemEval](https://github.com/xiaowu0162/longmemeval) benchmark — a 500-question dataset measuring five memory capabilities: information extraction, multi-session reasoning, knowledge updates, temporal reasoning, and abstention.

---

## What this tests

LongMemEval gives each question a "haystack" of conversation sessions (up to ~115k tokens for the `_s` variant). The system must answer the question using only what appears in that history.

We run three modes, each testing a different layer of the system:

| Mode | What it tests | Cost |
|---|---|---|
| `retrieval-augmented` | L0 keyword retrieval → Claude answers from top-K sessions | Low (retrieval free, generation ~$0.002/q with Haiku) |
| `full-history` | Claude answers from the full truncated haystack | Medium |
| `memory-wiki` | Full pipeline: L2 MWiki built from haystack, bootstrap injected, then retrieval+answer | High (LLM extraction per question) |

---

## Setup

### 1. Get the benchmark data

```bash
git clone https://github.com/xiaowu0162/longmemeval
```

The benchmark data should appear in `longmemeval/data/`. If not, download from the [HuggingFace dataset](https://huggingface.co/datasets/xiaowu0162/longmemeval):

```bash
pip install huggingface_hub
python -c "
from huggingface_hub import hf_hub_download
for f in ['longmemeval_s_cleaned.json', 'longmemeval_oracle.json']:
    hf_hub_download('xiaowu0162/longmemeval', f, repo_type='dataset', local_dir='data/')
"
```

We recommend starting with `longmemeval_oracle.json` (smallest, only evidence sessions per question).

### 2. Set API keys

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # for generation
export OPENAI_API_KEY=sk-...          # for QA evaluation (GPT-4o judge)
```

### 3. Install dependencies

```bash
pip install -e ".[dev]"
pip install tqdm
```

---

## Running the evaluation

All commands are run from the project root.

### Quick test (20 questions)

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_oracle.json \
  --output results/hypothesis_test.jsonl \
  --mode retrieval-augmented \
  --top-k 5 \
  --model claude-haiku-4-5-20251001 \
  --limit 20
```

### Retrieval only (no LLM cost)

```bash
python -m eval.longmemeval.run retrieve \
  --data data/longmemeval_oracle.json \
  --output results/retrieval_output.jsonl \
  --top-k 50 \
  --granularity session
```

Prints retrieval metrics (recall@K, NDCG@K) immediately without needing GPT-4o.

### Full generation (retrieval-augmented)

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_oracle.json \
  --output results/hypothesis_rag.jsonl \
  --mode retrieval-augmented \
  --top-k 5 \
  --model claude-haiku-4-5-20251001
```

### Full pipeline (memory-wiki mode)

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_oracle.json \
  --output results/hypothesis_wiki.jsonl \
  --mode memory-wiki \
  --top-k 5 \
  --model claude-sonnet-4-6
```

Note: `memory-wiki` mode builds an L2 MWiki for every question's haystack — it makes many LLM calls and is expensive for the full 500-question set. Use `--limit 50` for sampling.

### All modes in one command

```bash
python -m eval.longmemeval.run full-eval \
  --data data/longmemeval_oracle.json \
  --output-dir results/run_01/ \
  --mode retrieval-augmented \
  --top-k 5 \
  --model claude-haiku-4-5-20251001 \
  --limit 100
```

---

## Scoring with GPT-4o

After generating hypotheses, use LongMemEval's official evaluator:

```bash
cd <longmemeval_repo>/src/evaluation

python evaluate_qa.py gpt-4o \
  /path/to/results/hypothesis_rag.jsonl \
  /path/to/data/longmemeval_oracle.json

python print_qa_metrics.py \
  /path/to/results/hypothesis_rag.jsonl.eval-results-gpt-4o \
  /path/to/data/longmemeval_oracle.json
```

---

## Output formats

**Retrieval output** (`retrieval_output.jsonl`) — one JSON per line, original entry augmented with:
```json
{
  "question_id": "...",
  "retrieval_results": {
    "query": "question text",
    "granularity": "session",
    "ranked_items": [
      {"corpus_id": "sess_001", "text": "...", "timestamp": "2024-01-01"}
    ],
    "metrics": {"recall_any@1": 0.0, "recall_any@5": 1.0, "ndcg@5": 0.86}
  }
}
```

**Hypothesis output** (`hypothesis.jsonl`) — one JSON per line:
```json
{"question_id": "q_001", "hypothesis": "Text classification and named entity recognition."}
```

This format is directly compatible with LongMemEval's `evaluate_qa.py`.

---

## Retrieval metrics (reported without GPT-4o)

The `retrieve` command prints these immediately after running:

| Metric | Description |
|---|---|
| `recall_any@K` | ≥1 answer session in top-K |
| `recall_all@K` | All answer sessions in top-K |
| `ndcg@K` | Ranking quality (normalized DCG) |

K values: 1, 3, 5, 10, 30, 50.

---

## Expected results

Results depend on the benchmark variant and mode. Rough reference points from the LongMemEval paper for comparison:

| System | QA Accuracy (oracle variant) |
|---|---|
| Full history (GPT-4o, 128K) | ~51% |
| BM25 retrieval + GPT-4o | ~44% |
| Oracle retrieval + GPT-4o | ~60% |

Our `retrieval-augmented` mode (L0 keyword search + Claude Haiku) is comparable to the BM25 baseline. The `memory-wiki` mode adds structured memory context on top of retrieval, which should improve preference and multi-session question types.

---

## Design notes

**Why keyword retrieval at L0?**
L0 retrieval is intentionally simple — BM25-equivalent, no dependencies, no embedding model needed. It establishes a cost-free baseline. Plugging in a dense retriever (Contriever, Stella) would improve recall significantly.

**Why Claude Haiku by default?**
500 questions × average 8K context tokens ≈ 4M tokens total. At Haiku pricing this is ~$1. Sonnet is ~8×, Opus ~40×.

**Resume support**
All generation commands append to the output file and skip already-answered `question_id`s. Safe to interrupt and resume.

**Abstention questions**
Questions with IDs ending in `_abs` are unanswerable. The retrieval runner skips them for metric computation. The generation runner answers them normally; LongMemEval's evaluator handles the special abstention scoring.
