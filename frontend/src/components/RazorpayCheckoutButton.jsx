import { useState } from 'react';
import { Check, CreditCard, Loader2, ShieldCheck, AlertCircle } from 'lucide-react';
import {
  createRazorpayOrder,
  openStandardCheckout,
  verifyRazorpayPayment,
} from '../lib/razorpay.js';
import { money } from '../lib/format.js';

/**
 * Standard Razorpay Checkout Button Component.
 *
 * Implements the 3-step checkout flow:
 * 1. POST /api/create-order
 * 2. Razorpay Modal checkout
 * 3. POST /api/verify-payment
 */
export function RazorpayCheckoutButton({
  amount = 50000, // in paise (50000 = ₹500)
  currency = 'INR',
  name = 'Parallax 2027',
  description = 'Convention Pass',
  receipt = null,
  prefill = null,
  user = null,
  buttonText = null,
  className = '',
  onPaymentSuccess = null,
  onPaymentFailure = null,
}) {
  const [status, setStatus] = useState('idle'); // 'idle' | 'creating' | 'checkout' | 'verifying' | 'success' | 'error'
  const [errorMessage, setErrorMessage] = useState(null);
  const [paymentDetails, setPaymentDetails] = useState(null);

  const handleCheckout = async () => {
    setStatus('creating');
    setErrorMessage(null);
    setPaymentDetails(null);

    try {
      // Step 1: Call backend to create Razorpay Order
      const orderData = await createRazorpayOrder({
        amount,
        currency,
        receipt: receipt || `rcpt_${Date.now()}`,
      });

      const orderId = orderData.order_id || orderData.orderId;
      if (!orderId) {
        throw new Error('No order ID received from the server.');
      }

      setStatus('checkout');

      // Step 2: Open Razorpay modal with order_id
      const checkoutResult = await openStandardCheckout({
        orderId,
        amount: orderData.amount || amount,
        currency: orderData.currency || currency,
        key: orderData.key_id || orderData.keyId,
        name,
        description,
        user,
        prefill,
        onSuccess: async (razorpayResponse) => {
          // Step 3: Send verification payload to backend
          setStatus('verifying');
          try {
            const verification = await verifyRazorpayPayment({
              razorpay_order_id: razorpayResponse.razorpay_order_id,
              razorpay_payment_id: razorpayResponse.razorpay_payment_id,
              razorpay_signature: razorpayResponse.razorpay_signature,
            });

            setStatus('success');
            setPaymentDetails({
              paymentId: razorpayResponse.razorpay_payment_id,
              orderId: razorpayResponse.razorpay_order_id,
            });

            if (onPaymentSuccess) {
              onPaymentSuccess({
                ...razorpayResponse,
                verification,
              });
            }
          } catch (verifyErr) {
            setStatus('error');
            setErrorMessage(verifyErr.message || 'Payment signature verification failed.');
            if (onPaymentFailure) onPaymentFailure(verifyErr);
          }
        },
        onDismiss: () => {
          setStatus('idle');
          setErrorMessage('Payment window was closed before completion.');
        },
        onFailed: (failedResp) => {
          setStatus('error');
          const reason =
            failedResp?.error?.description ||
            failedResp?.error?.reason ||
            'Payment transaction failed.';
          setErrorMessage(reason);
          if (onPaymentFailure) onPaymentFailure(failedResp);
        },
      });

      if (!checkoutResult.success && !checkoutResult.dismissed && checkoutResult.error) {
        setStatus('error');
        setErrorMessage(checkoutResult.error.message || 'Payment was not completed.');
      }
    } catch (err) {
      setStatus('error');
      setErrorMessage(err.message || 'Could not initiate Razorpay checkout.');
      if (onPaymentFailure) onPaymentFailure(err);
    }
  };

  const isLoading = status === 'creating' || status === 'checkout' || status === 'verifying';

  return (
    <div className={`razorpay-checkout-wrap ${className}`}>
      <button
        type="button"
        className="razorpay-checkout-btn"
        onClick={handleCheckout}
        disabled={isLoading}
      >
        <span className="rzp-btn-icon">
          {isLoading ? (
            <Loader2 size={16} className="spin is-spinning" />
          ) : status === 'success' ? (
            <Check size={16} />
          ) : (
            <CreditCard size={16} />
          )}
        </span>
        <span className="rzp-btn-text">
          {isLoading
            ? status === 'verifying'
              ? 'Verifying Signature…'
              : 'Opening Razorpay…'
            : status === 'success'
              ? 'Payment Verified'
              : buttonText || `Pay with Razorpay (${money(amount)})`}
        </span>
      </button>

      {status === 'success' && paymentDetails ? (
        <div className="rzp-alert is-success" role="alert">
          <ShieldCheck size={15} />
          <div>
            <strong>Payment Verified Successfully!</strong>
            <small>Payment ID: {paymentDetails.paymentId}</small>
          </div>
        </div>
      ) : null}

      {errorMessage ? (
        <div className="rzp-alert is-error" role="alert">
          <AlertCircle size={15} />
          <div>
            <strong>Payment Issue:</strong> {errorMessage}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default RazorpayCheckoutButton;

