import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { QRCodeCanvas } from 'qrcode.react';
import {
  ArrowRight,
  LayoutDashboard,
  ArrowUpRight,
  BadgeCheck,
  Calendar,
  Check,
  CheckCircle2,
  Clipboard,
  Clock3,
  CreditCard,
  Download,
  IdCard,
  LogOut,
  MapPin,
  Plus,
  Printer,
  RefreshCw,
  ShieldCheck,
  Ticket,
  Users,
  Utensils,
} from 'lucide-react';
import { authApi, portalApi, publicApi, registrationApi } from '../lib/api.js';
import { openCheckout } from '../lib/razorpay.js';
import { ISTE, LOGO, NSSCE, PARALLAX_MARK } from './Public.jsx';
import { BrandedQr } from '../components/BrandedQr.jsx';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { useTheme } from '../lib/theme.jsx';
import { date, dateRange, dateTime, dayLabel, initials, money, percent } from '../lib/format.js';
import {
  Badge,
  Button,
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
  Stat,
  StatusBadge,
  Sheet,
  clearAsyncCache,
  useAsync,
} from '../components/ui.jsx';

const PORTAL_NAV = [
  ['My Pass & Ticket', '/portal/registration'],
  ['Select Events', '/portal/select-events'],
  ['My Registrations & Teams', '/portal/registrations'],
  ['Profile & Settings', '/portal/profile'],
];

function loadRazorpay() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve(window.Razorpay);
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = () => resolve(window.Razorpay);
    script.onerror = () => reject(new Error('Could not load the payment gateway.'));
    document.head.appendChild(script);
    return undefined;
  });
}

async function openRazorpay(order, user) {
  const Razorpay = await loadRazorpay();
  const logoUrl =
    typeof window !== 'undefined'
      ? `${window.location.origin}/favicon.png`
      : '';
  return new Promise((resolve, reject) => {
    const checkout = new Razorpay({
      key: order.razorpayKeyId,
      order_id: order.gatewayOrderId,
      amount: order.amountPaise,
      currency: 'INR',
      name: 'Parallax 2026',
      description: 'Convention pass',
      image: logoUrl,
      prefill: {
        email: user?.email || '',
        name: user?.fullName || '',
        contact: user?.phone || '',
      },
      theme: {
        color: '#0284c7',
        backdrop_color: 'rgba(5, 7, 10, 0.88)',
      },
      handler: () => resolve(true),
      modal: { ondismiss: () => resolve(false) },
    });
    try {
      checkout.open();
    } catch (error) {
      reject(error);
    }
  });
}

export function PortalLayout() {
  const { user, logout, isStaff, reload: reloadUser } = useAuth();
  const { edition, refresh: refreshSite } = useSite();
  const navigate = useNavigate();
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
          <div className="title-badges">
            <button
              type="button"
              className="button ghost small"
              onClick={refreshAll}
              disabled={refreshing}
              title="Re-fetch your profile, pass and bookings from the server"
              style={{ fontSize: 11, padding: '4px 8px' }}
            >
              <RefreshCw size={12} className={refreshing ? 'is-spinning' : ''} />
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
            {refreshNote ? (
              <small className="muted" style={{ fontSize: 11 }}>
                {refreshNote}
              </small>
            ) : null}
            {isStaff ? (
              <Badge tone="accent">Staff Access</Badge>
            ) : (
              <Badge tone="accent">Parallax 2027 Attendee</Badge>
            )}
            {user?.profileComplete ? <Badge tone="accent">Profile complete</Badge> : null}
            {isStaff ? (
              <Link to="/manage" className="button ghost small" style={{ fontSize: 11, padding: '4px 8px' }}>
                Staff Console →
              </Link>
            ) : null}
          </div>
        }
      />

      {/* Mobile Top User Bar & Swipeable Tabs */}
      <div className="section" style={{ paddingBottom: 0, paddingTop: 10 }}>
        <div className="portal-mobile-user-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
            <div className="avatar small" style={{ width: '32px', height: '32px', fontSize: '12px' }}>
              {initials(user?.fullName)}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: '13px', color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.fullName || 'Attendee'}
              </div>
              <div style={{ fontSize: '11px', color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.email}
              </div>
            </div>
          </div>
          <button className="text-link signout" onClick={signOut} style={{ fontSize: '12px', padding: '6px 10px', color: '#cbd5e1' }}>
            <LogOut size={13} /> Sign out
          </button>
        </div>

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
            <Link to="/manage" className="portal-mobile-tab-item" style={{ color: '#38bdf8' }}>
              <span>Staff Console ↗</span>
            </Link>
          ) : null}
        </nav>
      </div>

      <section className="section portal-layout">
        <aside className="portal-side">
          <div className="avatar">{initials(user?.fullName)}</div>
          <h3>{user?.fullName}</h3>
          <p>{user?.email}</p>
          {isStaff ? (
            <span className="pill staff-pill" style={{ borderColor: 'var(--cyan)', color: 'var(--cyan)' }}>
              Staff Administrator
            </span>
          ) : (
            <span className="pill" style={{ borderColor: 'rgba(56, 189, 248, 0.4)', color: 'var(--cyan)' }}>
              Attendee Portal
            </span>
          )}
          <nav aria-label="Participant portal">
            {PORTAL_NAV.map(([label, to, end]) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? 'active' : '')}>
                {label}
                <ArrowRight size={15} strokeWidth={1.5} />
              </NavLink>
            ))}
            {isStaff ? (
              <Link to="/manage" style={{ color: 'var(--cyan)' }}>
                Staff console
                <ArrowUpRight size={15} strokeWidth={1.5} />
              </Link>
            ) : null}
          </nav>
          <button className="text-link signout" onClick={signOut}>
            <LogOut size={15} strokeWidth={1.5} /> Sign out
          </button>
        </aside>
        <div className="portal-main">
          <Outlet key={pageKey} />
        </div>
      </section>
    </>
  );
}

function PassStatusCard({ pass, policy }) {
  const selection = pass?.selection;
  if (!pass) {
    return (
      <Panel className="portal-banner">
        <Eyebrow>Convention Pass</Eyebrow>
        <h2>No pass yet</h2>
        <p>
          Buy the {money(policy?.passPricePaise)} pass to unlock event selection, add-ons and your
          entry ticket.
        </p>
        <Button to="/portal/registration" icon={ArrowRight}>
          Get the pass
        </Button>
      </Panel>
    );
  }
  return (
    <Panel className="portal-banner">
      <div className="banner-top">
        <Eyebrow>CONVENTION PASS</Eyebrow>
        <StatusBadge status={pass.status} />
      </div>
      <h2>{pass.status === 'active' ? 'Pass active' : 'Pass awaiting payment'}</h2>
      <p>
        {money(pass.pricePaise)} · policy v{pass.policyVersion} ·{' '}
        {pass.paidAt ? `paid ${date(pass.paidAt)}` : 'payment pending'}
      </p>
      <div className="banner-actions">
        <Button to="/portal/tickets" variant="ghost" icon={Ticket}>
          View tickets
        </Button>
        <Button to="/portal/select-events" icon={ArrowRight}>
          {selection?.valid ? 'Review selections' : 'Finish selections'}
        </Button>
      </div>
    </Panel>
  );
}

