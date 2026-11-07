# Development Setup

Repo-relative workflow for running and changing Parallax-website locally.

## Run both services

### Backend (terminal 1)

```bash
cd backend
uv sync
cp .env.example .env   # PowerShell: Copy-Item .env.example .env
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

## Development boundaries

- Frontend SPA entry/routing: `frontend/src/main.jsx` (`BrowserRouter`), `frontend/src/App.jsx`.
- API client boundary: `frontend/src/lib/api.js` (preferred place for backend calls).
- Backend app factory: `backend/app/main.py`.
- API routers: `backend/app/api/v1/*.py`, mounted under `/api/v1`.
- Models: `backend/app/models/*.py`; schemas/services/integrations live under `backend/app/schemas`, `backend/app/services`, `backend/app/integrations`.

## Local behavior notes

- Vite proxies `/api` to the backend in development.
- Cookies/sessions/CSRF: state-changing requests must satisfy backend CSRF/origin expectations; use the shared API client patterns.
- SQLite fallback and seed data may be used in local/dev scenarios depending on environment and implementation; verify behavior before assuming production parity.
- Money values in payment/commerce logic are handled as integer paise.

## Typical change workflow

1. Identify the affected surface (public SPA route, participant flow, admin flow, API route, model/schema/service).
2. Update backend contract and frontend consumer together when API behavior changes.
3. Run relevant checks (frontend tests/build, backend tests/lint where configured).
4. Update docs when routes, config, deployment, or feature behavior changes.

## Useful commands

```bash
# frontend
cd frontend && npm test
cd frontend && npm run build

# backend (requires configured environment/dependencies)
cd backend && uv run pytest
```

If backend tests cannot run locally (e.g., missing environment/dependencies), report that explicitly rather than claiming verification.
