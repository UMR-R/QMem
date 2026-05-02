# Portable Personal Memory Layer

`llm_memory_transferor` is the Python memory pipeline used by this repository. It powers the local backend's organize flow, incremental updates, and package export logic, and it can also be used directly through the `mwiki` CLI.

## What It Does

- ingest raw chat history from `json`, `jsonl`, `md`, and `txt`
- ingest platform-memory signals such as saved memory or custom instructions
- build structured memory from raw conversations
- update structured memory incrementally from a new conversation
- export selected memory sections as a portable package
- generate bootstrap prompts for target platforms
- maintain a file-based wiki that stays readable in both Markdown and JSON

## Core Layers

The system is organized into four layers:

```text
L0  Raw Evidence        chat exports and raw conversation files
L1  Platform Signals    saved memory, summaries, custom instructions, profiles
L2  Managed Wiki        the file-based memory store owned by this project
L3  Schema & Policy     upgrade rules, conflict resolution, validation
```

## Current Pipeline

### Initial build

`mwiki scan` or the backend organize flow does the following:

1. ingest raw conversations through `L0RawLayer`
2. ingest optional platform-memory signals through `L1SignalLayer`
3. extract conversation-level episodes with `MemoryBuilder`
4. rebuild:
   - profile
   - preferences
   - projects
   - workflows
5. rebuild wiki indexes and supporting metadata

### Incremental update

`mwiki update` or the backend realtime update flow:

1. loads the current wiki state
2. runs `MemoryUpdater` on a new conversation
3. updates only the touched memory sections
4. creates a new episode
5. rebuilds the index

## Installation

From the `llm_memory_transferor/` directory:

```bash
pip install -e .
pip install -e ".[openai]"
pip install -e ".[anthropic]"
pip install -e ".[all]"
```

Requires Python `>=3.10`.

## LLM Backend Selection

The CLI auto-detects backend configuration in this order:

| Priority | Env var | Backend |
|---|---|---|
| 1 | `MWIKI_LLM_BACKEND` | explicit value |
| 2 | `ANTHROPIC_API_KEY` | `anthropic` |
| 3 | `OPENAI_API_KEY` | `openai` |
| 4 | `OPENAI_BASE_URL` | `openai_compat` |

You can also pass CLI flags directly:

```bash
mwiki scan history.json --backend openai_compat --base-url http://localhost:11434/v1 --model llama3
```

## Prompt Files

Processor prompts are no longer embedded directly in Python. They are loaded from the repository-level `prompts/` directory by [`processors/prompts.py`](./src/llm_memory_transferor/processors/prompts.py).

The active processor prompt files are:

- `prompts/episodes/episode_system.txt`
- `prompts/episodes/delta_system.txt`
- `prompts/nodes/profile_system.txt`
- `prompts/nodes/preferences_system.txt`
- `prompts/nodes/projects_system.txt`
- `prompts/nodes/workflows_system.txt`
- `prompts/nodes/daily_notes_system.txt`
- `prompts/nodes/skills_system.txt`
- `prompts/display/display_taxonomy_proposal.txt`

This means prompt tuning can be done without editing the Python package itself.

## CLI Quick Start

### Build a wiki from history

```bash
mwiki scan conversations.json -p chatgpt -m memory.json
```

### Incrementally update from a new conversation

```bash
mwiki update latest_chat.txt -p claude
```

### Inspect the wiki

```bash
mwiki show all
mwiki show episodes
mwiki show projects
```

### Export a package

```bash
mwiki export --target claude --output my_memory
```

### Generate a bootstrap prompt

```bash
mwiki bootstrap --target claude
```

## Testing On LongMemEval

The repository includes a LongMemEval adapter and runner under
`eval/longmemeval/`.

Recommended benchmark file:

```text
llm_memory_transferor/data/longmemeval_s_cleaned.json
```

Before running generation, configure one LLM backend. The examples below assume
an OpenAI-compatible endpoint such as DeepSeek:

```bash
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export MWIKI_API_KEY=sk-...
```

All commands below are run from the `llm_memory_transferor/` directory.

### Test persistent memory

Use `popup-organize-persistent` mode to simulate the real popup organize flow
and answer from the organized persistent memory only.

Quick sample:

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_s_cleaned.json \
  --output results/hypothesis_persistent_test.jsonl \
  --mode popup-organize-persistent \
  --top-k 5 \
  --backend openai_compat \
  --model deepseek-chat \
  --limit 20