export function PortalOverview() {
  const { user, isStaff } = useAuth();
  const { editionId, policy } = useSite();
  const pass = useAsync(() => portalApi.pass(editionId), [editionId], { enabled: Boolean(editionId) });
  const regs = useAsync(() => portalApi.registrations(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const tickets = useAsync(() => portalApi.tickets(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const verification = useAsync(() => portalApi.verification(editionId), [editionId], {
    enabled: Boolean(editionId),
  });

  const passData = pass.data?.data;
  const selection = passData?.selection;
  const registrations = regs.data?.data || [];
  const ticketRows = tickets.data?.data || [];
  const verificationStatus = verification.data?.data;

  return (
    <>
      {pass.loading ? <Loading label="Loading your pass" rows={1} /> : null}
      {pass.error ? <ErrorBox error={pass.error} onRetry={pass.reload} /> : null}
      {!pass.loading ? <PassStatusCard pass={passData} policy={policy} /> : null}

      <div className="portal-stats bezel">
        <div className="bezel-core">
          <Stat
            label="INCLUDED CHOICES"
            value={`${selection?.count || 0} / ${policy?.includedEventCount || 0}`}
            note={selection?.valid ? 'Selection valid' : 'Needs attention'}
          />
          <Stat
            label="SELECTED VALUE"
            value={money(selection?.valuePaise || 0)}
            note={`Cap ${money(policy?.includedValueCapPaise)}`}
          />
          <Stat label="REGISTRATIONS" value={registrations.length} note="Included and add-on" />
          <Stat label="TICKETS" value={ticketRows.length} note="Live entry credentials" />
        </div>
      </div>

      <div className="portal-columns">
        <Panel className="next-card">
          <Eyebrow>NEXT STEP</Eyebrow>
          <h3>
            {isStaff
              ? 'Staff Administration Active'
              : !passData
              ? 'Buy your convention pass'
              : !selection?.valid
                ? 'Complete your included selection'
                : verificationStatus?.status !== 'verified'
                  ? 'Finish student verification'
                  : 'You are ready for the convention'}
          </h3>
          <p>
            {isStaff
              ? 'You are signed in with staff privileges. Monitor live event registrations, scan badges at the door, and adjust convention controls.'
              : !passData
              ? 'The pass is mandatory and includes lunch, entry and the included-event allowance.'
              : !selection?.valid
                ? selection?.message || 'Choose included events within the published allowance.'
                : verificationStatus?.status !== 'verified'
                  ? 'Verification confirms your student status for the convention record.'
                  : 'Your pass, selections and ticket are all active.'}
          </p>
          <Button
            to={
              isStaff
                ? '/manage'
                : !passData
                  ? '/portal/registration'
                  : !selection?.valid
                    ? '/portal/select-events'
                    : '/portal/tickets'
            }
            icon={ArrowRight}
          >
            {isStaff ? 'Open Staff Console' : 'Continue'}
          </Button>
        </Panel>
        <Panel>
          <Eyebrow>PROGRESS</Eyebrow>
          <div className="progress-row">
            <span>Selection value</span>
            <b>{percent(selection?.valuePaise || 0, policy?.includedValueCapPaise || 0)}%</b>
          </div>
          <div className="progress-track">
            <i style={{ width: `${percent(selection?.valuePaise || 0, policy?.includedValueCapPaise || 0)}%` }} />
          </div>
          <div className="detail-row">
            <span>Selection deadline</span>
            <b>{date(policy?.selectionChangeDeadline)}</b>
          </div>
          <div className="detail-row">
            <span>Verification</span>
            <b style={isStaff ? { color: 'var(--cyan)' } : {}}>
              {isStaff ? 'Staff Exempt' : (verificationStatus?.status || 'unverified')}
            </b>
          </div>
          <div className="detail-row">
            <span>Lunch</span>
            <b>{(passData?.lunchDays || policy?.lunchIncludedDays || []).map(dayLabel).join(', ')}</b>
          </div>
        </Panel>
      </div>

      {ticketRows.length ? (
        <Panel>
          <div className="panel-head-row">
            <Eyebrow>ENTRY TICKETS</Eyebrow>
            <Link className="text-link" to="/portal/tickets">
              All tickets <ArrowRight size={15} strokeWidth={1.5} />
            </Link>
          </div>
          <div className="mini-ticket">
            <Ticket size={18} strokeWidth={1.4} />
            <div>
              <b>{ticketRows[0].title}</b>
              <small>
                {ticketRows[0].registrationNumber} · issued {date(ticketRows[0].issuedAt)}
              </small>
            </div>
            <StatusBadge status={ticketRows[0].status} />
          </div>
        </Panel>
      ) : null}
    </>
  );
}

export function PortalPass() {
  const { editionId, policy } = useSite();
  const { user } = useAuth();
  const navigate = useNavigate();
  const pass = useAsync(() => portalApi.pass(editionId), [editionId], { enabled: Boolean(editionId) });
  const [order, setOrder] = useState(null);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);

  const passData = pass.data?.data;

  const createOrder = async () => {
    setBusy('order');
    setMessage(null);
    try {
      const body = await portalApi.createPassOrder(editionId);
      setOrder(body.data);
      setMessage({ tone: 'info', text: 'Payment order created. Complete the payment to activate the pass.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const completePayment = async () => {
    if (!order) return;
    setBusy('pay');
    setMessage(null);
    try {
      if (order.mock) {
        await portalApi.mockPay(editionId, order.orderId);
      } else {
        const paid = await openRazorpay(order, user);
        if (!paid) {
          setMessage({ tone: 'info', text: 'Payment window closed. The order is still open.' });
          setBusy('');
          return;
        }
        for (let attempt = 0; attempt < 6; attempt += 1) {
          const status = await portalApi.payment(editionId, order.orderId);
          if (status.data?.status === 'paid') break;
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
      await pass.reload();
      setOrder(null);
      setMessage({ tone: 'success', text: 'Pass activated. Your entry ticket has been issued.' });
      setTimeout(() => navigate('/portal/tickets'), 900);
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  return (
    <>
      <SectionHead kicker="Convention Pass" title="One pass, full access" />
      {pass.loading ? <Loading label="Loading pass" rows={1} /> : null}
      {pass.error ? <ErrorBox error={pass.error} onRetry={pass.reload} /> : null}
      {!pass.loading && passData ? (
        <Panel>
          <div className="pass-summary">
            <div>
              <Eyebrow>STATUS</Eyebrow>
              <h3>{passData.status === 'active' ? 'Active pass' : 'Awaiting payment'}</h3>
              <p>
                {money(passData.pricePaise)} · policy v{passData.policyVersion}
              </p>
            </div>
            <StatusBadge status={passData.status} />
          </div>
          <div className="detail-row">
            <span>Purchased</span>
            <b>{date(passData.createdAt)}</b>
          </div>
          <div className="detail-row">
            <span>Paid</span>
            <b>{passData.paidAt ? dateTime(passData.paidAt) : 'Not paid'}</b>
          </div>
          <div className="detail-row">
            <span>Lunch</span>
            <b>{(passData.lunchDays || []).map(dayLabel).join(', ') || 'Included'}</b>
          </div>
          <div className="detail-row">
            <span>Included events</span>
            <b>{passData.selection?.count || 0} of {policy?.includedEventCount}</b>
          </div>
          <div className="banner-actions">
            <Button to="/portal/tickets" variant="ghost" icon={Ticket}>
              Tickets
            </Button>
            <Button to="/portal/select-events" icon={ArrowRight}>
              Choose events
            </Button>
          </div>
        </Panel>
      ) : null}

      {!pass.loading && !passData ? (
        <Panel className="buy-pass">
          <div className="buy-pass-head">
            <div>
              <Eyebrow>STEP 01</Eyebrow>
              <h2>Buy the convention pass</h2>
              <p className="buy-price">{money(policy?.passPricePaise)}</p>
            </div>
            <CreditCard size={40} strokeWidth={1} />
          </div>
          <ul className="check-list">
            <li>
              <Check size={15} strokeWidth={2.2} /> Lunch on{' '}
              {(policy?.lunchIncludedDays || []).map(dayLabel).join(' and ')}
            </li>
            <li>
              <Check size={15} strokeWidth={2.2} />{' '}
              {policy?.includedSelectionMode === 'exact' ? 'Exactly' : 'Up to'}{' '}
              {policy?.includedEventCount} included events within{' '}
              {money(policy?.includedValueCapPaise)}
            </li>
            <li>
              <Check size={15} strokeWidth={2.2} /> Entry ticket with a scannable token
            </li>
            <li>
              <Check size={15} strokeWidth={2.2} /> Add-on events available after activation
            </li>
          </ul>
          {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
          {!order ? (
            <Button onClick={createOrder} disabled={busy === 'order'} icon={ArrowRight}>
              {busy === 'order' ? 'Creating order' : 'Create payment order'}
            </Button>
          ) : (
            <div className="order-box">
              <div className="detail-row">
                <span>Amount</span>
                <b>{money(order.amountPaise)}</b>
              </div>
              <div className="detail-row">
                <span>Payment method</span>
                <b>{order.mock ? 'Instant verification' : 'Razorpay'}</b>
              </div>
              <Button onClick={completePayment} disabled={busy === 'pay'} icon={CreditCard}>
                {busy === 'pay'
                  ? 'Processing'
                  : order.mock
                    ? `Complete pass activation · ${money(order.amountPaise)}`
                    : 'Open secure checkout'}
              </Button>
            </div>
          )}
          <p className="notice">
            <ShieldCheck size={16} strokeWidth={1.5} />
            {order?.mock === false
              ? 'Card and UPI details are encrypted and entered on the payment gateway, never on this site.'
              : 'Completing payment activates your convention pass and issues your verified badge.'}
          </p>
        </Panel>
      ) : null}
    </>
  );
}

export function PortalSelectEvents() {
  const { editionId, slug, policy } = useSite();
  const { user } = useAuth();
  const pass = useAsync(() => portalApi.pass(editionId), [editionId], { enabled: Boolean(editionId) });
  const catalogue = useAsync(() => publicApi.events(slug, { pageSize: 100 }), [slug], {
    enabled: Boolean(slug),
  });
  const regs = useAsync(() => portalApi.registrations(editionId), [editionId], {
    enabled: Boolean(editionId),
  });

  const passData = pass.data?.data;
  const selection = passData?.selection;
  const [selected, setSelected] = useState([]);
  const [addons, setAddons] = useState([]);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');

  // Re-sync the draft only when the server's saved selection actually changes,
  // not on every unrelated refresh of the pass document.
  const savedSignature = useMemo(
    () =>
      (selection?.selections || [])
        .filter((item) => item.selected)
        .map((item) => item.eventId)
        .sort()
        .join('|'),
    [selection],
  );

  useEffect(() => {
    setSelected(savedSignature ? savedSignature.split('|') : []);
  }, [savedSignature]);

  const required = selection?.requiredCount ?? policy?.includedEventCount ?? 0;
  const mode = selection?.mode || policy?.includedSelectionMode || 'up_to';
  const cap = selection?.capPaise ?? policy?.includedValueCapPaise ?? 0;
  const capInclusive = selection?.capInclusive !== false;

  const addonRegisteredIds = new Set(
    (regs.data?.data || [])
      .filter(
        (row) =>
          row.kind === 'addon' && ['confirmed', 'reserved', 'pending'].includes(row.status),
      )
      .map((row) => row.eventId),
  );

  // An event already booked as an add-on cannot also be claimed inside the pass.
  const options = (selection?.selections || []).filter(
    (item) => !addonRegisteredIds.has(item.eventId) || selected.includes(item.eventId),
  );

  const value = options
    .filter((item) => selected.includes(item.eventId))
    .reduce((sum, item) => sum + item.baseValuePaise, 0);

  const withinCap = capInclusive ? value <= cap : value < cap;
  const withinCount = mode === 'exact' ? selected.length === required : selected.length <= required;
  const valid = withinCap && withinCount && !selection?.locked;

  const canAdd = (event) => {
    if (selection?.locked) return false;
    if (selected.includes(event.eventId)) return true;
    if (event.selectable === false) return false;
    if (selected.length >= required) return false;
    const nextValue = value + event.baseValuePaise;
    return capInclusive ? nextValue <= cap : nextValue < cap;
  };

  const registeredEventIds = new Set(
    (regs.data?.data || [])
      .filter((row) => ['confirmed', 'reserved', 'pending'].includes(row.status))
      .map((row) => row.eventId),
  );
  const addonOptions = (catalogue.data?.data || []).filter(
    (event) =>
      !selected.includes(event.id) &&
      !registeredEventIds.has(event.id) &&
      event.registrationOpen,
  );
  const addonTotal = addonOptions
    .filter((event) => addons.includes(event.id))
    .reduce((sum, event) => sum + event.addonPricePaise, 0);

  const toggle = (eventId) => {
    if (selection?.locked) {
      setMessage({ tone: 'error', text: 'Included selections are locked after the deadline.' });
      return;
    }
    if (selected.includes(eventId)) {
      setMessage(null);
      setSelected(selected.filter((id) => id !== eventId));
      return;
    }
    const option = options.find((item) => item.eventId === eventId);
    if (!option) {
      setMessage({ tone: 'error', text: 'That event is not available for included selection.' });
      return;
    }
    if (option.selectable === false) {
      setMessage({ tone: 'error', text: `${option.title} is full. Pick another event or join the waitlist at the desk.` });
      return;
    }
    if (selected.length >= required) {
      setMessage({
        tone: 'error',
        text:
          mode === 'exact'
            ? `This pass includes exactly ${required} events. Remove one before adding another.`
            : `You can include up to ${required} events. Remove one before adding another.`,
      });
      return;
    }
    const nextValue = value + option.baseValuePaise;
    if (capInclusive ? nextValue > cap : nextValue >= cap) {
      setMessage({
        tone: 'error',
        text: `Adding ${option.title} would take you past the ${money(cap)} base-value cap.`,
      });
      return;
    }
    setMessage(null);
    setSelected([...selected, eventId]);
  };

  const save = async () => {
    setBusy('save');
    setMessage(null);
    try {
      await portalApi.saveSelections(editionId, selected);
      await pass.reload();
      setMessage({ tone: 'success', text: 'Selections saved. Included registrations are updated.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const registerAddons = async () => {
    if (!addons.length) return;
    setBusy('addons');
    setMessage(null);
    try {
      const body = await portalApi.registerAddons(editionId, addons);
      const order = body.data?.order;
      if (order?.mock) {
        await portalApi.mockPay(editionId, order.orderId);
      } else if (order) {
        const attendeeUser = {
          ...user,
          fullName: user?.fullName || '',
          email: user?.email || '',
          phone: user?.phone || '',
        };
        const response = await openCheckout(
          order,
          attendeeUser,
          `Add-on Event Bookings (${addons.length}) - Parallax 2027`
        );
        if (!response) {
          setMessage({
            tone: 'info',
            text: 'Payment was cancelled or closed. Your add-on bookings were not charged.',
          });
          return;
        }
        if (response.failed) {
          setMessage({
            tone: 'error',
            text: response.error?.message || 'Payment declined in Razorpay. Please retry or choose another payment method.',
          });
          return;
        }
        await portalApi.verifyPayment(editionId, {
          orderId: order.orderId,
          razorpayPaymentId: response.razorpay_payment_id,
          razorpaySignature: response.razorpay_signature,
        });
      }
      setAddons([]);
      await Promise.all([regs.reload(), pass.reload()]);
      setMessage({
        tone: 'success',
        text: order
          ? `Add-on registrations confirmed & paid! Your tickets are ready.`
          : 'Add-on registrations confirmed.',
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  if (pass.loading) return <Loading label="Loading your pass" rows={2} />;
  if (!passData) {
    return (
      <Empty title="A pass is required first" desc="Buy the convention pass to unlock event selection.">
        <Button to="/portal/registration" icon={ArrowRight}>
          Get the pass
        </Button>
      </Empty>
    );
  }

  return (
    <>
      <SectionHead kicker="Step 2" title="Build your event lineup" />
      <div className="selector-note">
        <Ticket size={18} strokeWidth={1.4} />
        <p>
          Pass {money(passData.pricePaise)} · {mode === 'exact' ? 'Exactly' : 'Up to'} {required}{' '}
          included events · cap {money(cap)}. Base values decide the cap; add-on prices are separate.
        </p>
      </div>
      <div className="selector-summary">
        <div>
          <span>INCLUDED SELECTED</span>
          <b>
            {selected.length} / {required}
          </b>
        </div>
        <div>
          <span>BASE VALUE TOTAL</span>
          <b>{money(value)}</b>
        </div>
        <div>
          <span>CAP ROOM</span>
          <b>{money(Math.max(0, cap - value))}</b>
        </div>
        <Button variant="ghost" onClick={() => setSelected([])} icon={RefreshCw}>
          Reset
        </Button>
      </div>
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
      {selection?.locked ? (
        <InlineMessage tone="error">
          The selection deadline has passed. Contact the organisers for a change.
        </InlineMessage>
      ) : null}

      <h2 className="section-sub">Eligible included events</h2>
      <p className="muted">
        Toggling a choice updates the total immediately. Save once the allowance is satisfied.
      </p>
      {addonRegisteredIds.size ? (
        <InlineMessage tone="info">
          Events already booked as add-ons are excluded from the included allowance. Cancel that
          add-on first if you would rather claim it inside the pass.
        </InlineMessage>
      ) : null}
      <div className="choice-list">
        {options.map((event) => {
          const blocked = !canAdd(event) && !selected.includes(event.eventId);
          return (
          <label
            className={`choice ${selected.includes(event.eventId) ? 'is-selected' : ''} ${blocked ? 'is-blocked' : ''}`.trim()}
            key={event.eventId}
          >
            <input
              type="checkbox"
              checked={selected.includes(event.eventId)}
              onChange={() => toggle(event.eventId)}
              disabled={Boolean(selection?.locked) || event.selectable === false}
            />
            <span className="choice-check">
              {selected.includes(event.eventId) ? <Check size={14} strokeWidth={2.2} /> : <Plus size={14} strokeWidth={1.8} />}
            </span>
            <span className="choice-title">
              <b>{event.title}</b>
              <small>
                {event.format} · {date(event.startsAt)}
              </small>
            </span>
            <span className="choice-price">
              Base {money(event.baseValuePaise)}
              <small>
                {event.selectable === false
                  ? 'Full'
                  : event.seatsLeft != null
                    ? `${event.seatsLeft} seats left`
                    : `Add-on ${money(event.addonPricePaise)}`}
              </small>
            </span>
          </label>
          );
        })}
      </div>
      <div className="save-row">
        <Button
          onClick={save}
          disabled={busy === 'save' || Boolean(selection?.locked) || !valid}
          icon={Check}
        >
          {busy === 'save' ? 'Saving' : 'Save included selections'}
        </Button>
        <span className={valid ? 'valid-note' : 'invalid-note'}>
          {valid
            ? 'Within the allowance'
            : selection?.locked
              ? 'Locked after the deadline'
              : !withinCap
                ? `Value exceeds the ${money(cap)} cap`
                : `${selected.length} of ${required} chosen — ${mode === 'exact' ? 'exactly' : 'up to'} ${required} within ${money(cap)}`}
        </span>
      </div>

      <h2 className="section-sub">Additional paid events</h2>
      <p className="muted">
        Each add-on is charged at its published fee after the pass. The pass is never replaced.
      </p>
      {selected.length < required ? (
        <InlineMessage tone="info">
          You still have {required - selected.length} included{' '}
          {required - selected.length === 1 ? 'slot' : 'slots'} on your pass. Events inside your{' '}
          {money(cap)} allowance are already covered, so claim them above instead of paying the
          add-on price here.
        </InlineMessage>
      ) : null}
      <div className="addon-box">
        {addonOptions.length ? (
          addonOptions.map((event) => (
            <label key={event.id} className="addon-choice">
              <input
                type="checkbox"
                checked={addons.includes(event.id)}
                onChange={() =>
                  setAddons((current) =>
                    current.includes(event.id)
                      ? current.filter((id) => id !== event.id)
                      : [...current, event.id],
                  )
                }
              />
              <span>
                {event.title}
                <small>
                  {event.categoryName} · {event.format}
                </small>
              </span>
              <b>{money(event.addonPricePaise)}</b>
            </label>
          ))
        ) : (
          <p className="muted">No add-on events are currently open for you.</p>
        )}
        <div className="addon-total">
          <span>Pass</span>
          <b>{money(passData.pricePaise)}</b>
          <span>Add-ons</span>
          <b>{money(addonTotal)}</b>
          <strong>Due now {money(addonTotal)}</strong>
        </div>

        {/* Cancellation, Refund & Double Payment Warning */}
        <div style={{ margin: '14px 0', padding: '12px 14px', borderRadius: '10px', background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', fontSize: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#f8fafc', fontWeight: 700, marginBottom: '6px' }}>
            <ShieldCheck size={15} color="#38bdf8" />
            <span>Add-on Payment, Refund &amp; Safety Policy</span>
          </div>
          <p style={{ margin: '0 0 6px 0', color: '#94a3b8', lineHeight: '1.4' }}>
            • <b>Refund Guarantee:</b> If an event or workshop is cancelled by the organisers, a 100% refund is credited back to your bank within 5–7 working days.
          </p>
          <p style={{ margin: 0, color: '#fbbf24', lineHeight: '1.4' }}>
            • <b>Avoid Double Charges:</b> Do not refresh or exit while Razorpay checkout is processing. If money is deducted but tickets take a moment, wait 2 minutes or check your receipts before trying again.
          </p>
        </div>

        <Button onClick={registerAddons} disabled={!addons.length || busy === 'addons'} icon={CreditCard} variant="primary">
          {busy === 'addons' ? 'Securing booking…' : `Pay ${money(addonTotal)} with Razorpay`}
        </Button>
        <p className="demo-label">
          Add-on reservations expire after {policy?.holdMinutes || 15} minutes if unpaid.
        </p>
      </div>
    </>
  );
}

export function PortalRegistrations() {
  const { editionId } = useSite();
  const [activeTab, setActiveTab] = useState('events');
  const regs = useAsync(() => portalApi.registrations(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const [confirm, setConfirm] = useState(null);
  const [slip, setSlip] = useState(null);
  const [slipBusy, setSlipBusy] = useState(null);
  const [message, setMessage] = useState(null);
  const rows = regs.data?.data || [];

  // Payment slip for a paid add-on event, printable to PDF from the browser.
  const openSlip = async (row) => {
    setMessage(null);
    setSlipBusy(row.id);
    try {
      const body = await portalApi.registrationReceipt(editionId, row.id);
      setSlip(body?.data || null);
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setSlipBusy(null);
    }
  };
  const cancelCutoff = confirm?.eventStartsAt
    ? new Date(confirm.eventStartsAt).getTime() - 24 * 60 * 60 * 1000
    : null;
  const cancelLocked = cancelCutoff !== null && Date.now() >= cancelCutoff;

  const cancel = async (id) => {
    setMessage(null);
    try {
      await portalApi.cancelRegistration(editionId, id);
      await regs.reload();
      setMessage({ tone: 'success', text: 'Registration cancelled.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setConfirm(null);
    }
  };

  return (
    <>
      <div className="portal-subtabs" style={{ display: 'flex', gap: '10px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <button
          type="button"
          className={`button ${activeTab === 'events' ? 'primary' : 'ghost'}`}
          onClick={() => setActiveTab('events')}
          style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <Ticket size={16} />
          <span>My Event Registrations</span>
          {rows.length ? <span className="badge" style={{ padding: '2px 6px', fontSize: '11px' }}>{rows.length}</span> : null}
        </button>
        <button
          type="button"
          className={`button ${activeTab === 'teams' ? 'primary' : 'ghost'}`}
          onClick={() => setActiveTab('teams')}
          style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <Users size={16} />
          <span>My Teams &amp; Invites</span>
        </button>
      </div>

      {activeTab === 'teams' ? (
        <PortalTeams />
      ) : (
        <>
          <SectionHead
            kicker="Selection Record"
            title="My registrations"
            action={
              <Button to="/portal/select-events" variant="ghost" icon={Plus}>
                Add events
              </Button>
            }
          />
          {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
          {regs.loading ? <Loading label="Loading registrations" rows={2} /> : null}
          {regs.error ? <ErrorBox error={regs.error} onRetry={regs.reload} /> : null}
          {!regs.loading && !rows.length ? (
            <Empty title="No registrations yet" desc="Included selections and add-on events appear here.">
              <Button to="/portal/select-events" icon={ArrowRight}>
                Choose events
              </Button>
            </Empty>
          ) : null}
          <div className="registration-list">
            {rows.map((row) => (
              <div className="registration-row" key={row.id}>
                <span className="event-dot" />
                <div>
                  <b>{row.eventTitle}</b>
                  <small>
                    {row.registrationNumber} · {row.category} ·{' '}
                    {row.teamName ? `${row.teamName} · ` : ''}
                    {row.kind === 'included' ? 'Included with Pass (Free)' : row.kind}
                  </small>
                  {row.status === 'cancelled' && row.cancelledBy === 'admin' ? (
                    <div style={{ fontSize: '12px', color: '#f87171', marginTop: '4px', fontWeight: 500 }}>
                      ⚠️ Removed by administration{row.cancellationReason ? `: ${row.cancellationReason}` : ''}
                    </div>
                  ) : row.status === 'cancelled' && row.cancelledBy === 'user' ? (
                    <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>
                      Cancelled by you · Seat released
                    </div>
                  ) : null}
                </div>
                <span className="reg-fee">{money(row.feePaise)}</span>
                <div>
                  {row.status === 'cancelled' ? (
                    row.cancelledBy === 'admin' ? (
                      <Badge tone="bad">Removed by Admin</Badge>
                    ) : (
                      <Badge tone="muted">Cancelled</Badge>
                    )
                  ) : (
                    <StatusBadge status={row.status} />
                  )}
                  {row.kind === 'addon' &&
                  row.feePaise > 0 &&
                  (row.status === 'confirmed' || row.status === 'cancelled') ? (
                    <button
                      className="table-action"
                      style={{ marginTop: 6, display: 'block' }}
                      onClick={() => openSlip(row)}
                      disabled={slipBusy === row.id}
                    >
                      {slipBusy === row.id ? 'Loading…' : 'Payment slip'}
                    </button>
                  ) : null}
                </div>
                {row.status !== 'cancelled' ? (
                  <button className="table-action" onClick={() => setConfirm(row)}>
                    Cancel
                  </button>
                ) : null}
              </div>
            ))}
          </div>
          <Sheet
            open={Boolean(slip)}
            title={slip?.eventTitle ? `Payment slip · ${slip.eventTitle}` : 'Payment slip'}
            onClose={() => setSlip(null)}
            wide
            eyebrow="EVENT PAYMENT RECEIPT"
          >
            {slip ? (
              <div className="px-receipt-stage">
                <div className="px-receipt-card px-printable-target">
                  <div className="px-receipt-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <img
                        src={LOGO}
                        alt="Parallax"
                        style={{ height: '32px', width: 'auto', objectFit: 'contain' }}
                      />
                      <div className="px-receipt-title">
                        <h2 style={{ color: '#0f172a', margin: 0, fontSize: '18px', fontWeight: 800 }}>
                          PARALLAX · EVENT PAYMENT SLIP
                        </h2>
                        <p style={{ margin: '3px 0 0 0', fontSize: '11px', color: '#475569' }}>
                          {slip.editionName || 'Convention'} · ISTE Student Chapter, NSSCE Palakkad
                        </p>
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <img src={ISTE} alt="ISTE" style={{ height: '20px', width: 'auto' }} />
                        <img src={NSSCE} alt="NSSCE" style={{ height: '20px', width: 'auto' }} />
                      </div>
                      <span
                        className={`badge ${slip.paidPaise > 0 ? 'good' : 'warn'}`}
                        style={{ fontSize: '12px', fontWeight: '700' }}
                      >
                        {slip.paidPaise > 0 ? '✓ PAID' : 'PAYMENT PENDING'}
                      </span>
                      <p style={{ margin: 0, fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                        {slip.paidAt ? dateTime(slip.paidAt) : dateTime(slip.issuedAt)}
                      </p>
                    </div>
                  </div>

                  <div className="px-receipt-meta-grid">
                    <div className="px-receipt-meta-item">
                      <small>RECEIPT REF</small>
                      <b>{slip.registrationNumber}</b>
                    </div>
                    <div className="px-receipt-meta-item">
                      <small>PAYMENT ID</small>
                      <b>{slip.transactionId || '—'}</b>
                    </div>
                    <div className="px-receipt-meta-item">
                      <small>REGISTRATION</small>
                      <b style={{ textTransform: 'capitalize' }}>{slip.status}</b>
                    </div>
                    <div className="px-receipt-meta-item">
                      <small>EVENT DATE</small>
                      <b>{slip.eventStartsAt ? dateTime(slip.eventStartsAt) : '—'}</b>
                    </div>
                  </div>

                  <table className="px-receipt-table">
                    <thead>
                      <tr>
                        <th>Item Description</th>
                        <th>Attendee</th>
                        <th>Status</th>
                        <th style={{ textAlign: 'right' }}>Amount (INR)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>
                          <b>{slip.eventTitle}</b>
                          <div style={{ fontSize: '11px', color: '#64748b' }}>
                            {slip.eventVenue ? `Venue: ${slip.eventVenue}` : 'Event add-on registration'}
                          </div>
                        </td>
                        <td>
                          <div>{slip.participantName || '—'}</div>
                          <div style={{ fontSize: '11px', color: '#64748b' }}>
                            {slip.participantEmail || ''}
                          </div>
                        </td>
                        <td>
                          <span
                            style={{
                              color: slip.paidPaise > 0 ? '#16a34a' : '#b45309',
                              fontWeight: '700',
                            }}
                          >
                            {slip.paidPaise > 0 ? 'PAID' : 'PENDING'}
                          </span>
                        </td>
                        <td style={{ textAlign: 'right', fontWeight: '700' }}>
                          {money(slip.paidPaise || slip.feePaise || 0)}
                        </td>
                      </tr>
                      <tr className="px-receipt-total-row">
                        <td colSpan={3} style={{ textAlign: 'right', padding: '12px 4px' }}>
                          Total Amount Paid:
                        </td>
                        <td style={{ textAlign: 'right', padding: '12px 4px', color: '#0284c7' }}>
                          {money(slip.paidPaise || 0)}
                        </td>
                      </tr>
                    </tbody>
                  </table>

                  <div
                    style={{
                      borderTop: '1px solid #e2e8f0',
                      paddingTop: '12px',
                      fontSize: '11px',
                      color: '#64748b',
                      display: 'flex',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '8px',
                    }}
                  >
                    <div>
                      <b>Issuer:</b> ISTE Student Chapter, NSS College of Engineering, Palakkad - 678008
                    </div>
                    <div>This slip covers one event add-on payment. Keep it for your records.</div>
                  </div>
                </div>

                <div
                  className="no-print"
                  style={{ display: 'flex', gap: '12px', marginTop: '16px', flexWrap: 'wrap', justifyContent: 'center' }}
                >
                  <Button onClick={() => window.print()} icon={Printer} variant="primary">
                    Save as PDF
                  </Button>
                  <Button onClick={() => setSlip(null)} variant="ghost">
                    Close
                  </Button>
                </div>
              </div>
            ) : (
              <Loading label="Loading payment slip" rows={2} />
            )}
          </Sheet>

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
                  : 'Refunds are not automatic. The finance desk reviews every cancellation and returns the paid amount, less any processing charges, to your original payment method.'}
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
        </>
      )}
    </>
  );
}

export function PortalTickets() {
  const { user } = useAuth();
  const { edition, editionId } = useSite();
  const { accent } = useTheme();
  const [qrTheme, setQrTheme] = useState('auto');
  const tickets = useAsync(() => portalApi.tickets(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const profile = useAsync(() => authApi.profile(), [], { enabled: Boolean(user) });
  const [message, setMessage] = useState(null);
  const [downloadTicket, setDownloadTicket] = useState(null);
  const qrDownloadRef = useRef(null);
  const rows = tickets.data?.data || [];
  const prof = profile.data?.data || {};

  // The QR is drawn in the browser from the signed token the API returns, so
  // downloading it is just a canvas export.
  useEffect(() => {
    if (!downloadTicket) return;
    const canvas = qrDownloadRef.current?.querySelector('canvas');
    if (!canvas) return;
    const link = document.createElement('a');
    link.href = canvas.toDataURL('image/png');
    link.download = `parallax-pass-${downloadTicket.registrationNumber || downloadTicket.id}.png`;
    link.click();
    setMessage({ tone: 'success', text: 'Pass QR downloaded (PNG).' });
    setDownloadTicket(null);
  }, [downloadTicket]);

  const copy = async (token) => {
    try {
      await navigator.clipboard.writeText(token);
      setMessage({ tone: 'success', text: 'Ticket token copied to clipboard.' });
    } catch {
      setMessage({ tone: 'error', text: 'Clipboard access was blocked.' });
    }
  };

  const printBadge = () => {
    window.print();
  };

  const downloadQr = (ticket) => {
    if (!ticket?.token) {
      setMessage({ tone: 'error', text: 'This ticket has no scannable token yet.' });
      return;
    }
    setDownloadTicket(ticket);
  };

  return (
    <>
      <SectionHead
        kicker="Entry Credentials"
        title="Your official convention pass"
        action={
          rows.length ? (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <Button
                to="/portal/registration"
                variant="ghost"
                icon={IdCard}
              >
                Open pass &amp; save PDF
              </Button>
              <Button variant="light" onClick={printBadge} icon={Printer}>
                Print / Save pass
              </Button>
            </div>
          ) : null
        }
      />
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
      {tickets.loading ? <Loading label="Loading tickets" rows={2} /> : null}
      {tickets.error ? <ErrorBox error={tickets.error} onRetry={tickets.reload} /> : null}
      {!tickets.loading && !rows.length ? (
        <Empty title="No ticket issued yet" desc="Tickets are issued when a pass or paid registration activates.">
          <Button to="/portal/registration" icon={ArrowRight}>
            Get the pass
          </Button>
        </Empty>
      ) : null}

      <div className="makemypass-container">
        {rows.map((ticket) => (
          <div key={ticket.id} className="makemypass-card rise">
            {/* Top Lanyard Slot */}
            <div className="badge-hanger">
              <div className="badge-lanyard-strap" />
              <div className="badge-slot" />
            </div>

            {/* Badge Masthead */}
            <div className="badge-masthead">
              <div className="badge-brand-center">
                <img src={LOGO} alt="Parallax" className="badge-logo-center" />
                <div className="badge-sub-row">
                  <img src={ISTE} alt="ISTE" className="badge-host-logo-inline" />
                  <span className="badge-sub">{edition?.organizer || 'ISTE STUDENT CHAPTER · NSSCE'}</span>
                </div>
              </div>
              <div className="badge-campus-tag">
                <MapPin size={12} />
                <span>{edition?.host || 'NSS College of Engineering, Palakkad'}</span>
              </div>
            </div>

            {/* Attendee Identity Section */}
            <div className="badge-attendee-section">
              <div className="badge-role-pill">
                <span>{ticket.kind === 'pass' ? 'ALL-ACCESS DELEGATE' : 'EVENT PARTICIPANT'}</span>
              </div>
              <h2 className="badge-name">{prof.fullName || user?.fullName || 'Convention Delegate'}</h2>
              <p className="badge-college">
                {prof.collegeName || 'NSS College of Engineering, Palakkad'}
              </p>
              {prof.branch || prof.course ? (
                <p className="badge-dept">
                  {[prof.course, prof.branch, prof.yearOfStudy ? `Year ${prof.yearOfStudy}` : null].filter(Boolean).join(' · ')}
                </p>
              ) : null}
              <div className="badge-reg-strip">
                <span className="badge-reg-num">REF #{ticket.registrationNumber}</span>
                <span className="badge-status-chip">
                  <CheckCircle2 size={12} />
                  <span>{ticket.status === 'active' ? 'VALID PASS' : ticket.status.toUpperCase()}</span>
                </span>
              </div>
            </div>

            {/* Perforation Line with Side Notches */}
            <div className="badge-perforation">
              <div className="notch-cut notch-left" />
              <div className="perf-line" />
              <div className="notch-cut notch-right" />
            </div>

            {/* Core QR Matrix Box with Theme Styling & Laser Sweep */}
            <div className="badge-qr-box">
              <div className="qr-reticle reticle-tl" />
              <div className="qr-reticle reticle-tr" />
              <div className="qr-reticle reticle-bl" />
              <div className="qr-reticle reticle-br" />
              <div className="qr-matrix-surface">
                <BrandedQr
                  value={ticket.token}
                  title={`QR entry pass for ${ticket.title}`}
                  className="qr-img"
                  logoSrc={PARALLAX_MARK}
                />
              </div>

              {/* QR Theme Quick Switcher */}
              <div className="qr-mode-selector">
                <button
                  type="button"
                  className={`qr-mode-pill ${qrTheme === 'auto' ? 'is-active' : ''}`}
                  onClick={() => setQrTheme('auto')}
                  title="Follow active website theme"
                >
                  Theme Auto
                </button>
                <button
                  type="button"
                  className={`qr-mode-pill ${qrTheme === 'light' ? 'is-active' : ''}`}
                  onClick={() => setQrTheme('light')}
                  title="High-contrast print mode"
                >
                  Print High-Contrast
                </button>
              </div>
            </div>

            {/* Security Token Bar */}
            <div className="badge-token-bar">
              <span className="token-label">TOKEN</span>
              <code className="token-code">{ticket.token}</code>
              <button
                type="button"
                className="token-copy-btn"
                onClick={() => copy(ticket.token)}
                title="Copy token to clipboard"
                aria-label="Copy ticket token"
              >
                <Clipboard size={14} />
              </button>
            </div>

            {/* Convention Logistics Stub */}
            <div className="badge-logistics-grid">
              <div className="logistics-cell">
                <Calendar size={13} />
                <div>
                  <span className="cell-lbl">DATES</span>
                  <b>{ticket.startsAt ? dateTime(ticket.startsAt) : dateRange(edition?.startsAt, edition?.endsAt)}</b>
                </div>
              </div>
              <div className="logistics-cell">
                <Utensils size={13} />
                <div>
                  <span className="cell-lbl">MEALS</span>
                  <b>{(edition?.policy?.lunchIncludedDays || ['day1', 'day2']).length ? 'LUNCH INCLUDED' : 'NOT INCLUDED'}</b>
                </div>
              </div>
              <div className="logistics-cell full-width">
                <MapPin size={13} />
                <div>
                  <span className="cell-lbl">VENUE & CHECK-IN</span>
                  <b>
                    {ticket.venueRoom
                      ? `${ticket.venueRoom.toUpperCase()} · ${(edition?.venue || 'NSSCE CAMPUS').toUpperCase()}`
                      : (edition?.venue ? edition.venue.toUpperCase() : 'NSSCE CAMPUS, PALAKKAD')}
                  </b>
                </div>
              </div>
            </div>

            {/* Action Bar */}
            <div className="badge-actions-bar">
              <Button variant="light" onClick={printBadge} icon={Printer}>
                Print pass
              </Button>
              <Button variant="ghost" onClick={() => downloadQr(ticket)} icon={Download}>
                Save QR
              </Button>
            </div>

            {/* Subtle Security Footer */}
            <div className="badge-footer">
              <span>ISTE NSSCE CHAPTER · OFFICIAL ENTRY PASS</span>
              <span className="badge-security-hash">SECURE HMAC-SHA256 DERIVED</span>
            </div>
          </div>
        ))}
      </div>
      {downloadTicket ? (
        <div ref={qrDownloadRef} style={{ display: 'none' }} aria-hidden="true">
          <QRCodeCanvas
            value={downloadTicket.token}
            size={640}
            level="M"
            marginSize={4}
            bgColor="#ffffff"
            fgColor="#000000"
          />
        </div>
      ) : null}
    </>
  );
}

export function PortalTeams() {
  const { editionId, slug, policy } = useSite();
  const teams = useAsync(() => portalApi.teams(editionId), [editionId], { enabled: Boolean(editionId) });
  const pass = useAsync(() => portalApi.pass(editionId), [editionId], { enabled: Boolean(editionId) });
  const catalogue = useAsync(() => publicApi.events(slug, { format: 'team', pageSize: 100 }), [slug], {
    enabled: Boolean(slug),
  });
  const [form, setForm] = useState({ eventId: '', name: '' });
  const [joinCode, setJoinCode] = useState('');
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');

  const teamEvents = catalogue.data?.data || [];
  const rows = teams.data?.data || [];
  const passActive = pass.data?.data?.status === 'active';
  const needsPass = Boolean(policy?.teamMembersRequirePass) && !passActive && !pass.loading;

  useEffect(() => {
    if (!form.eventId && teamEvents.length) setForm((current) => ({ ...current, eventId: teamEvents[0].id }));
  }, [teamEvents.length]);

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
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}

      <div className="portal-columns">
        <Panel>
          <Eyebrow>CREATE A TEAM</Eyebrow>
          <FieldGrid>
            <Field label="Team event">
              <select
                value={form.eventId}
                onChange={(event) => setForm({ ...form, eventId: event.target.value })}
              >
                {teamEvents.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.title} ({event.teamMinSize}-{event.teamMaxSize})
                  </option>
                ))}
              </select>
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
          <Button
            onClick={() =>
              run(
                'create',
                () => portalApi.createTeam(editionId, { eventId: form.eventId, name: form.name }),
                'Team created. Share the invite code.',
              )
            }
            disabled={busy === 'create' || !form.eventId || form.name.trim().length < 2}
            icon={Users}
          >
            {busy === 'create' ? 'Creating' : 'Create team'}
          </Button>
        </Panel>
        <Panel>
          <Eyebrow>JOIN A TEAM</Eyebrow>
          <Field label="Invite code" hint="The leader shares an eight-character code.">
            <input
              value={joinCode}
              onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
              placeholder="A1B2C3D4"
              maxLength={16}
            />
          </Field>
          <Button
            variant="ghost"
            onClick={async () => {
              const ok = await run(
                'join',
                () => portalApi.joinTeam(editionId, joinCode),
                'You joined the team.',
              );
              if (ok) setJoinCode('');
            }}
            disabled={busy === 'join' || joinCode.trim().length < 4}
          >
            {busy === 'join' ? 'Joining' : 'Join with code'}
          </Button>
        </Panel>
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
            {team.inviteCode && team.status !== 'locked' ? (
              <div className="invite-row">
                <div>
                  <span>INVITE CODE</span>
                  <code>{team.inviteCode}</code>
                </div>
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
            ) : null}
            {team.status !== 'locked' ? (
              <Button
                variant="ghost"
                onClick={() =>
                  run(`leave-${team.id}`, () => portalApi.leaveTeam(editionId, team.id), 'You left the team.')
                }
                disabled={busy === `leave-${team.id}`}
              >
                Leave team
              </Button>
            ) : (
              <p className="muted" style={{ fontSize: '12px', fontStyle: 'italic', margin: '8px 0 0 0' }}>
                Roster is locked. Members cannot leave or change teams.
              </p>
            )}
          </Panel>
        ))}
      </div>
    </>
  );
}

export function PortalVerification() {
  const { editionId } = useSite();
  const { user, reload } = useAuth();
  const verification = useAsync(() => portalApi.verification(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const [method, setMethod] = useState('roster');
  const [institutionEmail, setInstitutionEmail] = useState('');
  const [file, setFile] = useState(null);
  const [code, setCode] = useState('');
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');

  const status = verification.data?.data;

  const submit = async () => {
    setBusy('submit');
    setMessage(null);
    try {
      const form = new FormData();
      form.set('method', method);
      if (method === 'college_email') form.set('institutionEmail', institutionEmail);
      if (method === 'document' && file) form.set('file', file);
      await portalApi.submitVerification(editionId, form);
      await verification.reload();
      await reload();
      setMessage({
        tone: 'success',
        text:
          method === 'college_email'
            ? 'Verification submitted. Enter the code sent to your institutional email.'
            : method === 'roster'
              ? 'Roster check submitted.'
              : 'Document submitted for review.',
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const confirm = async () => {
    setBusy('confirm');
    setMessage(null);
    try {
      await portalApi.confirmVerification(editionId, code);
      await verification.reload();
      await reload();
      setMessage({ tone: 'success', text: 'Email confirmed. You are verified.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  return (
    <>
      <SectionHead kicker="Student Status" title="Verification" />
      {verification.loading ? <Loading label="Loading verification" rows={1} /> : null}
      {verification.error ? <ErrorBox error={verification.error} onRetry={verification.reload} /> : null}
      {status ? (
        <Panel>
          <div className="banner-top">
            <Eyebrow>CURRENT STATUS</Eyebrow>
            <StatusBadge status={status.status} />
          </div>
          <h3 className="panel-title">{status.status === 'verified' ? 'Verified student' : 'Verification open'}</h3>
          <div className="detail-row">
            <span>Method</span>
            <b>{status.method || 'Not submitted'}</b>
          </div>
          <div className="detail-row">
            <span>Submitted</span>
            <b>{dateTime(status.submittedAt)}</b>
          </div>
          <div className="detail-row">
            <span>Reviewed</span>
            <b>{dateTime(status.reviewedAt)}</b>
          </div>
          {status.rejectionReason ? (
            <InlineMessage tone="error">{status.rejectionReason}</InlineMessage>
          ) : null}
        </Panel>
      ) : null}

      {!user?.profileComplete ? (
        <InlineMessage tone="info">
          Complete your profile first: college, course, year of study and student ID are required
          before verification.
        </InlineMessage>
      ) : null}
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}

      {status?.status !== 'verified' && status?.canResubmit !== false ? (
        <Panel>
          <Eyebrow>SUBMIT VERIFICATION</Eyebrow>
          <Field label="Method">
            <select value={method} onChange={(event) => setMethod(event.target.value)}>
              <option value="roster">Eligibility roster match</option>
              <option value="college_email">Institutional email</option>
              <option value="document">Student document</option>
            </select>
          </Field>
          {method === 'college_email' ? (
            <Field label="Institutional email" hint="Must use an accepted college domain.">
              <input
                type="email"
                value={institutionEmail}
                onChange={(event) => setInstitutionEmail(event.target.value)}
                placeholder="you@college.ac.in"
              />
            </Field>
          ) : null}
          {method === 'document' ? (
            <Field label="Document" hint="JPEG, PNG or PDF up to 3 MB.">
              <input
                type="file"
                accept="image/jpeg,image/png,application/pdf"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
            </Field>
          ) : null}
          {method === 'roster' ? (
            <p className="muted">
              The roster check matches your student ID or email against the imported eligibility
              list. If there is no match, the organisers review it manually.
            </p>
          ) : null}
          <Button onClick={submit} disabled={busy === 'submit' || !user?.profileComplete} icon={ShieldCheck}>
            {busy === 'submit' ? 'Submitting' : 'Submit verification'}
          </Button>
        </Panel>
      ) : null}

      {status?.method === 'college_email' && status?.status === 'pending' ? (
        <Panel>
          <Eyebrow>EMAIL CONFIRMATION</Eyebrow>
          <p className="muted">Enter the six-digit code sent to your institutional address.</p>
          <Field label="Confirmation code">
            <input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" maxLength={8} />
          </Field>
          <Button onClick={confirm} disabled={busy === 'confirm' || code.length < 4} icon={BadgeCheck}>
            {busy === 'confirm' ? 'Confirming' : 'Confirm email'}
          </Button>
        </Panel>
      ) : null}
    </>
  );
}

export function PortalProfile() {
  const profile = useAsync(() => authApi.profile(), []);
  const sessions = useAsync(() => authApi.sessions(), []);
  const { user, reload, logout } = useAuth();
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
        collegeName: data.collegeName || '',
        universityName: data.universityName || '',
        course: data.course || '',
        branch: data.branch || '',
        yearOfStudy: data.yearOfStudy || '',
        studentIdentifier: '',
        institutionEmail: data.institutionEmail || '',
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
        collegeName: form.collegeName,
        universityName: form.universityName,
        course: form.course,
        branch: form.branch,
        yearOfStudy: form.yearOfStudy ? Number(form.yearOfStudy) : null,
        institutionEmail: form.institutionEmail || null,
      };
      if (form.studentIdentifier) payload.studentIdentifier = form.studentIdentifier;
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
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
      <Panel>
        <form className="profile-form" onSubmit={save}>
          <FieldGrid>
            <Field label="Full name">
              <input value={form.fullName} onChange={(event) => update('fullName', event.target.value)} required />
            </Field>
            <Field label="Phone" hint="International format, e.g. +919876543210">
              <input value={form.phone} onChange={(event) => update('phone', event.target.value)} />
            </Field>
            <Field label="College">
              <input value={form.collegeName} onChange={(event) => update('collegeName', event.target.value)} />
            </Field>
            <Field label="University">
              <input value={form.universityName} onChange={(event) => update('universityName', event.target.value)} />
            </Field>
            <Field label="Course">
              <input value={form.course} onChange={(event) => update('course', event.target.value)} />
            </Field>
            <Field label="Branch">
              <input value={form.branch} onChange={(event) => update('branch', event.target.value)} />
            </Field>
            <Field label="Year of study">
              <input
                type="number"
                min="1"
                max="6"
                value={form.yearOfStudy}
                onChange={(event) => update('yearOfStudy', event.target.value)}
              />
            </Field>
            <Field
              label="Student ID"
              hint={profile.data?.data?.studentIdentifierLast4 ? `Saved ending ${profile.data.data.studentIdentifierLast4}` : 'Required for verification'}
            >
              <input
                value={form.studentIdentifier}
                onChange={(event) => update('studentIdentifier', event.target.value)}
                placeholder="Leave blank to keep the saved value"
              />
            </Field>
            <Field label="Institutional email">
              <input
                type="email"
                value={form.institutionEmail}
                onChange={(event) => update('institutionEmail', event.target.value)}
              />
            </Field>
          </FieldGrid>
          <p className="muted">Email {profile.data?.data?.email} is the signed-in identity and cannot be edited here.</p>
          <Button busy={busy === 'save'} type="submit" disabled={busy === 'save'} icon={Check}>
            {busy === 'save' ? 'Saving' : 'Save profile'}
          </Button>
        </form>
      </Panel>

      <Panel>
        <Eyebrow>ACTIVE SESSIONS</Eyebrow>
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
        <Button
          variant="ghost"
          onClick={async () => {
            await logout();
            navigate('/');
          }}
          icon={LogOut}
        >
          Sign out of this device
        </Button>
      </Panel>
    </>
  );
}
