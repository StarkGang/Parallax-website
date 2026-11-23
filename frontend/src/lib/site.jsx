import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { publicApi } from './api.js';

const SiteContext = createContext(null);
const CACHE_CONFIG_KEY = 'px_cached_config';
const CACHE_EDITION_KEY = 'px_cached_edition';

function getCached(key) {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const data = JSON.parse(raw);
    // Only a real database row is usable: an entry without an id cannot address
    // any API route, so treat it as absent instead of caching a broken shape.
    if (key === CACHE_EDITION_KEY && !data?.id) {
      sessionStorage.removeItem(key);
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

function setCached(key, value) {
  try {
    if (key === CACHE_EDITION_KEY && !value?.id) return;
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Storage can be full or blocked; the in-memory state still works. */
  }
}

export function SiteProvider({ children }) {
  const [config, setConfig] = useState(() => getCached(CACHE_CONFIG_KEY));
  const cachedEdition = getCached(CACHE_EDITION_KEY);
  const [edition, setEdition] = useState(cachedEdition);
  const [loading, setLoading] = useState(!cachedEdition);
  const [error, setError] = useState(null);
  // Only a real payload from a successful API read counts as verified. There is
  // deliberately no hardcoded stand-in edition: a made-up UUID or price could
  // reach a staff mutation or be shown to a visitor as real convention data.
  const [editionVerified, setEditionVerified] = useState(Boolean(cachedEdition));
  const [editionError, setEditionError] = useState(null);
  const [nonce, setNonce] = useState(0);

  const editionRef = useRef(edition);
  editionRef.current = edition;
  const configRef = useRef(config);
  configRef.current = config;

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    let alive = true;
    setError(null);
    setEditionError(null);
    if (!editionRef.current) setLoading(true);

    // The edition is required to render routes, so it gets a few automatic
    // retries while the API is waking up, then a slug lookup as a second path.
    // The branding/config document is optional and must never block the site.
    const acceptEdition = (data) => {
      setEdition(data);
      editionRef.current = data;
      setCached(CACHE_EDITION_KEY, data);
      setEditionVerified(true);
      setEditionError(null);
      setLoading(false);
    };

    const loadEdition = async () => {
      let lastError = null;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const body = await publicApi.edition();
          if (!alive) return;
          if (body?.data) {
            acceptEdition(body.data);
            return;
          }
        } catch (err) {
          if (!alive) return;
          lastError = err;
          // A permanent validation error will not heal itself, but a cold
          // database or gateway does. Retry regardless and let the fallbacks
          // below decide what to show.
          if (attempt < 2) {
            await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));
            if (!alive) return;
          }
        }
      }

      // Direct slug lookup: the catalogue endpoint can resolve an edition even
      // when the "current" resolver is briefly unavailable.
      const cached = getCached(CACHE_EDITION_KEY);
      const slugs = [cached?.slug, configRef.current?.editionSlug].filter(
        (slug, index, list) => Boolean(slug) && list.indexOf(slug) === index,
      );
      for (const slug of slugs) {
        try {
          const body = await publicApi.editionBySlug(slug);
          if (!alive) return;
          if (body?.data) {
            acceptEdition(body.data);
            return;
          }
        } catch {
          /* try the next slug */
        }
      }

      if (!alive) return;
      setLoading(false);

      // A previously loaded edition is still better than a blocked console: the
      // user keeps an operational site while the refresh resolves in the
      // background (site.refresh).
      if (editionRef.current) {
        setEditionVerified(true);
        setEditionError(lastError);
        return;
      }

      setEditionVerified(false);
      setEditionError(lastError);
      // Nothing has ever loaded: expose a retry screen instead of inventing an
      // edition with made-up prices. Pages only render once real data exists.
      setError(lastError);
    };

    const loadConfig = async () => {
      try {
        const body = await publicApi.config();
        if (!alive || !body) return;
        setConfig(body);
        setCached(CACHE_CONFIG_KEY, body);
        if (body.razorpayKeyId && typeof window !== 'undefined') {
          window.__RAZORPAY_KEY_ID__ = body.razorpayKeyId;
        }
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
      editionVerified,
      editionError,
      refresh,
      slug: edition?.slug || null,
      editionId: edition?.id || null,
    }),
    [config, edition, loading, error, editionVerified, editionError, refresh],
  );

  return <SiteContext.Provider value={value}>{children}</SiteContext.Provider>;
}

export function useSite() {
  const ctx = useContext(SiteContext);
  if (!ctx) throw new Error('useSite must be used inside SiteProvider');
  return ctx;
}
