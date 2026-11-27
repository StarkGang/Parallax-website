import { useCallback, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Copy,
  CreditCard,
  Link2,
  Plus,
  Ticket,
  Users,
} from 'lucide-react';
import { portalApi, publicApi } from '../lib/api.js';
import { fallbackImageUrl, resolveImageUrl } from '../lib/imageUrl.js';
import { EventGeneratedPoster } from '../components/EventGeneratedPoster.jsx';
import { payOrder } from '../lib/pay.js';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { date, money } from '../lib/format.js';
import {
  Badge,
  Button,
  ErrorBox,
  Feedback,
  InlineMessage,
  Loading,
  Sheet,
  useAsync,
} from '../components/ui.jsx';
import './Worklist.css';

function StepCard({ number, title, dateLabel, state, optional, children, action }) {
  return (
    <article className={`step-card is-${state} ${optional ? 'is-optional' : ''}`}>
      <div className="step-top">
        <span className="step-num">STEP {String(number).padStart(2, '0')}</span>
        <span className={`step-ring ${state}`} aria-hidden="true">
          {state === 'done' ? <Check size={11} strokeWidth={3} /> : null}
        </span>
      </div>
      <h3 className={`step-title ${state === 'done' ? 'is-struck' : ''}`}>{title}</h3>
      {dateLabel ? <div className="step-date">{dateLabel}</div> : null}
      <div className="step-body">{children}</div>
      {action ? <div className="step-action">{action}</div> : null}
    </article>
  );
}

