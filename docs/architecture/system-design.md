# System Design

This document describes the main runtime modules and responsibilities based on the current repository implementation.

## Runtime modules

```mermaid
flowchart TB
  subgraph Frontend[frontend/src]
    Main[main.jsx\nbootstrap + BrowserRouter]
    App[App.jsx\nroute composition]
    Pages[pages/components\npublic + portals]
    Api[lib/api.js\nHTTP client]
  end

  subgraph Backend[backend/app]
    Entry[main.py\nFastAPI app factory]
    V1[api/v1/* routers]
    Core[core/* config/security/session/csrf]
    Services[services/* domain logic]
    Schemas[schemas/* request/response models]
    Models[models/* SQLAlchemy entities]
    Integrations[integrations/* storage/email etc.]
  end

  Main --> App --> Pages --> Api
  Api -->|HTTP /api/v1| Entry --> V1
  V1 --> Core
  V1 --> Services --> Models
  V1 --> Schemas
  Services --> Integrations
```

## How to read this diagram

- It is a module-level map, not a complete call graph.
- Router handlers in `api/v1` coordinate validation, auth/context, services, and persistence.
- Exact endpoint behavior should be verified in `backend/app/api/v1/*.py` and the frontend calls in `frontend/src/lib/api.js`.

## Key responsibilities

| Area | Responsibility | Primary locations |
|---|---|---|
| SPA bootstrap/routing | Mount app, configure router, define route tree | `frontend/src/main.jsx`, `frontend/src/App.jsx` |
| Frontend API boundary | Send requests, include credentials/CSRF as implemented | `frontend/src/lib/api.js` |
| API composition | Create app, middleware/config wiring, mount `/api/v1` | `backend/app/main.py` |
| Route handling | Public/auth/me/participant/admin/webhooks endpoints | `backend/app/api/v1/*.py` |
| Domain/data | Domain entities and persistence | `backend/app/models/*.py`, DB/session modules |
| Integrations | Optional external capabilities (payments/auth/storage/email) | integration modules + config/env |

## Deployment design notes

- SPA path routing requires host rewrite/fallback to `index.html` (see `vercel.json`/Render notes).
- Serverless vs long-running deployment can affect database/session/storage behavior; treat those details as environment-specific unless verified.
