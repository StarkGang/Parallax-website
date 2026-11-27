import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Copy,
  CreditCard,
  Link2,
  Lock,
  Plus,
  RefreshCw,
  Share2,
  Ticket,
  Users,
} from 'lucide-react';
import { portalApi, publicApi } from '../lib/api.js';
import { resolveImageUrl } from '../lib/imageUrl.js';
import { EventGeneratedPoster } from '../components/EventGeneratedPoster.jsx';
import {
  EventsColumnsPicker,
  useEventGridColumns,
} from '../components/EventsColumnsPicker.jsx';
import { payOrder } from '../lib/pay.js';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { date, money } from '../lib/format.js';
import {
  Badge,
  Button,
  Empty,
  ErrorBox,
  Feedback,
  InlineMessage,
  Loading,
  SectionHead,
  Sheet,
  useAsync,
} from '../components/ui.jsx';
import './Worklist.css';
import './EventCard.css';

const EVENT_FRAME = `${import.meta.env.BASE_URL}images/event_frame.png`;
const PLAN_BG_CORE = `${import.meta.env.BASE_URL}images/parallax-bg-core.webp`;
const PLAN_BG_VAULT = `${import.meta.env.BASE_URL}images/parallax-bg-vault.webp`;
const PLAN_BG_PEDESTAL = `${import.meta.env.BASE_URL}images/parallax-bg-pedestal.webp`;
const PLAN_DEPTH_BG = `${import.meta.env.BASE_URL}images/parallax-depth-bg.webp`;

function planBackdrop(row) {
  const cat = `${row.categorySlug || ''} ${row.category || ''}`.toLowerCase();
  if (cat.includes('comput') || cat.includes('code')) return PLAN_BG_CORE;
  if (cat.includes('electr')) return PLAN_BG_VAULT;
  if (cat.includes('robot') || cat.includes('engin')) return PLAN_BG_PEDESTAL;
  if (cat.includes('design')) return PLAN_BG_VAULT;
  return PLAN_DEPTH_BG;
}

function pricePill(row) {
  if (row.state === 'confirmed') {
    return <span className="wl-pill included">Confirmed</span>;
  }
  if (row.state === 'team_included') {
    return <span className="wl-pill included">Included with pass</span>;
  }
  if (row.state === 'team_leader') {
    return <span className="wl-pill included">You're the team leader</span>;
  }
  if (row.state === 'team_member') {
    return <span className="wl-pill neutral">On a team</span>;
  }
  if (row.state === 'team_unpaid' || row.state === 'solo_unpaid' || row.state === 'addon_unpaid') {
    return <span className="wl-pill due">Payment pending</span>;
  }
  if (row.state === 'included_possible') {
    return <span className="wl-pill included">Included with your pass</span>;
  }
  if (row.state === 'free' || row.price?.duePaise === 0) {
    return <span className="wl-pill free">Free</span>;
  }
  if (row.state === 'solo') {
    return <span className="wl-pill neutral">Individual entry</span>;
  }
  return <span className="wl-pill due">{money(row.price?.duePaise || 0)} due</span>;
}

function formatLabel(row) {
  const team = row.format === 'team';
  return (
    <span className={`wl-format ${team ? 'team' : 'solo'}`}>
      {team ? 'Team' : 'Individual'}
    </span>
  );
}


