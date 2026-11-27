import React, { Component, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { AlertTriangle, Inbox, X } from 'lucide-react';

// Cache/hooks stay in one place; only the visual primitives are re-drawn here.
export { useAsync, useDebounced, clearAsyncCache } from './ui.jsx';

export function Eyebrow({ children, className = '' }) {
  return <div className={`eyebrow ${className}`.trim()}>{children}</div>;
}

export function PageTitle({ kicker, title, desc, aside }) {
  return (
    <div className="adm-page-head">
      <div className="adm-page-head-text">
        {kicker ? <p className="adm-kicker">{kicker}</p> : null}
        <h1>{title}</h1>
        {desc ? <p>{desc}</p> : null}
      </div>
      {aside ? <div className="adm-head-actions">{aside}</div> : null}
    </div>
  );
}

export function SectionHead({ kicker, title, subtitle, action }) {
  return (
    <div className="adm-page-head">
      <div className="adm-page-head-text">
        {kicker ? <p className="adm-kicker">{kicker}</p> : null}
        <h1>{title}</h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {action ? <div className="adm-head-actions">{action}</div> : null}
    </div>
  );
}

const VARIANT = {
  primary: 'is-primary',
  secondary: 'is-secondary',
  ghost: 'is-outline',
  outline: 'is-outline',
  light: 'is-primary',
  success: 'is-success',
  warning: 'is-warning',
  info: 'is-info',
  accent: 'is-accent',
  danger: 'is-destructive',
  destructive: 'is-destructive',
  link: 'is-ghost',
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
  ...rest
}) {
  const cls = `adm-btn ${VARIANT[variant] || 'is-primary'} ${size === 'small' ? 'is-sm' : ''} ${className}`.trim();
  const content = (
    <>
      {loading ? (
        Icon ? (
          <Icon className="adm-spin" aria-hidden="true" />
        ) : (
          <span className="adm-spinner" aria-hidden="true" />
        )
      ) : Icon ? (
        <Icon aria-hidden="true" />
      ) : null}
      {children}
    </>
  );
  if (to) {
    return (
      <Link to={to} className={cls} aria-busy={loading || undefined} {...rest}>
        {content}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} className={cls} {...rest}>
        {content}
      </a>
    );
  }
  return (
    <button
      type={type}
      className={cls}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {content}
    </button>
  );
}

