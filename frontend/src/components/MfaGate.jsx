import { useCallback, useEffect, useRef, useState } from 'react';
import { QRCodeCanvas } from 'qrcode.react';
import { ShieldCheck } from 'lucide-react';
import { authApi, onStepUpRequired } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { Button, Field, InlineMessage, Panel } from './ui.jsx';

/**
 * Staff authenticator-app gate.
 *
 * Staff roles listed in MFA_REQUIRED_ROLES cannot use the admin area until the
 * session is MFA-complete. First visit shows enrolment (QR + confirm code);
 * after that it only asks for the current six-digit code. Nobody is locked out
 * because enrolment is part of the gate itself.
 */
export default function MfaGate() {
  const { user, logout, reload } = useAuth();
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState('');
  const [useRecovery, setUseRecovery] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState(null);

  const enrolled = Boolean(user?.mfaEnabled);

  useEffect(() => {
    if (enrolled || setup) return;
    let alive = true;
    setBusy('setup');
    authApi
      .mfaSetup()
      .then((body) => {
        if (alive) setSetup(body?.data || body);
      })
      .catch((err) => {
        if (alive) setError(err.message);
      })
      .finally(() => {
        if (alive) setBusy('');
      });
    return () => {
      alive = false;
    };
  }, [enrolled, setup]);

  const enroll = async () => {
    setBusy('verify');
    setError(null);
    try {
      const body = await authApi.mfaVerify({ code: code.trim() });
      setRecoveryCodes((body?.data || body)?.recoveryCodes || []);
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const challenge = async () => {
    setBusy('challenge');
    setError(null);
    try {
      await authApi.mfaChallenge(
        useRecovery ? { recoveryCode: recoveryCode.trim() } : { code: code.trim() },
      );
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  if (recoveryCodes) {
    return (
      <div className="admin-gate">
        <Panel>
          <h2 className="panel-title">Save these recovery codes</h2>
          <p className="muted">
            Each code works once if you lose your authenticator. Store them somewhere offline; this
            is the only time they are shown.
          </p>
          <div className="recovery-code-grid">
            {recoveryCodes.map((value) => (
              <code key={value}>{value}</code>
            ))}
          </div>
          <Button onClick={() => reload()}>I have saved them</Button>
        </Panel>
      </div>
    );
  }

  return (
    <div className="admin-gate">
      <Panel>
        <h2 className="panel-title">
          <ShieldCheck size={20} /> Two-factor authentication
        </h2>
        {enrolled ? (
          <>
            <p className="muted">
              Enter the current six-digit code from your authenticator app to unlock the admin area.
            </p>
            {useRecovery ? (
              <Field label="Recovery code" hint="One of the codes you saved when you enrolled.">
                <input
                  value={recoveryCode}
                  onChange={(event) => setRecoveryCode(event.target.value)}
                  autoComplete="one-time-code"
                />
              </Field>
            ) : (
              <Field label="Authenticator code">
                <input
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={8}
                />
              </Field>
            )}
            {error ? <InlineMessage tone="error">{error}</InlineMessage> : null}
            <div className="admin-gate-actions">
              <Button
                onClick={challenge}
                disabled={busy === 'challenge' || (useRecovery ? !recoveryCode : code.length < 6)}
              >
                {busy === 'challenge' ? 'Checking' : 'Unlock'}
              </Button>
              <Button variant="ghost" onClick={() => setUseRecovery((v) => !v)}>
                {useRecovery ? 'Use authenticator code' : 'Use a recovery code'}
              </Button>
              <Button variant="ghost" onClick={logout}>
                Sign out
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="muted">
              Admin accounts use an authenticator app. Scan the code with Google Authenticator,
              Authy, 1Password or any TOTP app, then enter the six-digit code it shows.
            </p>
            {setup?.otpauthUri ? (
              <div className="mfa-qr">
                <QRCodeCanvas value={setup.otpauthUri} size={196} includeMargin />
                <p className="muted">
                  Can’t scan? Enter this key manually: <b>{setup.secretPreview}</b>
                </p>
              </div>
            ) : null}
            {!setup && busy === 'setup' ? (
              <InlineMessage tone="info">Preparing your key…</InlineMessage>
            ) : null}
            <Field label="Six-digit code">
              <input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
              />
            </Field>
            {error ? <InlineMessage tone="error">{error}</InlineMessage> : null}
            <div className="admin-gate-actions">
              <Button
                onClick={enroll}
                disabled={busy === 'verify' || !setup || code.trim().length < 6}
              >
                {busy === 'verify' ? 'Verifying' : 'Turn on two-factor'}
              </Button>
              <Button variant="ghost" onClick={logout}>
                Sign out
              </Button>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}

/**
 * Global step-up prompt. Requests that need a fresh code resolve through this
 * modal and are then retried automatically, so an admin never sees a dead
 * button.
 */
export function StepUpGate() {
  const [request, setRequest] = useState(null);
  const pending = useRef(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    onStepUpRequired(
      () =>
        new Promise((resolve) => {
          setCode('');
          setError(null);
          setRequest({ resolve });
        }),
    );
    return () => onStepUpRequired(null);
  }, []);

  const finish = useCallback((value) => {
    pending.current = null;
    setRequest((current) => {
      current?.resolve?.(value);
      return null;
    });
  }, []);

  if (!request) return null;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await authApi.mfaStepUp({ code: code.trim() });
      finish(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <Panel>
        <h3 className="panel-title">Confirm it’s you</h3>
        <p className="muted">This action needs a fresh code from your authenticator app.</p>
        <Field label="Authenticator code">
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={8}
            autoFocus
          />
        </Field>
        {error ? <InlineMessage tone="error">{error}</InlineMessage> : null}
        <div className="admin-gate-actions">
          <Button onClick={submit} disabled={busy || code.trim().length < 6}>
            {busy ? 'Checking' : 'Confirm'}
          </Button>
          <Button variant="ghost" onClick={() => finish(false)}>
            Cancel
          </Button>
        </div>
      </Panel>
    </div>
  );
}
