import React, { Component, useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Inbox, LoaderCircle, X } from 'lucide-react';

export function Eyebrow({ children, className = '' }) {
  return (
    <div className={`eyebrow ${className}`.trim()}>
      {children}
    </div>
  );
}

export function PageTitle({ kicker, title, desc, aside }) {
  return (
    <section className="page-title">
      <div className="page-title-inner">
        <div>
          <Eyebrow>{kicker}</Eyebrow>
          <h1>{title}</h1>
          {desc ? <p>{desc}</p> : null}
        </div>
        {aside ? <div className="page-title-aside">{aside}</div> : null}
      </div>
    </section>
  );
}

export function SectionHead({ kicker, title, action }) {
  return (
    <div className="section-heading">
      <div>
        {kicker ? <Eyebrow>{kicker}</Eyebrow> : null}
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

export function Button({
  to,
  href,
  variant = 'primary',
  icon: Icon,
  children,
  className = '',
  type = 'button',
  ...rest
}) {
  const inner = (
    <>
      <span>{children}</span>
      {Icon ? (
        <span className="btn-ico">
          <Icon size={14} strokeWidth={1.6} aria-hidden="true" />
        </span>
      ) : null}
    </>
  );
  const cls = `button ${variant} ${className}`.trim();
  if (to) {
    return (
      <Link to={to} className={cls} {...rest}>
        {inner}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} className={cls} {...rest}>
        {inner}
      </a>
    );
  }
  return (
    <button type={type} className={cls} {...rest}>
      {inner}
    </button>
  );
}

export function Panel({ children, className = '', padded = true, ...rest }) {
  return (
    <div className={`bezel ${className}`.trim()} {...rest}>
      <div className={`bezel-core ${padded ? 'is-padded' : ''}`.trim()}>{children}</div>
    </div>
  );
}

export function Stat({ label, value, note, tone = '' }) {
  return (
    <div className={`stat-card ${tone}`.trim()}>
      <span>{label}</span>
      <b>{value}</b>
      {note ? <small>{note}</small> : null}
    </div>
  );
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={`badge ${tone}`.trim()}>{children}</span>;
}

export function StatusBadge({ status }) {
  const value = String(status || '').toLowerCase();
  const good = ['active', 'verified', 'confirmed', 'paid', 'admitted', 'published', 'open'];
  const warn = ['pending', 'reserved', 'created', 'draft', 'forming', 'unverified'];
  const bad = ['cancelled', 'rejected', 'revoked', 'failed', 'suspended', 'closed', 'disbanded'];
  const tone = good.includes(value) ? 'good' : warn.includes(value) ? 'warn' : bad.includes(value) ? 'bad' : 'neutral';
  return <Badge tone={tone}>{value ? value.replace(/_/g, ' ') : 'unknown'}</Badge>;
}

export function Loading({ label = 'Loading', rows = 2 }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <LoaderCircle className="spin" size={18} strokeWidth={1.6} />
      <span>{label}</span>
      <span className="sr-only">Please wait</span>
      {rows > 0 ? (
        <div className="skeleton-stack" aria-hidden="true">
          {Array.from({ length: rows }).map((_, index) => (
            <div className="skeleton" key={index} style={{ animationDelay: `${index * 90}ms` }} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ErrorBox({ error, onRetry, title = 'That did not load' }) {
  return (
    <div className="state-box error" role="alert">
      <AlertTriangle size={20} strokeWidth={1.6} />
      <div>
        <h3>{title}</h3>
        <p>{error?.message || 'The server could not complete that request.'}</p>
        {error?.code ? <code>{error.code}</code> : null}
      </div>
      {onRetry ? (
        <Button variant="ghost" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Empty({ title = 'Nothing here yet', desc, children }) {
  return (
    <div className="state-box empty">
      <Inbox size={22} strokeWidth={1.4} />
      <div>
        <h3>{title}</h3>
        {desc ? <p>{desc}</p> : null}
      </div>
      {children}
    </div>
  );
}

export function Field({ label, hint, children, className = '' }) {
  return (
    <label className={`field ${className}`.trim()}>
      <span>{label}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}

export function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="toggle-track" aria-hidden="true" />
      <span className="toggle-copy">
        <b>{label}</b>
        {hint ? <small>{hint}</small> : null}
      </span>
    </label>
  );
}

export function InlineMessage({ tone = 'info', children }) {
  return (
    <p className={`inline-message ${tone}`.trim()} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </p>
  );
}

export function DataTable({ head, children, empty }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {head.map((cell) => (
              <th key={cell} scope="col">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {empty ? <div className="table-empty">{empty}</div> : null}
    </div>
  );
}


export class SheetErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error('Sheet render error:', error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '24px', color: '#f87171', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '12px', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <h3 style={{ margin: '0 0 8px', color: '#fca5a5' }}>Failed to render sheet contents</h3>
          <p style={{ margin: '0 0 12px', fontSize: '13px', color: '#fecaca' }}>{this.state.error?.message || 'Unknown error occurred while rendering the form.'}</p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{ padding: '6px 14px', background: '#ef4444', color: '#fff', border: 0, borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}
          >
            Retry form
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export class AdminErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("Admin error boundary caught error:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "32px", maxWidth: "600px", margin: "40px auto", background: "rgba(239, 68, 68, 0.08)", borderRadius: "16px", border: "1px solid rgba(239, 68, 68, 0.25)", color: "#fecaca" }}>
          <h2 style={{ margin: "0 0 10px", color: "#fca5a5", fontSize: "18px" }}>Module Encountered an Issue</h2>
          <p style={{ margin: "0 0 16px", fontSize: "14px", lineHeight: "1.5" }}>{this.state.error?.message || "An unexpected error occurred while loading this admin section."}</p>
          <button
            type="button"
            onClick={() => {
              clearAsyncCache();
              this.setState({ hasError: false, error: null });
            }}
            style={{ padding: "8px 18px", background: "#ef4444", color: "#fff", border: 0, borderRadius: "8px", cursor: "pointer", fontSize: "13px", fontWeight: 600 }}
          >
            Retry Module
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.reset = this.reset.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Page render error:', error, errorInfo);
  }

  reset() {
    // A stale cached payload is the usual cause; drop it and render again.
    clearAsyncCache();
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <section className="section" role="alert">
        <div className="state-box error">
          <AlertTriangle size={20} strokeWidth={1.6} />
          <div>
            <h3>This page could not be displayed</h3>
            <p>{this.state.error?.message || 'An unexpected error interrupted the page.'}</p>
          </div>
          <div className="banner-actions">
            <Button variant="ghost" onClick={this.reset}>
              Try again
            </Button>
            <Button to="/">Back to home</Button>
          </div>
        </div>
      </section>
    );
  }
}

export function Sheet({ open, title, onClose, children, wide = false }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    if (window.__lenis) window.__lenis.stop();
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
      if (window.__lenis) window.__lenis.start();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className={`modal sheet ${wide ? 'wide' : ''}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="sheet-head">
          <div>
            <Eyebrow>ADMIN ACTION</Eyebrow>
            <h2>{title}</h2>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <X size={18} strokeWidth={1.6} />
          </button>
        </header>
        <div className="sheet-body" data-lenis-prevent><SheetErrorBoundary>{children}</SheetErrorBoundary></div>
      </section>
    </div>
  );
}

const ASYNC_CACHE = new Map();
const INFLIGHT = new Map();
const CACHE_LIMIT = 150;

export function clearAsyncCache() {
  ASYNC_CACHE.clear();
  INFLIGHT.clear();
}

/**
 * Two call sites with the same dependency values (for example every participant
 * widget keyed by `[editionId]`) must not share a cache slot. The loader's own
 * source identifies the endpoint; the dependencies identify the variant.
 */
function loaderSignature(loader) {
  const source =
    typeof loader === 'function' ? Function.prototype.toString.call(loader) : String(loader);
  let hash = 5381;
  for (let index = 0; index < source.length; index += 1) {
    hash = ((hash << 5) + hash + source.charCodeAt(index)) | 0;
  }
  return `${source.length.toString(36)}.${(hash >>> 0).toString(36)}`;
}

function readCache(key, ttlMs) {
  if (!key) return null;
  const entry = ASYNC_CACHE.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > ttlMs) {
    ASYNC_CACHE.delete(key);
    return null;
  }
  // Refresh recency so the oldest unused entry is evicted first.
  ASYNC_CACHE.delete(key);
  ASYNC_CACHE.set(key, entry);
  return entry;
}

function writeCache(key, data) {
  if (!key) return;
  if (ASYNC_CACHE.has(key)) ASYNC_CACHE.delete(key);
  if (ASYNC_CACHE.size >= CACHE_LIMIT) {
    const oldest = ASYNC_CACHE.keys().next().value;
    if (oldest !== undefined) ASYNC_CACHE.delete(oldest);
  }
  ASYNC_CACHE.set(key, { data, timestamp: Date.now() });
}

function loadShared(key, loader) {
  const pending = INFLIGHT.get(key);
  if (pending) return pending;
  const request = Promise.resolve()
    .then(() => loader())
    .finally(() => {
      if (INFLIGHT.get(key) === request) INFLIGHT.delete(key);
    });
  INFLIGHT.set(key, request);
  return request;
}

export function useAsync(loader, deps = [], { enabled = true, ttlMs = 60000 } = {}) {
  const cacheKey = enabled ? `${loaderSignature(loader)}|${JSON.stringify(deps)}` : null;
  const [reloadToken, setReloadToken] = useState(0);
  const forceRef = useRef(false);

  const [state, setState] = useState(() => {
    const cached = cacheKey ? readCache(cacheKey, ttlMs) : null;
    return {
      key: cacheKey,
      loading: Boolean(enabled) && !cached,
      data: cached ? cached.data : null,
      error: null,
    };
  });

  const reload = useCallback(() => {
    forceRef.current = true;
    setReloadToken((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled || !cacheKey) {
      setState({ key: cacheKey, loading: false, data: null, error: null });
      return undefined;
    }

    let alive = true;
    const forced = forceRef.current;
    forceRef.current = false;
    const cached = forced ? null : readCache(cacheKey, ttlMs);

    setState((previous) => {
      const data = cached ? cached.data : previous.key === cacheKey ? previous.data : null;
      return { key: cacheKey, loading: !data, data, error: null };
    });

    loadShared(cacheKey, loader)
      .then((data) => {
        writeCache(cacheKey, data);
        if (alive) setState({ key: cacheKey, loading: false, data, error: null });
      })
      .catch((error) => {
        if (!alive) return;
        setState((previous) => ({
          key: cacheKey,
          loading: false,
          data: previous.key === cacheKey ? previous.data : null,
          error: previous.key === cacheKey && previous.data ? null : error,
        }));
      });

    return () => {
      alive = false;
    };
    // The cache key already encodes the loader signature and the dependency values.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, enabled, reloadToken]);

  const effective =
    state.key === cacheKey
      ? state
      : { key: cacheKey, loading: Boolean(enabled), data: null, error: null };

  return { loading: effective.loading, data: effective.data, error: effective.error, reload };
}

export function useDebounced(value, delay = 320) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function FieldGrid({ children }) {
  return <div className="field-grid">{children}</div>;
}
