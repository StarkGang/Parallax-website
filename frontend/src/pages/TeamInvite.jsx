import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, CreditCard, LogIn, Users } from 'lucide-react';
import { portalApi, publicApi } from '../lib/api.js';
import { payOrder } from '../lib/pay.js';
import { useAuth } from '../lib/auth.jsx';
import { date, money } from '../lib/format.js';
import { Badge, Button, ErrorBox, Feedback, InlineMessage, Loading, useAsync } from '../components/ui.jsx';
import './Worklist.css';

export function TeamInvite() {
  const { code } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const preview = useAsync(() => publicApi.teamInvite(code), [code]);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState(null);
  const [joined, setJoined] = useState(false);
  const navTimerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (navTimerRef.current) clearTimeout(navTimerRef.current);
    };
  }, []);

  const data = preview.data?.data;

  const join = async () => {
    if (!data) return;
    if (!data.edition?.id) {
      setMessage({ tone: 'error', text: 'This invite is not linked to an active edition.' });
      return;
    }
    setBusy('join');
    setMessage(null);
    try {
      const response = await portalApi.joinTeam(data.edition.id, data.code);
      const payment = response.data?.payment;
      if (payment) {
        const outcome = await payOrder(
          data.edition.id,
          payment,
          user,
          `${data.event.title} team entry`,
        );
        if (outcome.status !== 'paid') {
          setMessage({
            tone: outcome.status === 'cancelled' ? 'info' : 'error',
            text:
              outcome.status === 'cancelled'
                ? 'You joined, but the entry is unpaid. Pay it from your event worklist.'
                : outcome.message || 'The team entry could not be paid.',
          });
          navigate('/portal/events');
          return;
        }
      }
      setJoined(true);
      setMessage({ tone: 'success', text: 'You are on the team. Your seat is attached.' });
      navTimerRef.current = setTimeout(() => navigate('/portal/events'), 1200);
    } catch (error) {
      const needsPass = /pass/i.test(error.message || '');
      setMessage({
        tone: 'error',
        text: needsPass
          ? `${error.message} Buy your pass, then come back to this link.`
          : error.message,
      });
    } finally {
      setBusy('');
    }
  };

  if (preview.loading) return <Loading label="Loading the team invite" rows={2} />;
  if (preview.error) {
    return (
      <div className="wl-invite-page">
        <ErrorBox error={preview.error} onRetry={preview.reload} />
        <Link to="/events" className="table-action">
          <ArrowLeft size={14} /> Browse events
        </Link>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="wl-invite-page">
      <Link to="/events" className="table-action" style={{ alignSelf: 'flex-start' }}>
        <ArrowLeft size={14} /> Back to events
      </Link>

      <div className="wl-invite-hero">
        <span>Team invite · Parallax</span>
        <h1>Join {data.teamName}</h1>
        <p>
          {data.event.title} · {data.event.startsAt ? date(data.event.startsAt) : 'Date to be announced'}
          {data.event.venue ? ` · ${data.event.venue}` : ''}
        </p>
        <div className="wl-invite-stats">
          <div className="wl-invite-stat">
            <span>Roster</span>
            <b>
              {data.memberCount} / {data.maxSize}
            </b>
          </div>
          <div className="wl-invite-stat">
            <span>Leader</span>
            <b>{data.leaderName}</b>
          </div>
          <div className="wl-invite-stat">
            <span>Entry</span>
            <b>
              {data.event.listPaise > 0 ? money(data.event.listPaise) : 'Free'}
              {' / person'}
            </b>
          </div>
          <div className="wl-invite-stat">
            <span>Pass</span>
            <b>{data.requiresPass ? 'Required' : 'Not required'}</b>
          </div>
        </div>
      </div>

      <Feedback message={message} />

      {data.openForJoin ? null : (
        <InlineMessage tone="error">
          {data.status === 'locked'
            ? 'This roster is locked by the team leader.'
            : data.memberCount >= data.maxSize
              ? 'This team is full.'
              : 'This invite is no longer open.'}{' '}
          <Link to="/events" style={{ textDecoration: 'underline' }}>
            Browse events or create your own team.
          </Link>
        </InlineMessage>
      )}

      {!user ? (
        <div className="wl-invite-panel">
          <div className="wl-steps">
            <div className="wl-step">
              <span className="n">1</span>
              <div>
                <b>Sign in</b> with your convention account — your seat and pass travel with it.
              </div>
            </div>
            <div className="wl-step">
              <span className="n">2</span>
              <div>
                If you do not hold a seat, the next screen adds it through your pass allowance. A
                covered team entry is ₹0; otherwise you pay the entry fee once.
              </div>
            </div>
            <div style={{ marginTop: '8px' }}>
              <Button
                to={`/login?next=${encodeURIComponent(`/team/${data.code}`)}`}
                icon={LogIn}
              >
                Sign in to join
              </Button>
            </div>
          </div>
        </div>
      ) : joined ? (
        <InlineMessage tone="success">Joined. Opening your event worklist…</InlineMessage>
      ) : (
        <div className="wl-invite-panel">
          <div className="wl-steps">
            <div className="wl-step">
              <span className="n">1</span>
              <div>
                <b>You are signed in as {user.fullName || user.email}.</b> The seat for this event is
                added through the same pass allowance as any other event — team membership never adds
                a charge.
              </div>
            </div>
            <div className="wl-step">
              <span className="n">2</span>
              <div>
                {data.requiresPass
                  ? 'You must hold an active pass to join. If yours is missing, the button will take you to the pass page first.'
                  : 'No pass is required for this edition.'}
              </div>
            </div>
            <div style={{ marginTop: '8px' }}>
              <Button icon={Users} onClick={join} disabled={busy === 'join' || !data.openForJoin}>
                {busy === 'join' ? 'Joining' : `Join ${data.teamName}`}
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="wl-note">
        Invite links are derived from the team code, never stored as a separate address. If the
        leader rotates the code, this link stops working and they can share a fresh one.
      </div>
    </div>
  );
}

export default TeamInvite;
