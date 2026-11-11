import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, ShieldCheck, Wrench } from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { Button, Eyebrow, Field, InlineMessage } from '../components/ui.jsx';

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp`;

function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
      />
    </svg>
  );
}

const ERROR_MESSAGES = {
  signin_failed: 'Google Sign-In could not be completed. Please try again.',
  google_not_configured: 'Google Sign-In is being configured. Please contact support.',
  access_denied: 'Sign-in was cancelled.',
  session_expired: 'Sign-in session expired. Please try again.',
};

export default function Login() {
  const { user, loading, login } = useAuth();
  const { edition } = useSite();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = params.get('next') || '/portal';
  const errorParam = params.get('error');
  const [devEmail, setDevEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(errorParam ? (ERROR_MESSAGES[errorParam] || 'Sign-in failed.') : '');

  useEffect(() => {
    if (!loading && user) {
      const isStaff = user?.roles?.some((grant) => grant.role !== 'participant');
      navigate(isStaff && next === '/portal' ? '/manage' : next, { replace: true });
    }
  }, [loading, user, next, navigate]);

  // Dev mode is strictly restricted to local development builds with ?dev=true
  const isDevMode = import.meta.env.DEV && (params.get('dev') === 'true' || params.get('test') === 'true');

  const submitDevLogin = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const account = await login({
        email: devEmail.trim(),
        role: 'participant',
      });
      const staff = account?.roles?.some((grant) => grant.role !== 'participant');
      navigate(staff && next === '/portal' ? '/manage' : next, { replace: true });
    } catch (err) {
      setError(err.message || 'Dev sign-in failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="login-page">
      <aside className="login-art">
        <Link to="/" className="login-brand" aria-label="Parallax Home">
          <img src={LOGO} alt={edition?.name || 'Parallax 2026'} />
        </Link>
        <div>
          <Eyebrow>Attendee & Staff Portal</Eyebrow>
          <h1>Convention Sign In</h1>
          <p>
            Passes, included events, add-on registrations, team invites and entry tickets live in
            the portal. Authorized staff and organizers are automatically directed to the management console.
          </p>
          <div className="login-points">
            <span>
              <ShieldCheck size={16} strokeWidth={1.5} /> Secure Google authentication
            </span>
            <span>
              <CheckCircle2 size={16} strokeWidth={1.5} /> NSSCE Palakkad convention network
            </span>
          </div>
        </div>
        <Link to="/" className="text-link">
          <ArrowLeft size={15} strokeWidth={1.5} /> Back to the convention
        </Link>
      </aside>

      <div className="login-panel">
        <div className="login-card bezel">
          <div className="bezel-core is-padded">
            <Eyebrow>Single Sign-On</Eyebrow>
            <h2>Access your account</h2>
            <p className="muted">
              Sign in with your Google account. Attendees will access passes and registrations; organizers will be directed to the admin console.
            </p>

            {error ? (
              <div style={{ marginTop: '14px' }}>
                <InlineMessage tone="error">{error}</InlineMessage>
              </div>
            ) : null}

            <div className="login-oauth-action" style={{ margin: '28px 0 20px 0' }}>
              <a
                href={`/api/v1/auth/google/login?next=${encodeURIComponent(next)}`}
                className="google-sign-in-btn"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '12px',
                  width: '100%',
                  padding: '14px 22px',
                  backgroundColor: '#ffffff',
                  color: '#1f1f1f',
                  border: '1px solid #dadce0',
                  borderRadius: '9999px',
                  fontSize: '15px',
                  fontWeight: '600',
                  fontFamily: 'inherit',
                  textDecoration: 'none',
                  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.12)',
                  transition: 'all 0.2s ease',
                  cursor: 'pointer',
                }}
              >
                <GoogleIcon />
                <span>Sign in with Google</span>
              </a>
            </div>

            {isDevMode && (
              <div
                style={{
                  marginTop: '24px',
                  padding: '16px',
                  borderRadius: '8px',
                  border: '1px dashed var(--line-strong)',
                  background: 'rgba(255, 255, 255, 0.02)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '12px' }}>
                  <Wrench size={14} color="var(--accent)" />
                  <span style={{ font: '11px var(--mono)', color: 'var(--accent)', textTransform: 'uppercase' }}>
                    Local Dev Only Sign-In
                  </span>
                </div>
                <form onSubmit={submitDevLogin} className="login-form" style={{ marginTop: 0 }}>
                  <Field label="Test Email">
                    <input
                      type="email"
                      value={devEmail}
                      onChange={(event) => setDevEmail(event.target.value)}
                      aria-label="test@example.com" placeholder="test@example.com"
                      required
                    />
                  </Field>
                  <Button type="submit" disabled={busy} className="full">
                    {busy ? 'Signing in…' : 'Local Dev Login'}
                  </Button>
                </form>
              </div>
            )}

            <p className="login-legal">
              By continuing you agree to the convention code of conduct.
              Authentication is securely handled by Google.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
