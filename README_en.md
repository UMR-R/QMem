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
- `API Key`: the model API key used for memory organization
- `Local Directory`: the local memory folder. Choose a location that can be kept long term.

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

- `Sync Conversation`: continuously saves new conversations from the current platform to the local raw layer.
- `Migrate`: opens memory organization, selection, export, and injection.
- `Settings`: configures the local backend, API Key, local directory, and advanced options.
- `Skill`: manages My Skills and recommended Skills.

### Settings

- `Local Backend URL`: local FastAPI backend address.
- `API Key`: model provider key.
- `Local Directory`: storage directory for raw conversations and structured memory.
- `Import Conversation`: imports historical conversation files in `json`, `jsonl`, `md`, or `txt`.
- `Sync Memory`: automatically maintains memory after conversation sync.
- `Detailed Injection`: includes related raw turns during injection.
- `Clear All Memories` / `Clear Cache`: manages local data.

### Migrate

- `Add Current Conversation`: saves the current tab's conversation to local raw memory.
- `Add Platform Memory`: saves the current AI platform's reported saved memory, custom instructions, agent config, and platform skills.
- `Organize Memory`: rebuilds structured long-term memory from raw conversations and platform memory.
- `Export`: exports the selected memory package.
- `Inject`: injects selected memory into the current AI session.

### Skill

- `My Skill`: views saved Skills.
- `Recommended for You`: views backend-recommended Skills.
- `Add to My Skill`: saves recommended Skills.
- `Export` / `Inject Current Session`: migrates or uses Skills.

### Injection and Export

Regular injection:

- Injects structured memory nodes.
- Injects related episode summaries.
- Does not inject long raw conversation excerpts by default.

Detailed injection:

- Injects structured memory nodes.
- Injects episode summaries.
- Additionally injects related raw turns for cases that need complete context.

Export:

- Generates a portable memory package.
- Supports backup, copying to another device, or migration to another AI platform.

<br>

## Local Memory

Default memory directory:

```text
backend_service/.state/wiki/
```

Choose a local folder that you can keep long term. That folder is your local memory library.

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
