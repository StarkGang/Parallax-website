import { useEffect, useState } from 'react';
import { LayoutGrid } from 'lucide-react';

const DEFAULT_COLS = { mobile: 2, tablet: 2, desktop: 4 };
const COL_OPTIONS = {
  mobile: [1, 2, 3],
  tablet: [2, 3, 4],
  desktop: [2, 3, 4],
};

function getViewportTier() {
  if (typeof window === 'undefined') return 'desktop';
  if (window.matchMedia('(max-width: 639px)').matches) return 'mobile';
  if (window.matchMedia('(max-width: 1279px)').matches) return 'tablet';
  return 'desktop';
}

function readStoredCols(storageKey) {
  if (typeof window === 'undefined') return { ...DEFAULT_COLS };
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return { ...DEFAULT_COLS };
    const parsed = JSON.parse(raw);
    return {
      mobile: COL_OPTIONS.mobile.includes(parsed?.mobile) ? parsed.mobile : DEFAULT_COLS.mobile,
      tablet: COL_OPTIONS.tablet.includes(parsed?.tablet) ? parsed.tablet : DEFAULT_COLS.tablet,
      desktop: COL_OPTIONS.desktop.includes(parsed?.desktop) ? parsed.desktop : DEFAULT_COLS.desktop,
    };
  } catch {
    return { ...DEFAULT_COLS };
  }
}

/**
 * Responsive per-device column preference for `.exc-grid` event catalogues.
 * Defaults to 2 cards per row on mobile/tablet and 4 on desktop.
 */
export function useEventGridColumns(storageKey = 'parallax.events.cols.v1') {
  const [viewportTier, setViewportTier] = useState(getViewportTier);
  const [colsByTier, setColsByTier] = useState(() => readStoredCols(storageKey));

  useEffect(() => {
    const updateTier = () => setViewportTier(getViewportTier());
    updateTier();
    window.addEventListener('resize', updateTier);
    return () => window.removeEventListener('resize', updateTier);
  }, []);

  const colOptions = COL_OPTIONS[viewportTier];
  const activeCols = colsByTier[viewportTier] ?? DEFAULT_COLS[viewportTier];

  const handleColsChange = (nextCols) => {
    setColsByTier((prev) => {
      const updated = { ...prev, [viewportTier]: nextCols };
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(updated));
      } catch {
        // Ignore storage errors in private browsing.
      }
      return updated;
    });
  };

  return { activeCols, colOptions, handleColsChange };
}

/** Compact segmented control for adjusting cards per row on `.exc-grid`. */
export function EventsColumnsPicker({ activeCols, colOptions, onChange }) {
  return (
    <div className="exc-cols-picker" role="group" aria-label="Cards per row">
      <span className="exc-cols-label">
        <LayoutGrid size={12} strokeWidth={1.8} aria-hidden="true" />
        <span>Per row</span>
      </span>
      <div className="exc-cols-pills">
        {colOptions.map((n) => (
          <button
            key={n}
            type="button"
            className={`exc-cols-btn${activeCols === n ? ' is-active' : ''}`}
            aria-pressed={activeCols === n}
            onClick={() => onChange(n)}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

