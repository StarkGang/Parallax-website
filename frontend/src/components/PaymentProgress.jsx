import { Check, RefreshCw, ShieldCheck } from 'lucide-react';
import { money } from '../lib/format.js';

export const PAY_STEPS = [
  ['preparing', 'Payment order created'],
  ['gateway', 'Paid in Razorpay'],
  ['verifying', 'Signature verified'],
];

export const PAY_COPY = {
  preparing: {
    title: 'Securing your checkout',
    detail: 'Creating an encrypted order with Razorpay gateway. Please hold on.',
  },
  gateway: {
    title: 'Complete payment in Razorpay',
    detail: 'Finish payment in the official secure window. Do not refresh or close this tab.',
  },
  verifying: {
    title: 'Confirming your payment',
    detail: 'Razorpay approved the transaction. Verifying cryptographic signature with server...',
  },
  success: {
    title: 'Payment Confirmed!',
    detail: 'Transaction verified successfully. Your tickets & entry credentials are confirmed.',
  },
};

/**
 * Amazon / Google Pay standard payment workflow modal.
 * Shows stage transitions, live progress rings, security badge, and success pop animation.
 */
export function PaymentProgress({ stage, amount, slow, title, subtitle }) {
  if (!stage) return null;
  const copy = PAY_COPY[stage] || PAY_COPY.preparing;
  const activeIndex = PAY_STEPS.findIndex(([key]) => key === stage);
  const isSuccess = stage === 'success';

  return (
    <div className="pay-progress" role="status" aria-live="polite">
      <div className={`pay-progress-card ${isSuccess ? 'is-success' : ''}`}>
        <div className={`pay-progress-icon ${!isSuccess ? 'is-active' : ''}`}>
          {isSuccess ? (
            <Check size={32} strokeWidth={3} />
          ) : (
            <RefreshCw size={28} className="is-spinning" />
          )}
        </div>
        <h3>{title || copy.title}</h3>
        <p>{subtitle || copy.detail}</p>

        {amount ? (
          <div style={{ margin: '14px 0 6px' }}>
            <span className="pay-progress-amount">{money(amount)}</span>
          </div>
        ) : null}

        <ol className="pay-progress-steps">
          {PAY_STEPS.map(([key, label], index) => {
            const done = isSuccess || index < activeIndex;
            const active = !done && index === activeIndex;
            return (
              <li key={key} className={done ? 'is-done' : active ? 'is-active' : ''}>
                <span className="pay-progress-dot">
                  {done ? <Check size={12} strokeWidth={3} /> : index + 1}
                </span>
                <span style={{ fontWeight: active || done ? 600 : 400 }}>{label}</span>
                {active ? <RefreshCw size={12} className="is-spinning" style={{ marginLeft: 'auto' }} /> : null}
              </li>
            );
          })}
        </ol>

        <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', fontSize: '11px', color: '#64748b' }}>
          <ShieldCheck size={14} style={{ color: '#38bdf8' }} />
          <span>256-Bit Encrypted · Official Razorpay Gateway</span>
        </div>

        {slow && !isSuccess ? (
          <small className="pay-progress-hint">
            Still waiting on the banking network. Slow bank connections can take a moment — please keep this page open.
          </small>
        ) : null}
      </div>
    </div>
  );
}

export default PaymentProgress;

