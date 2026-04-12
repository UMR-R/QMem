# Portable Personal Memory Layer

A cross-platform LLM memory migration and maintenance system. Move the long-term understanding accumulated between you and one AI platform — profile, preferences, projects, workflows — to any other platform, without starting over.

> **The problem:** You've spent months "training" ChatGPT to know who you are, how you work, and what you're building. Now you want to try Claude. You start from zero again.
>
> **The solution:** Your memory lives outside the platform. You own it. You carry it anywhere.

---

## How it works

The system is built around four layers:

```
L0  Raw Evidence        chat exports, raw history files
L1  Platform Signals    saved memory, summaries, profiles, custom instructions
L2  Managed MWiki       the authoritative memory store (this system owns it)
L3  Schema & Policy     upgrade rules, conflict resolution, sensitivity checks
```

### Scenario 1 — Migration (A → B)

Give it your A-platform chat history and any memory exports. The build pipeline runs in two phases:

**Phase 1 — Episodic memory:** One LLM call per conversation in your raw history. Each call produces an `EpisodicMemory` record with the conversation timestamp, all topics covered, a short summary, key decisions, open issues, and relation flags indicating which persistent memory categories the conversation touches (profile, preferences, projects, workflows).

**Phase 2 — Persistent memory:** The episodes are aggregated into filtered digests per memory type. The LLM extracts each persistent memory object (profile, preferences, projects, workflows) from the relevant episode subset. Every persistent object is back-linked to the episode IDs that contributed to it, and through them to the original L0 raw session.

You then export a package and paste the bootstrap prompt into platform B. Done.

### Scenario 2 — Ongoing maintenance

Keep using any platform normally. Periodically feed new conversations into the system. It runs incremental delta updates — only touching the persistent memory objects affected by that session — and creates a new episode record. The episode is back-linked to any persistent objects it updated. When you switch to a new platform, export is nearly instant.

---

## Memory objects

| Type | What it stores | Lifespan |
|---|---|---|
| `EpisodicMemory` | One conversation: timestamp, topics, summary, decisions, relation flags, L0 session link | Medium-term; source of truth for persistent memory |
| `ProfileMemory` | Identity, role, domain, languages | Long-lived, infrequent updates |
| `PreferenceMemory` | Output style, forbidden expressions, formatting | Long-lived, medium updates |
| `ProjectMemory` | Goals, stage, timestamped decisions/questions/actions | Long-lived, frequent updates |
| `WorkflowMemory` | Recurring task patterns and steps | Long-lived, infrequent updates |
| `PlatformMappingMemory` | Field alignment between platforms | System-maintained |

All objects carry audit fields: `created_at`, `updated_at`, `version`, `evidence_links`, `conflict_log`, `source_episode_ids`.

`created_at` and `updated_at` on both episodic and persistent objects reflect the **time of the original conversation**, not the time of processing.

Each entry within a `ProjectMemory` (decisions, questions, actions, etc.) is a `ProjectEntry` carrying its own `timestamp` — the time the point was discussed.

---

## Installation

```bash
pip install -e .                   # core only (bring your own backend)
pip install -e ".[anthropic]"      # + Anthropic Claude
pip install -e ".[openai]"         # + OpenAI / local OpenAI-compatible servers
pip install -e ".[all]"            # + both
```

Requires Python ≥ 3.10.

### LLM backend configuration

The backend is auto-detected from environment variables (first match wins):

| Priority | Env var present | Backend selected |
|---|---|---|
| 1 | `MWIKI_LLM_BACKEND` | value of that var |
| 2 | `ANTHROPIC_API_KEY` | `anthropic` |
| 3 | `OPENAI_API_KEY` | `openai` |
| 4 | `OPENAI_BASE_URL` | `openai_compat` |

**Anthropic Claude** (default):
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**OpenAI / ChatGPT**:
```bash
export OPENAI_API_KEY=sk-...
# default model: gpt-4o  (override with --model)
```

**Local LLM** (Ollama, LM Studio, vLLM, llama.cpp, etc.):
```bash
export OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama example
export OPENAI_API_KEY=not-needed                    # required by client, value ignored
mwiki scan history.json --model llama3
```

You can also pass these per-command instead of using env vars:
```bash
mwiki scan history.json --backend openai_compat --base-url http://localhost:11434/v1 --model llama3
```

---

## Quick start

