import { useEffect, useRef, useState } from 'react';
import '../styles/admin-ui.css';
import { usePortalAvatar } from '../lib/portalAvatar.js';
import { resolveImageUrl } from '../lib/imageUrl.js';
import {
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom';
import jsQR from 'jsqr';
import {
  ArrowUpRight,
  CalendarDays,
  Camera,
  CameraOff,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  CreditCard,
  Database,
  Download,
  ExternalLink,
  FileText,
  Flashlight,
  FlipHorizontal,
  IdCard,
  Image,
  IndianRupee,
  LayoutDashboard,
  LogOut,
  Megaphone,
  PanelLeft,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Ticket,
  Trash2,
  Upload,
  Users,
  Wallet,
  X,
} from 'lucide-react';

import { adminApi, publicApi } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { foodLabel, genderLabel } from '../lib/attendee.js';
import {
  date,
  dateTime,
  fromLocalInput,
  money,
  paise,
  rupees,
  toLocalInput,
} from '../lib/format.js';
import {
  AdminErrorBoundary,
  Badge,
  Button,
  DataTable,
  ErrorBox,
  Eyebrow,
  Feedback,
  Field,
  FieldGrid,
  InlineMessage,
  Loading,
  Panel,
  SectionHead,
  Sheet,
  StatusBadge,
  Toggle,
} from '../components/admin-ui.jsx';
import { clearAsyncCache, useAsync, useDebounced } from '../components/ui.jsx';

const LOGO =
  String(import.meta.env.BASE_URL) +
  'images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp';

const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [['Overview', '/manage', LayoutDashboard]],
  },
  {
    label: 'Operations',
    items: [
      ['Events', '/manage/events', CalendarDays],
      ['Registration desk', '/manage/registration', IdCard],
      ['ID card studio', '/manage/id-cards', CreditCard],
      ['Check-in', '/manage/check-in', ClipboardCheck],
      ['Attendance', '/manage/attendance', FileText],
    ],
  },
  {
    label: 'Registrations',
    items: [
      ['All registrations', '/manage/registrations', Ticket],
      ['Teams', '/manage/teams', Users],
      ['Cancelled & refunds', '/manage/registrations?status=cancelled', Wallet],
    ],
  },
  {
    label: 'Finance',
    items: [['Payments', '/manage/payments', Wallet]],
  },
  {
    label: 'People',
    items: [['Users', '/manage/users', Users]],
  },
  {
    label: 'Communication',
    items: [['Announcements', '/manage/announcements', Megaphone]],
  },
  {
    label: 'Configuration',
    items: [
      ['Pass policy', '/manage/policy', ShieldCheck],
      ['Registration config', '/manage/registration-settings', Settings],
      ['Settings', '/manage/settings', Settings],
    ],
  },
  {
    label: 'System',
    items: [
      ['Audit log', '/manage/audit', FileText],
      ['DB playground', '/manage/database', Database],
    ],
  },
];

const ROLE_LABELS = {
  owner: 'Owner',
  super_admin: 'Super admin',
  edition_admin: 'Edition admin',
  finance_admin: 'Finance admin',
  event_coordinator: 'Event coordinator',
  checkin_staff: 'Check-in staff',
  participant: 'Participant',
};

// Roles the staff API accepts on a grant or invite (MembershipGrant pattern).
// ``owner`` is only a legacy label for a super admin; sending it is a 422.
const GRANTABLE_ROLES = ['edition_admin', 'finance_admin', 'event_coordinator', 'checkin_staff'];

// Highest privilege first: when an account still carries stacked roles from
// before grants became one-per-account, this is the one that describes them.
const ROLE_RANK = {
  owner: 0,
  super_admin: 1,
  edition_admin: 2,
  finance_admin: 3,
  event_coordinator: 4,
  checkin_staff: 5,
  participant: 6,
};

/** Collapse stacked memberships into one row per account. */
function oneRolePerAccount(rows = []) {
  const byUser = new Map();
  for (const row of rows) {
    const seen = byUser.get(row.userId);
    if (!seen) {
      byUser.set(row.userId, { ...row, staleRoles: [] });
      continue;
    }
    const incoming = ROLE_RANK[row.role] ?? 99;
    const current = ROLE_RANK[seen.role] ?? 99;
    if (incoming < current) {
      byUser.set(row.userId, {
        ...row,
        staleRoles: [...seen.staleRoles, seen.role],
      });
    } else {
      seen.staleRoles.push(row.role);
    }
  }
  return [...byUser.values()];
}

const ACCENTS = ['cyan', 'amber', 'orange', 'violet', 'lime', 'rose', 'ice'];

const RAIL_KEY = 'px_admin_rail';

function readRail() {
  try {
    return localStorage.getItem(RAIL_KEY) === '1';
  } catch {
    return false;
  }
}

function initialsOf(email) {
  const value = String(email || 'staff');
  const base = value
    .split('@')[0]
    .replace(/[^a-zA-Z0-9]+/g, ' ')
    .trim();
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return base.slice(0, 2).toUpperCase() || 'PX';
}

/** One matcher for the whole rail: `/manage/registrations?status=cancelled`
 *  and the unfiltered list share a path, so the query decides between them. */
function navItemActive(to, pathname, searchParams) {
  const [path, query] = to.split('?');
  if (path === '/manage/registrations') {
    if (pathname !== path) return false;
    const wanted = new URLSearchParams(query || '').get('status');
    const current = searchParams.get('status');
    return wanted ? current === wanted : current !== 'cancelled';
  }
  if (path === '/manage') return pathname === path;
  return pathname === path || pathname.startsWith(`${path}/`);
}

function pageLabelFor(pathname, searchParams) {
  for (const group of NAV_GROUPS) {
    for (const [label, to] of group.items) {
      if (
        navItemActive(to, pathname, searchParams) &&
        !(to === '/manage' && pathname !== '/manage')
      ) {
        return label;
      }
    }
  }
  return 'Staff console';
}