const PortalPlanCard = memo(function PortalPlanCard({
  row,
  selected,
  blocked,
  busy,
  onToggle,
  onPay,
  team,
}) {
  const navigate = useNavigate();
  const title = row.title || 'Untitled event';
  const detailPath = `/portal/events/${row.slug}`;
  const confirmed = row.seat?.status === 'confirmed';
  const due = Number(row.price?.duePaise || 0);
  const listPaise = Number(row.price?.listPaise || 0);
  const inBasket = selected;
  const isTeam = row.format === 'team';
  const canAdd = (row.actions || []).includes('add');
  const canPay = (row.actions || []).includes('pay') && row.payment;
  const canTicket = (row.actions || []).includes('ticket');
  const stateLabel = confirmed
    ? 'Confirmed'
    : inBasket
      ? 'On your list'
      : row.state === 'included_possible'
        ? 'Covered by your pass'
        : due > 0
          ? 'Extra payment only'
          : 'No charge';

  const open = (clickEvent) => {
    if (clickEvent.defaultPrevented) return;
    if (clickEvent.button !== 0) return;
    if (clickEvent.metaKey || clickEvent.ctrlKey || clickEvent.shiftKey || clickEvent.altKey) return;
    if (clickEvent.target.closest('a, button')) return;
    navigate(detailPath);
  };

  return (
    <article
      className={`exc wl-plan-card${inBasket ? ' is-selected' : ''}`}
      onClick={open}
      data-accent={row.categorySlug || undefined}
    >
      <div className="exc-poster">
        {row.bannerUrl ? (
          <img
            src={resolveImageUrl(row.bannerUrl, 960)}
            alt=""
            className="exc-poster-img"
            referrerPolicy="no-referrer"
            loading="lazy"
            decoding="async"
            width={480}
            height={320}
          />
        ) : (
          <EventGeneratedPoster event={row} />
        )}
      </div>

      <img
        className="exc-frame"
        src={EVENT_FRAME}
        alt=""
        aria-hidden="true"
        draggable="false"
        decoding="async"
      />

      <div className="exc-panel">
        <p className="exc-eyebrow">
          <span className="exc-dot" aria-hidden="true" />
          <span>{row.category || 'Event'}</span>
          <span className="exc-sep" aria-hidden="true">/</span>
          <span>
            {isTeam
              ? `Team of ${row.team?.minSize ?? 2}–${row.team?.maxSize ?? 4}`
              : 'Individual entry'}
          </span>
        </p>
        <h3 className={`exc-title${title.length > 20 ? ' is-long' : ''}`}>{title}</h3>
      </div>

      <div className="exc-actions">
        <Link className="exc-action" to={detailPath} aria-label={`Open details for ${title}`}>
          <span>Details</span>
          <ArrowUpRight size={11} strokeWidth={2.2} aria-hidden="true" />
        </Link>
        {canPay ? (
          <button
            type="button"
            className="exc-action is-primary"
            onClick={() => onPay(row)}
            disabled={busy === `pay-${row.eventId}`}
          >
            <span>{busy === `pay-${row.eventId}` ? 'Paying' : `Pay ${money(row.payment.amountPaise)}`}</span>
            <ArrowRight size={11} strokeWidth={2.4} aria-hidden="true" />
          </button>
        ) : canTicket ? (
          <Link className="exc-action is-primary" to="/portal/registration">
            <span>Ticket</span>
            <ArrowRight size={11} strokeWidth={2.4} aria-hidden="true" />
          </Link>
        ) : inBasket ? (
          <button
            type="button"
            className="exc-action"
            onClick={() => onToggle(row)}
          >
            <span>Remove</span>
            <Check size={11} strokeWidth={2.4} aria-hidden="true" />
          </button>
        ) : (
          <button
            type="button"
            className="exc-action is-primary"
            onClick={() => onToggle(row)}
            disabled={blocked || !canAdd}
          >
            <span>Add event</span>
            <Plus size={11} strokeWidth={2.4} aria-hidden="true" />
          </button>
        )}
      </div>

      <p className="exc-plaque">
        <b>
          {row.price?.basis === 'included' ? (
            listPaise > 0 ? (
              <>
                <s className="exc-was">{money(listPaise)}</s>
                ₹0
              </>
            ) : (
              'Included with pass'
            )
          ) : due > 0 ? (
            <>
              {listPaise > due ? <s className="exc-was">{money(listPaise)}</s> : null}
              {`${money(due)} due`}
            </>
          ) : (
            'Free'
          )}
        </b>
        <span aria-hidden="true">·</span>
        <span className="exc-open">{stateLabel}</span>
      </p>
    </article>
  );
});

function EventRow({
  row,
  index,
  selected,
  blocked,
  busy,
  onToggle,
  onPay,
  onRemove,
  onTeam,
  team,
  onCreate,
  onJoin,
}) {
  const inBasket = selected;
  const teamVisible = row.format === 'team' || team;
  const isLeader = Boolean(team?.isLeader);

  return (
    <article className={`wl-row wl-card ${inBasket ? 'is-in-basket' : ''}`}>
      <span className="wl-index" aria-hidden="true">
        {String((index ?? 0) + 1).padStart(2, '0')}
      </span>

      <div className="wl-title">
        <div className="wl-title-row">
          <Link to={`/portal/events/${row.slug}`} className="wl-title-link">
            <b>{row.title}</b>
          </Link>
          {formatLabel(row)}
          {team ? <Badge tone="accent">{team.name}</Badge> : null}
        </div>
        <div className="wl-meta">
          <span>{row.category}</span>
          {row.startsAt ? (
            <>
              <i />
              <span>{date(row.startsAt)}</span>
            </>
          ) : null}
          {row.venue ? (
            <>
              <i />
              <span>{row.venue}</span>
            </>
          ) : null}
          {row.format === 'team' ? (
            <>
              <i />
              <span>
                {team?.memberCount ?? row.team?.memberCount ?? 0} /{' '}
                {team?.maxSize ?? row.team?.maxSize ?? row.team_max_size ?? 4} members
              </span>
            </>
          ) : null}
          {row.seat?.reservationExpiresAt ? (
            <>
              <i />
              <span>Place held until {date(row.seat.reservationExpiresAt)}</span>
            </>
          ) : null}
        </div>
        {row.summary ? <p className="wl-card-summary">{row.summary}</p> : null}
        {teamVisible && (row.seat || team) ? (
          <div className="wl-team-strip">
            <span>
              {team ? (
                <>
                  Team <b>{team.name}</b>
                  {isLeader ? ' — you lead' : ` — led by ${team.members?.find((m) => m.isLeader)?.fullName || 'a teammate'}`}
                </>
              ) : (
                <>
                  <b>No team yet</b> — you can enter on your own and form a team later
                </>
              )}
            </span>
            <span className="wl-strip-actions">
              {team ? (
                <Button size="small" variant="ghost" icon={Users} onClick={() => onTeam(row)}>
                  Open team
                </Button>
              ) : (
                <>
                  <Button size="small" variant="light" icon={Plus} onClick={() => onCreate(row)}>
                    Create a team
                  </Button>
                  <Button size="small" variant="ghost" icon={Link2} onClick={() => onJoin(row)}>
                    Join with a code
                  </Button>
                </>
              )}
            </span>
          </div>
        ) : null}
      </div>

      <div className="wl-price">
        {pricePill(row)}
        <small>
          {row.price?.basis === 'included' && row.price?.listPaise
            ? `${money(row.price.listPaise)} value · covered by your pass`
            : row.price?.duePaise > 0
              ? 'only the extra is charged'
              : 'no charge'}
        </small>
      </div>

      <div className="wl-actions">
        {!row.seat && (row.actions || []).includes('add') ? (
          <Button
            size="small"
            variant={inBasket ? 'ghost' : 'light'}
            icon={inBasket ? Check : Plus}
            onClick={() => onToggle(row)}
            disabled={blocked || busy === `toggle-${row.eventId}`}
          >
            {busy === `toggle-${row.eventId}`
              ? 'Saving'
              : inBasket
                ? 'Remove event'
                : 'Add event'}
          </Button>
        ) : null}
        {(row.actions || []).includes('pay') && row.payment ? (
          <Button
            size="small"
            icon={CreditCard}
            onClick={() => onPay(row)}
            disabled={busy === `pay-${row.eventId}`}
          >
            {busy === `pay-${row.eventId}` ? 'Paying' : `Pay ${money(row.payment.amountPaise)}`}
          </Button>
        ) : null}
        {(row.actions || []).includes('ticket') ? (
          <Button size="small" variant="ghost" icon={Ticket} to="/portal/registration">
            Ticket
          </Button>
        ) : null}
        {(row.actions || []).includes('remove') ? (
          <Button
            size="small"
            variant="ghost"
            onClick={() => onRemove(row)}
            disabled={busy === `remove-${row.eventId}`}
          >
            Remove event
          </Button>
        ) : null}
        {!row.seat && row.state === 'available' && row.price?.duePaise > 0 ? null : null}
      </div>
    </article>
  );
}