### 1. Export your history from the source platform

- **ChatGPT**: Settings → Data controls → Export data → Download → unzip → use `conversations.json`
- **Claude**: Export is not yet native; use your saved memory text and any conversation you've manually saved
- **Others**: Any JSON, JSONL, Markdown, or plain text file of conversations works

### 2. Scan and build your memory wiki

```bash
mwiki scan conversations.json -p chatgpt -m memory.json
```

Where `-m` points to any platform memory/profile exports (optional but recommended). The wiki is written to `./wiki/` by default.

#### `conversations.json` format

The file can be JSON, JSONL, Markdown, or plain text. For ChatGPT, the official export (`conversations.json`) is a JSON array of conversation objects:

```json
[
  {
    "id": "conv-abc123",
    "title": "My conversation",
    "create_time": 1710000000.0,
    "update_time": 1710003600.0,
    "mapping": {
      "node-1": {
        "message": {
          "id": "msg-1",
          "author": {"role": "user"},
          "content": {"parts": ["Hello, I'm a software engineer."]}
        }
      },
      "node-2": {
        "message": {
          "id": "msg-2",
          "author": {"role": "assistant"},
          "content": {"parts": ["Nice to meet you!"]}
        }
      }
    }
  }
]
```

The parser also accepts a simpler flat `messages` list (useful for other platforms or manual exports):

```json
[
  {
    "id": "conv-1",
    "title": "My conversation",
    "platform": "chatgpt",
    "messages": [
      {"id": "m1", "role": "user", "content": "Hello"},
      {"id": "m2", "role": "assistant", "content": "Hi!"}
    ]
  }
]
```

For plain text / Markdown exports, role transitions are detected by lines containing `User:`, `Assistant:`, `Human:`, `Claude:`, etc.

#### `memory.json` format

This is the optional `-m` file — the platform's own saved memory or profile export. Recognized top-level keys:

| Key | Signal type | Example value |
|---|---|---|
| `memory` / `memories` | `saved_memory` | `"User prefers concise answers."` |
| `summary` | `summary` | `"Alice is an ML engineer focused on NLP."` |
| `profile` | `profile` | `"Alice, senior engineer, Python expert"` or `{...}` |
| `preferences` / `custom_instructions` | `preference` | `{"style": "concise"}` or `"Be brief."` |
| `persona` / `instruction` | `custom_instruction` | `"Always respond in English."` |

Any JSON object not matching the above keys is accepted as a generic signal. The file can also be a JSON array of such objects, a `.jsonl` file (one signal per line), or a `.md`/`.txt` file (treated as `saved_memory` if the filename contains "memory", otherwise guessed from the filename stem).

Example minimal `memory.json` for ChatGPT saved memory:

```json
{"memory": "I'm a Python developer. I prefer short, direct answers. I'm working on a RAG pipeline called FaceGPT."}
```

Example with multiple signal types:

```json
{
  "memory": "User prefers concise responses.",
  "profile": {"name": "Alice", "role": "ML engineer"},
  "preferences": {"language": "English", "style": "bullet points"}
}
```

During the scan, the detected topics across all episodes are printed to the terminal so you can verify what was found.

### 3. Inspect what was built

```bash
mwiki show all
mwiki show episodes
mwiki show projects
```

### 4. Correct anything wrong

```bash
mwiki edit profile
mwiki edit project --project-name "My Project"
mwiki delete project --name "Old Project"
```

### 5. Export a migration package

```bash
mwiki export --target claude --output my_memory
# → my_memory.zip
```

The package contains your episodic memories and whichever persistent memory sections you choose. You can filter both:

```bash
# Only include profile and projects, all episodes
mwiki export --target claude --include-persistent profile,projects

# Include all persistent memory, but only specific episodes
mwiki export --target claude --episode-ids abc12345,def67890

# Combine both filters
mwiki export --target claude --include-persistent projects --episode-ids abc12345
```

Or just get the bootstrap prompt directly:

```bash
mwiki bootstrap --target claude
```

### 6. Paste into the new platform

Copy `minimal_bootstrap_prompt.txt` from the package and paste it as the system prompt or custom instructions in your new platform. Start chatting — the model will recognize your context from turn one.

### 7. Keep it updated

After a new session on any platform, feed it in:

```bash
mwiki update todays_chat.txt -p claude
```

#### `todays_chat.txt` format

