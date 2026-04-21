# Memory Assistant

[中文文档](README_zh.md)

A Chrome extension that automatically captures AI conversations, builds a two-layer memory system (episodic + persistent), and lets you inject or export your memory into any supported platform.

## Supported platforms

| Platform | Domain |
|---|---|
| ChatGPT | chatgpt.com / chat.openai.com |
| Google Gemini | gemini.google.com |
| DeepSeek | chat.deepseek.com |
| Doubao (豆包) | www.doubao.com |

---

## Memory architecture

The extension organises memory in two layers:

**Episodic memory** — a structured export of a single conversation: summary, user profile snapshot, active projects, preferences, and workflows observed in that session. Each record has a unique `ep_XXXX` ID and is stored per-conversation. This is the raw evidence layer.

**Persistent nodes** — cross-session patterns distilled from multiple episodic records by DeepSeek. Each node has a type (`preference`, `profile`, `workflow`, `topic`, `platform`), a confidence level (`low` → `medium` → `high` based on how many episodes support it), and back-links to the episodes that contributed to it. These are what you inject or export when moving to a new platform.

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
2. Click **API Key** (top-right pill button) → enter your DeepSeek API key → click **保存**
3. Click **选择目录** in the directory badge → choose a local folder where memory files will be saved
4. The badge will display the folder name and the central **同步** button becomes active

---

## Interface

```
┌─────────────────────────────────────────┐
│  Memory Assistant              [API Key] │  ← header
├─────────────────────────────────────────┤
│                                         │
│            ╭ ─ ─ ─ ─ ─ ╮               │
│           │   ↺   同步   │              │  ← main sync button
│            ╰ ─ ─ ─ ─ ─ ╯               │    (disabled until dir selected)
│                                         │
│     📁  folder-name  [更换]             │  ← directory badge + select button
│                                         │
│   ┌─────────────────────────────────┐   │
│   │  🕐  保持更新         ◯        │   │  ← toggles card
│   │  ⚡  实时更新         ◯        │   │
│   └─────────────────────────────────┘   │
│                                         │
│   ┌── 导出并保存记忆 ────────────────┐  │  ← export current conversation
│   └──────────────────────────────────┘  │
├─────────────────────────────────────────┤
│  导入历史 │ 重建节点 │ 整理节点 │ 按标签导入 │  ← footer
└─────────────────────────────────────────┘
```

**同步** (circle) — Flush browser storage to your local folder and extract episodes from any unprocessed conversations. Disabled until a directory is selected.

**选择目录 / 更换** — Pick or change the local folder. Appears inside the directory badge.

**保持更新** — Capture every conversation on supported platforms in the background.

**实时更新** — After each AI reply, automatically call DeepSeek to update your memory. Requires 保持更新 to be on.

**导出并保存记忆** — Send a structured extraction prompt to the current AI, then have DeepSeek update your persistent nodes from the reply.

**Footer links:**
- **导入历史** — Import a ChatGPT / DeepSeek export file
- **重建节点** — Distill all unprocessed episodes into persistent nodes
- **整理节点** — Merge semantically overlapping nodes
- **按标签导入** — Browse and select persistent nodes to inject or export

---

## Usage

### Auto-capture (recommended)

The extension can silently capture and process every conversation in the background.

1. Click the extension icon → toggle on **保持更新**
2. (Optional) Toggle on **实时更新** for per-round memory updates via DeepSeek
3. Chat normally — conversations are captured automatically
4. Click **同步** at any time to flush to disk and extract episodes

### Build memory from history

Import an existing ChatGPT / DeepSeek conversation export in one go.

1. Export your history
   - **ChatGPT**: Settings → Data controls → Export data → download ZIP → unzip → use `conversations.json`
   - **DeepSeek**: use the exported file directly
2. Click the extension icon → footer **导入历史** → select the file
3. Conversations are parsed and episode extraction starts automatically
4. Processing runs in batches of 10. If more remain, the status bar shows "还有 N 条待提取" — click **同步** to continue
5. (Optional) Click **重建节点** to distill episodes into persistent nodes; click **整理节点** to merge overlapping nodes

---

### Sync to files

Click the **同步** button (center circle) to flush all memory from browser storage to your local folder. Duplicate conversation rounds are removed automatically.

If your DeepSeek API key is configured, clicking 同步 also extracts episodes from conversations captured while **实时更新** was off — no need to re-enable it.

