import { Component, useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  AlertTitle,
  Box,
  Button as MuiButton,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  Switch,
  Table,
  TableContainer,
  Typography,
} from '@mui/material';
import { styled } from '@mui/material/styles';
import { AlertTriangle, Inbox, X } from 'lucide-react';
import { ErrorPage } from './StatePages.jsx';

/** Pull a human message out of an API error, never surfacing raw JSON. */
export function readableError(error) {
  const fallback = 'The server could not complete that request.';
  const raw = error?.message;
  if (typeof raw !== 'string' || !raw.trim()) return fallback;

  const trimmed = raw.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed);
      const detail = parsed?.detail ?? parsed?.message ?? parsed?.error;
      if (typeof detail === 'string' && detail.trim()) return detail;
      if (Array.isArray(detail)) {
        const joined = detail
          .map((item) => (typeof item === 'string' ? item : item?.msg))
          .filter(Boolean)
          .join(', ');
        if (joined) return joined;
      }
    } catch {
      return fallback;
    }
    return fallback;
  }
  return raw;
}

export function Eyebrow({ children, className = '' }) {
  return (
    <div className={`eyebrow ${className}`.trim()}>
      {children}
    </div>
  );
}

const PARALLAX_DEPTH_BG = `${import.meta.env.BASE_URL}images/parallax-depth-bg.webp`;
const PARALLAX_MARK = `${import.meta.env.BASE_URL}images/parallax-vector.svg`;

export function PageTitle({ kicker, title, desc, aside }) {
  return (
    <section className="page-title tf-parallax-section">
      <div className="page-title-bg" aria-hidden="true">
        <img src={PARALLAX_DEPTH_BG} alt="" className="page-title-bg-img" />
        <div className="page-title-vignette" />
      </div>
      <div className="page-title-inner tf-parallax-fg">
        <div className="page-title-text">
          {kicker ? <Eyebrow>{kicker}</Eyebrow> : null}
          <h1>{title}</h1>
          {desc ? <p className="page-title-desc">{desc}</p> : null}
        </div>
        {aside ? <div className="page-title-aside">{aside}</div> : null}
      </div>
    </section>
  );
}

export function SectionHead({ kicker, title, subtitle, action }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px 16px',
        width: '100%',
        marginBottom: '8px',
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        {kicker ? <Eyebrow>{kicker}</Eyebrow> : null}
        <Typography variant="h3" component="h2" sx={{ mt: kicker ? 0.5 : 0 }}>
          {title}
        </Typography>
        {subtitle ? (
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            {subtitle}
          </Typography>
        ) : null}
      </Box>
      {action ? <Box sx={{ flexShrink: 0 }}>{action}</Box> : null}
    </div>
  );
}

const VARIANT_MAP = {
  primary: { variant: 'contained', color: 'primary' },
  secondary: { variant: 'contained', color: 'secondary' },
  danger: { variant: 'contained', color: 'error' },
  ghost: { variant: 'outlined', color: 'inherit' },
  light: {
    variant: 'contained',
    color: 'inherit',
    sx: { backgroundColor: '#f4f6fb', color: '#06080e', '&:hover': { backgroundColor: '#ffffff' } },
  },
};

export function Button({
  to,
  href,
  variant = 'primary',
  icon: Icon,
  loading = false,
  disabled,
  children,
  className = '',
  type = 'button',
  size = 'small',
  sx,
  ...rest
}) {
  const map = VARIANT_MAP[variant] || VARIANT_MAP.primary;
  const linkProps = to ? { component: Link, to } : href ? { component: 'a', href } : { type };
  // A loading button stays readable: block the click instead of greying it out.
  const busyProps = loading ? { sx: { pointerEvents: 'none' } } : {};

  return (
    <MuiButton
      {...map}
      size={size}
      className={className}
      disabled={disabled}
      endIcon={
        !loading && Icon ? <Icon size={14} strokeWidth={1.8} aria-hidden="true" /> : undefined
      }
      startIcon={
        loading ? (
          <CircularProgress size={13} thickness={5} color="inherit" aria-hidden="true" />
        ) : undefined
      }
      sx={{ ...(map.sx || {}), ...(sx || {}), ...(busyProps.sx || {}) }}
      aria-busy={loading || undefined}
      {...linkProps}
      {...rest}
    >
      {children}
    </MuiButton>
  );
}

const PanelSurface = styled(Paper)(({ theme }) => ({
  position: 'relative',
  border: `1px solid ${theme.palette.divider}`,
  borderRadius: 18,
  backgroundColor: theme.palette.background.paper,
  backgroundImage:
    'radial-gradient(circle at 100% 0%, rgba(124, 92, 255, 0.09), transparent 45%)',
  boxShadow: '0 1px 0 rgba(255,255,255,0.03) inset',
  overflow: 'hidden',
}));

