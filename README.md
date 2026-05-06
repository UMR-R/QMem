# QMem

<p align="center">
  <img src="docs/images/icon.png" alt="QMem logo" width="96">
</p>

[中文说明](README_zh.md)

QMem is a browser extension for AI conversations. It saves your conversations from platforms such as ChatGPT, Gemini, DeepSeek, and Doubao to local storage, then organizes them into long-term memory that can be viewed, selected, deleted, exported, and injected into a new AI session.

The basic workflow is simple: load the extension, configure the local backend and model API, click `同步对话` on the home page, then organize and migrate memory from the `迁移` page. The `同步记忆` switch in `设置` can be used for automatic incremental memory maintenance.

## Quickstart

### 1. Download and load the browser extension

1. Download this repository, or download the ZIP file and unzip it.
2. Open your browser extension management page.
   - Chrome / Arc / Brave: `chrome://extensions/`
   - Edge: `edge://extensions/`
3. Turn on Developer mode.
4. Click Load unpacked.
5. Select the repository root:

```text
QMem/
```

After loading succeeds, the QMem extension icon will appear in the browser toolbar.

### 2. Get familiar with the three main pages

The home page is used to start sync, enter migration, open settings, and manage Skills.

![QMem home page](docs/images/qmem-home.png)

The settings page is used to configure the local backend, model API, `本地目录`, and advanced switches.

![QMem settings page](docs/images/qmem-settings.png)

The migration page is used to organize memory, select memory items, export a memory package, or inject memory into the current AI session.

![QMem migration page](docs/images/qmem-organize.png)

<!-- If the screenshots above do not render, place them here:

```text
docs/images/qmem-home.png
docs/images/qmem-settings.png
docs/images/qmem-organize.png
``` -->

### 3. Configure the local backend, model, and local directory

The QMem extension calls a local API backend to save files, organize memory, and call the model. On first use, install dependencies from the repository root:

```bash
pip install -r backend_service/requirements.txt
```

Start the local backend when using QMem:

```bash
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

Then open the extension's `设置` page and fill in at least:

- `本地后端地址`: recommended value is `http://127.0.0.1:8765`
- `API Key`: the model API key used for memory organization
- `本地目录`: the local memory folder. Choose a location that can be kept long term.

After filling in the fields, click the corresponding `保存`, then click `测试连接` to confirm that the API is available.

The backend currently uses an OpenAI-compatible interface by default:

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

### 4. Start sync and organize memory

1. Click `同步对话` on the home page. The `同步记忆` switch in `设置` controls whether QMem also performs incremental memory maintenance after sync.
2. Continue chatting on a supported platform. QMem will save the raw conversation locally.
3. Go to `迁移` and click `整理记忆`.
4. After organization finishes, you can select profile, preferences, project memory, workflows, daily notes, and Skills.
5. Click `导出` to generate a migration package, or click `注入` to write the selected memory into the current AI session.

## Three Core Modules

### 1. Browser Extension

The extension handles user interaction, page-side collection, and memory injection.

Home page:

- Start or pause `同步对话`.
- Show sync status.
- Enter `迁移`, `设置`, and `Skill`.

Settings page:

- Configure `本地后端地址`.
- Configure `API Key`, then click `测试连接` to check the model API.
- Set `本地目录`.
- Click `导入对话` to import historical conversation files. Supported formats are `json`, `jsonl`, `md`, and `txt`.
- Turn `同步记忆` on or off.
- Turn `详细注入` on or off.
- Click `清理所有记忆` or `清理缓存` to manage local data.

Migration page:

- `加入当前对话`: save the current tab's conversation to local raw memory.
- `加入平台记忆`: ask the current AI platform to report its saved memory, custom instructions, agent config, and skills, then save that snapshot as platform memory.
- `整理记忆`: rebuild structured long-term memory from raw conversations and platform memory.
- `导出`: export the selected memory package.
- `注入`: inject the selected memory into the current AI session.

Skill page:

- View backend-recommended Skills.
- Click `加入我的 Skill` to save recommended Skills.
- Click `导出` or `注入当前会话` to use Skills.
- Manage saved Skills.

### 2. Local Backend

The local backend lives in `backend_service/`. It is responsible for:

- Reading and writing local memory files.
- Maintaining settings.
- Calling the model API to organize memory.
- Generating frontend display titles and summaries.
- Generating export packages and injection content.
- Managing recommended Skills and saved Skills.

If the extension says the backend is unavailable, check that:

- The backend process is running.
- `本地后端地址` in `设置` matches the port used by the backend.
- The browser is not blocking local requests.
- The API Key and model configuration are available.

### 3. Local Memory Files

QMem writes raw conversations and structured memory to the local directory you configure. If no directory is configured, it defaults to:

```text
backend_service/.state/wiki/
```

Choose a local folder that you can keep long term. That folder is your local memory library.

## Memory Layers

QMem manages memory in layers rather than storing one long text blob.

### Raw

The raw layer stores original chat content collected from webpages or imported from files.

Directory:

```text
raw/
```

All later memory should be traceable back to raw conversations.

### Platform Memory

The platform memory layer stores memory signals that an AI platform already holds or generates, such as:

- saved memory
- conversation summary
- profile / preferences
- custom instructions
- agent config
- platform skills

Directory:

```text
platform_memory/
```

### Episodes

Episodes are conversation-level memory units extracted from raw conversations. The current implementation primarily uses one conversation turn as the unit, while retaining its session, time, summary, keywords, turn refs, and episode connections.

Directory:

```text
episodes/
```

Episodes are the evidence base for profile, preferences, projects, workflows, daily notes, and skills.

### Persistent Memory

Persistent memory organizes episodes and platform memory into more stable structures:

- `profile/`: user profile, such as identity, knowledge background, and long-term focus.
- `preferences/`: preferences, such as language preference, expression style, format constraints, and main task types.
- `projects/`: project memory, such as long-term projects, current stage, goals, context, and status.
- `workflows/`: workflows / SOPs, such as methods, processes, and collaboration habits the user repeatedly uses.
- `daily_notes/`: daily notes, such as life preferences, choice patterns, and non-project context.
- `skills/`: Skill assets saved or recommended for the user.
- `metadata/`: indexes, organize state, display text, and delete / ignore records.

These items appear in the frontend as selectable memory entries. You can delete entries you do not want to keep. After deletion, QMem records ignore / lock state to avoid regenerating the same memory item in the next organization run.

## Injection and Export

After organization finishes, you can select memory to migrate from the `迁移` page.

Regular injection:

- Inject structured memory nodes.
- Inject related episode summaries.
- Do not inject long raw conversation excerpts by default.

Detailed injection:

- Inject structured memory nodes.
- Inject episode summaries.
- Additionally inject related raw turns for cases that need complete context.

Export:

- Generate a portable memory package.
- Use it for backup, copying to another device, or migrating to another AI platform.

## Sync Mechanism

QMem has two related controls:

- `同步对话`: the home-page button that continuously saves new conversations from the current platform to the local raw layer.
- `同步记忆`: the advanced setting that controls whether QMem also performs incremental memory maintenance after sync.

Common workflow:

1. Turn on sync.
2. Chat with AI as usual.
3. Later, go to `迁移` and click `整理记忆`.
4. Select the memory you want to export or inject.

## Repository Structure

- `popup/`: extension popup page.
- `content/`: page-side collection and injection logic.
- `background/`: extension background logic and incremental sync.
- `backend_service/`: local FastAPI backend and recommended Skill catalog.
- `prompts/`: runtime prompts.
- `memory_transferor/`: Python memory pipeline, storage models, policies, and export tools.
