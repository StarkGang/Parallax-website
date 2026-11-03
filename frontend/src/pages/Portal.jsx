import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
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
import { authApi, portalApi, publicApi } from '../lib/api.js';
import { ISTE, LOGO, NSSCE } from './Public.jsx';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { date, dateTime, dayLabel, initials, money, percent } from '../lib/format.js';
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
  useAsync,
} from '../components/ui.jsx';

const PORTAL_NAV = [
  ['Overview', '/portal', true],
  ['Pass', '/portal/pass'],
  ['Select events', '/portal/select-events'],
  ['Registrations', '/portal/registrations'],
  ['Tickets', '/portal/tickets'],
  ['Teams', '/portal/teams'],
  ['Verification', '/portal/verification'],
  ['Profile', '/portal/profile'],
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
  return new Promise((resolve, reject) => {
    const checkout = new Razorpay({
      key: order.razorpayKeyId,
      order_id: order.gatewayOrderId,
      amount: order.amountPaise,
      currency: 'INR',
      name: 'Parallax',
      description: 'Convention pass',
      prefill: { email: user?.email, name: user?.fullName },
      theme: { color: '#38bdf8' },
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
  const { user, logout, isStaff } = useAuth();
  const { edition } = useSite();
  const navigate = useNavigate();

  const signOut = async () => {
    await logout();
    navigate('/');
  };

  return (
    <>
      <PageTitle
        kicker="Attendee Portal"
        title="Your Convention Passes & Bookings"
        desc={`Signed in as ${user?.email} · Live bookings, selections, and entry tickets for ${edition.name}.`}
        aside={
          <div className="title-badges">
            <Badge tone={user?.studentVerified ? 'good' : 'muted'}>
              {user?.studentVerified ? 'Student verified' : 'Verification open'}
            </Badge>
            {user?.profileComplete ? <Badge tone="accent">Profile complete</Badge> : null}
            {isStaff ? (
              <Link to="/manage" className="button ghost small" style={{ fontSize: 11, padding: '4px 8px' }}>
                Staff Console →
              </Link>
            ) : null}
          </div>
        }
      />

      {/* Swipeable Horizontal Tabs on Mobile */}
      <div className="section" style={{ paddingBottom: 0, paddingTop: 10 }}>
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
          <span className="pill">{user?.studentVerified ? 'Verified student' : 'Student check pending'}</span>
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
          <Outlet />
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
        <Button to="/portal/pass" icon={ArrowRight}>
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
            {!passData
              ? 'Buy your convention pass'
              : !selection?.valid
                ? 'Complete your included selection'
                : verificationStatus?.status !== 'verified'
                  ? 'Finish student verification'
                  : 'You are ready for the convention'}
          </h3>
          <p>
            {!passData
              ? 'The pass is mandatory and includes lunch, entry and the included-event allowance.'
              : !selection?.valid
                ? selection?.message || 'Choose included events within the published allowance.'
                : verificationStatus?.status !== 'verified'
                  ? 'Verification confirms your student status for the convention record.'
                  : 'Your pass, selections and ticket are all active.'}
          </p>
          <Button
            to={
              !passData
                ? '/portal/pass'
                : !selection?.valid
                  ? '/portal/select-events'
                  : verificationStatus?.status !== 'verified'
                    ? '/portal/verification'
                    : '/portal/tickets'
            }
            icon={ArrowRight}
          >
            Continue
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
            <b>{verificationStatus?.status || 'unverified'}</b>
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

  useEffect(() => {
    if (!selection) return;
    setSelected(selection.selections.filter((item) => item.selected).map((item) => item.eventId));
  }, [selection?.passId, selection?.count, selection?.valuePaise]);

  const options = selection?.selections || [];
  const required = selection?.requiredCount ?? policy?.includedEventCount ?? 0;
  const mode = selection?.mode || policy?.includedSelectionMode || 'up_to';
  const cap = selection?.capPaise ?? policy?.includedValueCapPaise ?? 0;
  const value = options
    .filter((item) => selected.includes(item.eventId))
    .reduce((sum, item) => sum + item.baseValuePaise, 0);

  const withinCap = selection?.capInclusive === false ? value < cap : value <= cap;
  const withinCount = mode === 'exact' ? selected.length === required : selected.length <= required;
  const valid = withinCap && withinCount;

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
    const next = selected.includes(eventId)
      ? selected.filter((id) => id !== eventId)
      : [...selected, eventId];
    const nextValue = options
      .filter((item) => next.includes(item.eventId))
      .reduce((sum, item) => sum + item.baseValuePaise, 0);
    if (mode === 'exact' ? next.length > required : next.length > required) {
      setMessage({ tone: 'error', text: `You can include ${mode === 'exact' ? 'exactly' : 'up to'} ${required} events.` });
      return;
    }
    const capOk = selection?.capInclusive === false ? nextValue < cap : nextValue <= cap;
    if (!capOk) {
      setMessage({ tone: 'error', text: `That choice would exceed the ${money(cap)} base-value cap.` });
      return;
    }
    setMessage(null);
    setSelected(next);
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
      }
      setAddons([]);
      await Promise.all([regs.reload(), pass.reload()]);
      setMessage({
        tone: 'success',
        text: order
          ? `Add-on registrations confirmed. Your tickets are ready.`
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
        <Button to="/portal/pass" icon={ArrowRight}>
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
      <div className="choice-list">
        {options.map((event) => (
          <label className={`choice ${selected.includes(event.eventId) ? 'is-selected' : ''}`.trim()} key={event.eventId}>
            <input
              type="checkbox"
              checked={selected.includes(event.eventId)}
              onChange={() => toggle(event.eventId)}
              disabled={selection?.locked}
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
              <small>Add-on {money(event.addonPricePaise)}</small>
            </span>
          </label>
        ))}
      </div>
      <div className="save-row">
        <Button onClick={save} disabled={busy === 'save' || selection?.locked} icon={Check}>
          {busy === 'save' ? 'Saving' : 'Save included selections'}
        </Button>
        <span className={valid ? 'valid-note' : 'invalid-note'}>
          {valid
            ? 'Within the allowance'
            : mode === 'exact' && selected.length === required
              ? 'Value exceeds the cap'
              : `Choose ${mode === 'exact' ? 'exactly' : 'up to'} ${required} events within ${money(cap)}`}
        </span>
      </div>

      <h2 className="section-sub">Additional paid events</h2>
      <p className="muted">
        Each add-on is charged at its published fee after the pass. The pass is never replaced.
      </p>
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
        <Button onClick={registerAddons} disabled={!addons.length || busy === 'addons'} icon={ArrowRight}>
          {busy === 'addons' ? 'Registering' : 'Register selected add-ons'}
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
  const regs = useAsync(() => portalApi.registrations(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const [confirm, setConfirm] = useState(null);
  const [message, setMessage] = useState(null);
  const rows = regs.data?.data || [];

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
                {row.kind}
              </small>
            </div>
            <span className="reg-fee">{money(row.feePaise)}</span>
            <StatusBadge status={row.status} />
            {row.status !== 'cancelled' ? (
              <button className="table-action" onClick={() => setConfirm(row)}>
                Cancel
              </button>
            ) : null}
          </div>
        ))}
      </div>
      <Sheet open={Boolean(confirm)} title="Cancel registration" onClose={() => setConfirm(null)}>
        <p className="muted">
          Cancel the registration for <b>{confirm?.eventTitle}</b>? Add-on fees already paid are
          handled by the finance team, not automatically.
        </p>
        <div className="sheet-actions">
          <Button variant="ghost" onClick={() => setConfirm(null)}>
            Keep it
          </Button>
          <Button onClick={() => cancel(confirm.id)}>Cancel registration</Button>
        </div>
      </Sheet>
    </>
  );
}

export function PortalTickets() {
  const { user } = useAuth();
  const { edition, editionId } = useSite();
  const tickets = useAsync(() => portalApi.tickets(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const profile = useAsync(() => authApi.profile(), [], { enabled: Boolean(user) });
  const [message, setMessage] = useState(null);
  const rows = tickets.data?.data || [];
  const prof = profile.data?.data || {};

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

  const downloadQr = async (ticket) => {
    try {
      const url = portalApi.ticketQrUrl(editionId, ticket.id);
      const res = await fetch(url);
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `parallax-pass-${ticket.token}.svg`;
      a.click();
      URL.revokeObjectURL(a.href);
      setMessage({ tone: 'success', text: 'Pass QR code downloaded.' });
    } catch {
      setMessage({ tone: 'error', text: 'Could not download QR code.' });
    }
  };

  return (
    <>
      <SectionHead
        kicker="Entry Credentials"
        title="Your official convention pass"
        action={
          rows.length ? (
            <Button variant="light" onClick={printBadge} icon={Printer}>
              Print / Save pass
            </Button>
          ) : null
        }
      />
      {message ? <InlineMessage tone={message.tone}>{message.text}</InlineMessage> : null}
      {tickets.loading ? <Loading label="Loading tickets" rows={2} /> : null}
      {tickets.error ? <ErrorBox error={tickets.error} onRetry={tickets.reload} /> : null}
      {!tickets.loading && !rows.length ? (
        <Empty title="No ticket issued yet" desc="Tickets are issued when a pass or paid registration activates.">
          <Button to="/portal/pass" icon={ArrowRight}>
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
              <div className="badge-brand-row">
                <img src={LOGO} alt="Parallax" className="badge-logo" />
                <div className="badge-brand-text">
                  <span className="badge-super">{edition?.name || 'PARALLAX 2026'}</span>
                  <span className="badge-sub">{edition?.organizer || 'ISTE STATE STUDENT CONVENTION'}</span>
                </div>
                <img src={ISTE} alt="ISTE" className="badge-host-logo" />
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

            {/* Core QR Matrix Box */}
            <div className="badge-qr-box">
              <div className="qr-reticle reticle-tl" />
              <div className="qr-reticle reticle-tr" />
              <div className="qr-reticle reticle-bl" />
              <div className="qr-reticle reticle-br" />
              <div className="qr-matrix-surface">
                <img
                  src={portalApi.ticketQrUrl(editionId, ticket.id)}
                  alt={`QR entry pass for ${ticket.title}`}
                  className="qr-img"
                  width="200"
                  height="200"
                />
              </div>
              <span className="qr-scan-hint">SCAN FOR GATE ENTRY · DAY 1 & 2</span>
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
                  <b>04 - 05 NOV 2026</b>
                </div>
              </div>
              <div className="logistics-cell">
                <Utensils size={13} />
                <div>
                  <span className="cell-lbl">MEALS</span>
                  <b>LUNCH INCLUDED</b>
                </div>
              </div>
              <div className="logistics-cell full-width">
                <MapPin size={13} />
                <div>
                  <span className="cell-lbl">VENUE & CHECK-IN</span>
                  <b>NSSCE CAMPUS, PALAKKAD</b>
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
    </>
  );
}

export function PortalTeams() {
  const { editionId, slug, policy } = useSite();
  const teams = useAsync(() => portalApi.teams(editionId), [editionId], { enabled: Boolean(editionId) });
  const catalogue = useAsync(() => publicApi.events(slug, { format: 'team', pageSize: 100 }), [slug], {
    enabled: Boolean(slug),
  });
  const [form, setForm] = useState({ eventId: '', name: '' });
  const [joinCode, setJoinCode] = useState('');
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState('');

  const teamEvents = catalogue.data?.data || [];
  const rows = teams.data?.data || [];

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
                  {team.members.length} / {team.maxSize} members · {team.status}
                </p>
              </div>
              {team.isLeader ? <Badge tone="accent">You lead</Badge> : <Badge>Member</Badge>}
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
            {team.inviteCode ? (
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
            <Button
              variant="ghost"
              onClick={() =>
                run(`leave-${team.id}`, () => portalApi.leaveTeam(editionId, team.id), 'You left the team.')
              }
              disabled={busy === `leave-${team.id}`}
            >
              Leave team
            </Button>
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
        action={<StatusBadge status={user?.profileComplete ? 'complete' : 'incomplete'} />}
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
