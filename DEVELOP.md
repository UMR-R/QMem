# Memory Assistant Developer Guide

## Current Architecture

The project is no longer just a pure Chrome-extension pipeline. It is now a combined system:

- Chrome extension
- local FastAPI backend
- Python memory pipeline in `llm_memory_transferor/`

At a high level:

```text
content script / popup
  -> backend_service
  -> MemoryBuilder / MemoryUpdater
  -> wiki files + persistent nodes
```

## Project Structure

```text
memory_assistant/
├── manifest.json
├── config.js
├── popup/
│   ├── popup.html
│   ├── popup.css
│   └── popup.js
├── content/
│   ├── content.js
│   └── clipboard_interceptor.js
├── background/
│   ├── background.js
│   ├── memory_engine.js
│   ├── llm_client.js
│   └── l2_wiki.js
├── backend_service/
│   └── app.py
├── prompts/
│   ├── schema.txt
│   ├── episodes/
│   │   ├── delta_system.txt
│   │   └── episode_system.txt
│   ├── nodes/
│   │   ├── profile_system.txt
│   │   ├── preferences_system.txt
│   │   ├── projects_system.txt
│   │   ├── workflows_system.txt
│   │   ├── daily_notes_system.txt
│   │   └── skills_system.txt
│   ├── platform/
│   │   └── platform_memory_collect.txt
│   ├── display/
│   │   └── display_taxonomy_proposal.txt
│   └── cold_start.txt
└── llm_memory_transferor/
    └── src/llm_memory_transferor/
        ├── processors/
        ├── layers/
        └── utils/
```

## Runtime Environments

The extension still runs in several isolated environments, but many important memory actions now depend on the backend:

| Environment | Responsibility |
|---|---|
| `content/` | Detect supported sites, scrape current conversation, inject prompts/text into active page |
| `popup/` | User-facing controls, settings, organize/import/export/inject actions |
| `background/` | Background capture and incremental memory updates |
| `backend_service/` | Organize pipeline, memory storage, export/inject APIs, skill APIs |
| `llm_memory_transferor/` | Python memory models, builders, wiki persistence, updater logic |

## Current Main Flows

### 1. Organize Memory

Triggered by popup `整理记忆`.

Flow:

1. `popup/popup.js` calls `POST /api/memory/organize`
2. `backend_service/app.py` starts organize job
3. raw conversations are loaded
4. `MemoryBuilder` rebuilds:
   - episodes
   - profile
   - preferences
   - projects
   - workflows
5. daily-note persistent nodes are distilled using `prompts/nodes/daily_notes_system.txt`
6. results are written into the wiki / backend-managed storage

Relevant code:

- `popup/popup.js`
- `backend_service/app.py`
- `llm_memory_transferor/src/llm_memory_transferor/processors/memory_builder.py`

### 2. Add Current Conversation

Triggered by popup `加入当前对话`.

Flow:

1. popup scrapes current conversation from the active tab
2. popup calls backend import API
3. conversation is stored as raw data
4. user can organize later, or let later flows process it

Relevant code:

- `popup/popup.js` -> `addCurrentConversation()`
- `backend_service/app.py`

### 3. Add Platform Memory

Triggered by popup `加入平台记忆`.

Flow:

1. popup loads `prompts/platform/platform_memory_collect.txt`
2. popup injects the prompt into the current AI page
3. current AI reports saved memory / custom instructions / agent config / platform skills
4. popup parses the JSON result
5. popup sends the snapshot to backend import API

If prompt-based collection fails, popup falls back to page scraping.

Relevant code:

- `config.js`
- `popup/popup.js` -> `collectPlatformMemoryWithPrompt()`
- `backend_service/app.py`

### 4. Background Incremental Update

Triggered when sync policies are enabled and new rounds arrive.

Flow:

1. `content/content.js` detects a new assistant reply
2. background receives captured round
3. `background/memory_engine.js` uses `prompts/episodes/delta_system.txt`
4. incremental memory delta is produced
5. daily-note persistent node maintenance may also run with `prompts/nodes/daily_notes_system.txt`

This is separate from the full Python organize pipeline.

## Popup Responsibilities

`popup/popup.js` is now the main UI controller.

Important actions:

- `runOrganize()`
- `addCurrentConversation()`
- `addPlatformMemory()`
- `exportPackage()`
- `injectPackage()`
- settings load/save/test
- skill export/inject/save/delete

It also includes popup-side error reporting:

- global `window.error`
- global `unhandledrejection`
- organize-failure logging via `logPopupError(...)`

When popup execution fails, errors should appear in the browser console.

## Backend Responsibilities

`backend_service/app.py` is now the central app-facing orchestration layer.

Important API groups:

