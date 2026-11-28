# Changes Summary (`CHANGE.md`)

## 1. `/portal/events` Browse-Only Without Pass
- **`frontend/src/pages/Worklist.jsx`**
  - Added `noActivePass = Boolean(policyAddon && payload?.passStatus !== 'active')` and `cannotBuy = passBlocked || noActivePass`.
  - Event cards on `/portal/events` remain visible to users without an active pass, while add/pay actions are disabled (`Pass required`) so seats cannot be added or purchased without an active pass.

## 2. Category-Change Option Removed
- **`frontend/src/pages/PortalRegistration.jsx`**
  - Removed the `Request Category Change` button, `changeSheet` modal, `CATEGORY CHANGE REQUEST` status panel, and target-category document merge.
- **`frontend/src/pages/AdminRegistration.jsx`**
  - Removed the `CATEGORY CHANGE REQUEST` review/decision panel and `decideChange` handler.
- **`frontend/src/lib/api.js`**
  - Removed `requestCategoryChange`, `categoryChangePayment`, and `decideRegistrationCategoryChange`.
- **`backend/app/api/v1/registration.py`**
  - Removed `POST /category-change` and `GET /category-change/payment`.
- **`backend/app/api/v1/admin_registration.py`**
  - Removed `POST /{registration_id}/category-change`.
- **`backend/app/services/college_registrations.py`**
  - Set `canChangeCategory` to `False` in `serialize_registration`.

## 3. Pass / Entitlement Release & Refund Consistency (Group B + Legacy Cleanup)
- **`backend/app/services/passes.py` (`release_event_entitlements`)**
  - Cancels `confirmed`, `reserved`, and `pending` seats on pass revocation/rejection/suspension, purges team membership, drops attendance, and cancels `IncludedEventSelection` rows.
  - Never calls the payment gateway directly on admin reject/revoke/suspend; when `refund_paid_events=True`, queues one `pending` `Refund` row per paid event order for the finance desk. When `False`, creates no refund row and leaves money as paid and retained.
- **`backend/app/services/college_registrations.py`, `backend/app/services/pricing.py`, `backend/app/services/teams.py`, `backend/app/services/events.py`, `backend/app/services/users.py`, `backend/app/services/payments.py`, `backend/app/services/editions.py`**
  - Enforces seat-before-team (`create_team` / `join_team` require a live seat; `team_fee_basis` and restore-disbanded-team legacy paths removed).
  - Supports partial refunds at reject time (`RegistrationDecision.refundAmountPaise`), surfaces `refundPendingPaise` on bills (`CompleteReceiptSheet.jsx`), and aligns `Portal.jsx` / `Admin.jsx` / `Public.jsx` with the unified worklist flow.
- **`backend/migrations/versions/fdb2d352dbf8_drop_team_fee_basis.py`, `fdb2d352dbf9_drop_dead_policy_and_user_columns.py`**
  - Drops legacy `team_fee_basis` and dead policy/user columns.

## 4. Test Suite Updates (Group A / B / C / D & Category-Change Removal)
- **`backend/tests/seat_helpers.py` & Group A tests (`test_audit03_fixes.py`, `test_college_registration.py`, `test_compliance_deadlines.py`, `test_registration_lifecycle.py`, `test_state_drift.py`, `test_teams_and_editions.py`)**
  - Updated team creation/join fixtures to buy a seat before creating/joining a team (including `email_b` in `test_scenario_5d_suspended_team_leader`, plus `populate_existing=True` on `Team` re-read).
- **Group B tests (`test_audit08_flaws.py`, `test_compliance_deadlines.py`, `test_registration_lifecycle.py`, `test_state_drift.py`)**
  - Updated `test_reject_without_refund_still_parks_the_money` to assert no refund row is created when `initiateRefund=False` and order stays `paid`.
  - Updated `test_document_request_opens_24h_window_then_releases_seat`, `test_scenario_1a_reject_with_finance_and_working_gateway`, and `test_suspension_frees_seats_and_refunds_event_purchases` to assert `release_event_entitlements` queues `pending` refunds without calling the gateway directly (and `1a` processes each queued addon refund via `/admin/refunds/{id}/process`).
- **Group C & D & Category-Change tests**
  - Updated `test_pii_sessions_oauth.py` for edition-scoped `list_users`.
  - Removed obsolete restore-disbanded-team expectation and updated `test_college_registration.py` / `test_compliance_deadlines.py` to assert `404` on the removed `/registration/category-change` endpoint.

## 5. Database Maintenance (Live Supabase Postgres)
- Re-seeded 5 `event_categories` and 12 default `events` from `backend/app/seed.py` plus the 2 custom events (`carroms-tournament`, `warner-war`), and aligned `convention_editions`, `edition_policies`, `registration_settings`, and all non-carroms `events` to **Jan 7–8, 2027 (IST)**.