export function EventRoom() {
  const { eventSlug } = useParams();
  const { user } = useAuth();
  const { slug, editionId } = useSite();
  const navigate = useNavigate();

  const detail = useAsync(() => publicApi.event(slug, eventSlug), [slug, eventSlug], {
    enabled: Boolean(slug && eventSlug),
  });
  const work = useAsync(() => portalApi.worklist(editionId), [editionId], {
    enabled: Boolean(editionId),
  });
  const teams = useAsync(() => portalApi.teams(editionId), [editionId], {
    enabled: Boolean(editionId),
  });

  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [joinOpen, setJoinOpen] = useState(false);
  const [teamName, setTeamName] = useState(`Team ${(user?.fullName || 'Player').split(' ')[0]}`);
  const [joinCode, setJoinCode] = useState('');

  const event = detail.data?.data;
  const payload = work.data?.data;
  const rows = payload?.rows || [];
  const row = useMemo(
    () => rows.find((item) => item.slug === eventSlug) || null,
    [rows, eventSlug],
  );
  const basket = payload?.basket || null;
  const basketIds = (basket?.lines || [])
    .filter((line) => line.action === 'create')
    .map((line) => line.eventId);
  const inBasket = row ? basketIds.includes(row.eventId) : false;
  const basketLine = row
    ? (basket?.lines || []).find((line) => line.eventId === row.eventId && line.action === 'create')
    : null;
  const teamForEvent = useMemo(
    () =>
      (teams.data?.data || []).find(
        (item) => row && item.eventId === row.eventId,
      ) || null,
    [teams.data, row?.eventId],
  );

  const passActive = payload?.passStatus === 'active';
  const confirmed = row?.seat?.status === 'confirmed';
  const canAdd = Boolean(row && (row.actions || []).includes('add'));
  const isTeam = row?.format === 'team';
  const dueNow = basketLine
    ? Number(basketLine.duePaise || 0)
    : Number(row?.price?.duePaise || 0);

  const [bannerFailed, setBannerFailed] = useState(false);
  const reload = useCallback(async () => {
    await Promise.all([detail.reload(), work.reload(), teams.reload()]);
  }, [detail, work, teams]);

  const add = async () => {
    if (!row) return;
    setBusy('add');
    setMessage(null);
    try {
      await portalApi.addToBasket(editionId, [row.eventId]);
      await reload();
      setMessage({ tone: 'success', text: 'Added to your plan. The basket is shared with every event page.' });
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const remove = async () => {
    if (!row) return;
    setBusy('remove');
    try {
      await portalApi.removeFromBasket(editionId, row.eventId);
      await reload();
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const payHeld = async () => {
    if (!row?.payment) return;
    setBusy('pay');
    try {
      const outcome = await payOrder(editionId, row.payment, user, row.title);
      if (outcome.status === 'paid') {
        await reload();
        setMessage({ tone: 'success', text: 'Payment confirmed. Your ticket is ready.' });
      } else if (outcome.status === 'cancelled') {
        setMessage({ tone: 'info', text: 'Payment cancelled. The seat stays reserved until it expires.' });
      } else {
        setMessage({ tone: 'error', text: outcome.message || 'Payment failed.' });
      }
    } catch (error) {
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const createTeam = async () => {
    setBusy('create');
    try {
      const body = await portalApi.createTeam(editionId, {
        eventId: row.eventId,
        name: teamName,
      });
      const payment = body.data?.payment;
      if (payment) {
        const outcome = await payOrder(editionId, payment, user, `${row.title} team entry`);
        if (outcome.status !== 'paid') {
          setMessage({
            tone: 'info',
            text: 'Team created. The entry is unpaid — pay it from your event worklist.',
          });
          setCreateOpen(false);
          await reload();
          return;
        }
      }
      setCreateOpen(false);
      await reload();
      setMessage({ tone: 'success', text: 'Team created. Share the invite link.' });
    } catch (error) {
      if (error.code === 'SEAT_IN_BASKET') {
        setCreateOpen(false);
        setMessage({ tone: 'info', text: error.message });
        navigate('/portal/events?review=1');
        return;
      }
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const joinTeam = async () => {
    setBusy('join');
    try {
      const code = String(joinCode || '').trim().split('/').filter(Boolean).pop();
      const body = await portalApi.joinTeam(editionId, code.toUpperCase());
      const payment = body.data?.payment;
      if (payment) {
        const outcome = await payOrder(editionId, payment, user, `${row.title} team entry`);
        if (outcome.status !== 'paid') {
          setMessage({ tone: 'info', text: 'Joined. The entry is unpaid; pay it from the worklist.' });
          setJoinOpen(false);
          await reload();
          return;
        }
      }
      setJoinOpen(false);
      await reload();
      setMessage({ tone: 'success', text: `You joined ${body.data?.name || 'the team'}.` });
    } catch (error) {
      if (error.code === 'SEAT_IN_BASKET') {
        setJoinOpen(false);
        setMessage({ tone: 'info', text: error.message });
        navigate('/portal/events?review=1');
        return;
      }
      setMessage({ tone: 'error', text: error.message });
    } finally {
      setBusy('');
    }
  };

  const copyInvite = async () => {
    if (!teamForEvent) return;
    const url = teamForEvent.inviteLink
      ? `${window.location.origin}${teamForEvent.inviteLink}`
      : `${window.location.origin}/team/${teamForEvent.inviteCode}`;
    try {
      await navigator.clipboard.writeText(url);
      setMessage({ tone: 'success', text: 'Invite link copied.' });
    } catch {
      setMessage({ tone: 'info', text: url });
    }
  };

  if (detail.loading && !event) return <Loading label="Opening the event room" rows={3} />;
  if (detail.error) return <ErrorBox error={detail.error} onRetry={detail.reload} />;
  if (!event) return null;
  if (work.loading && !payload) return <Loading label="Loading your place" rows={2} />;

  const statusPill = confirmed ? (
    <Badge tone="good">Seat confirmed</Badge>
  ) : inBasket ? (
    <Badge tone="warn">In your plan · not paid</Badge>
  ) : (
    <Badge>Not registered</Badge>
  );

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <Link to="/portal/events" className="table-action">
          <ArrowLeft size={14} /> Back to worklist
        </Link>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {statusPill}
          {row?.format === 'team' ? <Badge tone="accent">Team event</Badge> : null}
        </div>
      </div>

      <Feedback message={message} />

      {event.bannerUrl && !bannerFailed ? (
        <div className="room-banner">
          <img
            className="room-banner-image"
            src={resolveImageUrl(event.bannerUrl)}
            alt=""
            referrerPolicy="no-referrer"
            loading="lazy"
            onError={(e) => {
              const alt = fallbackImageUrl(event.bannerUrl, 1200);
              if (alt && e.currentTarget.dataset.retried !== '1') {
                e.currentTarget.dataset.retried = '1';
                e.currentTarget.src = alt;
                return;
              }
              setBannerFailed(true);
            }}
          />
        </div>
      ) : (
        <div className="room-banner">
          <EventGeneratedPoster event={event} />
        </div>
      )}

      <div className="room-hero">
        <div>
          <span className="room-kicker">
            {event.category} · {event.format === 'team' ? 'Team event' : 'Individual event'}
          </span>
          <h1>{event.title}</h1>
          <p>{event.summary}</p>
          <div className="room-facts">
            <span>{event.startsAt ? date(event.startsAt) : 'Date to be announced'}</span>
            {event.venueRoom ? <span>{event.venueRoom}</span> : null}
            {event.format === 'team' ? (
              <span>
                Teams of {event.teamMinSize}–{event.teamMaxSize}
              </span>
            ) : (
              <span>Individual entry</span>
            )}
            {row?.capacity ? <span>{row.capacity} entries</span> : null}
          </div>
        </div>
        <aside className="room-price">
          <span className="room-kicker">Your price</span>
          {confirmed ? (
            <>
              <b>
                {row.seat?.kind === 'included'
                  ? 'Included with pass'
                  : row.seat?.feePaise > 0
                    ? money(row.seat.feePaise)
                    : 'Free'}
              </b>
              <small>Frozen when your seat was confirmed.</small>
            </>
          ) : inBasket ? (
            <>
              <b>{dueNow > 0 ? `${money(dueNow)} due` : '₹0 · covered'}</b>
              <small>Tentative until you confirm the basket.</small>
            </>
          ) : row?.price?.duePaise > 0 ? (
            <>
              <b>{money(row.price.duePaise)}</b>
              <small>Team membership never changes this price.</small>
            </>
          ) : (
            <>
              <b>{row?.price?.basis === 'included' ? 'Included if it fits' : 'Free'}</b>
              <small>Adding it re-prices the basket; nothing is guaranteed until checkout.</small>
            </>
          )}
          {!confirmed && !inBasket && passActive && canAdd ? (
            <Button variant="light" icon={Plus} onClick={add} disabled={busy === 'add'}>
              {busy === 'add' ? 'Adding' : 'Add to my plan'}
            </Button>
          ) : null}
          {inBasket ? (
            <>
              <Button variant="light" icon={CreditCard} onClick={() => navigate('/portal/events?review=1')}>
                Review &amp; pay
              </Button>
              <Button variant="ghost" onClick={remove} disabled={busy === 'remove'}>
                Remove from plan
              </Button>
            </>
          ) : null}
          {!passActive ? (
            <Button to="/portal/registration" variant="light" icon={ArrowRight}>
              Get your pass
            </Button>
          ) : null}
          {confirmed && row?.payment ? (
            <Button icon={CreditCard} onClick={payHeld} disabled={busy === 'pay'}>
              Pay {money(row.payment.amountPaise)}
            </Button>
          ) : null}
        </aside>
      </div>

      <h2 className="room-section-title">Your path for this event</h2>
      <p className="wl-note" style={{ marginTop: -6 }}>
        Four required steps; team formation is optional and never blocks the others.
      </p>

      <div className="step-grid">
        <StepCard
          number={1}
          title="Pass ready"
          dateLabel={passActive ? 'Active' : 'Needed before seats'}
          state={passActive ? 'done' : 'active'}
          action={
            passActive ? null : (
              <Button to="/portal/registration" variant="ghost" size="small">
                Get your pass
              </Button>
            )
          }
        >
          {passActive
            ? 'Your convention pass is active. It decides which events are included.'
            : 'A pass is required before you can add a seat for this event.'}
        </StepCard>

        <StepCard
          number={2}
          title={confirmed ? 'Seat secured' : inBasket ? 'Seat in your plan' : 'Get your seat'}
          dateLabel={confirmed ? row?.seat?.registrationNumber || 'Confirmed' : inBasket ? 'Awaiting checkout' : 'Not added'}
          state={confirmed ? 'done' : inBasket ? 'active' : 'active'}
          action={
            confirmed ? null : inBasket ? (
              <Button size="small" variant="ghost" onClick={() => navigate('/portal/events?review=1')}>
                Review basket
              </Button>
            ) : passActive ? (
              <Button size="small" icon={Plus} onClick={add} disabled={busy === 'add'}>
                Add seat
              </Button>
            ) : null
          }
        >
          {confirmed
            ? 'One seat is attached to you. It is frozen at this price.'
            : inBasket
              ? 'The seat is priced in your shared basket. Confirm it to get the ticket.'
              : 'The pass allowance and the cap decide whether this seat is ₹0 or paid.'}
        </StepCard>

        <StepCard
          number={3}
          title={isTeam ? (teamForEvent ? 'Team formed' : 'Join or form a team') : 'Team'}
          dateLabel={
            !isTeam
              ? 'Not needed'
              : teamForEvent
                ? `${teamForEvent.memberCount} / ${teamForEvent.maxSize} members`
                : 'Optional'
          }
          state={!isTeam ? 'done' : teamForEvent ? 'done' : 'optional'}
          optional={isTeam && !teamForEvent}
          action={
            !isTeam ? null : teamForEvent ? (
              <Button size="small" variant="ghost" onClick={copyInvite} icon={Copy}>
                Copy invite
              </Button>
            ) : (
              <div className="step-team-actions">
                <Button size="small" variant="light" icon={Users} onClick={() => setCreateOpen(true)}>
                  Create a team
                </Button>
                <Button size="small" variant="ghost" icon={Link2} onClick={() => setJoinOpen(true)}>
                  Join with a code
                </Button>
              </div>
            )
          }
        >
          {!isTeam
            ? 'This is an individual event. Solo is the whole entry.'
            : teamForEvent
              ? `${teamForEvent.name} · ${teamForEvent.isLeader ? 'you lead' : 'you are a member'}. Your seat is not charged twice.`
              : 'Competing solo is valid. Create a team or join one any time before the roster locks.'}
        </StepCard>

        <StepCard
          number={4}
          title="Ticket"
          dateLabel={confirmed ? 'Ready' : 'After the seat is confirmed'}
          state={confirmed ? 'done' : 'pending'}
          action={
            confirmed ? (
              <Button to="/portal/registration" size="small" variant="ghost" icon={Ticket}>
                Open ticket
              </Button>
            ) : null
          }
        >
          {confirmed
            ? 'The QR ticket was issued with the seat. The door will admit it.'
            : 'A ticket is issued when the seat is confirmed; an unpaid hold has none.'}
        </StepCard>

        <StepCard
          number={5}
          title="On the day"
          dateLabel={event.startsAt ? date(event.startsAt) : 'Schedule pending'}
          state="pending"
        >
          {event.venueRoom
            ? `Report to ${event.venueRoom}. Carry your college ID and your ticket.`
            : 'Venue and reporting time appear here once published.'}
        </StepCard>
      </div>

      {isTeam ? (
        <div className="room-guide-grid">
          <div className="room-guide">
            <h3>Solo entry</h3>
            {event.soloGuideHtml ? (
              <div dangerouslySetInnerHTML={{ __html: event.soloGuideHtml }} />
            ) : (
              <p>
                You can enter alone. Your price is the same as a team member&apos;s and the pass
                allowance applies exactly the same way.
              </p>
            )}
          </div>
          <div className="room-guide">
            <h3>Team entry</h3>
            {event.teamGuideHtml ? (
              <div dangerouslySetInnerHTML={{ __html: event.teamGuideHtml }} />
            ) : (
              <p>
                Teams run {event.teamMinSize}–{event.teamMaxSize} people. A per-team fee is paid
                once for the whole entry; a per-person fee is paid by each member. Leadership
                moves to the earliest member if the leader leaves.
              </p>
            )}
          </div>
        </div>
      ) : event.soloGuideHtml ? (
        <div className="room-guide">
          <h3>What you do and get</h3>
          <div dangerouslySetInnerHTML={{ __html: event.soloGuideHtml }} />
        </div>
      ) : null}

      {event.descriptionHtml ? (
        <div className="room-guide">
          <h3>About this event</h3>
          <div dangerouslySetInnerHTML={{ __html: event.descriptionHtml }} />
        </div>
      ) : null}

      {event.rulesHtml ? (
        <div className="room-guide">
          <h3>Rules</h3>
          <div dangerouslySetInnerHTML={{ __html: event.rulesHtml }} />
        </div>
      ) : null}

      {event.prizesHtml ? (
        <div className="room-guide">
          <h3>Prizes</h3>
          <div dangerouslySetInnerHTML={{ __html: event.prizesHtml }} />
        </div>
      ) : null}

      {basket?.quoteId ? (
        <div className="wl-basket">
          <div className="wl-basket-sum">
            <b>
              {(basket.lines || []).filter((line) => line.action === 'create').length} in your plan
            </b>{' '}
            · due <b className="wl-due">{money(basket.duePaise || 0)}</b>
          </div>
          <Button variant="light" icon={CreditCard} onClick={() => navigate('/portal/events?review=1')}>
            Review &amp; pay
          </Button>
        </div>
      ) : null}

      <Sheet
        open={createOpen}
        title="Create a team"
        eyebrow={event.title}
        onClose={() => setCreateOpen(false)}
      >
        <p className="wl-note">
          Your seat is attached to the team. If the pass covers the event, the team entry is ₹0.
        </p>
        <input
          className="wl-search"
          style={{ marginTop: 12, width: '100%' }}
          value={teamName}
          onChange={(e) => setTeamName(e.target.value)}
          maxLength={48}
        />
        <div className="sheet-actions" style={{ marginTop: 16 }}>
          <Button variant="ghost" onClick={() => setCreateOpen(false)}>
            Cancel
          </Button>
          <Button onClick={createTeam} disabled={busy === 'create' || teamName.trim().length < 3}>
            {busy === 'create' ? 'Creating' : 'Create team'}
          </Button>
        </div>
      </Sheet>

      <Sheet
        open={joinOpen}
        title="Join a team"
        eyebrow={event.title}
        onClose={() => setJoinOpen(false)}
      >
        <p className="wl-note">
          Paste the invite link or code. You need an active pass; a pass-covered seat joins for ₹0.
        </p>
        <input
          className="wl-search"
          style={{ marginTop: 12, width: '100%' }}
          placeholder="https://…/team/AB12CD34"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value)}
        />
        <div className="sheet-actions" style={{ marginTop: 16 }}>
          <Button variant="ghost" onClick={() => setJoinOpen(false)}>
            Cancel
          </Button>
          <Button onClick={joinTeam} disabled={busy === 'join' || joinCode.trim().length < 4}>
            {busy === 'join' ? 'Joining' : 'Join team'}
          </Button>
        </div>
      </Sheet>
    </>
  );
}

export default EventRoom;