The conversation file for `mwiki update` is passed as raw text directly to the LLM, so any human-readable format works. The LLM interprets whatever role structure it sees.

**Recommended plain-text format** (role markers on their own line):

```
User:
How should I frame the LoRA section in my CVPR paper?

```
mwiki scan HISTORY_FILES...     Build initial memory wiki from chat history
mwiki update CONVERSATION_FILE  Incrementally update wiki from a new session
mwiki export                    Export portable memory package
mwiki bootstrap                 Print minimal bootstrap prompt
mwiki show [SECTION]            Inspect wiki contents
mwiki edit [SECTION]            Edit a memory section in your editor
mwiki delete [SECTION]          Delete a memory entry
```

**Global options** (all commands):
- `-w, --wiki PATH` — wiki directory (default: `./wiki`)
- `--model TEXT` — model ID to use

**`mwiki scan`**:
```
HISTORY_FILES     One or more chat export files (JSON/JSONL/MD/TXT)
-p, --platform    Source platform name (chatgpt, claude, etc.)
-m, --memory-file Platform memory/profile export (repeatable)
```

**`mwiki update`**:
```
CONVERSATION_FILE  Path to new conversation file
-p, --platform     Source platform name
-m, --memory-file  Latest platform memory export (optional)
```

**`mwiki export`**:
```
-t, --target              Target platform: chatgpt | claude | deepseek | kimi | generic
-o, --output              Output path (default: memory_package_<target>)
--no-zip                  Output as directory instead of zip
--include-persistent      Comma-separated sections: profile,preferences,projects,workflows
                          Default: all four
--episode-ids             Comma-separated episode IDs to include. Default: all
```

**`mwiki show`**:
```
SECTION   all | profile | preferences | projects | workflows | episodes | index | changelog
```

**`mwiki delete`**:
```
SECTION        profile | preferences | project | episode | workflow
-n, --name     Name or ID of the item to delete
-y, --yes      Skip confirmation prompt
```

---

## Wiki directory layout

```
wiki/
├── profile.md / profile.json
├── preferences.md / preferences.json
├── workflows.md / workflows.json
├── projects/
│   └── {project_name}.md / .json
├── episodes/
│   └── {episode_id}.md / .json
├── mappings/
│   └── {platform}.json
├── metadata/
│   └── index.json
├── logs/
│   └── change_log.jsonl
└── evidence/
    └── evidence_index.json
```

The `wiki/` directory is designed to be human-readable, version-controllable, and editable with any text editor. The `.md` files are for reading; the `.json` files are the machine-authoritative source.

### File descriptions

| File | Description |
|---|---|
| `episodes/{id}.json` / `.md` | `EpisodicMemory` — one file per raw conversation: timestamp, topics covered, summary, key decisions, open issues, relation flags (`relates_to_profile`, `relates_to_preferences`, `relates_to_projects`, `relates_to_workflows`), and the L0 `conv_id`. These are the primary inputs for building persistent memory. |
| `profile.json` / `profile.md` | `ProfileMemory` — stable user identity: name, role, domain, languages, primary task types. Back-linked to the episodes that established each fact via `source_episode_ids`. |
| `preferences.json` / `preferences.md` | `PreferenceMemory` — output style, forbidden expressions, formatting constraints, language and response granularity. Back-linked to contributing episodes. |
| `projects/{name}.json` / `.md` | `ProjectMemory` — one file per project: goal, current stage, key terms. All list entries (decisions, questions, actions, constraints, entities) are `ProjectEntry` objects carrying the timestamp of the conversation where that point was discussed. Back-linked to contributing episodes via `source_episode_ids`. |
| `workflows.json` / `workflows.md` | `WorkflowMemory` list — recurring task patterns: trigger condition, typical steps, artifact format, review style, frequency. Back-linked to contributing episodes. |
| `mappings/{platform}.json` | `PlatformMappingMemory` — field alignment rules for a specific target platform. Used during export to format the bootstrap prompt correctly. |
| `metadata/index.json` | Index rebuilt on every `scan` or `update` — records `last_indexed` timestamp, presence of profile/preferences, project names, workflow and episode counts. |
| `logs/change_log.jsonl` | Append-only audit log. Each line is a JSON object with `timestamp`, `entity_type`, `action`, and `entity_id`. Full history of every write operation. |
| `evidence/evidence_index.json` | Index of raw evidence chunks referenced by memory objects. Tracks which L0 source excerpts support which memory entries. |

---

## Memory package contents

The export package contains only episodic memories and persistent memories. Raw history is never included.

```
manifest.json                — metadata, included sections, episode count, format version
episodes/
  {episode_id}.json          — selected EpisodicMemory objects
