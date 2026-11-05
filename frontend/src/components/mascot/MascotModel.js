import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { WALK_SPEED_PX_PER_SEC } from './config/behaviors.js';

const BASE_URL = import.meta.env.BASE_URL || '/';
const STATIC_MODEL_URL = `${BASE_URL}mascot/mascot.glb`;
const RIGGED_MODEL_URL = `${BASE_URL}mascot/mascot-rigged.glb`;

const MODEL_HEIGHT = 1.72;
const VIEW_HEIGHT = 2.5;
const REST_YAW = -0.18;
const MODEL_YAW_OFFSET = 0;

const CLIP_ALIASES = {
  idle: ['idle', 'breath', 'stand'],
  walk: ['walk'],
  point: ['point'],
  wave: ['wave'],
  jump: ['jump'],
};

let resolvedModelUrl = null;
// Only used as a last resort: if a rigged asset arrives without UVs or maps,
// the unrigged sculpture's material is borrowed so the guide is never blank.
let cachedStaticMaterial = null;
let staticMatPromiseGlobal = null;

/**
 * Load the textured material from the static (non-rigged) GLB and cache it
 * so multiple stage instances don't re-download it.
 */
function hasOwnTexture(model) {
  let usable = false;
  model.traverse((node) => {
    if (usable || !node.isMesh) return;
    if (!node.geometry?.attributes?.uv) return;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    usable = materials.some((material) => Boolean(material?.map));
  });
  return usable;
}

function loadStaticMaterial() {
  if (cachedStaticMaterial) return Promise.resolve(cachedStaticMaterial);
  if (staticMatPromiseGlobal) return staticMatPromiseGlobal;

  staticMatPromiseGlobal = new Promise((resolve) => {
    const staticLoader = new GLTFLoader();
    staticLoader.setMeshoptDecoder(MeshoptDecoder);
    staticLoader.load(
      STATIC_MODEL_URL,
      (gltf) => {
        let mat = null;
        gltf.scene.traverse((node) => {
          if (!mat && node.isMesh && node.material) {
            mat = Array.isArray(node.material) ? node.material[0] : node.material;
          }
        });
        cachedStaticMaterial = mat;
        resolve(mat);
      },
      undefined,
      () => resolve(null), // texture load failure is non-fatal
    );
  });

  return staticMatPromiseGlobal;
}

/**
 * Prefer the rigged asset when it is present. Vite serves index.html for
 * unknown paths in dev, so a 200 alone is not enough — check the content type.
 */
async function resolveModelUrl() {
  if (resolvedModelUrl) return resolvedModelUrl;
  try {
    const response = await fetch(RIGGED_MODEL_URL, { method: 'HEAD' });
    const type = response.headers.get('content-type') || '';
    if (response.ok && !type.includes('text/html')) {
      resolvedModelUrl = RIGGED_MODEL_URL;
      return resolvedModelUrl;
    }
  } catch {
    /* fall through to the static asset */
  }
  resolvedModelUrl = STATIC_MODEL_URL;
  return resolvedModelUrl;
}

