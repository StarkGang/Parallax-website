# Git Changes

## Summary

The working tree is clean apart from follow-up edits still in progress while this review ran. The change set under review is commit `7e30145 fix!` (parent `56ed12c`), 63 files, +11,427 / -1,584 lines. It removes the old eligibility-verification and event-coordinator features, adds refund/seat-release guarantees (edition cancel, pass rejection, suspension, 24-hour compliance windows, read-path lazy sweeps), adds idempotency to money-moving POSTs, and adds four Alembic migrations plus a large new regression suite. Backend tests currently show 7 failures, all inside the new test files; frontend build and frontend tests pass.

## Files Changed

| File | Status | What changed |
| --- | --- | --- |
| `.gitignore` | Modified | Ignores `/docs/audits/` and `AUDIT*.md` |
| `BACKEND.md` | Modified | Documents compliance windows, refunds, sweeps |
| `backend/app/api/deps.py` | Modified | Drops coordinator assignments and `require_event_access` |
| `backend/app/api/v1/admin.py` | Modified | Removes verification endpoints, adds compliance sweep route, attendance dedupe, cancel/refund guards, icon permission |
| `backend/app/api/v1/admin_registration.py` | Modified | Lazy sweep on desk list/detail, splits refund flag from permission |
| `backend/app/api/v1/auth.py` | Modified | Passes invite token through signed state |
| `backend/app/api/v1/participant.py` | Modified | Lazy sweep on pass/teams/registrations, pass gate, idempotency, team payment payload |
| `backend/app/api/v1/public.py` | Modified | Sweep before cached catalogue reads, richer credential validity |
| `backend/app/api/v1/registration.py` | Modified | Sweep on read, idempotent submit |
| `backend/app/core/config.py` | Modified | `expiry_sweep_enabled` now defaults to True |
| `backend/app/core/permissions.py` | Modified | Removes verifier role/permission, fixes step-up action names |
| `backend/app/core/rate_limit.py` | Modified | Rounds retry-after up, never 0 when blocked |
| `backend/app/core/sessions.py` | Modified | MFA step-up no longer extends absolute session cap |
| `backend/app/integrations/email.py` | Modified | Skipped rows without provider, retry backoff, failed-send alerts |
| `backend/app/main.py` | Modified | Startup and periodic sweeps (orders, compliance, idempotency, invites) |
| `backend/app/models/__init__.py` | Modified | Un-exports removed models |
| `backend/app/models/commerce.py` | Modified | Drops pass order link, keeps Registration.team_id |
| `backend/app/models/edition.py` | Modified | Drops verification and coordinator tables/columns |
| `backend/app/models/registration.py` | Modified | Adds compliance columns and index |
| `backend/app/models/user.py` | Modified | Drops verification fields |
| `backend/app/schemas/__init__.py` | Modified | Drops removed schema exports |
| `backend/app/schemas/admin.py` | Modified | Removes verification schemas, keeps stale `__all__` entry |
| `backend/app/schemas/auth.py` | Modified | Drops verification fields |
| `backend/app/schemas/participant.py` | Modified | Drops email confirmation schema |
| `backend/app/seed.py` | Modified | Seeds super admin, drops allowed domains |
| `backend/app/services/__init__.py` | Modified | Un-exports verification service |
| `backend/app/services/college_registrations.py` | Modified | Compliance windows, refund plan/guards, late-payment handling |
| `backend/app/services/editions.py` | Modified | Booking gate, edition cancel cascade, dashboard per-unit counts |
| `backend/app/services/events.py` | Modified | Capacity per unit, seats-left, close-event cascade |
| `backend/app/services/icons.py` | Modified | Archived icons not reseeded, archive blocked while in use |
| `backend/app/services/passes.py` | Modified | Seat release, ticket revoke, pass gate, demotion rules |
| `backend/app/services/payments.py` | Modified | Legacy pass orders park a refund instead of activating |
| `backend/app/services/registrations.py` | Modified | Own-registrations only, stricter reservation expiry |
| `backend/app/services/teams.py` | Modified | Leader handover, paid team seats, purge rules |
| `backend/app/services/tickets.py` | Modified | Registration number resolves only the pass ticket |
| `backend/app/services/users.py` | Modified | Suspension cascade, invite-token claiming |
| `backend/app/services/verification.py` | Deleted | Feature removed |
| `backend/migrations/versions/fdb2d352dbe4_drop_eligibility_verification.py` | Added | Drops verification tables |
| `backend/migrations/versions/fdb2d352dbe5_drop_dead_coordinator_and_policy_cols.py` | Added | Drops dead coordinator/policy columns |
| `backend/migrations/versions/fdb2d352dbe6_attendance_pass_day_unique.py` | Added | Attendance unique per pass/day |
| `backend/migrations/versions/fdb2d352dbe7_drop_dead_columns_and_unique_pending_change.py` | Added | Drops dead columns, one pending category change |
| `backend/migrations/versions/fdb2d352dbe8_registration_compliance_windows.py` | Added | Adds compliance columns and index |
| `backend/tests/conftest.py` | Modified | Test env adjustments |
| `backend/tests/lifecycle_helpers.py` | Added | Lifecycle fixtures, snapshots, invariants |
| `backend/tests/test_audit03_fixes.py` | Added | Regression tests for audit fixes |
| `backend/tests/test_audit08_flaws.py` | Added | Regression tests for audit flaws |
| `backend/tests/test_auth.py` | Modified | Updated for invite/verification removal |
| `backend/tests/test_college_registration.py` | Modified | Extra registration tests |
| `backend/tests/test_compliance_deadlines.py` | Added | 24-hour window and lazy sweep tests |
| `backend/tests/test_email_outbox.py` | Modified | Skipped-row and backoff tests |
| `backend/tests/test_email_verification.py` | Deleted | Feature removed |
| `backend/tests/test_event_cancellation_and_attendance.py` | Modified | Attendance dedupe expectations |
| `backend/tests/test_payment_audit.py` | Modified | Refund/legacy-order expectations |
| `backend/tests/test_registration_lifecycle.py` | Added | End-to-end lifecycle scenarios |
| `backend/tests/test_state_drift.py` | Added | State-drift guard tests |
| `backend/tests/test_teams_and_editions.py` | Added | Team/edition cascade tests |
| `backend/tests/test_workflow_guards.py` | Modified | Selection/cancel guard test |
| `frontend/src/App.jsx` | Modified | Removes verifications route |
| `frontend/src/lib/api.js` | Modified | Removes verification API methods |
| `frontend/src/pages/Admin.jsx` | Modified | Removes verification queue, suspension warning, net revenue |
| `frontend/src/pages/AdminRegistration.jsx` | Modified | Compliance stats, filters, deadline panel, reject warning |
| `frontend/src/pages/Portal.jsx` | Modified | Shared checkout helper, team seat payment, pass-state gates, disband confirm |
| `frontend/src/pages/PortalRegistration.jsx` | Modified | Compliance banner, resubmission panel, rejected/refunded view, receipt lines |

