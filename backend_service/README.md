# Local Backend Service

This folder contains the FastAPI backend used by the Chrome extension.

It is responsible for:

- storing extension settings
- reading and writing the local memory root
- importing raw conversations and platform-memory snapshots
- running organize and incremental memory flows
- exporting and injecting memory packages
- managing personal skills and recommended skills
- exposing job status for long-running popup actions

## Main API Endpoints

- `GET /api/health`
- `GET /api/settings`
- `POST /api/settings`
- `POST /api/settings/test-connection`
- `GET /api/summary`
- `GET /api/sync/status`
- `POST /api/sync/toggle`
- `POST /api/conversations/append`
- `POST /api/conversations/current/import`
- `POST /api/platform-memory/import`
- `POST /api/memory/organize`
- `GET /api/memory/categories`
- `GET /api/memory/items`
- `POST /api/export/package`
- `POST /api/inject/package`
- `GET /api/skills/my`
- `GET /api/skills/recommended`
- `POST /api/skills/recommended/refresh`
- `POST /api/skills/save`
- `POST /api/skills/export`
- `POST /api/skills/delete`
- `POST /api/skills/inject`
- `POST /api/import/history`
- `POST /api/cache/clear`
- `GET /api/jobs/{job_id}`

## Run Locally

From the repository root:

```bash
pip install -r backend_service/requirements.txt
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

`backend_service/requirements.txt` is the expected first-run install entrypoint. It also includes the runtime dependencies needed by the in-repo `llm_memory_transferor` modules imported by the backend.

Health check:

```bash
curl http://127.0.0.1:8765/api/health
```

## Default Runtime Settings

The backend currently defaults to:

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`
- `backend_url = http://127.0.0.1:8765`

The popup can override these values through `/api/settings`.

## Storage Behavior

If `storage_path` is configured, the backend uses that directory as the memory root.

If `storage_path` is empty, it falls back to:

```text
backend_service/.state/wiki/
```

Runtime backend state lives under:

```text
backend_service/.state/
```

This includes files and folders such as:

- `settings.json`
- `uploads/`
- `exports/`
- `wiki/`

## Memory Root Layout

The backend reads and writes a memory root with directories such as:

- `raw/`
- `platform_memory/`
- `episodes/`
- `profile/`
- `preferences/`
- `projects/`
- `workflows/`
- `skills/`
- `daily_notes/`
- `metadata/`

## Prompt Usage

The backend does not hardcode its processor prompts in Python. It loads editable text prompts from the repository-level `prompts/` directory, including:

- `episodes/episode_system.txt`
- `episodes/delta_system.txt`
- `nodes/profile_system.txt`
- `nodes/preferences_system.txt`
- `nodes/projects_system.txt`
- `nodes/workflows_system.txt`
- `nodes/daily_notes_system.txt`
- `nodes/skills_system.txt`
- `schema.txt`

## Notes

- Recommended skills are stored in `backend_service/catalog/recommended_skills/`.
- The backend also ships a built-in fallback recommended-skill catalog.
- On Windows, the service tries to prefer UTF-8 process output to reduce console encoding issues.
