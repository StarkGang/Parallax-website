import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { useSite } from '../lib/site.jsx';
import { Button, Eyebrow, Field, InlineMessage } from '../components/ui.jsx';

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.png`;

export default function Login() {
  const { user, loading, login, isStaff } = useAuth();
  const { config, edition } = useSite();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = params.get('next') || '/portal';
  const [form, setForm] = useState({ email: '', fullName: '' });
  const [isStaffLogin, setIsStaffLogin] = useState(params.get('staff') === 'true');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!loading && user) navigate(next, { replace: true });
  }, [loading, user, next, navigate]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const account = await login({
        email: form.email.trim(),
        role: isStaffLogin ? 'admin' : 'participant',
        fullName: form.fullName.trim() || undefined,
      });
      const staff = account?.roles?.some((grant) => grant.role !== 'participant');
      navigate(staff && next === '/portal' ? '/manage' : next, { replace: true });
    } catch (err) {
      setError(err.message || 'Sign-in failed.');
    } finally {
      setBusy(false);
    }
  };

  const hasGoogle = Boolean(config?.googleLogin);
  const hasDirect = Boolean(config?.devLogin);

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
            the portal. Staff credentials open the administrative console.
          </p>
          <div className="login-points">
            <span>
              <ShieldCheck size={16} strokeWidth={1.5} /> Secure attendee authentication
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
            <Eyebrow>{isStaffLogin ? 'Staff Access' : 'Sign In'}</Eyebrow>
            <h2>Access your account</h2>
            <p className="muted">
              {hasGoogle
                ? 'Continue with your Google account, or sign in using your college email.'
                : 'Enter your email address to access your convention pass and registrations.'}
            </p>

            {hasGoogle && (
              <div className="login-oauth-action">
                <Button href="/api/v1/auth/google/login?next=/portal" icon={ArrowRight} className="full">
                  Continue with Google
                </Button>
                {hasDirect && <div className="login-divider"><span>or with email</span></div>}
              </div>
            )}

            {hasDirect && (
              <form onSubmit={submit} className="login-form">
                <Field label="Email address">
                  <input
                    type="email"
                    value={form.email}
                    onChange={(event) => setForm({ ...form, email: event.target.value })}
                    placeholder="you@nssce.ac.in"
                    autoComplete="email"
                    required
                  />
                </Field>
                <Field label="Full name" hint="Used when this email signs in for the first time.">
                  <input
                    value={form.fullName}
                    onChange={(event) => setForm({ ...form, fullName: event.target.value })}
                    placeholder="e.g. Warner Stark"
                    autoComplete="name"
                  />
                </Field>
                {isStaffLogin && (
                  <InlineMessage tone="accent">
                    Signing in with staff & organiser privileges
                  </InlineMessage>
                )}
                {error ? <InlineMessage tone="error">{error}</InlineMessage> : null}
                <Button type="submit" disabled={busy} icon={ArrowRight} className="full">
                  {busy ? 'Signing in…' : isStaffLogin ? 'Sign in to Console' : 'Continue'}
                </Button>
                <div style={{ marginTop: '12px', textAlign: 'center' }}>
                  <button
                    type="button"
                    onClick={() => setIsStaffLogin(!isStaffLogin)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--muted)',
                      font: '11px var(--mono)',
                      cursor: 'pointer',
                      textDecoration: 'underline',
                      textUnderlineOffset: '3px'
                    }}
                  >
                    {isStaffLogin ? '← Switch to participant sign-in' : 'Staff or organiser sign in →'}
                  </button>
                </div>
              </form>
            )}

            {!hasGoogle && !hasDirect && (
              <InlineMessage tone="muted">Sign-in is currently unavailable.</InlineMessage>
            )}

            <p className="login-legal">
              By continuing you agree to the convention code of conduct. Student verification
              and institutional credentials are authenticated in the portal.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
