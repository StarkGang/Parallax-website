# Parallax Backend

The backend is a FastAPI service that owns the whole convention: the public
catalogue, participant accounts, passes, event selections, teams, verification,
payments, tickets, check-in and the staff console. The React app in `frontend/`
is only a client; every price, cap, event, registration, ticket and audit entry
comes from this service.

- **Framework:** FastAPI 0.115 + Starlette, Pydantic v2 / pydantic-settings
- **Database:** SQLAlchemy 2 async, SQLite for local development, PostgreSQL
  (Supabase) in staging/production
- **Entry point:** `backend/app/main.py` → `create_app()`
- **API prefix:** `/api/v1`
- **Python:** 3.12+ (the checked-in venv is 3.13)
- **Money:** every amount is an integer number of paise. The API never returns
  floating-point rupees.

---

## 1. Layout

```
backend/
├── app/
│   ├── main.py                 app factory, middleware, health, lifespan
│   ├── seed.py                 idempotent demo edition, events and accounts
│   ├── core/                   config, errors, logging, CSRF, permissions,
│   │                           crypto, text sanitisation, rate limiting
│   ├── db/                     async engine/session, declarative Base
│   ├── models/                 SQLAlchemy ORM (user, edition, commerce)
│   ├── schemas/                Pydantic request/response contracts
│   ├── services/               business rules (passes, payments, tickets,
│   │                           verification, teams, events, editions, users…)
│   └── api/
│       ├── deps.py             DB session, AuthContext, permission guards
│       └── v1/
│           ├── public.py       unauthenticated catalogue and config
│           ├── auth.py         login, OAuth, CSRF, logout, MFA
│           ├── me.py           current user, profile, sessions
│           ├── participant.py  pass, selections, registrations, teams,
│           │                   verification, tickets, payments
│           ├── admin.py        staff console API
│           └── webhooks.py     Razorpay webhook
├── tests/                      pytest suite (16 tests)
├── var/                        SQLite database + local uploaded files
├── .env / .env.example         runtime configuration
└── pyproject.toml              dependencies and pytest/ruff config
```

The frontend never imports backend code. It talks to `/api/v1` through the Vite
proxy in development and same-origin requests in production.

---

## 2. Running it

```bash
cd backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Or from a fresh checkout:

```bash
python -m venv .venv
./.venv/Scripts/pip install -e ".[dev]"
cp .env.example .env          # then set SERVER_SECRET_KEY
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

- Interactive docs: `http://127.0.0.1:8000/api/docs` (non-production only)
- OpenAPI: `/api/openapi.json`
- Liveness: `GET /health/live` → `{"status":"ok"}`
- Readiness: `GET /health/ready` (runs `SELECT 1`, returns 503 when the DB is down)

On startup in development the lifespan hook runs
`Base.metadata.create_all` and then `seed_if_empty`, which creates the demo
edition, policy, categories, events, announcements and the two local accounts.
Seeding is idempotent and never blocks the API from booting.

### Tests

```bash
cd backend
./.venv/Scripts/python.exe -m pytest -q
```

The suite covers the critical business rules (policy, passes, selections,
tickets, permissions, sanitation). It uses the app factory and an isolated
database; it does not touch the development database.

---

## 3. Configuration

All configuration is environment-driven (`pydantic-settings`, `.env` is read
from `backend/`). Prices and event rules are **not** configuration: they live in
`edition_policies` and are changed through the staff console.

