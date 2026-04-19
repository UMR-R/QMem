# Memory Assistant

[中文文档](README_zh.md)

A Chrome extension that automatically captures AI conversations, builds layered memories, and lets you export them to any platform.

## Supported platforms

| Platform | Domain |
|---|---|
| ChatGPT | chatgpt.com / chat.openai.com |
| Google Gemini | gemini.google.com |
| DeepSeek | chat.deepseek.com |
| Doubao (豆包) | www.doubao.com |

---

## Installation

### 1. Get a DeepSeek API key

Sign up at [platform.deepseek.com](https://platform.deepseek.com) and create an API key. This is used to distill memories in the background.

### 2. Load the extension in Chrome

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the `memory_assistant` folder
5. The extension icon will appear in your toolbar

### 3. First-time setup

1. Click the extension icon to open the popup
2. Click **Configure** → enter your DeepSeek API key → click **Save**
3. Click **Choose Folder** → choose a local folder where memory files will be saved

---

## Interface layout

The popup is divided into three sections:

**History Import** — Build memory from ChatGPT / DeepSeek export files

**Live Capture** — Accumulate memory automatically or manually during normal AI use

**Memory Management & Export** — View and maintain nodes, inject into or export to any platform

---

## Usage

### Scenario 1 — Build memory from history

Import an existing ChatGPT / DeepSeek conversation history and build a memory library in one go.

1. Export your history
   - **ChatGPT**: Settings → Data controls → Export data → Download ZIP → unzip → use `conversations.json`
   - **DeepSeek**: use the exported file directly
2. Click the extension icon → **History Import** → **Import ChatGPT / DeepSeek History**
3. Select the file — conversations are parsed and episodes are extracted automatically
4. Processing runs in batches of 10. If more remain, the status area will say how many are left — click import again with the same file to continue (already-imported conversations are skipped)
5. Click **Sync** to write the results to your local folder
6. (Optional) Click **Rebuild Nodes** to distill episodes into persistent nodes; click **Consolidate Nodes** to merge overlapping nodes

---

### Scenario 2 — Live memory maintenance

1. Click the extension icon → **Live Capture**
2. Toggle on **Keep Updated** — the extension starts capturing conversations on any supported platform
3. Toggle on **Realtime Update** — after each AI reply, DeepSeek is called automatically to update your memory (profile, preferences, projects, episodes)

> **Note:** Background memories are held in browser storage. Click **Sync** at any time to write them to your local folder.

For important conversations, click **Export Current Conversation** to send a structured extraction prompt to the current AI, then have DeepSeek update your persistent nodes from the reply.

---

### Sync to files

Click the **Sync** button at the top to flush all memory from browser storage to your local folder. Duplicate conversation rounds are removed automatically.

If your DeepSeek API key is configured, clicking Sync also extracts episodes from conversations captured while **Realtime Update** was off — no need to re-enable it. Each conversation is processed in a single API call (batch mode).

**Batch processing:** Each sync processes at most **10 conversations** at a time. If there are more remaining, the status area will show how many are left — click Sync again to continue.

Files written:

```
<your chosen directory>/
├── profile.json          # who you are
├── preferences.json      # how you like responses
├── workflows.json        # recurring task patterns
├── projects/
│   └── {project}.json    # per-project notes and decisions
├── episodes/
│   └── {id}.json         # per-conversation memory snapshots
├── raw/
│   └── {platform}/
│       └── {chatId}.json # raw captured conversation rounds
└── js_persistent_nodes.json  # cross-session distilled patterns
```

---

### Memory management & export

#### View and select nodes

Click **Browse Memory Nodes** to open a panel listing all persistent nodes grouped by type (preferences, profile, topics, etc.). Nodes with high confidence or high export priority are pre-checked.

#### Inject into current conversation

After selecting nodes, choose a target platform and click **Inject into Chat**: the extension uploads a memory package (selected nodes + supporting episode evidence) to the current AI and sends a cold-start prompt, giving the AI full context from your past conversations.

#### Export to file (cross-platform migration)

After selecting nodes, choose a target platform and click **Export File**: the extension generates a `.txt` file containing your memory data and a cold-start prompt. Paste it into any platform's system prompt or custom instructions field.

Supported output formats:

| Target | Format |
|---|---|
| Claude | XML-tagged (`<memory_package>`) |
| ChatGPT | Instructions + data separator format |
| DeepSeek | Same as above |
| Generic | Plain text, works with any system prompt field |

#### Maintain nodes

- **Rebuild Nodes**: Scans all episodes not yet distilled into persistent nodes and processes them one by one. Use this after accumulating many conversations with **Realtime Update** off.
- **Consolidate Nodes**: Asks DeepSeek to find and merge semantically overlapping nodes (e.g., multiple sub-topics under the same subject area).

---

## Customizing prompts

All prompts live as plain-text files in the `prompts/` directory. Edit them directly — no JS changes or build step required.

### Files

| File | Sent to | Triggered by |
|---|---|---|
| `prompts/export_episode.txt` | Target AI (current page) | Export Current Conversation |
| `prompts/architecture.txt` | Prepended to `distill_nodes.txt` | Export Current Conversation / Rebuild Nodes / Consolidate Nodes |
| `prompts/distill_nodes.txt` | DeepSeek API (popup context) | Export Current Conversation / Rebuild Nodes / Consolidate Nodes |
| `prompts/distill_nodes_bg.txt` | DeepSeek API (Service Worker) | Realtime Update per-round / Sync |
| `prompts/extract_delta.txt` | DeepSeek API (Service Worker) | Realtime Update per-round / Sync |
| `prompts/load_memory.txt` | Target AI | Inject into Chat / Export File |

### How to edit

1. Open the `.txt` file in any text editor and save it.
2. Go to `chrome://extensions/` and click the reload icon on the extension card.
3. Reopen the popup — changes take effect immediately.

---

## Typical workflow

```
Scenario 1 — Build from history
  └─ Import ChatGPT / DeepSeek history file → episodes extracted automatically
  └─ Click Sync → files written to your directory
  └─ (Optional) Click Rebuild Nodes → distill episodes into persistent nodes
  └─ (Optional) Click Consolidate Nodes → clean up overlapping nodes

Scenario 2 — Live maintenance
  └─ Keep Updated + Realtime Update ON → memory builds automatically
  └─ After each session, click Sync → files updated

Starting a new chat on any platform
  └─ Click Browse Memory Nodes → select nodes → choose target platform
  └─ Inject into Chat: inject directly into the current AI session
  └─ Export File: generate a .txt file to paste into any platform
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Capture doesn't trigger | Reload the page after enabling Keep Updated; the extension needs to inject into the page |
| Buttons don't respond | The AI platform may have updated its UI; reload the extension and try again |
| "API Key not configured" error | Click Configure and re-enter your DeepSeek API key |
| Directory permission denied | Click Choose Folder again; Chrome may have revoked the grant after a browser restart |
| DeepSeek API error | Check that your key is valid and has sufficient balance at platform.deepseek.com |
| Duplicate rounds in raw files | Click Sync — it automatically deduplicates rounds and writes clean data to disk |
| No episodes generated after sync | Make sure your DeepSeek API key is configured; episode extraction runs automatically on sync when the key is present |
| Episodes folder looks stale after manual deletion | Deleting files does not clear browser storage. Open the Service Worker console (`chrome://extensions/` → Service Worker → Inspect) and run the reset commands, then click Sync again |
