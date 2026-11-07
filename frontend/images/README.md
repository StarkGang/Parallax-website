# Supplied Visual Assets

This directory contains organizer-supplied visual references (logos, brochure/design utilities, team images, and related artwork used by the frontend).

## Guidelines

- **Preserve originals.** Keep supplied files intact unless a change is explicitly approved.
- **Document additions.** When adding new materials, use descriptive names (for example `parallax-logo-primary.svg`, `iste-mark-transparent.png`, `hero-abstract-01.webp`).
- **Organize intentionally.** Prefer grouping new materials into clear subdirectories (such as `logos/`, `backgrounds/`, `elements/`, `event-icons/`) without disrupting existing supplied paths that build/config/code may reference.
- **Format selection.** Prefer SVG for approved logos/simple artwork, transparent PNG/WebP for cutouts, and optimized JPG/WebP for photographs.
- **Track usage.** Record source, approval status, dimensions, and intended use in [docs/assets/image-and-media-inventory.md](../../docs/assets/image-and-media-inventory.md).
- **Brand integrity.** Never replace or modify official marks without brand-owner approval. Preserve aspect ratio and use `object-fit: contain` (or equivalent) for logos.
- **Derived assets.** Place optimized/derived files in clearly named project-owned locations; keep originals untouched.

## Relationship to Other Asset Locations

- `frontend/public/` — runtime static assets served directly.
- `frontend/src/assets/` — UI assets bundled by the frontend build.
- `backend/app/assets/icons/` — backend-bundled SVG icons for API/seed workflows.
- `ss/` — README screenshots (verify presence before referencing).

This file complements the repository-wide inventory; verify actual file paths before updating build configuration or UI references.
