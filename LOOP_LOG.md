# Audit HIGH Fix Loop Log

Starting commit (baseline): 7d4a9b66286975336be3afe9235543cf3001612c
Branch: audit-high-fixes

## Baseline (before any fix)
- Backend: `pytest tests/test_payment_fixes.py tests/test_payment_audit.py tests/test_razorpay_checkout.py tests/test_platform_fees.py tests/test_pricing_release_lunch.py -q` => 20 passed.
- Frontend: `npm run build` => clean (only a PLUGIN_TIMINGS warning, not an error).

## Fixes applied (one commit each)
1. approve_event_registration import Registration from commerce
2. revoked ticket no longer verifies as valid pass
3. reject amountPaise<=0 refund instead of refunding full fee
4. partial refund no longer hides the pass in the portal
5. force-cancel expires unpaid created order when unshared
6. force-cancel drops the attendee's attendance record
7. verify_payment rejects refunded/failed orders
8. verify_payment rejects caller payment id when payments off outside dev/mock
9. lock order row in refund_order to prevent double-refund race

## Rounds
(round entries appended below)

### Round 1
- Baseline: 5-file backend command => 20 passed (unchanged). Frontend build => clean.
- Re-reviewed all 9 hunks vs starting commit.
- Suspicion checks run:
  - No internal `RefundAction(amount_paise=0)` construction in app code (schema gt=0 only affects API boundary). PASS.
  - "failed" order status is set only when gateway order creation fails (payments.py:172) => terminal, cannot be paid; Fix 7 rejection is safe. PASS.
  - No `refund_order` caller reads the passed `order` after the call => Fix 9 `order = locked` reassignment is safe. PASS.
  - `func`/`select`/`PaymentOrder` already imported in admin.py/payments.py. PASS.
  - Broader suites: test_event_cancellation_and_attendance fully passed. test_registration_lifecycle has 6 failures that ALSO fail on the starting commit (pre-existing, verified by reverting backend/app to 7d4a9b6). test_audit03/08/college_registration have pre-existing ordering failures (verified earlier).
- New real bugs found: 0.
- Stop condition hit: a full round found 0 new real bugs.

### Round 2 (user answered Q1 + Q2)
- Q2 (align all three expiry paths): added shared helper `expire_order_if_unshared`
  in `payments.py`; used by `registrations.cancel_registration`, `pricing.remove_seat`,
  and `admin.force_cancel_registration`. Expires a `created` order only when no other
  non-cancelled registration references it AND no `Team.order_id` owns it (team orders
  are excluded entirely — team lifecycle owns them). Confirmed Registration statuses are
  exactly {confirmed, reserved, pending, cancelled} (`LIVE_SEAT_STATUSES`, pricing.py:47),
  so `!= "cancelled"` == `IN (confirmed,reserved,pending)`.
- Q1 (expired verify): expired orders are allowed to revive after the existing gateway
  amount/order-id re-confirmation (payments_enabled path); added `expired_order_revived`
  log. Prod-like (payments off, not mock) still rejected by Fix 8.
- Tests: solo→expired, shared→kept, team→kept for cancel_registration, remove_seat,
  force_cancel; expired dev revival→paid; expired+bad signature→stays expired.
- Baseline: 5-file => 20 passed (unchanged); +audit => 51 passed. Frontend build clean.
- New real bugs found: 0. No open decisions remain from this round.