export function PortalWorklist() {
  const { editionId, slug, policy } = useSite();
  const { user } = useAuth();
  useEffect(() => {
    try {
      localStorage.setItem('px_visited_events_portal', '1');
    } catch {}
  }, []);
  const [params, setParams] = useSearchParams();
  const data = useAsync(() => portalApi.worklist(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const teams = useAsync(() => portalApi.teams(editionId), [editionId], {
    enabled: Boolean(editionId),
  });

  const payload = data.data?.data;
  const rows = useMemo(() => payload?.rows || [], [payload]);
  const allowance = payload?.allowance || {};
  const gate = payload?.gate || '';
  const policyAddon = policy?.addonRequiresPass;

  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [removeRow, setRemoveRow] = useState(null);
  const [createRow, setCreateRow] = useState(null);
  const [joinRow, setJoinRow] = useState(null);
  const [teamRow, setTeamRow] = useState(null);
  const [teamName, setTeamName] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const { activeCols, colOptions, handleColsChange } = useEventGridColumns(
    'parallax.portal.events.cols.v1',
  );
  const quoteKeys = useRef({});

  const [optimisticSelected, setOptimisticSelected] = useState({});
  const desiredMapRef = useRef(new Map());
  const flushTimerRef = useRef(null);
  const flushChainRef = useRef(Promise.resolve());

  // The basket is server state, shared with the event rooms. Optimistic
  // overrides layer on top for 0ms UI feedback and coalesce rapid clicks.
  const basket = payload?.basket || null;
  const basketLines = useMemo(
    () => (basket?.lines || []).filter((line) => line.action === 'create'),
    [basket],
  );
  const serverSelected = useMemo(
    () => basketLines.map((line) => line.eventId),
    [basketLines],
  );
  const serverSelectedSet = useMemo(() => new Set(serverSelected), [serverSelected]);
  const selectedSet = useMemo(() => {
    const next = new Set(serverSelected);
    for (const [eventId, want] of Object.entries(optimisticSelected)) {
      if (want) next.add(eventId);
      else next.delete(eventId);
    }
    return next;
  }, [serverSelected, optimisticSelected]);
  const selected = useMemo(() => Array.from(selectedSet), [selectedSet]);
  const quote = basket?.quoteId ? basket : null;

  const serverSelectedRef = useRef(serverSelectedSet);
  serverSelectedRef.current = serverSelectedSet;
  const selectedSetRef = useRef(selectedSet);
  selectedSetRef.current = selectedSet;

  useEffect(() => {
    return () => {
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    };
  }, []);

  const teamsByEvent = useMemo(() => {
    const map = {};
    for (const team of teams.data?.data || []) map[team.eventId] = team;
    return map;
  }, [teams.data]);

  const selectedRows = useMemo(
    () => rows.filter((row) => selectedSet.has(row.eventId)),
    [rows, selectedSet],
  );
  const due = quote?.duePaise || 0;

  const visible = useMemo(
    () =>
      rows.filter((row) => {
        if (row.seat?.status === 'confirmed') {
          return false;
        }
        if (search) {
          const needle = search.toLowerCase();
          if (
            !`${row.title} ${row.category} ${row.summary || ''}`.toLowerCase().includes(needle)
          ) {
            return false;
          }
        }
        if (filter === 'free') {
          return row.price?.duePaise === 0 || row.state === 'free' || row.state === 'included_possible';
        }
        if (filter === 'due') {
          return row.price?.duePaise > 0 || row.state === 'addon_unpaid' || row.state === 'team_unpaid';
        }
        if (filter === 'selected') {
          return Boolean(row.seat) || selectedSet.has(row.eventId);
        }
        return true;
      }),
    [rows, search, filter, selectedSet],
  );

  const individualRows = useMemo(
    () => visible.filter((row) => row.format !== 'team'),
    [visible],
  );
  const teamRows = useMemo(
    () => visible.filter((row) => row.format === 'team'),
    [visible],
  );

  const reloadAll = useCallback(async () => {
    await Promise.all([data.reload(), teams.reload()]);
  }, [data, teams]);

  const flushBasketQueue = useCallback(() => {
    flushChainRef.current = flushChainRef.current.then(async () => {
      const pending = Array.from(desiredMapRef.current.entries());
      desiredMapRef.current.clear();
      if (!pending.length) return;

      const serverSet = serverSelectedRef.current;
      const toAdd = [];
      const toRemove = [];
      for (const [eventId, want] of pending) {
        if (want && !serverSet.has(eventId)) toAdd.push(eventId);
        else if (!want && serverSet.has(eventId)) toRemove.push(eventId);
      }

      if (!toAdd.length && !toRemove.length) {
        setOptimisticSelected((prev) => {
          const next = { ...prev };
          for (const [eventId] of pending) delete next[eventId];
          return next;
        });
        return;
      }

      try {
        let latestBasket = null;
        if (toAdd.length) {
          const res = await portalApi.addToBasket(editionId, toAdd);
          latestBasket = res?.data || latestBasket;
        }
        for (const eventId of toRemove) {
          const res = await portalApi.removeFromBasket(editionId, eventId);
          latestBasket = res?.data || latestBasket;
        }

        if (latestBasket) {
          data.setData((prev) =>
            prev?.data
              ? { ...prev, data: { ...prev.data, basket: latestBasket } }
              : prev,
          );
        }

        // If no more clicks arrived while requests were in flight, sync full
        // allowance & per-row pricing once in the background.
        if (desiredMapRef.current.size === 0) {
          const fresh = await portalApi.worklist(editionId);
          if (desiredMapRef.current.size === 0 && fresh) {
            data.setData(fresh);
          }
        }

        setOptimisticSelected((prev) => {
          const next = { ...prev };
          for (const [eventId] of pending) {
            if (!desiredMapRef.current.has(eventId)) delete next[eventId];
          }
          return next;
        });
      } catch (error) {
        setOptimisticSelected((prev) => {
          const next = { ...prev };
          for (const [eventId] of pending) {
            if (!desiredMapRef.current.has(eventId)) delete next[eventId];
          }
          return next;
        });
        setMessage({ tone: 'error', text: error.message });
      }
    });
  }, [editionId, data]);

  const toggle = useCallback(
    (row) => {
      if (row.seat) {
        setMessage({
          tone: 'info',
          text: 'This event is already confirmed on your list. Remove it first to change it.',
        });
        return;
      }
      const nextWant = !selectedSetRef.current.has(row.eventId);
      setMessage(null);
      setOptimisticSelected((prev) => ({ ...prev, [row.eventId]: nextWant }));
      desiredMapRef.current.set(row.eventId, nextWant);

      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
      flushTimerRef.current = setTimeout(() => {
        flushTimerRef.current = null;
        flushBasketQueue();
      }, 80);
    },
    [flushBasketQueue],
  );

  const payRow = useCallback(
    async (row) => {
      setBusy(`pay-${row.eventId}`);
      setMessage(null);
      try {
        const outcome = await payOrder(editionId, row.payment, user, row.title);
        if (outcome.status === 'paid') {
          await reloadAll();
          setMessage({ tone: 'success', text: 'Payment confirmed. Your place and ticket are ready.' });
        } else if (outcome.status === 'cancelled') {
          setMessage({
            tone: 'info',
            text: 'Payment cancelled. Your place is still held until the hold expires.',
          });
        } else {
          setMessage({ tone: 'error', text: outcome.message || 'Payment failed.' });
        }
      } catch (error) {
        setMessage({ tone: 'error', text: error.message });
      } finally {
        setBusy('');
      }
    },
    [editionId, user, reloadAll],
  );

  const checkout = async () => {
    if (!quote) return;
    setBusy('checkout');
    setMessage(null);
    try {
      const key =
        quoteKeys.current[quote.quoteId] ||
        (quoteKeys.current[quote.quoteId] = `wl-${quote.quoteId}-${Date.now()}`);
      const body = await portalApi.checkout(editionId, quote.quoteId, key);
      const order = body.data?.order;
      if (order) {
        const outcome = await payOrder(
          editionId,
          order,
          user,
          `Event basket (${selectedRows.length} events)`,
        );
        if (outcome.status !== 'paid') {
          setMessage({
            tone: outcome.status === 'cancelled' ? 'info' : 'error',
            text:
              outcome.status === 'cancelled'
                ? 'Payment cancelled. Your places are held until the hold expires.'
                : outcome.message || 'Payment failed.',
          });
          await reloadAll();
          return;
        }
      }
      setReviewOpen(false);
      await reloadAll();
      setMessage({
        tone: 'success',
        text: order
          ? 'Extra payment received. Your places and tickets are ready.'
          : 'Places confirmed. Your tickets are ready.',
      });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
      await reloadAll();
    } finally {
      setBusy('');
    }
  };

  const askRemove = (row) => {
    setRemoveRow(row);
  };

  const doRemove = async () => {
    if (!removeRow) return;
    setBusy(`remove-${removeRow.eventId}`);
    setMessage(null);
    try {
      const result = await portalApi.removeEvent(editionId, removeRow.eventId);
      const body = result.data || {};
      await reloadAll();
      setRemoveRow(null);
      if (body.refundedPaise > 0) {
        setMessage({
          tone: 'success',
          text: `${money(body.refundedPaise)} refund started to your original payment method.`,
        });
      } else {
        setMessage({ tone: 'success', text: 'Event removed. Your pass allowance is free again.' });
      }
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const openCreate = (row) => {
    setCreateRow(row);
    setTeamName(`Team ${(user?.fullName || 'Player').split(' ')[0]}`);
  };

  const createTeam = async () => {
    if (!createRow) return;
    setBusy('create-team');
    setMessage(null);
    try {
      const body = await portalApi.createTeam(editionId, {
        eventId: createRow.eventId,
        name: teamName,
      });
      const payment = body.data?.payment;
      if (payment) {
        const outcome = await payOrder(editionId, payment, user, `${createRow.title} team entry`);
        if (outcome.status !== 'paid') {
          setMessage({
            tone: outcome.status === 'cancelled' ? 'info' : 'error',
            text:
              outcome.status === 'cancelled'
                ? 'Team created. The entry is unpaid and held for you to pay from the team card.'
                : outcome.message || 'Team entry payment failed.',
          });
          setCreateRow(null);
          await reloadAll();
          return;
        }
      }
      setCreateRow(null);
      await reloadAll();
      setMessage({ tone: 'success', text: 'Team created. Share the invite link with your teammates.' });
    } catch (error) {
      if (error.code === 'SEAT_IN_BASKET') {
        setCreateRow(null);
        setMessage({ tone: 'info', text: error.message });
        return;
      }
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const openJoin = (row) => {
    setJoinRow(row);
    setJoinCode('');
  };

  const normaliseCode = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const parts = raw.split('/').filter(Boolean);
    return (parts[parts.length - 1] || raw).toUpperCase();
  };

  const joinTeam = async () => {
    if (!joinRow) return;
    setBusy('join-team');
    setMessage(null);
    try {
      const team = await portalApi.joinTeam(editionId, normaliseCode(joinCode));
      const payment = team.data?.payment;
      if (payment) {
        const outcome = await payOrder(editionId, payment, user, `${joinRow.title} team entry`);
        if (outcome.status !== 'paid') {
          setMessage({
            tone: outcome.status === 'cancelled' ? 'info' : 'error',
            text:
              outcome.status === 'cancelled'
                ? 'Joined the team. The entry is unpaid and held; pay it from the team card.'
                : outcome.message || 'Team entry payment failed.',
          });
          setJoinRow(null);
          await reloadAll();
          return;
        }
      }
      setJoinRow(null);
      await reloadAll();
      setMessage({ tone: 'success',           text: 'You joined the team. Your entry is attached — there is no second charge.' });
    } catch (error) {
      const needsPass = /pass/i.test(error.message || '');
      setMessage({
        tone: 'error',
        text: needsPass
          ? `${error.message} Get your pass, then open this invite again.`
          : error.message,
      });
    } finally {
      setBusy('');
    }
  };

  const openTeam = (row) => setTeamRow(row);

  const inviteUrl = (team) => {
    if (!team) return '';
    if (team.inviteLink) return `${window.location.origin}${team.inviteLink}`;
    if (team.inviteCode) return `${window.location.origin}/team/${team.inviteCode}`;
    return '';
  };

  const copyInvite = async (team) => {
    const url = inviteUrl(team);
    try {
      await navigator.clipboard.writeText(url);
      setMessage({ tone: 'success', text: 'Invite link copied. Anyone with it can preview the team.' });
    } catch {
      setMessage({ tone: 'info', text: url });
    }
  };

  const doLeave = async (team) => {
    setBusy(`leave-${team.id}`);
    setMessage(null);
    try {
      await portalApi.leaveTeam(editionId, team.id);
      setTeamRow(null);
      await reloadAll();
      setMessage({ tone: 'success', text: 'You left the team. If you were the leader, leadership moved to the earliest member.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const toggleLock = async (team) => {
    setBusy(`lock-${team.id}`);
    try {
      await portalApi.toggleTeamLock(editionId, team.id);
      await reloadAll();
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const rotate = async (team) => {
    setBusy(`rotate-${team.id}`);
    try {
      await portalApi.rotateInvite(editionId, team.id);
      await reloadAll();
      setMessage({ tone: 'success', text: 'A new invite code was generated. The old link no longer works.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const activeTeam = teamRow ? teamsByEvent[teamRow.eventId] : null;

  useEffect(() => {
    if (params.get('review') === '1' && quote?.quoteId) setReviewOpen(true);
  }, [params, quote?.quoteId]);
  useEffect(() => {
    const focus = params.get('event');
    if (!focus || !rows.length || busy) return;
    const row = rows.find((item) => item.slug === focus);
    if (!row || row.seat || selected.includes(row.eventId)) return;
    if (!(row.actions || []).includes('add')) return;
    toggle(row);
  }, [params, rows.length]);

  if (data.loading && !payload) return <Loading label="Loading your events" rows={3} />;
  if (data.error) return <ErrorBox error={data.error} onRetry={data.reload} />;

  const passBlocked = Boolean(gate);

  return (
    <>
      <SectionHead
        kicker="STEP 2 · CHOOSE YOUR EVENTS"
        title="Browse & Add Events"
        subtitle="Pick the events you want to take part in. Your pass covers what it can, and you pay any extra once, at the end."
      />
      <Feedback message={message} />

      <div className="wl-guide">
        <div>
          <b>Choose all your events in one place.</b> Add them here or from any event page. You
          check the total and pay once at the end.
        </div>
        <div>
          <b>Your pass includes {allowance.required ?? 0} events.</b>
          {allowance.capPaise != null
            ? ` That covers up to ${money(allowance.capPaise)} of event value.`
            : ''}{' '}
          Any extra event is charged on its own row, so adding one never fails.
        </div>
        <div>
          <b>Free events don't use your pass allowance.</b> For team events you can enter on your
          own now and create or join a team later — the price never changes.
        </div>
      </div>

      {passBlocked ? (
        <InlineMessage tone="error">
          {gate}{' '}
          <Link to="/portal/registration" style={{ textDecoration: 'underline', marginLeft: 6 }}>
            Open pass &amp; registration
          </Link>
        </InlineMessage>
      ) : null}
      {!passBlocked && policyAddon && !payload?.passStatus ? (
        <InlineMessage tone="info">
          A pass is needed before seats can be added.{' '}
          <Link to="/portal/registration" style={{ textDecoration: 'underline' }}>
            Get your pass
          </Link>
        </InlineMessage>
      ) : null}

      <div className="wl">
        <div className="wl-head">
          <div className="wl-meter">
            <div className="wl-meter-top">
              <span>
                Events included with your pass
                {allowance.mode === 'exact' ? ' (exactly)' : ' (up to)'}
              </span>
              <b>
                {allowance.count ?? 0} / {allowance.required ?? 0}{' '}
                <small style={{ fontWeight: 400, color: 'var(--dim)' }}>events</small>
              </b>
            </div>
            <div className="wl-meter-bar">
              <i
                style={{
                  width: `${
                    allowance.capPaise
                      ? Math.min(100, ((allowance.valuePaise || 0) / allowance.capPaise) * 100)
                      : allowance.required
                        ? Math.min(100, ((allowance.count || 0) / allowance.required) * 100)
                        : 0
                  }%`,
                }}
              />
            </div>
            <div className="wl-meter-notes">
              <span>
                Value of selected events <b>{money(allowance.valuePaise || 0)}</b>
                {allowance.capPaise != null ? (
                  <> of <b>{money(allowance.capPaise)}</b> covered by your pass</>
                ) : null}
              </span>
              {allowance.capPaise != null ? (
                <span>
                  Still covered <b>{money(allowance.remainingPaise || 0)}</b>
                </span>
              ) : null}
              {allowance.capPaise != null &&
              (allowance.valuePaise || 0) > allowance.capPaise ? (
                <span style={{ color: '#f2c46d' }}>
                  Extra value beyond your pass{' '}
                  <b>{money((allowance.valuePaise || 0) - allowance.capPaise)}</b>
                </span>
              ) : null}
              {quote && due > 0 ? (
                <span style={{ color: '#f2c46d' }}>
                  Extra to pay <b>{money(due)}</b>
                </span>
              ) : null}
              {allowance.locked ? (
                <span style={{ color: '#f2c46d' }}>Selection is locked by the organisers</span>
              ) : null}
            </div>
          </div>

        </div>

        <div className="wl-tools">
          <input
            className="wl-search"
            placeholder="Search events"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Search events"
          />
          <div className="wl-chip-row">
            {[
              ['all', 'All events'],
              ['selected', 'On my list'],
              ['free', 'Free or included'],
              ['due', 'Extra payment'],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`wl-chip ${filter === id ? 'on' : ''}`}
                onClick={() => setFilter(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <EventsColumnsPicker
            activeCols={activeCols}
            colOptions={colOptions}
            onChange={handleColsChange}
          />
        </div>

        <div className="wl-section">
          <div className="wl-section-head">
            <h2>Individual events</h2>
            <span className="wl-section-sub">
              one entry per person. Your pass allowance works the same as for team events
            </span>
            <span className="wl-count">{individualRows.length}</span>
          </div>
          <div className="exc-grid wl-plan-grid" data-cols={activeCols}>
            {individualRows.length ? (
              individualRows.map((row) => (
                <PortalPlanCard
                  key={row.eventId}
                  row={row}
                  selected={selected.includes(row.eventId)}
                  blocked={passBlocked}
                  busy={busy}
                  onToggle={toggle}
                  onPay={payRow}
                  team={teamsByEvent[row.eventId]}
                />
              ))
            ) : !search && filter === 'all' && rows.some((r) => r.format !== 'team' && r.seat?.status === 'confirmed') ? (
              <div className="wl-empty">
                You&apos;re already registered for all available individual events.
              </div>
            ) : (
              <div className="wl-empty">No individual events match this filter.</div>
            )}
          </div>
        </div>

        <div className="wl-section">
          <div className="wl-section-head">
            <h2>Team events</h2>
            <span className="wl-section-sub">
              enter on your own first if you like. You can create or join a team any time and the
              price never changes
            </span>
            <span className="wl-count">{teamRows.length}</span>
          </div>
          <div className="exc-grid wl-plan-grid" data-cols={activeCols}>
            {teamRows.length ? (
              teamRows.map((row) => (
                <PortalPlanCard
                  key={row.eventId}
                  row={row}
                  selected={selected.includes(row.eventId)}
                  blocked={passBlocked}
                  busy={busy}
                  onToggle={toggle}
                  onPay={payRow}
                  team={teamsByEvent[row.eventId]}
                />
              ))
            ) : !search && filter === 'all' && rows.some((r) => r.format === 'team' && r.seat?.status === 'confirmed') ? (
              <div className="wl-empty">
                You&apos;re already registered for all available team events.
              </div>
            ) : (
              <div className="wl-empty">No team events match this filter.</div>
            )}
          </div>
        </div>

        {selected.length ? (
          <div className="wl-basket">
            <div className="wl-basket-sum">
              <b>{selected.length} events selected</b> · your pass covers{' '}
              <b>{money(quote?.coveredPaise || 0)}</b> · you pay{' '}
              <b className="wl-due">{money(due)}</b>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                variant="ghost"
                onClick={async () => {
                  setBusy('clear');
                  try {
                    for (const id of selected) {
                      await portalApi.removeFromBasket(editionId, id);
                    }
                    await reloadAll();
                  } catch (error) {
                    setMessage({ tone: 'error', text: error.message });
                  } finally {
                    setBusy('');
                  }
                }}
                disabled={busy === 'clear'}
              >
                Clear selection
              </Button>
              <Button
                icon={CreditCard}
                variant="light"
                onClick={() => setReviewOpen(true)}
                disabled={!quote || busy === 'checkout'}
              >
                Review &amp; {due > 0 ? `pay ${money(due)}` : 'confirm free'}
              </Button>
            </div>
          </div>
        ) : null}

        <div className="wl-cross-nav">
          <p className="wl-cross-nav-note">
            Already registered? View your confirmed events, tickets, and receipts.
          </p>
          <Link to="/portal/registrations" className="login-machined-btn is-gold">
            <span>View My Events &amp; Bills</span>
            <ArrowRight size={14} strokeWidth={2} />
          </Link>
        </div>
      </div>

      {/* ---------------------------------------------------------------- quote */}
      <Sheet
        open={reviewOpen}
        title="Review your selection"
        eyebrow="CHECK BEFORE YOU PAY"
        onClose={() => setReviewOpen(false)}
      >
        {quote ? (
          <div>
            {(quote.lines || [])
              .filter((line) => line.action === 'create')
              .map((line) => (
                <div className="wl-quote-line" key={line.eventId}>
                  <div>
                    {line.title}
                    <small>
                      {line.basis === 'included'
                        ? 'Covered by your pass'
                        : line.basis === 'free'
                          ? 'Free event'
                          : 'Extra event — pay the difference'}
                      {line.format === 'team' ? ' · team entry' : ''}
                    </small>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    {line.duePaise > 0 ? (
                      <b>{money(line.duePaise)}</b>
                    ) : (
                      <span className="wl-pill included">₹0</span>
                    )}
                  </div>
                </div>
              ))}
            <div className="wl-quote-total">
              <span>Total to pay now</span>
              <span>{money(quote.duePaise)}</span>
            </div>
            <p className="wl-note" style={{ marginTop: 12 }}>
              Once you pay, that place is confirmed and its price won't change, even if you pick
              more events later. If you remove a paid event before the 24-hour deadline, the money
              goes back to your original payment method.
            </p>
            <div className="sheet-actions" style={{ marginTop: 16 }}>
              <Button variant="ghost" onClick={() => setReviewOpen(false)}>
                Back
              </Button>
              <Button
                icon={CreditCard}
                onClick={checkout}
                disabled={busy === 'checkout'}
              >
                {busy === 'checkout'
                  ? 'Confirming'
                  : quote.duePaise > 0
                    ? `Pay ${money(quote.duePaise)}`
                    : 'Confirm seats'}
              </Button>
            </div>
          </div>
        ) : (
          <p className="muted">Pricing your basket…</p>
        )}
      </Sheet>

      {/* --------------------------------------------------------------- remove */}
      <Sheet
        open={Boolean(removeRow)}
        title="Remove this event"
        eyebrow="WHAT HAPPENS TO YOUR MONEY"
        onClose={() => setRemoveRow(null)}
      >
        {removeRow ? (
          <div>
            <p className="muted">
              Remove <b>{removeRow.title}</b> from your list? Your place is released immediately
              and its ticket is cancelled.
            </p>
            {removeRow.seat?.feePaise > 0 ? (
              <p className="wl-note" style={{ marginTop: 12 }}>
                You paid <b>{money(removeRow.seat.feePaise)}</b> for this event. The money goes
                back to your original payment method, less any charges stated in the refund
                policy.
              </p>
            ) : (
              <p className="wl-note" style={{ marginTop: 12 }}>
                This event cost ₹0, so no money moves. If it was included with your pass, that
                place is free again for another event.
              </p>
            )}
            <div className="sheet-actions" style={{ marginTop: 16 }}>
              <Button variant="ghost" onClick={() => setRemoveRow(null)}>
                Keep event
              </Button>
              <Button
                onClick={doRemove}
                disabled={busy === `remove-${removeRow.eventId}`}
              >
                {busy === `remove-${removeRow.eventId}` ? 'Removing' : 'Remove event'}
              </Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      {/* --------------------------------------------------------------- create */}
      <Sheet
        open={Boolean(createRow)}
        title="Create a team"
        eyebrow={createRow?.title}
        onClose={() => setCreateRow(null)}
      >
        {createRow ? (
          <div>
            <p className="wl-note">
              Your existing entry for this event moves into the team. Nothing is charged again: if
              the event is included with your pass it stays ₹0, and if it is paid you pay it only
              once.
            </p>
            <label className="wl-note" style={{ display: 'block', marginTop: 14 }} htmlFor="team-name">
              Team name
            </label>
            <input
              id="team-name"
              className="wl-search"
              value={teamName}
              onChange={(event) => setTeamName(event.target.value)}
              maxLength={48}
              style={{ marginTop: 6, width: '100%' }}
            />
            <div className="sheet-actions" style={{ marginTop: 16 }}>
              <Button variant="ghost" onClick={() => setCreateRow(null)}>
                Cancel
              </Button>
              <Button
                icon={Users}
                onClick={createTeam}
                disabled={busy === 'create-team' || teamName.trim().length < 3}
              >
                {busy === 'create-team' ? 'Creating' : 'Create team'}
              </Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      {/* ----------------------------------------------------------------- join */}
      <Sheet
        open={Boolean(joinRow)}
        title="Join a team"
        eyebrow={joinRow?.title}
        onClose={() => setJoinRow(null)}
      >
        {joinRow ? (
          <div>
            <p className="wl-note">
              Paste the invite link or the code. You need an active pass to join. If you haven't
              picked this event yet, it is added using your pass allowance, so a covered entry
              joins for ₹0.
            </p>
            <input
              className="wl-search"
              placeholder="https://…/team/AB12CD34 or AB12CD34"
              value={joinCode}
              onChange={(event) => setJoinCode(event.target.value)}
              style={{ marginTop: 14, width: '100%' }}
            />
            <div className="sheet-actions" style={{ marginTop: 16 }}>
              <Button variant="ghost" onClick={() => setJoinRow(null)}>
                Cancel
              </Button>
              <Button
                icon={Link2}
                onClick={joinTeam}
                disabled={busy === 'join-team' || normaliseCode(joinCode).length < 4}
              >
                {busy === 'join-team' ? 'Joining' : 'Join team'}
              </Button>
            </div>
          </div>
        ) : null}
      </Sheet>

      {/* ------------------------------------------------------------ team panel */}
      <Sheet
        open={Boolean(teamRow)}
        title={activeTeam ? activeTeam.name : 'Team'}
        eyebrow={teamRow?.title}
        onClose={() => setTeamRow(null)}
      >
        {teamRow ? (
          <div className="wl-team-card">
            {activeTeam ? (
              <>
                <div className="wl-meta">
                  <Badge tone="accent">{activeTeam.formationState}</Badge>
                  <span>
                    {activeTeam.memberCount} / {activeTeam.maxSize} members · minimum{' '}
                    {activeTeam.minSize}
                  </span>
                  {activeTeam.status === 'locked' ? (
                    <span style={{ color: '#f2c46d' }}>Roster locked</span>
                  ) : null}
                </div>
                <div className="wl-team-members">
                  {(activeTeam.members || []).map((member) => (
                    <div className="wl-team-member" key={member.userId}>
                      <div>
                        <b>{member.fullName}</b>
                        <span>{member.collegeName || 'College not set'}</span>
                      </div>
                      {member.isLeader ? <Badge tone="accent">Leader</Badge> : null}
                    </div>
                  ))}
                </div>
                {activeTeam.isLeader ? (
                  <>
                    <div className="wl-invite">
                      <code>{inviteUrl(activeTeam)}</code>
                      <Button size="small" variant="ghost" icon={Copy} onClick={() => copyInvite(activeTeam)}>
                        Copy
                      </Button>
                      <Button
                        size="small"
                        variant="ghost"
                        icon={Share2}
                        onClick={() => {
                          const url = inviteUrl(activeTeam);
                          window.open(
                            `https://wa.me/?text=${encodeURIComponent(`Join ${activeTeam.name} on Parallax — ${url}`)}`,
                            '_blank',
                            'noopener',
                          );
                        }}
                      >
                        WhatsApp
                      </Button>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <Button
                        size="small"
                        variant="ghost"
                        icon={Lock}
                        onClick={() => toggleLock(activeTeam)}
                        disabled={busy === `lock-${activeTeam.id}`}
                      >
                        {activeTeam.status === 'locked' ? 'Unlock roster' : 'Lock roster'}
                      </Button>
                      <Button
                        size="small"
                        variant="ghost"
                        icon={RefreshCw}
                        onClick={() => rotate(activeTeam)}
                        disabled={busy === `rotate-${activeTeam.id}`}
                      >
                        New invite code
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="wl-note">
                    Only the leader can share or rotate the invite link. Your entry is attached and
                    you were not charged a second time.
                  </p>
                )}
                {teamRow.payment ? (
                  <Button
                    icon={CreditCard}
                    onClick={() => payRow({ ...teamRow, payment: teamRow.payment })}
                    disabled={busy === `pay-${teamRow.eventId}`}
                  >
                    Pay team fee {money(teamRow.payment.amountPaise)}
                  </Button>
                ) : null}
                <div className="sheet-actions" style={{ marginTop: 4 }}>
                  <Button variant="ghost" onClick={() => setTeamRow(null)}>
                    Close
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => doLeave(activeTeam)}
                    disabled={busy === `leave-${activeTeam.id}`}
                  >
                    {busy === `leave-${activeTeam.id}` ? 'Leaving' : 'Leave team'}
                  </Button>
                </div>
                <p className="wl-note">
                  If the leader leaves, the earliest-joined member becomes leader. The team
                  disbands only when the last member leaves.
                </p>
              </>
            ) : (
              <p className="muted">You are not on a team for this event yet.</p>
            )}
          </div>
        ) : null}
      </Sheet>
    </>
  );
}

export default PortalWorklist;
