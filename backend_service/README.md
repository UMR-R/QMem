# Local Backend Service

This folder contains the first local HTTP backend for the Chrome extension.

## What it does now

- exposes `GET /api/health`
- stores local settings
- returns summary counts from the existing memory folder layout
- exposes sync status placeholders for the popup
- keeps a minimal in-process job registry

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r backend_service/requirements.txt
```

3. Start the server from the repo root:

```bash
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

4. Test health:

```bash
curl http://127.0.0.1:8765/api/health
```

## State storage

Runtime state is written to:

```text
backend_service/.state/settings.json
```

That folder is ignored by git.
