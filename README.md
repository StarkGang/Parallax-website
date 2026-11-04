# PARALLAX Convention Web App

PARALLAX is a convention information and operations web application for an ISTE state student convention hosted by NSS College of Engineering, Palakkad. The repository contains a React single page frontend, a FastAPI backend, a relational data model, local development seed data, supplied brand artwork, and product and deployment documentation.

The browser app is a client of the backend. The backend is the source of truth for editions, policy, events, participant accounts, passes, registrations, tickets, staff permissions, and operational records. It validates important actions on the server and persists them in the database.

## GitHub Pages

The frontend deploys from `.github/workflows/deploy.yml` when changes are pushed to `main` (or from **Actions → Deploy to GitHub Pages → Run workflow**). In the repository settings, set **Pages → Build and deployment → Source** to **GitHub Actions**. The workflow builds `frontend` and deploys it; client routes use URL hashes so page refreshes work on GitHub Pages project sites.

GitHub Pages hosts static files only. To load convention data or use sign-in, registration, payments, and staff tools, deploy the FastAPI backend separately and add a repository Actions variable named `VITE_API_BASE` with the backend API base URL (for example, `https://api.example.com/api/v1`). Configure that backend's CORS and allowed frontend origin for the GitHub Pages URL. Without a backend, the static site shell loads but API-driven features are unavailable. The workflow derives the project-site asset path from the repository name; set the `VITE_BASE_PATH` Actions variable only if you need to override it (for example, `/` for a custom domain).

> Local development uses seeded demo records and a mock payment path. Do not enter real participant, identity document, or payment information into an unreviewed development environment.

## What the web app does

### Public convention site

The public pages present convention information and read the current edition from the API:

- **Home (`/`)** introduces the edition, highlights selected events, and links visitors to convention information and sign-in.
- **About (`/about`)** explains the convention and its organizers and host.
- **Events (`/events`)** displays the event catalogue. The API supports search, category, individual/team format, featured-only filtering, and pagination. Event cards show category, summary, individual or team format, included value, separate add-on price, availability, and registration state.
- **Event detail (`/events/:eventSlug`)** shows an event's description, rules, schedule, venue, team size or individual format, fees, and registration information.
- **Pass (`/pass`)** explains the convention pass, included event allowance, cap, add-on charges, and policy currently configured for the edition.
- **Schedule (`/schedule`)** displays schedule days and items returned by the API.
- **Venue (`/venue`)**, **FAQ (`/faq`)**, and **Contact (`/contact`)** provide visitor planning information.
- The global header links to the public pages and adapts to a mobile menu. A footer and not-found page are shared around public-facing routes.

### Participant portal

After sign-in, `/portal` provides an overview and links to participant tools. The portal pages are:

- **Pass (`/portal/pass`)** shows pass status and price, starts a pass order, and supports the configured payment flow.
- **Select events (`/portal/select-events`)** lets a participant choose included events within the edition's selection count and base-value cap. The server validates the selection and policy; the browser is not authoritative for prices or eligibility.
- **Registrations (`/portal/registrations`)** lists a participant's registrations and exposes cancellation when allowed by policy and registration state.
- **Tickets (`/portal/tickets`)** displays issued tickets and their QR codes for entry.
- **Teams (`/portal/teams`)** supports creating or joining a team, managing an invite code, and leaving a team, subject to event size and membership rules.
- **Verification (`/portal/verification`)** displays student verification status and supports the configured email or document submission workflow.
- **Profile (`/portal/profile`)** displays and edits the participant's profile details supported by the API.

The portal also shows pass, profile, and verification status, and provides sign-out. Staff accounts can switch between participant and staff views.

### Staff console

Staff-only routes under `/manage` provide operational views. Access is guarded in the frontend and authorized again by backend roles and permissions. The console includes:

