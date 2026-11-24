import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, NavLink, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  BadgeCheck,
  CalendarDays,
  Camera,
  CameraOff,
  Database,
  LayoutDashboard,
  Check,
  ClipboardCheck,
  CreditCard,
  Download,
  FileText,
  FlipHorizontal,
  IdCard,
  Image,
  LogOut,
  Megaphone,
  Menu,
  Plus,
  QrCode,
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

import { Avatar, Box, IconButton, Stack, Typography } from '@mui/material';

import { adminApi, publicApi } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
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
  Badge,
  Button,
  DataTable,
  Empty,
  ErrorBox,
  Eyebrow,
  Field,
  FieldGrid,
  InlineMessage,
  Loading,
  PageTitle,
  Panel,
  SectionHead,
  Sheet,
  Stat,
  StatusBadge,
  Toggle,
  useAsync,
  useDebounced,
  clearAsyncCache,
  AdminErrorBoundary,
} from '../components/ui.jsx';

const LOGO =
  String(import.meta.env.BASE_URL) +
  'images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp';

const NAV = [
  ['Overview', '/manage', LayoutDashboard, true],
  ['Events', '/manage/events', CalendarDays],
  ['Policy', '/manage/policy', ShieldCheck],
  ['Registrations', '/manage/registrations', Ticket],
  ['Cancelled & Refunds', '/manage/registrations?status=cancelled', Wallet],
  ['Registration desk', '/manage/registration', IdCard],
  ['ID Card Studio', '/manage/id-cards', CreditCard],
  ['Users', '/manage/users', Users],
  ['Verifications', '/manage/verifications', BadgeCheck],
  ['Payments', '/manage/payments', Wallet],
  ['Check-in', '/manage/check-in', ClipboardCheck],
  ['Announcements', '/manage/announcements', Megaphone],
  ['Attendance', '/manage/attendance', FileText],
  ['Audit log', '/manage/audit', FileText],
  ['DB Playground', '/manage/database', Database],
  ['Registration config', '/manage/registration-settings', Settings],
  ['Settings', '/manage/settings', Settings],
];

const ROLE_LABELS = {
  owner: 'Owner',
  super_admin: 'Super admin',
  edition_admin: 'Edition admin',
  finance_admin: 'Finance admin',
  eligibility_verifier: 'Verifier',
  event_coordinator: 'Event coordinator',
  checkin_staff: 'Check-in staff',
  participant: 'Participant',
};

const ACCENTS = ['cyan', 'amber', 'orange', 'violet', 'lime', 'rose', 'ice'];

