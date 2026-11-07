# Configuration

Configuration is environment-driven. Do not commit real secrets. Use repo-relative example files (`backend/.env.example`) as the source for variable names and defaults.

## Backend environment

Copy and edit:

```bash
cd backend
cp .env.example .env   # PowerShell: Copy-Item .env.example .env
```

Key areas (verify current names/defaults in `backend/app/core/config.py` and `backend/.env.example`):

| Area | Examples | Notes |
|---|---|---|
| App/CORS | `APP_ENV`, `APP_NAME`, `FRONTEND_ORIGIN`, `ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Origins affect CORS and cookie/CSRF behavior. |
| Database | `DATABASE_URL` | PostgreSQL recommended for production; SQLite fallback may be used locally depending on config/runtime. |
| Auth/sessions | `SECRET_KEY`, session cookie settings | Keep secrets out of docs and git. |
| Google OAuth | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, redirect/origin settings | Optional; verify enabled behavior in environment. |
| Payments | Razorpay keys/settings, webhook secret | Optional integration; mock payment behavior may exist when payments are not fully configured (verify per environment). |
| Storage | local/S3-compatible settings | Affects verification/document upload handling. |
| Email | SMTP/provider settings | Optional; check implementation/integration modules. |
| Admin/bootstrap | bootstrap/admin-related settings if present | Use only as documented in env example/config; avoid assumptions in production. |

## Frontend configuration

- Dev API proxy: `frontend/vite.config.js` proxies `/api` to `http://127.0.0.1:8000`.
- Production API base/routing depends on deployment. The frontend client lives in `frontend/src/lib/api.js` and uses cookie/session-aware requests (with CSRF handling where applicable). Do not hardcode machine-specific URLs in docs.

## Security and privacy

- Never place real API keys, passwords, tokens, webhook secrets, or personal data in documentation.
- Use placeholders like `<your-database-url>` or `<razorpay-webhook-secret>`.
- Mark unverified deployment secrets/infrastructure as environment-specific.

## Verification checklist

- Backend starts with `.env` loaded.
- Frontend can reach `/api/v1/*` (dev proxy or deployed routing).
- Auth/session cookies and CSRF work for state-changing requests.
- Optional integrations (OAuth, payments, storage, email) are explicitly configured before testing those flows.