export function Panel({ children, className = '', padded = true, ...rest }) {
  return (
    <div className={`adm-card ${padded ? '' : 'is-flush'} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

export function Stat({ label, value, note, tone = '', icon: Icon = null }) {
  return (
    <div className={`adm-stat ${tone ? `is-${tone}` : ''}`.trim()}>
      <span className="adm-stat-label">
        {Icon ? <Icon size={13} strokeWidth={1.8} style={{ marginRight: 6, verticalAlign: '-2px' }} /> : null}
        {label}
      </span>
      <b className="adm-stat-value">{value}</b>
      {note ? <span className="adm-stat-note">{note}</span> : null}
    </div>
  );
}

const TONE_CLASS = {
  good: 'is-good',
  warn: 'is-warn',
  bad: 'is-bad',
  accent: 'is-accent',
  muted: 'is-muted',
  neutral: '',
  solid: 'is-solid',
};

export function Badge({ tone = 'neutral', children, icon: Icon = null }) {
  return (
    <span className={`adm-badge ${TONE_CLASS[tone] ?? ''}`.trim()}>
      {Icon ? <Icon aria-hidden="true" /> : null}
      {children}
    </span>
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

export function Loading({ label = 'Loading', rows = 2 }) {
  return (
    <div className="adm-loading" role="status" aria-live="polite">
      <span className="adm-loading-label">
        <span className="adm-spinner" aria-hidden="true" />
        {label}
      </span>
      {Array.from({ length: Math.max(0, rows) }).map((_, index) => (
        <div className="adm-skel" key={index} style={{ width: `${100 - index * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ error, onRetry, title = 'That did not load' }) {
  return (
    <div className="adm-alert is-error" role="alert">
      <AlertTriangle aria-hidden="true" />
      <div>
        <b>{title}</b>
        <div>{error?.message || 'The server could not complete that request.'}</div>
        {error?.code ? (
          <div style={{ opacity: 0.7, fontSize: 11, marginTop: 2 }}>
            <code>{error.code}</code>
          </div>
        ) : null}
        {onRetry ? (
          <div style={{ marginTop: 8 }}>
            <Button variant="ghost" size="small" onClick={onRetry}>
              Try again
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function Empty({ title = 'Nothing here yet', desc, children }) {
  return (
    <div className="adm-empty">
      <Inbox aria-hidden="true" />
      <b>{title}</b>
      {desc ? <span>{desc}</span> : null}
      {children}
    </div>
  );
}

export function Field({ label, hint, children, className = '' }) {
  return (
    <label className={`adm-field ${className}`.trim()}>
      <span className="adm-field-label">{label}</span>
      {children}
      {hint ? <small className="adm-field-hint">{hint}</small> : null}
    </label>
  );
}

export function Toggle({ checked, onChange, label, hint }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={Boolean(checked)}
      aria-label={label}
      className={`adm-switch ${checked ? 'is-on' : ''}`.trim()}
      onClick={() => onChange(!checked)}
    >
      <span className="adm-switch-track" aria-hidden="true" />
      <span className="adm-switch-text">
        <b>{label}</b>
        {hint ? <small>{hint}</small> : null}
      </span>
    </button>
  );
}

const ALERT_TONE = { info: 'is-info', success: 'is-success', warn: 'is-warn', warning: 'is-warn', error: 'is-error' };

export function InlineMessage({ tone = 'info', children }) {
  return (
    <div className={`adm-alert ${ALERT_TONE[tone] || 'is-info'}`} role={tone === 'error' ? 'alert' : 'status'}>
      <div>{children}</div>
    </div>
  );
}

export function Feedback({ message }) {
  const anchor = useRef(null);
  useEffect(() => {
    const node = anchor.current;
    if (!message || !node) return;
    const viewport = window.innerHeight || document.documentElement.clientHeight;
    const rect = node.getBoundingClientRect();
    if (rect.top >= 0 && rect.bottom <= viewport) return;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false;
    node.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' });
  }, [message]);

  if (!message) return null;
  return (
    <div ref={anchor}>
      <InlineMessage tone={message.tone}>{message.text}</InlineMessage>
    </div>
  );
}

export function DataTable({ head, children, empty, title, action }) {
  const rows = React.Children.toArray(children).filter(Boolean);
  // Nothing to show and nothing to say: skip the card instead of leaving a
  // header-only table with a stray horizontal scrollbar behind.
  if (!rows.length && !empty) return null;
  return (
    <div className="adm-card adm-table-card">
      {title ? (
        <div className="adm-card-head">
          <div>
            <h2>{title}</h2>
          </div>
          {action ? <div className="adm-head-actions">{action}</div> : null}
        </div>
      ) : null}
      {rows.length ? (
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr>
                {head.map((cell) => (
                  <th key={cell} scope="col">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
      ) : null}
      {empty ? <div className="adm-table-empty">{empty}</div> : null}
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
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="adm-alert is-error">
        <AlertTriangle aria-hidden="true" />
        <div>
          <b>Failed to render sheet contents</b>
          <div>{this.state.error?.message || 'Unknown error occurred while rendering the form.'}</div>
          <div style={{ marginTop: 8 }}>
            <Button variant="danger" onClick={() => this.setState({ hasError: false, error: null })}>
              Retry form
            </Button>
          </div>
        </div>
      </div>
    );
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
    if (!this.state.hasError) return this.props.children;
    return (
      <ErrorBox
        error={this.state.error}
        title="Module encountered an issue"
        onRetry={() => this.setState({ hasError: false, error: null })}
      />
    );
  }
}

export function Sheet({ open, title, onClose, children, wide = false, eyebrow = 'Admin action', message = null }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div
      className="adm-scope adm-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <div className={`adm-dialog ${wide ? 'is-wide' : ''}`.trim()}>
        <div className="adm-dialog-head">
          <div>
            {eyebrow ? <p className="adm-kicker">{eyebrow}</p> : null}
            <h2>{title}</h2>
          </div>
          <button type="button" className="adm-icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>
        <div className="adm-dialog-body" data-lenis-prevent>
          {message ? <Feedback message={message} /> : null}
          <SheetErrorBoundary>{children}</SheetErrorBoundary>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function FieldGrid({ children }) {
  return <div className="adm-field-grid">{children}</div>;
}