export function AdminLayout() {
  const { isStaff, roles, user, loading, logout } = useAuth();
  const site = useSite();
  const { edition, editionId } = site;
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncToast, setSyncToast] = useState(null);
  const location = useLocation();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  const handleForceRefresh = async () => {
    setSyncing(true);
    setSyncToast(null);
    try {
      if (editionId) {
        await adminApi.sync(editionId);
      }
      clearAsyncCache();
      try {
        sessionStorage.removeItem('px_cached_edition');
        sessionStorage.removeItem('px_cached_config');
      } catch {}
      site.refresh();
      setSyncToast('Server caches purged. Public pages can lag up to 60s at the edge.');
      setTimeout(() => setSyncToast(null), 3500);
    } catch {
      clearAsyncCache();
      try {
        sessionStorage.removeItem('px_cached_edition');
        sessionStorage.removeItem('px_cached_config');
      } catch {}
      site.refresh();
      setSyncToast('Client cache purged & reloaded!');
      setTimeout(() => setSyncToast(null), 3500);
    } finally {
      setSyncing(false);
    }
  };

  if (loading) return <Loading label="Verifying staff credentials…" rows={0} />;
  if (!user)
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (!isStaff) return <Navigate to="/portal" replace />;

  // Staff modules need the real database edition row: without it every request
  // would address an id the API does not know, so gate them on a verified load.
  if (!site.editionVerified) {
    return (
      <div className="admin-gate">
        {site.editionError ? (
          <>
            <ErrorBox
              error={site.editionError}
              title="Could not load the convention edition"
              onRetry={site.refresh}
            />
            <p className="muted" style={{ marginTop: 12 }}>
              The console needs the live edition record before it can load staff modules.
              This is usually a short database wake-up: retry in a moment. Signing out and
              in again also refreshes the session.
            </p>
            <div className="admin-gate-actions">
              <Button variant="ghost" icon={RefreshCw} onClick={site.refresh}>
                Retry edition lookup
              </Button>
              <Button variant="ghost" to="/portal">
                Open participant portal
              </Button>
              <Button variant="ghost" icon={LogOut} onClick={logout}>
                Sign out
              </Button>
            </div>
          </>
        ) : (
          <Loading label="Resolving convention edition…" rows={0} />
        )}
      </div>
    );
  }

  return (
    <div className="admin-shell">
      {/* Dedicated Admin Header */}
      <header className="admin-header">
        <div className="admin-brand-lockup">
          <Link to="/manage" className="admin-brand-link" aria-label="Staff operations home">
            <img src={LOGO} alt={edition?.name || 'Parallax'} className="admin-brand-logo" />
          </Link>
          <Badge tone="accent">Staff Console</Badge>
          {edition?.name ? <Badge tone="muted">{edition.name}</Badge> : null}
        </div>

        <nav className="admin-header-nav" aria-label="Staff navigation shortcuts">
          {/* Switch to Participant Portal */}
          <Button
            to="/portal"
            variant="ghost"
            size="small"
            icon={Users}
            title="Open participant portal"
            className="admin-secondary-action"
            sx={{ display: { xs: 'none', sm: 'inline-flex' } }}
          >
            Participant Portal
          </Button>

          {/* Switch to Public Site */}
          <Button
            to="/"
            variant="ghost"
            size="small"
            icon={ArrowUpRight}
            title="View live convention website"
            className="admin-secondary-action"
            sx={{ display: { xs: 'none', sm: 'inline-flex' } }}
          >
            Live Site
          </Button>

          {/* Force Cache Refresh */}
          <Button
            variant="ghost"
            size="small"
            icon={RefreshCw}
            loading={syncing}
            onClick={handleForceRefresh}
            title="Force purge all caches and reload live database state"
          >
            {syncing ? 'Syncing…' : 'Force Refresh'}
          </Button>

          {/* Staff Identity Pill */}
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: 'center', px: 1.25, py: 0.5, borderRadius: 99, border: '1px solid', borderColor: 'divider' }}
          >
            <Badge tone="accent">{ROLE_LABELS[roles[0]] || 'Staff'}</Badge>
            <Typography
              variant="caption"
              sx={{ color: 'text.secondary', display: { xs: 'none', md: 'block' } }}
            >
              {user?.email}
            </Typography>
          </Stack>

          {/* Sign Out */}
          <Button variant="ghost" size="small" icon={LogOut} onClick={logout} title="Sign out of staff account">
            Sign out
          </Button>

          {/* Mobile Menu Button */}
          <button
            className="admin-mobile-menu-btn"
            onClick={() => setMobileNavOpen((open) => !open)}
            aria-label={mobileNavOpen ? 'Close staff menu' : 'Open staff menu'}
            aria-expanded={mobileNavOpen}
          >
            {mobileNavOpen ? (
              <X size={18} strokeWidth={1.8} />
            ) : (
              <Menu size={18} strokeWidth={1.8} />
            )}
          </button>
        </nav>
      </header>

      {syncToast ? (
        <div className="admin-sync-banner" role="status">
          <Check size={14} />
          <span>{syncToast}</span>
        </div>
      ) : null}

      {/* Horizontal Swipeable Mobile Tabs */}
      <nav className="admin-mobile-tabs" aria-label="Staff quick modules">
        {NAV.map(([label, to, Icon, end]) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `admin-mobile-tab-item ${isActive ? 'is-active' : ''}`}
          >
            <Icon size={13} strokeWidth={1.6} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Mobile Drawer (Accessible full list) */}
      {mobileNavOpen ? (
        <div
          className="admin-mobile-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="Staff modules"
        >
          <div className="admin-drawer-header">
            <span>Staff Console Modules</span>
            <button
              className="admin-drawer-close-btn"
              onClick={() => setMobileNavOpen(false)}
              aria-label="Close menu"
            >
              <X size={18} strokeWidth={1.8} />
            </button>
          </div>
          <div className="admin-drawer-links">
            {NAV.map(([label, to, Icon, end]) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={() => setMobileNavOpen(false)}
                className={({ isActive }) => `admin-drawer-item ${isActive ? 'is-active' : ''}`}
              >
                <Icon size={15} strokeWidth={1.6} />
                <span>{label}</span>
              </NavLink>
            ))}
          </div>
          <div className="admin-drawer-footer">
            <div className="admin-drawer-user">
              <b>{user?.email}</b>
              <small>{ROLE_LABELS[roles[0]] || 'Staff'}</small>
            </div>
            <button className="admin-signout-btn" onClick={logout}>
              <LogOut size={14} /> <span>Sign out</span>
            </button>
          </div>
        </div>
      ) : null}

      {/* Main Admin Body */}
      <div className="admin-body">
        <aside className="admin-desktop-sidebar">
          <div className="admin-sidebar-header">
            <span className="admin-sidebar-heading">Operations</span>
            <span className="admin-sidebar-meta">{NAV.length} modules</span>
          </div>
          <nav className="admin-desktop-nav" aria-label="Staff navigation">
            {NAV.map(([label, to, Icon, end]) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) => `admin-sidebar-link ${isActive ? 'is-active' : ''}`}
              >
                <Icon size={15} strokeWidth={1.5} />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="admin-sidebar-footer">
            <div className="admin-system-status">
              <span className="status-live-dot" />
              <span>Live Audit & RBAC Active</span>
            </div>
          </div>
        </aside>

        <main className="admin-content-area" id="admin-main">
          <AdminErrorBoundary key={location.pathname}>
            <Outlet />
          </AdminErrorBoundary>
        </main>
      </div>
    </div>
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

  const recent = data?.recentRegistrations || [];

  return (
    <>
      <div className="admin-page-header">
        <div className="admin-page-header-text">
          <Eyebrow>Operations Telemetry</Eyebrow>
          <h1>Convention Overview</h1>
          <p>Real-time metrics, ticketing volume, capacity, and door check-in status.</p>
        </div>
        <Button variant="ghost" onClick={stats.reload} icon={RefreshCw}>
          Refresh
        </Button>
      </div>

      <div className="stat-grid">
        <Stat
          label="PASSES SOLD"
          value={data?.passesSold ?? 0}
          note={`${data?.passesPending ?? 0} pending`}
        />
        <Stat
          label="REVENUE"
          value={money(data?.revenuePaise || 0)}
          note={`${money(data?.refundedPaise || 0)} refunded`}
        />
        <Stat
          label="REGISTRATIONS"
          value={data?.registrationsConfirmed ?? 0}
          note={`${data?.registrationsPending ?? 0} pending`}
        />
        <Stat label="CHECKED IN" value={data?.checkedIn ?? 0} note="Across both convention days" />
        <Stat
          label="EVENTS"
          value={`${data?.eventsPublished ?? 0} / ${data?.eventsTotal ?? 0}`}
          note="Published / total catalogue"
        />
        <Stat
          label="SEATS TAKEN"
          value={`${data?.seatsTaken ?? 0} / ${data?.seatsCapacity ?? 0}`}
          note="Taken / capacity"
        />
        <Stat
          label="VERIFICATIONS"
          value={data?.verificationsPending ?? 0}
          note="Awaiting review"
          tone={data?.verificationsPending ? 'warn' : ''}
        />
        <Link to="/manage/registrations?status=cancelled" style={{ textDecoration: 'none', display: 'block' }}>
          <Stat
            label="CANCELLATIONS / REFUNDS"
            value={data?.registrationsCancelled ?? 0}
            note={`${money(data?.refundedPaise || 0)} refunded · Click to review`}
            tone={data?.registrationsCancelled ? 'warn' : ''}
          />
        </Link>
        <Stat
          label="LATEST DAY SALES"
          value={
            (data?.salesByDay || []).length ? money(data.salesByDay.at(-1)?.amountPaise || 0) : '₹0'
          }
          note="Recorded on latest day"
        />
      </div>

      <div className="portal-columns">
        <Panel>
          <div className="panel-head-row">
            <Eyebrow>Recent Registrations</Eyebrow>
            <NavLink className="text-link" to="/manage/registrations">
              All registrations →
            </NavLink>
          </div>
          {recent.length ? (
            <div className="registration-list">
              {recent.slice(0, 8).map((row, index) => (
                <div
                  className="registration-row"
                  key={`${row.id || row.registrationNumber || index}`}
                >
                  <span className="event-dot" />
                  <div>
                    <b>{row.userName || row.participantName || row.name || 'Participant'}</b>
                    <small>{row.eventTitle || row.event || 'Convention pass'}</small>
                  </div>
                  <StatusBadge status={row.status} />
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No registrations recorded yet.</p>
          )}
        </Panel>
        <Panel>
          <Eyebrow>Quick Operational Actions</Eyebrow>
          <div className="quick-links">
            <Button to="/manage/check-in" variant="ghost" icon={ClipboardCheck}>
              Open Check-in Door Desk
            </Button>
            <Button to="/manage/registrations" variant="ghost" icon={Ticket}>
              Browse & Search Registrations
            </Button>
            <Button to="/manage/events" variant="ghost" icon={CalendarDays}>
              Manage Event Catalogue
            </Button>
            <Button to="/manage/verifications" variant="ghost" icon={BadgeCheck}>
              Review Student ID Verifications
            </Button>
            <Button to="/manage/policy" variant="ghost" icon={ShieldCheck}>
              Update Pricing & Pass Policy
            </Button>
            <Button to="/manage/settings" variant="ghost" icon={Settings}>
              Convention Edition Settings
            </Button>
          </div>
        </Panel>
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
        bannerUrl: form.bannerUrl?.trim() || null,
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
          label="Event Banner (Supabase Storage or Custom URL)"
          hint="Upload image or paste image link (16:9 recommended)"
        >
          <div className="banner-input-wrap">
            <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
              <input
                type="url"
                placeholder="https://... or click Upload Banner"
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
                  src={form.bannerUrl}
                  alt="Banner preview"
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
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
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
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
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
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
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
                    src={row.bannerUrl}
                    alt=""
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
      prev.includes(eid) ? prev.filter((id) => id !== eid) : [...prev, eid]
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
      setError('A valid audit reason is required (e.g., Bank transaction verified on Razorpay dashboard)');
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
            Resolve payment gateway disconnects where an attendee paid via Razorpay but webhooks
            or the redirect failed to activate their pass or confirm event add-ons. Every change is
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
          <Field label="Razorpay payment ID / transaction ref" hint="Optional — helps the auditor match the payment.">
            <input
              type="text"
              value={paymentRef}
              onChange={(e) => setPaymentRef(e.target.value)}
              placeholder="e.g. pay_Q8w9xY123abc or bank UTR"
            />
          </Field>

          <Field label="Justification / audit reason" hint="Required. Shown in the audit log and ops channel.">
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
          <Field
            label="Events to seed / confirm"
            hint={`${selectedEvents.length} selected`}
          >
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
          lunchDays: ['day1', 'day2'],
          addonRequiresPass: true,
          teamMembersRequirePass: true,
          holdMinutes: 15,
          deadline: '',
          teamFeeBasisDefault: 'per_participant',
          gstNote: 'Inclusive of all applicable taxes',
          reason: 'Initial policy setup',
        });
      }
      return;
    }
    setForm({
      passPrice: rupees(current.passPricePaise),
      includedEventCount: current.includedEventCount,
      mode: current.includedSelectionMode,
      cap: rupees(current.includedValueCapPaise),
      capInclusive: current.capInclusive,
      lunchDays: current.lunchIncludedDays || [],
      addonRequiresPass: current.addonRequiresPass,
      teamMembersRequirePass: current.teamMembersRequirePass,
      holdMinutes: current.holdMinutes,
      deadline: toLocalInput(current.selectionChangeDeadline),
      teamFeeBasisDefault: current.teamFeeBasisDefault || 'per_participant',
      gstNote: current.gstNote || '',
      reason: '',
    });
  }, [current?.id]);

  const set = (key, value) => setForm((value_) => ({ ...value_, [key]: value }));

  const payloadFrom = () => ({
    passPricePaise: paise(form.passPrice),
    includedEventCount: Number(form.includedEventCount) || 0,
    includedSelectionMode: form.mode,
    includedValueCapPaise: paise(form.cap),
    capInclusive: form.capInclusive,
    lunchIncludedDays: form.lunchDays,
    addonRequiresPass: form.addonRequiresPass,
    teamMembersRequirePass: form.teamMembersRequirePass,
    teamFeeBasisDefault: form.teamFeeBasisDefault,
    holdMinutes: Number(form.holdMinutes) || 15,
    selectionChangeDeadline: fromLocalInput(form.deadline),
    gstNote: form.gstNote || null,
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

  if (policies.loading || !form) return <Loading label="Loading policies" rows={2} />;
  if (policies.error) return <ErrorBox error={policies.error} onRetry={policies.reload} />;

  return (
    <>
      <SectionHead kicker="PRICING RULES" title="Edition policy" />
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
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
          <Field label="Pass price (₹)">
            <input
              type="number"
              min="0"
              step="50"
              value={form.passPrice}
              onChange={(event) => set('passPrice', event.target.value)}
            />
          </Field>
          <Field label="Included event count">
            <input
              type="number"
              min="0"
              max="20"
              value={form.includedEventCount}
              onChange={(event) => set('includedEventCount', event.target.value)}
            />
          </Field>
          <Field label="Selection mode">
            <select value={form.mode} onChange={(event) => set('mode', event.target.value)}>
              <option value="up_to">Up to</option>
              <option value="exact">Exactly</option>
            </select>
          </Field>
          <Field label="Included value cap (₹)">
            <input
              type="number"
              min="0"
              step="50"
              value={form.cap}
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

      <DataTable head={['Version', 'Pass', 'Included', 'Cap', 'Mode', 'Published', 'Reason']}>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              v{row.version} {row.isCurrent ? <Badge tone="good">Current</Badge> : null}
            </td>
            <td>{money(row.passPricePaise)}</td>
            <td>{row.includedEventCount}</td>
            <td>{money(row.includedValueCapPaise)}</td>
            <td>{row.includedSelectionMode}</td>
            <td>{date(row.createdAt)}</td>
            <td>{row.reason || '-'}</td>
          </tr>
        ))}
      </DataTable>
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
          <select
            value={selectedEventId}
            onChange={(e) => updateFilters(status, e.target.value)}
          >
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
        <Button variant="ghost" onClick={rows.reload} icon={RefreshCw}>
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
          onClick={() => updateFilters('confirmed', selectedEventId)}
        >
          Confirmed active
        </Button>
        <Button
          variant={status === 'reserved' ? 'primary' : 'ghost'}
          onClick={() => updateFilters('reserved', selectedEventId)}
        >
          Reserved
        </Button>
        <Button
          variant={status === 'cancelled' ? 'primary' : 'ghost'}
          icon={X}
          onClick={() => updateFilters('cancelled', selectedEventId)}
          sx={
            status === 'cancelled'
              ? {
                  backgroundColor: '#f87171',
                  color: '#1b0707',
                  '&:hover': { backgroundColor: '#f97c7c' },
                }
              : {
                  color: '#fca5a5',
                  borderColor: 'rgba(248, 113, 113, 0.42)',
                  '&:hover': {
                    backgroundColor: 'rgba(248, 113, 113, 0.12)',
                    borderColor: 'rgba(248, 113, 113, 0.75)',
                  },
                }
          }
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
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
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
              <div style={{ marginTop: '12px', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '10px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600 }}>
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
                      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
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
                      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
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
                          min="1"
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
                    ⚠️ No refund will be issued immediately. You can still issue a refund later from the registrations list.
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
            onChange={(e) =>
              setForceCancelForm({ ...forceCancelForm, reason: e.target.value })
            }
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
            <b style={{ color: '#38bdf8' }}>
              {money(refundTarget?.refundableAmountPaise || 0)}
            </b>
          </div>
        </div>

        <Field
          label={`Refund Amount in ₹ (Max: ₹${
            (refundTarget?.refundableAmountPaise || 0) / 100
          })`}
          hint="Defaults to full refundable amount. Strictly capped at paid fee."
        >
          <input
            type="number"
            min="1"
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
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
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
        head={['Name', 'College', 'Roles', 'Pass', 'Verification', 'Status', '']}
        empty={!rows.length && !users.loading ? 'No users match.' : null}
      >
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              <b>{row.fullName}</b>
              <div className="table-sub">{row.email}</div>
            </td>
            <td>{row.collegeName || '-'}</td>
            <td>
              {(row.roles || []).map((role) => ROLE_LABELS[role] || role).join(', ') ||
                'Participant'}
            </td>
            <td>{row.passStatus ? <StatusBadge status={row.passStatus} /> : '-'}</td>
            <td>
              <StatusBadge status={row.verificationStatus} />
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
        ))}
      </DataTable>
      <Sheet open={Boolean(target)} title="Change account status" onClose={() => setTarget(null)}>
        <p className="muted">
          {target?.status === 'active' ? 'Suspend' : 'Reactivate'} <b>{target?.fullName}</b>?
          Suspended accounts cannot sign in or register.
        </p>
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

