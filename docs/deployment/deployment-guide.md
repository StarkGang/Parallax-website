# Deployment Guide

Deployment is implementation-specific and depends on hosting/provider configuration. Use repository artifacts as the source of truth and verify live infrastructure settings outside the repo.

## Repository deployment artifacts

| Artifact | Purpose |
|---|---|
| `frontend/` build (`npm run build`) | Produces SPA static assets for static hosting/CDN. |
| `vercel.json` | Vercel-oriented config (including SPA rewrite behavior where configured). |
| `render.yaml` | Render blueprint/service configuration (verify current service/env setup). |
| `Dockerfile` | Container build/runtime entrypoint for backend or combined deployment pattern as defined in file. |
| `api/index.py` | Python/serverless entrypoint used by some deployment targets (verify target-specific behavior). |

## SPA routing requirement

Because the frontend uses path-based routing (`BrowserRouter`), deployed static hosting must rewrite unknown routes to `index.html`. Missing rewrites commonly cause refresh/deep-link 404s.

## Backend deployment checklist

- Set required environment variables from `backend/.env.example`/config (no secrets in docs).
- Configure database (`DATABASE_URL`) appropriate for the environment.
- Configure `FRONTEND_ORIGIN` / allowed origins / CSRF trusted origins to match deployed frontend URLs.
- Configure auth secrets/cookies for HTTPS/production domains.
- Enable and verify optional integrations explicitly: Google OAuth, payments/webhooks, storage, email.

## Payments/webhooks (environment-specific)

- Razorpay/live payment processing requires valid keys and webhook secret configuration in the deployment environment.
- Webhook endpoint reachability and signature verification must be tested in that environment.
- Mock payment behavior, if present in code paths, must not be documented as production behavior without verification.

## Database migrations/seed

- SQLAlchemy models define schema intent; migration tooling/operational workflow (e.g., Alembic usage in deployed environments) is not fully verifiable from docs alone unless explicitly configured/documented in the target environment.
- Local SQLite fallback/seed behavior is convenient for development but not a production guarantee.

## Post-deploy verification

- `GET /health` (or equivalent health endpoint) responds.
- SPA loads and deep links work on refresh.
- `/api/v1` requests succeed from the deployed frontend origin.
- Auth/session/CSRF flows work on the deployed domain.
- Optional integrations (OAuth, payments, uploads, email) are tested only after environment configuration is confirmed.
