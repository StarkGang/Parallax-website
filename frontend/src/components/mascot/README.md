# Mascot Guide (Frontend Component)

This directory implements the persistent 3D mascot guide used by the frontend shell. It is a **presentation-layer feature**; operational rules (pricing, eligibility, permissions, registration state) remain backend-authoritative.

## Runtime Behavior (Design Intent)

- Mounted once in the app shell and intended to persist across route changes.
- Avoids capturing page-level pointer events except its own small interaction surface (implementation-dependent).
- Supports hide/show preferences and reduced-motion/low-power handling (see implementation).
- Uses a Three.js canvas/model pipeline and DOM overlay/bubble for guidance.

## Main Files

| File | Responsibility |
|---|---|
| `MascotProvider.jsx` | Mount/lifecycle, feature gating, lazy loading, error boundary (as implemented) |
| `MascotOverlay.jsx` | Fixed overlay, anchor/bubble/highlight composition |
| `MascotCanvas.jsx` | Renderer/canvas lifecycle and drawing cadence |
| `MascotModel.js` | Three.js scene/model loading, normalization, lights/camera, clip handling, disposal |
| `MascotBrain.js` | State/scheduling/behavior selection |
| `TargetRegistry.js` | Resolves `[data-mascot-target]` elements and placement/collision logic |
| `SpeechBubble.jsx` | Accessible bubble/live-region presentation |
| `config/behaviors.js` | Route/target behavior configuration |
| `useMascotSettings.js` | Persisted visibility/settings and motion/power preferences |

> Verify exact behavior in code before documenting user-facing guarantees.

## Extending Guidance

Guidance can be attached via target attributes in UI markup and/or behavior config entries.

```jsx
<section
  data-mascot-target="pass-pricing"
  data-mascot-message="One pass covers both days."
  data-mascot-action="point"
  data-mascot-label="Convention pass"
  data-mascot-priority="2"
>
```

Behavior entries (example pattern) live in `config/behaviors.js`. Keep messages factual and aligned with API-driven policy data; do not hard-code pricing or eligibility claims.

## Model Assets & Build Notes

- Preferred/fallback model paths and clip-name matching are implementation-defined (see `MascotModel.js` and `public/mascot/` assets).
- Any rigging/export pipeline scripts referenced by this component should be treated as **tooling documentation**; verify script paths and inputs in the working copy before running.
- For skinned GLB optimization, preserve skin/armature integrity (avoid transforms/flatten/join/instance operations that break deformation).

## Accessibility & Performance

- Canvas should remain decorative/non-interactive for assistive tech where appropriate; bubble text should use polite announcements if implemented.
- Hide preference should be user-controlled and persisted.
- Reduced motion should suppress roaming/animation-heavy behaviors.
- Rendering should pause or throttle when hidden, offscreen, or when the tab is inactive (verify implementation).

## Maintenance

When mascot behavior or assets change, update this README and any related docs in `docs/FRONTEND_ARCHITECTURE.md`/`docs/features/public-and-portals.md` to keep documentation accurate.
