import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Wrench } from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { Button, Eyebrow, Field, InlineMessage } from '../components/ui.jsx';

const PROTOCOL_FRAME = `${import.meta.env.BASE_URL}images/login_protocol_frame.png`;

function GoogleIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: 0 }}>
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
      <div className="login-nebula" aria-hidden="true" />

      <div className="login-shell">
        <div className="login-grid">
          <aside className="login-art">
            <div className="login-hero-copy">
              <h1>
                Sign in to
                <br />
                <em>the portal.</em>
              </h1>
              <p className="login-lead">
                Access your convention passes, event registrations, and digital QR ID.
              </p>
            </div>

            <div className="login-points">
              <div className="login-point">
                <span className="login-point-num">01</span>
                <span>Digital pass &amp; QR check-in</span>
              </div>
              <div className="login-point">
                <span className="login-point-num">02</span>
                <span>Event entries &amp; team invites</span>
              </div>
              <div className="login-point">
                <span className="login-point-num">03</span>
                <span>Instant payment receipts</span>
              </div>
            </div>
          </aside>

          <div className="login-panel">
            <div className="login-frame-wrap">
              <div className="login-protocol-card">
                <img
                  className="login-protocol-frame"
                  src={PROTOCOL_FRAME}
                  alt=""
                  draggable="false"
                  decoding="async"
                />
                <div className="login-protocol-bay">
                  <div className="login-bezel-head">
                    <span className="login-bezel-code">01 / SINGLE SIGN-ON</span>
                  </div>

                  <div className="login-frame-main">
                    <h2 className="login-frame-title">Access your account</h2>
                    <p className="login-frame-sub">
                      Continue with Google to open your convention portal.
                    </p>

                    {error ? (
                      <div style={{ width: '100%', marginTop: '10px' }}>
                        <InlineMessage tone="error">{error}</InlineMessage>
                      </div>
                    ) : null}

                    <div className="login-oauth-action">
                      <a
                        href={`/api/v1/auth/google/login?next=${encodeURIComponent(next)}`}
                        className="login-machined-btn is-gold login-google-gold-btn"
                      >
                        <GoogleIcon size={18} />
                        <span>Sign in with Google</span>
                        <ArrowUpRight size={15} strokeWidth={2} />
                      </a>
                    </div>
                  </div>

                  <div className="login-frame-foot">
                    <span className="login-legal">Convention Code of Conduct applies</span>
                    <Link to="/contact" className="login-foot-help">
                      Need help? <ArrowUpRight size={12} strokeWidth={2} />
                    </Link>
                  </div>
                </div>
              </div>

              {isDevMode && (
                <div className="bezel login-dev-wrap">
                  <div className="bezel-core login-dev-core">
                    <div className="login-dev-head">
                      <Wrench size={13} color="var(--cyan)" />
                      <span>Local Dev Only Sign-In</span>
                    </div>
                    <form onSubmit={submitDevLogin} className="login-form">
                      <Field label="Test Email">
                        <input
                          type="email"
                          value={devEmail}
                          onChange={(event) => setDevEmail(event.target.value)}
                          placeholder="test@example.com"
                          required
                        />
                      </Field>
                      <Button type="submit" disabled={busy} className="full">
                        {busy ? 'Signing in…' : 'Local Dev Login'}
                      </Button>
                    </form>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
