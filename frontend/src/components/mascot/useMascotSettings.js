import { useCallback, useEffect, useState } from 'react';
import { MASCOT_STORAGE_KEY } from './config/behaviors.js';

function readHidden() {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(MASCOT_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function readReducedMotion() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function readLowPower() {
  if (typeof navigator === 'undefined') return false;
  try {
    const saveData = Boolean(navigator.connection?.saveData);
    const cores = navigator.hardwareConcurrency || 8;
    const memory = navigator.deviceMemory || 8;
    return saveData || cores <= 4 || memory <= 4;
  } catch {
    return false;
  }
}

/**
 * Persistent mascot preferences. Hiding the guide unloads the 3D renderer;
 * showing it mounts a fresh one (the GLB itself is served from HTTP cache).
 */
export function useMascotSettings() {
  const [hidden, setHiddenState] = useState(readHidden);
  const [reducedMotion, setReducedMotion] = useState(readReducedMotion);
  const [lowPower, setLowPower] = useState(readLowPower);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => setReducedMotion(query.matches);
    query.addEventListener?.('change', sync);
    return () => query.removeEventListener?.('change', sync);
  }, []);

  useEffect(() => {
    setLowPower(readLowPower());
  }, []);

  const setHidden = useCallback((value) => {
    setHiddenState(Boolean(value));
    try {
      window.localStorage.setItem(MASCOT_STORAGE_KEY, value ? '1' : '0');
    } catch {
      /* storage can be unavailable in private modes */
    }
  }, []);

  return { hidden, setHidden, reducedMotion, lowPower };
}
