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
  return typeof window !== 'undefined' ? (window.__RAZORPAY_KEY_ID__ || '') : '';
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
    let paymentCompleted = false;
    let settled = false;

    const finish = (result) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    const cleanPrefill = {};
    const prefillName = (prefill?.name || user?.fullName || user?.name || '').trim();
    const prefillEmail = (prefill?.email || user?.email || '').trim();
    const prefillPhone = (prefill?.phone || prefill?.contact || user?.phone || user?.contact || user?.mobile || '').trim();
    if (prefillName) cleanPrefill.name = prefillName;
    if (prefillEmail) cleanPrefill.email = prefillEmail;
    if (prefillPhone) cleanPrefill.contact = prefillPhone;

    const options = {
      key: keyId,
      order_id: orderId,
      amount: Math.round(Number(amount)),
      currency: currency || 'INR',
      name: name || 'Parallax 2027',
      description: description || 'Convention Pass',
      theme: {
        color: '#0284c7',
      },
      handler: async (response) => {
        paymentCompleted = true;
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
          if (paymentCompleted) return;
          setTimeout(() => {
            if (paymentCompleted || settled) return;
            if (onDismiss) onDismiss();
            finish({ success: false, dismissed: true, message: 'Payment window closed.' });
          }, 300);
        },
      },
    };

    if (Object.keys(cleanPrefill).length > 0) {
      options.prefill = cleanPrefill;
    }

    if (notes && Object.keys(notes).length > 0) {
      options.notes = notes;
    }

    // Only pass image if valid absolute HTTPS URL exists to prevent mixed-content & undefined parsing errors
    if (typeof window !== 'undefined' && window.location.protocol === 'https:') {
      options.image = `${window.location.origin}/images/parallax-logo.png`;
    }

    let checkout;
    try {
      checkout = new Razorpay(options);
    } catch (err) {
      settled = true;
      reject(err);
      return;
    }

    checkout.on('payment.failed', (failResponse) => {
      // payment.failed fires inside Razorpay for an attempt. Razorpay allows in-modal retries.
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
    let paymentCompleted = false;
    let settled = false;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };

    const keyId = order.razorpayKeyId || order.keyId || order.key || getRazorpayKeyId();
    const gatewayOrderId =
      order.gatewayOrderId ||
      order.gateway_order_id ||
      order.order_id ||
      (typeof order.orderId === 'string' && order.orderId.startsWith('order_') ? order.orderId : null);

    if (!gatewayOrderId && !order.mock) {
      settled = true;
      reject(new Error('Razorpay order ID was not created by the server. Please check your connection and retry.'));
      return;
    }

    const cleanPrefill = {};
    const name = (user?.fullName || user?.name || '').trim();
    const email = (user?.email || '').trim();
    const phone = (user?.phone || user?.contact || user?.mobile || '').trim();
    if (name) cleanPrefill.name = name;
    if (email) cleanPrefill.email = email;
    if (phone) cleanPrefill.contact = phone;

    const options = {
      key: keyId,
      order_id: gatewayOrderId,
      amount: Math.round(Number(order.amountPaise || order.amount)),
      currency: 'INR',
      name: 'Parallax 2027',
      description: description || 'Convention registration',
      theme: {
        color: '#0284c7',
      },
      handler: (response) => {
        paymentCompleted = true;
        finish(response);
      },
      modal: {
        ondismiss: () => {
          if (paymentCompleted) return;
          // Grace period allows handler() to resolve first if Razorpay closes modal during bank callback
          setTimeout(() => {
            if (paymentCompleted || settled) return;
            finish(null);
          }, 300);
        },
      },
    };

    if (Object.keys(cleanPrefill).length > 0) {
      options.prefill = cleanPrefill;
    }

    if (order.orderId || order.id) {
      options.notes = {
        order_id: String(order.orderId || order.id),
      };
    }

    // Only set image if HTTPS to prevent mixed-content or "undefined" image crashes on local development
    if (typeof window !== 'undefined' && window.location.protocol === 'https:') {
      options.image = `${window.location.origin}/images/parallax-logo.png`;
    }

    let checkout;
    try {
      checkout = new Razorpay(options);
    } catch (err) {
      settled = true;
      reject(err);
      return;
    }

    // Informational listener: let attendee retry inside Razorpay modal without killing the promise
    checkout.on('payment.failed', (failResp) => {
      console.warn('Razorpay payment attempt declined or failed:', failResp?.error?.description);
    });

    try {
      checkout.open();
    } catch (error) {
      settled = true;
      reject(error);
    }
  });
}