- **Overview:** edition and operational summary.
- **Events:** create and update events and categories, manage their descriptions, format, schedule, capacity, status, fees, and event icons.
- **Policy:** view and update edition policy, inspect policy validation, and control registration settings.
- **Registrations:** search and review participant registrations.
- **Users:** review users, account status, memberships, and staff access actions.
- **Verifications:** inspect student verification submissions and make decisions.
- **Payments:** review payment orders and refunds; the backend supports refunds when payment integration and permissions permit them.
- **Check-in:** look up or scan ticket information and record attendee entry.
- **Announcements:** publish, edit, and remove public convention announcements.
- **Attendance:** review check-in and attendance data.
- **Audit log:** inspect recorded administrative and operational changes.
- **Settings:** review or edit edition-level settings permitted to the signed-in staff role.

Staff roles are permission-scoped (for example super administrator, edition administrator, finance administrator, verifier, event coordinator, and check-in staff). The set of available actions depends on the role granted by the backend.

### Backend capabilities

The backend in `backend/app/` provides:

- Public edition configuration, current edition, policy, categories, searchable event catalogue, event details, schedule, announcements, public icons, and signed document access.
- Development login and optional Google OAuth, server-side sessions, CSRF protection, optional multi-factor authentication, session listing and revocation, and role-based access checks.
- Participant profiles, pass orders, included-event selections, add-on registrations, teams, student verification, payment status, tickets, and QR generation.
- Administrative event and policy editing, category and icon management, user and membership administration, verification decisions, payment/refund review, announcements, check-in, attendance, audit records, and settings.
- SQLite for local development, with PostgreSQL/Supabase support configured for staging or production. Startup creates database tables and seeds demo data in development when enabled.
- Optional integrations for Razorpay payments, Google sign-in, Supabase or S3 storage, email, and error monitoring. These require explicit environment configuration; empty example values do not enable them.

## Repository guide

```text
.
├── frontend/                 React + Vite application
│   ├── src/
│   │   ├── main.jsx           React entry point and provider composition
│   │   ├── App.jsx            shared shell, route table, access gates, not-found page
│   │   ├── components/ui.jsx  reusable buttons, fields, panels and async states
│   │   ├── pages/             public, portal, staff and login screens
│   │   ├── style.css          base styles, visual tokens, breakpoints
│   │   └── theme.css          additional treatments and page styles
│   ├── images/                frontend source copies of supplied assets
│   ├── index.html             browser document shell and metadata
│   ├── package.json           frontend commands and dependencies
│   └── vite.config.js         dev proxy, build base, selected asset copying
├── backend/
│   ├── app/api/v1/            public, auth, profile, participant, admin, webhook APIs
│   ├── app/services/          business rules for events, passes, teams, payments, etc.
│   ├── app/models/            SQLAlchemy database models
│   ├── app/schemas/           Pydantic API input/output contracts
│   ├── app/core/              settings, security, permissions, errors and middleware
│   ├── app/integrations/      storage and email adapters
│   ├── app/seed.py            idempotent local demo edition and accounts
│   └── tests/                 backend test suite
├── docs/                     product, business rules, architecture and deployment notes
├── images/                   original supplied artwork and logos
├── BACKEND.md                backend setup and API/operations guide
├── DEPLOY.md                 deployment notes
├── CONTRIBUTING.md           contribution conventions
├── Dockerfile, render.yaml   deployment configuration
└── vercel.json               root hosting configuration
```

## Run the application locally

Run backend and frontend in separate terminals from the repository root. Python 3.12 is recommended. Node.js and npm are needed for the frontend.

### 1. Start the backend

In terminal 1, create the environment and install the backend package. These instructions use PowerShell on Windows:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On macOS/Linux, use the platform's Python 3.12 executable and venv path:

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For local development, the backend generates a development secret if `SERVER_SECRET_KEY` is unset, uses SQLite at `backend/var/parallax.db` by default, creates tables, and seeds demo data on first startup. No `.env` file is required for the default local setup. To customize the environment, copy `backend/.env.example` to `backend/.env` and review every value before use. Keep secrets out of version control.

Wait for the `Application startup complete` message. Useful URLs:

- API health: <http://127.0.0.1:8000/health/live>
- API readiness and database check: <http://127.0.0.1:8000/health/ready>
- Interactive API docs in development: <http://127.0.0.1:8000/api/docs>

