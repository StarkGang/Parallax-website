import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate, useSearchParams } from 'react-router-dom';
import { Avatar, Box, Stack, Typography } from '@mui/material';
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Copy,
  CreditCard,
  Download,
  LogOut,
  Plus,
  Printer,
  RefreshCw,
  ShieldCheck,
  Ticket,
  Users,
} from 'lucide-react';
import { authApi, portalApi, publicApi, registrationApi } from '../lib/api.js';
import { payOrder } from '../lib/pay.js';
import { CompleteReceiptSheet } from '../components/CompleteReceiptSheet.jsx';
import { PaymentProgress } from '../components/PaymentProgress.jsx';
import '../components/PassTierCard.css';
import { ISTE, LOGO, NSSCE } from './Public.jsx';
import './Worklist.css';
import './EventCard.css';

import { PORTAL_AVATARS, usePortalAvatar } from '../lib/portalAvatar.js';
import { resolveImageUrl } from '../lib/imageUrl.js';
import { EventGeneratedPoster } from '../components/EventGeneratedPoster.jsx';
import {
  BRANCH_SUGGESTIONS,
  COLLEGE_SUGGESTIONS,
  ComboInput,
  INDIAN_STATES,
  KERALA_CITIES,
  SelectInput,
  YEAR_SUGGESTIONS,
  normalizeYear,
  parseYearNumber,
} from '../components/AttendeeInputs.jsx';

const REG_EVENT_FRAME = `${import.meta.env.BASE_URL}images/event_frame.png`;
const REG_BG_CORE = `${import.meta.env.BASE_URL}images/parallax-bg-core.webp`;
const REG_BG_VAULT = `${import.meta.env.BASE_URL}images/parallax-bg-vault.webp`;
const REG_BG_PEDESTAL = `${import.meta.env.BASE_URL}images/parallax-bg-pedestal.webp`;
const REG_BG_DEPTH = `${import.meta.env.BASE_URL}images/parallax-depth-bg.webp`;

function regBackdrop(category = '') {
  const cat = String(category).toLowerCase();
  if (cat.includes('comput') || cat.includes('code')) return REG_BG_CORE;
  if (cat.includes('robot') || cat.includes('electr')) return REG_BG_VAULT;
  if (cat.includes('civil') || cat.includes('mech')) return REG_BG_PEDESTAL;
  return REG_BG_DEPTH;
}
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { date, dateTime, initials, money } from '../lib/format.js';
import { eventListPricePaise } from '../lib/pricing.js';
import { FOOD_OPTIONS, GENDER_OPTIONS } from '../lib/attendee.js';
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Eyebrow,
  Feedback,
  Field,
  FieldGrid,
  InlineMessage,
  Loading,
  PageTitle,
  Panel,
  SectionHead,
  StatusBadge,
  Sheet,
  clearAsyncCache,
  useAsync,
} from '../components/ui.jsx';

const PORTAL_NAV = [
  ['My Pass & Ticket', '/portal/registration'],
  ['Browse Events', '/portal/events'],
  ['Teams & Invites', '/portal/teams'],
  ['My Events & Bills', '/portal/registrations'],
  ['Instructions & Guide', '/portal/instructions'],
  ['Profile & Settings', '/portal/profile'],
];