export function Panel({ children, className = '', padded = true, sx, ...rest }) {
  return (
    <PanelSurface
      elevation={0}
      variant="outlined"
      className={className}
      sx={{ p: padded ? 2.5 : 0, ...(sx || {}) }}
      {...rest}
    >
      {children}
    </PanelSurface>
  );
}

export function Stat({ label, value, note, tone = '' }) {
  const accent =
    tone === 'warn' ? '#fbbf24' : tone === 'good' ? '#3ddc97' : tone === 'bad' ? '#f87171' : null;

  return (
    <PanelSurface
      elevation={0}
      variant="outlined"
      sx={{
        display: 'flex',
        flexDirection: 'column',
        gap: 0.5,
        p: 2,
        minWidth: 0,
        borderColor: accent ? `color-mix(in srgb, ${accent} 40%, transparent)` : undefined,
      }}
    >
      <Typography
        variant="overline"
        component="span"
        sx={{ color: 'text.secondary', fontSize: '0.6rem' }}
      >
        {label}
      </Typography>
      <Box
        component="b"
        sx={{
          fontFamily: 'var(--display, inherit)',
          fontSize: '1.5rem',
          lineHeight: 1.1,
          letterSpacing: '-0.02em',
          color: accent || 'text.primary',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {value}
      </Box>
      {note ? (
        <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem' }}>
          {note}
        </Typography>
      ) : null}
    </PanelSurface>
  );
}

const BADGE_TONES = {
  good: { color: '#3ddc97', bg: 'rgba(61, 220, 151, 0.12)', border: 'rgba(61, 220, 151, 0.32)' },
  warn: { color: '#fbbf24', bg: 'rgba(251, 191, 36, 0.12)', border: 'rgba(251, 191, 36, 0.32)' },
  bad: { color: '#f87171', bg: 'rgba(248, 113, 113, 0.12)', border: 'rgba(248, 113, 113, 0.32)' },
  accent: { color: '#a58cff', bg: 'rgba(124, 92, 255, 0.16)', border: 'rgba(124, 92, 255, 0.38)' },
  muted: { color: '#93a4c6', bg: 'rgba(148, 170, 205, 0.08)', border: 'rgba(148, 170, 205, 0.24)' },
  neutral: { color: '#cbd5e1', bg: 'rgba(255, 255, 255, 0.05)', border: 'rgba(148, 170, 205, 0.26)' },
};

export function Badge({ tone = 'neutral', children }) {
  const style = BADGE_TONES[tone] || BADGE_TONES.neutral;
  return (
    <Chip
      size="small"
      variant="outlined"
      label={children}
      sx={{
        color: style.color,
        backgroundColor: style.bg,
        borderColor: style.border,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        fontSize: '0.65rem',
        height: 22,
        '& .MuiChip-label': { px: 1.1 },
      }}
    />
  );
}

export function StatusBadge({ status }) {
  const value = String(status || '').toLowerCase();
  const good = ['active', 'verified', 'confirmed', 'paid', 'admitted', 'published', 'open'];
  const warn = ['pending', 'reserved', 'created', 'draft', 'forming', 'unverified'];
  const bad = ['cancelled', 'rejected', 'revoked', 'failed', 'suspended', 'closed', 'disbanded'];
  const tone = good.includes(value) ? 'good' : warn.includes(value) ? 'warn' : bad.includes(value) ? 'bad' : 'neutral';
  return <Badge tone={tone}>{value ? value.replace(/_/g, ' ') : 'unknown'}</Badge>;
}

/**
 * Parallax loader: three credential plates fan apart in depth behind the brand
 * mark, and a shimmer row hints at the content that is still arriving. Pure
 * CSS so it stays at 60fps on low-end phones, and it settles to a static frame
 * when motion is reduced.
 */
export function Loading({ label = 'Loading', fullPage = false }) {
  return (
    <Box
      className={`px-loader${fullPage ? ' is-fullpage' : ''}`}
      role="status"
      aria-live="polite"
      sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2 }}
    >
      <img className="px-loader-logo" src={PARALLAX_MARK} alt="Parallax" />
      <div className="px-win-spinner" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      {label ? <span className="px-loader-label">{label}</span> : null}
      <span className="sr-only">Please wait</span>
    </Box>
  );
}

export function ErrorBox({ error, onRetry, title = 'That did not load' }) {
  return (
    <Alert
      severity="error"
      variant="outlined"
      icon={<AlertTriangle size={19} strokeWidth={1.7} />}
      action={
        onRetry ? (
          <Button variant="ghost" size="small" onClick={onRetry}>
            Try again
          </Button>
        ) : undefined
      }
      sx={{ alignItems: 'flex-start' }}
    >
      <AlertTitle sx={{ fontWeight: 700, fontSize: '0.875rem', mb: 0.25 }}>{title}</AlertTitle>
      <Typography variant="body2" sx={{ color: 'rgba(254, 202, 202, 0.9)' }}>
        {readableError(error)}
      </Typography>
      {error?.code ? (
        <Box
          component="code"
          sx={{ display: 'inline-block', mt: 0.5, fontSize: '0.7rem', opacity: 0.7 }}
        >
          {error.code}
        </Box>
      ) : null}
    </Alert>
  );
}

