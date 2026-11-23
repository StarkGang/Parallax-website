import { createPortal } from 'react-dom';
import { Check, Loader2, ShieldCheck } from 'lucide-react';
import { money } from '../lib/format.js';

export const PAY_STEPS = [
  ['preparing', 'Payment order created'],
  ['gateway', 'Paid in Razorpay'],
  ['verifying', 'Signature verified'],
];

export const PAY_COPY = {
  preparing: {
    title: 'Securing your checkout',
    detail: 'Initializing an encrypted checkout session with Razorpay...',
  },
  gateway: {
    title: 'Complete payment in Razorpay',
    detail: 'Finish payment in the secure modal. Do not refresh or exit.',
  },
  verifying: {
    title: 'Confirming your payment',
    detail: 'Cryptographic signature received. Confirming credentials...',
  },
  success: {
    title: 'Payment Confirmed',
    detail: 'Transaction verified successfully. Your tickets and entry credentials are confirmed.',
  },
};

/**
 * Clean Material UI payment progress modal.
 * Uses React Portal to mount directly to document.body, avoiding any stacking context clipping.
 */
export function PaymentProgress({ stage, amount, slow, title, subtitle }) {
  if (!stage) return null;
  if (typeof document === 'undefined') return null;

  const copy = PAY_COPY[stage] || PAY_COPY.preparing;
  const activeIndex = PAY_STEPS.findIndex(([key]) => key === stage);
  const isSuccess = stage === 'success';

  const modalNode = (
    <div className="pay-progress-overlay" role="dialog" aria-modal="true" aria-live="polite">
      <div className={`pay-progress-dialog ${isSuccess ? 'is-success' : ''}`}>
        {/* Status Icon */}
        <div className="pay-progress-icon-cell">
          {isSuccess ? (
            <div className="pay-icon-success">
              <Check size={24} strokeWidth={2.5} />
            </div>
          ) : (
            <div className="pay-icon-spinner">
              <Loader2 size={24} strokeWidth={2.2} className="pay-spin" />
            </div>
          )}
        </div>

        <h3 className="pay-progress-headline">{title || copy.title}</h3>
        <p className="pay-progress-subline">{subtitle || copy.detail}</p>

        {amount ? (
          <div className="pay-progress-badge">
            <span className="pay-badge-label">Total Amount</span>
            <span className="pay-badge-value">{money(amount)}</span>
          </div>
        ) : null}

        {/* Stepped Progress Indicator */}
        <ol className="pay-progress-stepper">
          {PAY_STEPS.map(([key, label], index) => {
            const done = isSuccess || index < activeIndex;
            const active = !done && index === activeIndex;
            return (
              <li key={key} className={`pay-step-row ${done ? 'is-done' : active ? 'is-active' : 'is-pending'}`}>
                <div className="pay-step-badge">
                  {done ? (
                    <Check size={12} strokeWidth={3} />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </div>
                <span className="pay-step-text">{label}</span>
                {active ? <Loader2 size={13} strokeWidth={2.4} className="pay-spin pay-step-inline-spin" /> : null}
              </li>
            );
          })}
        </ol>

        {/* Security Assurance */}
        <div className="pay-progress-footer-note">
          <ShieldCheck size={14} className="pay-shield-svg" />
          <span>256-Bit SSL Encrypted · Razorpay Payment Gateway</span>
        </div>

        {slow && !isSuccess ? (
          <div className="pay-progress-notice">
            <span>Still waiting on the banking network. Please keep this window open.</span>
          </div>
        ) : null}
      </div>
    </div>
  );

  return createPortal(modalNode, document.body);
}

export default PaymentProgress;