Four of these files (`backend/app/api/v1/admin.py`, `backend/app/services/passes.py`, `backend/tests/lifecycle_helpers.py`, `backend/tests/test_registration_lifecycle.py`) also have uncommitted edits that were being written during this review, so line numbers and test results below are a moving target.

## Sanity Check

| Check | Result | Key output |
| --- | --- | --- |
| Logic / null access / off-by-one review of changed hunks | Pass | No defect found in the hunks reviewed (see issues for the two loose ends) |
| Broken imports or stale symbol references | Fail | `VerificationRow` still exported |
| Leftover debug code (`console.log`, `debugger`, `pdb`, new TODO/FIXME) | Pass | None on added lines |
| Hardcoded secrets | Pass | None on added lines |
| Unrelated or generated noise (build output, logs, lockfiles) | Pass | `frontend/dist` is ignored, no generated files staged |
| Backend tests (`python -m pytest -q`) | Fail | 7 failed, 174 passed at 18:52 |
| Backend lint, type check | Skipped | No `ruff`, `flake8` or `mypy` installed in the venv; ruff has no config for a substitute tool |
| Frontend build (`npm run build`) | Pass | Vite build succeeded |
| Frontend tests (`npm test`) | Pass | 8/8 |
| Alembic revision graph (`alembic heads`) | Pass | Single head `fdb2d352dbe8` |
| `alembic upgrade head` on SQLite | Skipped | Older revision uses Postgres-only `DROP COLUMN IF EXISTS` |

