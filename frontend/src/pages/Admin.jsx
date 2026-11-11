import { useEffect, useRef, useState } from 'react';
import { BrowserQRCodeReader } from '@zxing/browser';
import { Link, Navigate, NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  ArrowUpRight,
  BadgeCheck,
  CalendarDays,
  LayoutDashboard,
  Check,
  ClipboardCheck,
  CreditCard,
  FileText,
  Image,
  LogOut,
  Megaphone,
  Menu,
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
import {
  date,
  dateTime,
  fromLocalInput,
  money,
  paise,
  rupees,
  toLocalInput,
  toISTInput,
  fromISTInput,
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

const LOGO = String(import.meta.env.BASE_URL) + 'images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp';

const NAV = [
  ['Overview', '/manage', LayoutDashboard, true],
  ['Events', '/manage/events', CalendarDays],
  ['Policy', '/manage/policy', ShieldCheck],
  ['Registrations', '/manage/registrations', Ticket],
  ['Users', '/manage/users', Users],
  ['Verifications', '/manage/verifications', BadgeCheck],
  ['Payments', '/manage/payments', Wallet],
  ['Check-in', '/manage/check-in', ClipboardCheck],
  ['Announcements', '/manage/announcements', Megaphone],
  ['Attendance', '/manage/attendance', FileText],
  ['Audit log', '/manage/audit', FileText],
  ['Settings', '/manage/settings', Settings],
];

const ROLE_LABELS = {
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
      setSyncToast('Caches purged & synchronized with database!');
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
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (!isStaff) return <Navigate to="/portal" replace />;

  return (
    <div className="admin-shell">
      {/* Dedicated Admin Header */}
      <header className="admin-header">
        <div className="admin-brand-lockup">
          <Link to="/manage" className="admin-brand-link" aria-label="Staff operations home">
            <img src={LOGO} alt={edition?.name || 'Parallax'} className="admin-brand-logo" />
          </Link>
          <span className="admin-badge-console">Staff Console</span>
          {edition?.name ? <span className="admin-edition-chip">{edition.name}</span> : null}
        </div>

        <nav className="admin-header-nav" aria-label="Staff navigation shortcuts">
          {/* Switch to Participant Portal */}
          <Link to="/portal" className="admin-link-pill" title="Open participant portal">
            <Users size={14} strokeWidth={1.6} />
            <span className="hide-xs">Participant Portal</span>
          </Link>

          {/* Switch to Public Site */}
          <Link to="/" className="admin-link-pill" title="View live convention website">
            <ArrowUpRight size={14} strokeWidth={1.6} />
            <span className="hide-xs">Live Site</span>
          </Link>

          {/* Force Cache Refresh */}
          <button
            className="admin-link-pill admin-sync-pill"
            onClick={handleForceRefresh}
            title="Force purge all caches and reload live database state"
            disabled={syncing}
            type="button"
          >
            <RefreshCw size={13} strokeWidth={1.8} className={syncing ? 'spin' : ''} />
            <span className="hide-xs">{syncing ? 'Syncing…' : 'Force Refresh'}</span>
          </button>

          {/* Staff Identity Pill */}
          <div className="admin-user-pill">
            <span className="admin-role-tag">{ROLE_LABELS[roles[0]] || 'Staff'}</span>
            <span className="admin-user-email">{user?.email}</span>
          </div>

          {/* Sign Out */}
          <button className="admin-signout-btn" onClick={logout} title="Sign out of staff account">
            <LogOut size={14} strokeWidth={1.6} />
            <span className="hide-sm">Sign out</span>
          </button>

          {/* Mobile Menu Button */}
          <button
            className="admin-mobile-menu-btn"
            onClick={() => setMobileNavOpen((open) => !open)}
            aria-label={mobileNavOpen ? 'Close staff menu' : 'Open staff menu'}
            aria-expanded={mobileNavOpen}
          >
            {mobileNavOpen ? <X size={18} strokeWidth={1.8} /> : <Menu size={18} strokeWidth={1.8} />}
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
        <div className="admin-mobile-drawer" role="dialog" aria-modal="true" aria-label="Staff modules">
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
            <span className="admin-sidebar-meta">12 modules</span>
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
  const { editionId } = useSite();
  const stats = useAsync(() => adminApi.overview(editionId), [editionId], { enabled: Boolean(editionId) });
  const data = stats.data?.data;

  if (stats.loading) return <Loading label="Loading operational telemetry" rows={3} />;
  if (stats.error) return <ErrorBox error={stats.error} onRetry={stats.reload} />;

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
        <Stat label="PASSES SOLD" value={data?.passesSold ?? 0} note={`${data?.passesPending ?? 0} pending`} />
        <Stat label="REVENUE" value={money(data?.revenuePaise || 0)} note={`${money(data?.refundedPaise || 0)} refunded`} />
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
        <Stat label="SEATS TAKEN" value={`${data?.seatsTaken ?? 0} / ${data?.seatsCapacity ?? 0}`} note="Taken / capacity" />
        <Stat
          label="VERIFICATIONS"
          value={data?.verificationsPending ?? 0}
          note="Awaiting review"
          tone={data?.verificationsPending ? 'warn' : ''}
        />
        <Stat
          label="LATEST DAY SALES"
          value={(data?.salesByDay || []).length ? money((data.salesByDay.at(-1)?.amountPaise) || 0) : '₹0'}
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
                  key={row.id || row.registrationNumber || `${row.userName}-${row.eventTitle}`}
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
      adminApi.icons(editionId).then((res) => {
        setIconsList(res.data || []);
      }).catch(() => {});
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
        registrationOpensAt: fromLocalInput(form.registrationOpensAt) || fromLocalInput(form.startsAt),
        registrationClosesAt: fromLocalInput(form.registrationClosesAt) || fromLocalInput(form.startsAt),
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
          <input value={form.title} onChange={(event) => set('title', event.target.value)} required />
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
          <select value={form.categoryId} onChange={(event) => set('categoryId', event.target.value)} required>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category?.name || 'Category'}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Event Banner (Supabase Storage or Custom URL)" hint="Upload image or paste image link (16:9 recommended)">
          <div className="banner-input-wrap">
            <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
              <input
                type="url"
                aria-label="Banner image URL" placeholder="https://... or click Upload Banner"
                value={form.bannerUrl || ''}
                onChange={(e) => set('bannerUrl', e.target.value)}
                style={{ flex: 1 }}
              />
              <label className="btn-upload-file" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '0 14px', height: '40px', background: 'rgba(56,189,248,0.12)', border: '1px solid rgba(56,189,248,0.35)', borderRadius: '6px', color: '#38bdf8', cursor: 'pointer', fontSize: '12px', fontWeight: 600, whiteSpace: 'nowrap' }}>
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
              <div style={{ position: 'relative', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.15)', maxHeight: '120px' }}>
                <img src={form.bannerUrl} alt="Banner preview" style={{ width: '100%', height: '120px', objectFit: 'cover', display: 'block' }} onError={(e) => { e.target.style.display = 'none'; }} />
                <button
                  type="button"
                  className="btn-clear-icon"
                  style={{ position: 'absolute', top: '8px', right: '8px', background: 'rgba(0,0,0,0.75)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)', padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', fontSize: '11px' }}
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
          <input value={form.venueRoom} onChange={(event) => set('venueRoom', event.target.value)} />
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
        <Field label="Event Icon / Artwork" hint="Select from catalog or upload an image file" className="full-span">
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
          <select value={form.addonChargeBasis} onChange={(event) => set('addonChargeBasis', event.target.value)}>
            <option value="per_participant">Per participant</option>
            <option value="per_team">Per team</option>
          </select>
        </Field>
        <Field label="Team fee basis">
          <select value={form.teamFeeBasis} onChange={(event) => set('teamFeeBasis', event.target.value)}>
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
          <select value={form.capacityUnit} onChange={(event) => set('capacityUnit', event.target.value)}>
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
          aria-label="Short event summary" placeholder="Brief 1-2 sentence overview for cards and public previews"
          required
        />
      </Field>
      <Field label="Description (Markdown)" className="full-span" hint="Detailed agenda, eligibility, and instructions">
        <textarea
          rows="4"
          value={form.descriptionMd}
          onChange={(event) => set('descriptionMd', event.target.value)}
          aria-label="Event details in Markdown" placeholder="Write in Markdown. Detailed breakdown of the event, schedule, and guidelines..."
        />
      </Field>
      <Field label="Rules (Markdown)" className="full-span" hint="Code of conduct and evaluation criteria">
        <textarea
          rows="3"
          value={form.rulesMd}
          onChange={(event) => set('rulesMd', event.target.value)}
          aria-label="Round guidelines, one step per line" placeholder="1. General guidelines&#10;2. Round structure and timing&#10;3. Judging criteria..."
        />
      </Field>
      <Field label="Prizes (Markdown)" className="full-span" hint="Cash rewards, certificates, or perks">
        <textarea
          rows="2"
          value={form.prizesMd}
          onChange={(event) => set('prizesMd', event.target.value)}
          aria-label="Prize breakdown" placeholder="1st Prize: ₹10,000&#10;2nd Prize: ₹5,000&#10;Certificates for all finalists"
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
                slug: editId ? form.slug : event.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
              })
            }
            required
          />
        </Field>
        <Field label="Slug">
          <input value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value })} required />
        </Field>
        <Field label="Accent">
          <select value={form.accent} onChange={(event) => setForm({ ...form, accent: event.target.value })}>
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
                    style={{ width: '44px', height: '28px', objectFit: 'cover', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.15)', flexShrink: 0 }}
                  />
                ) : null}
                <div>
                  <b>{row.title}</b>
                  <div className="table-sub">{row.slug}</div>
                </div>
              </div>
            </td>
            <td>{row.categoryName}</td>
            <td>{row.format === 'team' ? `Team ${row.teamMinSize}-${row.teamMaxSize}` : 'Individual'}</td>
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
                <button className="table-action" onClick={() => openEdit(row)} disabled={busyId === row.id}>
                  {busyId === row.id ? 'Loading' : 'Edit'}
                </button>
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