| Group | Variables | Notes |
| --- | --- | --- |
| Runtime | `APP_ENV`, `APP_DEBUG`, `APP_BASE_URL`, `FRONTEND_ORIGIN`, `ALLOWED_HOSTS`, `TRUSTED_PROXY_IPS` | `APP_ENV` is `development`, `staging`, `production` or `test`. |
| Database | `DATABASE_URL`, `SUPABASE_DB_URL`, `DATABASE_MIGRATION_URL`, `DB_POOL_SIZE`, `DB_STATEMENT_TIMEOUT_MS`, `DB_SSL`, `AUTO_CREATE_TABLES` | `postgres://` and `postgresql://` are normalised to `postgresql+asyncpg://`. |
| Sessions | `SESSION_COOKIE_NAME`, `SESSION_IDLE_TTL_*`, `SESSION_ABSOLUTE_TTL_*`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `SERVER_SECRET_KEY`, `SERVER_SECRET_KEY_PREVIOUS`, `TOTP_ENCRYPTION_KEY` | `SERVER_SECRET_KEY` must be at least 32 bytes and is mandatory outside development. |
| Auth | `MFA_ENFORCED`, `ALLOW_DIRECT_LOGIN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `DEV_AUTH_ENABLED`, `DEV_ADMIN_EMAIL`, `DEV_PARTICIPANT_EMAIL` | Google OAuth is optional; dev sign-in is development-only. |
| Payments | `PAYMENTS_ENABLED`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Enabling payments requires all three Razorpay values, and test/live keys are validated per environment. |
| Storage | `STORAGE_BACKEND` (`auto`/`supabase`/`s3`/`local`), `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`, `S3_*`, `SIGNED_URL_TTL_SECONDS` | `auto` prefers Supabase, then S3, then local disk. |
| Email | `EMAIL_ENABLED`, `EMAIL_PROVIDER_API_KEY`, `EMAIL_FROM` | Email is optional; verification codes are stored hashed regardless. |
| Limits | `MAX_REQUEST_BODY_BYTES`, `MAX_UPLOAD_BYTES_DOCUMENT`, `MAX_UPLOAD_BYTES_ICON_SVG`, `MAX_UPLOAD_BYTES_ICON_PNG` | 1 MiB bodies, 3 MiB documents, 64 KiB SVG icons, 256 KiB PNG icons by default. |
| Ops | `BOOTSTRAP_OWNER_EMAIL`, `SENTRY_DSN`, `SEED_DEMO_DATA` | |

### Production guards

`Settings._validate()` refuses to start when:

- `SERVER_SECRET_KEY` is missing, shorter than 32 bytes, or a placeholder
- `APP_DEBUG` is true, cookies are not secure, or `FRONTEND_ORIGIN` is not HTTPS
- `ALLOWED_HOSTS` is empty or `*`
- `PAYMENTS_ENABLED` is on without Razorpay credentials, or a test key is used
  in production / a live key in staging
- the runtime and migration database URLs use the same role in production

The session cookie is named `__Host-px_session` outside development (Secure,
`Path=/`, no `Domain`). OAuth state uses `__Host-px_oauth`.

---

## 4. Request pipeline

Middleware is applied in `create_app()`:

1. **CORS** — only `FRONTEND_ORIGIN`, credentials allowed, the custom headers
   `X-CSRF-Token`, `Idempotency-Key` and `X-Request-ID` are accepted.
2. **TrustedHost** — the `ALLOWED_HOSTS` allow-list (when not `*`).
3. **Body limit** — rejects oversized `Content-Length` with `413 PAYLOAD_TOO_LARGE`.
4. **Origin check** — every unsafe method must carry an `Origin` equal to
   `FRONTEND_ORIGIN`; `/api/v1/webhooks/*` is exempt. A mismatch is
   `403 ORIGIN_REJECTED`.
5. **Request context** — attaches/propagates `X-Request-ID`, sets security
   headers (`nosniff`, `Referrer-Policy`, `Permissions-Policy`,
   `frame-ancestors 'none'`, a locked-down API CSP), `Cache-Control: no-store`
   for non-public API responses, and HSTS in production.

Errors use one envelope:

```json
{ "error": { "code": "POLICY_CAP_EXCEEDED", "message": "…", "details": {}, "requestId": "…" } }
```

Successful reads use `{ "data": … }`; lists either include `meta`
(`{page, pageSize, total}`) for the public catalogue or top-level
`page`/`pageSize`/`total` in the staff API.

---

## 5. Authentication and sessions

### Local / development

- `POST /api/v1/auth/login` with
  `{"email":"participant@parallax.local","role":"participant"}` or
  `{"email":"owner@parallax.local","role":"admin"}` creates or reuses the
  development account, opens a server-side session and sets the session cookie.
- `GET /api/v1/auth/dev/login?role=admin|participant&next=/portal` does the same
  and redirects to the SPA, which is what OAuth-style links need.
- Available only when `APP_ENV` is development/test, `DEV_AUTH_ENABLED=true` and
  `ALLOW_DIRECT_LOGIN=true`.

### Google OAuth

`GET /auth/google/login?next=…` stores a signed OAuth state cookie and redirects
to Google. `GET /auth/google/callback` validates state, exchanges the code,
requires a verified email, links/creates the user and redirects to
`FRONTEND_ORIGIN` + `next` (`/portal` by default).

### Sessions

Sessions are rows in the database, not JWTs. The cookie carries an opaque
session id; the server checks idle and absolute expiry on every request. Staff
sessions are short-lived (30 min idle / 8 h absolute by default), participant
sessions long-lived (7 days / 30 days). `POST /auth/logout` ends the current
session; `POST /auth/logout-all` ends all sessions for the user.
`GET /me/sessions` lists the active sessions with a `current` flag.

### CSRF

1. `Origin` must match `FRONTEND_ORIGIN` for every mutation.
2. `GET /api/v1/auth/csrf` returns `{csrfToken}` tied to the session.
3. Mutations must send it as `X-CSRF-Token`. A missing/expired token is
   `403 CSRF_INVALID`; the frontend refreshes once and retries.

### MFA

TOTP endpoints exist (`/auth/mfa/setup`, `/verify`, `/challenge`, `/step-up`)
and sensitive actions are listed in `STEP_UP_ACTIONS`. `MFA_ENFORCED=false`
keeps the flow optional for this convention.

---

## 6. Roles and permissions

Roles are database memberships, optionally scoped to an edition:
`super_admin`, `edition_admin`, `finance_admin`, `event_coordinator`,
`checkin_staff`, `participant`. (`eligibility_verifier` was retired with the old
verification feature; the migration converts any leftover row.)

`app/core/permissions.py` owns the permission catalogue and the single
role → permissions map. Routes declare `require_permission("…")`; there is no
implicit allow. `super_admin` passes every check. `edition_admin` holds the full
catalogue except refund approval. Staff roles can be granted per edition with
`POST /admin/memberships` or invited with `POST /admin/staff-invites`.

An account holds **one staff role per edition**. Granting a second role replaces
the first (the response names the replaced role), claiming a new invite retires
the old role, and permission checks read that single role, so a leftover
duplicate row can never widen what someone can do. `super_admin` is never revoked
by a grant.

`GET /api/v1/editions/{edition_id}/admin/my-permissions` returns the caller's
role and effective permissions, which the console uses to shape the UI.

---

## 7. Data model

### Identity (`models/user.py`)

| Table | Purpose |
| --- | --- |
| `users` | Google subject, normalised email, verified flag, name, picture, status, phone, MFA secret/recovery codes, last login. |
| `participant_profiles` | College, university, course, branch, year, student identifier (hash + last four), institution email. |
| `edition_memberships` | `(user, edition, role, status)` — staff and participant roles. |
| `sessions` | Opaque session id, auth level, idle/absolute expiry, IP prefix, user-agent hash. |
| `staff_invites` | Token hash, role, edition, expiry, accepted state. |

### Convention (`models/edition.py`)

| Table | Purpose |
| --- | --- |
| `convention_editions` | Slug, name, hero copy, organiser/host/venue/city, dates, registration window, status, contact email, allowed domains, branding. |
| `edition_policies` | Immutable, versioned pricing rules; exactly one `is_current` per edition. |
| `event_categories` | Slug, name, accent, display order, icon. |
| `events` | Catalogue record: slug, copy (Markdown), format, team sizes, base value, add-on fee, charge basis, capacity, schedule, room, registration window, approval flag, icon, accent, featured flag, status, sort order. |
| `event_price_history` | Append-only record of price changes with actor and reason. |
| `event_coordinators` | Staff assigned to an event. |
| `announcements` | Markdown + rendered HTML, audience (`public`/`participants`/`staff`), draft/published, publish time. |
| `icon_assets` | Uploaded SVG/PNG icons, storage key, MIME, size, recolorable flag, status. |

### Commerce (`models/commerce.py`)

| Table | Purpose |
| --- | --- |
| `convention_passes` | One per participant per edition: price snapshot, policy version, status, paid time, lunch days. |
| `included_event_selections` | The participant's included-choice snapshot: selected flag, base value, lock state. |
| `registrations` | `included` or `addon`; confirmed/reserved/pending/cancelled; fee, team, registration number. |
| `teams` / `team_members` | Team entry for team events, leader flag, invite-code hash. |
| `payment_orders` | Purpose (pass/registration), amount, gateway order id, status, mock flag. |
| `refunds` | Requested/approved/processed amount, reason code and note, actors. |
| `tickets` | Deterministic HMAC token, kind, registration link, status, issue time. |
| `attendance_records` | Check-in result per participant/event/day, actor, device label. |
| `audit_logs` | Actor, role, action, resource, before/after JSON, request id. |
| `idempotency_keys` | Stored response snapshots for safe retries. |

All money columns are `Integer` paise. Prices are snapshotted onto passes,
registrations and orders so later catalogue edits cannot rewrite history.

---

## 8. Pricing policy engine

`edition_policies` is versioned and immutable. Creating a policy inserts a new
version and flips `is_current` in one transaction, so an in-flight purchase
always references a complete rule set.

Fields that drive behaviour:

- `pass_price_paise` — fallback pass price. Attendees pay their **registration
  tier** (`registration_categories.fee_paise`); this value only covers manual
  passes and desk seeding, so never quote it as "the pass price".
- `lunch_included_days` — e.g. `["day1","day2"]`
- `included_event_count` + `included_selection_mode` (`exact` or `up_to`)
- `included_value_cap_paise` + `cap_inclusive` — cap on the sum of **base
  values**, not on the pass price
- `selection_change_deadline` — after this the selection locks
- `addon_requires_pass`, `team_members_require_pass`
- `team_fee_basis_default` — `per_participant` or `per_team`
- `hold_minutes` — unpaid add-on reservation lifetime
- `refund_rules`, `gst_note`

`POST /admin/policies/check` runs the same validator without writing and returns
`{ok, blocking, warnings, impact}`. `POST /admin/policies` publishes a new
version (optionally overriding a price lock).

---

## 9. Pass, selection and registration flows

1. **Pass purchase** — the college registration *is* the pass purchase. The
   chosen **registration tier** (`registration_categories.fee_paise`) is
   snapshotted onto the registration and its `PaymentOrder`; there is no
   separate pass order anymore.
2. **Payment** — with payments disabled, `POST
   /editions/{id}/payments/{order_id}/mock` marks the order paid. With Razorpay
   enabled, the browser completes checkout and the webhook (or the status poll)
   marks it paid.
3. **Activation** — on payment the pass becomes `active`, included
   registrations are synchronised, and a pass ticket is issued.
4. **Included selections** — `PUT /editions/{id}/pass/selections` validates
   count, cap, eligibility, duplicate events, deadline and lock state, then
   creates/cancels included registrations and rewrites the selection snapshot.
5. **Add-ons** — `POST /editions/{id}/registrations` validates the pass rule,
   capacity, team rules and duplicates, creates `reserved` registrations and one
   order for the add-on total. Unpaid reservations expire after `hold_minutes`.
6. **Cancellation** — `DELETE /editions/{id}/registrations/{registration_id}`
   cancels an owned registration and frees capacity.

The service layer (`services/passes.py`) is the only place these rules live; the
routes do not re-implement them. That is what keeps the public page, portal and
staff console consistent.

---

## 10. Tickets and check-in

`services/tickets.py` issues deterministic tokens:

```
PX-<32 hex chars>-<10 hex chars>
```

The first part identifies the ticket, the suffix is an HMAC over the ticket id
with the server secret. No plaintext token is stored, so a database leak does not
leak usable entry credentials.

- `GET /editions/{id}/tickets` — the caller's tickets
- `GET /editions/{id}/tickets/{ticket_id}/qr` — PNG QR generated with `segno`
- `POST /admin/checkin` — staff scan or type a token; the service resolves it,
  validates status/pass/event/day, detects duplicates for the same day, records
  `attendance_records`, writes an audit entry and returns
  `{result, participantName, checkedInAt, …}` (`admitted`, `duplicate`, `denied`).

`GET /admin/recent-checkins` and `GET /admin/attendance?day=YYYY-MM-DD` power the
door desk and attendance views.

### Custom credentials (people who are not registrations)

Staff, faculty, sponsors, press and guests have no user account or registration,
so their badges are stored in `custom_credentials` (`models/credential.py`,
`services/credentials.py`). Each row is a normal printed ID that the same desk
accepts for identification.

A card built from a registration (the studio's attendee picker) is linked to it
and carries **no token of its own**: its QR is the attendee's own entry payload,
the string their portal pass prints (`entryQr` on the registration and on the
saved card; `entry_payload` in `services/tickets.py`). Scanning a linked card is
therefore scanning the attendee's pass — attendance, duplicates, suspensions,
unpaid upgrades and event rules all come from that one path, and a card cannot
grant anything the registration does not have. A registration with nothing
issued yet (unpaid, no number) has no entry payload, so its card prints no QR.
Unlinked cards keep their own `PXC` token and never admit anyone by themselves.

- Printed ID: `PXC-XXXXXX` (6 characters, alphabet excludes `I O 0 1` so it can
  be read off a card and typed). Unique per edition; a duplicate returns
  `409 CREDENTIAL_CODE_TAKEN`, as does an ID that matches a participant's
  registration number.
- QR payload: `PXC-<credential uuid hex>-<16 hex signature>`, signed with the
  same HMAC as tickets, so an edited payload fails resolution instead of
  admitting someone.
- `POST /admin/checkin` tries tickets first and falls back to credentials, so one
  scan box and one camera loop serve both kinds of card. A revoked card returns
  `409 CREDENTIAL_REVOKED`.
- `GET /public/c/{value}` resolves either kind and renders a verification page
  (valid/revoked) for phone cameras, or JSON for API clients.

Routes: `GET|POST /admin/custom-credentials`,
`PATCH /admin/custom-credentials/{id}` and
`POST /admin/custom-credentials/{id}/revoke`, all behind `credential.write`
(super admin and edition admin). Revoking keeps the row as the audit trail and
blocks printing; editing a revoked card is refused.
`POST /admin/custom-credentials/photo` stores a card photo and returns its URL.
The studio uploads there instead of embedding a browser `blob:` URL, which died
with the tab and left a reprinted card faceless.

Guards the API enforces itself, not just the studio buttons: a blank or
whitespace-only `name`/`role` is rejected (`422`), fields are trimmed before they
are stored, lengths match the columns, and `design` is capped at 4 KB of
serialisable JSON because it is presentation only.

The desk dispatches on the token shape (`PX` for tickets, `PXC` for cards), so
scanning a studio card costs one query instead of a failed ticket lookup first.
A hand-typed ID has no required prefix, so the ticket-then-credential fallback
stays for that case.

### Gender, meal and accommodation

The pass form asks for gender, veg/non-veg and whether the attendee needs
accommodation, alongside college, branch and year. They are real columns on
`college_registrations` and on `custom_credentials`, shown at the desk when a QR
is scanned (`gender`, `foodPreference`, `needsAccommodation` in the check-in
response).

Storage is one small integer per answer: gender `0` = male, `1` = female; meal
`0` = veg, `1` = non-veg. Only male and female are offered. The API and the UI
keep speaking names, encoded and decoded in one place (`core/attendee.py`), so no
screen invents a third spelling.

- Gender and meal are required by `POST /registration/submit`, the endpoint that
  creates the payment order. A direct API client cannot buy a pass while
  skipping them; the answer comes back as `422 MANDATORY_DETAILS_MISSING` with
  `missingFields: ["Gender", "Meal Preference"]`. They stay optional on the
  profile endpoint, which doubles as the draft save during document upload.
- Food and accommodation stay editable after payment: they are logistics the
  kitchen and hostel need to change, not verified identity. An edit may correct
  them but never blank them out once the pass is paid, because the counts have
  already been cooked and allocated. `PUT /registration/profile` is a full
  replace, so an omitted or null answer is a request to remove it: a paid row
  answers `409 LOGISTICS_LOCKED` instead of silently keeping the old value.
- A studio card prints them on the back face ("Female · Veg · Hostel stay") and
  hides the line when nothing is on record.

---

## 11. Verification

There is no separate eligibility-verification service. Student verification
happens inside the college registration:

| Document | Purpose |
| --- | --- |
| `photo` | Passport-size photo printed on the pass and the studio ID card. |
| `college_id` | Proof the attendee studies at the college they claimed. |
| `iste_card` | ISTE membership proof, only where the chosen tier asks for it. |

The participant uploads them at
`POST /editions/{id}/registration/documents/{doc_type}`. Staff read the queue at
`GET /admin/registration`, open a document through
`GET /admin/registration/{registration_id}/documents/{document_id}/content` and
decide at `POST /admin/registration/{registration_id}/decision` (approve, reject
or ask for specific documents again). Rejections are resubmittable, and every
decision is audited.

### 24-hour registration compliance window

When the college-registration desk asks for corrected documents or approves a
category change that needs a top-up payment, the registration stores a 24-hour
window in `college_registrations.compliance_kind` / `compliance_deadline_at`.
The participant dashboard shows a countdown warning and the same request is
emailed immediately.

An expired window is enforced lazily wherever the data is read, not only when
the attendee acts: opening the public events catalogue or event detail, the
participant event-selection page, the participant's registrations/tickets/team
pages, and the admin dashboard, event, roster and registration screens all run
a throttled sweep before returning seats or rosters. `lazy_sweep_due` keeps the
common case to one indexed query per edition every few seconds, and only
commits when a row was actually enforced. It also runs on the next profile save
or checkout in that edition, by `POST /admin/maintenance/enforce-compliance`,
and by the optional background sweep. Enforcement releases every event seat the
attendee holds, refunds paid event orders (or parks them for finance when the
gateway fails), and removes them from team rosters. Team leadership moves to the
next member instead of disbanding an innocent team, so a teammate opening the
team page sees the change immediately. Team create/join also sweep first so a
stale roster cannot occupy the last entry. `compliance_enforced_at` is claimed
with a conditional `UPDATE` inside a savepoint, making enforcement exactly-once
even when the read sweep and cron run at the same time; after answering the
request the attendee must select events and join a team again. A rejected pass
uses the same release path and additionally refunds the pass itself.

---

## 12. Payments and refunds

Payments are **off by default**. `payments_enabled=false` means:

- orders are created with no gateway order id and `mock: true`
- the portal shows a clearly labelled sandbox payment button
- `POST …/payments/{order_id}/mock` activates the order without money moving

With `PAYMENTS_ENABLED=true`:

- Razorpay orders are created server-side; the key id is the only value sent to
  the browser
- the browser completes checkout on Razorpay's domain
- `POST /api/v1/webhooks/razorpay` verifies `X-Razorpay-Signature` with the
  webhook secret and processes the event idempotently
- `GET /editions/{id}/payments/{order_id}` lets the client poll status

Refunds are staff actions: `POST /admin/refunds` records a request (amount,
reason code/note); approval and processing are permission-gated
(`finance.write`, `refund.approve`) and audited. Refunds never mutate the
original order amount.

---

## 13. Storage

`STORAGE_BACKEND=auto` selects Supabase Storage, then S3, then local disk
(`backend/var/storage`). Private documents and icons are served through
short-lived signed URLs (`SIGNED_URL_TTL_SECONDS`, 120 s default) or a guarded
API route — never as public object URLs.

Uploads are limited by content length and by MIME/size: 3 MiB for verification
documents, 64 KiB for SVG icons, 256 KiB for PNG icons. SVG uploads are parsed
with `defusedxml` and sanitised; rendered Markdown is sanitised with `nh3`
allowing only a small tag/attribute set (no `rel`, no scripts, no event
handlers). The database stores only storage keys, not bytes.

---

## 14. API surface

All paths are under `/api/v1` unless noted.

### Public (no session)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/public/config` | Branding, feature flags, payment/auth mode |
| GET | `/public/editions/current` | Current edition + current policy |
| GET | `/public/editions/{slug}` | Edition by slug |
| GET | `/public/editions/{slug}/categories` | Categories |
| GET | `/public/editions/{slug}/events` | Catalogue (`q`, `category`, `format`, `featured`, `page`, `pageSize`) |
| GET | `/public/editions/{slug}/events/{event_slug}` | Event detail with rendered Markdown |
| GET | `/public/editions/{slug}/schedule` | Sessions grouped by day |
| GET | `/public/editions/{slug}/announcements` | Published announcements |
| GET | `/public/c/{value}` | Ticket or custom-credential verification (HTML for cameras, JSON for clients) |
| GET | `/public/editions/{slug}/policy` | Current pricing policy |
| GET | `/public/icons/{icon_id}` | Public icon bytes |
| GET | `/public/documents/{key}` | Guarded document route |

### Auth and account

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/csrf` | Session CSRF token |
| POST | `/auth/login` | Direct/dev login |
| GET | `/auth/dev/login` | Development redirect login |
| GET | `/auth/google/login`  /  `/auth/google/callback` | OAuth |
| POST | `/auth/logout`  /  `/auth/logout-all` | End session(s) |
| GET | `/me` | Identity, roles, profile/verification flags |
| GET/PATCH | `/me/profile` | Read/update profile |
| GET | `/me/sessions` | Active sessions |
| POST | `/auth/mfa/*` | TOTP setup, verify, challenge, step-up |

### Participant (`/editions/{edition_id}/…`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/pass` | Pass + selection state |
| PUT | `/pass/selections` | Save included selections |
| GET/POST | `/registrations` | List / register add-ons |
| DELETE | `/registrations/{id}` | Cancel a registration |
| GET/POST | `/teams` | List / create teams |
| POST | `/teams/join` | Join with invite code |
| DELETE | `/teams/{id}` | Leave a team |
| POST | `/teams/{id}/rotate-invite` | Rotate the invite code (leader) |
| GET | `/tickets`  /  `/tickets/{id}/qr` | Entry tickets and QR |
| GET | `/payments/{order_id}` | Payment status |
| POST | `/payments/{order_id}/mock` | Sandbox payment (payments disabled) |

### Staff (`/editions/{edition_id}/admin/…`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/overview` | Dashboard metrics and recent activity |
| GET | `/my-permissions` | Effective role and permissions |
| GET/PATCH | `/settings` | Edition settings |
| GET/POST | `/policies`  /  POST `/policies/check` | Version and validate policy |
| GET/POST | `/categories`  /  PATCH `/categories/{id}` | Category management |
| GET/POST | `/events`  /  GET/PATCH `/events/{id}` | Catalogue management |
| GET/POST/DELETE | `/icons` | Icon library |
| GET | `/users`  /  PATCH `/users/{id}/status`  /  POST `/users/{id}/reset-mfa` | User administration |
| GET/POST | `/memberships`  /  POST `/staff-invites` | Staff access |
| GET | `/registrations` | Registration records |
| GET | `/payments`  /  GET/POST `/refunds` | Finance ledger |
| GET | `/registration`  /  GET `/registration/{id}`  /  POST `/registration/{id}/decision` | College registration desk and document review |
| GET/POST/PATCH/DELETE | `/announcements` | Bulletin |
| GET | `/audit` | Audit log |
| POST | `/checkin`  /  GET `/recent-checkins`  /  GET `/attendance` | Door desk |
| GET/POST/PATCH | `/custom-credentials`  /  POST `/custom-credentials/{id}/revoke`  /  POST `/custom-credentials/photo` | Studio-issued ID cards |

### Webhooks

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/webhooks/razorpay` | Signed payment events (exempt from Origin check) |

---

## 15. Audit, idempotency and observability

- **Audit** — every staff write and every check-in records actor, role, action,
  resource, before/after and request id in `audit_logs`.
- **Idempotency** — mutation endpoints accept `Idempotency-Key`; the response is
  snapshotted so a retried request returns the original result instead of
  double-charging or double-registering.
- **Logging** — `structlog` with request id context; JSON logs outside
  development, coloured console logs inside. Stdout is forced to UTF-8 so
  Windows consoles do not crash on non-ASCII names.
- **Rate limiting** — login, verification and other sensitive routes are
  throttled per IP/session.
- **Errors** — typed domain errors map to stable codes and HTTP statuses;
  unexpected exceptions return a generic 500 with a request id and are logged.

---

## 16. Frontend contract

The SPA (`frontend/`) uses `BrowserRouter` and calls this API through
`src/lib/api.js`:

- `fetch` with `credentials: 'include'`
- CSRF token from `/auth/csrf`, sent as `X-CSRF-Token`, refreshed once on
  `CSRF_INVALID`
- `Origin` is satisfied automatically because the browser sends it for
  same-origin/Vite-proxied requests
- in development Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`

Key pages map to endpoints as follows:

| Page | Endpoints |
| --- | --- |
| Home / About / Venue / FAQ / Contact | public edition, events, announcements, policy |
| Events / Event detail | public categories, events, event detail |
| Pass | public policy + live registration tiers |
| Portal overview / pass | `GET /pass`, payments, tickets |
| Select events | `PUT /pass/selections`, add-on `POST /registrations` |
| Registrations / Teams | participant endpoints |
| Tickets | `GET /tickets`, QR route |
| Staff console | the `/admin/*` group, including check-in and audit |

---

## 17. Operations

### Reset the local database

`create_all` cannot add columns to an existing SQLite file. After a schema
change, stop the API and remove the development database so it is recreated and
reseeded:

```bash
cd backend
rm -f var/parallax.db
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

For staging/production use a real migration (Alembic is a declared dependency)
against `DATABASE_MIGRATION_URL`; do not run `create_all` there. Back up before
migrating.

### Seeded development data

| Item | Value |
| --- | --- |
| Edition | `parallax-2027`, published, dates relative to seed time |
| Pass | ₹500 (`50000` paise) |
| Included | up to 3 events, base-value cap ₹450 (`45000`), cap inclusive |
| Lunch | day 1 and day 2 |
| Selection deadline | day 1, 10:00 |
| Hold window | 15 minutes |
| Staff account | `owner@parallax.local` (super admin) |
| Participant | `participant@parallax.local` (Aparna Menon) |
| Payments | disabled → `mock: true` sandbox path |

### Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `401 UNAUTHENTICATED` | No/expired session cookie. Sign in again. |
| `403 CSRF_INVALID` | Missing/stale `X-CSRF-Token`; fetch `/auth/csrf` and retry once. |
| `403 ORIGIN_REJECTED` | Request `Origin` is not exactly `FRONTEND_ORIGIN`. |
| `403 FORBIDDEN` | Role lacks the route permission; check `/admin/my-permissions`. |
| `409` on pass/selection | State changed (already paid, locked, capacity, duplicate). Re-read state. |
| `422` | Pydantic validation; inspect `error.details`. |
| `503` on `/health/ready` | Database unreachable. |
| Pass page shows setup error | API is not running or the edition is missing; start the backend. |
| `no such column` after pulling | Stale SQLite file; delete `var/parallax.db` and restart. |
| Check-in rejects a valid ticket | Wrong day, cancelled registration, already used, or a token from another environment. |

---

## 18. Security notes

- Deny-by-default route permissions; the test suite fails routes without a
  declared guard.
- Server-side sessions with rotation-friendly secrets (`SERVER_SECRET_KEY` and
  `_PREVIOUS`), `__Host-` cookies outside development.
- Origin check + session-bound CSRF token on every mutation.
- No secrets in the frontend: Razorpay key id only, never the secret.
- Signed, expiring URLs for private documents; no public buckets for PII.
- Upload size + MIME limits, XML hardening and `nh3` sanitisation for all
  rendered Markdown.
- Prices, caps and fees are database rows with history, never client input.
- Every privileged action is audited with actor and request id.
- PII is minimised: student identifiers are stored as a hash plus last four;
  sessions store only an IP prefix and a user-agent hash.
