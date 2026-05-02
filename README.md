# Memory Assistant

[中文说明](README_zh.md)

Memory Assistant is a Chrome extension plus a local FastAPI backend for capturing AI conversations, organizing them into structured long-term memory, and moving that memory between platforms.

The current repository has three cooperating parts:

- `popup/`, `content/`, `background/`: the Chrome extension UI, page integration, and background sync logic.
- `backend_service/`: the local HTTP service used by the extension.
- `llm_memory_transferor/`: the Python memory pipeline that builds and updates structured memory.

## What It Can Do

- Capture conversations from supported AI sites such as ChatGPT, Gemini, DeepSeek, and Doubao.
- Import the current conversation into the local memory store.
- Ask the current platform to report its saved memory, custom instructions, agent config, and available skills, then store that snapshot locally.
- Rebuild structured memory from raw conversations.
- Maintain incremental memory updates when `Sync Memory` is enabled.
- Export selected memory sections as a package.
- Inject exported memory or selected skills into the current session.
- Manage both personal skills and recommended skills from the backend catalog.

## Quick Start

### 1. Start the local backend

From the repository root:

```bash
pip install -r backend_service/requirements.txt
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

Recommended backend URL:

```text
http://127.0.0.1:8765
```

`backend_service/requirements.txt` is the intended first-run install entrypoint
for the local backend and includes the runtime dependencies needed by the
in-repo `llm_memory_transferor` modules imported by `backend_service.app`.

### 2. Load the Chrome extension from this repository

1. Open Chrome and go to `chrome://extensions/`.
2. Turn on `Developer mode` in the top-right corner.
3. Click `Load unpacked`.
4. Select the repository root folder:

```text
memory_assistant_git/
```

Do not select only `popup/` or `background/`. Chrome needs the root because the
extension manifest lives at:

```text
manifest.json
```

After loading, you should see the Memory Assistant extension card in the
extensions page.

### 3. Pin the extension and open the popup

1. Click the Chrome extensions icon in the toolbar.
2. Pin `Memory Assistant` so it stays visible.
3. Click the extension icon to open the popup.

If the popup does not open correctly, go back to `chrome://extensions/`,
open the extension details page, and inspect errors first.

### 4. Configure the popup

In `Settings`, fill in:

- `Backend URL`: usually `http://127.0.0.1:8765`
- `API key`: your model provider key
- `Local storage directory`: where the backend should store raw chats and memory

The current backend defaults are:

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

By default, organize and incremental updates use the backend LLM configuration
above. Platform memory collection is handled through the current AI page.

### 5. Add data and build memory

There are two main ways to accumulate conversation data:

- `Import History`: use the popup `Settings` page to import local `json`, `jsonl`, `md`, or `txt` chat exports
- `Sync Conversation`: turn on sync in the popup, keep chatting on a supported AI site, and let the extension capture new rounds in realtime

After raw conversations have been collected, open `Migrate` and click
`Organize Memory` to rebuild:

- episodes
- profile
- preferences
- projects
- workflows
- daily notes / persistent nodes

### 6. Export or inject memory

After memory is organized:

1. Open `Migrate`
2. Select the memory sections you want
3. Click `Export` to create a package, or `Inject` to inject into the current AI session

### 7. Use the Skill page

The `Skill` page lets you:

- save recommended skills into your personal set
- export skills
- inject skills into the current session
- manage backend-provided skill assets

## Current Product Flow

1. The extension captures raw conversations or imports them manually.
2. Raw chats are stored under the local memory root.
3. `Organize Memory` calls `POST /api/memory/organize`.
4. The backend uses `MemoryBuilder` to rebuild:
   - episodes
   - profile
   - preferences
   - projects
   - workflows
5. The backend stores the Daily Notes category in `daily_notes/`.
6. If realtime memory sync is enabled, new rounds can also trigger incremental updates through `MemoryUpdater` and the background memory engine.

## Popup Views

### Home