export function PortalLayout() {
  const { user, logout, isStaff, reload: reloadUser } = useAuth();
  const { edition, refresh: refreshSite } = useSite();
  const navigate = useNavigate();
  const [activeGlyph] = usePortalAvatar(user?.id, isStaff ? 'root' : 'parallax');
  const [pageKey, setPageKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState('');
  const lastRefreshRef = useRef(0);

  const signOut = async () => {
    await logout();
    navigate('/');
  };

  // Stale-data escape hatch: drop cached API responses, re-check the signed-in
  // profile and edition/policy, then remount the page so every widget refetches.
  const refreshAll = async () => {
    if (refreshing) return;
    // A short cooldown keeps a repeated click from becoming a request loop.
    if (Date.now() - lastRefreshRef.current < 10_000) {
      setRefreshNote('Just refreshed — wait a moment');
      return;
    }
    lastRefreshRef.current = Date.now();
    setRefreshing(true);
    setRefreshNote('');
    try {
      try {
        localStorage.removeItem('px_visited_events_portal');
        localStorage.removeItem('px_visited_teams_portal');
      } catch {}
      clearAsyncCache();
      const freshUser = await reloadUser();
      refreshSite();
      setPageKey((value) => value + 1);
      setRefreshNote(
        freshUser
          ? `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
          : 'Could not reach the server',
      );
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <>
      <PageTitle
        kicker="Attendee Portal"
        title="Your Convention Passes & Bookings"
        desc={`Signed in as ${user?.email} · Live bookings, selections, and entry tickets for ${edition?.name || 'Parallax 2027'}.`}
        aside={
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1 }}
          >
            <Button
              variant="ghost"
              size="small"
              icon={RefreshCw}
              loading={refreshing}
              onClick={refreshAll}
              className="portal-header-btn"
              title="Re-fetch your profile, pass and bookings from the server"
            >
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </Button>
            {refreshNote ? (
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {refreshNote}
              </Typography>
            ) : null}
            <span className="portal-side-role" style={{ marginBottom: 0 }}>
              {isStaff ? 'Staff Access' : `${edition?.name || 'Convention'} Attendee`}
            </span>
            {user?.profileComplete ? (
              <span className="portal-side-role portal-side-role--good" style={{ marginBottom: 0 }}>
                Profile Complete
              </span>
            ) : null}
            {isStaff ? (
              <Button variant="ghost" size="small" to="/manage" icon={ArrowUpRight} className="portal-header-btn">
                Staff Console
              </Button>
            ) : null}
          </Stack>
        }
      />

      {/* Mobile Top User Bar & Swipeable Tabs */}
      <div className="section" style={{ paddingBottom: 0, paddingTop: 10 }}>
        <Box
          className="portal-mobile-user-bar"
          sx={{
            display: { xs: 'flex', md: 'none' },
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', minWidth: 0 }}>
            <Avatar
              className={`portal-side-avatar ${isStaff ? 'is-staff' : 'is-attendee'} ${activeGlyph.kind === 'portrait' ? 'is-portrait' : ''}`}
              src={activeGlyph.src}
              alt={`${activeGlyph.label} avatar`}
              imgProps={{
                style:
                  activeGlyph.kind === 'portrait'
                    ? { objectFit: 'cover', objectPosition: 'center top', padding: 0 }
                    : { objectFit: 'contain', padding: '4px' },
              }}
              sx={{ width: 38, height: 38, fontSize: 13 }}
            >
              {initials(user?.fullName)}
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography
                variant="body2"
                sx={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
              >
                {user?.fullName || 'Attendee'}
              </Typography>
              <Typography
                variant="caption"
                sx={{ display: 'block', color: 'text.secondary', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
              >
                {user?.email}
              </Typography>
            </Box>
          </Stack>
          <Button variant="ghost" size="small" icon={LogOut} onClick={signOut} className="portal-side-signout">
            Sign out
          </Button>
        </Box>

        <nav className="portal-mobile-tabs" aria-label="Participant portal modules">
          {PORTAL_NAV.map(([label, to, end]) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `portal-mobile-tab-item ${isActive ? 'is-active' : ''}`}
            >
              <span>{label}</span>
            </NavLink>
          ))}
          {isStaff ? (
            <Link to="/manage" className="portal-mobile-tab-item portal-mobile-staff-tab">
              <span>Staff Console ↗</span>
            </Link>
          ) : null}
        </nav>
      </div>

      <section className="section portal-layout">
        <aside className="portal-side">
          <Avatar
            className={`portal-side-avatar ${isStaff ? 'is-staff' : 'is-attendee'} ${activeGlyph.kind === 'portrait' ? 'is-portrait' : ''}`}
            src={activeGlyph.src}
            alt={`${activeGlyph.label} avatar`}
            imgProps={{
              style:
                activeGlyph.kind === 'portrait'
                  ? { objectFit: 'cover', objectPosition: 'center top', padding: 0 }
                  : { objectFit: 'contain', padding: '6px' },
            }}
            sx={{ width: 56, height: 56, fontSize: 18, mb: 1.25 }}
          >
            {initials(user?.fullName)}
          </Avatar>
          <Typography variant="h4" component="h3">
            {user?.fullName}
          </Typography>
          <Typography variant="caption" component="p" sx={{ mb: 1.25, wordBreak: 'break-word' }}>
            {user?.email}
          </Typography>
          <span className="portal-side-role">
            {isStaff ? 'Staff Administrator' : 'Attendee Portal'}
          </span>
          <nav aria-label="Participant portal">
            {PORTAL_NAV.map(([label, to, end]) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? 'active' : '')}>
                {label}
                <ArrowRight size={15} strokeWidth={1.5} />
              </NavLink>
            ))}
            {isStaff ? (
              <Link to="/manage" className="portal-side-staff-link">
                Staff console
                <ArrowUpRight size={15} strokeWidth={1.5} />
              </Link>
            ) : null}
          </nav>
          <Button variant="ghost" size="small" icon={LogOut} onClick={signOut} className="portal-side-signout" sx={{ mt: 1.5 }}>
            Sign out
          </Button>
        </aside>
        <div className="portal-main">
          <Outlet key={pageKey} />
        </div>
      </section>
    </>
  );
}

export function PortalRegistrations() {
  const { editionId, edition } = useSite();
  const { user } = useAuth();
  const regs = useAsync(() => portalApi.registrations(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const tickets = useAsync(() => portalApi.tickets(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const pass = useAsync(() => portalApi.pass(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const teams = useAsync(() => portalApi.teams(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const eventsCatalog = useAsync(() => publicApi.events(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const myTeams = teams.data?.data || [];
  const openTeams = myTeams.filter((team) => team.status === 'active');
  const isSuspended = user?.status === 'suspended' || pass.data?.data?.status === 'suspended';
  const [confirm, setConfirm] = useState(null);
  const [message, setMessage] = useState(null);
  const [showReceipt, setShowReceipt] = useState(false);
  const regQuery = useAsync(
    () => registrationApi.get(editionId),
    [editionId],
    { enabled: Boolean(editionId && showReceipt) },
  );
  const rows = regs.data?.data || [];
  const hasVisitedTeamsPortal = (() => {
    try {
      return localStorage.getItem('px_visited_teams_portal') === '1';
    } catch {
      return false;
    }
  })();

  const eventById = useMemo(() => {
    const map = new Map();
    for (const ev of eventsCatalog.data?.data || []) {
      if (ev?.id) map.set(String(ev.id), ev);
    }
    return map;
  }, [eventsCatalog.data]);

  const dateGroups = useMemo(() => {
    const groups = new Map();
    const sorted = [...rows].sort((a, b) => {
      const ta = a.eventStartsAt ? new Date(a.eventStartsAt).getTime() : Number.MAX_SAFE_INTEGER;
      const tb = b.eventStartsAt ? new Date(b.eventStartsAt).getTime() : Number.MAX_SAFE_INTEGER;
      return ta - tb;
    });
    for (const row of sorted) {
      const ev = eventById.get(String(row.eventId || ''));
      const rawDate = row.eventStartsAt || ev?.startsAt || null;
      const d = rawDate ? new Date(rawDate) : null;
      const valid = d && !Number.isNaN(d.getTime());
      const key = valid ? d.toISOString().slice(0, 10) : 'tba';
      const label = valid
        ? d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
        : 'Schedule TBA';
      const subLabel = valid
        ? d.toLocaleDateString('en-IN', { weekday: 'long' })
        : 'Date to be announced';
      if (!groups.has(key)) {
        groups.set(key, { key, label, subLabel, items: [] });
      }
      groups.get(key).items.push({ row, ev, rawDate });
    }
    return Array.from(groups.values());
  }, [rows, eventById]);
  const cancelCutoff = confirm?.eventStartsAt
    ? new Date(confirm.eventStartsAt).getTime() - 24 * 60 * 60 * 1000
    : null;
  const cancelLocked = cancelCutoff !== null && Date.now() >= cancelCutoff;

  const cancel = async (id) => {
    setMessage(null);
    try {
      await portalApi.cancelRegistration(editionId, id);
      await regs.reload();
      setMessage({
        tone: 'success',
        text: 'Event cancelled. Any refund waits for admin approval — you are refunded after the admin approves it.',
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setConfirm(null);
    }
  };

  return (
    <>
          <SectionHead
            kicker="Selection Record"
            title="My events & bills"
            action={
              <Button variant="ghost" icon={Printer} onClick={() => setShowReceipt(true)}>
                View complete receipt
              </Button>
            }
          />
          <Feedback message={message} />
          {myTeams.length && !hasVisitedTeamsPortal ? (
            <InlineMessage tone="info">
              {openTeams.length
                ? `You are on ${openTeams.length} open team roster${openTeams.length === 1 ? '' : 's'}. Share the invite code with your teammates and lock the roster before the event starts.`
                : 'Your team rosters are set. Every member has their own event registration.'}{' '}
              <Link to="/portal/teams" style={{ color: '#38bdf8', fontWeight: 600 }}>
                Manage Teams →
              </Link>
            </InlineMessage>
          ) : null}
          {regs.loading ? <Loading label="Loading registrations" rows={2} /> : null}
          {regs.error ? <ErrorBox error={regs.error} onRetry={regs.reload} /> : null}
          {!regs.loading && !rows.length ? (
            <Empty title="No registrations yet" desc="Included selections and add-on events appear here.">
              {!isSuspended ? (
                <Link to="/portal/events" className="login-machined-btn is-gold">
                  <span>Browse &amp; Add Events</span>
                  <ArrowRight size={14} strokeWidth={2} />
                </Link>
              ) : null}
            </Empty>
          ) : null}
          {rows.length ? (
            <div className="reg-timeline">
              {dateGroups.map((group) => (
                <section className="reg-tl-group" key={group.key}>
                  <div className="reg-tl-date-row">
                    <span className="reg-tl-diamond" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="18" height="18">
                        <polygon
                          points="12,1.5 22.5,12 12,22.5 1.5,12"
                          fill="#12100b"
                          stroke="#d4af37"
                          strokeWidth="1.2"
                        />
                        <polygon points="12,3.5 18.5,12 12,12" fill="#fde68a" />
                        <polygon points="12,3.5 5.5,12 12,12" fill="#f5d061" />
                        <polygon points="5.5,12 12,20.5 12,12" fill="#b45309" />
                        <polygon points="18.5,12 12,20.5 12,12" fill="#d97706" />
                        <line x1="12" y1="3.5" x2="12" y2="20.5" stroke="#fef3c7" strokeOpacity="0.45" strokeWidth="0.6" />
                        <line x1="5.5" y1="12" x2="18.5" y2="12" stroke="#fef3c7" strokeOpacity="0.45" strokeWidth="0.6" />
                      </svg>
                    </span>
                    <div className="reg-tl-date-head">
                      <strong>{group.label}</strong>
                      <span>{group.subLabel}</span>
                    </div>
                  </div>

                  <div className="reg-tl-cards">
                    {group.items.map(({ row, ev, rawDate }) => {
                      const title = row.eventTitle || ev?.title || 'Event';
                      const isCancelled = row.status === 'cancelled';
                      const isEventCancelled = Boolean(
                        row.eventStatus && ['cancelled', 'closed', 'draft'].includes(row.eventStatus)
                      );
                      const statusInfo = isEventCancelled
                        ? { label: 'Event Cancelled', tone: 'bad' }
                        : isCancelled && row.cancelledBy === 'admin'
                          ? { label: 'Removed by Admin', tone: 'bad' }
                          : isCancelled
                            ? { label: 'Cancelled', tone: 'muted' }
                            : row.status === 'confirmed'
                              ? { label: 'Confirmed', tone: 'good' }
                              : { label: row.status || 'Pending', tone: 'warn' };

                      const billingLabel =
                        row.billingRole === 'payer'
                          ? 'Team entry · paid by you'
                          : row.kind === 'included'
                            ? 'Included with Pass (Free)'
                            : row.kind;

                      const timeStr = rawDate
                        ? new Date(rawDate).toLocaleTimeString('en-IN', {
                            hour: 'numeric',
                            minute: '2-digit',
                          })
                        : 'Time TBA';

                      const rawBanner = ev?.posterUrl || ev?.bannerUrl || ev?.imageUrl;
                      const bannerSrc = resolveImageUrl(rawBanner, 800);
                      const venue = ev?.venue || ev?.room || null;
                      const formatLabel = ev?.teamMode === 'team' ? 'Team Event' : 'Solo Entry';

                      return (
                        <article
                          className={`reg-tl-card${isCancelled || isEventCancelled ? ' is-cancelled' : ''}`}
                          key={row.id}
                        >
                          <div className="reg-tl-main">
                            <div className="reg-tl-top">
                              <div className="reg-tl-top-left">
                                <span className="reg-tl-time">{timeStr}</span>
                                <span className="reg-tl-cat">{row.category || 'Event'}</span>
                              </div>
                              <span className="reg-tl-num">{row.registrationNumber}</span>
                            </div>

                            <h3 className="reg-tl-title">
                              {ev?.slug ? (
                                <Link to={`/events/${ev.slug}`}>{title}</Link>
                              ) : (
                                title
                              )}
                            </h3>

                            <div className="reg-tl-specs">
                              <span className="reg-tl-spec">
                                <b>Pass:</b> {billingLabel}
                              </span>
                              <span className="reg-tl-spec">
                                <b>Mode:</b> {formatLabel}
                              </span>
                              {venue ? (
                                <span className="reg-tl-spec">
                                  <b>Venue:</b> {venue}
                                </span>
                              ) : null}
                              {row.teamName ? (
                                <span className="reg-tl-spec">
                                  <b>Squad:</b> {row.teamName}
                                </span>
                              ) : null}
                            </div>

                            {isEventCancelled ? (
                              <div className="reg-tl-alert is-bad">
                                Event cancelled by the organisers
                              </div>
                            ) : isCancelled && row.cancelledBy === 'admin' ? (
                              <div className="reg-tl-alert is-bad">
                                Removed by administration
                                {row.cancellationReason ? `: ${row.cancellationReason}` : ''}
                              </div>
                            ) : isCancelled && row.cancelledBy === 'user' ? (
                              <div className="reg-tl-alert is-muted">
                                Cancelled by you · Seat released
                              </div>
                            ) : null}

                            <div className="reg-tl-foot">
                              <div className="reg-tl-badges">
                                <Badge tone={statusInfo.tone}>{statusInfo.label}</Badge>
                                {row.refundStatus === 'processed' || row.paymentStatus === 'refunded' ? (
                                  <Badge tone="good">
                                    Refunded {money(row.refundedPaise || row.feePaise)}
                                  </Badge>
                                ) : row.refundStatus === 'processing' ? (
                                  <Badge tone="warn">
                                    Refund Processing ({money(row.refundedPaise || row.feePaise)})
                                  </Badge>
                                ) : row.refundStatus === 'pending' || row.paymentStatus === 'refund_pending' ? (
                                  <Badge tone="warn">
                                    Refund Pending ({money(row.refundedPaise || row.feePaise)})
                                  </Badge>
                                ) : row.refundStatus === 'failed' ? (
                                  <Badge tone="bad">Refund Failed</Badge>
                                ) : (
                                  <span className="reg-tl-fee">
                                    {row.feePaise > 0 ? money(row.feePaise) : '₹0 · Pass'}
                                  </span>
                                )}
                              </div>

                              <div className="reg-tl-actions">
                                {row.status === 'confirmed' ? (
                                  <Link className="reg-tl-btn is-primary" to="/portal/registration">
                                    Ticket <ArrowRight size={12} strokeWidth={2.2} />
                                  </Link>
                                ) : null}
                                {row.teamId ? (
                                  <Link className="reg-tl-btn" to="/portal/teams">
                                    Team <ArrowUpRight size={12} strokeWidth={2} />
                                  </Link>
                                ) : row.kind !== 'included' && row.feePaise > 0 ? (
                                  <Link className="reg-tl-btn" to="/portal/registration">
                                    Receipt <ArrowUpRight size={12} strokeWidth={2} />
                                  </Link>
                                ) : null}
                                {row.status !== 'cancelled' ? (
                                  <button
                                    type="button"
                                    className="reg-tl-btn is-danger"
                                    onClick={() => setConfirm(row)}
                                  >
                                    Cancel
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          </div>

                          <div className="reg-tl-banner">
                            {bannerSrc ? (
                              <img
                                src={bannerSrc}
                                alt={title}
                                referrerPolicy="no-referrer"
                                loading="lazy"
                                onError={(e) => {
                                  e.currentTarget.onerror = null;
                                  e.currentTarget.src = regBackdrop(row.category);
                                }}
                              />
                            ) : (
                              <EventGeneratedPoster event={ev || row} />
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          ) : null}
          {rows.length && !isSuspended ? (
            <div className="wl-cross-nav">
              <p className="wl-cross-nav-note">
                Want to add more competitions or use remaining pass allowance?
              </p>
              <Link to="/portal/events" className="login-machined-btn is-gold">
                <span>Browse &amp; Add Events</span>
                <ArrowRight size={14} strokeWidth={2} />
              </Link>
            </div>
          ) : null}
          <Sheet open={Boolean(confirm)} title="Cancel registration" onClose={() => setConfirm(null)}>
            <p className="muted">
              Cancel the registration for <b>{confirm?.eventTitle}</b>? Your seat is released
              immediately and the event ticket is revoked.
            </p>
            <div
              style={{
                margin: '12px 0 16px',
                padding: '12px 14px',
                borderRadius: '10px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                fontSize: '13px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span className="muted">{confirm?.kind === 'included' ? 'Selection Type' : 'Amount you paid'}</span>
                <b>{confirm?.kind === 'included' ? 'Included with Pass (₹0)' : money(confirm?.feePaise || 0)}</b>
              </div>
              <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
                {confirm?.kind === 'included'
                  ? 'This event was selected as part of your pass quota. Cancelling releases your seat immediately and restores 1 event credit so you can choose another event before the 24-hour cutoff.'
                  : 'No refund is automatic. Your cancellation waits for the registration desk: once the admin approves the refund, the amount is returned to your original payment method.'}
              </p>
              {cancelLocked ? (
                <InlineMessage tone="error">
                  Cancellation is closed: this event starts within 24 hours. Contact the helpdesk if
                  you cannot attend.
                </InlineMessage>
              ) : null}
            </div>
            <div className="sheet-actions">
              <Button variant="ghost" onClick={() => setConfirm(null)}>
                Keep it
              </Button>
              <Button onClick={() => cancel(confirm.id)} disabled={cancelLocked}>
                Cancel registration
              </Button>
            </div>
          </Sheet>
      <CompleteReceiptSheet
        open={showReceipt}
        onClose={() => setShowReceipt(false)}
        edition={edition}
        registration={regQuery.data?.data?.registration}
        eventRegistrations={rows}
        user={user}
      />
    </>
  );
}

export function PortalTeams() {
  const { editionId, slug, policy } = useSite();
  const { user } = useAuth();
  useEffect(() => {
    try {
      localStorage.setItem('px_visited_teams_portal', '1');
    } catch {}
  }, []);
  const [searchParams] = useSearchParams();
  const requestedEventId = searchParams.get('event') || '';
  const teams = useAsync(() => portalApi.teams(editionId), [editionId], { enabled: Boolean(editionId) });
  const pass = useAsync(() => portalApi.pass(editionId), [editionId], { enabled: Boolean(editionId) });
  const regs = useAsync(() => portalApi.registrations(editionId), [editionId], { enabled: Boolean(editionId) });
  const catalogue = useAsync(() => publicApi.events(slug, { format: 'team', pageSize: 100 }), [slug], {
    enabled: Boolean(slug),
    ttlMs: 300000,
  });
  const [form, setForm] = useState({ eventId: requestedEventId, name: '' });
  const [joinCode, setJoinCode] = useState('');
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');
  // Leaving as leader hands the team to the next member; disbanding is a
  // separate, explicit choice, so the prompt offers both.
  const [confirmLeave, setConfirmLeave] = useState(null);

  const loadingTeamEvents = (regs.loading && !regs.data) || (catalogue.loading && !catalogue.data);
  const allTeamEvents = catalogue.data?.data || [];
  const registeredEventIds = new Set(
    (regs.data?.data || [])
      .filter((r) => ['confirmed', 'reserved'].includes(r.status))
      .map((r) => r.eventId),
  );
  const teamEvents = allTeamEvents.filter((event) => registeredEventIds.has(event.id));
  const rows = teams.data?.data || [];
  const joinedEventIds = new Set(rows.map((team) => team.eventId));
  const passActive = pass.data?.data?.status === 'active';
  const needsPass = Boolean(policy?.teamMembersRequirePass) && !passActive && !pass.loading;
  const selectedEvent = teamEvents.find((event) => event.id === form.eventId);

  useEffect(() => {
    if (requestedEventId && teamEvents.some((event) => event.id === requestedEventId)) {
      setForm((current) => ({ ...current, eventId: requestedEventId }));
      return;
    }
    if ((!form.eventId || !teamEvents.some((e) => e.id === form.eventId) || joinedEventIds.has(form.eventId)) && teamEvents.length) {
      const nextOpen = teamEvents.find((event) => !joinedEventIds.has(event.id)) || teamEvents[0];
      if (nextOpen && nextOpen.id !== form.eventId) {
        setForm((current) => ({ ...current, eventId: nextOpen.id }));
      }
    } else if (!teamEvents.length && form.eventId) {
      setForm((current) => ({ ...current, eventId: '' }));
    }
  }, [requestedEventId, teamEvents, joinedEventIds, form.eventId]);

  const run = async (key, action, success) => {
    setBusy(key);
    setMessage(null);
    try {
      await action();
      await teams.reload();
      setMessage({ tone: 'success', text: success });
      return true;
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
      return false;
    } finally {
      setBusy('');
    }
  };

  return (
    <>
      <SectionHead kicker="Team Events" title="Teams and invites" />
      <p className="muted">
        {policy?.teamMembersRequirePass
          ? 'Every member needs an active convention pass before joining.'
          : 'A pass is not required per member for this edition.'}
      </p>
      {needsPass ? (
        <InlineMessage tone="warn">
          You need an active convention pass before you can create or join a team.{' '}
          <Link to="/portal/registration" style={{ color: '#38bdf8', fontWeight: 600 }}>
            Get your pass →
          </Link>
        </InlineMessage>
      ) : null}
      <div className="team-protocol-strip">
        <div className="team-protocol-col">
          <span className="team-protocol-tag">01 / CREATE</span>
          <p>Form a separate team for each team event you want to compete in.</p>
        </div>
        <div className="team-protocol-col">
          <span className="team-protocol-tag">02 / INVITE</span>
          <p>Share the invite code with teammates so they can join from the Portal or invite link.</p>
        </div>
        <div className="team-protocol-col">
          <span className="team-protocol-tag">03 / LOCK ROSTER</span>
          <p>Lock the roster before the event starts to finalize your squad for check-in.</p>
        </div>
      </div>
      <Feedback message={message} />

      <div className="portal-columns team-columns">
        <div className="team-action-card">
          <div className="team-action-head">
            <span>01 / SQUAD FORMATION</span>
            <Users size={15} strokeWidth={1.8} />
          </div>
          <h3>Create a team</h3>
          {!loadingTeamEvents && !teamEvents.length ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: 1 }}>
              <p className="team-action-note">
                Register for a team event in Browse Events first before creating a team.
              </p>
              <div style={{ marginTop: 'auto' }}>
                <Link to="/portal/events" className="login-machined-btn is-gold">
                  <span>Browse Events</span>
                  <ArrowRight size={14} strokeWidth={2} />
                </Link>
              </div>
            </div>
          ) : (
            <>
              <FieldGrid>
                <Field label="Registered team event">
                  <select
                    value={loadingTeamEvents && !teamEvents.length ? '' : form.eventId}
                    disabled={loadingTeamEvents && !teamEvents.length}
                    onChange={(event) => setForm({ ...form, eventId: event.target.value })}
                  >
                    {loadingTeamEvents && !teamEvents.length ? (
                      <option value="">Loading registered team events…</option>
                    ) : (
                      teamEvents.map((event) => (
                        <option key={event.id} value={event.id} disabled={joinedEventIds.has(event.id)}>
                          {event.title} ({event.teamMinSize}-{event.teamMaxSize})
                          {joinedEventIds.has(event.id) ? ' — Already in a team' : ''}
                        </option>
                      ))
                    )}
                  </select>
                  {loadingTeamEvents && !teamEvents.length ? (
                    <small className="muted" style={{ display: 'block', marginTop: '6px' }}>
                      Loading your registered team events…
                    </small>
                  ) : selectedEvent ? (
                    <small className="muted" style={{ display: 'block', marginTop: '6px' }}>
                      {selectedEvent.addonPricePaise > 0
                        ? `Fee: ${money(selectedEvent.addonPricePaise)} per participant (each member pays their own seat).`
                        : 'Free team event (pass required).'}
                    </small>
                  ) : null}
                </Field>
                <Field label="Team name">
                  <input
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                    placeholder="Vector Five"
                    maxLength={100}
                  />
                </Field>
              </FieldGrid>
              <button
                type="button"
                className="login-machined-btn is-gold"
                onClick={() =>
                  run(
                    'create',
                    async () => {
                      const body = await portalApi.createTeam(editionId, {
                        eventId: form.eventId,
                        name: form.name,
                      });
                      // A priced team seat is reserved, not confirmed: the team
                      // exists but nobody is admitted until the seat is paid.
                      const payment = body.data?.payment;
                      if (payment) {
                        const outcome = await payOrder(
                          editionId,
                          payment,
                          user,
                          `Team seat - ${body.data?.name || form.name}`,
                        );
                        if (outcome.status !== 'paid') {
                          clearAsyncCache();
                          throw new Error(
                            outcome.status === 'cancelled'
                              ? 'Team created, but the seat payment was cancelled. Pay it from the team card to confirm your place.'
                              : outcome.message ||
                                  'Team created, but the seat payment failed. Try paying again from the team card.',
                          );
                        }
                      }
                    },
                    'Team created. Share the invite code.',
                  ).then((ok) => {
                    if (ok) setForm((f) => ({ ...f, name: '' }));
                  })
                }
                disabled={
                  (loadingTeamEvents && !teamEvents.length) ||
                  busy === 'create' ||
                  !form.eventId ||
                  form.name.trim().length < 2
                }
              >
                <Users size={14} strokeWidth={2} />
                <span>{busy === 'create' ? 'Creating…' : 'Create team'}</span>
              </button>
            </>
          )}
        </div>
        <div className="team-action-card">
          <div className="team-action-head">
            <span>02 / ROSTER ENTRY</span>
            <ShieldCheck size={15} strokeWidth={1.8} />
          </div>
          <h3>Join a team</h3>
          <Field label="Invite code" hint="The leader shares an eight-character code.">
            <input
              value={joinCode}
              onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
              placeholder="A1B2C3D4"
              maxLength={16}
            />
          </Field>
          <div style={{ marginTop: 'auto' }}>
            <button
              type="button"
              className="login-machined-btn"
              onClick={async () => {
                const ok = await run(
                  'join',
                  async () => {
                    const body = await portalApi.joinTeam(editionId, joinCode);
                    const payment = body.data?.payment;
                    if (payment) {
                      const outcome = await payOrder(
                        editionId,
                        payment,
                        user,
                        `Team seat - ${body.data?.name || 'team'}`,
                      );
                      if (outcome.status !== 'paid') {
                        clearAsyncCache();
                        throw new Error(
                          outcome.status === 'cancelled'
                            ? 'You joined the team, but the seat payment was cancelled. Pay it from the team card to confirm your place.'
                            : outcome.message ||
                                'You joined the team, but the seat payment failed. Try paying again from the team card.',
                        );
                      }
                    }
                  },
                  'You joined the team.',
                );
                if (ok) setJoinCode('');
              }}
              disabled={busy === 'join' || joinCode.trim().length < 4}
            >
              <span>{busy === 'join' ? 'Joining…' : 'Join with code'}</span>
              <ArrowRight size={14} strokeWidth={2} />
            </button>
          </div>
        </div>
      </div>

      {teams.loading ? <Loading label="Loading teams" rows={2} /> : null}
      {teams.error ? <ErrorBox error={teams.error} onRetry={teams.reload} /> : null}
      {!teams.loading && !rows.length ? (
        <Empty title="No teams yet" desc="Create a team for a team event, or join one with a code." />
      ) : null}

      <div className="team-list">
        {rows.map((team) => (
          <Panel key={team.id} className="team-card">
            <div className="team-head">
              <div>
                <Eyebrow>{team.eventTitle}</Eyebrow>
                <h3>{team.name}</h3>
                <p className="muted">
                  {team.members.length} / {team.maxSize} members ·{' '}
                  {team.status === 'locked' ? (
                    <span style={{ color: '#fbbf24', fontWeight: 600 }}>🔒 Roster Locked</span>
                  ) : (
                    <span style={{ color: '#38bdf8' }}>Forming</span>
                  )}
                </p>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {team.status === 'locked' ? (
                  <Badge tone="positive">Locked</Badge>
                ) : (
                  <Badge tone="accent">Open</Badge>
                )}
                {team.isLeader ? <Badge tone="accent">You lead</Badge> : <Badge>Member</Badge>}
              </div>
            </div>
            <ul className="member-list">
              {team.members.map((member) => (
                <li key={member.userId}>
                  <span className="avatar small">{initials(member.fullName)}</span>
                  <span>
                    <b>{member.fullName}</b>
                    <small>{member.collegeName || 'College not set'}</small>
                  </span>
                  {member.isLeader ? <Badge tone="muted">Leader</Badge> : null}
                  {member.seatStatus === 'confirmed' ? (
                    <Badge tone="positive">Entry confirmed</Badge>
                  ) : member.seatStatus === 'reserved' ? (
                    <Badge tone="warn">Fee due</Badge>
                  ) : (
                    <Badge tone="bad">No seat</Badge>
                  )}
                </li>
              ))}
            </ul>
            {team.isLeader ? (
              <div style={{ margin: '14px 0 10px 0', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                <Button
                  variant={team.status === 'locked' ? 'ghost' : 'primary'}
                  onClick={() =>
                    run(
                      `lock-${team.id}`,
                      () => portalApi.toggleTeamLock(editionId, team.id),
                      team.status === 'locked'
                        ? 'Team roster unlocked.'
                        : 'Team roster finalized and locked for competition check-in.',
                    )
                  }
                  disabled={busy === `lock-${team.id}`}
                >
                  {team.status === 'locked' ? '🔓 Unlock Team Roster' : '🔒 Lock & Finalize Roster'}
                </Button>
                <small className="muted" style={{ fontSize: '11px' }}>
                  {team.status === 'locked'
                    ? 'Roster is locked for event check-in. Unlock if you need to add or remove members.'
                    : 'Lock before event start to freeze team members.'}
                </small>
              </div>
            ) : null}
            {team.payment ? (
              <InlineMessage tone="warn">
                This seat is not confirmed yet - the door will not admit it until it is paid.{' '}
                <Button
                  variant="primary"
                  onClick={() =>
                    run(
                      `pay-${team.id}`,
                      async () => {
                        const outcome = await payOrder(
                          editionId,
                          team.payment,
                          user,
                          `Team seat - ${team.name}`,
                        );
                        if (outcome.status !== 'paid') {
                          clearAsyncCache();
                          throw new Error(
                            outcome.status === 'cancelled'
                              ? 'Payment cancelled. Your seat stays reserved until it is paid.'
                              : outcome.message ||
                                  'Payment failed. Your seat stays reserved until it is paid.',
                          );
                        }
                      },
                      'Seat paid. You are on the roster.',
                    )
                  }
                  disabled={busy === `pay-${team.id}`}
                >
                  {busy === `pay-${team.id}` ? 'Paying' : `Pay ${money(team.payment.amountPaise)}`}
                </Button>
              </InlineMessage>
            ) : null}
            {team.inviteCode && team.status !== 'locked' ? (
              <div className="invite-row">
                <div>
                  <span>INVITE CODE</span>
                  <code>{team.inviteCode}</code>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button
                    variant="ghost"
                    icon={Copy}
                    onClick={() => {
                      navigator.clipboard?.writeText(team.inviteCode);
                      setMessage({ tone: 'success', text: `Copied invite code ${team.inviteCode}.` });
                    }}
                  >
                    Copy
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() =>
                      run(
                        `rotate-${team.id}`,
                        () => portalApi.rotateInvite(editionId, team.id),
                        'Invite code rotated.',
                      )
                    }
                    disabled={busy === `rotate-${team.id}`}
                  >
                    Rotate
                  </Button>
                </div>
              </div>
            ) : null}
            {team.status !== 'locked' ? (
              team.isLeader ? (
                <Button variant="ghost" onClick={() => setConfirmLeave(team)} disabled={busy === `leave-${team.id}`}>
                  {team.members.length > 1 ? 'Leave / Disband team' : 'Disband team'}
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  onClick={() =>
                    run(`leave-${team.id}`, () => portalApi.leaveTeam(editionId, team.id), 'You left the team.')
                  }
                  disabled={busy === `leave-${team.id}`}
                >
                  Leave team
                </Button>
              )
            ) : (
              <p className="muted" style={{ fontSize: '12px', fontStyle: 'italic', margin: '8px 0 0 0' }}>
                Roster is locked. Members cannot leave or change teams.
              </p>
            )}
          </Panel>
        ))}
      </div>

      <Sheet
        open={Boolean(confirmLeave)}
        title={confirmLeave?.members?.length > 1 ? 'Leave or disband this team?' : 'Disband this team?'}
        onClose={() => setConfirmLeave(null)}
      >
        <p className="muted">
          {confirmLeave?.members?.length > 1 ? (
            <>
              You are the leader of <b>{confirmLeave?.name}</b>. Leaving will promote{' '}
              <b>{confirmLeave.members.find((member) => !member.isLeader)?.fullName || 'the next member'}</b>{' '}
              to team leader — or you can disband the team. Everyone keeps their event registration.
            </>
          ) : (
            <>
              You are the only member of <b>{confirmLeave?.name}</b>. Disbanding will remove the
              team, and your event registration will stay active.
            </>
          )}
        </p>
        <div className="sheet-actions" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <Button variant="ghost" onClick={() => setConfirmLeave(null)}>
            Keep the team
          </Button>
          {confirmLeave?.members?.length > 1 ? (
            <Button
              variant="primary"
              onClick={async () => {
                const team = confirmLeave;
                setConfirmLeave(null);
                await run(
                  `leave-${team.id}`,
                  () => portalApi.leaveTeam(editionId, team.id, { disband: false }),
                  'You left the team and leadership passed to the next member.',
                );
              }}
            >
              Leave &amp; hand over
            </Button>
          ) : null}
          <Button
            variant="danger"
            onClick={async () => {
              const team = confirmLeave;
              setConfirmLeave(null);
              await run(
                `leave-${team.id}`,
                () => portalApi.leaveTeam(editionId, team.id, { disband: true }),
                'Team disbanded. Your event registration stays active.',
              );
            }}
          >
            Disband team
          </Button>
        </div>
      </Sheet>
    </>
  );
}

export function InstructionsPage() {
  const { edition } = useSite();
  const helpdeskPhone = (edition?.helpdeskPhone || '').trim();
  const contactEmail = edition?.contactEmail || 'iste@nssce.ac.in';

  const sections = [
    {
      title: '1. Pass Purchase & Document Verification',
      points: [
        'Every participant is required to purchase a Convention Pass by completing their profile details, uploading the mandatory identification documents, and completing payment.',
        'All submitted passes are subject to review and verification by the registration desk.',
        'If the desk requests corrected documents, a 24-hour resubmission window applies. Failure to submit the requested documents within 24 hours may result in pass revocation and release of associated event seats and team placements in accordance with convention policy.',
        'If a pass is rejected or revoked, it will no longer grant gate entry or appear as active on your dashboard; however, your payment receipt remains available for your records.',
      ],
    },
    {
      title: '2. Event Selection, Pass Allowance & Seat Holds',
      points: [
        'Your Convention Pass may include an event allowance configured by count and/or value cap. Only events that fit strictly within the remaining allowance limits are covered at ₹0; any additional events are billed at their full applicable add-on fee.',
        'During checkout, selected seats are temporarily reserved while payment is in progress. If payment is cancelled, closed, or fails, reserved seats are released back to general availability.',
        'Applicable platform or Razorpay payment gateway fees may apply to online transactions depending on the active edition policy.',
      ],
    },
    {
      title: '3. Single Pass QR for All Access',
      points: [
        'Your Convention Pass QR code serves as your unified credential across the convention — it is used for main gate admission, individual event check-ins, and lunch check-ins.',
        'Please keep your Pass QR accessible and present physical college identification if requested by verification staff at the gate.',
      ],
    },
    {
      title: '4. Teams & Leadership Handover',
      points: [
        'For team events, you may create a team and share its invite code, or join an existing team using an invite code.',
        'If a team leader cancels their event registration or is removed, team leadership is automatically transferred to the earliest remaining member on the roster. A team is disbanded only if no members remain.',
      ],
    },
    {
      title: '5. Cancellations, Refunds & Receipts',
      points: [
        'Event cancellations are subject to the convention cancellation window and refund policy. Eligible refunds for cancelled paid events are processed once reviewed and confirmed by the finance desk, and their live status is tracked under your events list.',
        'You can view and print your complete consolidated receipt at any time from "My Pass & Ticket" or via "View complete receipt" in "My Events & Bills".',
      ],
    },
    {
      title: '6. Support & Assistance',
      points: [
        'All registrations, allowances, and refunds are governed by the active edition policy and verification guidelines.',
        'For any questions, discrepancies, or assistance with your pass, events, or refunds, please contact our support desk.',
      ],
    },
  ];

  return (
    <>
      <SectionHead
        kicker="Participant Guide"
        title="Instructions & Policies"
        action={
          <Link to="/contact" style={{ textDecoration: 'none' }}>
            <Button variant="ghost" icon={ArrowRight}>
              Contact Support
            </Button>
          </Link>
        }
      />
      <div style={{ display: 'grid', gap: 16 }}>
        {sections.map((sec) => (
          <Panel key={sec.title}>
            <h3 style={{ margin: '0 0 10px 0', fontSize: 16 }}>{sec.title}</h3>
            <ul
              style={{
                margin: 0,
                paddingLeft: 18,
                display: 'grid',
                gap: 8,
                color: 'var(--dim)',
                lineHeight: 1.6,
                fontSize: 14,
              }}
            >
              {sec.points.map((pt, idx) => (
                <li key={idx}>{pt}</li>
              ))}
            </ul>
          </Panel>
        ))}
        <Panel>
          <h3 style={{ margin: '0 0 8px 0', fontSize: 16 }}>Need Help?</h3>
          <p className="muted" style={{ margin: '0 0 12px 0', fontSize: 14, lineHeight: 1.6 }}>
            If you require assistance with verification, event bookings, or refunds, please reach
            out to the organising desk:
          </p>
          <div style={{ display: 'grid', gap: 10, fontSize: 14 }}>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <span>
                Email:{' '}
                <a href={`mailto:${contactEmail}`} style={{ color: '#38bdf8' }}>
                  {contactEmail}
                </a>
              </span>
              {helpdeskPhone && !/00000/.test(helpdeskPhone) ? (
                <span>
                  Phone / WhatsApp:{' '}
                  <a href={`tel:${helpdeskPhone.replace(/[^\d+]/g, '')}`} style={{ color: '#38bdf8' }}>
                    {helpdeskPhone}
                  </a>
                </span>
              ) : null}
            </div>
            <div style={{ marginTop: 6 }}>
              <Link to="/contact" className="login-machined-btn is-gold">
                <span>Open Contact Page</span>
                <ArrowRight size={14} strokeWidth={2} />
              </Link>
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}

export function PortalProfile() {
  const profile = useAsync(() => authApi.profile(), []);
  const sessions = useAsync(() => authApi.sessions(), []);
  const { user, isStaff, reload, logout } = useAuth();
  const [activeGlyph, selectGlyph] = usePortalAvatar(user?.id, isStaff ? 'root' : 'parallax');
  const navigate = useNavigate();
  const [form, setForm] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');
  const lastRefreshRef = useRef(0);

  useEffect(() => {
    if (profile.data?.data) {
      const data = profile.data.data;
      setForm({
        fullName: data.fullName || '',
        phone: data.phone || '',
        collegeName: data.collegeName || data.universityName || '',
        course: data.course || '',
        branch: data.branch || '',
        yearOfStudy: normalizeYear(data.yearOfStudy),
        dateOfBirth: data.dateOfBirth || '',
        city: data.city || '',
        state: data.state || '',
        gender: data.gender || '',
        foodPreference: data.foodPreference || '',
        needsAccommodation: Boolean(data.needsAccommodation),
      });
    }
  }, [profile.data]);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const refreshDetails = async () => {
    if (Date.now() - lastRefreshRef.current < 10_000) {
      setMessage({ tone: 'info', text: 'Details were just refreshed. Try again in a moment.' });
      return;
    }
    lastRefreshRef.current = Date.now();
    setBusy('refresh');
    setMessage(null);
    try {
      // Direct read first so a failed refetch surfaces instead of silently
      // keeping the stale cached copy.
      await authApi.profile();
      await Promise.all([profile.reload(), reload()]);
      setMessage({ tone: 'success', text: 'Details refreshed from the server.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const save = async (event) => {
    event.preventDefault();
    setBusy('save');
    setMessage(null);
    try {
      const payload = {
        fullName: form.fullName,
        phone: form.phone || null,
        // One institution field: attendees of a standalone university just type
        // the university here, so a separate "University" box is not needed.
        collegeName: form.collegeName,
        course: form.course,
        branch: form.branch,
        yearOfStudy: parseYearNumber(form.yearOfStudy),
        dateOfBirth: form.dateOfBirth || null,
        city: form.city?.trim() || null,
        state: form.state?.trim() || null,
        gender: form.gender || null,
        foodPreference: form.foodPreference || null,
        needsAccommodation: Boolean(form.needsAccommodation),
      };
      await authApi.updateProfile(payload);
      await Promise.all([profile.reload(), reload()]);
      setMessage({ tone: 'success', text: 'Profile saved.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  if (profile.loading || !form) return <Loading label="Loading profile" rows={3} />;
  if (profile.error) return <ErrorBox error={profile.error} onRetry={profile.reload} />;

  const isLocked = Boolean(profile.data?.data?.profileLocked);

  return (
    <>
      <SectionHead
        kicker="Account"
        title="Profile and sessions"
        action={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Button
              variant="ghost"
              onClick={refreshDetails}
              disabled={busy === 'refresh' || busy === 'save'}
              icon={RefreshCw}
              title="Re-fetch your saved details from the server"
            >
              {busy === 'refresh' ? 'Refreshing…' : 'Refresh details'}
            </Button>
            <StatusBadge status={user?.profileComplete ? 'complete' : 'incomplete'} />
          </div>
        }
      />
      <Feedback message={message} />
      {isLocked ? (
        <InlineMessage tone="info">
          Your profile is locked because you have an active registration or pass. Ask the organiser
          desk if any detail needs to be corrected.
        </InlineMessage>
      ) : null}
      <div className="team-action-card" style={{ marginBottom: '18px' }}>
        <div className="team-action-head">
          <span>01 / ATTENDEE RECORD</span>
          <ShieldCheck size={15} strokeWidth={1.8} />
        </div>
        <form className="profile-form" onSubmit={save}>
          <FieldGrid>
            <Field label="Full name">
              <input
                value={form.fullName}
                onChange={(event) => update('fullName', event.target.value)}
                disabled={isLocked}
                required
              />
            </Field>
            <Field label="Phone" hint="International format, e.g. +919876543210">
              <input
                value={form.phone}
                onChange={(event) => update('phone', event.target.value)}
                disabled={isLocked}
              />
            </Field>
            <Field
              label="College / University"
              hint="Your college, or the university if you study directly under one"
            >
              <ComboInput
                value={form.collegeName}
                onChange={(val) => update('collegeName', val)}
                options={COLLEGE_SUGGESTIONS}
                placeholder="Search your college, or type it"
                disabled={isLocked}
                required
                maxLength={200}
              />
            </Field>
            <Field label="Course">
              <input
                value={form.course}
                onChange={(event) => update('course', event.target.value)}
                disabled={isLocked}
              />
            </Field>
            <Field label="Branch / Department">
              <ComboInput
                value={form.branch}
                onChange={(val) => update('branch', val)}
                options={BRANCH_SUGGESTIONS}
                placeholder="Search your branch, or type it"
                disabled={isLocked}
                maxLength={120}
              />
            </Field>
            <Field label="Year of study">
              <ComboInput
                value={form.yearOfStudy}
                onChange={(val) => update('yearOfStudy', val)}
                options={YEAR_SUGGESTIONS}
                placeholder="Select or type year"
                disabled={isLocked}
                maxLength={40}
              />
            </Field>
            <Field label="Date of birth">
              <input
                type="date"
                value={form.dateOfBirth}
                onChange={(event) => update('dateOfBirth', event.target.value)}
                max={new Date().toISOString().slice(0, 10)}
                min="1950-01-01"
                disabled={isLocked}
              />
            </Field>
            <Field label="City">
              <ComboInput
                value={form.city}
                onChange={(val) => update('city', val)}
                options={KERALA_CITIES}
                placeholder="Select or type city (e.g. Palakkad)"
                disabled={isLocked}
                maxLength={120}
              />
            </Field>
            <Field label="State">
              <ComboInput
                value={form.state}
                onChange={(val) => update('state', val)}
                options={INDIAN_STATES}
                placeholder="Select or type state (e.g. Kerala)"
                disabled={isLocked}
                maxLength={120}
              />
            </Field>
            <Field label="Gender">
              <SelectInput
                value={form.gender}
                onChange={(val) => update('gender', val)}
                options={GENDER_OPTIONS}
                placeholder="Select gender"
                disabled={isLocked}
              />
            </Field>
            <Field label="Meal preference">
              <SelectInput
                value={form.foodPreference}
                onChange={(val) => update('foodPreference', val)}
                options={FOOD_OPTIONS}
                placeholder="Select meal preference"
                disabled={isLocked}
              />
            </Field>
          </FieldGrid>
          <label
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              marginTop: '14px',
              marginBottom: '12px',
              padding: '12px 14px',
              borderRadius: '10px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              background: 'rgba(255, 255, 255, 0.03)',
              cursor: isLocked ? 'default' : 'pointer',
              fontSize: '13.5px',
              opacity: isLocked ? 0.7 : 1,
            }}
          >
            <input
              type="checkbox"
              checked={Boolean(form.needsAccommodation)}
              onChange={(event) => update('needsAccommodation', event.target.checked)}
              disabled={isLocked}
              style={{ marginTop: '2px' }}
            />
            <span>
              I need hostel accommodation during the convention
              <span className="muted" style={{ display: 'block', fontSize: '12px' }}>
                Tick this and the accommodation desk will contact you. It is not charged here.
              </span>
            </span>
          </label>
          <p className="muted">
            Email {profile.data?.data?.email} is the signed-in identity and cannot be edited here.
          </p>
          {!isLocked ? (
            <button
              type="submit"
              className="login-machined-btn is-gold"
              disabled={busy === 'save'}
            >
              <Check size={14} strokeWidth={2.2} />
              <span>{busy === 'save' ? 'Saving…' : 'Save profile'}</span>
            </button>
          ) : null}
        </form>
      </div>

      <div className="team-action-card" style={{ marginBottom: '18px' }}>
        <div className="team-action-head">
          <span>02 / PORTAL AVATAR</span>
          <span className="muted" style={{ fontSize: '11px', letterSpacing: '0.08em' }}>
            {isStaff ? 'STAFF CLEARANCE' : 'ATTENDEE'}
          </span>
        </div>
        <div className="glyph-picker-grid">
          {PORTAL_AVATARS.map((g) => {
            const selected = activeGlyph.id === g.id;
            return (
              <button
                key={g.id}
                type="button"
                className={`glyph-picker-tile ${selected ? 'is-selected' : ''} ${isStaff ? 'is-staff' : ''}`}
                onClick={() => selectGlyph(g.id)}
                aria-pressed={selected}
              >
                <img
                  src={g.src}
                  alt={g.label}
                  className={`glyph-picker-img ${g.kind === 'portrait' ? 'is-portrait' : ''}`}
                />
                <span className="glyph-picker-label">{g.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="team-action-card">
        <div className="team-action-head">
          <span>03 / ACTIVE SESSIONS</span>
          <LogOut size={15} strokeWidth={1.8} />
        </div>
        <div className="session-list">
          {(sessions.data?.data || []).map((session) => (
            <div className="session-row" key={session.id}>
              <div>
                <b>{session.current ? 'This device' : 'Signed-in device'}</b>
                <small>
                  {session.ipPrefix || 'unknown network'} · last seen {dateTime(session.lastSeenAt)}
                </small>
              </div>
              <span className="pill">{session.authLevel}</span>
            </div>
          ))}
        </div>
        <div>
          <button
            type="button"
            className="login-machined-btn"
            onClick={async () => {
              await logout();
              navigate('/');
            }}
          >
            <LogOut size={14} strokeWidth={2} />
            <span>Sign out of this device</span>
          </button>
        </div>
      </div>
    </>
  );
}