export function AdminVerifications() {
  const { editionId } = useSite();
  const [status, setStatus] = useState('pending');
  const rows = useAsync(() => adminApi.verifications(editionId, { status }), [editionId, status], {
    enabled: Boolean(editionId),
  });
  const [target, setTarget] = useState(null);
  const [decision, setDecision] = useState('verified');
  const [reason, setReason] = useState('');
  const [message, setMessage] = useState(null);
  const list = rows.data?.data || [];

  const openDocument = async (id) => {
    setMessage(null);
    try {
      const body = await adminApi.verificationDocument(editionId, id);
      const url = body.data?.url || body.data?.documentUrl;
      if (!url) throw new Error('No document is attached.');
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

  const decide = async () => {
    setMessage(null);
    try {
      await adminApi.decideVerification(editionId, target.id, {
        decision,
        reason: reason || null,
      });
      await rows.reload();
      setTarget(null);
      setReason('');
      setMessage({ tone: 'success', text: 'Verification decision recorded.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

  return (
    <>
      <SectionHead kicker="STUDENT STATUS" title="Verification queue" />
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
      <div className="table-filters">
        <Field label="Status">
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            {['pending', 'verified', 'rejected', 'unverified'].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
        <Button variant="ghost" onClick={rows.reload}>
          Refresh
        </Button>
      </div>
      {rows.loading ? <Loading label="Loading verifications" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={['Student', 'College', 'Method', 'Submitted', 'Status', '']}
        empty={!list.length && !rows.loading ? 'Nothing in this queue.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>
              <b>{row.fullName}</b>
              <div className="table-sub">{row.email}</div>
            </td>
            <td>{row.collegeName || '-'}</td>
            <td>{row.method}</td>
            <td>{dateTime(row.submittedAt)}</td>
            <td>
              <StatusBadge status={row.status} />
            </td>
            <td className="row-actions">
              {row.documentName ? (
                <button className="table-action" onClick={() => openDocument(row.id)}>
                  View Document
                </button>
              ) : null}
              {row.status === 'pending' && row.method === 'college_email' ? (
                <button
                  className="table-action"
                  onClick={async () => {
                    setMessage(null);
                    try {
                      await adminApi.resendVerificationCode(editionId, row.id);
                      setMessage({
                        tone: 'success',
                        text: `A new confirmation code was sent to ${row.fullName}.`,
                      });
                    } catch (error) {
                      setMessage({ tone: 'error', text: error.message });
                    }
                  }}
                >
                  Resend code
                </button>
              ) : null}
              {row.status === 'pending' ? (
                <button
                  className="table-action"
                  style={{ color: '#22c55e' }}
                  onClick={async () => {
                    try {
                      await adminApi.decideVerification(editionId, row.id, {
                        decision: 'verified',
                        reason: 'Approved via quick action',
                      });
                      await rows.reload();
                      setMessage({ tone: 'success', text: `Verified student: ${row.fullName}` });
                    } catch (err) {
                      setMessage({ tone: 'error', text: err.message });
                    }
                  }}
                >
                  Quick Approve
                </button>
              ) : null}
              <button
                className="table-action"
                onClick={() => {
                  setTarget(row);
                  setDecision('verified');
                  setReason(row.rejectionReason || '');
                }}
              >
                Review
              </button>
            </td>
          </tr>
        ))}
      </DataTable>
      <Sheet open={Boolean(target)} title="Review verification" onClose={() => setTarget(null)}>
        <p className="muted">
          {target?.fullName} · {target?.email}
        </p>
        <Field label="Decision">
          <select value={decision} onChange={(event) => setDecision(event.target.value)}>
            <option value="verified">Verify student</option>
            <option value="rejected">Reject</option>
          </select>
        </Field>
        <Field
          label="Reason"
          hint={decision === 'rejected' ? 'Required for a rejection.' : 'Optional note.'}
        >
          <input value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setTarget(null)}>
            Cancel
          </Button>
          <Button
            onClick={decide}
            disabled={decision === 'rejected' && !reason.trim()}
            icon={BadgeCheck}
          >
            Save decision
          </Button>
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

  const openRefund = (row) => {
    setTarget(row);
    setForm({
      amount: rupees(row.amountPaise),
      reasonCode: 'requested_by_participant',
      note: '',
    });
  };

  const submit = async () => {
    setMessage(null);
    try {
      await adminApi.createRefund(editionId, {
        orderId: target.id,
        amountPaise: paise(form.amount),
        reasonCode: form.reasonCode,
        reasonNote: form.note || null,
      });
      await Promise.all([payments.reload(), refunds.reload()]);
      setTarget(null);
      setMessage({ tone: 'success', text: 'Refund requested.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

  return (
    <>
      <SectionHead kicker="FINANCE" title="Payments and refunds" />
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
      {payments.loading ? <Loading label="Loading payments" rows={2} /> : null}
      {payments.error ? <ErrorBox error={payments.error} onRetry={payments.reload} /> : null}
      <DataTable
        head={['Participant', 'Purpose', 'Amount', 'Status', 'Created', 'Paid', '']}
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
              <StatusBadge status={row.status} />
            </td>
            <td>{date(row.createdAt)}</td>
            <td>{row.paidAt ? date(row.paidAt) : '-'}</td>
            <td>
              {row.status === 'paid' ? (
                <button className="table-action" onClick={() => openRefund(row)}>
                  Refund
                </button>
              ) : null}
            </td>
          </tr>
        ))}
      </DataTable>

      <SectionHead kicker="LEDGER" title="Refund requests" />
      <DataTable
        head={['Order', 'Amount', 'Reason', 'Status', 'Requested', 'Processed']}
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
          </tr>
        ))}
      </DataTable>

      <Sheet open={Boolean(target)} title="Request a refund" onClose={() => setTarget(null)}>
        <p className="muted">
          {target?.userName} · {money(target?.amountPaise)} order
        </p>
        <FieldGrid>
          <Field label="Amount (₹)">
            <input
              type="number"
              min="1"
              max={rupees(target?.amountPaise || 0)}
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
            disabled={!form.amount || Number(form.amount) <= 0}
            icon={CreditCard}
          >
            Request refund
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
  const [rosterFilter, setRosterFilter] = useState('all');
  const [rosterSearch, setRosterSearch] = useState('');
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const scanIntervalRef = useRef(null);

  useEffect(() => {
    const evId = searchParams.get('eventId');
    if (evId) setSelectedEventId(evId);
  }, [searchParams]);

  const eventsList = useAsync(
    () => (slug ? publicApi.events(slug, { pageSize: 100 }) : Promise.resolve({ data: [] })),
    [slug],
    { enabled: Boolean(slug) }
  );

  const recent = useAsync(() => adminApi.recentCheckins(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const attendance = useAsync(() => adminApi.attendance(editionId, { day }), [editionId, day], {
    enabled: Boolean(editionId),
  });

  const rosterAsync = useAsync(
    () =>
      selectedEventId
        ? adminApi.eventRoster(editionId, selectedEventId, { day })
        : Promise.resolve({ data: null }),
    [editionId, selectedEventId, day],
    { enabled: Boolean(editionId && selectedEventId) }
  );

  const performCheckin = async (rawToken) => {
    const cleanToken = (rawToken || token || '').trim();
    if (!cleanToken) return;
    setBusy(true);
    setMessage(null);
    setResult(null);
    try {
      const body = await adminApi.checkin(editionId, {
        token: cleanToken,
        day: day || null,
        eventId: selectedEventId || null,
      });
      setResult(body.data);
      setToken('');
      recent.reload();
      attendance.reload();
      if (selectedEventId) {
        rosterAsync.reload();
      }
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
    } finally {
      setBusy(false);
    }
  };

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

  // Camera video stream lifecycle
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
      return undefined;
    }

    let active = true;

    async function startCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: facingMode } },
          audio: false,
        });
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play();
        }

        if ('BarcodeDetector' in window) {
          const barcodeDetector = new window.BarcodeDetector({ formats: ['qr_code'] });
          scanIntervalRef.current = setInterval(async () => {
            if (
              videoRef.current &&
              videoRef.current.readyState === videoRef.current.HAVE_ENOUGH_DATA
            ) {
              try {
                const barcodes = await barcodeDetector.detect(videoRef.current);
                if (barcodes && barcodes.length > 0) {
                  const scannedVal = barcodes[0].rawValue;
                  if (scannedVal) {
                    performCheckin(scannedVal);
                  }
                }
              } catch {
                // Ignore detector frame error
              }
            }
          }, 400);
        }
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
      <SectionHead kicker="DOOR DESK &amp; EVENT CHECK-IN" title="Check-in &amp; Scanner Station" />
      <Panel className="checkin-panel">
        {/* Live Camera Scanner Box */}
        {cameraActive ? (
          <div
            style={{
              position: 'relative',
              width: '100%',
              maxWidth: '380px',
              margin: '0 auto 20px auto',
              borderRadius: '14px',
              overflow: 'hidden',
              border: '2px solid rgba(56, 189, 248, 0.5)',
              background: '#09090b',
              boxShadow: '0 12px 32px rgba(0,0,0,0.8)',
            }}
          >
            <video
              ref={videoRef}
              playsInline
              muted
              style={{ width: '100%', height: '240px', objectFit: 'cover' }}
            />
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
                  width: '180px',
                  height: '180px',
                  border: '2px dashed rgba(56, 189, 248, 0.9)',
                  borderRadius: '12px',
                  boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.4)',
                }}
              />
            </div>
            {/* Camera Controls Overlay */}
            <div
              style={{
                position: 'absolute',
                bottom: '10px',
                left: 0,
                right: 0,
                display: 'flex',
                justifyContent: 'center',
                gap: '8px',
              }}
            >
              <button
                type="button"
                onClick={() => setFacingMode((m) => (m === 'environment' ? 'user' : 'environment'))}
                style={{
                  background: 'rgba(15, 23, 42, 0.85)',
                  color: '#fff',
                  border: '1px solid rgba(255,255,255,0.2)',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <FlipHorizontal size={13} /> Switch Camera
              </button>
              <button
                type="button"
                onClick={() => setCameraActive(false)}
                style={{
                  background: 'rgba(239, 68, 68, 0.85)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <CameraOff size={13} /> Stop Camera
              </button>
            </div>
          </div>
        ) : null}

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '16px' }}>
          <Button
            type="button"
            variant={cameraActive ? 'primary' : 'ghost'}
            onClick={() => setCameraActive((v) => !v)}
            icon={cameraActive ? CameraOff : Camera}
          >
            {cameraActive ? 'Close Camera Scanner' : 'Open Camera QR Scanner'}
          </Button>
        </div>

        <form onSubmit={scan} className="checkin-form">
          <Field
            label="Check-in Station / Event"
            hint="Pick an event for workshop / competition verification, or General Pass for door turnstile admission."
          >
            <select
              value={selectedEventId}
              onChange={(e) => setSelectedEventId(e.target.value)}
              style={{
                width: '100%',
                background: 'rgba(255,255,255,0.05)',
                color: '#fff',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: '8px',
                padding: '9px 12px',
                fontSize: '14px',
              }}
            >
              <option value="">🎟️ General Fest Turnstile Admission (All Passes)</option>
              {(eventsList.data?.data || []).map((ev) => (
                <option key={ev.id} value={ev.id}>
                  🎯 {ev.title} {ev.venueRoom ? `· Room ${ev.venueRoom}` : ''} ({ev.categoryName || ev.category})
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
              autoFocus
              required
            />
          </Field>

          <Field label="Convention Day">
            <input type="date" value={day} onChange={(event) => setDay(event.target.value)} />
          </Field>

          <Button type="submit" disabled={busy || !token.trim()} icon={ClipboardCheck}>
            {busy ? 'Verifying…' : 'Admit & Check-in'}
          </Button>
        </form>

        {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}

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
              {result.registrationNumber || 'Registered Attendee'} ·{' '}
              {dateTime(result.checkedInAt)}
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
              <Button variant="ghost" size="small" onClick={() => rosterAsync.reload()} icon={RefreshCw}>
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
  const [form, setForm] = useState({ title: '', bodyMd: '', audience: 'public', status: 'draft' });

  useEffect(() => {
    if (!sheet) return;
    setForm({
      title: sheet.title || '',
      bodyMd: sheet.bodyMd || '',
      audience: sheet.audience || 'public',
      status: sheet.status || 'draft',
    });
  }, [sheet]);

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const payload = { ...form };
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
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
      {rows.loading ? <Loading label="Loading announcements" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={['Title', 'Audience', 'Status', 'Published', '']}
        empty={!list.length && !rows.loading ? 'No announcements yet.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>
              <b>{row.title}</b>
              <div className="table-sub">{row.bodyMd?.slice(0, 90)}</div>
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
    { enabled: Boolean(slug) }
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
    }
  );
  const list = rows.data?.data || [];

  const handleRevoke = async (attendanceId) => {
    if (!window.confirm('Revoke this attendance record?')) return;
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
          <select
            value={selectedEventId}
            onChange={(e) => setSelectedEventId(e.target.value)}
          >
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
        <Button variant="ghost" onClick={rows.reload} icon={RefreshCw}>
          Refresh
        </Button>
      </div>
      {rows.loading ? <Loading label="Loading attendance" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={['Participant', 'Station / Event', 'Room / Venue', 'Day', 'Result', 'Checked In', 'Host / Staff', 'Actions']}
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
      allowedEmailDomains: (data.allowedEmailDomains || []).join(', '),
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
        allowedEmailDomains: form.allowedEmailDomains
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
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
      await adminApi.grantMembership(editionId, staffForm);
      await memberships.reload();
      setStaffForm({ email: '', role: 'event_coordinator' });
      setMessage({ tone: 'success', text: 'Staff role granted.' });
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

  const memberRows = memberships.data?.data || [];
  const iconRows = icons.data?.data || [];

  return (
    <>
      <SectionHead kicker="CONFIGURATION" title="Edition settings" />
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
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
              <input value={form.venue} onChange={(event) => set('venue', event.target.value)} />
            </Field>
            <Field label="City">
              <input value={form.city} onChange={(event) => set('city', event.target.value)} />
            </Field>
            <Field label="Starts at">
              <input
                type="datetime-local"
                value={form.startsAt}
                onChange={(event) => set('startsAt', event.target.value)}
              />
            </Field>
            <Field label="Ends at">
              <input
                type="datetime-local"
                value={form.endsAt}
                onChange={(event) => set('endsAt', event.target.value)}
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
                {['draft', 'published', 'archived'].map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Contact email">
              <input
                type="email"
                value={form.contactEmail}
                onChange={(event) => set('contactEmail', event.target.value)}
              />
            </Field>
            <Field label="Allowed email domains" hint="Comma separated." className="full-span">
              <input
                value={form.allowedEmailDomains}
                onChange={(event) => set('allowedEmailDomains', event.target.value)}
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
                {Object.entries(ROLE_LABELS)
                  .filter(([role]) => role !== 'participant' && role !== 'super_admin')
                  .map(([role, label]) => (
                    <option key={role} value={role}>
                      {label}
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
                  if (!window.confirm(`Archive the icon "${icon.name}"? Pages stop showing it.`)) return;
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
