export const MASCOT_SAY_EVENT = 'parallax:mascot-say';

/**
 * Ask the 3D guide to speak a contextual line immediately.
 * Safe no-op when the guide is hidden or not mounted (e.g. /portal, /manage).
 */
export function mascotSay(text, ttl = 5200, gesture = null) {
  if (typeof window === 'undefined' || !text) return;
  window.dispatchEvent(
    new CustomEvent(MASCOT_SAY_EVENT, {
      detail: { text: String(text), ttl, gesture },
    }),
  );
}

