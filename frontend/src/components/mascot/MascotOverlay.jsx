import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import MascotCanvas from './MascotCanvas.jsx';
import SpeechBubble from './SpeechBubble.jsx';
import { MascotBrain, REST_YAW } from './MascotBrain.js';
import { TargetRegistry } from './TargetRegistry.js';
import {
  MASCOT_EGG_EVENT,
  formatEggText,
  pickEasterEgg,
} from '../MascotEasterEgg.jsx';
import { resolveRouteBehavior } from './config/behaviors.js';

function computeLayout() {
  if (typeof window === 'undefined') {
    return { size: { w: 220, h: 260 }, viewport: { w: 1280, h: 800 } };
  }
  const viewport = { w: window.innerWidth, h: window.innerHeight };
  const width = viewport.w;
  const size =
    width < 760 ? { w: 164, h: 196 } : width < 1100 ? { w: 200, h: 238 } : { w: 220, h: 260 };
  return { size, viewport };
}

function fallbackRest(layout) {
  return {
    x: 20,
    y: Math.max(96, layout.viewport.h - layout.size.h - 16),
  };
}

export default function MascotOverlay({ pathname, settings, onFail }) {
  const [layout, setLayout] = useState(computeLayout);
  const layoutRef = useRef(layout);
  const [pose, setPose] = useState(() => ({
    ...fallbackRest(computeLayout()),
    facing: REST_YAW,
    duration: 0,
    ready: true,
  }));
  const [mascotState, setMascotState] = useState('idle');
  const [bubble, setBubble] = useState(null);
  const [hovered, setHovered] = useState(false);
  const [gesture, setGesture] = useState(0);
  const [failed, setFailed] = useState(false);

  const tapCountRef = useRef(0);
  const eggTimerRef = useRef(null);
  const brainRef = useRef(null);
  const registryRef = useRef(null);
  const settingsRef = useRef(settings);
  const pathnameRef = useRef(pathname);
  const lastRouteRef = useRef(null);

  useEffect(() => {
    settingsRef.current = settings;
    pathnameRef.current = pathname;
  }, [settings, pathname]);

  useEffect(() => {
    const registry = new TargetRegistry({
      onChange: () => brainRef.current?.sync(),
      onHover: (type, target) => {
        if (type === 'enter') brainRef.current?.hoverTarget(target.id);
        else brainRef.current?.unhoverTarget(target.id);
      },
    });
    registryRef.current = registry;
    registry.start();

    const brain = new MascotBrain({
      registry,
      getLayout: () => layoutRef.current,
      reducedMotion: settingsRef.current.reducedMotion,
      lowPower: settingsRef.current.lowPower,
      onPose: setPose,
      onBubble: setBubble,
      onState: setMascotState,
      onGesture: (type = 'wave') => setGesture(`${type}-${Date.now()}`),
    });
    brainRef.current = brain;

    if (import.meta.env.DEV) {
      window.__parallaxMascot = { brain, registry };
    }

    const initial =
      registry.findRestSpot(layoutRef.current.size, layoutRef.current.viewport) ||
      fallbackRest(layoutRef.current);
    setPose({ ...initial, facing: REST_YAW, duration: 0, ready: true });
    brain.start(pathnameRef.current);

    const onVisibility = () => brain.setPaused(document.hidden);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      brain.destroy();
      registry.destroy();
      brainRef.current = null;
      registryRef.current = null;
      if (import.meta.env.DEV) delete window.__parallaxMascot;
    };
  }, []);

  useEffect(() => {
    if (!brainRef.current) return undefined;
    if (lastRouteRef.current === null) {
      lastRouteRef.current = pathname;
      return undefined;
    }
    if (lastRouteRef.current === pathname) return undefined;
    lastRouteRef.current = pathname;
    brainRef.current.setRoute(pathname);
    const timer = setTimeout(() => registryRef.current?.refresh(), 350);
    return () => clearTimeout(timer);
  }, [pathname]);

  useEffect(() => {
    brainRef.current?.setSettings({
      reducedMotion: settings.reducedMotion,
      lowPower: settings.lowPower,
    });
  }, [settings.reducedMotion, settings.lowPower]);

  useEffect(() => {
    let timer = 0;

    const update = () => {
      const next = computeLayout();
      layoutRef.current = next;
      setLayout(next);
      registryRef.current?.refresh();
      brainRef.current?.setLayout();
    };

    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(update, 180);
    };

    window.addEventListener('resize', schedule);
    window.addEventListener('orientationchange', schedule);
    window.visualViewport?.addEventListener('resize', schedule);

    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', schedule);
      window.removeEventListener('orientationchange', schedule);
      window.visualViewport?.removeEventListener('resize', schedule);
    };
  }, []);

  useEffect(
    () => () => {
      if (eggTimerRef.current) clearTimeout(eggTimerRef.current);
    },
    [],
  );

  const speakEgg = useCallback(() => {
    const text = formatEggText(pickEasterEgg());
    if (brainRef.current) {
      brainRef.current.say(text, 'user', 7500);
      return;
    }
    setBubble({ text });
    if (eggTimerRef.current) clearTimeout(eggTimerRef.current);
    eggTimerRef.current = setTimeout(() => setBubble(null), 7500);
  }, []);

  // Keyboard ("midhun", arrows) and swipe triggers from the provider.
  useEffect(() => {
    window.addEventListener(MASCOT_EGG_EVENT, speakEgg);
    return () => window.removeEventListener(MASCOT_EGG_EVENT, speakEgg);
  }, [speakEgg]);

  // Four taps on the guide turn the usual reaction into an easter egg.
  const handleMascotTap = () => {
    brainRef.current?.interact();
    tapCountRef.current += 1;
    if (tapCountRef.current < 4) return;

    tapCountRef.current = 0;
    speakEgg();
  };

  const handleFail = () => {
    setFailed(true);
    onFail?.();
  };

  if (failed) return null;

  const active = Boolean(resolveRouteBehavior(pathname));
  const { size, viewport } = layout;
  const bubbleSide = pose.y < 150 ? 'below' : 'above';
  const centerX = pose.x + size.w / 2;
  const bubbleAlign = centerX < 180 ? 'left' : centerX > viewport.w - 180 ? 'right' : 'center';
  const canvasPaused = !active || mascotState === 'hidden';

  return (
    <div className={`mascot-layer${active ? '' : ' is-off'}`} data-state={mascotState}>
      <div
        className={`mascot-anchor${pose.ready ? ' is-ready' : ''}`}
        style={{
          width: `${size.w}px`,
          height: `${size.h}px`,
          transform: `translate3d(${pose.x}px, ${pose.y}px, 0)`,
          transitionDuration: `${pose.duration || 0}ms`,
        }}
      >
        <div className={`mascot-float${hovered ? ' is-hovered' : ''}`}>
          <MascotCanvas
            facing={pose.facing}
            state={mascotState}
            gesture={gesture}
            paused={canvasPaused}
            reducedMotion={settings.reducedMotion}
            lowPower={settings.lowPower}
            dprCap={settings.lowPower ? 1 : viewport.w < 760 ? 1.25 : 1.5}
            onFail={handleFail}
          />

          <SpeechBubble bubble={bubble} side={bubbleSide} align={bubbleAlign} />

          <div
            className="mascot-hit"
            aria-hidden="true"
            onClick={handleMascotTap}
            onPointerEnter={() => setHovered(true)}
            onPointerLeave={() => setHovered(false)}
          />

          <button
            type="button"
            className="mascot-hide"
            onClick={() => settings.setHidden(true)}
            aria-label="Hide the Analogue Interface"
            title="Hide guide"
          >
            <X size={12} strokeWidth={2.4} aria-hidden="true" />
          </button>
        </div>
      </div>

    </div>
  );
}
