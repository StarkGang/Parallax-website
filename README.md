# PARALLAX — ISTE State Student Convention

A presentation-ready, static React prototype for the proposed PARALLAX two-day ISTE state student convention hosted by NSS College of Engineering, Palakkad, Kerala, India. It is designed for faculty and organizing committee review and static hosting on GitHub Pages.

> **Prototype boundary:** This is a frontend demo. It does not authenticate participants, verify student status, take payments, save registrations to a server, send email, or persist management edits. Never treat visible demo records as real registrations.

## Convention rules and decision status

The planning brief supplies these baseline requirements: a two-day convention; host NSS College of Engineering, Palakkad; dates unconfirmed; and a mandatory ₹500 convention pass for every participant. The pass includes lunch on both days. The included event allowance and event fees are separate from the pass.

This prototype demonstrates an allowance of **up to 3 eligible events**. The sum of their published `baseValue` figures must not exceed an illustrative **₹450 cap**. The planning discussion mentions ₹400 or ₹450; ₹450 here is explicitly not final. Whether selection must be exactly 3 or may be up to 3 is also awaiting approval. Extra events can be selected at their `addonPrice` only after the mandatory pass. The pass amount is never added to the included event value sum. Team members each need their own valid pass before team confirmation unless an edition administrator later configures another policy.

| Status | Details |
|---|---|
| Planning baseline | Convention name, host, two-day duration, mandatory ₹500 pass, lunch both days |
| Provisional demo values | Tagline, 3-event count, up-to selection, ₹450 cap, fictional events and event prices |
| Awaiting confirmation | Dates, official email, final cap and count/mode, schedule, venue rooms, event rules, eligibility, capacity, cancellation/refund policy, social accounts, travel/accommodation guidance, brand approvals |

The displayed participant volume of 500–1,000 is a planning estimate, not a confirmed capacity.

## Technology

- **React** builds reusable public and portal interfaces.
- **Vite** provides a small development server and static production build.
- **React Router `HashRouter`** supports deep navigation on GitHub Pages without server rewrite rules.
- **Plain CSS design system** keeps styling cohesive without an extra CSS framework dependency.
- **Lucide React** supplies accessible interface icons.
- **Static data and mock service adapters** create an API boundary for future migration without network calls.

## Setup and commands

Prerequisites: Node.js 22 LTS (or a compatible current Node release) and npm. From the repository root:

```sh
npm install
npm run dev
npm run build
npm run preview
npm test
```

`npm run dev` prints the local URL. `npm run build` writes the static site to `dist/`. `npm run preview` serves that build locally. Tests use Node's built-in test runner; add tests as pricing policy is finalized.

## Main routes

| Route | Page |
|---|---|
| `/` | Home, convention summary, pass model, featured events |
| `/about` | Convention and host context |
| `/events`, `/events/:slug` | Searchable/filterable event catalog and details |
| `/pass` | Mandatory pass and included/add-on pricing explanation |
| `/schedule`, `/venue`, `/faq`, `/contact` | Public planning information |
| `/portal` | Demo participant dashboard |
| `/portal/select-events` | Local interactive included/add-on selection calculation |
| `/portal/registrations`, `/portal/profile` | Demo registration and profile views |
| `/manage` | Coordinator dashboard and event configuration concept |

Routes are hash URLs (for example `/#/events`) by design; direct nested-route refreshes therefore do not require GitHub Pages rewrite support.

## Repository map

```text
.
├── .github/workflows/deploy.yml  # build and GitHub Pages deployment
├── docs/                         # product, rules, architecture, configuration, deployment
├── images/                       # supplied originals; preserve these
├── index.html                    # document shell and metadata
├── public/                       # reserved for project-owned public files
├── src/
│   ├── config/convention.config.js # edition settings and provisional-policy comments
│   ├── data/events.js              # fictional sample event records
│   ├── data/navigation.js          # shared route labels
│   ├── services/mockServices.js    # local service boundary
│   ├── utils/                      # pricing and event eligibility pure helpers
│   ├── main.jsx                    # page components and HashRouter
│   └── style.css                   # responsive design system
├── vite.config.js                 # Vite base-path configuration
└── package.json                   # commands and dependencies
```

See [Frontend architecture](docs/FRONTEND_ARCHITECTURE.md) and [Configuration guide](docs/CONFIGURATION_GUIDE.md) for fuller maps.

## Create another edition

Edit `src/config/convention.config.js` for edition name, tagline, organizer, host, dates, day count, city, email placeholder, social links, registration status, currency, pass, lunch, allowance count, cap, selection mode and demo flag. Components read these settings. Selection mode supports `up_to` and `exact`; the clearly labeled demo default is `up_to`. Update `src/data/events.js` with stable IDs/slugs, category, format, `baseValue`, `addonPrice`, team size, eligibility, capacity, state, rules, schedule and featured flag. Keep fictional content labeled and obtain approval before replacing provisional values with official policy.

### Pricing semantics

- `passPrice`: mandatory independent convention pass, currently ₹500.
- `baseValue`: event's published value used only for included-event cap validation.
- `addonPrice`: separate fee to register for that event after a pass.
- `includedEventValueCap`: maximum sum of selected included-event `baseValue` values.
- `includedEventCount` and `selectionMode`: allowance policy.

Example: event base values ₹100 + ₹150 + ₹200 = ₹450, meeting the illustrative cap. With `up_to: 3`, fewer selections are also allowed. Add-on fees of ₹150 and ₹200 create ₹350 of add-ons; the participant still needs the separate ₹500 pass. The demo total is ₹850, before any other charges. A ₹200 event base value does not imply its add-on costs ₹200.