export function AdminPolicy() {
  const { editionId } = useSite();
  const policies = useAsync(() => adminApi.policies(editionId), [editionId], { enabled: Boolean(editionId) });
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
          passPrice: '350',
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
            <input type="number" min="0" step="50" value={form.passPrice} onChange={(event) => set('passPrice', event.target.value)} />
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
            <input type="number" min="0" step="50" value={form.cap} onChange={(event) => set('cap', event.target.value)} />
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
            <input type="datetime-local" value={form.deadline} onChange={(event) => set('deadline', event.target.value)} />
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
            <input value={form.reason} onChange={(event) => set('reason', event.target.value)} aria-label="Explain this version" placeholder="Explain this version" />
          </Field>
        </FieldGrid>
        <div className="toggle-row">
          <Toggle checked={form.capInclusive} onChange={(value) => set('capInclusive', value)} label="Cap is inclusive" />
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
                set('lunchDays', value ? [...form.lunchDays, day] : form.lunchDays.filter((item) => item !== day))
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
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const debounced = useDebounced(query);
  const rows = useAsync(
    () =>
      adminApi.registrations(editionId, {
        status,
        q: debounced,
        page,
        page_size: 50,
      }),
    [editionId, status, debounced, page],
    { enabled: Boolean(editionId) }
  );
  const list = rows.data?.data || [];
  const total = rows.data?.total ?? list.length;
  const pages = Math.max(1, Math.ceil(total / 50));

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
            aria-label="Name, email, PX-..., or event title..." placeholder="Name, email, PX-..., or event title..."
          />
        </Field>
        <Field label="Status filter">
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {['confirmed', 'reserved', 'pending', 'cancelled'].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>
        <Button variant="ghost" onClick={rows.reload} icon={RefreshCw}>
          Refresh
        </Button>
      </div>
      {rows.loading ? <Loading label="Loading registrations" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={['Reg #', 'Participant', 'Event', 'Kind', 'Fee', 'Status', 'Date']}
        empty={!list.length && !rows.loading ? 'No registrations match.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td className="mono-note">{row.registrationNumber}</td>
            <td>
              <b>{row.userName}</b>
              <div className="table-sub">{row.userEmail}</div>
            </td>
            <td>{row.eventTitle}</td>
            <td>{row.kind}</td>
            <td>{money(row.feePaise)}</td>
            <td>
              <StatusBadge status={row.status} />
            </td>
            <td>{date(row.createdAt)}</td>
          </tr>
        ))}
      </DataTable>
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
    </>
  );
}

