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

export function SiteProvider({ children }) {
  const [config, setConfig] = useState(() => getCached(CACHE_CONFIG_KEY));
  const [edition, setEdition] = useState(() => getCached(CACHE_EDITION_KEY));
  const [loading, setLoading] = useState(() => !getCached(CACHE_EDITION_KEY));
  const [error, setError] = useState(null);
  const [nonce, setNonce] = useState(0);

  const editionRef = useRef(edition);
  editionRef.current = edition;

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
          if (!editionRef.current) setError(err);
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
