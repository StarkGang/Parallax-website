# Image and Media Inventory

Inventory of image/media locations verified in the repository checkout. Use repo-relative paths; do not add machine-local absolute paths.

## Verified locations

| Location | Purpose | Notes |
|---|---|---|
| `frontend/images/` | Frontend image assets/source artwork kept with frontend | Treat official logos/supplied artwork as authoritative unless maintainers approve changes. |
| `frontend/public/` | Public/runtime static assets served by the frontend | Files here may be referenced by public URLs/asset paths at runtime. |
| `frontend/src/assets/` | Imported frontend source assets (including `hud/`) | Used by components/build pipeline. |
| `backend/app/assets/icons/` | Backend-packaged icon assets | Verify usage before moving/renaming. |
| `ss/` | Repository screenshots (`1.png`–`6.png` present in checkout) | Useful for README/docs previews; keep references repo-relative. |

## Not verified / absent

| Path | Status |
|---|---|
| root `images/` | Not present in the inspected checkout; do not document as an active asset source unless it exists. |

## Guidance

- Preserve official logos and supplied artwork; optimize/copy only when necessary and approved.
- When adding screenshots/media to docs, store them in a repo-tracked location and reference them relatively.
- Avoid embedding local filesystem paths or user-profile directories in markdown.