user_profile.json            — ProfileMemory (if included)
preferences.json             — PreferenceMemory (if included)
active_projects.json         — list of active ProjectMemory objects (if included)
key_workflows.json           — list of WorkflowMemory objects (if included)
minimal_bootstrap_prompt.txt — ready-to-paste system prompt
target_platform_mapping.json — field alignment rules for the target
```

Users choose which persistent memory sections and which episodes to include at export time.

---

## Supported platforms

| Platform | Bootstrap format |
|---|---|
| `chatgpt` | Custom instructions block |
| `claude` | XML-tagged system prompt |
| `deepseek` | Compact system prompt |
| `kimi` | Chinese-first system prompt |
| `generic` | Plain markdown sections |

Each platform has a built-in injection template and token budget. If a platform isn't listed, use `generic` — it works with any system prompt field.

---

## Design decisions

**Why build episodic memory first?**
Persistent memory objects (profile, preferences, projects, workflows) are derived from episodes, not directly from raw history. This means every fact in persistent memory is traceable to a specific conversation via `source_episode_ids → conv_id → L0 raw session`. It also makes incremental updates clean: a new conversation creates one episode, and only the persistent objects that episode touches are updated.

**Why timestamps on individual entries?**
Each `ProjectEntry` (decision, question, action, constraint) carries the timestamp of the conversation where it was discussed. This makes it possible to see the chronological evolution of a project, and to filter or prune stale entries by age.

**Why not just summarize the whole history?**
Full-history summarization is expensive, noisy, and destroys traceability. Phase 1 makes one focused LLM call per conversation. Phase 2 aggregates the already-structured episode output. It's incremental, auditable, and cheap to re-run for a single new conversation.

**Why markdown + JSON?**
JSON is the machine source of truth. Markdown is generated from it and is human-editable. If you edit the markdown directly (via `mwiki edit`), the change is visible immediately; the JSON syncs on the next `update` or `scan`.

**Which LLM for extraction?**
The extraction prompts output valid JSON and are designed to be conservative — they skip ambiguous content rather than hallucinate. Any capable model works. Claude and GPT-4o produce the most reliable structured output; smaller local models work but may need retries on complex history. Use `--model` to override the default for your backend.

**Why file-based storage?**
No database to set up. The `wiki/` directory is portable, git-friendly, and can be inspected or edited with any tool. The change log (`change_log.jsonl`) gives you a full audit trail.

**Upgrade thresholds:**
- Preferences require 2+ consistent occurrences before graduating to long-term.
- Workflows require 3+ occurrences.
- Profile identity fields (name, role, organization) require explicit user confirmation before updating.

---

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Project structure

```
src/llm_memory_transferor/
├── cli.py                      mwiki CLI entrypoint
├── models/
│   ├── base.py                 MemoryBase with audit fields + source_episode_ids
│   ├── profile.py              ProfileMemory
│   ├── preference.py           PreferenceMemory
│   ├── project.py              ProjectMemory + ProjectEntry (timestamped entries)
│   ├── workflow.py             WorkflowMemory
│   ├── episode.py              EpisodicMemory with relation flags and conv_id
│   └── platform_mapping.py    PlatformMappingMemory + built-in platform configs
├── layers/
│   ├── l0_raw.py               Raw chat history ingestion; RawConversation with start/end timestamps
│   ├── l1_signals.py           Platform memory signal reader
│   ├── l2_wiki.py              Managed MWiki file store
│   └── l3_schema.py            Upgrade rules, conflict resolution, sensitivity
├── processors/
│   ├── prompts.py              All LLM prompts in one place
│   ├── memory_builder.py       Scenario 1: two-phase build (episodes → persistent)
│   └── memory_updater.py       Scenario 2: incremental delta update
├── exporters/
│   ├── bootstrap_generator.py  Minimal bootstrap prompt generator
│   └── package_exporter.py     Export with episode + persistent section selection
└── utils/
    ├── llm_client.py           LLM backend wrapper (Anthropic, OpenAI, compat)
    └── storage.py              File I/O helpers
```