### Issues

1. `backend/app/schemas/admin.py:352` (low). `__all__` still lists `"VerificationRow"`, but the class was deleted with the verification feature. Nothing imports it with `*`, so it is dead metadata rather than an import error. Fix: delete that line.

2. `backend/tests/test_registration_lifecycle.py` (medium). 6 of the new lifecycle scenarios fail, and each failure is an expectation that the implementation or the test environment contradicts rather than a crash in shipped code:
   - `test_scenario_1a...`: asserts the pass refund equals total collected, but add-on orders are refunded separately (29900 vs 44900).
   - `test_scenario_1c...` and `1e...`: expect `refundStatus == "failed"`, but with `PAYMENTS_ENABLED=false` no gateway call is attempted, so it stays `initiated`.
   - `test_scenario_1d...`: calls `admin_approve` without a permitted login, gets 403, then asserts on a stale response.
   - `test_scenario_1b...`: the invariant reads `refund_status=not_initiated` after completion, consistent with the shared test session not seeing the API commit.
   - `test_scenario_2f...`: expects resubmission to work while the edition policy disables it (409 `RESUBMISSION_DISABLED`).
   Fix: align these tests with per-order refunds, payments-disabled behaviour, required logins, fresh session reads, and the resubmission policy flag. If any expectation is the intended product behaviour, fix the code instead.

3. `backend/tests/test_workflow_guards.py:169` (medium). The new test selects 1 included event and expects 200, but the policy mode is exact with `included_event_count=3`, so the API returns 422. Fix: select exactly 3 eligible events or set the policy to up-to.

4. `backend/app/api/v1/registration.py:222-228` and `backend/app/api/v1/participant.py:159-173` (low). The idempotency record is written in a second commit after the booking commit. If that second commit fails or the process dies between them, a retry with the same key books and charges again. Fix: store the record in the same transaction as the booking.

## Risks

- This is a very large behavioural commit in one step (11.4k added lines). The four migrations drop verification/coordinator tables and dead columns; they are irreversible through `downgrade` for the data they remove. Take a database backup before running `alembic upgrade head` in production and rehearse on a copy.
- `expiry_sweep_enabled` now defaults to True. Any deployment that relied on the old default (or on a separate cron) will now also sweep unpaid orders, compliance windows, idempotency keys and invites on startup and every 15 minutes.
- Setting an edition status to `cancelled` through the settings PATCH now triggers a cascade that closes events, cancels passes and queues refunds for every paid order. A typo in that field is no longer a label change.
- GET handlers (public catalogue, participant pages, admin dashboards and desk) can now commit, because the lazy compliance sweep writes when it enforces. This is intended but makes read endpoints non-read-only under load.
- The commit's own guarantees are not yet proven: the added regression suite is red, so the refund, seat-release and suspension behaviour it exists to protect is unverified until those tests pass.
- Edits were still being written in three source/test files while this review ran. Re-run the suite on a frozen tree before trusting the pass counts above.

## Suggested Commit Message

```
fix: make pass rejection, cancellation and holds refund and release seats consistently

- add 24-hour compliance windows with lazy and cron enforcement, seat release, refunds and team leader handover
- cascade pass rejection, suspension, event close and edition cancel through tickets, seats, teams and refunds
- make add-on bookings and registration submit idempotent, gate event selection on pass/account state
- remove the dead eligibility-verification and event-coordinator features with migrations
- fix session step-up caps, rate-limit retry-after, email retry backoff and attendance dedupe
```