**Batch processing:** Each sync processes at most **10 conversations** at a time. If there are more, the status area will show "还有 N 条对话待提取，再次点击同步继续".

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

Click **按标签导入** in the footer to open the node panel.

#### Inject into current conversation

Select nodes → choose a target platform → click **注入当前对话**: the extension uploads a memory package (selected nodes + supporting episode evidence) to the current AI and sends a cold-start prompt.

#### Export to file (cross-platform migration)

Select nodes → choose a target platform → click **导出文件**: generates a `.txt` file containing your memory data and a cold-start prompt formatted for the chosen platform. Paste it into any platform's system prompt or custom instructions field.

| Target | Format |
|---|---|
| Claude | XML-tagged (`<memory_package>`) |
| ChatGPT | Instructions + data separator |
| DeepSeek | Same as above |
| Generic | Plain text, works with any system prompt field |

#### Maintain nodes

- **重建节点**: Scans all episodes not yet distilled into persistent nodes and processes them one by one. Use this after accumulating many conversations with **实时更新** off.
- **整理节点**: Asks DeepSeek to find and merge semantically overlapping nodes.

---

## Customizing prompts

All prompts live as plain-text files in the `prompts/` directory. Edit them directly — no JS changes or build step required.

| File | Sent to | Triggered by |
|---|---|---|
| `prompts/episode_extract.txt` | Target AI (current page) | 导出并保存记忆 |
| `prompts/schema.txt` | Prepended to `persistent_node_distill.txt` as DeepSeek system prompt | 导出并保存记忆 / 重建节点 / 整理节点 |
| `prompts/persistent_node_distill.txt` | DeepSeek API (popup) — full ruleset | After 导出并保存记忆 / 重建节点 / 整理节点 |
| `prompts/persistent_node_distill_bg.txt` | DeepSeek API (Service Worker) — compact, self-contained | 实时更新 per-round / 同步 |
| `prompts/delta_extract.txt` | DeepSeek API (Service Worker) — incremental delta per round | 实时更新 per-round / 同步 |
| `prompts/cold_start.txt` | Target AI | 注入当前对话 / 导出文件 |

To apply edits: save the file → go to `chrome://extensions/` → click the reload icon → reopen the popup.

**Notes:**
- `episode_extract.txt` contains a `{{EXISTING_TAGS}}` placeholder that is replaced at runtime with your existing tag list — keep it when editing.
- `schema.txt` defines the two-layer memory schema. It is prepended to `persistent_node_distill.txt` for popup calls, but **not** to `episode_extract.txt` — the target AI only needs to know how to extract, not the full schema.
- `persistent_node_distill.txt` vs `persistent_node_distill_bg.txt`: the popup version is combined with `schema.txt` at runtime and contains the full ruleset (detailed merge logic, sub-topic aggregation, granularity rules). The background version is self-contained — it embeds the schema definition directly — and uses a compact format suited for automatic per-round processing by the Service Worker.

---

## Typical workflow

```
Build from history
  └─ Footer → 导入历史 → select export file → episodes extracted automatically
  └─ Click 同步 (circle) → files written to your directory
  └─ (Optional) Footer → 重建节点 → distill episodes into persistent nodes
  └─ (Optional) Footer → 整理节点 → clean up overlapping nodes

Live maintenance
  └─ 保持更新 + 实时更新 ON → memory builds automatically
  └─ After each session, click 同步 → files updated

Starting a new chat on any platform
  └─ Footer → 按标签导入 → select nodes → choose target platform
  └─ 注入当前对话: inject directly into the current AI session
  └─ 导出文件: generate a .txt file to paste into any platform
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Capture doesn't trigger | Reload the page after enabling 保持更新; the extension needs to inject into the page |
| Buttons don't respond | The AI platform may have updated its UI; reload the extension and try again |
| "API Key 未配置" error | Click **API Key** (top-right) and re-enter your DeepSeek API key |
| Directory permission denied | Click **更换** in the directory badge; Chrome may have revoked the grant after a browser restart |
| DeepSeek API error | Check that your key is valid and has sufficient balance at platform.deepseek.com |
| Duplicate rounds in raw files | Click **同步** — it automatically deduplicates rounds |
| No episodes generated after sync | Make sure your DeepSeek API key is configured; episode extraction runs automatically on sync |
| Episodes folder looks stale after manual deletion | Deleting files does not clear browser storage. Open the Service Worker console (`chrome://extensions/` → Service Worker → 检查) and run reset commands, then click 同步 again |
