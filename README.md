# Memory Assistant

[中文文档](README.zh.md)

A Chrome extension that automatically captures AI conversations, builds layered memories, and lets you import them into any supported platform.

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
2. Click **设置** → enter your DeepSeek API key → click **保存**
3. Click **选择目录** → choose a local folder where memory files will be saved

---

## Usage

### Auto-capture (recommended)

The extension can silently capture and process every conversation in the background.

1. Click the extension icon
2. Toggle on **保持更新** — the extension will start capturing conversations on any supported platform
3. Toggle on **实时更新** — after each AI reply, the extension automatically calls DeepSeek to update your memory (profile, preferences, projects, episodes)

Once enabled, you can chat normally. Memory is built automatically without any manual steps.

> **Note:** Memories accumulated in the background are held in the browser's local storage. Click **同步** (the directory button) at any time to write them out to your chosen folder as readable JSON files.

---

### Sync to files

Click **同步** (the button showing your directory name) to flush all memory from browser storage to your local folder. This also removes any duplicate conversation rounds that may have been captured.

If your DeepSeek API key is configured, clicking 同步 also automatically extracts episodes from any conversations that were captured while **实时更新** was off. You don't need to enable 实时更新 retroactively — just click 同步 and episodes will be generated in the background before the files are written.

**Batch processing:** To avoid long waits and browser extension timeouts, each sync processes at most **10 conversations** at a time. If there are more remaining, the result area will show "还有 N 条对话待提取，再次点击同步继续" — just keep clicking 同步 until all conversations are processed. Each click takes roughly 30–60 seconds depending on conversation length.

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

### Manual export

For a higher-quality, structured memory snapshot of the current conversation:

1. Navigate to a supported platform with an active conversation
2. Click the extension icon → **导出并保存记忆**
3. The extension sends a structured extraction prompt to the AI, waits for the reply, then calls DeepSeek to update your persistent memory nodes

Use this when you want a careful, complete capture of an important conversation.

---

### Build persistent memory nodes

Persistent nodes are cross-session patterns distilled from multiple episodes (e.g., "prefers concise answers", "working on project X").

**First time / after many new conversations:**

Click **从历史对话重建记忆节点**. The extension reads all captured episodes, skips any already processed, and calls DeepSeek to extract stable patterns. Progress is shown in the status area.

**Merge duplicates:**

Click **整理节点（合并相似）** to ask DeepSeek to find and merge semantically overlapping nodes (e.g., multiple sub-topics under the same subject area).

---

### Import memory into a new conversation

1. Start a new conversation on any supported platform
2. Click the extension icon → **按标签导入记忆**
3. A panel lists all persistent nodes grouped by type (preferences, profile, topics, etc.). Nodes with high confidence or high export priority are pre-checked
4. Check the nodes you want to load
5. Click **确认导入选中节点**

The extension uploads a memory package (selected nodes + supporting episode evidence) to the AI and sends a cold-start prompt, giving the AI full context from your past conversations.

---

## Customizing prompts

All prompts used by the extension are plain text and can be edited directly in the source files — no build step required.

| Prompt | File | Purpose |
|---|---|---|
| Export prompt | `config.js` → `CONFIG.skills.episodicTag` | Injected into the target AI during **导出并保存记忆**. Instructs the AI to output a structured JSON summary of the conversation. Edit this to change what fields are captured or how the AI is asked to summarize. |
| Persistent distill prompt | `config.js` → `CONFIG.skills.persistentDistill` | Sent to DeepSeek after export to extract cross-session patterns (persistent nodes). Edit this to change how nodes are named, merged, or prioritized. |
| Architecture context | `config.js` → `CONFIG.skills.architecture` | Shared preamble prepended to both prompts above. Describes the two-layer memory structure (episodic + persistent). |
| Import cold-start prompt | `config.js` → `CONFIG.load` | Sent to the target AI after uploading the memory package during **确认导入选中节点**. Edit this to change how the AI is instructed to use the imported memory. |
| Auto-capture delta prompt | `background/memory_engine.js` → `_getDeltaSystem()` | Used during **实时更新** to extract incremental changes (profile, preferences, projects) from each conversation round. Edit this to tune what the background processor picks up. |

**Notes:**
- `config.js` is loaded by the popup. `memory_engine.js` runs in the Service Worker — these are separate contexts, so each maintains its own copy of the distill prompt.
- The export prompt contains a `{{EXISTING_TAGS}}` placeholder that is replaced at runtime with your current tag list. Keep this placeholder if you edit the prompt.
- After editing any file, reload the extension at `chrome://extensions/` for changes to take effect.

---

## Typical workflow

```
Daily chatting
  └─ 保持更新 + 实时更新 ON → memory builds automatically

After each session
  └─ Click 同步 → files updated in your directory

Periodically
  └─ Click 从历史对话重建记忆节点 → distill new episodes into persistent nodes
  └─ Click 整理节点 → clean up overlapping nodes

Starting a new chat on any platform
  └─ Click 按标签导入记忆 → select nodes → 确认导入
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Capture doesn't trigger | Reload the page after enabling 保持更新; the extension needs to inject into the page |
| Buttons don't respond | The AI platform may have updated its UI; reload the extension and try again |
| "API Key 未配置" error | Click 设置 and re-enter your DeepSeek API key |
| "权限被拒绝" on directory | Click the directory button again; Chrome may have revoked the grant after a browser restart |
| DeepSeek API error | Check that your key is valid and has sufficient balance at platform.deepseek.com |
| Duplicate rounds in raw files | Click 同步 — it automatically deduplicates rounds and writes clean data to disk |
| No episodes generated after sync | Make sure your DeepSeek API key is configured; episode extraction runs automatically on sync when the key is present |
| Episodes folder looks stale after manual deletion | Deleting files does not clear browser storage. To fully reset episodes: open the Service Worker console (`chrome://extensions/` → Service Worker → 检查) and run the reset commands from the PROJECT_SPEC.md debugging section, then click 同步 again |