export function AdminLayout() {
  const { isStaff, roles, user, loading, logout } = useAuth();
  const [activeAvatar] = usePortalAvatar(user?.id, 'root');
  const site = useSite();
  const { edition, editionId } = site;
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [collapsed, setCollapsed] = useState(readRail);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [pageKey, setPageKey] = useState(0);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    setMobileOpen(false);
    setAccountOpen(false);
  }, [location.pathname, location.search]);

  const toggleRail = () => {
    setCollapsed((value) => {
      const next = !value;
      try {
        localStorage.setItem(RAIL_KEY, next ? '1' : '0');
      } catch {
        /* private mode */
      }
      return next;
    });
  };

  useEffect(() => {
    const onKey = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearchOpen((value) => !value);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // The console scrolls inside its own column while Lenis drives the document,
  // so pausing it stops the wheel from moving a page that never moves.
  useEffect(() => {
    const lenis = window.__lenis;
    lenis?.stop?.();
    return () => lenis?.start?.();
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(id);
  }, [toast]);

  const handleForceRefresh = async () => {
    if (syncing) return;
    setSyncing(true);
    setToast(null);
    const minSpin = new Promise((resolve) => setTimeout(resolve, 650));
    try {
      await Promise.all([
        editionId ? adminApi.sync(editionId) : Promise.resolve(),
        minSpin,
      ]);
      clearAsyncCache();
      try {
        sessionStorage.removeItem('px_cached_edition');
        sessionStorage.removeItem('px_cached_config');
      } catch {
        /* private mode */
      }
      site.refresh();
      setPageKey((k) => k + 1);
      setToast('Server caches purged and module reloaded.');
    } catch {
      await minSpin;
      clearAsyncCache();
      try {
        sessionStorage.removeItem('px_cached_edition');
        sessionStorage.removeItem('px_cached_config');
      } catch {
        /* private mode */
      }
      site.refresh();
      setPageKey((k) => k + 1);
      setToast('Client cache purged and reloaded.');
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="adm-scope adm-gate">
        <Loading label="Verifying staff credentials…" rows={0} />
      </div>
    );
  }
  if (!user) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  }
  if (!isStaff) return <Navigate to="/portal" replace />;

  // Staff modules need the real database edition row: without it every request
  // would address an id the API does not know, so gate them on a verified load.
  if (!site.editionVerified) {
    return (
      <div className="adm-scope adm-gate">
        {site.editionError ? (
          <div className="adm-stack">
            <ErrorBox
              error={site.editionError}
              title="Could not load the convention edition"
              onRetry={site.refresh}
            />
            <p className="muted">
              The console needs the live edition record before it can load staff modules. This is
              usually a short database wake-up: retry in a moment. Signing out and in again also
              refreshes the session.
            </p>
            <div className="adm-btn-row">
              <Button variant="outline" icon={RefreshCw} onClick={site.refresh}>
                Retry edition lookup
              </Button>
              <Button variant="ghost" to="/portal">
                Open participant portal
              </Button>
              <Button variant="ghost" icon={LogOut} onClick={logout}>
                Sign out
              </Button>
            </div>
          </div>
        ) : (
          <Loading label="Resolving convention edition…" rows={0} />
        )}
      </div>
    );
  }

  const pageLabel = pageLabelFor(location.pathname, searchParams);
  const roleLabel = ROLE_LABELS[roles[0]] || 'Staff';

  const navGroups = (onNavigate) =>
    NAV_GROUPS.map((group) => (
      <div className="adm-nav-group" key={group.label}>
        <div className="adm-nav-label">{group.label}</div>
        {group.items.map(([label, to, Icon]) => {
          const active = navItemActive(to, location.pathname, searchParams);
          return (
            <Link
              key={`${group.label}-${label}`}
              to={to}
              title={label}
              aria-current={active ? 'page' : undefined}
              onClick={onNavigate}
              className={`adm-nav-item ${active ? 'is-active' : ''}`.trim()}
            >
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </Link>
          );
        })}
      </div>
    ));

  return (
    <div className={`adm adm-scope ${collapsed ? 'is-collapsed' : ''}`.trim()} data-lenis-prevent>
      <aside className="adm-sidebar">
        <div className="adm-sidebar-head">
          <Link to="/manage" className="adm-brand" aria-label="Staff operations home">
            <img src={LOGO} alt="" className="adm-brand-logo" />
            <span className="adm-brand-text">
              <b>{edition?.name || 'Parallax'}</b>
              <small>Staff console</small>
            </span>
          </Link>
          <button
            type="button"
            className="adm-icon-btn adm-collapse-btn"
            onClick={toggleRail}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
          >
            <PanelLeftClose size={15} strokeWidth={1.7} />
          </button>
        </div>

        <nav className="adm-sidebar-nav" aria-label="Staff navigation">
          {navGroups()}
        </nav>

        <div className="adm-sidebar-foot">
          <div className="adm-user">
            <span className={`adm-avatar ${activeAvatar.kind === 'glyph' ? 'is-glyph' : ''}`}>
              <img src={activeAvatar.src} alt={activeAvatar.label || roleLabel} />
            </span>
            <span className="adm-user-meta">
              <b>{roleLabel}</b>
              <small>{user?.email}</small>
            </span>
            <button
              type="button"
              className="adm-icon-btn adm-rail-hide"
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={15} strokeWidth={1.7} />
            </button>
          </div>
        </div>
      </aside>

      <div className="adm-main">
        <header className="adm-header">
          <div className="adm-header-left">
            <button
              type="button"
              className="adm-icon-btn"
              onClick={() => {
                if (window.matchMedia('(max-width: 1023px)').matches) setMobileOpen(true);
                else toggleRail();
              }}
              aria-label="Toggle navigation"
            >
              <PanelLeft size={16} strokeWidth={1.7} />
            </button>
            <span className="adm-vsep" />
            <nav className="adm-crumbs" aria-label="Breadcrumb">
              <span>Staff console</span>
              <ChevronRight size={14} strokeWidth={1.8} />
              <b>{pageLabel}</b>
            </nav>
          </div>

          <div className="adm-header-right">
            <button
              type="button"
              className="adm-search-trigger"
              onClick={() => setSearchOpen(true)}
            >
              <Search size={14} strokeWidth={1.8} />
              <span>Search modules…</span>
              <span className="adm-kbd">⌘K</span>
            </button>
            <button
              type="button"
              className="adm-icon-btn"
              title="Refresh server caches"
              aria-label="Refresh server caches"
              onClick={handleForceRefresh}
              disabled={syncing}
            >
              <RefreshCw size={15} strokeWidth={1.7} className={syncing ? 'adm-spin' : ''} />
            </button>
            <Link
              to="/"
              className="adm-icon-btn adm-hide-xs"
              title="Open live site"
              aria-label="Open live site"
            >
              <ExternalLink size={15} strokeWidth={1.7} />
            </Link>
            <Link
              to="/portal"
              className="adm-icon-btn adm-hide-xs"
              title="Participant portal"
              aria-label="Participant portal"
            >
              <Users size={15} strokeWidth={1.7} />
            </Link>
            <span className="adm-vsep" />
            <div className="adm-account">
              <button
                type="button"
                className="adm-account-btn"
                aria-expanded={accountOpen}
                aria-haspopup="menu"
                onClick={() => setAccountOpen((value) => !value)}
              >
                <span
                  className={`adm-avatar is-round ${activeAvatar.kind === 'glyph' ? 'is-glyph' : ''}`}
                >
                  <img src={activeAvatar.src} alt={activeAvatar.label || roleLabel} />
                </span>
                <ChevronDown size={14} strokeWidth={1.8} />
              </button>
              {accountOpen ? (
                <>
                  <div className="adm-menu-backdrop" onClick={() => setAccountOpen(false)} />
                  <div className="adm-menu" role="menu">
                    <div className="adm-menu-head">
                      <b>{roleLabel}</b>
                      <small>{user?.email}</small>
                    </div>
                    <Link className="adm-menu-item" to="/portal" role="menuitem">
                      <Users /> Participant portal
                    </Link>
                    <Link className="adm-menu-item" to="/" role="menuitem">
                      <ArrowUpRight /> Live site
                    </Link>
                    <Link className="adm-menu-item" to="/manage/settings" role="menuitem">
                      <Settings /> Console settings
                    </Link>
                    <div className="adm-menu-sep" />
                    <button
                      type="button"
                      className="adm-menu-item is-danger"
                      onClick={logout}
                      role="menuitem"
                    >
                      <LogOut /> Sign out
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </header>

        <main className="adm-content" id="admin-main" data-lenis-prevent>
          <AdminErrorBoundary key={`${location.pathname}:${pageKey}`}>
            <Outlet key={pageKey} />
          </AdminErrorBoundary>
        </main>
      </div>

      {mobileOpen ? (
        <>
          <div className="adm-drawer-backdrop" onClick={() => setMobileOpen(false)} />
          <div className="adm-drawer" role="dialog" aria-modal="true" aria-label="Staff modules">
            <div className="adm-sidebar-head">
              <Link to="/manage" className="adm-brand" onClick={() => setMobileOpen(false)}>
                <img src={LOGO} alt="" className="adm-brand-logo" />
                <span className="adm-brand-text">
                  <b>{edition?.name || 'Parallax'}</b>
                  <small>Staff console</small>
                </span>
              </Link>
              <button
                type="button"
                className="adm-icon-btn"
                onClick={() => setMobileOpen(false)}
                aria-label="Close menu"
              >
                <X size={16} strokeWidth={1.8} />
              </button>
            </div>
            <nav className="adm-sidebar-nav" aria-label="Staff modules">
              {navGroups(() => setMobileOpen(false))}
            </nav>
            <div className="adm-sidebar-foot">
              <div className="adm-user">
                <span className={`adm-avatar ${activeAvatar.kind === 'glyph' ? 'is-glyph' : ''}`}>
                  <img src={activeAvatar.src} alt={activeAvatar.label || roleLabel} />
                </span>
                <span className="adm-user-meta">
                  <b>{roleLabel}</b>
                  <small>{user?.email}</small>
                </span>
                <button
                  type="button"
                  className="adm-icon-btn"
                  onClick={logout}
                  aria-label="Sign out"
                >
                  <LogOut size={15} strokeWidth={1.7} />
                </button>
              </div>
            </div>
          </div>
        </>
      ) : null}

      <CommandPalette open={searchOpen} onClose={() => setSearchOpen(false)} />

      {toast ? (
        <div
          className="adm-alert is-success"
          role="status"
          style={{ position: 'fixed', right: 16, bottom: 16, zIndex: 1400, maxWidth: 380 }}
        >
          <Check aria-hidden="true" />
          <div>{toast}</div>
        </div>
      ) : null}
    </div>
  );
}

function CommandPalette({ open, onClose }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    setQuery('');
    const id = setTimeout(() => inputRef.current?.focus(), 30);
    const onKey = (event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(id);
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  const needle = query.trim().toLowerCase();
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter(([label]) => label.toLowerCase().includes(needle)),
  })).filter((group) => group.items.length);

  const go = (to) => {
    onClose();
    navigate(to);
  };

  return (
    <div
      className="adm-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="adm-command" role="dialog" aria-modal="true" aria-label="Search modules">
        <div className="adm-command-input">
          <Search size={15} strokeWidth={1.8} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search admin modules…"
            aria-label="Search admin modules"
            onKeyDown={(event) => {
              if (event.key === 'Enter' && groups[0]?.items[0]) go(groups[0].items[0][1]);
            }}
          />
          <span className="adm-kbd">esc</span>
        </div>
        <div className="adm-command-list">
          {groups.length ? (
            groups.map((group) => (
              <div key={group.label}>
                <div className="adm-command-group">{group.label}</div>
                {group.items.map(([label, to, Icon]) => (
                  <button
                    key={to}
                    type="button"
                    className="adm-command-item"
                    onClick={() => go(to)}
                  >
                    <Icon aria-hidden="true" />
                    <span>{label}</span>
                  </button>
                ))}
              </div>
            ))
          ) : (
            <div className="adm-command-empty">No modules match “{query}”.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, note, badge, badgeTone = 'muted', chart = null }) {
  return (
    <div className="adm-metric">
      <div className="adm-metric-top">
        <span className="adm-metric-icon">
          <Icon aria-hidden="true" />
        </span>
        {badge ? <Badge tone={badgeTone}>{badge}</Badge> : null}
      </div>
      <span className="adm-metric-label">{label}</span>
      <b className="adm-metric-value">{value}</b>
      {chart}
      {note ? <span className="adm-metric-note">{note}</span> : null}
    </div>
  );
}

function Sparkline({ values, color = 'var(--adm-chart, #7dd3fc)' }) {
  const list = (values || []).map((value) => Number(value) || 0);
  if (list.length < 2) return null;
  const max = Math.max(...list);
  const min = Math.min(...list);
  const span = max - min || 1;
  const W = 120;
  const H = 34;
  const points = list.map((value, index) => [
    (index / (list.length - 1)) * W,
    H - 2 - ((value - min) / span) * (H - 6),
  ]);
  const path = points
    .map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  return (
    <svg
      className="adm-spark"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path d={path} fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

function Donut({ segments, total, centerLabel = 'total' }) {
  const size = 104;
  const stroke = 11;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const sum = total || segments.reduce((count, segment) => count + (segment.count || 0), 0);
  let offset = 0;
  return (
    <div className="adm-donut">
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={centerLabel}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={stroke}
        />
        {sum
          ? segments
              .filter((segment) => segment.count > 0)
              .map((segment) => {
                const length = (segment.count / sum) * circumference;
                const node = (
                  <circle
                    key={segment.label}
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke={segment.color}
                    strokeWidth={stroke}
                    strokeDasharray={`${length} ${circumference - length}`}
                    strokeDashoffset={-offset}
                    transform={`rotate(-90 ${size / 2} ${size / 2})`}
                  />
                );
                offset += length;
                return node;
              })
          : null}
      </svg>
      <div className="adm-donut-center">
        <b>{sum}</b>
        <span>{centerLabel}</span>
      </div>
    </div>
  );
}

function Breakdown({ items, emptyLabel = 'No data yet.', centerLabel = 'total' }) {
  const total = items.reduce((sum, item) => sum + (Number(item.count) || 0), 0);
  if (!total)
    return (
      <p className="muted" style={{ margin: 0 }}>
        {emptyLabel}
      </p>
    );
  return (
    <div className="adm-donut-wrap">
      <Donut segments={items} total={total} centerLabel={centerLabel} />
      <div className="adm-dist-legend" style={{ marginTop: 0, flex: 1 }}>
        {items.map((item) => (
          <div className="adm-dist-row" key={item.label}>
            <span className="adm-dot" style={{ background: item.color }} />
            <span>{item.label}</span>
            <b>
              {item.count}{' '}
              <small style={{ color: 'var(--adm-fg-dim)', fontWeight: 400 }}>
                ({Math.round((item.count / total) * 100)}%)
              </small>
            </b>
          </div>
        ))}
      </div>
    </div>
  );
}

function SalesChart({ rows }) {
  const raw = (rows || []).slice(-14);
  if (!raw.length) {
    return (
      <p className="muted" style={{ margin: 0 }}>
        No paid orders recorded yet.
      </p>
    );
  }

  // Pad to at least 7 days ending on the latest recorded day so single-day
  // launches render a real trend curve instead of one isolated dot.
  let series = raw;
  if (raw.length < 7) {
    const byDate = new Map(raw.map((r) => [String(r.date), Number(r.amountPaise) || 0]));
    const lastParsed = new Date(`${raw[raw.length - 1].date}T00:00:00`);
    if (!Number.isNaN(lastParsed.getTime())) {
      series = [];
      for (let offset = 6; offset >= 0; offset -= 1) {
        const d = new Date(lastParsed);
        d.setDate(d.getDate() - offset);
        const key = d.toISOString().slice(0, 10);
        series.push({ date: key, amountPaise: byDate.get(key) || 0 });
      }
    }
  }

  const amounts = series.map((row) => Number(row.amountPaise) || 0);
  const peak = Math.max(...amounts, 1);
  const W = 720;
  const H = 190;
  const top = 12;
  const bottom = 26;
  const plotH = H - top - bottom;
  const step = series.length > 1 ? (W - 16) / (series.length - 1) : 0;
  const points = amounts.map((value, index) => [
    8 + index * step,
    top + plotH - (value / peak) * plotH,
  ]);
  const line = points
    .map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  const area = `${line} L ${points[points.length - 1][0].toFixed(1)},${H - bottom} L ${points[0][0].toFixed(1)},${H - bottom} Z`;
  const dayLabel = (value) => {
    const parsed = new Date(`${value}T00:00:00`);
    return Number.isNaN(parsed.getTime())
      ? String(value || '')
      : parsed.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  };

  return (
    <>
      <div className="adm-chart">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Paid revenue per day"
        >
          <defs>
            <linearGradient id="adm-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7dd3fc" stopOpacity="0.24" />
              <stop offset="100%" stopColor="#7dd3fc" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0, 1, 2, 3].map((index) => {
            const y = top + (plotH / 3) * index;
            return <line key={index} className="adm-chart-grid" x1="8" x2={W - 8} y1={y} y2={y} />;
          })}
          <path d={area} fill="url(#adm-area)" />
          <path d={line} className="adm-chart-line" />
          {points.map(([x, y], index) => (
            <circle
              key={index}
              className="adm-chart-dot"
              cx={x}
              cy={y}
              r={series.length > 10 ? 2 : 2.6}
            />
          ))}
        </svg>
      </div>
      <div className="adm-chart-axis">
        <span>{dayLabel(series[0].date)}</span>
        <span>{series.length > 2 ? dayLabel(series[Math.floor(series.length / 2)].date) : ''}</span>
        <span>{dayLabel(series[series.length - 1].date)}</span>
      </div>
    </>
  );
}

export function AdminOverview() {
  const site = useSite();
  const { editionId, editionVerified } = site;
  const stats = useAsync(() => adminApi.overview(editionId), [editionId], {
    enabled: Boolean(editionId) && editionVerified,
  });
  const data = stats.data?.data;

  if (!editionVerified) return <Loading label="Resolving convention edition…" rows={0} />;
  if (stats.loading) return <Loading label="Loading operational telemetry" rows={3} />;
  if (stats.error) {
    return (
      <ErrorBox
        error={stats.error}
        onRetry={() => {
          stats.reload();
          site.refresh();
        }}
      />
    );
  }

  const sales = data?.salesByDay || [];
  const recent = data?.recentRegistrations || [];
  const passesSold = data?.passesSold ?? 0;
  const checkedIn = data?.checkedIn ?? 0;
  const refunded = data?.refundedPaise || 0;
  const pendingRefundsPaise = data?.pendingRefundsPaise || 0;
  const pendingRefundsCount = data?.pendingRefundsCount || 0;
  const recentRefunds = data?.recentRefunds || [];
  const revenueCollected = sales.reduce((sum, row) => sum + (Number(row.amountPaise) || 0), 0);
  const orders = sales.reduce((sum, row) => sum + (Number(row.count) || 0), 0);
  const peakDay = sales.reduce((peak, row) => Math.max(peak, Number(row.amountPaise) || 0), 0);
  const checkRate = passesSold ? Math.round((checkedIn / passesSold) * 100) : 0;
  const seatsTaken = data?.seatsTaken ?? 0;
  const seatsCapacity = data?.seatsCapacity ?? 0;
  const capacityPct = seatsCapacity
    ? Math.min(100, Math.round((seatsTaken / seatsCapacity) * 100))
    : 0;
  const units = Object.entries(data?.seatsTakenByUnit || {});
  const genderSplit = data?.genderSplit || [];
  const foodSplit = data?.foodSplit || [];
  const accommodation = data?.accommodation || {};
  const passCategories = data?.passCategories || [];
  const eventRegistrations = data?.eventRegistrations || [];
  const attendees = genderSplit.reduce((sum, row) => sum + (Number(row.count) || 0), 0);
  const categoryTotal = passCategories.reduce((sum, row) => sum + (Number(row.count) || 0), 0);

  return (
    <>
      <div className="adm-page-head">
        <div className="adm-page-head-text">
          <p className="adm-kicker">Operations telemetry</p>
          <h1>Overview</h1>
          <p>
            Real-time metrics, ticketing volume, capacity and door check-in status for{' '}
            {data?.editionName || 'the convention'}.
          </p>
        </div>
        <div className="adm-head-actions">
          <Button to="/manage/check-in" icon={ClipboardCheck}>
            Open check-in
          </Button>
        </div>
      </div>

      <div className="adm-metrics">
        <MetricCard
          icon={Ticket}
          label="Passes sold"
          value={passesSold}
          badge={`${data?.registrationsConfirmed ?? 0} confirmed`}
          badgeTone="accent"
          note="Active convention passes issued."
        />
        <MetricCard
          icon={IndianRupee}
          label="Net revenue"
          value={money(data?.netRevenuePaise ?? data?.revenuePaise ?? 0)}
          badge={refunded ? `-${money(refunded)} refunded` : 'No refunds'}
          badgeTone={refunded ? 'bad' : 'muted'}
          note={`Gross ${money(data?.revenuePaise || 0)} − ${money(refunded)} refunded across ${orders} orders.`}
          chart={<Sparkline values={sales.map((row) => Number(row.amountPaise) || 0)} />}
        />
        <MetricCard
          icon={Wallet}
          label="Refunds"
          value={refunded ? `-${money(refunded)}` : money(0)}
          badge={
            pendingRefundsCount
              ? `${pendingRefundsCount} pending (${money(pendingRefundsPaise)})`
              : 'None pending'
          }
          badgeTone={pendingRefundsCount ? 'warn' : refunded ? 'bad' : 'muted'}
          note={
            <Link to="/manage/finance" style={{ color: 'var(--accent)', textDecoration: 'none' }}>
              Review &amp; process refunds →
            </Link>
          }
        />
        <MetricCard
          icon={Users}
          label="Registrations"
          value={data?.registrationsConfirmed ?? 0}
          badge={`${data?.registrationsPending ?? 0} pending`}
          badgeTone={data?.registrationsPending ? 'warn' : 'muted'}
          note="Passes and event sign-ups."
          chart={
            <div className="adm-metric-meter">
              <i
                style={{
                  width: `${
                    (data?.registrationsConfirmed ?? 0) + (data?.registrationsPending ?? 0)
                      ? Math.round(
                          ((data?.registrationsConfirmed ?? 0) /
                            ((data?.registrationsConfirmed ?? 0) +
                              (data?.registrationsPending ?? 0))) *
                            100,
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
          }
        />
        <MetricCard
          icon={ClipboardCheck}
          label="Checked in"
          value={checkedIn}
          badge={`${checkRate}% of passes`}
          badgeTone={checkRate >= 50 ? 'good' : 'muted'}
          note="Door scans across both convention days."
          chart={
            <div className="adm-metric-meter">
              <i style={{ width: `${checkRate}%` }} />
            </div>
          }
        />
      </div>

      <div className="adm-card">
        <div className="adm-card-head">
          <div>
            <h2>Recent refunds</h2>
            <p>Processed refunds are deducted from net revenue; pending ones await confirmation.</p>
          </div>
          <Button variant="ghost" to="/manage/finance">
            Open finance ledger
          </Button>
        </div>
        {recentRefunds.length ? (
          <DataTable head={['Order', 'Amount', 'Reason', 'Status', 'Date']}>
            {recentRefunds.map((rf) => (
              <tr key={rf.id}>
                <td className="mono-note">{rf.orderId}</td>
                <td style={{ color: '#f87171', fontWeight: 600 }}>-{money(rf.amountPaise)}</td>
                <td>
                  {rf.reasonCode}
                  {rf.reasonNote ? <div className="table-sub">{rf.reasonNote}</div> : null}
                </td>
                <td>
                  <StatusBadge status={rf.status} />
                </td>
                <td>{date(rf.processedAt || rf.createdAt)}</td>
              </tr>
            ))}
          </DataTable>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            No refunds recorded for this edition yet.
          </p>
        )}
      </div>

      <div className="adm-card">
        <div className="adm-card-head">
          <div>
            <h2>Revenue performance</h2>
            <p>Paid orders per day for the last {Math.max(sales.length, 7)} days.</p>
          </div>
          <div className="adm-head-actions">
            <Badge tone="muted">{orders} orders</Badge>
            <Badge tone="good">{money(revenueCollected)} collected</Badge>
          </div>
        </div>
        <SalesChart rows={sales} />
        <div className="adm-chart-legend">
          <span>
            <i className="adm-chart-swatch" /> Daily revenue
          </span>
          <span>Peak day {money(peakDay)}</span>
        </div>
      </div>

      <div className="adm-columns-3">
        <div className="adm-card">
          <div className="adm-card-head">
            <div>
              <h2>Gender split</h2>
              <p>{attendees} attendees on file.</p>
            </div>
          </div>
          <Breakdown
            centerLabel="attendees"
            emptyLabel="No gender answers recorded yet."
            items={genderSplit.map((row) => ({
              label: row.label,
              count: row.count || 0,
              color: row.key === 'male' ? '#7dd3fc' : row.key === 'female' ? '#f0abfc' : '#404040',
            }))}
          />
        </div>

        <div className="adm-card">
          <div className="adm-card-head">
            <div>
              <h2>Meal preference</h2>
              <p>Kitchen headcount by plate.</p>
            </div>
          </div>
          <Breakdown
            centerLabel="meals"
            emptyLabel="No meal preferences recorded yet."
            items={foodSplit.map((row) => ({
              label: row.label,
              count: row.count || 0,
              color: row.key === 'veg' ? '#4ade80' : row.key === 'non_veg' ? '#f87171' : '#404040',
            }))}
          />
        </div>

        <div className="adm-card">
          <div className="adm-card-head">
            <div>
              <h2>Accommodation</h2>
              <p>{accommodation.needed ?? 0} attendees need a hostel bed.</p>
            </div>
          </div>
          <Breakdown
            centerLabel="stays"
            emptyLabel="No accommodation answers recorded yet."
            items={[
              { label: 'Hostel stay', count: accommodation.needed || 0, color: '#fafafa' },
              { label: 'No stay needed', count: accommodation.notNeeded || 0, color: '#404040' },
            ]}
          />
        </div>
      </div>

      <div className="adm-columns-2">
        <div className="adm-card adm-table-card">
          <div className="adm-card-head">
            <div>
              <h2>Registrations by event</h2>
              <p>Every event in the edition · confirmed and pending entries.</p>
            </div>
            <div className="adm-head-actions">
              <Badge tone="muted">{eventRegistrations.length} events</Badge>
              <Link className="text-link" to="/manage/events">
                Manage events →
              </Link>
            </div>
          </div>
          {eventRegistrations.length ? (
            <div className="adm-table-wrap">
              <table className="adm-table">
                <thead>
                  <tr>
                    <th scope="col">Event</th>
                    <th scope="col">Status</th>
                    <th scope="col">Registrations</th>
                    <th scope="col">Filled</th>
                  </tr>
                </thead>
                <tbody>
                  {eventRegistrations.map((row) => {
                    const pct = row.capacity
                      ? Math.min(100, Math.round((row.count / row.capacity) * 100))
                      : 0;
                    return (
                      <tr key={row.id}>
                        <td>
                          <b>{row.title}</b>
                          <div className="table-sub">
                            {row.capacity ? `${row.capacity} ${row.capacityUnit}` : 'Unlimited'}
                          </div>
                        </td>
                        <td>
                          <StatusBadge status={row.status} />
                        </td>
                        <td>{row.count}</td>
                        <td style={{ minWidth: 130 }}>
                          <div className="adm-progress">
                            <i style={{ width: `${pct}%` }} />
                          </div>
                          <div className="table-sub">{pct}%</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="adm-table-empty">No events in the catalogue yet.</div>
          )}
          {eventRegistrations.length ? (
            <div className="adm-table-empty" style={{ borderTop: '1px solid var(--adm-border)' }}>
              Showing all {eventRegistrations.length} events, including events with no registrations
              yet.
            </div>
          ) : null}
        </div>

        <div className="adm-card">
          <div className="adm-card-head">
            <div>
              <h2>Pass categories</h2>
              <p>Which pass type each attendee bought.</p>
            </div>
            <Badge tone="muted">{categoryTotal} passes</Badge>
          </div>
          {passCategories.length ? (
            <div className="adm-count-list">
              {passCategories.map((row) => {
                const pct = categoryTotal ? Math.round((row.count / categoryTotal) * 100) : 0;
                return (
                  <div className="adm-count-row" key={row.code}>
                    <div className="adm-count-meta">
                      <b>{row.name}</b>
                      <small>
                        {row.count} · {pct}%
                      </small>
                    </div>
                    <div className="adm-progress">
                      <i style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              No pass categories recorded yet.
            </p>
          )}
        </div>
      </div>

      <div className="adm-split">
        <div className="adm-card adm-table-card">
          <div className="adm-card-head">
            <div>
              <h2>Recent registrations</h2>
              <p>Latest {recent.length} passes and event sign-ups.</p>
            </div>
            <div className="adm-head-actions">
              <Badge tone="muted">{data?.registrationsConfirmed ?? 0} confirmed</Badge>
              <Link className="text-link" to="/manage/registrations">
                View all →
              </Link>
            </div>
          </div>
          {recent.length ? (
            <div className="adm-table-wrap">
              <table className="adm-table">
                <thead>
                  <tr>
                    <th scope="col">Attendee</th>
                    <th scope="col">Registration</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.slice(0, 8).map((row, index) => (
                    <tr key={`${row.id || row.registrationNumber || index}`}>
                      <td>
                        <b>{row.userName || row.participantName || row.name || 'Participant'}</b>
                        <div className="table-sub">
                          {row.registrationNumber || 'Convention pass'}
                        </div>
                      </td>
                      <td>{row.eventTitle || row.event || 'Convention pass'}</td>
                      <td>
                        <StatusBadge status={row.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="adm-table-empty">No registrations recorded yet.</div>
          )}
        </div>

        <div className="adm-stack">
          <div className="adm-card">
            <div className="adm-card-head">
              <div>
                <h2>Quick actions</h2>
              </div>
            </div>
            <div className="adm-action-list">
              <Link className="adm-action" to="/manage/check-in">
                <ClipboardCheck />
                <span>Open check-in door desk</span>
              </Link>
              <Link className="adm-action" to="/manage/registrations">
                <Ticket />
                <span>Browse registrations</span>
              </Link>
              <Link className="adm-action" to="/manage/registrations?status=cancelled">
                <Wallet />
                <span>Cancellations &amp; refunds</span>
                <em>{data?.registrationsCancelled ?? 0}</em>
              </Link>
              <Link className="adm-action" to="/manage/events">
                <CalendarDays />
                <span>Manage event catalogue</span>
              </Link>
              <Link className="adm-action" to="/manage/policy">
                <ShieldCheck />
                <span>Pricing &amp; pass policy</span>
              </Link>
              <Link className="adm-action" to="/manage/settings">
                <Settings />
                <span>Edition settings</span>
              </Link>
            </div>
          </div>

          <div className="adm-card">
            <div className="adm-card-head">
              <div>
                <h2>Capacity</h2>
                <p>
                  {seatsTaken} of {seatsCapacity || 'unlimited'} seats taken.
                </p>
              </div>
            </div>
            <div className="adm-progress-row">
              <div className="adm-progress-meta">
                <span>Overall occupancy</span>
                <b>{capacityPct}%</b>
              </div>
              <div className="adm-progress">
                <i style={{ width: `${capacityPct}%` }} />
              </div>
            </div>
            {units.map(([unit, taken]) => {
              const unitCapacity = data?.capacityByUnit?.[unit] ?? 0;
              const pct = unitCapacity
                ? Math.min(100, Math.round((taken / unitCapacity) * 100))
                : 0;
              return (
                <div className="adm-progress-row" key={unit} style={{ marginTop: 12 }}>
                  <div className="adm-progress-meta">
                    <span style={{ textTransform: 'capitalize' }}>{unit}</span>
                    <b>
                      {taken}
                      {unitCapacity ? ` / ${unitCapacity}` : ''}
                    </b>
                  </div>
                  <div className="adm-progress">
                    <i style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
            <div className="adm-progress-row" style={{ marginTop: 14 }}>
              <div className="adm-progress-meta">
                <span>Door check-in</span>
                <b>
                  {checkedIn} / {passesSold}
                </b>
              </div>
              <div className="adm-progress">
                <i style={{ width: `${checkRate}%` }} />
              </div>
            </div>
          </div>

          <div className="adm-card">
            <div className="adm-card-head">
              <div>
                <h2>Catalogue</h2>
                <p>Published events and latest day sales.</p>
              </div>
            </div>
            <div className="adm-card-head" style={{ marginBottom: 0 }}>
              <div className="adm-progress-meta" style={{ width: '100%' }}>
                <span>Events published</span>
                <b>
                  {data?.eventsPublished ?? 0} / {data?.eventsTotal ?? 0}
                </b>
              </div>
            </div>
            <div className="adm-progress-row" style={{ marginTop: 12 }}>
              <div className="adm-progress-meta">
                <span>Latest day sales</span>
                <b>{money(sales.at(-1)?.amountPaise || 0)}</b>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function formFromEvent(item) {
  if (!item) {
    return {
      slug: '',
      title: '',
      summary: '',
      categoryId: '',
      format: 'individual',
      teamMinSize: 2,
      teamMaxSize: 4,
      baseValue: '',
      addonPrice: '',
      capacity: 50,
      capacityUnit: 'participants',
      status: 'published',
      accent: 'cyan',
      startsAt: '',
      endsAt: '',
      venueRoom: '',
      registrationOpensAt: '',
      registrationClosesAt: '',
      descriptionMd: '',
      rulesMd: '',
      prizesMd: '',
      soloGuideMd: '',
      teamGuideMd: '',
      isFeatured: false,
      includedEligible: true,
      requiresApproval: false,
      sortOrder: 0,
      addonChargeBasis: 'per_participant',
      teamFeeBasis: 'per_participant',
      iconId: null,
      bannerUrl: '',
    };
  }
  return {
    slug: item.slug || '',
    title: item.title || '',
    summary: item.summary || '',
    categoryId: item.categoryId || '',
    format: item.format || 'individual',
    teamMinSize: item.teamMinSize ?? 2,
    teamMaxSize: item.teamMaxSize ?? 4,
    baseValue: rupees(item.baseValuePaise),
    addonPrice: rupees(item.addonPricePaise),
    capacity: item.capacity ?? 50,
    capacityUnit: item.capacityUnit || 'participants',
    status: item.status || 'draft',
    accent: item.accent || 'cyan',
    startsAt: toLocalInput(item.startsAt),
    endsAt: toLocalInput(item.endsAt),
    venueRoom: item.venueRoom || '',
    registrationOpensAt: toLocalInput(item.registrationOpensAt),
    registrationClosesAt: toLocalInput(item.registrationClosesAt),
    descriptionMd: item.descriptionMd || '',
    rulesMd: item.rulesMd || '',
    prizesMd: item.prizesMd || '',
    soloGuideMd: item.soloGuideMd || '',
    teamGuideMd: item.teamGuideMd || '',
    isFeatured: Boolean(item.isFeatured),
    includedEligible: item.includedEligible !== false,
    requiresApproval: Boolean(item.requiresApproval),
    sortOrder: item.sortOrder ?? 0,
    addonChargeBasis: item.addonChargeBasis || 'per_participant',
    teamFeeBasis: item.teamFeeBasis || 'per_participant',
    iconId: item.iconId || null,
    bannerUrl: item.bannerUrl || '',
  };
}

function EventForm({ editionId, categories, initial, onDone, onClose }) {
  const [form, setForm] = useState(() => {
    const f = formFromEvent(initial);
    if (!f.categoryId && categories?.[0]?.id) f.categoryId = categories[0].id;
    return f;
  });
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [iconsList, setIconsList] = useState([]);
  const [uploadingIcon, setUploadingIcon] = useState(false);

  useEffect(() => {
    setForm(formFromEvent(initial));
  }, [initial]);

  useEffect(() => {
    if (editionId) {
      adminApi
        .icons(editionId)
        .then((res) => {
          setIconsList(res.data || []);
        })
        .catch(() => {});
    }
  }, [editionId]);

  const handleIconUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingIcon(true);
    setMessage(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('name', file.name.replace(/\.[^/.]+$/, ''));
      const res = await adminApi.uploadIcon(editionId, fd);
      if (res.data?.id) {
        set('iconId', res.data.id);
        setMessage({ tone: 'success', text: `Uploaded and attached icon: ${res.data.name}` });
        const refreshed = await adminApi.icons(editionId);
        setIconsList(refreshed.data || []);
      }
    } catch (err) {
      setMessage({ tone: 'error', text: err.message || 'Failed to upload icon image.' });
    } finally {
      setUploadingIcon(false);
      e.target.value = '';
    }
  };

  const [uploadingBanner, setUploadingBanner] = useState(false);

  const handleBannerUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingBanner(true);
    setMessage(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await adminApi.uploadBanner(editionId, fd);
      const url = res.data?.url || res.url;
      if (url) {
        set('bannerUrl', url);
        setMessage({ tone: 'success', text: `Uploaded banner to Supabase storage: ${file.name}` });
      } else {
        throw new Error('No storage URL returned');
      }
    } catch (err) {
      setMessage({ tone: 'error', text: err.message || 'Failed to upload banner to storage.' });
    } finally {
      setUploadingBanner(false);
      e.target.value = '';
    }
  };

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const payload = {
        categoryId: form.categoryId || categories[0]?.id,
        slug: form.slug.trim(),
        title: form.title.trim(),
        summary: form.summary.trim(),
        descriptionMd: form.descriptionMd,
        rulesMd: form.rulesMd,
        prizesMd: form.prizesMd,
        soloGuideMd: form.soloGuideMd,
        teamGuideMd: form.teamGuideMd,
        format: form.format,
        teamMinSize: Number(form.teamMinSize) || 1,
        teamMaxSize: Number(form.teamMaxSize) || 1,
        baseValuePaise: paise(form.baseValue),
        includedEligible: form.includedEligible,
        addonPricePaise: paise(form.addonPrice),
        addonChargeBasis: form.addonChargeBasis,
        teamFeeBasis: form.teamFeeBasis || 'per_participant',
        capacity: Number(form.capacity) || 0,
        capacityUnit: form.capacityUnit,
        startsAt: fromLocalInput(form.startsAt),
        endsAt: fromLocalInput(form.endsAt),
        venueRoom: form.venueRoom?.trim() || '',
        registrationOpensAt:
          fromLocalInput(form.registrationOpensAt) || fromLocalInput(form.startsAt),
        registrationClosesAt:
          fromLocalInput(form.registrationClosesAt) || fromLocalInput(form.startsAt),
        requiresApproval: form.requiresApproval,
        iconId: form.iconId || null,
        bannerUrl: resolveImageUrl(form.bannerUrl) || null,
        accent: form.accent,
        isFeatured: form.isFeatured,
        sortOrder: Number(form.sortOrder) || 0,
        status: form.status,
        changeReason: 'Updated in the staff console',
      };
      if (!payload.categoryId) throw new Error('Create or select a category first.');
      if (initial?.id) {
        await adminApi.updateEvent(editionId, initial.id, payload);
      } else {
        await adminApi.createEvent(editionId, payload);
      }
      onDone(initial?.id ? 'Event updated.' : 'Event created.');
      onClose();
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="admin-form" onSubmit={submit}>
      <FieldGrid>
        <Field label="Title">
          <input
            value={form.title}
            onChange={(event) => set('title', event.target.value)}
            required
          />
        </Field>
        <Field label="Slug" hint="lowercase-with-hyphens">
          <input
            value={form.slug}
            onChange={(event) => set('slug', event.target.value.toLowerCase())}
            pattern="[a-z0-9]+(-[a-z0-9]+)*"
            required
          />
        </Field>
        <Field label="Category">
          <select
            value={form.categoryId}
            onChange={(event) => set('categoryId', event.target.value)}
            required
          >
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category?.name || 'Category'}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Event Banner (Supabase, Google Drive, or Custom URL)"
          hint="Upload image or paste a direct image or Google Drive share link (16:10 / 16:9 landscape recommended)"
        >
          <div className="banner-input-wrap">
            <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
              <input
                type="url"
                placeholder="https://drive.google.com/file/d/... or https://..."
                value={form.bannerUrl || ''}
                onChange={(e) => set('bannerUrl', e.target.value)}
                style={{ flex: 1 }}
              />
              <label
                className="btn-upload-file"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '0 14px',
                  height: '40px',
                  background: 'rgba(56,189,248,0.12)',
                  border: '1px solid rgba(56,189,248,0.35)',
                  borderRadius: '6px',
                  color: '#38bdf8',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                }}
              >
                <Upload size={14} />
                <span>{uploadingBanner ? 'Uploading...' : 'Upload Banner'}</span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/avif"
                  onChange={handleBannerUpload}
                  disabled={uploadingBanner}
                  style={{ display: 'none' }}
                />
              </label>
            </div>
            {form.bannerUrl ? (
              <div
                style={{
                  position: 'relative',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  border: '1px solid rgba(255,255,255,0.15)',
                  maxHeight: '120px',
                }}
              >
                <img
                  src={resolveImageUrl(form.bannerUrl)}
                  alt="Banner preview"
                  referrerPolicy="no-referrer"
                  style={{ width: '100%', height: '120px', objectFit: 'cover', display: 'block' }}
                  onError={(e) => {
                    e.target.style.display = 'none';
                  }}
                />
                <button
                  type="button"
                  className="btn-clear-icon"
                  style={{
                    position: 'absolute',
                    top: '8px',
                    right: '8px',
                    background: 'rgba(0,0,0,0.75)',
                    color: '#fff',
                    border: '1px solid rgba(255,255,255,0.2)',
                    padding: '4px 10px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '11px',
                  }}
                  onClick={() => set('bannerUrl', '')}
                >
                  Remove banner
                </button>
              </div>
            ) : null}
          </div>
        </Field>
        <Field label="Format">
          <select value={form.format} onChange={(event) => set('format', event.target.value)}>
            <option value="individual">Individual</option>
            <option value="team">Team</option>
          </select>
        </Field>
        <Field label="Starts at">
          <input
            type="datetime-local"
            value={form.startsAt}
            onChange={(event) => set('startsAt', event.target.value)}
            required
          />
        </Field>
        <Field label="Ends at">
          <input
            type="datetime-local"
            value={form.endsAt}
            onChange={(event) => set('endsAt', event.target.value)}
            required
          />
        </Field>
        <Field label="Venue room">
          <input
            value={form.venueRoom}
            onChange={(event) => set('venueRoom', event.target.value)}
          />
        </Field>
        <Field label="Accent">
          <select value={form.accent} onChange={(event) => set('accent', event.target.value)}>
            {ACCENTS.map((accent) => (
              <option key={accent} value={accent}>
                {accent}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Event Icon / Artwork"
          hint="Select from catalog or upload an image file"
          className="full-span"
        >
          <div className="icon-selector-wrap">
            <div className="icon-preview-box">
              {form.iconId ? (
                <img
                  src={publicApi.iconUrl(form.iconId)}
                  alt="Selected event icon"
                  className="icon-preview-img"
                />
              ) : (
                <span className="icon-preview-empty">No custom icon</span>
              )}
            </div>
            <div className="icon-controls">
              <select
                value={form.iconId || ''}
                onChange={(e) => set('iconId', e.target.value || null)}
                className="icon-select"
              >
                <option value="">No custom icon (uses category fallback)</option>
                {iconsList.map((ic) => (
                  <option key={ic.id} value={ic.id}>
                    {ic.name} ({ic.mime?.split('/')[1] || 'image'})
                  </option>
                ))}
              </select>
              <div className="icon-btn-row">
                <label className="btn-upload-file">
                  <Upload size={14} />
                  <span>{uploadingIcon ? 'Uploading...' : 'Upload Image / SVG'}</span>
                  <input
                    type="file"
                    accept="image/png,image/svg+xml,image/webp,image/jpeg"
                    onChange={handleIconUpload}
                    disabled={uploadingIcon}
                    style={{ display: 'none' }}
                  />
                </label>
                {form.iconId ? (
                  <button
                    type="button"
                    className="btn-clear-icon"
                    onClick={() => set('iconId', null)}
                  >
                    Clear icon
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </Field>
        <Field label="Included base value (₹)">
          <input
            type="number"
            min="0"
            step="50"
            value={form.baseValue}
            onChange={(event) => set('baseValue', event.target.value)}
          />
        </Field>
        <Field label="Add-on fee (₹)">
          <input
            type="number"
            min="0"
            step="50"
            value={form.addonPrice}
            onChange={(event) => set('addonPrice', event.target.value)}
          />
        </Field>
        <Field label="Add-on charge basis">
          <select
            value={form.addonChargeBasis}
            onChange={(event) => set('addonChargeBasis', event.target.value)}
          >
            <option value="per_participant">Per participant</option>
            <option value="per_team">Per team</option>
          </select>
        </Field>
        <Field label="Team fee basis">
          <select
            value={form.teamFeeBasis}
            onChange={(event) => set('teamFeeBasis', event.target.value)}
          >
            <option value="per_participant">Per participant</option>
            <option value="per_team">Per team</option>
          </select>
        </Field>
        <Field label="Team min size">
          <input
            type="number"
            min="1"
            value={form.teamMinSize}
            onChange={(event) => set('teamMinSize', event.target.value)}
          />
        </Field>
        <Field label="Team max size">
          <input
            type="number"
            min="1"
            value={form.teamMaxSize}
            onChange={(event) => set('teamMaxSize', event.target.value)}
          />
        </Field>
        <Field label="Capacity">
          <input
            type="number"
            min="0"
            value={form.capacity}
            onChange={(event) => set('capacity', event.target.value)}
          />
        </Field>
        <Field label="Capacity unit">
          <select
            value={form.capacityUnit}
            onChange={(event) => set('capacityUnit', event.target.value)}
          >
            <option value="participants">Participants</option>
            <option value="entries">Entries</option>
          </select>
        </Field>
        <Field label="Registration opens">
          <input
            type="datetime-local"
            value={form.registrationOpensAt}
            onChange={(event) => set('registrationOpensAt', event.target.value)}
          />
        </Field>
        <Field label="Registration closes">
          <input
            type="datetime-local"
            value={form.registrationClosesAt}
            onChange={(event) => set('registrationClosesAt', event.target.value)}
          />
        </Field>
        <Field label="Status" hint="Must be Published or Open to appear on the public website">
          <select value={form.status} onChange={(event) => set('status', event.target.value)}>
            <option value="published">Published (live and active)</option>
            <option value="open">Open (accepting entries)</option>
            <option value="draft">Draft (hidden from public)</option>
            <option value="closed">Closed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </Field>
        <Field label="Sort order">
          <input
            type="number"
            value={form.sortOrder}
            onChange={(event) => set('sortOrder', event.target.value)}
          />
        </Field>
      </FieldGrid>
      <Field label="Summary" className="full-span">
        <textarea
          rows="2"
          value={form.summary}
          onChange={(event) => set('summary', event.target.value)}
          placeholder="Brief 1-2 sentence overview for cards and public previews"
          required
        />
      </Field>
      <Field
        label="Description (Markdown)"
        className="full-span"
        hint="Detailed agenda, eligibility, and instructions"
      >
        <textarea
          rows="4"
          value={form.descriptionMd}
          onChange={(event) => set('descriptionMd', event.target.value)}
          placeholder="Write in Markdown. Detailed breakdown of the event, schedule, and guidelines..."
        />
      </Field>
      <Field
        label="Rules (Markdown)"
        className="full-span"
        hint="Code of conduct and evaluation criteria"
      >
        <textarea
          rows="3"
          value={form.rulesMd}
          onChange={(event) => set('rulesMd', event.target.value)}
          placeholder="1. General guidelines&#10;2. Round structure and timing&#10;3. Judging criteria..."
        />
      </Field>
      <Field
        label="Prizes (Markdown)"
        className="full-span"
        hint="Cash rewards, certificates, or perks"
      >
        <textarea
          rows="2"
          value={form.prizesMd}
          onChange={(event) => set('prizesMd', event.target.value)}
          placeholder="1st Prize: ₹10,000&#10;2nd Prize: ₹5,000&#10;Certificates for all finalists"
        />
      </Field>
      <Field
        label="Solo participation guide (Markdown)"
        className="full-span"
        hint="What one person does and gets — shown on the event room"
      >
        <textarea
          rows="3"
          value={form.soloGuideMd}
          onChange={(event) => set('soloGuideMd', event.target.value)}
          placeholder="Who it is for, what you build/solve alone, what you get..."
        />
      </Field>
      <Field
        label="Team participation guide (Markdown)"
        className="full-span"
        hint="Team size, roles, judging, who pays — shown on the event room"
      >
        <textarea
          rows="3"
          value={form.teamGuideMd}
          onChange={(event) => set('teamGuideMd', event.target.value)}
          placeholder="Ideal team size, suggested roles, how judging works..."
        />
      </Field>
      <div className="toggle-row">
        <Toggle
          checked={form.includedEligible}
          onChange={(value) => set('includedEligible', value)}
          label="Eligible for included selection"
          hint="Participants can claim this using their base pass allowance"
        />
        <Toggle
          checked={form.isFeatured}
          onChange={(value) => {
            setForm((current) => ({
              ...current,
              isFeatured: value,
              status: value && current.status === 'draft' ? 'published' : current.status,
            }));
          }}
          label="Featured on the home page"
          hint="Highlights this event on the main convention page"
        />
        <Toggle
          checked={form.requiresApproval}
          onChange={(value) => set('requiresApproval', value)}
          label="Requires coordinator approval"
          hint="Admissions require manual verification before confirmation"
        />
      </div>
      <Feedback message={message} />
      <div className="sheet-actions">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={busy} icon={Check}>
          {busy ? 'Saving' : initial?.id ? 'Save event' : 'Create event'}
        </Button>
      </div>
    </form>
  );
}

function CategoryManager({ editionId, categories, onChanged }) {
  const [form, setForm] = useState({ name: '', slug: '', accent: 'cyan', displayOrder: 0 });
  const [editId, setEditId] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const payload = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        accent: form.accent,
        displayOrder: Number(form.displayOrder) || 0,
        iconId: null,
      };
      if (editId) await adminApi.updateCategory(editionId, editId, payload);
      else await adminApi.createCategory(editionId, payload);
      setForm({ name: '', slug: '', accent: 'cyan', displayOrder: 0 });
      setEditId(null);
      onChanged();
      setMessage({ tone: 'success', text: editId ? 'Category updated.' : 'Category created.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel>
      <Eyebrow>CATEGORIES</Eyebrow>
      <div className="category-list">
        {categories.map((category) => (
          <div className="category-row" key={category.id}>
            <span>{category?.name || 'Untitled'}</span>
            <code>{category.slug}</code>
            <button
              className="table-action"
              onClick={() => {
                setEditId(category.id);
                setForm({
                  name: category.name || '',
                  slug: category.slug || '',
                  accent: category.accent || 'cyan',
                  displayOrder: category.displayOrder ?? 0,
                });
              }}
            >
              Edit
            </button>
          </div>
        ))}
      </div>
      <form className="inline-form" onSubmit={submit}>
        <Field label={editId ? 'Rename category' : 'New category'}>
          <input
            value={form.name}
            onChange={(event) =>
              setForm({
                ...form,
                name: event.target.value,
                slug: editId
                  ? form.slug
                  : event.target.value
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, '-')
                      .replace(/^-|-$/g, ''),
              })
            }
            required
          />
        </Field>
        <Field label="Slug">
          <input
            value={form.slug}
            onChange={(event) => setForm({ ...form, slug: event.target.value })}
            required
          />
        </Field>
        <Field label="Accent">
          <select
            value={form.accent}
            onChange={(event) => setForm({ ...form, accent: event.target.value })}
          >
            {ACCENTS.map((accent) => (
              <option key={accent} value={accent}>
                {accent}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit" variant="ghost" disabled={busy}>
          {editId ? 'Save' : 'Add'}
        </Button>
        {editId ? (
          <Button
            variant="ghost"
            onClick={() => {
              setEditId(null);
              setForm({ name: '', slug: '', accent: 'cyan', displayOrder: 0 });
            }}
          >
            Clear
          </Button>
        ) : null}
      </form>
      <Feedback message={message} />
    </Panel>
  );
}

export function AdminEvents() {
  const { editionId } = useSite();
  const [version, setVersion] = useState(0);
  const events = useAsync(() => adminApi.events(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  const categories = useAsync(() => adminApi.categories(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  const [sheet, setSheet] = useState(null);
  const [message, setMessage] = useState(null);
  const [busyId, setBusyId] = useState('');

  const rows = events.data?.data || [];
  const categoryRows = categories.data?.data || [];

  const openEdit = async (row) => {
    setBusyId(row.id);
    setMessage(null);
    try {
      const body = await adminApi.event(editionId, row.id);
      setSheet(body.data);
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusyId('');
    }
  };

  return (
    <>
      <SectionHead
        kicker="CATALOGUE"
        title="Events and fees"
        action={
          <Button onClick={() => setSheet({})} icon={Plus}>
            New event
          </Button>
        }
      />
      <Feedback message={message} />
      {events.loading ? <Loading label="Loading events" rows={2} /> : null}
      {events.error ? <ErrorBox error={events.error} onRetry={events.reload} /> : null}
      <DataTable
        head={['Event', 'Category', 'Format', 'Base / add-on', 'Capacity', 'Status', '']}
        empty={!rows.length && !events.loading ? 'No events yet.' : null}
      >
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {row.bannerUrl ? (
                  <img
                    src={resolveImageUrl(row.bannerUrl, 400)}
                    alt=""
                    referrerPolicy="no-referrer"
                    style={{
                      width: '44px',
                      height: '28px',
                      objectFit: 'cover',
                      borderRadius: '4px',
                      border: '1px solid rgba(255,255,255,0.15)',
                      flexShrink: 0,
                    }}
                  />
                ) : null}
                <div>
                  <b>{row.title}</b>
                  <div className="table-sub">{row.slug}</div>
                </div>
              </div>
            </td>
            <td>{row.categoryName}</td>
            <td>
              {row.format === 'team' ? `Team ${row.teamMinSize}-${row.teamMaxSize}` : 'Individual'}
            </td>
            <td>
              {money(row.baseValuePaise)}
              <div className="table-sub">{money(row.addonPricePaise)} add-on</div>
            </td>
            <td>{row.capacity || 'Unlimited'}</td>
            <td>
              <StatusBadge status={row.status} />
              {row.isFeatured ? <Badge tone="accent">Featured</Badge> : null}
            </td>
            <td>
              <div style={{ display: 'inline-flex', gap: '8px' }}>
                <a
                  href={`/events/${row.slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="table-action"
                  title="View live event page on public site"
                >
                  View
                </a>
                <button
                  className="table-action"
                  onClick={() => openEdit(row)}
                  disabled={busyId === row.id}
                >
                  {busyId === row.id ? 'Loading' : 'Edit'}
                </button>
                <Link
                  to={`/manage/registrations?eventId=${row.id}`}
                  className="table-action"
                  title="View event attendee list, cancellations & refunds"
                >
                  Registrations
                </Link>
                <Link
                  to={`/manage/check-in?eventId=${row.id}`}
                  className="table-action"
                  title="Live room attendance roster"
                >
                  Room Roster
                </Link>
              </div>
            </td>
          </tr>
        ))}
      </DataTable>

      <CategoryManager
        editionId={editionId}
        categories={categoryRows}
        onChanged={() => {
          setVersion((value) => value + 1);
          events.reload();
          categories.reload();
        }}
      />

      <Sheet
        open={sheet !== null}
        title={sheet?.id ? 'Edit event' : 'New event'}
        onClose={() => setSheet(null)}
        wide
      >
        {sheet !== null ? (
          <EventForm
            editionId={editionId}
            categories={categoryRows}
            initial={sheet?.id ? sheet : null}
            onDone={(text) => {
              setMessage({ tone: 'success', text });
              setVersion((value) => value + 1);
            }}
            onClose={() => setSheet(null)}
          />
        ) : null}
      </Sheet>
    </>
  );
}

function DbPlaygroundSection({ editionId, events = [], onSeeded }) {
  const { roles } = useAuth();
  const isSuperOrEditionAdmin = roles.some((r) => r === 'super_admin' || r === 'edition_admin');

  const [emailOrId, setEmailOrId] = useState('');
  const [target, setTarget] = useState('both');
  const [selectedEvents, setSelectedEvents] = useState([]);
  const [reason, setReason] = useState('');
  const [paymentRef, setPaymentRef] = useState('');
  const [markApproved, setMarkApproved] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isSuperOrEditionAdmin) {
    return null;
  }

  const toggleEvent = (eid) => {
    setSelectedEvents((prev) =>
      prev.includes(eid) ? prev.filter((id) => id !== eid) : [...prev, eid],
    );
  };

  const handleSeed = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    if (
      !window.confirm(
        'Seed passes or registrations directly in the database? This writes real data and is audited.',
      )
    ) {
      return;
    }

    if (!emailOrId.trim()) {
      setError('Please provide participant email or user ID');
      return;
    }
    if (!reason.trim()) {
      setError(
        'A valid audit reason is required (e.g., Bank transaction verified on Razorpay dashboard)',
      );
      return;
    }

    setBusy(true);
    try {
      const res = await adminApi.dbPlaygroundSeed(editionId, {
        userEmailOrId: emailOrId.trim(),
        target,
        eventIds: selectedEvents,
        reason: reason.trim(),
        paymentReference: paymentRef.trim() || undefined,
        markCollegeRegApproved: markApproved,
      });
      setResult(res.data);
      if (onSeeded) onSeeded();
    } catch (err) {
      setError(err.message || 'Failed to seed database');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel id="db-playground" className="db-playground">
      <div className="panel-head-row">
        <div>
          <Eyebrow>DANGER ZONE</Eyebrow>
          <p className="muted" style={{ marginTop: 4 }}>
            Resolve payment gateway disconnects where an attendee paid via Razorpay but webhooks or
            the redirect failed to activate their pass or confirm event add-ons. Every change is
            recorded in the permanent audit log and broadcast to the Telegram ops channel.
          </p>
        </div>
        <Badge tone="bad">
          <Database size={13} strokeWidth={1.8} style={{ marginRight: 5 }} />
          Super Admin / Edition Admin only
        </Badge>
      </div>

      {error ? <InlineMessage tone="error">{error}</InlineMessage> : null}
      {result ? (
        <InlineMessage tone="success">
          <b>Successfully restored.</b> Actions: {result.actions?.join(' · ')} for attendee{' '}
          {result.userName} ({result.userEmail}).
        </InlineMessage>
      ) : null}

      <form className="admin-form db-playground-form" onSubmit={handleSeed}>
        <FieldGrid>
          <Field label="Attendee email or user ID" hint="The account that paid.">
            <input
              type="text"
              value={emailOrId}
              onChange={(e) => setEmailOrId(e.target.value)}
              placeholder="e.g. attendee@college.edu"
              required
            />
          </Field>

          <Field label="Recovery target" hint="What should be activated for this attendee.">
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="both">Both (pass + selected events)</option>
              <option value="pass">Convention pass only</option>
              <option value="event">Event registration(s) only</option>
            </select>
          </Field>
        </FieldGrid>

        <FieldGrid>
          <Field
            label="Razorpay payment ID / transaction ref"
            hint="Optional — helps the auditor match the payment."
          >
            <input
              type="text"
              value={paymentRef}
              onChange={(e) => setPaymentRef(e.target.value)}
              placeholder="e.g. pay_Q8w9xY123abc or bank UTR"
            />
          </Field>

          <Field
            label="Justification / audit reason"
            hint="Required. Shown in the audit log and ops channel."
          >
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Verified captured payment on Razorpay portal"
              required
            />
          </Field>
        </FieldGrid>

        <Toggle
          checked={markApproved}
          onChange={setMarkApproved}
          label="Mark the college registration paid & approved"
          hint="Skips manual verification for this attendee."
        />

        {target !== 'pass' && events.length > 0 ? (
          <Field label="Events to seed / confirm" hint={`${selectedEvents.length} selected`}>
            <div className="db-event-picker">
              {events.map((ev) => (
                <label key={ev.id} className="db-event-option">
                  <input
                    type="checkbox"
                    checked={selectedEvents.includes(ev.id)}
                    onChange={() => toggleEvent(ev.id)}
                  />
                  <span>{ev.title}</span>
                </label>
              ))}
            </div>
          </Field>
        ) : null}

        <div className="sheet-actions">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setEmailOrId('');
              setPaymentRef('');
              setReason('');
              setSelectedEvents([]);
              setResult(null);
              setError(null);
            }}
            disabled={busy}
          >
            Clear
          </Button>
          <Button type="submit" variant="danger" loading={busy} icon={Database}>
            {busy ? 'Restoring & broadcasting' : 'Seed & confirm in database'}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

export function AdminDbPlayground() {
  const { editionId } = useSite();
  const [version, setVersion] = useState(0);
  const events = useAsync(() => adminApi.events(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  const rows = events.data?.data || [];

  return (
    <>
      <SectionHead
        kicker="DEVELOPMENT & TESTING"
        title="Database Playground"
        subtitle="Seed test registrations, simulate transactions, and inspect database state in isolation."
      />
      <DbPlaygroundSection
        editionId={editionId}
        events={rows}
        onSeeded={() => {
          setVersion((value) => value + 1);
          events.reload();
        }}
      />
    </>
  );
}

export function AdminPolicy() {
  const { editionId } = useSite();
  const policies = useAsync(() => adminApi.policies(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const rows = policies.data?.data || [];
  const current = rows.find((row) => row.isCurrent) || rows[0];
  const [form, setForm] = useState(null);
  const [check, setCheck] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!current) {
      if (!policies.loading && rows.length === 0) {
        setForm({
          passPrice: '500',
          includedEventCount: 3,
          mode: 'up_to',
          cap: '450',
          capInclusive: true,
          allowancePackOrder: 0,
          lunchDays: ['day1', 'day2'],
          addonRequiresPass: true,
          teamMembersRequirePass: true,
          holdMinutes: 15,
          deadline: '',
          teamFeeBasisDefault: 'per_participant',
          gstNote: 'Inclusive of all applicable taxes',
          platformFeePercent: '0',
          platformFeeExemptUnder: '0',
          reason: 'Initial policy setup',
        });
      }
      return;
    }
    setForm({
      passPrice: rupees(current.passPricePaise),
      includedEventCount: current.includedEventCount,
      mode: current.includedSelectionMode,
      cap: current.includedValueCapPaise != null ? rupees(current.includedValueCapPaise) : '',
      capInclusive: current.capInclusive,
      allowancePackOrder: Number(current.allowancePackOrder ?? 0),
      lunchDays: current.lunchIncludedDays || [],
      addonRequiresPass: current.addonRequiresPass,
      teamMembersRequirePass: current.teamMembersRequirePass,
      holdMinutes: current.holdMinutes,
      deadline: toLocalInput(current.selectionChangeDeadline),
      teamFeeBasisDefault: current.teamFeeBasisDefault || 'per_participant',
      gstNote: current.gstNote || '',
      platformFeePercent: current.platformFeeBps ? String(current.platformFeeBps / 100) : '0',
      platformFeeExemptUnder: current.platformFeeExemptUnderPaise
        ? rupees(current.platformFeeExemptUnderPaise)
        : '0',
      reason: '',
    });
  }, [current?.id]);

  const set = (key, value) => setForm((value_) => ({ ...value_, [key]: value }));

  const payloadFrom = () => ({
    passPricePaise: paise(form.passPrice),
    includedEventCount: form.includedEventCount === '' ? 0 : Number(form.includedEventCount),
    includedSelectionMode: form.mode,
    includedValueCapPaise: form.cap === '' || form.cap == null ? null : paise(form.cap),
    capInclusive: form.capInclusive,
    allowancePackOrder: Number(form.allowancePackOrder ?? 0),
    lunchIncludedDays: form.lunchDays,
    addonRequiresPass: form.addonRequiresPass,
    teamMembersRequirePass: form.teamMembersRequirePass,
    teamFeeBasisDefault: form.teamFeeBasisDefault,
    holdMinutes: Number(form.holdMinutes) || 15,
    selectionChangeDeadline: fromLocalInput(form.deadline),
    gstNote: form.gstNote || null,
    platformFeeBps: Math.max(0, Math.min(2500, Math.round((Number(form.platformFeePercent) || 0) * 100))),
    platformFeeExemptUnderPaise: form.platformFeeExemptUnder ? paise(form.platformFeeExemptUnder) : 0,
    reason: form.reason || 'Updated in the staff console',
  });

  const validate = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const body = await adminApi.checkPolicy(editionId, payloadFrom());
      setCheck(body.data);
      setMessage({
        tone: body.data?.ok ? 'success' : 'error',
        text: body.data?.ok
          ? 'Policy check passed. You can publish this version.'
          : 'Policy check found blocking issues.',
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const payload = payloadFrom();
      if (!check?.ok) {
        const checkRes = await adminApi.checkPolicy(editionId, payload);
        setCheck(checkRes.data);
        if (!checkRes.data?.ok) {
          setMessage({
            tone: 'error',
            text: 'Policy check found blocking issues. Please resolve before publishing.',
          });
          setBusy(false);
          return;
        }
      }
      await adminApi.createPolicy(editionId, payload);
      await policies.reload();
      setCheck(null);
      setMessage({ tone: 'success', text: 'New policy version published.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy(false);
    }
  };

  const deleteVersion = async (row) => {
    setBusy(true);
    setMessage(null);
    try {
      await adminApi.deletePolicy(editionId, row.id);
      await policies.reload();
      setMessage({ tone: 'success', text: `Deleted policy v${row.version}.` });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy(false);
    }
  };

  if (policies.loading || !form) return <Loading label="Loading policies" rows={2} />;
  if (policies.error) return <ErrorBox error={policies.error} onRetry={policies.reload} />;

  return (
    <>
      <SectionHead kicker="PRICING RULES" title="Edition policy" />
      <Feedback message={message} />
      {check ? (
        <Panel>
          <Eyebrow>POLICY CHECK</Eyebrow>
          <p className="mono-note">{check.ok ? 'PASSED' : 'BLOCKED'}</p>
          {(check.blocking || []).map((item) => (
            <InlineMessage tone="error" key={item}>
              {item}
            </InlineMessage>
          ))}
          {(check.warnings || []).map((item) => (
            <InlineMessage tone="info" key={item}>
              {item}
            </InlineMessage>
          ))}
        </Panel>
      ) : null}
      <Panel>
        <div className="banner-top">
          <Eyebrow>NEW VERSION</Eyebrow>
          <Badge tone="accent">Current v{current?.version}</Badge>
        </div>
        <FieldGrid>
          <Field
            label="Fallback pass price (₹)"
            hint="Registration tiers set what attendees actually pay. This price is only for manual passes and desk seeding."
          >
            <input
              type="number"
              min="0"
              step="50"
              value={form.passPrice}
              onChange={(event) => set('passPrice', event.target.value)}
            />
          </Field>
          <Field label="Included event count (-1 = unlimited under cap)">
            <input
              type="number"
              min="-1"
              max="20"
              value={form.includedEventCount}
              onChange={(event) => set('includedEventCount', event.target.value)}
            />
          </Field>
          <Field label="Allowance packing order">
            <select
              value={String(form.allowancePackOrder ?? 0)}
              onChange={(event) => set('allowancePackOrder', Number(event.target.value))}
            >
              <option value="0">0 — Cheapest first (protects revenue)</option>
              <option value="1">1 — Expensive first (maximizes discount)</option>
            </select>
          </Field>
          <Field label="Selection mode">
            <select value={form.mode} onChange={(event) => set('mode', event.target.value)}>
              <option value="up_to">Up to</option>
              <option value="exact">Exactly</option>
            </select>
          </Field>
          <Field label="Included value cap (₹, blank = no cap)">
            <input
              type="number"
              min="0"
              step="50"
              value={form.cap}
              placeholder="No cap"
              onChange={(event) => set('cap', event.target.value)}
            />
          </Field>
          <Field label="Hold window (minutes)">
            <input
              type="number"
              min="5"
              max="120"
              value={form.holdMinutes}
              onChange={(event) => set('holdMinutes', event.target.value)}
            />
          </Field>
          <Field label="Selection deadline">
            <input
              type="datetime-local"
              value={form.deadline}
              onChange={(event) => set('deadline', event.target.value)}
            />
          </Field>
          <Field label="Default team fee basis">
            <select
              value={form.teamFeeBasisDefault}
              onChange={(event) => set('teamFeeBasisDefault', event.target.value)}
            >
              <option value="per_participant">Per participant</option>
              <option value="per_team">Per team</option>
            </select>
          </Field>
          <Field label="GST note">
            <input value={form.gstNote} onChange={(event) => set('gstNote', event.target.value)} />
          </Field>
          <Field label="Platform fee (%)" hint="0 = disabled. Applied to every paid transaction.">
            <input
              type="number"
              min="0"
              max="25"
              step="0.01"
              value={form.platformFeePercent ?? '0'}
              onChange={(event) => set('platformFeePercent', event.target.value)}
            />
          </Field>
          <Field
            label="No platform fee under (₹)"
            hint="0 = charge platform fee on all paid transactions when % > 0."
          >
            <input
              type="number"
              min="0"
              step="1"
              value={form.platformFeeExemptUnder ?? '0'}
              onChange={(event) => set('platformFeeExemptUnder', event.target.value)}
            />
          </Field>
          <Field label="Reason for change" className="full-span">
            <input
              value={form.reason}
              onChange={(event) => set('reason', event.target.value)}
              placeholder="Explain this version"
            />
          </Field>
        </FieldGrid>
        <div className="toggle-row">
          <Toggle
            checked={form.capInclusive}
            onChange={(value) => set('capInclusive', value)}
            label="Cap is inclusive"
          />
          <Toggle
            checked={form.addonRequiresPass}
            onChange={(value) => set('addonRequiresPass', value)}
            label="Add-ons require a pass"
          />
          <Toggle
            checked={form.teamMembersRequirePass}
            onChange={(value) => set('teamMembersRequirePass', value)}
            label="Every team member needs a pass"
          />
          {['day1', 'day2'].map((day) => (
            <Toggle
              key={day}
              checked={form.lunchDays.includes(day)}
              onChange={(value) =>
                set(
                  'lunchDays',
                  value ? [...form.lunchDays, day] : form.lunchDays.filter((item) => item !== day),
                )
              }
              label={`Lunch on ${day === 'day1' ? 'day one' : 'day two'}`}
            />
          ))}
        </div>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={validate} disabled={busy}>
            Run policy check
          </Button>
          <Button onClick={publish} disabled={busy} icon={Check}>
            {check?.ok ? 'Publish version' : 'Check & publish'}
          </Button>
        </div>
      </Panel>

      <DataTable
        head={['Version', 'Fallback pass', 'Included', 'Cap', 'Mode', 'Published', 'Reason', '']}
      >
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              v{row.version} {row.isCurrent ? <Badge tone="good">Current</Badge> : null}
            </td>
            <td>{money(row.passPricePaise)}</td>
            <td>{row.includedEventCount}</td>
            <td>
              {row.includedValueCapPaise != null ? money(row.includedValueCapPaise) : 'No cap'}
            </td>
            <td>{row.includedSelectionMode}</td>
            <td>{date(row.createdAt)}</td>
            <td>{row.reason || '-'}</td>
            <td style={{ textAlign: 'right' }}>
              {!row.isCurrent ? (
                <button
                  type="button"
                  title={`Delete policy v${row.version}`}
                  disabled={busy}
                  onClick={() => deleteVersion(row)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#f87171',
                    cursor: busy ? 'not-allowed' : 'pointer',
                    padding: '4px 6px',
                    borderRadius: '6px',
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}
                >
                  <Trash2 size={15} />
                </button>
              ) : null}
            </td>
          </tr>
        ))}
      </DataTable>
    </>
  );
}

export function AdminTeams() {
  const { editionId } = useSite();
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');
  const teams = useAsync(
    () => adminApi.teams(editionId, statusFilter ? { status: statusFilter } : {}),
    [editionId, statusFilter],
    { enabled: Boolean(editionId) },
  );

  const rows = (teams.data?.data || []).filter((t) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return (
      t.name.toLowerCase().includes(q) ||
      t.eventTitle.toLowerCase().includes(q) ||
      t.leaderName.toLowerCase().includes(q) ||
      t.leaderEmail.toLowerCase().includes(q) ||
      (t.inviteCode || '').toLowerCase().includes(q)
    );
  });

  const toggleLock = async (team) => {
    setBusy(`lock-${team.id}`);
    setMessage(null);
    try {
      await adminApi.toggleTeamLock(editionId, team.id);
      await teams.reload();
      setMessage({
        tone: 'success',
        text: team.status === 'locked' ? `Unlocked ${team.name}.` : `Locked ${team.name}.`,
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const disband = async (team) => {
    if (
      !window.confirm(
        `Disband team "${team.name}"? All members' seats and tickets will be revoked and paid fees refunded.`,
      )
    ) {
      return;
    }
    setBusy(`disband-${team.id}`);
    setMessage(null);
    try {
      await adminApi.disbandTeam(editionId, team.id);
      await teams.reload();
      setMessage({ tone: 'success', text: `Team ${team.name} disbanded and seats revoked.` });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  return (
    <>
      <SectionHead
        kicker="Team Events"
        title="Teams & rosters"
        action={
          <Button
            variant="ghost"
            icon={RefreshCw}
            onClick={() => teams.reload()}
            loading={teams.refreshing || teams.loading}
          >
            Refresh
          </Button>
        }
      />
      <Feedback message={message} />
      <Panel>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search team, event, leader, or invite code…"
            style={{ flex: '1 1 240px', minWidth: '200px' }}
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="locked">Locked</option>
            <option value="disbanded">Disbanded</option>
          </select>
        </div>
        {teams.loading ? <Loading label="Loading teams" rows={3} /> : null}
        {teams.error ? <ErrorBox error={teams.error} onRetry={teams.reload} /> : null}
        {!teams.loading && !rows.length ? (
          <p className="muted">No teams match the current filter.</p>
        ) : null}
        <DataTable
          head={['Team', 'Event', 'Leader', 'Members', 'Invite', 'Status', 'Actions']}
          rows={rows.map((t) => [
            <strong key="n">{t.name}</strong>,
            t.eventTitle,
            <span key="l">
              {t.leaderName}
              <br />
              <small className="muted">{t.leaderEmail}</small>
            </span>,
            <span key="m">
              {t.members.length} / {t.maxSize}
              <br />
              <small className="muted">{t.members.map((m) => m.fullName).join(', ')}</small>
            </span>,
            <code key="c">{t.inviteCode || '—'}</code>,
            <StatusBadge key="s" status={t.status} />,
            t.status !== 'disbanded' ? (
              <div key="a" style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy === `lock-${t.id}`}
                  onClick={() => toggleLock(t)}
                >
                  {t.status === 'locked' ? 'Unlock' : 'Lock'}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy === `disband-${t.id}`}
                  onClick={() => disband(t)}
                >
                  Disband
                </Button>
              </div>
            ) : (
              '—'
            ),
          ])}
        />
      </Panel>
    </>
  );
}

export function AdminRegistrations() {
  const { editionId } = useSite();
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState(searchParams.get('status') || '');
  const [selectedEventId, setSelectedEventId] = useState(searchParams.get('eventId') || '');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [forceCancelTarget, setForceCancelTarget] = useState(null);
  const [forceCancelForm, setForceCancelForm] = useState({
    reason: 'Removed from event by administration',
    issueRefund: true,
    refundMode: 'full',
    customAmount: '',
    refundReason: '',
  });
  const [refundTarget, setRefundTarget] = useState(null);
  const [refundForm, setRefundForm] = useState({
    amount: '',
    reasonNote: '',
  });
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  useEffect(() => {
    setStatus(searchParams.get('status') || '');
    setSelectedEventId(searchParams.get('eventId') || '');
    setPage(1);
  }, [searchParams]);

  const updateFilters = (newStatus, newEventId) => {
    const s = newStatus !== undefined ? newStatus : status;
    const e = newEventId !== undefined ? newEventId : selectedEventId;
    setStatus(s);
    setSelectedEventId(e);
    setPage(1);
    const params = new URLSearchParams();
    if (s) params.set('status', s);
    if (e) params.set('eventId', e);
    setSearchParams(params);
  };

  const eventsQuery = useAsync(() => adminApi.events(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const eventsList = eventsQuery.data?.data || [];

  const debounced = useDebounced(query);
  const rows = useAsync(
    () =>
      adminApi.registrations(editionId, {
        status: status || undefined,
        event_id: selectedEventId || undefined,
        q: debounced,
        page,
        page_size: 50,
      }),
    [editionId, status, selectedEventId, debounced, page],
    { enabled: Boolean(editionId) },
  );
  const list = rows.data?.data || [];
  const total = rows.data?.total ?? list.length;
  const pages = Math.max(1, Math.ceil(total / 50));

  const openForceCancel = (row) => {
    setForceCancelTarget(row);
    setForceCancelForm({
      reason: 'Removed from event by administration',
      issueRefund: Boolean(!row.isIncluded && row.feePaise > 0 && row.isRefundable),
      refundMode: 'full',
      customAmount: row.refundableAmountPaise ? String(row.refundableAmountPaise / 100) : '',
      refundReason: 'Event registration force-cancelled by admin',
    });
    setActionMessage(null);
  };

  const submitForceCancel = async () => {
    if (!forceCancelTarget) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const isPaid = !forceCancelTarget.isIncluded && forceCancelTarget.feePaise > 0;
      let refundPaise = null;
      if (isPaid && forceCancelForm.issueRefund) {
        if (forceCancelForm.refundMode === 'full') {
          refundPaise = forceCancelTarget.refundableAmountPaise;
        } else {
          const amt = Number(forceCancelForm.customAmount);
          if (isNaN(amt) || amt <= 0) {
            throw new Error('Please enter a valid refund amount greater than 0.');
          }
          refundPaise = Math.round(amt * 100);
          if (refundPaise > forceCancelTarget.feePaise) {
            throw new Error(
              `Refund cannot exceed the paid fee of ₹${forceCancelTarget.feePaise / 100}.`,
            );
          }
          if (refundPaise > forceCancelTarget.refundableAmountPaise) {
            throw new Error(
              `Refund cannot exceed the remaining refundable amount of ₹${
                forceCancelTarget.refundableAmountPaise / 100
              }.`,
            );
          }
        }
      }

      await adminApi.forceCancelEventRegistration(editionId, forceCancelTarget.id, {
        reason: forceCancelForm.reason.trim() || 'Removed from event by administration',
        issueRefund: Boolean(isPaid && forceCancelForm.issueRefund),
        refundAmountPaise: refundPaise,
        refundReasonNote: forceCancelForm.refundReason.trim() || null,
      });

      setForceCancelTarget(null);
      rows.reload();
    } catch (err) {
      setActionMessage({ tone: 'error', text: err.message });
    } finally {
      setActionBusy(false);
    }
  };

  const openRefund = (row) => {
    setRefundTarget(row);
    setRefundForm({
      amount: row.refundableAmountPaise ? String(row.refundableAmountPaise / 100) : '',
      reasonNote: 'Registration refund issued by admin',
    });
    setActionMessage(null);
  };

  const submitRefund = async () => {
    if (!refundTarget) return;
    setActionBusy(true);
    setActionMessage(null);
    try {
      const amt = Number(refundForm.amount);
      if (isNaN(amt) || amt <= 0) {
        throw new Error('Please enter a valid refund amount greater than 0.');
      }
      const amtPaise = Math.round(amt * 100);
      if (amtPaise > refundTarget.feePaise) {
        throw new Error(`Refund cannot exceed the paid fee of ₹${refundTarget.feePaise / 100}.`);
      }
      if (amtPaise > refundTarget.refundableAmountPaise) {
        throw new Error(
          `Refund cannot exceed the remaining refundable amount of ₹${
            refundTarget.refundableAmountPaise / 100
          }.`,
        );
      }

      await adminApi.refundEventRegistration(editionId, refundTarget.id, {
        amountPaise: amtPaise,
        reasonNote: refundForm.reasonNote.trim() || null,
      });

      setRefundTarget(null);
      rows.reload();
    } catch (err) {
      setActionMessage({ tone: 'error', text: err.message });
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <>
      <SectionHead kicker="Records" title="Registrations" />
      <div className="table-filters">
        <Field label="Search participant or registration">
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Name, email, PX-..., or event title..."
          />
        </Field>
        <Field label="Filter by Event">
          <select value={selectedEventId} onChange={(e) => updateFilters(status, e.target.value)}>
            <option value="">All Events</option>
            {eventsList.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.title} {ev.venueRoom ? `(Room ${ev.venueRoom})` : ''}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status filter">
          <select
            value={status}
            onChange={(event) => updateFilters(event.target.value, selectedEventId)}
          >
            <option value="">All statuses</option>
            {['confirmed', 'reserved', 'cancelled'].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
        <Button
          variant="ghost"
          onClick={rows.reload}
          icon={RefreshCw}
          loading={rows.refreshing || rows.loading}
        >
          Refresh
        </Button>
        <Button
          variant="ghost"
          icon={Download}
          onClick={() => {
            if (!list.length) return;
            const headers = [
              'Reg #',
              'Participant',
              'Email',
              'Phone',
              'College',
              'Event',
              'Type',
              'Fee (INR)',
              'Status',
              'Refund Status',
              'Cancelled By',
              'Reason',
              'Date',
            ];
            const csvRows = list.map((r) => [
              r.registrationNumber || '',
              `"${(r.userName || '').replace(/"/g, '""')}"`,
              `"${(r.userEmail || '').replace(/"/g, '""')}"`,
              `"${(r.userPhone || '').replace(/"/g, '""')}"`,
              `"${(r.userCollege || '').replace(/"/g, '""')}"`,
              `"${(r.eventTitle || '').replace(/"/g, '""')}"`,
              r.isIncluded ? 'Included (Free)' : 'Paid Add-on',
              (r.feePaise / 100).toFixed(2),
              r.status,
              r.refundedAmountPaise > 0
                ? `Refunded ₹${r.refundedAmountPaise / 100}`
                : r.isRefundable
                  ? 'Refund Eligible'
                  : 'N/A',
              r.cancelledBy || '',
              `"${(r.cancellationReason || '').replace(/"/g, '""')}"`,
              r.createdAt ? new Date(r.createdAt).toISOString() : '',
            ]);
            const csvContent =
              'data:text/csv;charset=utf-8,' +
              [headers.join(','), ...csvRows.map((e) => e.join(','))].join('\n');
            const encodedUri = encodeURI(csvContent);
            const link = document.createElement('a');
            link.setAttribute('href', encodedUri);
            link.setAttribute(
              'download',
              `parallax_registrations_${status || 'all'}_${Date.now()}.csv`,
            );
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
          }}
        >
          Export CSV
        </Button>
      </div>

      {/* Quick status filter tabs */}
      <div className="filter-chip-row">
        <Button
          variant={status === '' ? 'primary' : 'ghost'}
          onClick={() => updateFilters('', selectedEventId)}
        >
          All registrations
        </Button>
        <Button
          variant={status === 'confirmed' ? 'primary' : 'ghost'}
          className="adm-chip-good"
          onClick={() => updateFilters('confirmed', selectedEventId)}
        >
          Confirmed active
        </Button>
        <Button
          variant={status === 'reserved' ? 'primary' : 'ghost'}
          className="adm-chip-warn"
          onClick={() => updateFilters('reserved', selectedEventId)}
        >
          Reserved
        </Button>
        <Button
          variant={status === 'pending' ? 'primary' : 'ghost'}
          className="adm-chip-warn"
          onClick={() => updateFilters('pending', selectedEventId)}
        >
          Pending approval
        </Button>
        <Button
          variant={status === 'cancelled' ? 'primary' : 'ghost'}
          className="adm-chip-bad"
          icon={X}
          onClick={() => updateFilters('cancelled', selectedEventId)}
        >
          Cancelled &amp; removed
        </Button>
      </div>

      {actionMessage ? (
        <InlineMessage tone={actionMessage.tone}>{actionMessage.text}</InlineMessage>
      ) : null}

      {rows.loading ? <Loading label="Loading registrations" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}

      {!rows.error && (
        <DataTable
          head={['Reg #', 'Participant', 'Event', 'Type', 'Fee', 'Status', 'Date', 'Actions']}
          empty={!list.length && !rows.loading ? 'No registrations match.' : null}
        >
          {list.map((row) => (
            <tr key={row.id}>
              <td className="mono-note">{row.registrationNumber}</td>
              <td>
                <b>{row.userName}</b>
                <div className="table-sub">{row.userEmail}</div>
                {row.userCollege ? (
                  <div className="table-sub" style={{ opacity: 0.8 }}>
                    🏛️ {row.userCollege}
                  </div>
                ) : null}
              </td>
              <td>
                <b>{row.eventTitle}</b>
                {row.venueRoom ? <div className="table-sub">📍 Room {row.venueRoom}</div> : null}
              </td>
              <td>
                {row.isIncluded ? (
                  <Badge tone="muted">Included (Free)</Badge>
                ) : (
                  <Badge tone="accent">Paid Add-on</Badge>
                )}
              </td>
              <td>
                <b>{money(row.feePaise)}</b>
                {row.refundedAmountPaise > 0 ? (
                  <div className="table-sub" style={{ color: 'var(--color-good, #2bb673)' }}>
                    Refunded: {money(row.refundedAmountPaise)}
                  </div>
                ) : null}
              </td>
              <td>
                {row.status === 'confirmed' ? (
                  <Badge tone="good">Confirmed</Badge>
                ) : row.status === 'reserved' ? (
                  <Badge tone="warn">Reserved</Badge>
                ) : row.status === 'cancelled' ? (
                  <div>
                    {row.cancelledBy === 'admin' ? (
                      <Badge tone="bad">Removed by Admin</Badge>
                    ) : (
                      <Badge tone="muted">Cancelled by User</Badge>
                    )}
                    {row.cancellationReason ? (
                      <div className="table-sub" style={{ fontSize: '11px', marginTop: '2px' }}>
                        {row.cancellationReason}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <StatusBadge status={row.status} />
                )}
              </td>
              <td>{date(row.createdAt)}</td>
              <td>
                <div
                  style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}
                >
                  {row.canApprove ? (
                    <button
                      type="button"
                      className="table-action"
                      style={{ color: '#2bb673' }}
                      onClick={async () => {
                        setActionBusy(true);
                        setActionMessage(null);
                        try {
                          await adminApi.approveEventRegistration(editionId, row.id);
                          setActionMessage({ tone: 'success', text: `Approved ${row.userName} for ${row.eventTitle}.` });
                          rows.reload();
                        } catch (err) {
                          setActionMessage({ tone: 'error', text: err.message });
                        } finally {
                          setActionBusy(false);
                        }
                      }}
                    >
                      Approve
                    </button>
                  ) : null}

                  {row.canCancel ? (
                    <button
                      type="button"
                      className="table-action"
                      style={{ color: '#f87171' }}
                      onClick={() => openForceCancel(row)}
                    >
                      Force Remove
                    </button>
                  ) : null}

                  {row.status === 'cancelled' && row.isRefundable ? (
                    <button
                      type="button"
                      className="table-action"
                      style={{ color: '#38bdf8' }}
                      onClick={() => openRefund(row)}
                    >
                      Issue Refund
                    </button>
                  ) : null}

                  {row.status === 'cancelled' && row.isIncluded ? (
                    <span className="mono-note" style={{ fontSize: '11px', opacity: 0.6 }}>
                      Free (Seat Freed)
                    </span>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </DataTable>
      )}

      {/* Force Cancel Sheet */}
      <Sheet
        open={Boolean(forceCancelTarget)}
        title="Force Remove Attendee from Event"
        message={actionMessage}
        onClose={() => setForceCancelTarget(null)}
      >
        <p className="muted" style={{ marginTop: 0 }}>
          Remove <b>{forceCancelTarget?.userName}</b> from <b>{forceCancelTarget?.eventTitle}</b>?
          This immediately revokes their ticket and releases the seat for other attendees.
        </p>

        {forceCancelTarget?.isIncluded ? (
          <div
            style={{
              padding: '12px 14px',
              borderRadius: '8px',
              background: 'rgba(56, 189, 248, 0.08)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              margin: '12px 0 16px 0',
              fontSize: '13px',
              lineHeight: 1.5,
            }}
          >
            ℹ️ <b>Free Included Event Selection:</b> This registration was part of the attendee's
            pass quota with no additional fee (₹0). Removing them will release the seat immediately
            and restore their included event credit quota so they can choose another event. No
            refund is applicable.
          </div>
        ) : (
          <div
            style={{
              padding: '12px 14px',
              borderRadius: '8px',
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              margin: '12px 0 16px 0',
              fontSize: '13px',
              lineHeight: 1.5,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span className="muted">Registration Fee Paid:</span>
              <b>{money(forceCancelTarget?.feePaise || 0)}</b>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span className="muted">Available to Refund:</span>
              <b style={{ color: '#2bb673' }}>
                {money(forceCancelTarget?.refundableAmountPaise || 0)}
              </b>
            </div>

            {forceCancelTarget?.isRefundable ? (
              <div
                style={{
                  marginTop: '12px',
                  borderTop: '1px solid rgba(255,255,255,0.08)',
                  paddingTop: '10px',
                }}
              >
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={forceCancelForm.issueRefund}
                    onChange={(e) =>
                      setForceCancelForm({ ...forceCancelForm, issueRefund: e.target.checked })
                    }
                  />
                  <span>Process refund for this cancellation</span>
                </label>

                {forceCancelForm.issueRefund ? (
                  <div style={{ marginTop: '12px', paddingLeft: '24px' }}>
                    <div style={{ display: 'flex', gap: '16px', marginBottom: '10px' }}>
                      <label
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="radio"
                          name="refundMode"
                          checked={forceCancelForm.refundMode === 'full'}
                          onChange={() =>
                            setForceCancelForm({ ...forceCancelForm, refundMode: 'full' })
                          }
                        />
                        <span>Full refund ({money(forceCancelTarget.refundableAmountPaise)})</span>
                      </label>
                      <label
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="radio"
                          name="refundMode"
                          checked={forceCancelForm.refundMode === 'custom'}
                          onChange={() =>
                            setForceCancelForm({
                              ...forceCancelForm,
                              refundMode: 'custom',
                              customAmount: String(forceCancelTarget.refundableAmountPaise / 100),
                            })
                          }
                        />
                        <span>Custom amount</span>
                      </label>
                    </div>

                    {forceCancelForm.refundMode === 'custom' ? (
                      <Field
                        label={`Custom Refund Amount in ₹ (Max: ₹${
                          forceCancelTarget.refundableAmountPaise / 100
                        })`}
                        hint="Cannot exceed the paid amount"
                      >
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          max={forceCancelTarget.refundableAmountPaise / 100}
                          step="0.01"
                          value={forceCancelForm.customAmount}
                          onChange={(e) =>
                            setForceCancelForm({
                              ...forceCancelForm,
                              customAmount: e.target.value,
                            })
                          }
                        />
                      </Field>
                    ) : null}

                    <Field label="Refund Note (for records)">
                      <input
                        value={forceCancelForm.refundReason}
                        onChange={(e) =>
                          setForceCancelForm({
                            ...forceCancelForm,
                            refundReason: e.target.value,
                          })
                        }
                        placeholder="e.g. Host initiated cancellation"
                      />
                    </Field>
                  </div>
                ) : (
                  <p className="table-sub" style={{ margin: '8px 0 0 24px', color: '#f59e0b' }}>
                    ⚠️ No refund will be issued immediately. You can still issue a refund later from
                    the registrations list.
                  </p>
                )}
              </div>
            ) : (
              <p className="table-sub" style={{ margin: '8px 0 0', color: '#f59e0b' }}>
                Order is already refunded or payment was not completed.
              </p>
            )}
          </div>
        )}

        <Field
          label="Removal Reason (Visible to Attendee in Portal)"
          hint="This note will be shown to the attendee in their user portal."
        >
          <input
            value={forceCancelForm.reason}
            onChange={(e) => setForceCancelForm({ ...forceCancelForm, reason: e.target.value })}
            placeholder="Reason for removal..."
            required
          />
        </Field>

        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setForceCancelTarget(null)}>
            Keep Registration
          </Button>
          <Button
            variant="danger"
            onClick={submitForceCancel}
            disabled={actionBusy || !forceCancelForm.reason.trim()}
          >
            {actionBusy ? 'Removing...' : 'Confirm Force Removal'}
          </Button>
        </div>
      </Sheet>

      {/* Issue Refund Sheet */}
      <Sheet
        open={Boolean(refundTarget)}
        title="Issue Refund for Cancelled Registration"
        message={actionMessage}
        onClose={() => setRefundTarget(null)}
      >
        <p className="muted" style={{ marginTop: 0 }}>
          Refund for <b>{refundTarget?.userName}</b> · {refundTarget?.eventTitle}
        </p>

        <div
          style={{
            padding: '12px 14px',
            borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.04)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            margin: '12px 0 16px 0',
            fontSize: '13px',
            lineHeight: 1.5,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span className="muted">Registration Fee Paid:</span>
            <b>{money(refundTarget?.feePaise || 0)}</b>
          </div>
          {refundTarget?.refundedAmountPaise > 0 ? (
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span className="muted">Already Refunded:</span>
              <span style={{ color: '#2bb673' }}>
                {money(refundTarget?.refundedAmountPaise || 0)}
              </span>
            </div>
          ) : null}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span className="muted">Max Refundable Amount:</span>
            <b style={{ color: '#38bdf8' }}>{money(refundTarget?.refundableAmountPaise || 0)}</b>
          </div>
        </div>

        <Field
          label={`Refund Amount in ₹ (Max: ₹${(refundTarget?.refundableAmountPaise || 0) / 100})`}
          hint="Defaults to full refundable amount. Strictly capped at paid fee."
        >
          <input
            type="number"
            min="0.01"
            step="0.01"
            max={(refundTarget?.refundableAmountPaise || 0) / 100}
            step="0.01"
            value={refundForm.amount}
            onChange={(e) => setRefundForm({ ...refundForm, amount: e.target.value })}
            required
          />
        </Field>

        <Field label="Refund Reason Note">
          <input
            value={refundForm.reasonNote}
            onChange={(e) => setRefundForm({ ...refundForm, reasonNote: e.target.value })}
            placeholder="e.g. Cancelled attendee refund"
          />
        </Field>

        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setRefundTarget(null)}>
            Cancel
          </Button>
          <Button
            onClick={submitRefund}
            disabled={
              actionBusy ||
              !refundForm.amount ||
              Number(refundForm.amount) <= 0 ||
              Number(refundForm.amount) > (refundTarget?.refundableAmountPaise || 0) / 100
            }
          >
            {actionBusy
              ? 'Processing...'
              : `Issue Refund (${money(Math.round(Number(refundForm.amount || 0) * 100))})`}
          </Button>
        </div>
      </Sheet>

      {!rows.error && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            marginTop: '12px',
          }}
        >
          <span className="table-sub">
            {total
              ? `Showing ${(page - 1) * 50 + 1}-${Math.min(page * 50, total)} of ${total}`
              : 'No registrations'}
          </span>
          {pages > 1 ? (
            <div style={{ display: 'inline-flex', gap: '8px' }}>
              <Button
                variant="ghost"
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                disabled={page <= 1}
              >
                Previous
              </Button>
              <Button
                variant="ghost"
                onClick={() => setPage((value) => Math.min(pages, value + 1))}
                disabled={page >= pages}
              >
                Next
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </>
  );
}

export function AdminUsers() {
  const { editionId } = useSite();
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query);
  const users = useAsync(
    () => adminApi.users(editionId, { q: debounced }),
    [editionId, debounced],
    {
      enabled: Boolean(editionId),
    },
  );
  const [target, setTarget] = useState(null);
  const [reason, setReason] = useState('');
  const [message, setMessage] = useState(null);
  const rows = users.data?.data || [];

  const apply = async () => {
    if (!target) return;
    setMessage(null);
    try {
      await adminApi.setUserStatus(editionId, target.id, {
        status: target.status === 'active' ? 'suspended' : 'active',
        reason: reason || null,
      });
      await users.reload();
      setMessage({ tone: 'success', text: 'User status updated.' });
      setTarget(null);
      setReason('');
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

  return (
    <>
      <SectionHead kicker="PEOPLE" title="Users" />
      <Feedback message={message} />
      <div className="table-filters">
        <Field label="Search">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name or email"
          />
        </Field>
      </div>
      {users.loading ? <Loading label="Loading users" rows={2} /> : null}
      {users.error ? <ErrorBox error={users.error} onRetry={users.reload} /> : null}
      <DataTable
        head={[
          'User & Contact',
          'College & Profile',
          'Roles',
          'Pass & Events',
          'Last Sign-In',
          'Status',
          '',
        ]}
        empty={!rows.length && !users.loading ? 'No users match.' : null}
      >
        {rows.map((row) => {
          const academic = [
            row.course,
            row.branch,
            row.yearOfStudy ? `Yr ${row.yearOfStudy}` : null,
          ]
            .filter(Boolean)
            .join(' · ');
          const location = [row.city, row.state].filter(Boolean).join(', ');
          return (
            <tr key={row.id}>
              <td>
                <b>{row.fullName}</b>
                <div className="table-sub">{row.email}</div>
                {row.phone ? <div className="table-sub">{row.phone}</div> : null}
              </td>
              <td>
                <div>{row.collegeName || '-'}</div>
                {academic ? <div className="table-sub">{academic}</div> : null}
                {location ? <div className="table-sub">{location}</div> : null}
              </td>
              <td>
                {(row.roles || []).map((role) => ROLE_LABELS[role] || role).join(', ') ||
                  'Participant'}
              </td>
              <td>
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                    alignItems: 'flex-start',
                  }}
                >
                  {row.passStatus ? (
                    <StatusBadge status={row.passStatus} />
                  ) : (
                    <span className="table-sub">No pass</span>
                  )}
                  {row.eventCount > 0 ? (
                    <span className="table-sub">
                      {row.eventCount} event{row.eventCount === 1 ? '' : 's'}
                    </span>
                  ) : null}
                </div>
              </td>
              <td>
                <span className="table-sub">
                  {row.lastLoginAt
                    ? dateTime(row.lastLoginAt)
                    : row.createdAt
                      ? dateTime(row.createdAt)
                      : '-'}
                </span>
              </td>
              <td>
                <StatusBadge status={row.status} />
              </td>
              <td>
                <button className="table-action" onClick={() => setTarget(row)}>
                  {row.status === 'active' ? 'Suspend' : 'Reactivate'}
                </button>
              </td>
            </tr>
          );
        })}
      </DataTable>
      <Sheet
        open={Boolean(target)}
        title="Change account status"
        message={message}
        onClose={() => setTarget(null)}
      >
        <p className="muted">
          {target?.status === 'active' ? 'Suspend' : 'Reactivate'} <b>{target?.fullName}</b>?
        </p>
        {target?.status === 'active' ? (
          <InlineMessage tone="warn">
            <b>Warning:</b> Suspending this account will immediately:
            <ul style={{ margin: '6px 0 0 16px', padding: 0, lineHeight: 1.5 }}>
              <li>Revoke their convention pass &amp; door check-in QR</li>
              <li>Cancel all booked event registrations and release their seats</li>
              <li>Queue refunds for any paid add-on event bookings</li>
              <li>
                Remove them from team rosters (if they lead a team, leadership is transferred to
                another member)
              </li>
              <li>Terminate active login sessions across all devices</li>
            </ul>
          </InlineMessage>
        ) : (
          <InlineMessage tone="info">
            Reactivating this account restores login access and pass status. Cancelled event seats
            will need to be re-selected if still available.
          </InlineMessage>
        )}
        <Field label="Reason">
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Shown in the audit log"
          />
        </Field>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setTarget(null)}>
            Cancel
          </Button>
          <Button onClick={apply}>Apply change</Button>
        </div>
      </Sheet>
    </>
  );
}

export function AdminPayments() {
  const { editionId } = useSite();
  const payments = useAsync(() => adminApi.payments(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const refunds = useAsync(() => adminApi.refunds(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const [target, setTarget] = useState(null);
  const [form, setForm] = useState({
    amount: '',
    reasonCode: 'requested_by_participant',
    note: '',
  });
  const [message, setMessage] = useState(null);
  const list = payments.data?.data || [];
  const refundRows = refunds.data?.data || [];

  const remainingForOrder = (orderRow) => {
    if (!orderRow) return 0;
    // Prefer the server-computed refundedPaise which already accounts for
    // pending + processing + processed refunds so we never offer to refund
    // money that is already committed (even if not yet settled).
    const committed = Number(orderRow.refundedPaise) || 0;
    return Math.max(0, (Number(orderRow.amountPaise) || 0) - committed);
  };

  const openRefund = (row) => {
    const rem = remainingForOrder(row);
    setTarget({ ...row, remainingPaise: rem });
    setForm({
      amount: rem > 0 ? String(rem / 100) : '',
      reasonCode: 'requested_by_participant',
      note: '',
    });
    setMessage(null);
  };

  const submit = async () => {
    setMessage(null);
    try {
      const amt = Number(form.amount);
      if (isNaN(amt) || amt <= 0) {
        throw new Error('Please enter a valid refund amount greater than 0.');
      }
      const amtPaise = Math.round(amt * 100);
      // Use the server-side remaining amount (which includes pending + processing
      // refunds already committed) so we never accidentally double-refund.
      const maxPaise = target?.remainingPaise ?? target?.amountPaise ?? 0;
      if (amtPaise > maxPaise) {
        throw new Error(`Refund cannot exceed the remaining refundable amount of ${money(maxPaise)}.`);
      }
      await adminApi.createRefund(editionId, {
        orderId: target.id,
        amountPaise: amtPaise,
        reasonCode: form.reasonCode,
        reasonNote: form.note || null,
      });
      await Promise.all([payments.reload(), refunds.reload()]);
      setTarget(null);
      setMessage({ tone: 'success', text: `Refund of ${money(amtPaise)} initiated.` });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

  return (
    <>
      <SectionHead kicker="FINANCE" title="Payments and refunds" />
      <Feedback message={message} />
      {payments.loading ? <Loading label="Loading payments" rows={2} /> : null}
      {payments.error ? <ErrorBox error={payments.error} onRetry={payments.reload} /> : null}
      <DataTable
        head={['Participant', 'Purpose', 'Amount', 'Refunded', 'Status', 'Created', 'Paid', '']}
        empty={!list.length && !payments.loading ? 'No payments recorded.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>
              <b>{row.userName}</b>
              <div className="table-sub">{row.userEmail}</div>
            </td>
            <td>{row.purpose}</td>
            <td>{money(row.amountPaise)}</td>
            <td>
              {Number(row.refundedPaise) > 0 ? (
                <span style={{ color: '#f87171', fontWeight: 600 }}>
                  -{money(Number(row.refundedPaise))}
                </span>
              ) : (
                <span className="muted" style={{ fontSize: '12px' }}>—</span>
              )}
            </td>
            <td>
              <StatusBadge status={row.status} />
            </td>
            <td>{date(row.createdAt)}</td>
            <td>{row.paidAt ? date(row.paidAt) : '-'}</td>
            <td>
              {row.status === 'paid' && remainingForOrder(row) > 0 ? (
                <button className="table-action" onClick={() => openRefund(row)}>
                  Refund
                </button>
              ) : row.status === 'paid' && remainingForOrder(row) <= 0 ? (
                <span className="mono-note" style={{ fontSize: '11px', opacity: 0.6 }}>
                  Fully committed
                </span>
              ) : null}
            </td>
          </tr>
        ))}
      </DataTable>

      <SectionHead kicker="LEDGER" title="Refund requests" />
      <DataTable
        head={['Order', 'Amount', 'Reason', 'Status', 'Requested', 'Processed', 'Actions']}
        empty={!refundRows.length ? 'No refunds requested.' : null}
      >
        {refundRows.map((row) => (
          <tr key={row.id}>
            <td className="mono-note">{row.orderId}</td>
            <td>{money(row.amountPaise)}</td>
            <td>
              {row.reasonCode}
              {row.reasonNote ? <div className="table-sub">{row.reasonNote}</div> : null}
            </td>
            <td>
              <StatusBadge status={row.status} />
            </td>
            <td>{date(row.createdAt)}</td>
            <td>{row.processedAt ? date(row.processedAt) : '-'}</td>
            <td>
              {row.status === 'pending' || row.status === 'failed' ? (
                <button
                  type="button"
                  className="table-action"
                  onClick={async () => {
                    setMessage(null);
                    try {
                      const res = await adminApi.processRefund(editionId, row.id);
                      const st = res.data?.status;
                      setMessage({
                        tone: 'success',
                        text:
                          st === 'processed'
                            ? `Refund of ${money(row.amountPaise)} completed.`
                            : `Refund of ${money(row.amountPaise)} initiated and processing.`,
                      });
                      await Promise.all([payments.reload(), refunds.reload()]);
                    } catch (err) {
                      setMessage({ tone: 'error', text: err.message });
                    }
                  }}
                >
                  Confirm &amp; Refund
                </button>
              ) : row.status === 'processing' ? (
                <button
                  type="button"
                  className="table-action"
                  onClick={async () => {
                    setMessage(null);
                    try {
                      const res = await adminApi.processRefund(editionId, row.id);
                      setMessage({
                        tone: 'info',
                        text: `Refund status: ${res.data?.status || 'processing'}.`,
                      });
                      await Promise.all([payments.reload(), refunds.reload()]);
                    } catch (err) {
                      setMessage({ tone: 'error', text: err.message });
                    }
                  }}
                >
                  Sync Status
                </button>
              ) : null}
            </td>
          </tr>
        ))}
      </DataTable>

      <Sheet
        open={Boolean(target)}
        title="Request a refund"
        message={message}
        onClose={() => setTarget(null)}
      >
        <p className="muted">
          {target?.userName} · {money(target?.amountPaise)} order
        </p>
        {target?.refundedPaise > 0 ? (
          <div
            style={{
              padding: '10px 12px',
              borderRadius: '6px',
              background: 'rgba(248,113,113,0.08)',
              border: '1px solid rgba(248,113,113,0.2)',
              marginBottom: '14px',
              fontSize: '13px',
            }}
          >
            <span style={{ opacity: 0.7 }}>Already refunded / committed: </span>
            <b style={{ color: '#f87171' }}>{money(target.refundedPaise)}</b>
            <span style={{ opacity: 0.7 }}> · Remaining: </span>
            <b style={{ color: '#38bdf8' }}>{money(target.remainingPaise ?? 0)}</b>
          </div>
        ) : null}
        <FieldGrid>
          <Field label="Amount (₹)">
            <input
              type="number"
              min="0.01"
              step="0.01"
              max={(target?.remainingPaise ?? target?.amountPaise ?? 0) / 100}
              value={form.amount}
              onChange={(event) => setForm({ ...form, amount: event.target.value })}
            />
          </Field>
          <Field label="Reason code">
            <select
              value={form.reasonCode}
              onChange={(event) => setForm({ ...form, reasonCode: event.target.value })}
            >
              {[
                'requested_by_participant',
                'duplicate',
                'event_cancelled',
                'payment_failed',
                'other',
              ].map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </Field>
        </FieldGrid>
        <Field label="Note">
          <input
            value={form.note}
            onChange={(event) => setForm({ ...form, note: event.target.value })}
          />
        </Field>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setTarget(null)}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={
              !form.amount ||
              Number(form.amount) <= 0 ||
              Number(form.amount) > (target?.remainingPaise ?? target?.amountPaise ?? 0) / 100
            }
            icon={CreditCard}
          >
            {form.amount && Number(form.amount) > 0
              ? `Request refund (${money(Math.round(Number(form.amount) * 100))})`
              : 'Request refund'}
          </Button>
        </div>
      </Sheet>
    </>
  );
}

export function AdminCheckin() {
  const { editionId, slug } = useSite();
  const [searchParams] = useSearchParams();
  const [token, setToken] = useState('');
  const [selectedEventId, setSelectedEventId] = useState(searchParams.get('eventId') || '');
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [facingMode, setFacingMode] = useState('environment');
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [scanStatus, setScanStatus] = useState('');
  const [rosterFilter, setRosterFilter] = useState('all');
  const [rosterSearch, setRosterSearch] = useState('');
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const scanIntervalRef = useRef(null);
  const scanBusyRef = useRef(false);
  const lastScannedRef = useRef({ code: '', at: 0 });
  const performCheckinRef = useRef(null);

  useEffect(() => {
    const evId = searchParams.get('eventId');
    if (evId) setSelectedEventId(evId);
  }, [searchParams]);

  const eventsList = useAsync(
    () => (slug ? publicApi.events(slug, { pageSize: 100 }) : Promise.resolve({ data: [] })),
    [slug],
    { enabled: Boolean(slug) },
  );

  const recent = useAsync(() => adminApi.recentCheckins(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const attendance = useAsync(() => adminApi.attendance(editionId, { day }), [editionId, day], {
    enabled: Boolean(editionId),
  });

  const isRealEvent = Boolean(selectedEventId && selectedEventId !== '__lunch__');

  const rosterAsync = useAsync(
    () =>
      isRealEvent
        ? adminApi.eventRoster(editionId, selectedEventId, { day })
        : Promise.resolve({ data: null }),
    [editionId, selectedEventId, isRealEvent, day],
    { enabled: Boolean(editionId && isRealEvent) },
  );

  const performCheckin = async (rawToken) => {
    const cleanToken = (rawToken || token || '').trim();
    if (!cleanToken) return;
    scanBusyRef.current = true;
    setBusy(true);
    setScanStatus('Checking…');
    setMessage(null);
    setResult(null);
    const isLunch = selectedEventId === '__lunch__';
    try {
      const body = await adminApi.checkin(editionId, {
        token: cleanToken,
        day: day || null,
        scope: isLunch ? 'lunch' : isRealEvent ? 'event' : 'pass',
        eventId: isRealEvent ? selectedEventId : null,
      });
      setResult(body.data);
      setToken('');
      setScanStatus(body.data?.result === 'duplicate' ? 'Already checked in' : 'Admitted ✓');
      recent.reload();
      attendance.reload();
      if (isRealEvent) {
        rosterAsync.reload();
      }
      navigator.vibrate?.(body.data?.result === 'duplicate' ? [40, 40, 40] : 80);
      // Audible chime
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, audioCtx.currentTime);
        osc.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.15);
      } catch {}
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
      setScanStatus('Entry denied');
      navigator.vibrate?.([120, 60, 120]);
    } finally {
      scanBusyRef.current = false;
      setBusy(false);
    }
  };
  performCheckinRef.current = performCheckin;

  const scan = async (event) => {
    event.preventDefault();
    await performCheckin(token);
  };

  const handleManualMark = async (userId) => {
    setMessage(null);
    try {
      await adminApi.markAttendance(editionId, {
        userId,
        eventId: selectedEventId || null,
        day,
        note: 'host_manual_roster',
      });
      if (selectedEventId) rosterAsync.reload();
      attendance.reload();
      recent.reload();
    } catch (err) {
      setMessage({ tone: 'error', text: err.message });
    }
  };

  const handleUndoAttendance = async (attendanceId) => {
    if (!attendanceId) return;
    if (
      !window.confirm(
        'Warning: This will reset this attendance record so the attendee can be scanned and marked again. Continue?',
      )
    ) {
      return;
    }
    setMessage(null);
    try {
      await adminApi.deleteAttendance(editionId, attendanceId);
      if (selectedEventId) rosterAsync.reload();
      attendance.reload();
      recent.reload();
    } catch (err) {
      setMessage({ tone: 'error', text: err.message });
    }
  };

  const toggleTorch = async () => {
    const track = streamRef.current?.getVideoTracks?.()[0];
    if (!track) return;
    const next = !torchOn;
    try {
      await track.applyConstraints({ advanced: [{ torch: next }] });
      setTorchOn(next);
    } catch {
      setTorchAvailable(false);
    }
  };

  // Camera video stream lifecycle (works across desktop & mobile via jsQR + optional BarcodeDetector)
  useEffect(() => {
    if (!cameraActive) {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      if (scanIntervalRef.current) {
        clearInterval(scanIntervalRef.current);
        scanIntervalRef.current = null;
      }
      setTorchAvailable(false);
      setTorchOn(false);
      setScanStatus('');
      return undefined;
    }

    let active = true;

    async function startCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setMessage({
          tone: 'error',
          text: 'Camera API is unavailable in this browser context. On mobile, open this page over HTTPS (or localhost) to use the camera.',
        });
        setCameraActive(false);
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        });
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const track = stream.getVideoTracks()[0];
        const caps = track?.getCapabilities?.();
        setTorchAvailable(Boolean(caps?.torch));
        setTorchOn(false);
        setScanStatus('Point camera at QR code');

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }

        const nativeDetector =
          'BarcodeDetector' in window ? new window.BarcodeDetector({ formats: ['qr_code'] }) : null;
        if (!canvasRef.current) {
          canvasRef.current = document.createElement('canvas');
        }

        scanIntervalRef.current = setInterval(async () => {
          const video = videoRef.current;
          if (!video || video.readyState < video.HAVE_CURRENT_DATA || scanBusyRef.current) {
            return;
          }
          const vw = video.videoWidth;
          const vh = video.videoHeight;
          if (!vw || !vh) return;

          let decoded = '';
          if (nativeDetector) {
            try {
              const barcodes = await nativeDetector.detect(video);
              if (barcodes?.length && barcodes[0].rawValue) {
                decoded = barcodes[0].rawValue;
              }
            } catch {
              // Fall back to jsQR below
            }
          }

          if (!decoded) {
            try {
              const maxDim = 640;
              const scale = Math.min(1, maxDim / Math.max(vw, vh));
              const cw = Math.max(1, Math.round(vw * scale));
              const ch = Math.max(1, Math.round(vh * scale));
              const canvas = canvasRef.current;
              if (canvas.width !== cw) canvas.width = cw;
              if (canvas.height !== ch) canvas.height = ch;
              const ctx = canvas.getContext('2d', { willReadFrequently: true });
              if (ctx) {
                ctx.drawImage(video, 0, 0, cw, ch);
                const img = ctx.getImageData(0, 0, cw, ch);
                const qr = jsQR(img.data, cw, ch, { inversionAttempts: 'attemptBoth' });
                if (qr?.data) decoded = qr.data;
              }
            } catch {
              // Ignore frame decode error
            }
          }

          if (decoded) {
            const now = Date.now();
            if (lastScannedRef.current.code === decoded && now - lastScannedRef.current.at < 2500) {
              return;
            }
            lastScannedRef.current = { code: decoded, at: now };
            performCheckinRef.current?.(decoded);
          }
        }, 200);
      } catch (err) {
        setMessage({
          tone: 'error',
          text: `Camera permission denied or camera unavailable: ${err.message}. You can still paste or scan using a handheld barcode scanner.`,
        });
        setCameraActive(false);
      }
    }

    startCamera();

    return () => {
      active = false;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (scanIntervalRef.current) {
        clearInterval(scanIntervalRef.current);
        scanIntervalRef.current = null;
      }
    };
  }, [cameraActive, facingMode]);

  const recentRows = recent.data?.data || [];
  const attendanceRows = attendance.data?.data || [];
  const rosterData = rosterAsync.data?.data || null;
  const rawRosterList = rosterData?.roster || [];

  const filteredRoster = rawRosterList.filter((row) => {
    if (rosterFilter === 'present' && !row.attended) return false;
    if (rosterFilter === 'pending' && row.attended) return false;
    if (rosterSearch.trim()) {
      const term = rosterSearch.trim().toLowerCase();
      const match =
        (row.userName && row.userName.toLowerCase().includes(term)) ||
        (row.userEmail && row.userEmail.toLowerCase().includes(term)) ||
        (row.registrationNumber && row.registrationNumber.toLowerCase().includes(term)) ||
        (row.userCollege && row.userCollege.toLowerCase().includes(term)) ||
        (row.teamName && row.teamName.toLowerCase().includes(term));
      if (!match) return false;
    }
    return true;
  });

  return (
    <>
      <SectionHead
        kicker="DOOR DESK &amp; EVENT CHECK-IN"
        title="Check-in &amp; Scanner Station"
        action={
          <Button
            type="button"
            variant={cameraActive ? 'danger' : 'info'}
            onClick={() => setCameraActive((v) => !v)}
            icon={cameraActive ? CameraOff : Camera}
          >
            {cameraActive ? 'Close Camera Scanner' : 'Open Camera QR Scanner'}
          </Button>
        }
      />
      <Panel className="checkin-panel">
        {/* Live Camera Scanner Box */}
        {cameraActive ? (
          <div
            style={{
              position: 'relative',
              width: '100%',
              maxWidth: '420px',
              aspectRatio: '4 / 3',
              margin: '0 auto 20px auto',
              borderRadius: '16px',
              overflow: 'hidden',
              border: '2px solid rgba(56, 189, 248, 0.55)',
              background: '#09090b',
              boxShadow: '0 12px 32px rgba(0,0,0,0.65)',
            }}
          >
            <video
              ref={videoRef}
              playsInline
              muted
              autoPlay
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
            {scanStatus ? (
              <div
                style={{
                  position: 'absolute',
                  top: '10px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  background: 'rgba(9, 9, 11, 0.82)',
                  color: '#e2e8f0',
                  border: '1px solid rgba(255,255,255,0.16)',
                  borderRadius: '999px',
                  padding: '4px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  backdropFilter: 'blur(6px)',
                }}
              >
                {scanStatus}
              </div>
            ) : null}
            {/* Visual targeting grid */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                pointerEvents: 'none',
              }}
            >
              <div
                style={{
                  width: 'min(200px, 56%)',
                  aspectRatio: '1 / 1',
                  border: '2px dashed rgba(56, 189, 248, 0.9)',
                  borderRadius: '14px',
                  boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.35)',
                }}
              />
            </div>
            {/* Camera Controls Overlay */}
            <div
              style={{
                position: 'absolute',
                bottom: '12px',
                left: '10px',
                right: '10px',
                display: 'flex',
                justifyContent: 'center',
                flexWrap: 'wrap',
                gap: '8px',
              }}
            >
              <button
                type="button"
                onClick={() => setFacingMode((m) => (m === 'environment' ? 'user' : 'environment'))}
                style={{
                  background: 'rgba(15, 23, 42, 0.88)',
                  color: '#fff',
                  border: '1px solid rgba(255,255,255,0.22)',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <FlipHorizontal size={14} /> Flip
              </button>
              {torchAvailable ? (
                <button
                  type="button"
                  onClick={toggleTorch}
                  style={{
                    background: torchOn ? 'rgba(245, 158, 11, 0.9)' : 'rgba(15, 23, 42, 0.88)',
                    color: torchOn ? '#09090b' : '#fff',
                    border: '1px solid rgba(255,255,255,0.22)',
                    borderRadius: '8px',
                    padding: '8px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Flashlight size={14} /> {torchOn ? 'Flash On' : 'Flash'}
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => setCameraActive(false)}
                style={{
                  background: 'rgba(225, 29, 72, 0.9)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '8px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <CameraOff size={14} /> Stop
              </button>
            </div>
          </div>
        ) : null}

        <form onSubmit={scan} className="checkin-form">
          <Field
            label="Check-in Station / Event"
            hint="Pick an event for workshop / competition verification, or General Pass for door turnstile admission."
          >
            <select value={selectedEventId} onChange={(e) => setSelectedEventId(e.target.value)}>
              <option value="">🎟️ General Fest Turnstile Admission (All Passes)</option>
              <option value="__lunch__">🍽️ Lunch Check-in (Kitchen / Dining Hall)</option>
              {(eventsList.data?.data || []).map((ev) => (
                <option key={ev.id} value={ev.id}>
                  🎯 {ev.title} {ev.venueRoom ? `· Room ${ev.venueRoom}` : ''} (
                  {ev.categoryName || ev.category})
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Ticket token or Registration code"
            hint="Scan QR with camera or barcode gun, or paste the attendee's code (e.g. PX-26-EA130B)."
          >
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Scan QR or paste PX-…"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="characters"
              spellCheck={false}
              required
            />
          </Field>

          <Field label="Convention Day">
            <input type="date" value={day} onChange={(event) => setDay(event.target.value)} />
          </Field>

          <Button
            type="submit"
            variant="success"
            disabled={busy || !token.trim()}
            icon={ClipboardCheck}
          >
            {busy ? 'Verifying…' : 'Admit & Check-in'}
          </Button>
        </form>

        <Feedback message={message} />

        {result ? (
          <div className={`checkin-result ${result.result}`}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 8,
              }}
            >
              <span style={{ textTransform: 'uppercase', fontWeight: 800 }}>
                {result.result === 'admitted' ? '✓ ADMITTED' : result.result}
              </span>
              <Button variant="ghost" size="small" onClick={() => setResult(null)}>
                Scan next
              </Button>
            </div>

            <h3 style={{ margin: '4px 0' }}>{result.participantName}</h3>

            {result.gender || result.foodPreference || result.needsAccommodation !== undefined ? (
              <div
                className="checkin-logistics"
                style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0' }}
              >
                {[
                  result.gender ? genderLabel(result.gender) : null,
                  result.foodPreference ? foodLabel(result.foodPreference) : null,
                  result.needsAccommodation ? 'Accommodation: yes' : 'Accommodation: no',
                ]
                  .filter(Boolean)
                  .map((label) => (
                    <span
                      key={label}
                      style={{
                        padding: '4px 10px',
                        borderRadius: 999,
                        fontSize: 12,
                        fontWeight: 700,
                        letterSpacing: '0.02em',
                        background: 'rgba(148, 163, 184, 0.18)',
                        border: '1px solid rgba(148, 163, 184, 0.35)',
                      }}
                    >
                      {label}
                    </span>
                  ))}
              </div>
            ) : null}

            {result.team ? (
              <div
                style={{
                  margin: '8px 0',
                  padding: '6px 10px',
                  borderRadius: 6,
                  background: 'rgba(56, 189, 248, 0.15)',
                  border: '1px solid rgba(56, 189, 248, 0.4)',
                  color: '#38bdf8',
                  fontWeight: 600,
                  fontSize: '13px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                👥 Team: <b>{result.team.teamName}</b>{' '}
                {result.team.isLeader ? '(Team Leader)' : '(Team Member)'}
              </div>
            ) : null}

            {result.warning ? (
              <div
                style={{
                  margin: '10px 0',
                  padding: '10px 14px',
                  borderRadius: 8,
                  background: 'rgba(234, 179, 8, 0.15)',
                  border: '1px solid rgba(234, 179, 8, 0.5)',
                  color: '#facc15',
                  fontWeight: 600,
                  fontSize: '13px',
                }}
              >
                ⚠️ {result.warning}
              </div>
            ) : null}

            <p>
              {result.eventTitle || 'Convention Pass'} ·{' '}
              {result.registrationNumber || 'Registered Attendee'} · {dateTime(result.checkedInAt)}
            </p>
            {result.message ? <p className="muted">{result.message}</p> : null}
          </div>
        ) : null}
      </Panel>

      {/* Dedicated Event Room Host Roster */}
      {selectedEventId && rosterData ? (
        <Panel style={{ marginTop: '20px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '12px',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
              paddingBottom: '14px',
              marginBottom: '16px',
            }}
          >
            <div>
              <Eyebrow>ROOM HOST LIVE ATTENDANCE ROSTER</Eyebrow>
              <h3 style={{ margin: '4px 0 2px 0' }}>{rosterData.event.title}</h3>
              <p className="table-sub" style={{ margin: 0 }}>
                {rosterData.event.venueRoom ? `📍 Room ${rosterData.event.venueRoom} · ` : ''}
                Format: {rosterData.event.format} · Capacity: {rosterData.event.capacity}
              </p>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '11px', textTransform: 'uppercase', opacity: 0.7 }}>
                  Checked In Today
                </div>
                <b style={{ fontSize: '18px', color: '#2bb673' }}>
                  {rosterData.totalAttended} / {rosterData.totalRegistered}
                </b>
              </div>
              <Button
                variant="ghost"
                size="small"
                onClick={() => rosterAsync.reload()}
                icon={RefreshCw}
                loading={rosterAsync.refreshing || rosterAsync.loading}
              >
                Refresh
              </Button>
            </div>
          </div>

          <div className="roster-toolbar">
            <div className="filter-chip-row" style={{ marginBottom: 0 }}>
              <Button
                variant={rosterFilter === 'all' ? 'primary' : 'ghost'}
                onClick={() => setRosterFilter('all')}
              >
                All ({rosterData.totalRegistered})
              </Button>
              <Button
                variant={rosterFilter === 'present' ? 'primary' : 'ghost'}
                onClick={() => setRosterFilter('present')}
              >
                Present ({rosterData.totalAttended})
              </Button>
              <Button
                variant={rosterFilter === 'pending' ? 'primary' : 'ghost'}
                onClick={() => setRosterFilter('pending')}
              >
                Pending ({rosterData.totalRegistered - rosterData.totalAttended})
              </Button>
            </div>

            <input
              type="text"
              className="toolbar-input"
              placeholder="Filter roster by attendee or team…"
              value={rosterSearch}
              onChange={(e) => setRosterSearch(e.target.value)}
            />
          </div>

          <DataTable
            head={['Participant', 'College', 'Team / Group', 'Status', 'Attendance', 'Actions']}
            empty={!filteredRoster.length ? 'No participants match the filter.' : null}
          >
            {filteredRoster.map((item) => (
              <tr key={item.registrationId}>
                <td>
                  <b>{item.userName}</b>
                  <div className="table-sub">{item.userEmail}</div>
                  <div className="mono-note" style={{ fontSize: '11px' }}>
                    {item.registrationNumber}
                  </div>
                </td>
                <td>
                  {item.userCollege ? (
                    <div style={{ fontSize: '13px' }}>{item.userCollege}</div>
                  ) : (
                    <span className="muted">-</span>
                  )}
                </td>
                <td>
                  {item.teamName ? (
                    <div>
                      <Badge tone="accent">👥 {item.teamName}</Badge>
                      {item.isTeamLeader ? (
                        <span style={{ fontSize: '11px', color: '#ff9f2e', marginLeft: '6px' }}>
                          ★ Leader
                        </span>
                      ) : null}
                    </div>
                  ) : (
                    <span className="muted">Individual</span>
                  )}
                </td>
                <td>
                  {item.status === 'confirmed' ? (
                    <Badge tone="good">Confirmed</Badge>
                  ) : item.status === 'cancelled' ? (
                    <Badge tone="bad">Cancelled</Badge>
                  ) : (
                    <StatusBadge status={item.status} />
                  )}
                </td>
                <td>
                  {item.attended ? (
                    <div>
                      <Badge tone="good">✓ Present</Badge>
                      {item.checkedInAt ? (
                        <div className="table-sub" style={{ fontSize: '11px' }}>
                          {dateTime(item.checkedInAt)}
                        </div>
                      ) : null}
                      {item.checkedInByName ? (
                        <div className="table-sub" style={{ fontSize: '11px', opacity: 0.7 }}>
                          Host: {item.checkedInByName}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <Badge tone="muted">Not Checked In</Badge>
                  )}
                </td>
                <td>
                  {item.attended ? (
                    <button
                      type="button"
                      className="table-action"
                      style={{ color: '#f87171' }}
                      onClick={() => handleUndoAttendance(item.attendanceId)}
                    >
                      Undo
                    </button>
                  ) : item.status !== 'cancelled' ? (
                    <button
                      type="button"
                      className="table-action"
                      style={{ color: '#2bb673', fontWeight: 600 }}
                      onClick={() => handleManualMark(item.userId)}
                    >
                      Mark Present
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </DataTable>
        </Panel>
      ) : null}

      <div className="portal-columns" style={{ marginTop: '20px' }}>
        <Panel>
          <Eyebrow>RECENT CHECK-INS</Eyebrow>
          {recentRows.length ? (
            <div className="registration-list">
              {recentRows.slice(0, 8).map((row) => (
                <div className="registration-row" key={row.id}>
                  <span className="event-dot" />
                  <div>
                    <b>{row.participantName}</b>
                    <small>{dateTime(row.checkedInAt)}</small>
                  </div>
                  <StatusBadge status={row.result} />
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No check-ins recorded yet.</p>
          )}
        </Panel>
        <Panel>
          <Eyebrow>ATTENDANCE LOGS · {day}</Eyebrow>
          <p className="mono-note">{attendanceRows.length} records</p>
          {attendanceRows.slice(0, 8).map((row) => (
            <div className="detail-row" key={row.id}>
              <span>
                {row.participantName}{' '}
                {row.eventTitle && row.eventTitle !== 'Convention Pass Gate' ? (
                  <small className="muted">({row.eventTitle})</small>
                ) : null}
              </span>
              <b>{row.result}</b>
            </div>
          ))}
        </Panel>
      </div>
    </>
  );
}

export function AdminAnnouncements() {
  const { editionId } = useSite();
  const [version, setVersion] = useState(0);
  const rows = useAsync(() => adminApi.announcements(editionId), [editionId, version], {
    enabled: Boolean(editionId),
  });
  const [sheet, setSheet] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    title: '',
    bodyMd: '',
    bannerUrl: '',
    ctaLabel: '',
    ctaUrl: '',
    showOnHome: false,
    audience: 'public',
    status: 'draft',
  });

  useEffect(() => {
    if (!sheet) return;
    setForm({
      title: sheet.title || '',
      bodyMd: sheet.bodyMd || '',
      bannerUrl: sheet.bannerUrl || '',
      ctaLabel: sheet.ctaLabel || '',
      ctaUrl: sheet.ctaUrl || '',
      showOnHome: Boolean(sheet.showOnHome),
      audience: sheet.audience || 'public',
      status: sheet.status || 'draft',
    });
  }, [sheet]);

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const payload = {
        ...form,
        bannerUrl: resolveImageUrl(form.bannerUrl) || null,
        ctaLabel: form.ctaLabel?.trim() || null,
        ctaUrl: form.ctaUrl?.trim() || null,
        showOnHome: Boolean(form.showOnHome),
      };
      if (sheet?.id) await adminApi.updateAnnouncement(editionId, sheet.id, payload);
      else await adminApi.createAnnouncement(editionId, payload);
      setSheet(null);
      setVersion((value) => value + 1);
      setMessage({ tone: 'success', text: 'Announcement saved.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm) return;
    try {
      await adminApi.deleteAnnouncement(editionId, confirm.id);
      setConfirm(null);
      setVersion((value) => value + 1);
      setMessage({ tone: 'success', text: 'Announcement deleted.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

  const list = rows.data?.data || [];

  return (
    <>
      <SectionHead
        kicker="BULLETIN"
        title="Announcements"
        action={
          <Button onClick={() => setSheet({})} icon={Plus}>
            New announcement
          </Button>
        }
      />
      <Feedback message={message} />
      {rows.loading ? <Loading label="Loading announcements" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={['Title', 'Audience', 'Status', 'Published', '']}
        empty={!list.length && !rows.loading ? 'No announcements yet.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {row.bannerUrl ? (
                  <img
                    src={resolveImageUrl(row.bannerUrl, 400)}
                    alt=""
                    referrerPolicy="no-referrer"
                    style={{
                      width: '44px',
                      height: '28px',
                      objectFit: 'cover',
                      borderRadius: '4px',
                      border: '1px solid rgba(255,255,255,0.15)',
                      flexShrink: 0,
                    }}
                  />
                ) : null}
                <div>
                  <b>{row.title}</b>
                  {row.showOnHome ? (
                    <span style={{ marginLeft: '8px' }}>
                      <Badge tone="accent">Home</Badge>
                    </span>
                  ) : null}
                  <div className="table-sub">{row.bodyMd?.slice(0, 90)}</div>
                </div>
              </div>
            </td>
            <td>{row.audience}</td>
            <td>
              <StatusBadge status={row.status} />
            </td>
            <td>{row.publishedAt ? date(row.publishedAt) : '-'}</td>
            <td className="row-actions">
              <button className="table-action" onClick={() => setSheet(row)}>
                Edit
              </button>
              <button className="table-action danger" onClick={() => setConfirm(row)}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </DataTable>

      <Sheet
        open={Boolean(sheet)}
        title={sheet?.id ? 'Edit announcement' : 'New announcement'}
        message={message}
        onClose={() => setSheet(null)}
      >
        <form className="admin-form" onSubmit={save}>
          <Field label="Title">
            <input
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              required
            />
          </Field>
          <Field label="Body (Markdown)">
            <textarea
              rows="6"
              value={form.bodyMd}
              onChange={(event) => setForm({ ...form, bodyMd: event.target.value })}
              required
            />
          </Field>
          <Field
            label="Banner URL (Direct or Google Drive link)"
            hint="Optional 16:9 banner shown when featured on the home screen"
          >
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                type="url"
                placeholder="https://drive.google.com/file/d/... or https://..."
                value={form.bannerUrl || ''}
                onChange={(event) => setForm({ ...form, bannerUrl: event.target.value })}
                style={{ flex: 1 }}
              />
              {form.bannerUrl ? (
                <button
                  type="button"
                  className="table-action"
                  onClick={() => setForm({ ...form, bannerUrl: '' })}
                >
                  Clear
                </button>
              ) : null}
            </div>
            {form.bannerUrl ? (
              <img
                src={resolveImageUrl(form.bannerUrl)}
                alt="Announcement banner preview"
                referrerPolicy="no-referrer"
                style={{
                  marginTop: '8px',
                  width: '100%',
                  maxHeight: '120px',
                  objectFit: 'cover',
                  borderRadius: '6px',
                  border: '1px solid rgba(255,255,255,0.14)',
                }}
              />
            ) : null}
          </Field>
          <FieldGrid>
            <Field label="Action button label (optional)">
              <input
                value={form.ctaLabel}
                onChange={(event) => setForm({ ...form, ctaLabel: event.target.value })}
                placeholder="e.g. Read Instructions"
                maxLength={80}
              />
            </Field>
            <Field label="Action link (optional)">
              <input
                list="announcement-cta-urls"
                value={form.ctaUrl}
                onChange={(event) => setForm({ ...form, ctaUrl: event.target.value })}
                placeholder="/portal/instructions or https://..."
                maxLength={500}
              />
              <datalist id="announcement-cta-urls">
                <option value="/portal/instructions">Instructions &amp; Policies</option>
                <option value="/portal/registration">Pass &amp; Registration</option>
                <option value="/portal/events">Browse Events</option>
                <option value="/portal/registrations">My Events &amp; Bills</option>
                <option value="/events">Public Events</option>
                <option value="/pass">Pass Tiers</option>
                <option value="/schedule">Schedule</option>
                <option value="/faq">FAQ</option>
              </datalist>
            </Field>
          </FieldGrid>
          <Toggle
            checked={Boolean(form.showOnHome)}
            onChange={(value) => setForm({ ...form, showOnHome: value })}
            label="Show on home screen"
            hint="Highlights this announcement with its banner in a clean showcase on the home page"
          />
          <FieldGrid>
            <Field label="Audience">
              <select
                value={form.audience}
                onChange={(event) => setForm({ ...form, audience: event.target.value })}
              >
                {['public', 'participants', 'staff'].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Status">
              <select
                value={form.status}
                onChange={(event) => setForm({ ...form, status: event.target.value })}
              >
                <option value="draft">Draft</option>
                <option value="published">Published</option>
              </select>
            </Field>
          </FieldGrid>
          <div className="sheet-actions">
            <Button variant="ghost" onClick={() => setSheet(null)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy} icon={Megaphone}>
              {busy ? 'Saving' : 'Save announcement'}
            </Button>
          </div>
        </form>
      </Sheet>

      <Sheet open={Boolean(confirm)} title="Delete announcement" onClose={() => setConfirm(null)}>
        <p className="muted">
          Delete <b>{confirm?.title}</b>? This removes it from the public bulletin.
        </p>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setConfirm(null)}>
            Keep it
          </Button>
          <Button onClick={remove} icon={Trash2}>
            Delete
          </Button>
        </div>
      </Sheet>
    </>
  );
}

export function AdminAttendance() {
  const { editionId, slug } = useSite();
  const [day, setDay] = useState('');
  const [selectedEventId, setSelectedEventId] = useState('');
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query);

  const eventsList = useAsync(
    () => (slug ? publicApi.events(slug, { pageSize: 100 }) : Promise.resolve({ data: [] })),
    [slug],
    { enabled: Boolean(slug) },
  );

  const rows = useAsync(
    () =>
      adminApi.attendance(editionId, {
        day: day || undefined,
        event_id: selectedEventId || undefined,
        q: debounced || undefined,
      }),
    [editionId, day, selectedEventId, debounced],
    {
      enabled: Boolean(editionId),
    },
  );
  const list = rows.data?.data || [];

  const handleRevoke = async (attendanceId) => {
    if (
      !window.confirm(
        'Warning: This will reset this attendance record so the attendee can be scanned and marked again. Continue?',
      )
    )
      return;
    try {
      await adminApi.deleteAttendance(editionId, attendanceId);
      rows.reload();
    } catch (err) {
      alert(err.message);
    }
  };

  return (
    <>
      <SectionHead kicker="DOOR &amp; ROOM RECORDS" title="Attendance Records" />
      <div className="table-filters">
        <Field label="Search participant or event">
          <input
            type="text"
            placeholder="Search name, email, event..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </Field>
        <Field label="Event / Station Filter">
          <select value={selectedEventId} onChange={(e) => setSelectedEventId(e.target.value)}>
            <option value="">All Stations &amp; Events</option>
            {(eventsList.data?.data || []).map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.title} {ev.venueRoom ? `· Room ${ev.venueRoom}` : ''}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Day">
          <input type="date" value={day} onChange={(event) => setDay(event.target.value)} />
        </Field>
        <Button
          variant="ghost"
          onClick={rows.reload}
          icon={RefreshCw}
          loading={rows.refreshing || rows.loading}
        >
          Refresh
        </Button>
      </div>
      {rows.loading ? <Loading label="Loading attendance" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={[
          'Participant',
          'Station / Event',
          'Room / Venue',
          'Day',
          'Result',
          'Checked In',
          'Host / Staff',
          'Actions',
        ]}
        empty={!list.length && !rows.loading ? 'No attendance records match.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>
              <b>{row.participantName}</b>
              <div className="table-sub">{row.participantEmail}</div>
            </td>
            <td>
              <b>{row.eventTitle || 'Convention Pass Gate'}</b>
            </td>
            <td>
              <span className="mono-note">{row.venueRoom || '-'}</span>
            </td>
            <td>{row.day || '-'}</td>
            <td>
              <StatusBadge status={row.result} />
            </td>
            <td>{dateTime(row.checkedInAt)}</td>
            <td>
              {row.checkedInByName ? (
                <span>{row.checkedInByName}</span>
              ) : (
                <span className="muted">-</span>
              )}
            </td>
            <td>
              <button
                type="button"
                className="table-action"
                style={{ color: '#f87171' }}
                onClick={() => handleRevoke(row.id)}
              >
                Revoke
              </button>
            </td>
          </tr>
        ))}
      </DataTable>
    </>
  );
}

export function AdminAudit() {
  const { editionId } = useSite();
  const rows = useAsync(() => adminApi.audit(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const list = rows.data?.data || [];

  return (
    <>
      <SectionHead kicker="ACCOUNTABILITY" title="Audit log" />
      {rows.loading ? <Loading label="Loading audit log" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={['When', 'Actor', 'Action', 'Resource', 'Details']}
        empty={!list.length && !rows.loading ? 'No audit entries.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>{dateTime(row.createdAt)}</td>
            <td>
              <b>{row.actorName || 'System'}</b>
              <div className="table-sub">{row.actorRole || '-'}</div>
            </td>
            <td>
              <code>{row.action}</code>
            </td>
            <td>
              {row.resourceType}
              <div className="table-sub">{row.resourceId || '-'}</div>
            </td>
            <td>
              {row.after || row.before ? (
                <details className="audit-detail">
                  <summary>View change</summary>
                  <pre>{JSON.stringify({ before: row.before, after: row.after }, null, 2)}</pre>
                </details>
              ) : (
                '-'
              )}
            </td>
          </tr>
        ))}
      </DataTable>
    </>
  );
}

export function AdminSettings() {
  const { editionId, refresh } = useSite();
  const settings = useAsync(() => adminApi.settings(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const memberships = useAsync(() => adminApi.memberships(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const icons = useAsync(() => adminApi.icons(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const [form, setForm] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');
  const [staffForm, setStaffForm] = useState({ email: '', role: 'event_coordinator' });
  const [invite, setInvite] = useState('');
  const [iconForm, setIconForm] = useState({ name: '', recolorable: false, file: null });

  useEffect(() => {
    const data = settings.data?.data;
    if (!data) return;
    setForm({
      name: data.name || '',
      tagline: data.tagline || '',
      venue: data.venue || '',
      city: data.city || '',
      startsAt: toLocalInput(data.startsAt),
      endsAt: toLocalInput(data.endsAt),
      registrationOpensAt: toLocalInput(data.registrationOpensAt),
      registrationClosesAt: toLocalInput(data.registrationClosesAt),
      status: data.status || 'draft',
      contactEmail: data.contactEmail || '',
    });
  }, [settings.data]);

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const save = async (event) => {
    event.preventDefault();
    setBusy('settings');
    setMessage(null);
    try {
      await adminApi.updateSettings(editionId, {
        name: form.name,
        tagline: form.tagline,
        venue: form.venue,
        city: form.city,
        startsAt: fromLocalInput(form.startsAt),
        endsAt: fromLocalInput(form.endsAt),
        registrationOpensAt: fromLocalInput(form.registrationOpensAt),
        registrationClosesAt: fromLocalInput(form.registrationClosesAt),
        status: form.status,
        contactEmail: form.contactEmail || null,
      });
      await settings.reload();
      refresh();
      setMessage({ tone: 'success', text: 'Edition settings saved.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const grant = async (event) => {
    event.preventDefault();
    setBusy('staff');
    setMessage(null);
    try {
      const body = await adminApi.grantMembership(editionId, staffForm);
      await memberships.reload();
      setStaffForm({ email: '', role: 'event_coordinator' });
      // One role per account: say which role was replaced so nobody assumes the
      // previous permission set is still live.
      const replaced = body.data?.replacedRoles || [];
      setMessage({
        tone: 'success',
        text: replaced.length
          ? `Staff role granted as ${ROLE_LABELS[staffForm.role] || staffForm.role}. Replaced ${replaced
              .map((role) => ROLE_LABELS[role] || role)
              .join(', ')}.`
          : 'Staff role granted.',
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const sendInvite = async () => {
    setBusy('invite');
    setMessage(null);
    try {
      const body = await adminApi.inviteStaff(editionId, { email: invite, role: staffForm.role });
      setInvite('');
      setMessage({
        tone: 'success',
        text: `Invite created. Share this link: ${body.data?.inviteUrl || body.data?.invite_url || 'see server logs'}`,
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const uploadIcon = async (event) => {
    event.preventDefault();
    if (!iconForm.file) return;
    setBusy('icon');
    setMessage(null);
    try {
      const body = new FormData();
      body.set('file', iconForm.file);
      body.set('name', iconForm.name || iconForm.file.name);
      body.set('recolorable', iconForm.recolorable ? 'true' : 'false');
      await adminApi.uploadIcon(editionId, body);
      await icons.reload();
      setIconForm({ name: '', recolorable: false, file: null });
      setMessage({ tone: 'success', text: 'Icon uploaded.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  if (settings.loading || !form) return <Loading label="Loading settings" rows={3} />;
  if (settings.error) return <ErrorBox error={settings.error} onRetry={settings.reload} />;

  const memberRows = oneRolePerAccount(memberships.data?.data || []);
  const iconRows = icons.data?.data || [];

  return (
    <>
      <SectionHead kicker="CONFIGURATION" title="Edition settings" />
      <Feedback message={message} />
      <Panel>
        <form className="admin-form" onSubmit={save}>
          <FieldGrid>
            <Field label="Edition name">
              <input
                value={form.name}
                onChange={(event) => set('name', event.target.value)}
                required
              />
            </Field>
            <Field label="Tagline">
              <input
                value={form.tagline}
                onChange={(event) => set('tagline', event.target.value)}
              />
            </Field>
            <Field label="Venue">
              <input
                value={form.venue}
                onChange={(event) => set('venue', event.target.value)}
                required
              />
            </Field>
            <Field label="City">
              <input
                value={form.city}
                onChange={(event) => set('city', event.target.value)}
                required
              />
            </Field>
            <Field label="Starts at">
              <input
                type="datetime-local"
                value={form.startsAt}
                onChange={(event) => set('startsAt', event.target.value)}
                required
              />
            </Field>
            <Field label="Ends at">
              <input
                type="datetime-local"
                value={form.endsAt}
                onChange={(event) => set('endsAt', event.target.value)}
                required
              />
            </Field>
            <Field label="Registration opens">
              <input
                type="datetime-local"
                value={form.registrationOpensAt}
                onChange={(event) => set('registrationOpensAt', event.target.value)}
              />
            </Field>
            <Field label="Registration closes">
              <input
                type="datetime-local"
                value={form.registrationClosesAt}
                onChange={(event) => set('registrationClosesAt', event.target.value)}
              />
            </Field>
            <Field label="Status">
              <select value={form.status} onChange={(event) => set('status', event.target.value)}>
                {/* Keep an out-of-list server status (open/closed) selectable so the
                    field never renders blank and never rewrites it by accident. */}
                {Array.from(new Set(['draft', 'published', 'archived', form.status])).map(
                  (status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label="Contact email">
              <input
                type="email"
                value={form.contactEmail}
                onChange={(event) => set('contactEmail', event.target.value)}
              />
            </Field>
          </FieldGrid>
          <div className="sheet-actions">
            <Button type="submit" disabled={busy === 'settings'} icon={Check}>
              {busy === 'settings' ? 'Saving' : 'Save settings'}
            </Button>
          </div>
        </form>
      </Panel>

      <SectionHead kicker="ACCESS" title="Staff and roles" />
      <div className="portal-columns">
        <Panel>
          <Eyebrow>GRANT A ROLE</Eyebrow>
          <form className="admin-form" onSubmit={grant}>
            <Field label="Account email">
              <input
                type="email"
                value={staffForm.email}
                onChange={(event) => setStaffForm({ ...staffForm, email: event.target.value })}
                required
              />
            </Field>
            <Field label="Role">
              <select
                value={staffForm.role}
                onChange={(event) => setStaffForm({ ...staffForm, role: event.target.value })}
              >
                {GRANTABLE_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role] || role}
                  </option>
                ))}
              </select>
            </Field>
            <Button type="submit" disabled={busy === 'staff'} variant="ghost">
              Grant role
            </Button>
          </form>
          <div className="host-rule" />
          <Eyebrow>INVITE BY EMAIL</Eyebrow>
          <Field label="Invite email">
            <input
              type="email"
              value={invite}
              onChange={(event) => setInvite(event.target.value)}
            />
          </Field>
          <Button onClick={sendInvite} disabled={busy === 'invite' || !invite} variant="ghost">
            Create invite link
          </Button>
        </Panel>
        <Panel>
          <Eyebrow>ACTIVE MEMBERSHIPS</Eyebrow>
          <div className="registration-list">
            {memberRows.map((row) => (
              <div className="registration-row" key={row.id}>
                <div>
                  <b>{row.fullName || row.email}</b>
                  <small>{row.email}</small>
                  {row.staleRoles?.length ? (
                    <small className="muted">
                      Also holds{' '}
                      {row.staleRoles.map((role) => ROLE_LABELS[role] || role).join(', ')} from an
                      older grant. Grant one role again to collapse it.
                    </small>
                  ) : null}
                </div>
                <Badge tone="accent">{ROLE_LABELS[row.role] || row.role}</Badge>
                <StatusBadge status={row.status} />
              </div>
            ))}
            {!memberRows.length ? <p className="muted">No staff memberships yet.</p> : null}
          </div>
        </Panel>
      </div>

      <SectionHead kicker="BRAND" title="Icon library" />
      <Panel>
        <form className="inline-form" onSubmit={uploadIcon}>
          <Field label="Icon name">
            <input
              value={iconForm.name}
              onChange={(event) => setIconForm({ ...iconForm, name: event.target.value })}
            />
          </Field>
          <Field label="SVG or PNG">
            <input
              type="file"
              accept="image/svg+xml,image/png"
              onChange={(event) =>
                setIconForm({ ...iconForm, file: event.target.files?.[0] || null })
              }
            />
          </Field>
          <Toggle
            checked={iconForm.recolorable}
            onChange={(value) => setIconForm({ ...iconForm, recolorable: value })}
            label="Recolorable"
          />
          <Button
            type="submit"
            disabled={busy === 'icon' || !iconForm.file}
            variant="ghost"
            icon={Image}
          >
            Upload
          </Button>
        </form>
        <div className="icon-grid">
          {iconRows.map((icon) => (
            <div className="icon-tile" key={icon.id}>
              <img src={icon.url} alt={icon.name} />
              <span>{icon.name}</span>
              <button
                className="table-action danger"
                onClick={async () => {
                  if (!window.confirm(`Archive the icon "${icon.name}"? Pages stop showing it.`))
                    return;
                  try {
                    await adminApi.archiveIcon(editionId, icon.id);
                    await icons.reload();
                  } catch (error) {
                    setMessage({ tone: 'error', text: error.message });
                  }
                }}
              >
                Archive
              </button>
            </div>
          ))}
          {!iconRows.length ? <p className="muted">No icons uploaded yet.</p> : null}
        </div>
      </Panel>
    </>
  );
}