```

Full run:

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_s_cleaned.json \
  --output results/hypothesis_persistent.jsonl \
  --mode popup-organize-persistent \
  --top-k 5 \
  --backend openai_compat \
  --model deepseek-chat
```

### Test popup organize flow with raw evidence

Use `popup-organize` mode to simulate the real product path triggered by
clicking "Organize Memory" in the popup. This mode writes the LongMemEval
haystack into backend raw storage, runs the backend organize flow, builds
profile, preferences, projects, workflows, and persistent nodes, and then
answers using the organized memory package plus retrieved evidence.

Quick sample:

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_s_cleaned.json \
  --output results/hypothesis_popup_organize_test.jsonl \
  --mode popup-organize \
  --top-k 5 \
  --backend openai_compat \
  --model deepseek-chat \
  --limit 20
```

Full run:

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_s_cleaned.json \
  --output results/hypothesis_popup_organize.jsonl \
  --mode popup-organize \
  --top-k 5 \
  --backend openai_compat \
  --model deepseek-chat
```

### Test episodic memory

Use `popup-organize-episodic` mode to simulate the real popup organize flow and
answer from the organized episodic evidence only.

Quick sample:

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_s_cleaned.json \
  --output results/hypothesis_episode_test.jsonl \
  --mode popup-organize-episodic \
  --top-k 5 \
  --backend openai_compat \
  --model deepseek-chat \
  --limit 20
```

Full run:

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_s_cleaned.json \
  --output results/hypothesis_episode.jsonl \
  --mode popup-organize-episodic \
  --top-k 5 \
  --backend openai_compat \
  --model deepseek-chat
```

### Optional baselines

Retrieval-only baseline:

```bash
python -m eval.longmemeval.run retrieve \
  --data data/longmemeval_s_cleaned.json \
  --output results/retrieval_output.jsonl \
  --top-k 50 \
  --granularity session
```

Full-history baseline:

```bash
python -m eval.longmemeval.run generate \
  --data data/longmemeval_s_cleaned.json \
  --output results/hypothesis_full_history.jsonl \
  --mode full-history \
  --backend openai_compat \
  --model deepseek-chat
```

### Official LongMemEval scoring

After generation, score the output with the official LongMemEval evaluator:

```bash
cd <longmemeval_repo>/src/evaluation

python evaluate_qa.py gpt-4o \
  /path/to/results/hypothesis_episode.jsonl \
  /path/to/data/longmemeval_s_cleaned.json

python print_qa_metrics.py \
  /path/to/results/hypothesis_episode.jsonl.eval-results-gpt-4o \
  /path/to/data/longmemeval_s_cleaned.json
```

## Supported CLI Commands

- `mwiki scan`
- `mwiki update`
- `mwiki export`
- `mwiki bootstrap`
- `mwiki show`
- `mwiki edit`
- `mwiki delete`

Common options include:

- `--wiki` / `-w`
- `--platform` / `-p`
- `--memory-file` / `-m`
- `--model`
- `--backend`
- `--api-key`
- `--base-url`

The default wiki directory for the CLI is:

```text
./wiki
```

## Wiki Layout

The managed wiki is file-based and human-readable. It commonly contains:

```text
wiki/
├── profile/
├── preferences/
├── projects/
├── workflows/
├── episodes/
├── metadata/
├── mappings/
├── logs/
└── README.md
```

The machine-readable source is JSON, and Markdown is generated for inspection and manual editing.

## Package Export

The exporter can include:

- episodic memories
- profile
- preferences
- active projects
- workflows
- target-platform bootstrap prompt

You can filter exported content by persistent section and episode IDs.

## Relationship To The Main Repo

Inside this repository:

- the Chrome extension triggers backend endpoints
- the backend imports this package from `llm_memory_transferor/src`
- the backend adds one more layer on top: raw import management, skill management, persistent-node distillation, and popup-facing APIs

So this package is the structured-memory engine, while `backend_service/` is the app wrapper around it.

## Development

Run tests from `llm_memory_transferor/`:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Project source lives under:

```text
llm_memory_transferor/src/llm_memory_transferor/
```

Key modules:

- `cli.py`
- `layers/`
- `models/`
- `processors/`
- `exporters/`
- `utils/`
