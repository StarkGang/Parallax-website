# Common Issues

## Frontend can’t reach backend API

- In dev, confirm backend runs on `127.0.0.1:8000` and Vite proxy (`frontend/vite.config.js`) targets it.
- In deployed environments, confirm frontend/API routing and CORS/allowed origins match.
- Check browser network tab for 401/403/CSRF/CORS failures.

## SPA deep link returns 404 on refresh

- Cause: host serves static files without SPA fallback.
- Fix: configure rewrite/fallback to `index.html` (see `vercel.json` / deployment config).

## Auth/session/CSRF failures

- Verify `FRONTEND_ORIGIN`, `ALLOWED_ORIGINS`, and CSRF trusted origins.
- Ensure requests use credential/cookie behavior expected by `frontend/src/lib/api.js` and backend middleware.
- Check HTTPS/domain cookie settings in production (environment-specific).

## Backend fails to start

- Verify Python version (`>=3.12,<3.13`) and dependencies installed.
- Verify `.env` exists and required values are set.
- Check database connectivity/URL; SQLite fallback behavior is environment/config dependent.

## Payments/webhooks not behaving as expected

- Confirm provider keys/webhook secret are configured in the target environment.
- Do not assume mock payment paths represent production.
- Validate webhook endpoint reachability and signature verification from provider/dashboard logs (external, unverified here).

## Docs contain local machine paths

- Run a markdown-only scan for Windows user-profile paths, macOS user-profile paths, local usernames/machine IDs, `file:///` URLs, and repo-local absolute paths.
- Replace with repo-relative paths or placeholders like `<repository-root>`.