The default development demo account emails are `participant@parallax.local` and `owner@parallax.local` (staff). They do not use passwords in the local development login flow. Development login is disabled outside development/test and can be controlled by `DEV_AUTH_ENABLED` and `ALLOW_DIRECT_LOGIN`. Google OAuth requires valid client credentials.

### 2. Start the frontend

In terminal 2, from the repository root:

```sh
cd frontend
npm install
npm run dev
```

Vite normally serves the frontend at <http://localhost:5173>. Its development proxy forwards `/api` and `/health` to `http://127.0.0.1:8000`; set `VITE_API_PROXY` if the backend is on another address. The frontend and backend origin settings must agree for development session and CSRF checks. The browser app expects the backend's current edition to load before it renders the routes.

### Current frontend checkout limitation

The React source imports modules from `frontend/src/lib/` including `auth.jsx`, `site.jsx`, `theme.jsx`, `api.js`, and `format.js`, but `frontend/src/lib/` is missing from this checkout. As a result, Vite reports errors such as `Failed to resolve import "./lib/auth.jsx" from "src/main.jsx"`, and the frontend cannot compile until those source modules are restored. The backend can be run and its API inspected independently. The frontend directory's available scripts are:

```sh
npm run dev          # Vite development server
npm run build        # production files in frontend/dist/
npm run preview      # preview the last production build
npm run format       # format frontend files using Prettier
npm run format:check # check formatting
npm test             # Node test runner; no frontend test files are included
```

## How requests and pages work

1. `frontend/index.html` provides the root HTML document and loads `src/main.jsx`.
2. `main.jsx` mounts React, React Router's `BrowserRouter`, and providers for theme, edition/site data, and authentication. It imports both global stylesheets.
3. `App.jsx` chooses the page for the current route, loads shared navigation and footer, and applies participant/staff route gates.
4. `pages/Public.jsx`, `Portal.jsx`, `Admin.jsx`, and `Login.jsx` render the visitor, participant, staff, and login interfaces. `components/ui.jsx` supplies shared interface elements.
5. Page components call shared functions from the absent `src/lib/` modules. The names/usages indicate API clients, auth/site/theme providers, and date/currency formatting helpers; their implementation is unavailable in this checkout.
6. The backend mounts its routers below `/api/v1`. Public reads are grouped under `/public`; authentication, current-user, participant, admin, and webhook endpoints are separated by responsibility.
7. In local development Vite proxies API calls to FastAPI. In production the frontend and API are intended to be served from the configured deployment origin.

`App.jsx` also mounts a shared theme customizer across routes. Its implementation is imported from the missing `src/lib/theme.jsx`, so its exact controls and behavior cannot be confirmed from this checkout.

The route table includes public routes `/`, `/about`, `/events`, `/events/:eventSlug`, `/pass`, `/schedule`, `/venue`, `/faq`, `/contact`; `/login`; participant routes `/portal`, `/portal/pass`, `/portal/select-events`, `/portal/registrations`, `/portal/tickets`, `/portal/teams`, `/portal/verification`, `/portal/profile`; and staff routes `/manage`, `/manage/events`, `/manage/policy`, `/manage/registrations`, `/manage/users`, `/manage/verifications`, `/manage/payments`, `/manage/check-in`, `/manage/announcements`, `/manage/attendance`, `/manage/audit`, `/manage/settings`.

## Editing the frontend

Make interface changes in `frontend/`:

| Change | Files to start with |
|---|---|
| Public page content or event catalogue presentation | `frontend/src/pages/Public.jsx` |
| Participant workflow screens | `frontend/src/pages/Portal.jsx` |
| Staff console screens | `frontend/src/pages/Admin.jsx` |
| Sign-in screen | `frontend/src/pages/Login.jsx` |
| URLs, shared header/footer, route guards, page shell | `frontend/src/App.jsx` |
| Shared buttons, panels, form fields, empty/loading/error UI | `frontend/src/components/ui.jsx` |
| Global colors, typography, spacing, responsive rules | `frontend/src/style.css`, `frontend/src/theme.css` |
| HTML title, metadata, root document | `frontend/index.html` |
| API proxy, base path, selected static asset build copying | `frontend/vite.config.js` |
| Event, policy, account, payment, or registration rules | `backend/app/` services, schemas, and API routes |