export function Empty({ title = 'Nothing here yet', desc, children }) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        gap: 1,
        px: 2.5,
        py: 4,
        borderRadius: 3,
        border: '1px dashed',
        borderColor: 'divider',
        backgroundColor: 'rgba(255,255,255,0.015)',
        color: 'text.secondary',
      }}
    >
      <Inbox size={24} strokeWidth={1.4} />
      <Typography variant="subtitle1" sx={{ color: 'text.primary' }}>
        {title}
      </Typography>
      {desc ? (
        <Typography variant="body2" sx={{ maxWidth: 420 }}>
          {desc}
        </Typography>
      ) : null}
      {children}
    </Box>
  );
}

export function Field({ label, hint, children, className = '' }) {
  return (
    <label className={`field ${className}`.trim()}>
      <Typography
        component="span"
        variant="overline"
        sx={{ display: 'block', color: 'text.secondary', fontSize: '0.6rem' }}
      >
        {label}
      </Typography>
      {children}
      {hint ? (
        <Typography component="small" variant="caption" sx={{ display: 'block', mt: 0.5 }}>
          {hint}
        </Typography>
      ) : null}
    </label>
  );
}

export function Toggle({ checked, onChange, label, hint }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        px: 1.75,
        py: 1,
        borderRadius: 2.5,
        border: '1px solid',
        borderColor: 'divider',
        backgroundColor: 'rgba(255,255,255,0.02)',
      }}
    >
      <Switch
        checked={Boolean(checked)}
        onChange={(event) => onChange(event.target.checked)}
        size="small"
        slotProps={{ input: { 'aria-label': label } }}
      />
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="subtitle2" component="b" sx={{ display: 'block' }}>
          {label}
        </Typography>
        {hint ? (
          <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
            {hint}
          </Typography>
        ) : null}
      </Box>
    </Box>
  );
}

const ALERT_SEVERITY = {
  info: 'info',
  success: 'success',
  warn: 'warning',
  warning: 'warning',
  error: 'error',
};

export function InlineMessage({ tone = 'info', children }) {
  return (
    <Alert
      severity={ALERT_SEVERITY[tone] || 'info'}
      variant="outlined"
      role={tone === 'error' ? 'alert' : 'status'}
      sx={{ py: 0.25 }}
    >
      {children}
    </Alert>
  );
}

/**
 * Shows an action result and brings it into view.
 *
 * Admin actions sit at the bottom of long panels and inside modals, so a result
 * rendered at the top of the page was often never seen: the operator waited,
 * assumed the click failed, and scrolled up to find the error. Toasts solve
 * this at the viewport edge; this keeps the message where the page already
 * renders it and moves the user to it instead.
 */
export function Feedback({ message }) {
  const anchor = useRef(null);

  useEffect(() => {
    const node = anchor.current;
    if (!message || !node) return;
    const viewport = window.innerHeight || document.documentElement.clientHeight;
    const rect = node.getBoundingClientRect();
    // Already readable: leave the page where the operator left it.
    if (rect.top >= 0 && rect.bottom <= viewport) return;
    const reduced =
      window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false;
    const lenis = window.__lenis;
    // While a dialog is open the page copy sits behind the backdrop: scrolling
    // it would only move the page the operator returns to. The dialog renders
    // its own copy, which is the one they can see.
    const inDialog = Boolean(node.closest('[role="dialog"]'));
    if (lenis?.isStopped && !inDialog) return;
    if (lenis?.isStopped || typeof lenis?.scrollTo !== 'function') {
      // A dialog owns the screen, so scroll its body rather than the page
      // behind it (native scrolling works inside the sheet).
      node.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' });
      return;
    }
    lenis.scrollTo(node, {
      offset: -104,
      duration: reduced ? 0 : 0.5,
      immediate: reduced,
    });
  }, [message]);

  if (!message) return null;
  return (
    <div ref={anchor} style={{ scrollMarginTop: 104 }}>
      <InlineMessage tone={message.tone}>{message.text}</InlineMessage>
    </div>
  );
}