- settings
  - `/api/settings`
  - `/api/settings/test-connection`
- memory actions
  - `/api/memory/organize`
  - `/api/memory/items`
- package actions
  - export package
  - inject package
- import actions
  - import current conversation
  - import platform memory
  - import history
- skill actions
  - my skills
  - recommended skills
  - export / inject skills

Default backend LLM settings:

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

The backend is configurable from the popup settings page.

## Python Memory Pipeline

The Python pipeline lives under:

- `llm_memory_transferor/src/llm_memory_transferor/`

Important modules:

- `processors/memory_builder.py`
  Builds episodes and persistent memory objects from raw conversations.

- `processors/memory_updater.py`
  Handles incremental update logic in the Python pipeline.

- `processors/prompts.py`
  Loads Python-side prompt files from the repository `prompts/` directory.

- `layers/l2_wiki.py`
  Reads and writes wiki-layer files.

### Python prompt files currently in use

- `prompts/episodes/episode_system.txt`
- `prompts/episodes/delta_system.txt`
- `prompts/nodes/profile_system.txt`
- `prompts/nodes/preferences_system.txt`
- `prompts/nodes/projects_system.txt`
- `prompts/nodes/workflows_system.txt`
- `prompts/nodes/daily_notes_system.txt`
- `prompts/nodes/skills_system.txt`

`processors/prompts.py` is now the loader layer for these files.

## Active Prompt Files

These `prompts/*.txt` files are part of the current runtime:

| File | Used by | Purpose |
|---|---|---|
| `platform/platform_memory_collect.txt` | popup | Collect current platform memory/config from the webpage AI |
| `cold_start.txt` | popup | Bootstrap prompt for inject/export flows |
| `episodes/episode_system.txt` | Python `MemoryBuilder` | Episode extraction during organize |
| `episodes/delta_system.txt` | Python `MemoryUpdater` + background memory engine | Shared incremental memory delta extraction |
| `nodes/profile_system.txt` | Python `MemoryBuilder` + backend | Profile rebuild |
| `nodes/preferences_system.txt` | Python `MemoryBuilder` + backend | Preference rebuild |
| `nodes/projects_system.txt` | Python `MemoryBuilder` + backend | Project rebuild |
| `nodes/workflows_system.txt` | Python `MemoryBuilder` + backend | Workflow rebuild |
| `nodes/daily_notes_system.txt` | backend + background | Daily-note persistent node distillation / maintenance |
| `nodes/skills_system.txt` | memory policy / future skill flow | Saved and recommended skill memory |
| `display/display_taxonomy_proposal.txt` | memory display policy | Optional display taxonomy proposals |
| `schema.txt` | node distill flow | Schema context for persistent nodes |

The previously unused prompt files removed from the repo are not part of the live flow anymore.

## content.js Notes

`content/content.js` currently handles:

- supported-platform detection
- DOM observation for new AI replies
- conversation scraping
- prompt injection / text injection into the current tab

Supported hosts include:

- `chatgpt.com`
- `chat.openai.com`
- `gemini.google.com`
- `chat.deepseek.com`
- `www.doubao.com`

When a platform changes its DOM, selectors in `content.js` are usually the first thing to update.

## Background Notes

`background/background.js` and `background/memory_engine.js` still matter, but they are no longer the whole memory system.

Their main role is:

- capture-time event handling
- incremental update
- prompt-based background memory maintenance

The full rebuild / organize flow now belongs to the backend + Python pipeline.

## Storage Overview

The project uses multiple storage layers:

```text
chrome.storage.local
  -> extension-side cached state and background data

IndexedDB
  -> popup directory handle persistence

backend-managed local files / wiki files
  -> raw conversations
  -> episodic memories
  -> persistent memory objects
  -> persistent nodes
```

## Windows Compatibility Notes

Recent fixes added for Windows:

- stdout / stderr UTF-8 reconfiguration in backend startup
- explicit UTF-8 reads and writes in key wiki-layer paths
- safer organize-time console output to avoid `gbk` failures
- popup-side console logging for organize failures
- list-field normalization in `MemoryBuilder` for unstable LLM JSON output

These are especially relevant when debugging user reports from Windows environments.

## Recommended Debug Entry Points

When debugging a feature, start from:

- popup action problems
  - `popup/popup.js`

- page scraping / prompt injection problems
  - `content/content.js`

- organize-memory failures
  - `backend_service/app.py`
  - `processors/memory_builder.py`
  - `layers/l2_wiki.py`

- incremental-update problems
  - `background/memory_engine.js`
  - `prompts/episodes/delta_system.txt`

- persistent-node problems
  - `prompts/nodes/daily_notes_system.txt`
  - `background/memory_engine.js`
  - `backend_service/app.py`