Use React Router `Link`/`NavLink` for internal navigation, semantic buttons and form labels for controls, and existing CSS classes/tokens for consistent styling. Preserve keyboard focus, responsive layouts, and accessible names when editing interactive pages. Keep data access behind the shared API layer when its missing files are restored. Never put secrets in frontend code or `VITE_` environment variables because Vite embeds those values in the browser bundle.

The standard edit loop is: start the backend and frontend, edit the page/component and corresponding CSS, inspect desktop and narrow mobile layouts, then run `npm run build` from `frontend/` once the missing `src/lib/` modules are restored. Changes to server-side rules should be implemented and validated in the backend; UI checks alone cannot enforce authorization, prices, capacity, or eligibility.

## Edition data and policy

The seeded edition slug is `parallax-2026`. Local seed data includes categories such as Computing, Engineering, Robotics, Electronics, and Design, plus individual and team events. The seed's current policy sets a ₹350 pass, a lunch entitlement for both days, up to three included events subject to an inclusive ₹450 base-value cap, a 15-minute hold window, and a selection deadline. Values live in database edition/policy/event records and can differ from defaults after staff changes; the API is authoritative. Amounts in API/database logic are integer paise.

An included event's base value is used for the included-event cap. Its add-on price is a separate fee and does not count as the base value. A convention pass is required independently of event selection. Team registration has team size and membership rules. The backend validates event eligibility, selection count and cap, registration state, available capacity, pass requirements, team membership, and staff permissions.

For planning context and policy definitions, see [business rules](docs/BUSINESS_RULES.md) and [open decisions](docs/DECISIONS_AND_OPEN_QUESTIONS.md). Do not hard-code a displayed price or policy in a page when it should come from the current edition API.

## Payments, verification, and local demo behavior

Payments are disabled in the default local configuration (`PAYMENTS_ENABLED=false`). The API reports when an order uses the mock path, and provides a development mock payment action to exercise local pass/registration flows. This does not contact a payment provider or transfer money. Real Razorpay processing requires configured credentials and webhook setup; never use production credentials for local development.

Verification can be configured for institution email or document review. Email delivery and remote storage integrations are optional and depend on backend settings. The local demo may use local storage and development-only login. Do not treat a seeded account, verification status, payment, or ticket as evidence of real-world eligibility or successful payment.

## Deployment and assets

`frontend/vite.config.js` uses `VITE_BASE_PATH` for the static asset base, proxies local API requests, and copies a selected set of supplied brand files into the build. `frontend/vercel.json`, root `vercel.json`, `render.yaml`, and `Dockerfile` provide deployment configuration. Deployment is not automatic from local development. Read [DEPLOY.md](DEPLOY.md) and the relevant hosting guide before publishing or changing base URLs, origins, cookies, storage, or secrets.

Original visual assets are under root `images/`; frontend source copies are under `frontend/images/`. Preserve official logos and supplied artwork. See [asset inventory](docs/IMAGE_ASSET_INVENTORY.md) and [frontend image notes](frontend/images/README.md) for current mappings.

## Documentation index

- [Backend setup, endpoints, data, and security](BACKEND.md)
- [Product overview](docs/PRODUCT_OVERVIEW.md)
- [Frontend architecture notes](docs/FRONTEND_ARCHITECTURE.md)
- [Business rules](docs/BUSINESS_RULES.md)
- [Open decisions](docs/DECISIONS_AND_OPEN_QUESTIONS.md)
- [Configuration guide](docs/CONFIGURATION_GUIDE.md)
- [Image inventory](docs/IMAGE_ASSET_INVENTORY.md)
- [Deployment](DEPLOY.md)
- [Contributing](CONTRIBUTING.md)
