# Coding Guidelines

Follow the repository's existing patterns and keep docs/code aligned with implementation.

## General

- Make minimal, targeted changes; avoid unrelated refactors.
- Preserve working behavior unless the task requires a behavior change.
- Keep paths and examples repo-relative or placeholder-based in docs (`<repository-root>`, `<database-url>`). Never commit machine-local absolute paths or secrets.

## Frontend (React/Vite)

- Use `frontend/src/lib/api.js` as the API boundary where established.
- Keep route changes synchronized with SPA hosting rewrites/fallback behavior.
- Match existing component/style patterns in `frontend/src/`.
- Run relevant frontend checks/tests for changed behavior.

## Backend (FastAPI)

- Keep API changes consistent across router (`backend/app/api/v1/*`), schemas, services, and models.
- Enforce authorization/business rules server-side.
- Handle money as integer paise where applicable.
- Be explicit about environment-dependent integrations (OAuth, payments, storage, email, webhooks).

## Documentation

- Prefer implementation/config as source of truth.
- Mark unverified operational details (live deployment, secrets, DNS, provider dashboards, migration execution) clearly.
- Update diagrams when architecture/flow changes; include a short “how to read this diagram” note.
- Validate relative links and scan for local-path leaks before finishing.
