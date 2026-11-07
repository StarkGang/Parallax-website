# Installation

Local installation for the Parallax-website repository (React/Vite frontend + FastAPI backend).

## Prerequisites

- Git
- Node.js and npm (frontend)
- Python `>=3.12,<3.13` (backend; see `backend/pyproject.toml`)
- `uv` recommended for backend dependency management (repo includes `backend/uv.lock`)

## Clone and enter the repository

```bash
git clone <your-fork-or-repo-url>
cd <repository-root>
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite serves the SPA locally (default port commonly `5173`; check terminal output). The dev server proxies `/api` to `http://127.0.0.1:8000` by default (`frontend/vite.config.js`).

## Backend

```bash
cd backend
uv sync
cp .env.example .env   # PowerShell: Copy-Item .env.example .env
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Alternative (pip): create/activate a virtual environment, install dependencies compatible with `pyproject.toml`, then run uvicorn. A checked-in `.venv` is not assumed.

## Database note

- SQLite is the default fallback for local development when PostgreSQL is unavailable/unconfigured (see `backend/app/core/config.py` / `backend/app/db/session.py` behavior).
- PostgreSQL is recommended for production-like testing. `backend/.env.example` includes `DATABASE_URL` guidance.

## Verify

- Frontend: open the local Vite URL.
- Backend: `GET /health` and `GET /docs` on the API server.

## Next

- [Configuration](configuration.md)
- [Development setup](development-setup.md)
- [Troubleshooting](../troubleshooting/common-issues.md)
