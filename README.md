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
5. The backend distills long-term persistent nodes into `interest_discoveries/`.
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

The extension talks to a local FastAPI service. Main endpoints currently include:

- `GET /api/health`
- `GET/POST /api/settings`
- `POST /api/settings/test-connection`
- `GET /api/summary`
- `GET /api/sync/status`
- `POST /api/sync/toggle`
- `POST /api/conversations/current/import`
- `POST /api/platform-memory/import`
- `POST /api/memory/organize`
- `GET /api/memory/categories`
- `GET /api/memory/items`
- `POST /api/export/package`
- `POST /api/inject/package`
- `GET /api/skills/my`
- `GET /api/skills/recommended`
- `POST /api/skills/save`
- `POST /api/skills/export`
- `POST /api/skills/delete`
- `POST /api/skills/inject`
- `POST /api/import/history`
- `POST /api/cache/clear`
- `GET /api/jobs/{job_id}`

Start the backend from the repository root:

```bash
pip install -r backend_service/requirements.txt
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

`backend_service/requirements.txt` is the intended first-run install entrypoint for the local backend and includes the runtime dependencies needed by the in-repo `llm_memory_transferor` modules imported by `backend_service.app`.

Recommended backend URL:

```text
http://127.0.0.1:8765
```

## Default LLM Settings

The backend defaults are:

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

By default, organize and incremental updates use the backend LLM configuration above. Platform memory collection is handled through the current AI page.

## Active Prompt Files

Prompt files now live in `prompts/` and are used directly by the extension, backend, and Python pipeline.

| File | Used by | Purpose |
|---|---|---|
| `prompts/cold_start.txt` | popup injection flow | bootstrap prompt for memory injection |
| `prompts/platform_memory_collect.txt` | popup platform-memory flow | collect saved memory and agent configuration from the current platform |
| `prompts/episode_system.txt` | `MemoryBuilder` | episode extraction during organize |
| `prompts/profile_system.txt` | `MemoryBuilder` | profile rebuild |
| `prompts/preference_system.txt` | `MemoryBuilder` | preference rebuild |
| `prompts/projects_system.txt` | `MemoryBuilder` | project rebuild |
| `prompts/workflows_system.txt` | `MemoryBuilder` | workflow rebuild |
| `prompts/delta_system.txt` | `MemoryUpdater` and background engine | incremental memory update |
| `prompts/persistent_node_distill_bg.txt` | backend and background engine | persistent-node distillation |
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
- `interest_discoveries/`: distilled persistent nodes
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

## Quick Start

1. Load the extension in Chrome from the repository root.
2. Start the backend:

```bash
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

3. Open the popup and configure:
   - backend URL
   - API key
   - storage directory
4. Use `Add Current Conversation`, `Add Platform Memory`, or `Import History` to add source data.
5. Click `Organize Memory` to build structured memory.
6. Select memory sections and use `Export` or `Inject`.
7. Use the `Skill` page to save, export, or inject skills.

## Notes

- Supported host matching in the popup currently includes `chatgpt.com`, `chat.openai.com`, `gemini.google.com`, `chat.deepseek.com`, and `www.doubao.com`.
- The popup shows a selectable command modal for starting the backend instead of a native alert.
- The project contains several Windows-oriented UTF-8 fixes in the popup, backend, and wiki I/O paths.
- If a popup action fails, inspect the popup console from `chrome://extensions/`.
