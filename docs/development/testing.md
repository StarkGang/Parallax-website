# Testing

Testing guidance based on repository tooling. Run commands from repo-relative directories; record unexecuted checks explicitly.

## Frontend

From `frontend/`:

```bash
npm test
npm run build
```

Check `frontend/package.json` for the exact test runner/scripts configured in the current checkout.

## Backend

From `backend/` (environment/dependencies required):

```bash
uv run pytest
```

The backend uses Python `>=3.12,<3.13` (`backend/pyproject.toml`). If `.venv`/dependencies/services are not configured, pytest may not run; report that state instead of claiming results.

## What to verify when changing code

- **API contract changes:** update backend route/schema/service and frontend `src/lib/api.js`/consumers together.
- **Auth/session/CSRF changes:** test login/session flows and state-changing requests with correct origins.
- **Registration/payment/verification flows:** test server-authoritative behavior; do not rely on mock paths as production proof.
- **Routing/hosting changes:** verify SPA deep-link refresh behavior with host rewrites.
- **Docs changes:** run markdown-only relative-link and local-path leak scans.

## CI / automation

CI configuration was not verified as part of this documentation pass. If workflows exist, treat them as the authoritative automated checks and keep this doc aligned with them.
