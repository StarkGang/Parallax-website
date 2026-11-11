import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { publicApi } from './api.js';

const SiteContext = createContext(null);
const CACHE_CONFIG_KEY = 'px_cached_config';
const CACHE_EDITION_KEY = 'px_cached_edition';

function getCached(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function setCached(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Storage can be full or blocked; the in-memory state still works. */
  }
}

export const FALLBACK_EDITION = {
  id: '00000000-0000-0000-0000-000000000001',
  slug: 'parallax-2027',
  name: 'Parallax 2027',
  tagline: 'A Shift in Perspective',
  organizer: "ISTE Students' Chapter",
  host: 'NSS College of Engineering',
  venue: 'NSSCE Campus',
  city: 'Palakkad, Kerala',
  timezone: 'Asia/Kolkata',
  startsAt: '2027-01-08T09:00:00+05:30',
  endsAt: '2027-01-09T18:00:00+05:30',
  registrationOpensAt: '2026-11-15T00:00:00+05:30',
  registrationClosesAt: '2026-11-30T23:59:59+05:30',
  status: 'published',
  contactEmail: 'iste@nssce.ac.in',
  branding: {},
  policy: {
    passPricePaise: 50000,
    lunchIncludedDays: ['Day 1', 'Day 2'],
    includedEventCount: 3,
    includedSelectionMode: 'free_choice',
    capInclusive: false,
    addonRequiresPass: true,
    teamMembersRequirePass: false,
    teamFeeBasisDefault: 'per_team',
    holdMinutes: 15,
    policyVersion: 1,
  },
  registrationOpen: true,
};

export function SiteProvider({ children }) {
  const [config, setConfig] = useState(() => getCached(CACHE_CONFIG_KEY));
  const [edition, setEdition] = useState(() => getCached(CACHE_EDITION_KEY) || FALLBACK_EDITION);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [nonce, setNonce] = useState(0);

  const editionRef = useRef(edition);
  // Keep the guard ref in sync after commit rather than mutating it in render.
  useEffect(() => {
    editionRef.current = edition;
  }, [edition]);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    let alive = true;
    setError(null);
    if (!editionRef.current) setLoading(true);

    // The edition is required to render routes, so it gets one automatic retry.
    // The branding/config document is optional and must never block the site.
    const loadEdition = async () => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const body = await publicApi.edition();
          if (!alive) return;
          if (body?.data) {
            setEdition(body.data);
            editionRef.current = body.data;
            setCached(CACHE_EDITION_KEY, body.data);
          }
          setLoading(false);
          return;
        } catch (err) {
          if (!alive) return;
          if (attempt === 0) {
            await new Promise((resolve) => setTimeout(resolve, 600));
            continue;
          }
          setLoading(false);
          if (!editionRef.current) {
            setEdition(FALLBACK_EDITION);
            editionRef.current = FALLBACK_EDITION;
          }
        }
      }
    };

    const loadConfig = async () => {
      try {
        const body = await publicApi.config();
        if (!alive || !body) return;
        setConfig(body);
        setCached(CACHE_CONFIG_KEY, body);
      } catch {
        /* Keep the last known configuration. Feature flags are optional. */
      }
    };

    loadEdition();
    loadConfig();

    return () => {
      alive = false;
    };
  }, [nonce]);

  const value = useMemo(
    () => ({
      config,
      edition,
      policy: edition?.policy || null,
      loading,
      error,
      refresh,
      slug: edition?.slug || null,
      editionId: edition?.id || null,
    }),
    [config, edition, loading, error, refresh],
  );

  return <SiteContext.Provider value={value}>{children}</SiteContext.Provider>;
}

export function useSite() {
  const ctx = useContext(SiteContext);
  if (!ctx) throw new Error('useSite must be used inside SiteProvider');
  return ctx;
}