The helper functions in `src/utils/pricing.js` calculate selected base totals, count/cap validity, add-on totals and INR display. `src/utils/eventEligibility.js` determines whether a sample event is eligible under the configured cap.

### Annotated event record

```js
{
  id: 'circuit-lab',                 // stable identifier
  slug: 'circuit-lab',               // route segment
  title: 'Circuit Lab',
  category: 'Engineering',
  format: 'individual',              // individual | team
  baseValue: 100,                    // included-cap calculation only
  addonPrice: 150,                   // separately payable after pass
  teamMin: 1, teamMax: 1,
  eligibility: 'Student status requires future verification.',
  capacity: 'To be announced',
  registrationState: 'Planning preview',
  rules: ['Illustrative rule pending approval.'],
  schedule: 'Day and time to be announced',
  venue: 'Venue to be announced',
  featured: true
}
```

Archive an event by removing it from the active `events` array after confirming it is no longer referenced; feature it by setting `featured: true`. Do not recycle stable IDs. Production should preserve historical registrations and use an explicit active state.

## Brand assets and visual system

The root `images/` folder contains supplied originals. Do not rename, overwrite, delete, recolor or distort official logo files. The Parallax logo is used at intrinsic proportions in the navigation; the NSSCE logo appears on About; ISTE appears in the footer. The hero uses the supplied decorative globe SVG. The Vite build copies only these four used files into `dist/images/`; all other supplied assets remain inventoried source references. Event illustrations, supplied background art and raw stock are inventoried for committee review; no remote image is required for the core pages. The configured tagline is prototype copy. Do not treat the abstract site treatment as a newly approved logo.

See [`images/README.md`](images/README.md) for safe additions and [`docs/IMAGE_ASSET_INVENTORY.md`](docs/IMAGE_ASSET_INVENTORY.md) for every supplied path, dimensions and current usage map. The inventory distinguishes files currently used from candidates requiring human review.

Colors and responsive rules are CSS custom properties and media queries in `src/style.css`. Fonts use Manrope and DM Mono with system fallbacks; Google Fonts is optional and is not required for app function. Replace remote font imports with approved local font files if the production deployment needs to avoid external font requests.

## GitHub Pages deployment

The workflow in `.github/workflows/deploy.yml` builds on pushes to `main` and manual dispatch. For a repository project site it supplies `VITE_BASE_PATH=/<repository-name>/`, without hard-coding an owner or repository. Set repository variable `VITE_BASE_PATH` to `/` for a user/organization site or custom domain. `vite.config.js` defaults to `./` for local builds.

1. Push this repository to GitHub, with the deployment workflow on `main`.
2. In **Settings → Pages**, select **GitHub Actions** as the build and deployment source.
3. Ensure Actions are permitted for the repository and that the workflow's Pages permissions are not restricted by organization policy.
4. Run the workflow or push to `main`; wait for the deploy job to complete.
5. Open the URL shown by the deployment job, normally `https://USERNAME.github.io/REPOSITORY/`.

The site has not been deployed by this prototype task. See [deployment guide](docs/GITHUB_PAGES_DEPLOYMENT.md). A blank screen usually means the base path is wrong: check the generated asset URLs and set `VITE_BASE_PATH` to the project prefix with both slashes. Routes use `/#/...` to avoid nested-route refresh errors. For a custom domain configure it in Pages and set the base to `/`; add DNS only after the repository owner confirms the domain.

## Services and future migration

UI-facing service-shaped adapters live in `src/services/mockServices.js`: events, participant profile, registrations, pricing, payment and management. They currently return local demo data; no arbitrary URL is fetched. Future Express REST implementations can replace these adapters. Production is expected to use React/Vite, Node/Express, Supabase Auth for Google OAuth, PostgreSQL, server-created payment orders and verified webhooks, role-based permissions, and database-enforced capacity/pricing/pass/duplicate rules. Never place payment secrets, service-role keys or OAuth client secrets in frontend source or Vite variables. See [migration plan](docs/FUTURE_FULL_STACK_MIGRATION.md).

## Review, accessibility and limitations

For committee review, walk through Home → Pass → Events → Portal → Select events; try adding a choice beyond the configured count and a choice beyond the cap; inspect team pass language; then review About, Schedule, Venue and FAQ for provisional placeholders. The selector is local React state and resets on navigation/reload. The profile is read-only mock content. Buttons for future server actions show a demo notice; no successful payment or verification is represented.

The UI uses landmarks, a skip link, labels, keyboard-operable links and controls, visible focus, reduced-motion rules, responsive layouts and semantic disclosure elements. Review contrast and keyboard behavior with assistive technology before production. Demo data is not suitable for real personal or financial information. Production requires server-side validation, authentication, authorization, privacy/security review, accessible verification, confirmed policies and proper audit controls.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md). Suggested branches: `feat/event-selector`, `fix/pages-base-path`, `docs/policy-review`; use concise commits such as `feat: add event filters`. Keep policy configuration centralized, preserve supplied artwork, and update docs when behavior changes.

## Glossary

- **Convention pass:** mandatory ₹500 admission pass per participant, including both lunches.
- **Base value:** published event value used to validate the included-event cap.
- **Addon price:** separate event fee after a convention pass.
- **Included-event cap:** maximum permitted sum of selected base values.
- **Team registration:** one team event entry whose members each need a pass under the proposed rule.
- **Verified student:** a participant whose student eligibility has been checked by a future real verification process; the prototype verifies nobody.