export function createMascotStage({
  host,
  dprCap = 1.5,
  antialias = true,
  reducedMotion = false,
  onFail,
  onReady,
} = {}) {
  if (!host) return null;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias,
      powerPreference: 'low-power',
    });
    if (!renderer.getContext()) throw new Error('No WebGL context');
  } catch {
    onFail?.();
    return null;
  }

  const canvas = renderer.domElement;
  canvas.className = 'mascot-webgl';
  canvas.setAttribute('aria-hidden', 'true');
  canvas.setAttribute('role', 'presentation');
  host.appendChild(canvas);

  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 20);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);

  scene.add(new THREE.HemisphereLight('#eaf6ff', '#162536', 2.1));
  scene.add(new THREE.AmbientLight('#9bd8f5', 0.45));

  const key = new THREE.DirectionalLight('#ffffff', 3.4);
  key.position.set(2.4, 3.4, 4);
  scene.add(key);

  const fill = new THREE.DirectionalLight('#9adcff', 2.0);
  fill.position.set(-2.6, 1.4, 3.4);
  scene.add(fill);

  const front = new THREE.DirectionalLight('#e6f7ff', 1.45);
  front.position.set(0, 1.4, 4.5);
  scene.add(front);

  const rim = new THREE.DirectionalLight('#38bdf8', 3.2);
  rim.position.set(-2.4, 2.6, -3);
  scene.add(rim);

  const group = new THREE.Group();
  group.position.y = -VIEW_HEIGHT / 2 + 0.06;
  group.rotation.y = REST_YAW + MODEL_YAW_OFFSET;
  scene.add(group);

  let mixer = null;
  let actions = new Map();
  let currentAction = null;
  let currentKey = '';
  let desiredState = 'idle';
  let oneShot = false;
  let targetYaw = group.rotation.y;
  let paused = false;
  let disposed = false;
  let contextLost = false;
  let reduced = Boolean(reducedMotion);
  let rafId = 0;
  let yawRaf = 0;
  let loopId = 0;
  let lastFrame = 0;
  // Walk pacing: how far one cycle travels (in the skin's units) and how that
  // maps to screen pixels, so the clip can be paced to the guide's speed.
  let walkStride = 0;
  let walkCycle = 0;
  let modelScale = 1;
  let walkTimeScale = 1;

  function requestRender() {
    if (disposed || contextLost || rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      if (!disposed && !contextLost) renderer.render(scene, camera);
    });
  }

  function stopClipLoop() {
    if (loopId) cancelAnimationFrame(loopId);
    loopId = 0;
  }

  function startClipLoop() {
    if (loopId || disposed || paused || contextLost || reduced || !mixer) return;
    lastFrame = performance.now();
    const tick = (now) => {
      loopId = 0;
      if (disposed || paused || contextLost || reduced || !mixer) return;
      loopId = requestAnimationFrame(tick);
      const delta = Math.min(0.05, (now - lastFrame) / 1000);
      lastFrame = now;
      group.rotation.y = THREE.MathUtils.damp(group.rotation.y, targetYaw, 6, delta);
      mixer.update(delta);
      renderer.render(scene, camera);
    };
    loopId = requestAnimationFrame(tick);
  }

  function resize() {
    if (disposed) return;
    // The renderer sizes the canvas, and the canvas is styled to fill the host.
    // If the stylesheet is missing or the host has no constrained height, that
    // feedback loop can grow without bound and collapse the camera aspect, so
    // clamp to the viewport before applying it.
    const maxEdge = Math.max(
      1,
      Math.min(4096, Math.max(window.innerWidth || 0, window.innerHeight || 0) * 2 || 4096),
    );
    const width = Math.min(host.clientWidth || 1, maxEdge);
    const height = Math.min(host.clientHeight || 1, maxEdge);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, dprCap));
    renderer.setSize(width, height, false);
    const aspect = width / height;
    camera.left = -(VIEW_HEIGHT * aspect) / 2;
    camera.right = (VIEW_HEIGHT * aspect) / 2;
    camera.top = VIEW_HEIGHT / 2;
    camera.bottom = -VIEW_HEIGHT / 2;
    camera.updateProjectionMatrix();

    if (actions.has('walk')) {
      const next = computeWalkTimeScale();
      if (next !== walkTimeScale) {
        walkTimeScale = next;
        if (currentKey === 'walk' && currentAction) {
          currentAction.setEffectiveTimeScale(walkTimeScale);
        }
      }
    }

    requestRender();
  }

  function clipKeyForState(stateName) {
    if (stateName === 'walking' || stateName === 'returning') return 'walk';
    if (stateName === 'guiding') return 'point';
    return 'idle';
  }

  function findClip(animations, key) {
    const aliases = CLIP_ALIASES[key] || [key];
    return animations.find((clip) => {
      const name = String(clip.name || '').toLowerCase();
      return aliases.some((alias) => name.includes(alias));
    });
  }

  function onClipFinished(event) {
    if (!oneShot || event.action !== currentAction) return;
    oneShot = false;
    const key = clipKeyForState(desiredState);
    if (actions.has(key)) playClip(key);
  }

  function playClip(key, { once = false } = {}) {
    const next = actions.get(key);
    if (!next) return false;
    if (!once && next === currentAction) return true;

    next.reset();
    next.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, once ? 1 : Infinity);
    next.clampWhenFinished = once;
    next.enabled = true;
    next.setEffectiveTimeScale(key === 'walk' ? walkTimeScale : 1);
    next.setEffectiveWeight(1);

    if (currentAction && currentAction !== next) {
      next.crossFadeFrom(currentAction, 0.3, false);
    } else {
      next.fadeIn(0.25);
    }

    next.play();
    currentAction = next;
    currentKey = key;
    startClipLoop();
    return true;
  }

  const HIPS_POSITION = /hips\.position$/i;

  function findHipsPosition(clip) {
    return clip?.tracks?.find((track) => HIPS_POSITION.test(track.name)) || null;
  }

  /**
   * The five Mixamo clips do not share one coordinate space. Idle is baked with
   * the skinned FBX and keeps the Hips near its rest offset (~0.011 units),
   * while the four animation-only imports carry the Hips at its source unit
   * (~0.93) plus a forward walk drift. Played untouched, Walk, Point, Wave and
   * Jump translate the model hundreds of view units away and it disappears.
   *
   * Normalize every clip against the Idle rest pose: rescale the vertical bob
   * and hop into the skin's units and pin the lateral / forward axes, because
   * the brain owns the on-screen movement.
   */
  function normalizeRootMotion(animations, idleClip, walkClip) {
    const idleTrack = findHipsPosition(idleClip);
    if (!idleTrack || idleTrack.values.length < 3) return;

    const anchor = [idleTrack.values[0], idleTrack.values[1], idleTrack.values[2]];
    const idleRest = Math.hypot(anchor[0], anchor[1], anchor[2]);

    for (const clip of animations) {
      if (clip === idleClip) continue;
      const track = findHipsPosition(clip);
      if (!track || track.values.length < 3) continue;

      const values = track.values;
      const first = [values[0], values[1], values[2]];

      // The largest rest component is the hips height, i.e. the vertical axis.
      let vertical = 0;
      for (let axis = 1; axis < 3; axis += 1) {
        if (Math.abs(first[axis]) > Math.abs(first[vertical])) vertical = axis;
      }

      const rest = Math.hypot(first[0], first[1], first[2]);
      const unit = rest > 1e-6 && idleRest > 1e-6 ? Math.min(1, idleRest / rest) : 1;

      // Measure the stride before the horizontal axes are pinned: the widest
      // horizontal excursion of the hips is how far one cycle travels.
      let stride = 0;
      for (let axis = 0; axis < 3; axis += 1) {
        if (axis === vertical) continue;
        let low = Infinity;
        let high = -Infinity;
        for (let i = 0; i < values.length; i += 3) {
          low = Math.min(low, values[i + axis]);
          high = Math.max(high, values[i + axis]);
        }
        stride = Math.max(stride, (high - low) * unit);
      }
      if (clip === walkClip) {
        walkStride = stride;
        walkCycle = clip.duration || 0;
      }

      for (let i = 0; i < values.length; i += 3) {
        for (let axis = 0; axis < 3; axis += 1) {
          values[i + axis] =
            axis === vertical
              ? anchor[axis] + (values[i + axis] - first[axis]) * unit
              : anchor[axis];
        }
      }
    }
  }

  /**
   * Pace the walk cycle to the ground it actually covers. The authored clip
   * ambles (~0.8 m/s at this size) while the brain moves the guide at
   * WALK_SPEED_PX_PER_SEC, so playing it at 1x slides the feet. Matching the
   * two keeps each step planted on the page instead of skating.
   */
  function computeWalkTimeScale() {
    if (!walkStride || !walkCycle || !modelScale) return 1;
    const pxPerWorldUnit = (host.clientHeight || window.innerHeight || 1) / VIEW_HEIGHT;
    const naturalSpeed = (walkStride * modelScale * pxPerWorldUnit) / walkCycle;
    if (!(naturalSpeed > 0.5)) return 1;
    return THREE.MathUtils.clamp(WALK_SPEED_PX_PER_SEC / naturalSpeed, 0.8, 2.8);
  }

  function setupAnimations(animations, model) {
    if (!animations?.length) return;
    mixer = new THREE.AnimationMixer(model);

    // Put every clip in the same in-place space before creating actions.
    const idleClip = findClip(animations, 'idle');
    normalizeRootMotion(animations, idleClip, findClip(animations, 'walk'));

    for (const key of Object.keys(CLIP_ALIASES)) {
      const clip = findClip(animations, key);
      if (!clip) continue;
      actions.set(key, mixer.clipAction(clip));
    }
    mixer.addEventListener('finished', onClipFinished);
    walkTimeScale = computeWalkTimeScale();

    // The requested state may already have moved on while the GLB was
    // downloading, so restore whatever the stage is meant to show now.
    const requestedKey = clipKeyForState(desiredState);
    if (actions.has(requestedKey) && requestedKey !== 'idle') {
      playClip(requestedKey);
      mixer.update(0);
    } else if (actions.has('idle')) {
      playClip('idle');
      // Evaluate the first Idle frame before painting so the bind-pose T-pose
      // never flashes during the initial render.
      mixer.update(0);
    }
  }

  function applyMaterial(model, mat) {
    if (!mat) return;
    // Tune the shared material for in-scene readability.
    mat.envMapIntensity = 0;
    if ('metalness' in mat) mat.metalness = Math.min(mat.metalness ?? 0, 0.25);
    mat.needsUpdate = true;
    model.traverse((node) => {
      if (!node.isMesh) return;
      node.frustumCulled = false;
      node.castShadow = false;
      node.receiveShadow = false;
      node.material = mat;
    });
  }

  function tuneMaterial(material) {
    if (!material || material.userData?.__mascotShared) return;
    material.envMapIntensity = 0;
    // Only damp metalness when nothing authored drives it: a metallicRoughness
    // map is part of the sculpture's look and must not be flattened.
    if ('metalness' in material && !material.metalnessMap) {
      material.metalness = Math.min(material.metalness ?? 0, 0.25);
    }
    material.needsUpdate = true;
  }

  function handleModel(gltf, staticMat) {
    if (disposed) return;
    const model = gltf.scene;
    const isRigged = Boolean(gltf.animations && gltf.animations.length > 0);

    if (isRigged && staticMat && !hasOwnTexture(model)) {
      // Legacy fallback for a rig exported without UVs: borrow the sculpture's
      // atlas material rather than render an untextured silhouette.
      applyMaterial(model, staticMat);
    } else {
      // The rigged asset carries its own UVs and atlas, so keep its material
      // and only tune the shading in place.
      model.traverse((node) => {
        if (!node.isMesh) return;
        node.frustumCulled = false;
        node.castShadow = false;
        node.receiveShadow = false;
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        for (const material of materials) tuneMaterial(material);
      });
    }

    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const scale = MODEL_HEIGHT / (size.y || 1);
    modelScale = scale;
    model.scale.setScalar(scale);
    model.updateMatrixWorld(true);

    const scaledBounds = new THREE.Box3().setFromObject(model);
    const center = scaledBounds.getCenter(new THREE.Vector3());
    // Mixamo-rigged animations already ground the feet at Y=0 in world space.
    // The static mesh is bind-pose centred at origin so we need min.y offset.
    const yOffset = isRigged ? 0 : -scaledBounds.min.y;

    model.position.set(model.position.x - center.x, yOffset, model.position.z - center.z);

    group.add(model);
    setupAnimations(gltf.animations, model);
    requestRender();
    onReady?.();
  }

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  resolveModelUrl()
    .then((url) => {
      loader.load(
        url,
        async (gltf) => {
          if (disposed) return;
          // Only fetch the sculpture material when the rig cannot shade itself.
          const needsBorrowedMaterial = gltf.animations?.length > 0 && !hasOwnTexture(gltf.scene);
          const staticMat = needsBorrowedMaterial ? await loadStaticMaterial() : null;
          handleModel(gltf, staticMat);
        },
        undefined,
        () => {
          if (!disposed) onFail?.();
        },
      );
    })
    .catch(() => {
      if (!disposed) onFail?.();
    });

  const onContextLost = (event) => {
    event.preventDefault();
    contextLost = true;
    stopClipLoop();
    cancelAnimationFrame(yawRaf);
    cancelAnimationFrame(rafId);
    rafId = 0;
  };

  const onContextRestored = () => {
    contextLost = false;
    resize();
  };

  canvas.addEventListener('webglcontextlost', onContextLost, false);
  canvas.addEventListener('webglcontextrestored', onContextRestored, false);

  resize();

  return {
    setFacing(radians) {
      if (disposed || typeof radians !== 'number') return;
      targetYaw = THREE.MathUtils.clamp(radians, -1.15, 1.15) + MODEL_YAW_OFFSET;
      if (mixer) {
        startClipLoop();
        return;
      }
      if (reduced || paused || contextLost) {
        group.rotation.y = targetYaw;
        requestRender();
        return;
      }
      const from = group.rotation.y;
      const start = performance.now();
      cancelAnimationFrame(yawRaf);
      const step = (now) => {
        if (disposed) return;
        const k = Math.min(1, (now - start) / 420);
        const eased = 1 - Math.pow(1 - k, 3);
        group.rotation.y = from + (targetYaw - from) * eased;
        renderer.render(scene, camera);
        if (k < 1) yawRaf = requestAnimationFrame(step);
        else yawRaf = 0;
      };
      yawRaf = requestAnimationFrame(step);
    },

    setState(stateName) {
      desiredState = stateName || 'idle';
      if (!mixer || actions.size === 0) return;
      const key = clipKeyForState(desiredState);
      if (actions.has(key)) playClip(key);
    },

    wave() {
      if (!mixer || !actions.has('wave')) return;
      oneShot = true;
      playClip('wave', { once: true });
    },

    jump() {
      if (!mixer || !actions.has('jump')) return;
      oneShot = true;
      playClip('jump', { once: true });
    },

    playGesture(name) {
      if (!mixer || !actions.has(name)) return;
      oneShot = true;
      playClip(name, { once: true });
    },

    setPaused(value) {
      paused = Boolean(value);
      if (paused) {
        stopClipLoop();
        cancelAnimationFrame(yawRaf);
        yawRaf = 0;
      } else {
        requestRender();
        if (mixer) startClipLoop();
      }
    },

    setReducedMotion(value) {
      reduced = Boolean(value);
      if (reduced) {
        stopClipLoop();
        cancelAnimationFrame(yawRaf);
        yawRaf = 0;
        group.rotation.y = targetYaw;
        requestRender();
      } else if (mixer) {
        startClipLoop();
      }
    },

    resize,

    dispose() {
      if (disposed) return;
      disposed = true;
      stopClipLoop();
      cancelAnimationFrame(rafId);
      cancelAnimationFrame(yawRaf);
      canvas.removeEventListener('webglcontextlost', onContextLost);
      canvas.removeEventListener('webglcontextrestored', onContextRestored);
      mixer?.removeEventListener('finished', onClipFinished);
      mixer?.stopAllAction();
      mixer = null;
      actions.clear();
      currentAction = null;

      scene.traverse((node) => {
        if (!node.isMesh) return;
        node.geometry?.dispose?.();
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        for (const material of materials) {
          if (!material) continue;
          // Textures shared with the cached sculpture material are not ours.
          if (material.userData?.__mascotShared) continue;
          for (const slot of [
            'map',
            'normalMap',
            'roughnessMap',
            'metalnessMap',
            'emissiveMap',
            'alphaMap',
            'aoMap',
          ]) {
            material[slot]?.dispose?.();
          }
          material.dispose?.();
        }
      });

      renderer.dispose();
      renderer.forceContextLoss?.();
      canvas.parentNode?.removeChild(canvas);
    },
  };
}
