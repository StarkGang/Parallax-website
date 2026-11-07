import { Component, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { useMascotSettings } from './useMascotSettings.js';
import { resolveRouteBehavior } from './config/behaviors.js';
import { attachEggTriggers } from './eggTriggers.js';
import { MASCOT_EGG_EVENT } from '../MascotEasterEgg.jsx';
import './mascot.css';

const importOverlay = () => import('./MascotOverlay.jsx');

function canUseWebGL() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    return Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext('webgl2') || canvas.getContext('webgl')),
    );
  } catch {
    return false;
  }
}

class MascotBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError?.();
  }

  render() {
    if (this.state.failed) return null;
    return this.props.children;
  }
}

/**
 * Owns the single mascot instance. It survives route changes (the overlay is
 * mounted once), loads after first paint, and unloads completely when hidden.
 */
export default function MascotProvider() {
  const { pathname } = useLocation();
  const settings = useMascotSettings();
  const [supported] = useState(canUseWebGL);
  const [failed, setFailed] = useState(false);
  const [Overlay, setOverlay] = useState(null);
  const routeEnabled = Boolean(resolveRouteBehavior(pathname));

  // Fun triggers live here so they keep working even while the 3D chunk is
  // still loading; whoever is on screen answers the event.
  useEffect(() => {
    return attachEggTriggers(() => {
      window.dispatchEvent(new CustomEvent(MASCOT_EGG_EVENT, { detail: { source: 'trigger' } }));
    });
  }, []);

  useEffect(() => {
    if (!supported || failed || settings.hidden || Overlay || !routeEnabled) {
      return undefined;
    }

    let cancelled = false;
    let idleId = 0;
    let timerId = 0;

    const load = () => {
      importOverlay()
        .then((module) => {
          if (!cancelled) setOverlay(() => module.default);
        })
        .catch(() => {
          if (!cancelled) setFailed(true);
        });
    };

    const connection =
      typeof navigator !== 'undefined' ? navigator.connection : null;
    const slowConnection =
      Boolean(connection?.saveData) ||
      ['slow-2g', '2g'].includes(connection?.effectiveType);

    // Defer the 3D chunk until after first paint and idle time. Save-data and
    // slow connections wait longer before spending bytes on the mascot.
    timerId = window.setTimeout(
      () => {
        if (typeof window.requestIdleCallback === 'function') {
          idleId = window.requestIdleCallback(load, { timeout: 2200 });
        } else {
          load();
        }
      },
      slowConnection ? 5000 : 350,
    );

    return () => {
      cancelled = true;
      clearTimeout(timerId);
      if (idleId) window.cancelIdleCallback?.(idleId);
    };
  }, [supported, failed, settings.hidden, Overlay, routeEnabled]);

  if (!supported || failed) return null;

  if (settings.hidden) {
    if (!routeEnabled) return null;
    return (
      <button
        type="button"
        className="mascot-show"
        onClick={() => settings.setHidden(false)}
        aria-label="Show the Analogue Interface"
      >
        <span className="mascot-show-icon" aria-hidden="true">
          <Sparkles size={13} strokeWidth={1.8} />
        </span>
        <span className="mascot-show-label">Guide</span>
      </button>
    );
  }

  if (!Overlay) return null;

  return (
    <MascotBoundary onError={() => setFailed(true)}>
      <Overlay
        pathname={pathname}
        settings={settings}
        onFail={() => setFailed(true)}
      />
    </MascotBoundary>
  );
}