export function DataTable({ head, children, empty }) {
  return (
    <TableContainer
      component={Paper}
      elevation={0}
      variant="outlined"
      sx={{
        borderColor: 'divider',
        backgroundColor: 'rgba(255,255,255,0.015)',
        borderRadius: 3,
        overflowX: 'auto',
      }}
    >
      <Table
        size="small"
        sx={{
          borderCollapse: 'collapse',
          minWidth: 560,
          '& th': {
            fontFamily: 'var(--mono, monospace)',
            fontSize: '0.6rem',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: 'text.secondary',
            fontWeight: 600,
            textAlign: 'left',
            padding: '10px 14px',
            borderBottom: '1px solid',
            borderColor: 'divider',
            whiteSpace: 'nowrap',
            backgroundColor: 'rgba(255,255,255,0.02)',
          },
          '& td': {
            fontSize: '0.8125rem',
            padding: '12px 14px',
            borderBottom: '1px solid rgba(148,170,205,0.10)',
            color: 'text.primary',
            verticalAlign: 'middle',
          },
          '& tbody tr:last-of-type td': { borderBottom: 0 },
          '& tbody tr': { transition: 'background-color 120ms ease' },
          '& tbody tr:hover': { backgroundColor: 'rgba(124, 92, 255, 0.07)' },
          '& td b': { fontWeight: 600 },
        }}
      >
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
      </Table>
      {empty ? (
        <Box
          sx={{
            p: 3,
            textAlign: 'center',
            color: 'text.secondary',
            fontSize: '0.8125rem',
            borderTop: '1px solid',
            borderColor: 'divider',
          }}
        >
          {empty}
        </Box>
      ) : null}
    </TableContainer>
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
        <Box sx={{ p: 3 }}>
          <Alert severity="error" variant="outlined">
            <AlertTitle>Failed to render sheet contents</AlertTitle>
            <Typography variant="body2">
              {this.state.error?.message || 'Unknown error occurred while rendering the form.'}
            </Typography>
            <Button
              variant="danger"
              size="small"
              sx={{ mt: 1.5 }}
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Retry form
            </Button>
          </Alert>
        </Box>
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
    console.error('Admin error boundary caught error:', error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <Box sx={{ p: 4, maxWidth: 620, mx: 'auto' }}>
          <Alert
            severity="error"
            variant="outlined"
            action={
              <Button
                variant="danger"
                size="small"
                onClick={() => {
                  clearAsyncCache();
                  this.setState({ hasError: false, error: null });
                }}
              >
                Retry module
              </Button>
            }
          >
            <AlertTitle>Module encountered an issue</AlertTitle>
            <Typography variant="body2">
              {this.state.error?.message ||
                'An unexpected error occurred while loading this admin section.'}
            </Typography>
          </Alert>
        </Box>
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
    return <ErrorPage onRetry={this.reset} />;
  }
}

/**
 * Material dialog shell. Keeps the `.sheet` / `.sheet-body` hooks because the
 * ticket and ID-card print styles target them.
 */
export function Sheet({
  open,
  title,
  onClose,
  children,
  wide = false,
  eyebrow = 'ADMIN ACTION',
  message = null,
}) {
  useEffect(() => {
    if (!open) return undefined;
    // Lenis drives the page scroll, so stop it while the dialog owns the screen.
    if (window.__lenis) window.__lenis.stop();
    return () => {
      if (window.__lenis) window.__lenis.start();
    };
  }, [open]);

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      fullWidth
      maxWidth={false}
      aria-label={title}
      slotProps={{
        backdrop: {
          sx: { backgroundColor: 'rgba(3, 6, 12, 0.66)', backdropFilter: 'blur(6px)' },
        },
        paper: {
          className: `sheet ${wide ? 'is-wide' : ''}`.trim(),
          sx: {
            width: wide ? 900 : 620,
            maxWidth: 'calc(100vw - 28px)',
            maxHeight: 'calc(100vh - 64px)',
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 3,
            backgroundColor: 'background.paper',
            backgroundImage: 'none',
            boxShadow: '0 30px 80px rgba(0, 0, 0, 0.6)',
            overflow: 'hidden',
          },
        },
      }}
    >
      <DialogTitle
        component="header"
        sx={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 2,
          px: 3,
          pt: 2.5,
          pb: 1.75,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Box>
          <Eyebrow>{eyebrow}</Eyebrow>
          <Typography variant="h3" component="h2" sx={{ mt: 0.5 }}>
            {title}
          </Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="Close" size="small">
          <X size={17} strokeWidth={1.7} />
        </IconButton>
      </DialogTitle>
      <DialogContent
        className="sheet-body"
        data-lenis-prevent
        sx={{ px: 3, py: 2.5 }}
        dividers={false}
      >
        {/* An action that fails with the dialog still open writes its error
            into the page behind the backdrop. Showing the same message here
            is what the operator actually sees. */}
        <Feedback message={message} />
        <SheetErrorBoundary>{children}</SheetErrorBoundary>
      </DialogContent>
    </Dialog>
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
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
        gap: 2,
      }}
    >
      {children}
    </Box>
  );
}
