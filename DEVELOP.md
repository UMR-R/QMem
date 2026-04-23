# Memory Assistant — Developer Guide

## Project structure

```
memory_assistant/
├── manifest.json
├── config.js
├── background/
│   ├── background.js
│   ├── memory_engine.js
│   ├── llm_client.js
│   └── l2_wiki.js
├── content/
│   ├── content.js
│   └── clipboard_interceptor.js
├── popup/
│   ├── popup.html
│   ├── popup.css
│   └── popup.js
├── offscreen/
│   ├── offscreen.html
│   └── offscreen.js
├── prompts/
│   ├── schema.txt
│   ├── persistent_node_distill_bg.txt
│   ├── delta_extract.txt
│   ├── cold_start.txt
│   └── platform_memory_collect.txt
└── icons/
```

---

## Execution environments

The extension runs in three separate, isolated environments:

| Environment | Lifetime | File System API | Notes |
|---|---|---|---|
| **Service Worker** | Event-driven, suspended after ~30s idle | No | Handles all background tasks |
| **Popup** | While popup window is open | Yes | Destroyed when user dismisses it |
| **Content Script** | Page lifetime | No | Injected into every tab |

**Key constraint:** because the File System Access API is unavailable in the Service Worker, all disk writes go through the popup. The Service Worker buffers everything in `chrome.storage.local`; the popup flushes to disk on open.

---

## Module descriptions

### `manifest.json`

Chrome extension manifest v3. Declares permissions (`storage`, `downloads`, `clipboardRead`, `idle`, `alarms`, `offscreen`), registers the Service Worker entry point, and injects both content scripts into all URLs.

---

### `config.js`

Loaded by `popup.html` via `<script>`. Contains the hardcoded fallback versions of the prompts still used by the popup and a `CONFIG.loadPrompts()` function that fetches the active `prompts/*.txt` files at popup init and overwrites the in-memory defaults.

---

### `background/background.js`

**Service Worker entry point.** Responsibilities:

- **Message routing** — listens for messages from content scripts and popup:
  - `ROUND_CAPTURED` — a new conversation round was captured; calls `memory_engine.updateMemory`
  - `FLUSH_NOW` — popup requests an immediate flush of pending data
  - `PROCESS_ALL_RAW` — process up to N unprocessed raw conversations (batch mode)
  - `SAVE_DOCUMENT` — save a raw document string to storage
- **Periodic flush** — sets a 15-minute alarm (`chrome.alarms`) to flush pending data
- **Idle detection** — triggers a flush when the browser goes idle (`chrome.idle`)

---

### `background/memory_engine.js`

**Core memory update logic.** All state is kept in `chrome.storage.local`; disk writes happen in the popup. Storage keys are namespaced with `mw:` (e.g. `mw:profile`, `mw:preferences`, `mw:projects:<name>`, `mw:episodes:<id>`, `mw:persistent_nodes`).

Two update modes, both exported as `updateMemory(chatData, apiKey, opts)`:

| Mode | When used | How it works |
|---|---|---|
| **Per-round** (`batchMode: false`) | 实时更新, live capture | One DeepSeek call per conversation round; applies `delta_system` prompt |
| **Batch** (`batchMode: true`) | 同步 / 历史导入 | Concatenates all rounds into one prompt; single DeepSeek call — ~N× faster |

After each update, `_buildAndSaveEpisode` creates an `EpisodicMemory` record and asynchronously triggers `_updatePersistentNodes`, which calls DeepSeek with `persistent_distill_background` to update the persistent node store.

**`delta_system` output schema** (what DeepSeek returns per round):

```json
{
  "is_noise": false,
  "profile_updates": {},
  "preference_updates": {
    "add_style": [],
    "add_forbidden": [],
    "update_language": "",
    "update_granularity": ""
  },
  "project_updates": [{
    "project_name": "",
    "action": "update | create",
    "stage_update": "",
    "new_decisions": [],
    "new_questions": [],
    "resolved_questions": [],
    "new_next_actions": []
  }],
  "workflow_updates": [{
    "workflow_name": "",
    "action": "confirm | create",
    "steps_update": []
  }],
  "episode": {
    "topic": "",
    "summary": "",
    "key_decisions": [],
    "open_issues": [],
    "related_project": ""
  }
}
```

If `is_noise` is `true` the round is skipped entirely.

---

### `background/llm_client.js`

Thin wrapper over the DeepSeek API (`deepseek-chat`, temperature 0 for JSON calls). Exports two functions:

- `extractJson(system, user, apiKey)` — calls the API and returns a parsed JSON object. Falls back through three parse strategies: direct `JSON.parse` → markdown code block extraction → regex `{…}` extraction. Returns `{}` on failure.
- `summarize(system, user, apiKey)` — calls the API and returns plain text (temperature 0.3, 1024 tokens).