export function AdminUsers() {
  const { editionId } = useSite();
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query);
  const users = useAsync(() => adminApi.users(editionId, { q: debounced }), [editionId, debounced], {
    enabled: Boolean(editionId),
  });
  const [choiceKind, setChoiceKind] = useState('branch');
  const choices = useAsync(() => adminApi.profileChoices(editionId, choiceKind), [editionId, choiceKind], { enabled: Boolean(editionId) });
  const choiceList = choices.data?.data || [];
  const [sourceChoice, setSourceChoice] = useState('');
  const [targetChoice, setTargetChoice] = useState('');
  const [target, setTarget] = useState(null);
  const [reason, setReason] = useState('');
  const [message, setMessage] = useState(null);
  const rows = users.data?.data || [];

  const mergeChoice = async () => {
    try {
      await adminApi.mergeProfileChoice(editionId, sourceChoice, targetChoice);
      await choices.reload();
      setSourceChoice('');
      setTargetChoice('');
      setMessage({ tone: 'success', text: 'Profile choice merged.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

  const removeChoice = async () => {
    if (!sourceChoice || !window.confirm('Delete this unused profile choice?')) return;
    try {
      await adminApi.deleteProfileChoice(editionId, sourceChoice);
      await choices.reload();
      setSourceChoice('');
      setMessage({ tone: 'success', text: 'Profile choice deleted.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    }
  };

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
          <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Name or email" placeholder="Name or email" />
        </Field>
      </div>
      <details className="profile-choice-admin">
        <summary>Manage branch and college options</summary>
        <div className="table-filters">
          <Field label="Option type">
            <select value={choiceKind} onChange={(event) => { setChoiceKind(event.target.value); setSourceChoice(''); setTargetChoice(''); }}>
              <option value="branch">Branches</option><option value="college">Colleges</option>
            </select>
          </Field>
          <Field label="Entry">
            <select value={sourceChoice} onChange={(event) => setSourceChoice(event.target.value)}>
              <option value="">Choose an entry</option>
              {choiceList.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
          <Field label="Merge into">
            <select value={targetChoice} onChange={(event) => setTargetChoice(event.target.value)}>
              <option value="">Choose a target</option>
              {choiceList.filter((item) => item.id !== sourceChoice).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
          <div className="sheet-actions">
            <Button variant="ghost" onClick={removeChoice} disabled={!sourceChoice}>Delete unused</Button>
            <Button onClick={mergeChoice} disabled={!sourceChoice || !targetChoice}>Merge entries</Button>
          </div>
        </div>
      </details>
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
            <td>{(row.roles || []).map((role) => ROLE_LABELS[role] || role).join(', ') || 'Participant'}</td>
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
              {row.status === 'deletion_requested' ? (
                <button className="table-action" onClick={async () => {
                  if (!window.confirm(`Delete ${row.fullName}'s account data and documents?`)) return;
                  try {
                    await adminApi.fulfillDeletion(editionId, row.id);
                    await users.reload();
                    setMessage({ tone: 'success', text: 'Account data and documents deleted.' });
                  } catch (error) {
                    setMessage({ tone: 'error', text: error.message });
                  }
                }}>Fulfill deletion request</button>
              ) : null}
            </td>
          </tr>
        ))}
      </DataTable>
      <Sheet open={Boolean(target)} title="Change account status" onClose={() => setTarget(null)}>
        <p className="muted">
          {target?.status === 'active' ? 'Suspend' : 'Reactivate'} <b>{target?.fullName}</b>? Suspended
          accounts cannot sign in or register.
        </p>
        <Field label="Reason">
          <input value={reason} onChange={(event) => setReason(event.target.value)} aria-label="Shown in the audit log" placeholder="Shown in the audit log" />
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
  const [fakeOrInvalid, setFakeOrInvalid] = useState(false);
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
        fakeOrInvalid: decision === 'rejected' && fakeOrInvalid,
      });
      await rows.reload();
      setTarget(null);
      setReason('');
      setFakeOrInvalid(false);
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
              <button className="table-action" onClick={() => window.open(adminApi.profileDocumentUrl(editionId, row.userId, 'college_id'), '_blank', 'noopener,noreferrer')}>
                View College ID
              </button>
              <button className="table-action" onClick={() => window.open(adminApi.profileDocumentUrl(editionId, row.userId, 'iste_proof'), '_blank', 'noopener,noreferrer')}>
                View ISTE Proof
              </button>
              {row.documentName ? (
                <button className="table-action" onClick={() => openDocument(row.id)}>
                  View Document
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
                  setFakeOrInvalid(false);
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
        <Field label="Reason" hint={decision === 'rejected' ? 'Required for a rejection.' : 'Optional note.'}>
          <input value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        {decision === 'rejected' ? <label className="privacy-consent"><input type="checkbox" checked={fakeOrInvalid} onChange={(event) => setFakeOrInvalid(event.target.checked)} /> Mark the proof as fake or invalid and automatically refund paid orders.</label> : null}
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setTarget(null)}>
            Cancel
          </Button>
          <Button onClick={decide} disabled={decision === 'rejected' && !reason.trim()} icon={BadgeCheck}>
            Save decision
          </Button>
        </div>
      </Sheet>
    </>
  );
}

export function AdminPayments() {
  const { editionId } = useSite();
  const payments = useAsync(() => adminApi.payments(editionId), [editionId], { enabled: Boolean(editionId) });
  const refunds = useAsync(() => adminApi.refunds(editionId), [editionId], { enabled: Boolean(editionId) });
  const [target, setTarget] = useState(null);
  const [form, setForm] = useState({ amount: '', reasonCode: 'requested_by_participant', note: '' });
  const [message, setMessage] = useState(null);
  const list = payments.data?.data || [];
  const refundRows = refunds.data?.data || [];

  const openRefund = (row) => {
    setTarget(row);
    setForm({
      amount: rupees(row.amountPaise),
      reasonCode: 'requested_by_participant',
      note: '',
      idempotencyKey: globalThis.crypto?.randomUUID?.() || `refund-${row.id}-${Date.now()}`,
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
        idempotencyKey: form.idempotencyKey,
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
            <select value={form.reasonCode} onChange={(event) => setForm({ ...form, reasonCode: event.target.value })}>
              {['requested_by_participant', 'duplicate', 'event_cancelled', 'payment_failed', 'other'].map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </Field>
        </FieldGrid>
        <Field label="Note">
          <input value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
        </Field>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setTarget(null)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!form.amount || Number(form.amount) <= 0} icon={CreditCard}>
            Request refund
          </Button>
        </div>
      </Sheet>
    </>
  );
}

export function AdminCheckin() {
  const { editionId } = useSite();
  const [token, setToken] = useState('');
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [scannerActive, setScannerActive] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const videoRef = useRef(null);
  const scannerControls = useRef(null);
  const scanLocked = useRef(false);
  const recent = useAsync(() => adminApi.recentCheckins(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const attendance = useAsync(() => adminApi.attendance(editionId, { day }), [editionId, day], {
    enabled: Boolean(editionId),
  });

  const stopScanner = () => {
    scannerControls.current?.stop();
    scannerControls.current = null;
    setScannerActive(false);
  };

  useEffect(() => () => scannerControls.current?.stop(), []);

  const checkInToken = async (rawToken) => {
    const cleanToken = String(rawToken || '').trim();
    if (!cleanToken) return;
    setBusy(true);
    setMessage(null);
    setResult(null);
    try {
      const body = await adminApi.checkin(editionId, { token: cleanToken, day: day || null });
      setResult(body.data);
      setToken('');
      recent.reload();
      attendance.reload();
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy(false);
    }
  };

  const scan = (event) => {
    event.preventDefault();
    void checkInToken(token);
  };

  const startScanner = async () => {
    setCameraError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Camera scanning is unavailable in this browser. Use the ticket token field.');
      return;
    }
    try {
      const reader = new BrowserQRCodeReader();
      setScannerActive(true);
      const controls = await reader.decodeFromVideoDevice(undefined, videoRef.current, (result) => {
        if (!result || scanLocked.current) return;
        scanLocked.current = true;
        const ticketToken = result.getText().trim();
        scannerControls.current?.stop();
        scannerControls.current = null;
        setScannerActive(false);
        setToken(ticketToken);
        void checkInToken(ticketToken).finally(() => {
          scanLocked.current = false;
        });
      });
      scannerControls.current = controls;
    } catch {
      setScannerActive(false);
      setCameraError('Could not start the camera. Check camera permission or enter the token manually.');
    }
  };

  const recentRows = recent.data?.data || [];
  const attendanceRows = attendance.data?.data || [];

  return (
    <>
      <SectionHead kicker="DOOR DESK" title="Check-in" />
      <Panel className="checkin-panel">
        <div className="checkin-camera-actions">
          {!scannerActive ? <Button variant="ghost" onClick={startScanner} icon={Search}>Scan QR with camera</Button> : null}
          {scannerActive ? <Button variant="ghost" onClick={stopScanner} icon={X}>Stop camera</Button> : null}
          {cameraError ? <InlineMessage tone="error">{cameraError}</InlineMessage> : null}
        </div>
        <video ref={videoRef} className="checkin-camera" hidden={!scannerActive} autoPlay muted playsInline aria-label="Live camera view for scanning a ticket QR code" />
        <form onSubmit={scan} className="checkin-form">
          <Field label="Ticket token" hint="Scan the QR, or type the PX-… token from the participant portal.">
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              aria-label="PX-…" placeholder="PX-…"
              autoFocus
              required
            />
          </Field>
          <Field label="Convention day">
            <input type="date" value={day} onChange={(event) => setDay(event.target.value)} />
          </Field>
          <Button type="submit" disabled={busy || !token.trim()} icon={ClipboardCheck}>
            {busy ? 'Checking' : 'Admit participant'}
          </Button>
        </form>
        {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
        {result ? (
          <div className={`checkin-result ${result.result}`}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span>{result.result}</span>
              <button
                type="button"
                className="button ghost small"
                onClick={() => setResult(null)}
                style={{ fontSize: 11, padding: '4px 8px' }}
              >
                Scan next
              </button>
            </div>
            <h3>{result.participantName}</h3>
            <p>
              {result.eventTitle || 'Convention pass'} · {result.registrationNumber || 'no registration number'} ·{' '}
              {dateTime(result.checkedInAt)}
            </p>
            {result.message ? <p className="muted">{result.message}</p> : null}
          </div>
        ) : null}
      </Panel>

      <div className="portal-columns">
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
          <Eyebrow>ATTENDANCE · {day}</Eyebrow>
          <p className="mono-note">{attendanceRows.length} records</p>
          {attendanceRows.slice(0, 8).map((row) => (
            <div className="detail-row" key={row.id}>
              <span>{row.participantName}</span>
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

      <Sheet open={Boolean(sheet)} title={sheet?.id ? 'Edit announcement' : 'New announcement'} onClose={() => setSheet(null)}>
        <form className="admin-form" onSubmit={save}>
          <Field label="Title">
            <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
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
              <select value={form.audience} onChange={(event) => setForm({ ...form, audience: event.target.value })}>
                {['public', 'participants', 'staff'].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Status">
              <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
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
  const { editionId } = useSite();
  const [day, setDay] = useState('');
  const rows = useAsync(() => adminApi.attendance(editionId, { day }), [editionId, day], {
    enabled: Boolean(editionId),
  });
  const list = rows.data?.data || [];

  return (
    <>
      <SectionHead kicker="DOOR RECORDS" title="Attendance" />
      <div className="table-filters">
        <Field label="Day">
          <input type="date" value={day} onChange={(event) => setDay(event.target.value)} />
        </Field>
        <Button variant="ghost" onClick={rows.reload}>
          Refresh
        </Button>
      </div>
      {rows.loading ? <Loading label="Loading attendance" rows={2} /> : null}
      {rows.error ? <ErrorBox error={rows.error} onRetry={rows.reload} /> : null}
      <DataTable
        head={['Participant', 'Event', 'Day', 'Result', 'Checked in', 'By']}
        empty={!list.length && !rows.loading ? 'No attendance records.' : null}
      >
        {list.map((row) => (
          <tr key={row.id}>
            <td>
              <b>{row.participantName}</b>
            </td>
            <td>{row.eventTitle || 'Convention pass'}</td>
            <td>{row.day || '-'}</td>
            <td>
              <StatusBadge status={row.result} />
            </td>
            <td>{dateTime(row.checkedInAt)}</td>
            <td>{row.checkedInByName || '-'}</td>
          </tr>
        ))}
      </DataTable>
    </>
  );
}

export function AdminAudit() {
  const { editionId } = useSite();
  const rows = useAsync(() => adminApi.audit(editionId), [editionId], { enabled: Boolean(editionId) });
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
  const settings = useAsync(() => adminApi.settings(editionId), [editionId], { enabled: Boolean(editionId) });
  const memberships = useAsync(() => adminApi.memberships(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const icons = useAsync(() => adminApi.icons(editionId), [editionId], { enabled: Boolean(editionId) });
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
      registrationUnlockAt: toISTInput(data.registrationUnlockAt),
      rateISTE: data.registrationPrices?.isteMemberPaise ?? 49900,
      rateNonISTE: data.registrationPrices?.nonIstePaise ?? 59900,
      ratePolytechnic: data.registrationPrices?.polytechnicPaise ?? 29900,
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
        registrationUnlockAt: fromISTInput(form.registrationUnlockAt),
        registrationPriceIsteMemberPaise: Number(form.rateISTE),
        registrationPriceNonIstePaise: Number(form.rateNonISTE),
        registrationPricePolytechnicPaise: Number(form.ratePolytechnic),
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
              <input value={form.name} onChange={(event) => set('name', event.target.value)} required />
            </Field>
            <Field label="Tagline">
              <input value={form.tagline} onChange={(event) => set('tagline', event.target.value)} />
            </Field>
            <Field label="Venue">
              <input value={form.venue} onChange={(event) => set('venue', event.target.value)} />
            </Field>
            <Field label="City">
              <input value={form.city} onChange={(event) => set('city', event.target.value)} />
            </Field>
            <Field label="Starts at">
              <input type="datetime-local" value={form.startsAt} onChange={(event) => set('startsAt', event.target.value)} />
            </Field>
            <Field label="Ends at">
              <input type="datetime-local" value={form.endsAt} onChange={(event) => set('endsAt', event.target.value)} />
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
            <Field label="Registration unlock (IST)" hint="Stored in UTC; this value is shown in India Standard Time.">
              <input type="datetime-local" value={form.registrationUnlockAt} onChange={(event) => set('registrationUnlockAt', event.target.value)} required />
            </Field>
            <Field label="ISTE member rate (₹)">
              <input type="number" min="1" value={form.rateISTE / 100} onChange={(event) => set('rateISTE', Math.round((Number(event.target.value) || 0) * 100))} required />
            </Field>
            <Field label="Non-ISTE rate (₹)">
              <input type="number" min="1" value={form.rateNonISTE / 100} onChange={(event) => set('rateNonISTE', Math.round((Number(event.target.value) || 0) * 100))} required />
            </Field>
            <Field label="Polytechnic rate (₹)" hint="Polytechnic rate takes precedence over ISTE membership.">
              <input type="number" min="1" value={form.ratePolytechnic / 100} onChange={(event) => set('ratePolytechnic', Math.round((Number(event.target.value) || 0) * 100))} required />
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
              <input type="email" value={form.contactEmail} onChange={(event) => set('contactEmail', event.target.value)} />
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
            <input type="email" value={invite} onChange={(event) => setInvite(event.target.value)} />
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
            <input value={iconForm.name} onChange={(event) => setIconForm({ ...iconForm, name: event.target.value })} />
          </Field>
          <Field label="SVG or PNG">
            <input
              type="file"
              accept="image/svg+xml,image/png"
              onChange={(event) => setIconForm({ ...iconForm, file: event.target.files?.[0] || null })}
            />
          </Field>
          <Toggle
            checked={iconForm.recolorable}
            onChange={(value) => setIconForm({ ...iconForm, recolorable: value })}
            label="Recolorable"
          />
          <Button type="submit" disabled={busy === 'icon' || !iconForm.file} variant="ghost" icon={Image}>
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
