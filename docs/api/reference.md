# API Reference

Summary of the backend HTTP API mounted under `/api/v1` (see `backend/app/main.py` and routers in `backend/app/api/v1/`). This is an implementation map, not a substitute for runtime OpenAPI docs.

## Runtime references

- OpenAPI/interactive docs: backend serves FastAPI docs (commonly `/docs`) when enabled.
- Frontend client: `frontend/src/lib/api.js` contains request helpers and endpoint usage patterns.
- Routers: `backend/app/api/v1/public.py`, `auth.py`, `me.py`, `participant.py`, `admin.py`, `webhooks.py` (verify exact filenames/exports in repo).

## Route groups (high level)

| Group | Purpose | Notes |
|---|---|---|
| Public | Public content/data needed by SPA pages | Read-oriented; verify exact paths in `public.py` and frontend calls. |
| Auth | Login/register/session and optional Google OAuth flows | Cookie/session + CSRF/origin behavior applies; OAuth is env-dependent. |
| Me / session context | Current user/session/profile context | Used by portal UI to determine access/state. |
| Participant | Registration, participation, team/verification/payment-related user actions | Server-authoritative business rules; money in integer paise where applicable. |
| Admin | Administrative/content/management operations | Requires appropriate authorization; verify permissions server-side. |
| Webhooks | External callbacks (e.g., payment provider) | Signature/secret validation is environment-specific; do not expose secrets. |

## Conventions

- **Base path:** `/api/v1`.
- **Auth:** cookie/session-oriented patterns are used by the SPA; state-changing requests must satisfy CSRF/origin checks as implemented.
- **Errors:** expect HTTP status codes and JSON error payloads; exact shape should be confirmed against backend handlers/schemas.
- **Contracts:** when changing behavior, update backend schema/handler and `frontend/src/lib/api.js` together, then update this doc.

## Verification guidance

For exact request/response fields, confirm:
1. Router handler signature and response schema in `backend/app/api/v1/*.py` and `backend/app/schemas/*`.
2. Frontend usage in `frontend/src/lib/api.js` and calling pages/components.
3. Live OpenAPI output from a running backend.
