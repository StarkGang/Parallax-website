import { useCallback, useEffect, useRef, useState } from 'react';
import { QRCodeCanvas } from 'qrcode.react';
import { ShieldCheck, Download, Copy, Check } from 'lucide-react';
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
  const [copied, setCopied] = useState(false);

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

  const requestReset = async () => {
    setBusy('setup');
    setError(null);
    try {
      const body = await authApi.mfaSetup({ reset: true });
      setSetup(body?.data || body);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const [copiedAll, setCopiedAll] = useState(false);

  const enroll = async () => {
    setBusy('verify');
    setError(null);
    try {
      const body = await authApi.mfaVerify({ code: code.trim() });
      setRecoveryCodes((body?.data || body)?.recoveryCodes || []);
      // Do not auto-reload here so the user has time to read/download recovery codes
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const downloadCodes = () => {
    if (!recoveryCodes || !recoveryCodes.length) return;
    const content = [
      '====================================================',
      'PARALLAX ISTE CONVENTION - MFA RECOVERY CODES',
      `Account: ${user?.email || 'Admin'}`,
      `Generated: ${new Date().toLocaleString()}`,
      `Developed by Midhun K M [midhunkm.pages.dev]`,
      '====================================================',
      '',
      'Keep these codes in a secure, offline location.',
      'Each code can only be used once if you lose access to your authenticator app.',
      '',
      ...recoveryCodes.map((c, i) => `${i + 1}. ${c}`),
      '',
    ].join('\r\n');

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const safeUser = user?.email?.split('@')[0] || 'admin';
    link.download = `parallax-mfa-recovery-codes-${safeUser}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const copyAllCodes = () => {
    if (!recoveryCodes || !recoveryCodes.length) return;
    navigator.clipboard?.writeText(recoveryCodes.join('\n'));
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), 2000);
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
          <h2 className="panel-title">
            <ShieldCheck size={20} /> Save these recovery codes
          </h2>
          <p className="muted">
            Each code works once if you lose your authenticator. Store them somewhere offline; this
            is the only time they are shown.
          </p>
          <div className="recovery-code-grid" style={{ margin: '16px 0' }}>
            {recoveryCodes.map((value) => (
              <code key={value} style={{ userSelect: 'all' }}>{value}</code>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '10px', marginTop: '20px', flexWrap: 'wrap' }}>
            <Button type="button" onClick={downloadCodes}>
              <Download size={15} style={{ marginRight: '6px' }} /> Download as textfile
            </Button>
            <Button type="button" variant="ghost" onClick={copyAllCodes}>
              {copiedAll ? (
                <>
                  <Check size={15} style={{ marginRight: '6px' }} /> Copied all
                </>
              ) : (
                <>
                  <Copy size={15} style={{ marginRight: '6px' }} /> Copy all codes
                </>
              )}
            </Button>
            <Button
              type="button"
              style={{ marginLeft: 'auto' }}
              onClick={() => reload()}
            >
              I have saved them & continue
            </Button>
          </div>
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
                <div style={{ marginTop: '12px', textAlign: 'center' }}>
                  <p className="muted" style={{ marginBottom: '8px' }}>
                    Can’t scan? Enter this key manually in your authenticator app:
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <code
                      style={{
                        padding: '4px 10px',
                        borderRadius: '4px',
                        background: 'rgba(255, 255, 255, 0.08)',
                        border: '1px solid var(--line)',
                        fontSize: '13px',
                        letterSpacing: '1px',
                        fontWeight: 'bold',
                        userSelect: 'all',
                      }}
                    >
                      {setup.secret || setup.secretPreview}
                    </code>
                    <Button
                      type="button"
                      variant="ghost"
                      style={{ padding: '4px 10px', height: 'auto', fontSize: '12px' }}
                      onClick={() => {
                        const val = setup.secret || setup.secretPreview;
                        if (val) {
                          navigator.clipboard?.writeText(val);
                          setCopied(true);
                          setTimeout(() => setCopied(false), 2000);
                        }
                      }}
                    >
                      {copied ? 'Copied!' : 'Copy Key'}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      style={{ padding: '4px 10px', height: 'auto', fontSize: '12px', opacity: 0.8 }}
                      onClick={requestReset}
                      disabled={busy === 'setup'}
                    >
                      Get New QR Code
                    </Button>
                  </div>
                </div>
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