Each request has a 60-second timeout.

---

### `background/l2_wiki.js`

**File system layer.** Implements the same directory schema as the Python `llm_memory_transferor` so the JS extension and the `mwiki` CLI can share the same local folder.

The directory handle is persisted in IndexedDB (`MemAssistDB / settings / dirHandle`) so it survives Service Worker restarts.

Exports schema constructors (`newProfile`, `newPreferences`, `newProject`, `newWorkflow`, `newEpisode`) and async read/write helpers for each memory type. Every write bumps `version` and `updated_at`, and appends a line to `logs/change_log.jsonl`.

Also exports `rebuildIndex()`, which writes `metadata/index.json` summarising the current state of the wiki directory.

---

### `content/content.js`

**Content script** (runs in the extension's isolated world on every page). Handles:

- **Platform detection** — matches `location.hostname` against the `PLATFORMS` map (`chatgpt.com`, `chat.openai.com`, `gemini.google.com`, `chat.deepseek.com`, `www.doubao.com`)
- **Conversation capture** — when 保持更新 is on, observes DOM mutations to detect new assistant replies, then sends `ROUND_CAPTURED` to the Service Worker
- **Message injection** — on request from popup, types a prompt into the platform's input field and clicks Send; used by 导出并保存记忆 and 注入当前对话
- **Copy-button trigger** — clicks the platform's copy button and reads the clipboard (via the interceptor) to extract the last AI reply

Platform selectors (input fields, send buttons, stop buttons, response containers, user message containers) are defined per-platform at the top of the file. Update these when a platform changes its DOM.

---

### `content/clipboard_interceptor.js`

Runs in the **MAIN world** (direct page access, no extension sandbox). Wraps `navigator.clipboard.writeText` to intercept copy events and forwards the copied text to the isolated content script via `window.postMessage`. Required because the isolated world cannot read the clipboard directly on some platforms.

---

### `popup/popup.js`

**Popup controller.** All user-facing actions live here. Key responsibilities:

- On open: loads config (`CONFIG.loadPrompts()`), restores UI state, and triggers a file sync (flushes `chrome.storage.local` → disk via `l2_wiki.js`)
- **同步**: sends `FLUSH_NOW` to the Service Worker, then calls `PROCESS_ALL_RAW` (up to 10 conversations at a time) and writes results to disk
- **重建节点**: iterates all unprocessed episodes and runs persistent distillation on each
- **整理节点**: sends all existing nodes to DeepSeek and applies the returned merge operations
- **按标签导入**: shows the persistent node panel; 注入当前对话 uploads the memory package to the current AI tab; 导出文件 generates a `.txt` bootstrap file

---

### `offscreen/offscreen.html` + `offscreen.js`

An offscreen document (Chrome MV3 mechanism for background DOM access). Used when a clipboard or DOM operation is needed from the Service Worker context, which has no document.

---

## Prompts

| File | Used by | Purpose |
|---|---|---|
| `persistent_node_distill_bg.txt` | memory_engine.js → DeepSeek | Self-contained version (embeds schema); compact rules for automatic per-episode processing in the Service Worker |
| `delta_extract.txt` | memory_engine.js → DeepSeek | Incremental delta extraction per conversation round; outputs the delta JSON schema above |
| `cold_start.txt` | popup.js → target AI | Cold-start prompt sent when injecting a memory package into a new AI session |
| `platform_memory_collect.txt` | popup.js → target AI | Collects saved memory / custom instructions / agent config from the current AI page |

---

## Storage layers

```
chrome.storage.local        ← Service Worker writes here (no file system access)
    mw:profile
    mw:preferences
    mw:workflows
    mw:projects:<name>
    mw:episodes:<id>
    mw:persistent_nodes     ← { pn_next_id, episodic_tag_paths, nodes: { pn_XXXX: ... } }

IndexedDB (MemAssistDB)     ← stores the File System Access dirHandle across restarts
    settings / dirHandle

File System (user-chosen)   ← popup writes here on sync
    profile.json
    preferences.json
    workflows.json
    projects/{name}.json
    episodes/{id}.json
    raw/{platform}/{chatId}.json
    js_persistent_nodes.json
    metadata/index.json
    logs/change_log.jsonl
```

## Data flow

```
User chats on supported platform
    └─ content.js detects new reply
    └─ sends ROUND_CAPTURED → Service Worker
            └─ memory_engine: delta update (DeepSeek, delta_system.txt)
            └─ saves to chrome.storage.local
            └─ async: persistent node update (DeepSeek, persistent_distill_background.txt)

User opens popup
    └─ popup.js flushes chrome.storage.local → disk (via l2_wiki.js)

User clicks 同步
    └─ FLUSH_NOW → Service Worker
    └─ PROCESS_ALL_RAW (batch mode, ≤10 at a time)
    └─ results written to disk
```
