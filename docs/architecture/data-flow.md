# Data Flow

Conceptual request and workflow flows based on current implementation patterns.

## Public/API request flow

```mermaid
sequenceDiagram
  participant B as Browser (React SPA)
  participant F as frontend/src/lib/api.js
  participant A as FastAPI /api/v1
  participant S as Services/Core
  participant D as Database/Integrations

  B->>F: user action / page load
  F->>A: HTTP request (cookies; CSRF for state changes)
  A->>S: validate, auth/session, business logic
  S->>D: query/persist or call integration
  D-->>S: result
  S-->>A: response model/data
  A-->>F: JSON/HTTP status
  F-->>B: render state
```

## How to read this diagram

- This is a generalized flow; individual routes may add authorization checks, idempotency, file handling, or webhook verification.
- Cookie/session and CSRF behavior is implementation- and origin-dependent; use configured origins in local/dev and deployment environments.

## Domain flows (conceptual)

```mermaid
flowchart TD
  V[Visitor] --> P[Public pages / public API]
  V --> L[Login/register/OAuth if enabled]
  L --> ME[Authenticated /me context]
  ME --> PAR[Participant actions]
  PAR --> REG[Register / team / verification / payments as applicable]
  REG --> DB[(Persisted state)]
  ADM[Admin user] --> ADMIN[Admin API/UI actions]
  ADMIN --> DB
  WH[External webhook, e.g. payments] --> WAPI[/api/v1/webhooks/*]
  WAPI --> DB
```

## Verification and safety notes

- Registration, payment confirmation, verification, and admin mutations must be treated as server-authoritative.
- Webhook endpoints require correct secrets/signature validation in configured environments (details are env-specific).
- Mock/local fallback behaviors (e.g., payments or SQLite/seed paths) should be verified before documenting as production behavior.
