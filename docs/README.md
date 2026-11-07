# Documentation

Repository-relative documentation for the Parallax-website implementation (React/Vite frontend + FastAPI backend). Content is derived from the checked-in code/config; unverified operational or external-provider details are marked as such.

## Start here

- [Installation](getting-started/installation.md)
- [Configuration](getting-started/configuration.md)
- [Development setup](getting-started/development-setup.md)
- [System overview](architecture/overview.md)
- [API reference](api/reference.md)
- [Deployment guide](deployment/deployment-guide.md)
- [Troubleshooting](troubleshooting/common-issues.md)

## Architecture

- [Overview](architecture/overview.md) — high-level components and boundaries
- [System design](architecture/system-design.md) — runtime modules, integrations, and responsibilities
- [Data flow](architecture/data-flow.md) — request, auth, registration/payment, and verification flows
- [Database schema](architecture/database-schema.md) — conceptual model based on SQLAlchemy models

## API and features

- [API reference](api/reference.md) — `/api/v1` route summary mapped to backend routers and frontend client
- [Public and portals](features/public-and-portals.md) — SPA routes, public pages, participant/admin surfaces

## Development and operations

- [Testing](development/testing.md)
- [Coding guidelines](development/coding-guidelines.md)
- [Deployment guide](deployment/deployment-guide.md)
- [Common issues](troubleshooting/common-issues.md)
- [Image and media inventory](assets/image-and-media-inventory.md)

## Legacy/reference docs

These files predate the full-stack implementation and are retained as product/reference context; check implementation-aligned docs above for current behavior.

- [Product overview](PRODUCT_OVERVIEW.md)
- [Frontend architecture (legacy context)](FRONTEND_ARCHITECTURE.md)
- [Business rules (working notes)](BUSINESS_RULES.md)
- [Configuration guide (legacy context)](CONFIGURATION_GUIDE.md)
- [Decisions and open questions](DECISIONS_AND_OPEN_QUESTIONS.md)
- [GitHub Pages deployment note](GITHUB_PAGES_DEPLOYMENT.md)
- [Future full-stack migration note](FUTURE_FULL_STACK_MIGRATION.md)
