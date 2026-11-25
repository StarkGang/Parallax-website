import { portalApi } from './api.js';
import { openCheckout } from './razorpay.js';

/**
 * Run the checkout for one server-priced order and report what happened.
 * The amount always comes from the server; this only opens the gateway.
 */
export async function payOrder(editionId, order, user, title) {
  if (!order) return { status: 'paid' };
  if (order.mock) {
    await portalApi.mockPay(editionId, order.orderId);
    return { status: 'paid' };
  }
  const attendee = {
    ...user,
    fullName: user?.fullName || '',
    email: user?.email || '',
    phone: user?.phone || '',
  };
  const response = await openCheckout(order, attendee, title);
  if (!response) return { status: 'cancelled' };
  if (response.failed) return { status: 'failed', message: response.error?.message };
  await portalApi.verifyPayment(editionId, {
    orderId: order.orderId,
    razorpayPaymentId: response.razorpay_payment_id,
    razorpaySignature: response.razorpay_signature,
  });
  return { status: 'paid' };
}
