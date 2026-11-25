/**
 * Razorpay Standard Web Checkout Integration.
 *
 * Loads the checkout.js SDK on demand and opens the modal for an order that
 * the backend already created and priced. Signature verification and
 * fulfilment live in the edition-scoped payment endpoints.
 */

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
 * Opens the checkout modal for a server-priced order. The order carries exactly
 * orderId, amountPaise, gatewayOrderId, razorpayKeyId and mock.
 */
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

    const keyId = order.razorpayKeyId || getRazorpayKeyId();
    const gatewayOrderId = order.gatewayOrderId;

    if (!gatewayOrderId && !order.mock) {
      settled = true;
      reject(new Error('Razorpay order ID was not created by the server. Please check your connection and retry.'));
      return;
    }

    const cleanPrefill = {};
    const name = (user?.fullName || '').trim();
    const email = (user?.email || '').trim();
    const phone = (user?.phone || '').trim();
    if (name) cleanPrefill.name = name;
    if (email) cleanPrefill.email = email;
    if (phone) cleanPrefill.contact = phone;

    const options = {
      key: keyId,
      order_id: gatewayOrderId,
      amount: Math.round(Number(order.amountPaise)),
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

    if (order.orderId) {
      options.notes = { order_id: String(order.orderId) };
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