- `Sync Conversation`: turns background capture on or off.
- `Migrate`: opens memory selection, organize, export, and inject actions.
- `Settings`: configures backend URL, API key, storage path, and realtime memory sync.
- `Skill`: manages saved skills, recommended skills, export, and injection.

### Migrate

- `Organize Memory`: rebuilds structured memory from local raw conversations.
- `Add Current Conversation`: imports the active chat page into the backend.
- `Add Platform Memory`: captures the platform's saved memory/custom instructions/agent config/skills and imports that snapshot.
- `Export`: exports the selected memory package.
- `Inject`: injects the selected package into the current AI session.

### Settings

- Backend URL
- API key
- Local storage directory
- Realtime memory update toggle
- History import for `json/jsonl/md/txt`
- Temporary cache cleanup

## Local Backend

The extension talks to a local FastAPI backend in `backend_service/`. For the
main user flow, the important thing is simply that the backend is running and
the popup can reach it at the configured URL.

## Active Prompt Files

Prompt files now live in `prompts/` and are used directly by the extension, backend, and Python pipeline.

| File | Used by | Purpose |
|---|---|---|
| `prompts/cold_start.txt` | popup injection flow | bootstrap prompt for memory injection |
| `prompts/platform/platform_memory_collect.txt` | popup platform-memory flow | collect saved memory and agent configuration from the current platform |
| `prompts/episodes/episode_system.txt` | `MemoryBuilder` | episode extraction during organize |
| `prompts/episodes/delta_system.txt` | `MemoryUpdater` and background engine | incremental memory update |
| `prompts/nodes/profile_system.txt` | `MemoryBuilder` | profile rebuild |
| `prompts/nodes/preferences_system.txt` | `MemoryBuilder` | preference rebuild |
| `prompts/nodes/projects_system.txt` | `MemoryBuilder` | project rebuild |
| `prompts/nodes/workflows_system.txt` | `MemoryBuilder` | workflow rebuild |
| `prompts/nodes/daily_notes_system.txt` | backend and background engine | daily-note persistent-node distillation |
| `prompts/nodes/skills_system.txt` | memory policy / future skill flow | saved and recommended skill memory |
| `prompts/display/display_taxonomy_proposal.txt` | memory display policy | optional display taxonomy proposals |
| `prompts/schema.txt` | backend/background persistent-node flow | schema context |

## Memory Store Layout

When `storage_path` is configured, the backend writes there. Otherwise it uses `backend_service/.state/wiki/`.

The active memory root currently contains directories such as:

- `raw/`: imported raw conversations
- `platform_memory/`: snapshots of saved memory or custom instructions from external platforms
- `episodes/`: conversation-level episodic memories
- `profile/`: profile memory
- `preferences/`: preference memory
- `projects/`: project memory
- `workflows/`: workflow memory
- `skills/`: saved skills
- `daily_notes/`: Daily Notes, including reusable daily-life context, personal choices, tastes, constraints, and other non-project context
- `metadata/`: indexes, organize state, display texts

The checked-in sample memory root in this repo is `llm_mem4/`.

## Repository Structure

- `popup/`: popup HTML/CSS/JS
- `content/`: page-side collection and injection logic
- `background/`: service worker and incremental memory engine
- `backend_service/`: local FastAPI backend and recommended-skill catalog
- `prompts/`: editable runtime prompts
- `llm_memory_transferor/`: Python library, CLI, exporters, tests, and evaluation scripts
- `llm_mem4/`: example memory store generated by the system

## Notes

- Supported host matching in the popup currently includes `chatgpt.com`, `chat.openai.com`, `gemini.google.com`, `chat.deepseek.com`, and `www.doubao.com`.
- The popup shows a selectable command modal for starting the backend instead of a native alert.
- The project contains several Windows-oriented UTF-8 fixes in the popup, backend, and wiki I/O paths.
- If a popup action fails, inspect the popup console from `chrome://extensions/`.
