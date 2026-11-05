# Parallax mascot guide

A single persistent 3D guide mounted in the app shell. It never remounts on
route changes, never captures page-level pointer events, and unloads completely
when hidden.

## How it is put together

| File | Responsibility |
| --- | --- |
| `MascotProvider.jsx` | Mount point, WebGL check, lazy chunk loading, hide/show control, error boundary |
| `MascotOverlay.jsx` | Fixed layer, positioned anchor, bubble, hit area, highlight ring |
| `MascotCanvas.jsx` | React lifecycle for the renderer, resize and prop wiring |
| `MascotModel.js` | Three.js stage: loader, normalization, lights, camera, clips, disposal |
| `MascotBrain.js` | Explicit state machine and scheduler |
| `TargetRegistry.js` | Finds `[data-mascot-target]`, measures it, picks collision-free spots |
| `SpeechBubble.jsx` | DOM bubble (`role="status"`, `aria-live="polite"`) |
| `config/behaviors.js` | Route/target messages, priorities, cooldowns |
| `useMascotSettings.js` | Persisted hide preference, reduced motion, low-power detection |

There is **one** `<canvas>`, one renderer and one model. Movement is a CSS
transform on the anchor; the renderer only draws when the model is loaded, when
the facing changes, or while a rigged clip is playing (capped at ~30fps). It
stops when the tab is hidden, the route is excluded, or the guide is hidden.

## Adding behaviour

No core changes are needed:

```jsx
<section
  data-mascot-target="pass-pricing"
  data-mascot-message="One pass covers both days."
  data-mascot-action="point"
  data-mascot-label="Convention pass"
  data-mascot-priority="2"
>
```

```js
// config/behaviors.js
{
  id: 'pass',
  match: /^\/pass$/,
  behaviors: [
    { target: 'pass-pricing', message: 'One pass covers both days.', cooldownMs: 90000, maxShows: 1 },
  ],
}
```

For catalogues, use `group: { prefix: 'event-' }`. Every element whose target id
starts with the prefix is a candidate; no list of card ids has to be maintained.

- Guidance only fires while the target is visible.
- A collision check rejects spots that overlap the target, any visible
  interactive element (links, buttons, fields) or page copy. On wide screens
  the registry can use the outer margin beside the content. If a layout has no
  free spot at all, guidance falls back to the ring and bubble at the resting
  corner.
- Guidance is suppressed on mobile and under reduced motion (ring + bubble at
  rest only).
- Cooldowns, per-target show limits and a global cooldown stop it nagging.

## Model contract

The loader prefers `public/mascot/mascot-rigged.glb`, then falls back to
`public/mascot/mascot.glb`.

Clip names are matched loosely (case-insensitive substrings):

| State | Accepted names |
| --- | --- |
| idle | `Idle`, `Breathing Idle`, `Stand` |
| walk | `Walk`, `Walking` |
| point | `Point`, `Pointing` |
| wave | `Wave`, `Waving` |
| jump | `Jump`, `Jumping` |

Walk must be **in place** — the brain moves the mascot. Clips crossfade over
0.3s. One-shots (Wave) clamp and return to the current state. If a clip is
missing, that gesture is skipped; the model is never rotated or bent to fake it.

The supplied files are two different meshes — the sculpture has 74,822 vertices
with UVs and a full PBR material, the Mixamo skin has 87,667 vertices, no UV
layer and no textures. Their UVs and vertex orders cannot be swapped; doing that
samples unrelated atlas islands and the model looks random. So the rigged asset
is the *sculpture* skinned to the Mixamo skeleton: `skin_sculpture.py` transfers
the skin weights onto the sculpture by closest surface, parents it to the
armature and exports one file with the sculpture's UVs, material and all five
clips. Textures stay as authored (1024² webp).

Root motion is normalized at load: Idle is baked with the skin (hips offset
~0.011) while the four animation-only imports are ~100x larger and carry a
forward walk drift. Every clip is rescaled and re-anchored to the Idle hips, so
Walk, Point, Wave and Jump stay in frame with only the vertical bob and hop
kept.

The Mixamo handoff folder is `mascot-rig-source/`; see its README for the five
exact FBX filenames and export settings.

### Rebuilding the rigged asset

Run from `frontend/`:

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python mascot-rig-source/skin_sculpture.py

node mascot-rig-source/finalize_rig.mjs \
  mascot-rig-source/mascot-merged.raw.glb \
  mascot-rig-source/mascot-merged.oriented.glb

npx gltf-transform optimize mascot-rig-source/mascot-merged.oriented.glb \
  public/mascot/mascot-rigged.glb \
  --compress meshopt --simplify false --palette false \
  --flatten false --join false --instance false
```

No `--texture-size` / `--texture-compress` step: the authored 1024² maps ship
untouched. For a skinned asset keep `--flatten`, `--join` and `--instance` off —
flattening re-parents the mesh out of the armature and bakes a second root
rotation, which collapses the character on screen. Verify in the browser that
the mesh still deforms (a bind T-pose means the skin was lost).

## Accessibility

- The renderer canvas is `aria-hidden`; the small hit area is pointer-only.
- Bubble copy is a polite live region.
- Hide is a real button; the preference persists in `localStorage`
  (`parallax.mascot.hidden`). Hiding unmounts the renderer and frees GPU memory.
- Reduced motion disables roaming, floating and clip playback.
- No audio is used, so there is no mute state.
