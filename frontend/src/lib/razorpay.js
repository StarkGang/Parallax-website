/**
 * Razorpay Standard Web Checkout Integration.
 *
 * Implements:
 * 1. Loading the checkout.js SDK dynamically if not in index.html
 * 2. Creating orders via POST /api/create-order
 * 3. Opening the Razorpay standard modal with proper options and theme
 * 4. Verifying payment signatures via POST /api/verify-payment
 * 5. Event handling for modal dismissal and payment.failed
 */

import { api } from './api.js';

export function getRazorpayKeyId() {
  return (
    import.meta.env.VITE_RAZORPAY_KEY_ID ||
    window.__RAZORPAY_KEY_ID__ ||
    'rzp_test_U2P4j5SmTptx2Z'
  );
}

export function loadRazorpay() {
  return new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.Razorpay) {
      return resolve(window.Razorpay);
    }
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.onload = () => resolve(window.Razorpay);
    script.onerror = () => reject(new Error('Could not load the Razorpay payment gateway.'));
    document.head.appendChild(script);
    return undefined;
  });
}

/**
 * Step 1: Request order creation from backend.
 * Calls /api/create-order (or /api/v1/create-order).
 */
export async function createRazorpayOrder({ amount, currency = 'INR', receipt = null, notes = null }) {
  try {
    return await api('/create-order', {
      method: 'POST',
      body: { amount, currency, receipt, notes },
    });
  } catch (err) {
    // Also try direct relative /api/create-order if API_BASE differed
    const res = await fetch('/api/create-order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount, currency, receipt, notes }),
    });
    const data = await res.json();
    if (!res.ok) {
      const msg = data.error?.message || data.detail || 'Failed to create order';
      throw new Error(msg);
    }
    return data;
  }
}

/**
 * Step 3: Verify the payment signature on backend.
 * Calls /api/verify-payment (or /api/v1/verify-payment).
 */
export async function verifyRazorpayPayment({
  razorpay_order_id,
  razorpay_payment_id,
  razorpay_signature,
}) {
  const payload = {
    razorpay_order_id,
    razorpay_payment_id,
    razorpay_signature,
  };
  try {
    return await api('/verify-payment', {
      method: 'POST',
      body: payload,
    });
  } catch (err) {
    const res = await fetch('/api/verify-payment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      const msg = data.error?.message || data.detail || 'Payment verification failed';
      throw new Error(msg);
    }
    return data;
  }
}

/**
 * Step 2: Open Razorpay Checkout modal and handle flow.
 */
export async function openStandardCheckout({
  orderId,
  amount,
  currency = 'INR',
  key = null,
  name = 'Parallax 2027',
  description = 'Convention Pass',
  user = null,
  prefill = null,
  notes = null,
  onSuccess,
  onDismiss,
  onFailed,
}) {
  const Razorpay = await loadRazorpay();
  const keyId = key || getRazorpayKeyId();

  return new Promise((resolve, reject) => {
    let settled = false;
    let lastFailure = null;

    const finish = (result) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    const logoUrl =
      typeof window !== 'undefined'
        ? `${window.location.origin}/favicon.png`
        : undefined;

    const options = {
      key: keyId,
      order_id: orderId,
      amount,
      currency,
      name: name || 'Parallax 2027',
      description,
      image: logoUrl,
      prefill: {
        email: prefill?.email || user?.email || '',
        name: prefill?.name || user?.fullName || user?.name || '',
        contact: prefill?.phone || prefill?.contact || user?.phone || '',
      },
      notes: notes || {},
      theme: {
        color: '#0284c7',
        backdrop_color: 'rgba(5, 7, 10, 0.88)',
      },
      handler: async (response) => {
        try {
          if (onSuccess) {
            await onSuccess(response);
          }
          finish({ success: true, response });
        } catch (err) {
          finish({ success: false, error: err });
        }
      },
      modal: {
        ondismiss: () => {
          if (onDismiss) onDismiss();
          if (lastFailure) {
            const errorMsg =
              lastFailure?.error?.description ||
              lastFailure?.error?.reason ||
              'Payment failed or was declined by the bank.';
            finish({
              success: false,
              failed: true,
              dismissed: true,
              error: new Error(errorMsg),
              details: lastFailure,
            });
          } else {
            finish({ success: false, dismissed: true, message: 'Payment cancelled by user.' });
          }
        },
      },
    };

    const checkout = new Razorpay(options);

    // Razorpay standard checkout: payment.failed fires when a payment attempt fails.
    // The checkout modal DOES NOT close, allowing the user to retry or switch methods.
    // Do not settle/terminate the promise here so retried payments can succeed.
    checkout.on('payment.failed', (failResponse) => {
      lastFailure = failResponse;
      if (onFailed) onFailed(failResponse);
    });

    try {
      checkout.open();
    } catch (error) {
      settled = true;
      reject(error);
    }
  });
}

/** Backwards-compatible helper for existing portal code */
export async function openCheckout(order, user, description = 'Convention registration') {
  const Razorpay = await loadRazorpay();
  return new Promise((resolve, reject) => {
    let settled = false;
    let lastFailure = null;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const logoUrl =
      typeof window !== 'undefined'
        ? `${window.location.origin}/favicon.png`
        : '';
    const phone = user?.phone || user?.contact || user?.mobile || '';

    const checkout = new Razorpay({
      key: order.razorpayKeyId || getRazorpayKeyId(),
      order_id: order.gatewayOrderId,
      amount: order.amountPaise,
      currency: 'INR',
      name: 'Parallax 2027',
      description,
      image: logoUrl,
      prefill: {
        email: user?.email || '',
        name: user?.fullName || user?.name || '',
        contact: phone,
      },
      theme: {
        color: '#0284c7',
        backdrop_color: 'rgba(5, 7, 10, 0.88)',
      },
      handler: (response) => finish(response),
      modal: {
        ondismiss: () => {
          if (lastFailure) {
            const reason =
              lastFailure?.error?.description ||
              lastFailure?.error?.reason ||
              'Payment transaction declined or failed.';
            finish({ failed: true, error: new Error(reason), details: lastFailure });
          } else {
            finish(null);
          }
        },
        backdropclose: false,
      },
    });

    // An individual payment attempt failure (wrong OTP, card decline) allows user retry
    // inside the open Razorpay modal. Store the last failure and let handler settle on retry success.
    checkout.on('payment.failed', (failResp) => {
      lastFailure = failResp;
    });

    try {
      checkout.open();
    } catch (error) {
      settled = true;
      reject(error);
    }
  });
}
