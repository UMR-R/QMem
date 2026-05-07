<p align="center">
  <img src="docs/images/slogan.png" alt="QMem slogan" width="460">
</p>

<p align="center">
  <strong>Welcome contributors:</strong> Xinan Xu, Haoran Wang, Xinting Hu
</p>

<p align="center">
  <a href="README.md">中文说明</a>
</p>

QMem is a browser extension for AI conversations. It saves conversations from ChatGPT, Gemini, DeepSeek, Doubao, and other AI platforms to local storage, then organizes them into long-term memory that can be viewed, selected, deleted, exported, and injected into a new AI session.

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#pages">Pages</a> ·
  <a href="#local-memory">Local Memory</a> ·
  <a href="#repository-structure">Repository Structure</a>
</p>

<br>

## Interface Preview

<table>
  <tr>
    <td width="33%"><img src="docs/images/qmem-home.png" alt="QMem home page"></td>
    <td width="33%"><img src="docs/images/qmem-settings.png" alt="QMem settings page"></td>
    <td width="33%"><img src="docs/images/qmem-organize.png" alt="QMem migrate page"></td>
  </tr>
  <tr>
    <td align="center">Home</td>
    <td align="center">Settings</td>
    <td align="center">Migrate</td>
  </tr>
</table>

<br>

## Quickstart

### 1. Load the extension

1. Download this repository, or download the ZIP file and unzip it.
2. Open your browser extension management page.
   - Chrome / Arc / Brave: `chrome://extensions/`
   - Edge: `edge://extensions/`
3. Turn on Developer mode.
4. Click Load unpacked.
5. Select the repository root `QMem/`.

After loading succeeds, the QMem extension icon will appear in the browser toolbar.

### 2. Start the local backend

On first use, install dependencies from the repository root:

```bash
pip install -r backend_service/requirements.txt
```

Start the local backend when using QMem:

```bash
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

### 3. Configure Settings

Open the extension Settings page and fill in:

- `Local Backend URL`: recommended value is `http://127.0.0.1:8765`
- `API Key`: used for memory organization and automatic extraction. You can leave it unconfigured if you only want to record raw conversations.
- `Local Directory`: leave it empty to use the default directory, or enter a long-term absolute path.

Then click `Save` and `Test Connection`.

The backend currently uses an OpenAI-compatible interface by default:

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

### 4. Sync, organize, and migrate

1. Click `Sync Conversation` on the Home page.
2. Turn on `Sync Memory` in Settings if you want automatic incremental memory maintenance.
3. Continue chatting on a supported platform, or click `Add Current Conversation` / `Add Platform Memory` on the Migrate page.
4. Go to Migrate and click `Organize Memory`.
5. Select the memory you want, then click `Export` or `Inject`.

<br>

## Pages

### Home

- `Sync Conversation`: starts or pauses conversation capture on the current platform. When enabled, QMem keeps saving new user / assistant turns to the local raw layer.
- `Migrate`: opens the memory migration workspace. Use it to add the current conversation, add platform memory, organize memory, select memory items, export, or inject.
- `Settings`: opens local configuration for the backend URL, API Key, local directory, sync behavior, injection behavior, and data cleanup.
- `Skill`: opens Skill management for saved Skills, recommended Skills, Skill export, and Skill injection.

### Settings

- `Local Backend URL`: the local FastAPI backend address, usually `http://127.0.0.1:8765`. The extension uses it to read/write memory and call organization APIs.
- `API Key`: the model provider key used to organize memory, generate structured nodes, and produce frontend display text. It is not required when only recording raw conversations.
- `Test Connection`: checks whether the local backend and model API are available. Use it after first setup or after replacing the key.
- `Local Directory`: sets the storage directory for raw conversations, episodes, persistent memory, and metadata. Leave it empty to use the default directory; use an absolute path when customizing it.
- `Import Conversation`: imports historical conversation files in `json`, `jsonl`, `md`, or `txt` into the local raw layer.
- `Sync Memory`: when enabled, newly synced conversations automatically trigger incremental memory maintenance. When disabled, you can organize manually later.
- `Detailed Injection`: controls whether `Inject` also includes related raw turns. When disabled, injection includes structured memory and episode summaries; when enabled, it includes more original context.
- `Clear All Memories`: deletes saved raw conversations and structured memory while keeping current settings.
- `Clear Cache`: clears temporary cache while keeping primary memory files.

### Migrate

- `Add Current Conversation`: saves the AI conversation in the current tab to local raw memory. Use it when you want to add the conversation you are currently viewing to QMem.
- `Add Platform Memory`: asks the current AI platform to report saved memory, custom instructions, agent config, and platform skills, then saves that report as a platform memory snapshot.
- `Organize Memory`: rebuilds structured long-term memory from raw conversations and platform memory, including profile, preferences, projects, workflows, daily notes, and Skills.
- `Export`: turns the selected memory items into a portable memory package. The package can be used for backup, copied to another device, or migrated to another AI platform.
- `Inject`: writes the selected memory into the current AI session. Regular injection includes structured memory nodes and related episode summaries, without long raw conversation excerpts by default. If `Detailed Injection` is enabled in Settings, QMem also injects related raw turns for cases that need complete context.

### Skill

- `My Skill`: shows Skills already saved locally.
- `Recommended for You`: shows backend-recommended Skills based on the current catalog and memory context.
- `Add to My Skill`: saves selected recommended Skills into My Skill for later export or injection.
- `Export`: exports selected Skills for backup or migration.
- `Inject Current Session`: writes selected Skills into the current AI session so the conversation can temporarily use those capability instructions.

<br>

## Local Memory

Default memory directory:

```text
backend_service/wiki/
```

You can leave `Local Directory` empty in Settings. When it is empty, QMem uses the default directory above. If you customize it, enter an absolute path that is valid on your operating system.

QMem uses layered memory:

- `raw/`: original conversations collected from webpages or imported files.
- `platform_memory/`: memory signals already saved or generated by external AI platforms.
- `episodes/`: conversation-level memory units extracted from raw conversations.
- `profile/`: user profile, such as identity, knowledge background, and long-term focus.
- `preferences/`: preferences, such as language preference, expression style, format constraints, and main task types.
- `projects/`: project memory, such as long-term projects, current stage, goals, context, and status.
- `workflows/`: workflows / SOPs, such as repeated methods, processes, and collaboration habits.
- `daily_notes/`: daily notes, such as life preferences, choice patterns, and non-project context.
- `skills/`: Skill assets saved or recommended for the user.
- `metadata/`: indexes, organize state, display text, and delete / ignore records.

After you delete an unwanted memory item, QMem records ignore / lock state to avoid regenerating the same item in the next organization run.

<br>

## Repository Structure

- `popup/`: extension popup page.
- `content/`: page-side collection and injection logic.
- `background/`: extension background logic and incremental sync.
- `backend_service/`: local FastAPI backend and recommended Skill catalog.
- `prompts/`: runtime prompts.
- `memory_transferor/`: Python memory pipeline, storage models, policies, and export tools.
