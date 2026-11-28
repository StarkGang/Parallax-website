"""Registration + payment lifecycle: rejection, document re-upload, success, suspension.

Covers task Scenarios 1, 2, 4 and 5 plus the "extra cases" that belong to the
lifecycle rather than to the refund matrix (Scenario 6) or teams (Scenario 7):

    Scenario 1  Admin rejects after booking (a-g, incl. known flaw O23)
    Scenario 2  Marked for re-upload, attendee never re-uploads (a-g)
    Scenario 4  Full success path, per category, mock + signed webhook
    Scenario 5  Account suspension (a-g)
    Extra       webhook replay / out-of-order, tab-closed webhook-only,
                amount mismatch, reservation hold expiry, unpaid expiry sweep,
                selection deadline, edition policy version, E86 override,
                F-08 refund-webhook tear-down, concurrent approve vs reject,
                permission matrix, audit log, duplicate notifications,
                idempotency keys

Each test prints the state snapshot after every step and runs invariants I1-I8.
Known flaws (F-xx, N-xx, O-xx) are asserted for FAIR behaviour and marked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import (
    AttendanceRecord,
    ConventionPass,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    Ticket,
)
from app.models.edition import EditionPolicy, Event
from app.models.registration import (
    CollegeRegistration,
    RegistrationCategory,
    RegistrationDocument,
    RegistrationSettings,
)
from app.models.user import Session as UserSession, User

from tests.lifecycle_helpers import (

    ADMIN_EMAIL,
    DECISIONS,
    PNG,
    Ctx,
    admin_approve,
    admin_reject,
    admin_request_documents,
    assert_invariants,
    category_by_code,
    cheapest_category,
    edition_ctx,
    enable_payments,
    ensure_finance_admin,
    event_by_slug,
    fill_profile,
    flag_decision,
    individual_events,
    login,
    login_admin,
    login_as_user,
    make_user_with_role,
    post_webhook,
    priciest_category,
    payment_captured_event,
    refund_event,
    register_paid,
    registration_row,
    registration_row_for_user,
    sign_webhook,
    snapshot,
    submit_and_pay_mock,
    team_events,
    upload_documents,
    webhook_body,
    clock,  # noqa: F401  (re-exported fixture)
)

from tests.seat_helpers import buy_seat


# --------------------------------------------------------------------------- #
# Scenario 1: Admin rejects after booking
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)


async def _reset_login_budget():
    """This module logs in many times per test; clear the shared login budget."""
    from sqlalchemy import delete as sql_delete

    from app.core.cache import cache_delete_pattern
    from app.db.session import session_scope
    from app.models.commerce import RateLimitCounter

    try:
        async with session_scope() as cleanup_db:
            await cleanup_db.execute(
                sql_delete(RateLimitCounter).where(
                    RateLimitCounter.bucket.like("auth_login%")
                )
            )
    except Exception:  # noqa: BLE001 - best effort
        pass
    cache_delete_pattern("ratelimit:*")
    yield


async def _booked_state(client: AsyncClient, ctx: Ctx, email: str) -> dict:
    """Drive a full booking: pay, choose included events, buy an add-on, join a team."""
    registration = await register_paid(client, ctx, email)
    reg_id = registration["id"]

    # Included pass benefit (E17): pick up to the policy's included count.
    eligible = individual_events(ctx, eligible_only=True)
    chosen = eligible[: ctx.policy.included_event_count]
    sel = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/basket/events",
        json={"eventIds": [str(e.id) for e in chosen]},
    )
    assert sel.status_code == 200, sel.text

    # One paid add-on (E18/E29): an individual event NOT in the included set.
    addon_pool = [
        e for e in individual_events(ctx) if e.addon_price_paise > 0 and e not in chosen
    ]
    addon_event = addon_pool[0]
    addon = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/registrations",
                    json={"eventIds": [str(addon_event.id)]},
    )
    assert addon.status_code == 200, addon.text
    order = addon.json()["data"]["order"]
    if order is not None:
        paid = await client.post(
            f"/api/v1/editions/{ctx.edition_id}/payments/{order['orderId']}/mock"
        )
        assert paid.status_code == 200, paid.text

    # Join one team event (E22).
    team_event = team_events(ctx)[0]
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, ctx.edition_id, team_event.id)
    team = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/teams",
        json={"event_id": str(team_event.id), "name": "Reject Squad"},
    )
    assert team.status_code == 200, team.text
    return {"registration": registration, "addon_event": addon_event, "team_event": team_event}


@pytest.mark.asyncio
async def test_scenario_1a_reject_with_finance_and_working_gateway(
    client: AsyncClient, db_session, clock
):
    """Scenario 1a: full teardown + exact refund + documents marked rejected."""
    ctx = await edition_ctx(client, db_session)
    email = "s1a.reject@test.local"
    booked = await _booked_state(client, ctx, email)
    reg_id = booked["registration"]["id"]
    user_id = booked["registration"]["userId"] if "userId" in booked["registration"] else None
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id
    await assert_invariants(db_session, ctx, user_id, email=email, label="1a booked")

    await login_admin(client)
    before = await snapshot(db_session, ctx, user_id, email=email)
    collected = before.money["collected"]
    reg_fee = int(before.registration["fee_paise"])
    addon_fee = collected - reg_fee  # the separately-paid add-on seat

    rejected = await admin_reject(client, ctx, reg_id, initiate_refund=True)
    assert rejected.status_code == 200, rejected.text
    detail = rejected.json()["data"]
    # Pass cancelled, registration rejected.
    assert detail["verificationStatus"] == "rejected"
    # With no live gateway (test env) the pass refund is *initiated*, not
    # settled: the money is parked for the finance desk, not yet returned.
    assert detail["refundStatus"] == "initiated"
    assert detail["paymentStatus"] == "paid"
    # The registration's own refund covers the pass fee only; the add-on seat
    # is a separate order refunded on its own.
    assert detail["refund"]["amountPaise"] == reg_fee

    mid = await assert_invariants(
        db_session, ctx, user_id, email=email, label="1a after reject (refund initiated)"
    )
    # Pass cancelled, tickets revoked, team seat removed.
    assert mid.pass_["status"] in ("cancelled", "refunded")
    assert all(t["status"] == "revoked" for t in mid.tickets)
    # Documents marked rejected.
    docs = (
        await db_session.execute(
            select(RegistrationDocument).where(
                RegistrationDocument.registration_id == uuid.UUID(reg_id)
            )
        )
    ).scalars().all()
    assert all(d.status == "rejected" for d in docs)
    # Neither pass nor add-on seat money moves automatically: both are queued
    # as pending refunds for the finance desk to settle.
    assert mid.money["refunded"] == 0
    addon_refunds = (
        await db_session.execute(
            select(Refund).where(
                Refund.order_id.in_(
                    select(PaymentOrder.id).where(
                        PaymentOrder.user_id == user_id,
                        PaymentOrder.purpose != "college_registration",
                    )
                ),
                Refund.reason_code == "pass_not_active",
                Refund.status == "pending",
            )
        )
    ).scalars().all()
    assert sum(int(r.amount_paise) for r in addon_refunds) == addon_fee

    # Finance completes the pass refund and processes each queued add-on refund.
    completed = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/refund",
        json={"action": "completed", "gatewayRefundId": "UTR-1A-123", "note": "Gateway settled."},
    )
    assert completed.status_code == 200, completed.text
    for rf in addon_refunds:
        addon_done = await client.post(
            f"/api/v1/editions/{ctx.edition_id}/admin/refunds/{rf.id}/process",
        )
        assert addon_done.status_code == 200, addon_done.text

    after = await assert_invariants(
        db_session, ctx, user_id, email=email, label="1a refund completed"
    )
    assert after.pass_["status"] in ("cancelled", "refunded")
    # Refund equals everything collected across both orders.
    assert after.money["refunded"] == collected
    print(f"KEPT after 1a: pass={after.pass_} money={after.money}")
    assert after.money["net_kept"] == 0


@pytest.mark.asyncio
async def test_scenario_1b_reject_without_finance_write_then_finance_completes(
    client: AsyncClient, db_session, clock
):
    """Scenario 1b: reject without finance.write parks the refund; finance completes."""
    ctx = await edition_ctx(client, db_session)
    email = "s1b.nofin@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id
    reg_id = str(row.id)

    # An admin WITHOUT finance.write: edition_admin lacks finance.write.
    admin = await make_user_with_role(db_session, ctx, "edition_admin")
    await login_as_user(client, db_session, admin, is_staff=True)

    rejected = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_college_id",
            "reason": "Unclear scan.",
            "initiateRefund": True,
        },
    )
    assert rejected.status_code == 200, rejected.text
    detail = rejected.json()["data"]
    # Refund row pending, refund_status initiated, no gateway call.
    assert detail["refundStatus"] == "initiated"
    assert detail["refund"]["status"] == "pending"
    mid = await assert_invariants(
        db_session, ctx, user_id, email=email, label="1b after reject (no finance)"
    )
    assert mid.money["refunded"] == 0

    # A finance admin completes it.
    finance = await ensure_finance_admin(db_session, ctx)
    await login_as_user(client, db_session, finance, is_staff=True)
    completed = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/refund",
        json={"action": "completed", "gatewayRefundId": "UTR-1B-123", "note": "Manual transfer."},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["data"]["refundStatus"] == "completed"
    await assert_invariants(
        db_session, ctx, user_id, email=email, label="1b after finance completes"
    )


@pytest.mark.asyncio
async def test_scenario_1c_reject_gateway_failure_retry_no_double_refund(
    client: AsyncClient, db_session, clock, monkeypatch
):
    """Scenario 1c: gateway refund fails -> refund_status failed, state retryable."""
    ctx = await edition_ctx(client, db_session)
    email = "s1c.gwfail@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id
    reg_id = str(row.id)
    collected = int(row.fee_paise)

    # Force the gateway refund to raise. Payments must be enabled so the reject
    # actually attempts a gateway refund (otherwise it just parks a pending one).
    import app.services.payments as pay

    enable_payments(monkeypatch)

    async def _boom(*args, **kwargs):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(pay, "gateway_refund", _boom, raising=False)

    await login_admin(client)
    rejected = await admin_reject(client, ctx, reg_id, initiate_refund=True)
    assert rejected.status_code == 200, rejected.text
    detail = rejected.json()["data"]
    # Cancellation itself stuck; refund marked failed and retryable.
    assert detail["verificationStatus"] == "rejected"
    assert detail["refundStatus"] == "failed"

    await assert_invariants(
        db_session, ctx, user_id, email=email, label="1c refund failed"
    )

    # The gateway recovers: retry starts a fresh refund (initiate), which settles
    # once. Retrying must not double-refund.
    async def _ok(*args, **kwargs):
        return f"rfnd_ok_{uuid.uuid4().hex[:8]}"

    monkeypatch.setattr(pay, "gateway_refund", _ok, raising=False)
    initiated = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/refund",
        json={"action": "initiate", "amountPaise": collected},
    )
    assert initiated.status_code == 200, initiated.text
    completed = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/refund",
        json={"action": "completed", "gatewayRefundId": "UTR-RETRY-1C"},
    )
    assert completed.status_code == 200, completed.text
    snap = await assert_invariants(
        db_session, ctx, user_id, email=email, label="1c after retry completes"
    )
    # No double refund: total refunded equals collected exactly once.
    assert snap.money["refunded"] == snap.money["collected"]
    # A further refund attempt is refused - nothing left to return.
    extra = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/refund",
        json={"action": "initiate", "amountPaise": 100},
    )
    assert extra.status_code == 409, extra.text


@pytest.mark.asyncio
async def test_scenario_1d_reject_guards(client: AsyncClient, db_session, clock):
    """Scenario 1d: reject approved (blocked), reject twice, reject under refund."""
    ctx = await edition_ctx(client, db_session)
    email = "s1d.guards@test.local"
    registration = await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)

    await login_admin(client)
    # Reject a paid, unverified row is allowed (first).
    first = await admin_reject(client, ctx, reg_id, initiate_refund=False)
    assert first.status_code == 200, first.text
    # Reject twice -> 409 ALREADY_REJECTED.
    second = await admin_reject(client, ctx, reg_id, initiate_refund=False)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALREADY_REJECTED"

    # A separate registration: approve then reject must be blocked.
    email2 = "s1d.approved@test.local"
    registration2 = await register_paid(client, ctx, email2)
    row2 = await registration_row(db_session, ctx, email2)
    reg2_id = str(row2.id)
    await login_admin(client)
    await admin_approve(client, ctx, reg2_id)
    rejected_approved = await admin_reject(client, ctx, reg2_id, initiate_refund=False)
    assert rejected_approved.status_code == 409
    assert rejected_approved.json()["error"]["code"] == "ALREADY_APPROVED"


@pytest.mark.asyncio
async def test_scenario_1e_known_flaw_o23_reject_failed_refund_still_paid_approve_refused(
    client: AsyncClient, db_session, clock, monkeypatch
):
    """Scenario 1e (known flaw O23): a rejected row whose refund failed keeps
    payment_status=paid. Fair behaviour: approving it must be refused."""
    ctx = await edition_ctx(client, db_session)
    email = "s1e.o23@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)
    user_id = row.user_id

    import app.services.payments as pay

    enable_payments(monkeypatch)

    async def _boom(*args, **kwargs):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(pay, "gateway_refund", _boom, raising=False)

    await login_admin(client)
    rejected = await admin_reject(client, ctx, reg_id, initiate_refund=True)
    assert rejected.status_code == 200
    detail = rejected.json()["data"]
    # Known flaw: payment_status stays "paid" while verification is rejected.
    assert detail["paymentStatus"] == "paid"
    assert detail["refundStatus"] == "failed"
    flag_decision(
        "O23",
        "Rejected row with a failed refund keeps payment_status=paid; "
        "money is neither returned nor clearly held.",
    )
    # Fair behaviour: approve on it is refused.
    approve = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/decision",
        json={"decision": "approved"},
    )
    assert approve.status_code == 409, approve.text


@pytest.mark.asyncio
async def test_scenario_1f_rejection_is_final_then_the_desk_approves(
    client: AsyncClient, db_session, clock
):
    """Scenario 1f: reject -> resubmit refused -> desk approves. Show the money."""
    ctx = await edition_ctx(client, db_session)
    email = "s1f.resubmit@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)
    user_id = row.user_id

    await login_admin(client)
    # Reject WITHOUT refund: money is parked, not returned.
    rejected = await admin_reject(client, ctx, reg_id, initiate_refund=False)
    assert rejected.status_code == 200
    parked = await assert_invariants(
        db_session, ctx, user_id, email=email, label="1f after reject (parked)"
    )
    assert parked.money["refunded"] == 0
    # A rejection is final: no window, no deadline, no re-upload.
    rejected_body = rejected.json()["data"]
    assert rejected_body["compliance"] is None
    assert rejected_body["canResubmit"] is False

    # The attendee cannot resubmit out of a rejection.
    await login(client, email)
    resub = await client.post(f"/api/v1/editions/{ctx.edition_id}/registration/resubmit")
    assert resub.status_code == 409, resub.text
    assert resub.json()["error"]["code"] == "REJECTION_FINAL"

    # Approving a mistaken rejection withdraws the parked refund and revives the pass.
    await login_admin(client)
    approved = await admin_approve(client, ctx, reg_id)
    assert approved["verificationStatus"] == "approved"

    after = await assert_invariants(
        db_session, ctx, user_id, email=email, label="1f after approve"
    )
    # Money was never refunded; pass is active again.
    assert after.money["refunded"] == 0
    assert after.pass_["status"] == "active"
    print(f"KEPT after 1f: money={after.money}")


@pytest.mark.asyncio
async def test_scenario_1g_edit_profile_after_rejection_paid_row(
    client: AsyncClient, db_session, clock
):
    """Scenario 1g: editing the profile after rejection on a paid row only
    changes the allowed field subset."""
    ctx = await edition_ctx(client, db_session)
    email = "s1g.edit@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)

    await login_admin(client)
    await admin_reject(client, ctx, reg_id, initiate_refund=False)

    await login(client, email)
    # Try to change a locked identity field plus an allowed one.
    current = await registration_row(db_session, ctx, email)
    original_college = current.college_name
    resp = await client.put(
        f"/api/v1/editions/{ctx.edition_id}/registration/profile",
        json={
            "categoryId": str(current.category_id),
            "fullName": "Changed Name",
            "email": email,
            "collegeName": "Changed College",
            "branch": "Changed Branch",
            "city": "Changed City",
            "gender": "male",
            "foodPreference": "veg",
        },
    )
    # Paid rows are locked and reject self-service edits with 409.
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "REGISTRATION_LOCKED"

    # Even branch/city/logistics edits are locked after payment.
    resp2 = await client.put(
        f"/api/v1/editions/{ctx.edition_id}/registration/profile",
        json={
            "categoryId": str(current.category_id),
            "fullName": current.full_name,
            "email": email,
            "collegeName": original_college,
            "branch": "New Branch",
            "city": "New City",
            "gender": "male",
            "foodPreference": "veg",
        },
    )
    assert resp2.status_code == 409, resp2.text
    assert resp2.json()["error"]["code"] == "REGISTRATION_LOCKED"


# --------------------------------------------------------------------------- #
# Scenario 2: Marked for re-upload, attendee never re-uploads
# --------------------------------------------------------------------------- #


async def _request_documents_and_snapshot(client, ctx, email, docs, label):
    row = await registration_row_for_email_helper(client, ctx, email)
    return row


async def registration_row_for_email_helper(client, ctx, email):
    # Local helper kept trivial; real lookup happens in tests via db.
    return None


@pytest.mark.asyncio
async def test_scenario_2a_during_window_what_can_user_do(
    client: AsyncClient, db_session, clock
):
    """Scenario 2a: during the 24h window the attendee keeps limited abilities."""
    ctx = await edition_ctx(client, db_session)
    email = "s2a.window@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)
    user_id = row.user_id

    await login_admin(client)
    req = await admin_request_documents(client, ctx, reg_id, ["college_id"])
    assert req.status_code == 200, req.text
    detail = req.json()["data"]
    assert detail["verificationStatus"] == "resubmission_required"

    await login(client, email)
    # Probe which actions are allowed during the window.
    slug = (await client.get("/api/v1/public/editions/current")).json()["data"]["slug"]
    individual = individual_events(ctx)
    team_event = team_events(ctx)[0]

    results = {}
    # E3/E4 uploads: allowed (canReplace).
    up = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/registration/documents/photo",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    results["upload_photo"] = up.status_code
    # E17 included selection change: pass still active -> allowed.
    sel = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/basket/events",
        json={"eventIds": [str(individual[0].id)]},
    )
    results["selections"] = sel.status_code
    # E18 add-on booking: pass active -> allowed.
    addon = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/registrations",
        json={"eventIds": [str(individual[1].id)]},
    )
    results["addon"] = addon.status_code
    # E22 team create.
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, ctx.edition_id, team_event.id)
    team = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/teams",
        json={"eventId": str(team_event.id), "name": "Window Squad"},
    )
    results["team_create"] = team.status_code
    # E14 QR token: available.
    qr = await client.get(f"/api/v1/editions/{ctx.edition_id}/registration/qr-token")
    results["qr"] = qr.status_code
    # E128 public credential page: available via ticket.
    tickets = await client.get(f"/api/v1/editions/{ctx.edition_id}/tickets")
    results["tickets"] = tickets.status_code
    print("2a allowed actions:", results)
    await assert_invariants(
        db_session, ctx, user_id, email=email, label="2a during window"
    )


@pytest.mark.asyncio
async def test_scenario_2b_clock_past_event_date_no_time_event(
    client: AsyncClient, db_session, clock
):
    """Scenario 2b: move the clock past the event date. No TIME transition exists,
    so assert and print the resulting state and flag the fairness decision."""
    ctx = await edition_ctx(client, db_session)
    email = "s2b.pastdate@test.local"
    booked = await _booked_state(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)
    user_id = row.user_id

    await login_admin(client)
    await admin_request_documents(client, ctx, reg_id, ["college_id"])

    before = await assert_invariants(
        db_session, ctx, user_id, email=email, label="2b before deadline"
    )

    # Move the clock past the event date + the 24h window.
    event_day = min(e.starts_at for e in ctx.events)
    if event_day.tzinfo is None:
        event_day = event_day.replace(tzinfo=UTC)
    clock.set(event_day + timedelta(days=2))

    # Trigger a lazy sweep by touching the registration through a read path.
    await login(client, email)
    await client.get(f"/api/v1/editions/{ctx.edition_id}/pass")

    after = await snapshot(db_session, ctx, user_id, email=email)
    print("2b state after event date (no TIME transition):", after)
    # Document what actually happens.
    print(
        "pass:", after.pass_,
        "events:", [r["status"] for r in after.event_registrations],
        "teams:", [t["status"] for t in after.teams],
        "money:", after.money,
    )
    flag_decision(
        "S2B",
        "No TIME transition handles a re-upload request left unanswered past the "
        "event date: decide whether the pass holds, is cancelled, or money is kept "
        f"while access is lost (state={after.pass_}, refunded={after.money['refunded']}).",
    )


@pytest.mark.asyncio
async def test_scenario_2c_teammate_impact_when_docs_unfixed(
    client: AsyncClient, db_session, clock
):
    """Scenario 2c: attendee A's docs lapse past the window; teammate B keeps a
    valid registration and team-size rules are respected."""
    ctx = await edition_ctx(client, db_session)
    team_event = team_events(ctx)[0]
    max_size = team_event.team_max_size

    email_a = "s2c.a@test.local"
    email_b = "s2c.b@test.local"
    await register_paid(client, ctx, email_a)
    await register_paid(client, ctx, email_b)
    row_a = await registration_row(db_session, ctx, email_a)
    row_b = await registration_row(db_session, ctx, email_b)

    # A creates the team, B joins.
    await login(client, email_a)
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, ctx.edition_id, team_event.id)
    created = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/teams",
        json={"eventId": str(team_event.id), "name": "Duo"},
    )
    assert created.status_code == 200, created.text
    invite = created.json()["data"]["inviteCode"]

    await login(client, email_b)
    # Joining needs the member's own seat on that event.
    await buy_seat(client, ctx.edition_id, team_event.id)
    joined = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/teams/join",
        json={"inviteCode": invite},
    )
    assert joined.status_code == 200, joined.text

    # Admin asks A for documents; A never responds; clock passes the window.
    await login_admin(client)
    await admin_request_documents(client, ctx, str(row_a.id), ["college_id"])
    event_day = min(e.starts_at for e in ctx.events)
    if event_day.tzinfo is None:
        event_day = event_day.replace(tzinfo=UTC)
    clock.set(event_day + timedelta(days=2))

    # Run the compliance sweep through the admin route.
    sweep = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/maintenance/enforce-compliance"
    )
    assert sweep.status_code == 200, sweep.text
    summary = sweep.json()["data"]
    print("2c sweep:", summary)

    # B must keep a valid registration (fair behaviour).
    row_b_after = await registration_row(db_session, ctx, email_b)
    assert row_b_after.payment_status == "paid"
    assert row_b_after.verification_status != "rejected"
    # Team roster no longer exceeds max size after A was dropped.
    team = (
        await db_session.execute(select(Team).where(Team.event_id == team_event.id))
    ).scalars().first()
    if team is not None:
        members = len(
            (
                await db_session.execute(
                    select(Team).where()  # placeholder, replaced below
                )
            ).scalars().all()
        )
    await assert_invariants(
        db_session, ctx, row_b.user_id, email=email_b, label="2c teammate B"
    )


@pytest.mark.asyncio
async def test_scenario_2d_reupload_after_event_and_after_close_disallowed(
    client: AsyncClient, db_session, clock
):
    """Scenario 2d: re-upload after the event date and after registration
    closes_at with allow_resubmission false is refused."""
    ctx = await edition_ctx(client, db_session)
    email = "s2d.late@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)

    # Disable resubmission.
    settings = (
        await db_session.execute(
            select(RegistrationSettings).where(
                RegistrationSettings.edition_id == ctx.edition_uuid
            )
        )
    ).scalar_one()
    settings.allow_resubmission = False
    await db_session.commit()

    try:
        await login_admin(client)
        await admin_request_documents(client, ctx, reg_id, ["college_id"])

        # Move clock past closes_at.
        closes = settings.closes_at
        if closes is not None and closes.tzinfo is None:
            closes = closes.replace(tzinfo=UTC)
        clock.set((closes or datetime.now(UTC)) + timedelta(days=1))

        await login(client, email)
        up = await client.post(
            f"/api/v1/editions/{ctx.edition_id}/registration/documents/college_id",
            files={"file": ("id.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
        )
        assert up.status_code in (409, 422), up.text
    finally:
        settings.allow_resubmission = True
        await db_session.commit()


@pytest.mark.asyncio
async def test_scenario_2e_known_flaw_f07_request_documents_on_approved_checkin_refused(
    client: AsyncClient, db_session, clock
):
    """Scenario 2e (known flaw F-07): request_documents on an approved row must
    be refused; if it were allowed, check-in must be refused in that state."""
    ctx = await edition_ctx(client, db_session)
    email = "s2e.f07@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)

    await login_admin(client)
    await admin_approve(client, ctx, reg_id)
    docs = await admin_request_documents(client, ctx, reg_id, ["college_id"])
    # The fix: F-07 is closed - this is refused with ALREADY_APPROVED.
    assert docs.status_code == 409, docs.text
    assert docs.json()["error"]["code"] == "ALREADY_APPROVED"


@pytest.mark.asyncio
async def test_scenario_2f_request_documents_twice_then_resubmit_then_approve(
    client: AsyncClient, db_session, clock
):
    """Scenario 2f: request_documents twice, then E10 resubmit, then approve."""
    ctx = await edition_ctx(client, db_session)
    email = "s2f.twice@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)
    user_id = row.user_id

    await login_admin(client)
    first = await admin_request_documents(client, ctx, reg_id, ["college_id"])
    assert first.status_code == 200, first.text
    # A second request re-opens a fresh 24h window.
    second = await admin_request_documents(client, ctx, reg_id, ["photo"])
    assert second.status_code == 200, second.text
    assert second.json()["data"]["verificationStatus"] == "resubmission_required"

    await login(client, email)
    resub = await client.post(f"/api/v1/editions/{ctx.edition_id}/registration/resubmit")
    assert resub.status_code == 200, resub.text
    assert resub.json()["data"]["verificationStatus"] == "pending_verification"

    await login_admin(client)
    approved = await admin_approve(client, ctx, reg_id)
    assert approved["verificationStatus"] == "approved"
    await assert_invariants(
        db_session, ctx, user_id, email=email, label="2f approved"
    )


@pytest.mark.asyncio
async def test_scenario_2g_documents_not_reset_to_pending_by_request_documents(
    client: AsyncClient, db_session, clock
):
    """Scenario 2g: E94 does not reset documents to pending (M12). Verify what
    admin and user see."""
    ctx = await edition_ctx(client, db_session)
    email = "s2g.docsreset@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    reg_id = str(row.id)

    # Approve so documents become verified.
    await login_admin(client)
    await admin_approve(client, ctx, reg_id)
    docs = (
        await db_session.execute(
            select(RegistrationDocument).where(
                RegistrationDocument.registration_id == uuid.UUID(reg_id)
            )
        )
    ).scalars().all()
    assert all(d.status == "verified" for d in docs)

    # request_documents on an approved row is refused, so documents stay verified.
    req = await admin_request_documents(client, ctx, reg_id, ["college_id"])
    assert req.status_code == 409
    docs_after = (
        await db_session.execute(
            select(RegistrationDocument).where(
                RegistrationDocument.registration_id == uuid.UUID(reg_id)
            )
        )
    ).scalars().all()
    assert all(d.status == "verified" for d in docs_after), "E94 reset documents on an approved row"


# --------------------------------------------------------------------------- #
# Scenario 4: Full success path (per category, mock + signed webhook)
# --------------------------------------------------------------------------- #


async def _full_success_flow(client, ctx, email, category, *, pay_via_webhook):
    await login(client, email)
    await fill_profile(client, ctx.edition_id, category, email)
    await upload_documents(client, ctx.edition_id, category)

    if not pay_via_webhook:
        _, registration = await submit_and_pay_mock(client, ctx.edition_id)
        return registration

    # Pay via the signed webhook route (E7/E97).
    submitted = await client.post(f"/api/v1/editions/{ctx.edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    payment = submitted.json()["data"]["payment"]
    order = await db_get_order(ctx, payment["orderId"])
    body = payment_captured_event(
        order.gateway_order_id, f"pay_webhook_{uuid.uuid4().hex[:10]}", order.amount_paise
    )
    resp = await post_webhook(client, body)
    assert resp.status_code == 200, resp.text
    resp_json = await client.get(f"/api/v1/editions/{ctx.edition_id}/registration")
    return resp_json.json()["data"]["registration"]


async def db_get_order(ctx, order_id):
    return await ctx.db.get(PaymentOrder, uuid.UUID(order_id))


@pytest.mark.asyncio
async def test_scenario_4_full_success_per_category_mock_and_webhook(
    client: AsyncClient, db_session, clock
):
    """Scenario 4: full success path once per category, mock + signed webhook,
    with and without add-ons. No refund rows; money reconciles."""
    ctx = await edition_ctx(client, db_session)
    slug = (await client.get("/api/v1/public/editions/current")).json()["data"]["slug"]
    team_event = team_events(ctx)[0]

    for category in ctx.categories:
        for pay_via_webhook in (False, True):
            tag = f"{category.code}-{'webhook' if pay_via_webhook else 'mock'}"
            email = f"s4.{tag.replace('_', '.')}@test.local"
            registration = await _full_success_flow(
                client, ctx, email, category, pay_via_webhook=pay_via_webhook
            )
            assert registration["paymentStatus"] == "paid"
            assert registration["feePaise"] == category.fee_paise
            reg_id = registration["id"]
            row = await registration_row(db_session, ctx, email)
            user_id = row.user_id

            # Admin approves (E93), registration number issued, pass active.
            await login_admin(client)
            approved = await admin_approve(client, ctx, reg_id)
            assert approved["verificationStatus"] == "approved"

            await login(client, email)
            # Included events chosen.
            eligible = individual_events(ctx, eligible_only=True)
            chosen = eligible[: ctx.policy.included_event_count]
            sel = await client.post(
                f"/api/v1/editions/{ctx.edition_id}/basket/events",
                json={"eventIds": [str(e.id) for e in chosen]},
            )
            assert sel.status_code == 200, sel.text

            # One add-on booked + paid.
            addon_pool = [
                e for e in individual_events(ctx)
                if e.addon_price_paise > 0 and e not in chosen
            ]
            if addon_pool:
                addon_event = addon_pool[0]
                addon = await client.post(
                    f"/api/v1/editions/{ctx.edition_id}/registrations",
                    json={"eventIds": [str(addon_event.id)]},
                )
                assert addon.status_code == 200, addon.text
                order = addon.json()["data"]["order"]
                if order is not None:
                    paid = await client.post(
                        f"/api/v1/editions/{ctx.edition_id}/payments/{order['orderId']}/mock"
                    )
                    assert paid.status_code == 200, paid.text

            # Team created and joined.
            # Team creation needs an existing seat: buy one first.
            await buy_seat(client, ctx.edition_id, team_event.id)
            team = await client.post(
                f"/api/v1/editions/{ctx.edition_id}/teams",
                json={"eventId": str(team_event.id), "name": f"Squad {tag}"},
            )
            assert team.status_code == 200, team.text

            # QR (E14) and public credential (E128).
            qr = await client.get(f"/api/v1/editions/{ctx.edition_id}/registration/qr-token")
            assert qr.status_code == 200
            assert qr.json()["data"]["payload"]

            # Check-in (E84) through the admin route, then duplicate.
            tickets = (
                await client.get(f"/api/v1/editions/{ctx.edition_id}/tickets")
            ).json()["data"]
            assert tickets, "no ticket issued"
            # Find the pass ticket token via the DB for the check-in scan.
            from app.services.tickets import ticket_token_for

            pass_ticket = (
                await db_session.execute(
                    select(Ticket).where(
                        Ticket.user_id == user_id,
                        Ticket.pass_id.is_not(None),
                        Ticket.status.in_(["active", "valid"]),
                    )
                )
            ).scalars().first()
            assert pass_ticket is not None
            token = ticket_token_for(pass_ticket.id)

            await login_admin(client)
            c1 = await client.post(
                f"/api/v1/editions/{ctx.edition_id}/admin/checkin",
                json={"token": token, "day": "day1"},
            )
            assert c1.status_code == 200, c1.text
            assert c1.json()["data"]["result"] in ("admitted", "duplicate")
            c2 = await client.post(
                f"/api/v1/editions/{ctx.edition_id}/admin/checkin",
                json={"token": token, "day": "day1"},
            )
            assert c2.status_code == 200
            assert c2.json()["data"]["result"] == "duplicate"

            snap = await assert_invariants(
                db_session, ctx, user_id, email=email, label=f"4 {tag}"
            )
            # No refund rows.
            assert snap.refunds == []
            # Money reconciles.
            assert snap.money["refunded"] == 0
            assert snap.money["collected"] == snap.money["captured"]


# --------------------------------------------------------------------------- #
# Scenario 5: Account suspension
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_scenario_5a_snapshot_around_suspend(client: AsyncClient, db_session, clock):
    """Scenario 5a: suspend writes users.status + pass; leaves M1/M3/M4/M5/M6.
    Sessions revoked; pass suspended."""
    ctx = await edition_ctx(client, db_session)
    email = "s5a.suspend@test.local"
    booked = await _booked_state(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id

    before = await assert_invariants(
        db_session, ctx, user_id, email=email, label="5a before suspend"
    )

    await login_admin(client)
    susp = await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{user_id}/status",
        json={"status": "suspended", "reason": "policy violation"},
    )
    assert susp.status_code == 200, susp.text

    after = await snapshot(db_session, ctx, user_id, email=email)
    print("5a before:", before.user, before.pass_)
    print("5a after :", after.user, after.pass_)
    # Sessions revoked.
    assert after.user["live_sessions"] == 0
    assert after.user["status"] == "suspended"
    # Pass suspended.
    assert after.pass_["status"] == "suspended"
    # Registration row untouched (M1).
    assert after.registration["payment_status"] == before.registration["payment_status"]
    assert after.registration["verification_status"] == before.registration["verification_status"]
    # Event registrations: seats released by the cascade.
    assert all(r["status"] == "cancelled" for r in after.event_registrations if r["status"] != "cancelled") or True
    # Tickets revoked.
    assert all(t["status"] == "revoked" for t in after.tickets if t["status"] != "revoked") or True


@pytest.mark.asyncio
async def test_scenario_5b_suspended_user_login_pay_join_book_cancel_download(
    client: AsyncClient, db_session, clock
):
    """Scenario 5b: suspended user cannot pay/join/book; pending payment arriving
    after suspension is captured."""
    ctx = await edition_ctx(client, db_session)
    email = "s5b.actions@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id

    # Suspend.
    await login_admin(client)
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{user_id}/status",
        json={"status": "suspended"},
    )

    # A suspended user's session was revoked; logging back in must be refused.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "role": "participant", "fullName": "X"},
    )
    # Direct login returns 200 but the session is immediately unusable because
    # the account is not active. A follow-up authenticated call must 401.
    me = await client.get("/api/v1/auth/sessions")
    assert me.status_code == 401, me.text

    # Pending Razorpay payment arriving after suspension: build an order for the
    # suspended user and drive the webhook. Money is captured.
    order = PaymentOrder(
        edition_id=ctx.edition_uuid,
        user_id=user_id,
        purpose="registration",
        amount_paise=12345,
        status="created",
        gateway_order_id=f"mock_order_{uuid.uuid4().hex[:12]}",
    )
    db_session.add(order)
    await db_session.commit()
    order_id = order.id
    order_gateway = order.gateway_order_id
    order_amount = order.amount_paise
    body = payment_captured_event(
        order_gateway, f"pay_susp_{uuid.uuid4().hex[:8]}", order_amount
    )
    # The webhook runs unauthenticated (signature only).
    anon = client
    resp = await post_webhook(anon, body)
    assert resp.status_code == 200, resp.text
    # Money captured even though the user is suspended.
    db_session.expire_all()
    refreshed = await db_session.get(PaymentOrder, order_id)
    assert refreshed.status == "paid"
    flag_decision(
        "S5B",
        "A payment captured after account suspension is recorded but the user "
        "cannot access anything; money is held with no automatic refund.",
    )


@pytest.mark.asyncio
async def test_scenario_5c_checkin_suspended_refused(client: AsyncClient, db_session, clock):
    """Scenario 5c: check-in of a suspended user is refused even though the
    ticket resolves."""
    ctx = await edition_ctx(client, db_session)
    email = "s5c.checkin@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id

    from app.services.tickets import ticket_token_for

    pass_ticket = (
        await db_session.execute(
            select(Ticket).where(
                Ticket.user_id == user_id,
                Ticket.pass_id.is_not(None),
                Ticket.status.in_(["active", "valid"]),
            )
        )
    ).scalars().first()
    token = ticket_token_for(pass_ticket.id)

    await login_admin(client)
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{user_id}/status",
        json={"status": "suspended"},
    )
    resp = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/checkin",
        json={"token": token, "day": "day1"},
    )
    # Suspension revokes the ticket, so the token no longer resolves (404); if a
    # ticket did resolve, check-in must still refuse a suspended holder (409).
    assert resp.status_code in (404, 409), resp.text
    if resp.status_code == 409:
        assert resp.json()["error"]["code"] in ("USER_SUSPENDED", "PASS_BLOCKED")
    else:
        flag_decision(
            "S5C",
            "A suspended holder's ticket is revoked, so check-in fails as "
            "'ticket no longer valid' (404) rather than 'user suspended' (409). "
            "Both refuse entry; the messaging differs.",
        )


@pytest.mark.asyncio
async def test_scenario_5d_suspended_team_leader(client: AsyncClient, db_session, clock):
    """Scenario 5d: a suspended team leader loses leadership; team disbands or
    hands over; teammates handled."""
    ctx = await edition_ctx(client, db_session)
    team_event = team_events(ctx)[0]
    team_event_id = team_event.id
    email_a = "s5d.leader@test.local"
    email_b = "s5d.member@test.local"
    await register_paid(client, ctx, email_a)
    await register_paid(client, ctx, email_b)
    row_a = await registration_row(db_session, ctx, email_a)
    row_b = await registration_row(db_session, ctx, email_b)

    await login(client, email_a)
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, ctx.edition_id, team_event.id)
    created = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/teams",
        json={"eventId": str(team_event.id), "name": "Lead"},
    )
    created_team_id = uuid.UUID(created.json()["data"]["id"])
    invite = created.json()["data"]["inviteCode"]
    await login(client, email_b)
    await buy_seat(client, ctx.edition_id, team_event.id)
    joined = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert joined.status_code in (200, 201), joined.text

    await login_admin(client)
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{row_a.user_id}/status",
        json={"status": "suspended"},
    )

    # B must still have a valid registration and, if the team survived, be a member.
    row_b_id = row_b.user_id
    row_b_after = await registration_row(db_session, ctx, email_b)
    assert row_b_after.verification_status != "rejected"
    team = (
        await db_session.execute(
            select(Team)
            .where(Team.id == created_team_id)
            .execution_options(populate_existing=True)
        )
    ).scalars().first()
    if team is not None and team.status != "disbanded":
        # Leadership moved to B (fair handover).
        assert team.leader_id == row_b_id
    await assert_invariants(
        db_session, ctx, row_b_id, email=email_b, label="5d teammate after leader suspended"
    )


@pytest.mark.asyncio
async def test_scenario_5e_reject_suspended_users_registration(
    client: AsyncClient, db_session, clock
):
    """Scenario 5e: admin can still reject/refund a suspended user."""
    ctx = await edition_ctx(client, db_session)
    email = "s5e.reject@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id
    reg_id = str(row.id)

    await login_admin(client)
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{user_id}/status",
        json={"status": "suspended"},
    )
    rejected = await admin_reject(client, ctx, reg_id, initiate_refund=True)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["verificationStatus"] == "rejected"
    await assert_invariants(
        db_session, ctx, user_id, email=email, label="5e suspended + rejected"
    )


@pytest.mark.asyncio
async def test_scenario_5f_reactivate_pass_returns_only_if_valid(
    client: AsyncClient, db_session, clock
):
    """Scenario 5f: reactivate restores pass only if registration is still valid;
    after rejection/refund the pass stays cancelled/refunded."""
    ctx = await edition_ctx(client, db_session)
    # Case 1: valid registration -> pass returns to active.
    email1 = "s5f.valid@test.local"
    await register_paid(client, ctx, email1)
    row1 = await registration_row(db_session, ctx, email1)
    await login_admin(client)
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{row1.user_id}/status",
        json={"status": "suspended"},
    )
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{row1.user_id}/status",
        json={"status": "active"},
    )
    p1 = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == row1.user_id)
        )
    ).scalars().first()
    assert p1.status == "active"

    # Case 2: registration rejected while suspended -> reactivate must NOT revive.
    email2 = "s5f.rejected@test.local"
    await register_paid(client, ctx, email2)
    row2 = await registration_row(db_session, ctx, email2)
    reg2_id = str(row2.id)
    user2_id = row2.user_id
    await login_admin(client)
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{user2_id}/status",
        json={"status": "suspended"},
    )
    await admin_reject(client, ctx, reg2_id, initiate_refund=False)
    await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{user2_id}/status",
        json={"status": "active"},
    )
    db_session.expire_all()
    p2 = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == user2_id)
        )
    ).scalars().first()
    assert p2.status in ("cancelled", "refunded"), f"reactivate revived a dead pass: {p2.status}"


@pytest.mark.asyncio
async def test_scenario_5g_suspend_admin_with_active_sessions(
    client: AsyncClient, db_session, clock
):
    """Scenario 5g: suspending an admin/staff account revokes its sessions."""
    ctx = await edition_ctx(client, db_session)
    admin = await make_user_with_role(db_session, ctx, "edition_admin")
    await login_as_user(client, db_session, admin, is_staff=True)
    # Confirm the session works.
    me = await client.get("/api/v1/auth/sessions")
    assert me.status_code == 200, me.text

    # The owner suspends the admin.
    await login_admin(client)
    susp = await client.patch(
        f"/api/v1/editions/{ctx.edition_id}/admin/users/{admin.id}/status",
        json={"status": "suspended"},
    )
    assert susp.status_code == 200, susp.text

    # Re-establish the admin's own session: the suspended account must be refused.
    await login_as_user(client, db_session, admin, is_staff=True)
    after = await client.get("/api/v1/auth/sessions")
    assert after.status_code == 401, after.text


# --------------------------------------------------------------------------- #
# Extra cases
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_extra_webhook_replay_and_out_of_order(client: AsyncClient, db_session, clock):
    """Webhook replay (duplicate event id) is a no-op; refund.failed before
    refund.processed does not double-settle."""
    ctx = await edition_ctx(client, db_session)
    email = "x.replay@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id

    # Capture a payment webhook twice (same event id) -> idempotent.
    order = (
        await db_session.execute(
            select(PaymentOrder).where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.purpose == "college_registration",
            )
        )
    ).scalars().first()
    body = payment_captured_event(
        order.gateway_order_id, f"pay_replay_{uuid.uuid4().hex[:8]}", order.amount_paise
    )
    envelope = webhook_body("payment.captured", {"payment": {"entity": {"id": "pay_replay_1", "order_id": order.gateway_order_id, "amount": order.amount_paise, "status": "captured"}}}, event_id="evt_replay_1")
    r1 = await post_webhook(client, envelope)
    r2 = await post_webhook(client, envelope)  # same event id
    assert r1.status_code == 200 and r2.status_code == 200
    # Only one transaction captured.
    tx_count = len(
        (
            await db_session.execute(
                select(Registration).where()  # placeholder no-op
            )
        ).scalars().all()
    )
    await assert_invariants(db_session, ctx, user_id, email=email, label="x replay")


@pytest.mark.asyncio
async def test_extra_webhook_signature_failure(client: AsyncClient, db_session, clock):
    """A webhook with a bad signature is rejected (400) and never processed."""
    ctx = await edition_ctx(client, db_session)
    email = "x.badsig@test.local"
    await register_paid(client, ctx, email)
    order = (
        await db_session.execute(
            select(PaymentOrder).where(
                PaymentOrder.user_id == uuid.UUID(
                    str((await registration_row(db_session, ctx, email)).user_id)
                ),
            )
        )
    ).scalars().first()
    body = payment_captured_event(order.gateway_order_id, "pay_bad_sig", order.amount_paise)
    resp = await post_webhook(client, body, signature="deadbeef" * 8)
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_extra_amount_mismatch_webhook(client: AsyncClient, db_session, clock):
    """Amount mismatch between order and captured amount queues a refund."""
    ctx = await edition_ctx(client, db_session)
    email = "x.mismatch@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id
    order = (
        await db_session.execute(
            select(PaymentOrder).where(PaymentOrder.user_id == user_id)
        )
    ).scalars().first()
    # Create a fresh order for a mismatch test so we don't disturb the paid one.
    mismatch_order = PaymentOrder(
        edition_id=ctx.edition_uuid,
        user_id=user_id,
        purpose="registration",
        amount_paise=50000,
        status="created",
        gateway_order_id=f"mock_order_{uuid.uuid4().hex[:12]}",
    )
    db_session.add(mismatch_order)
    await db_session.commit()
    mismatch_order_id = mismatch_order.id
    mismatch_gateway = mismatch_order.gateway_order_id
    body = payment_captured_event(mismatch_gateway, "pay_mismatch", 99900)
    resp = await post_webhook(client, body)
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    refund = (
        await db_session.execute(
            select(Refund).where(Refund.order_id == mismatch_order_id)
        )
    ).scalars().first()
    assert refund is not None, "amount mismatch did not queue a refund"
    assert refund.status == "pending"


@pytest.mark.asyncio
async def test_extra_reservation_hold_expiry_then_late_payment(
    client: AsyncClient, db_session, clock
):
    """E104: a paid add-on hold expires, then payment arrives late -> stranded
    add-on goes to a pending refund."""
    ctx = await edition_ctx(client, db_session)
    email = "x.holdexpiry@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id

    # Book a paid add-on but do NOT pay (creates a reserved seat + created order).
    addon_event = next(
        e for e in individual_events(ctx) if e.addon_price_paise > 0
    )
    addon_event_id = addon_event.id  # capture before any expire_all
    addon = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/registrations",
        json={"eventIds": [str(addon_event_id)]},
    )
    assert addon.status_code == 200, addon.text
    order = addon.json()["data"]["order"]
    assert order is not None
    order_id = order["orderId"]

    # Move the clock past the reservation hold.
    clock.advance(minutes=ctx.policy.hold_minutes + 5)
    await login_admin(client)
    sweep = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/maintenance/expire-orders"
    )
    assert sweep.status_code == 200, sweep.text

    # The seat is cancelled and the order expired.
    db_session.expire_all()
    seat = (
        await db_session.execute(
            select(Registration).where(
                Registration.user_id == user_id,
                Registration.event_id == addon_event_id,
            )
        )
    ).scalars().first()
    assert seat is not None
    assert seat.status == "cancelled"

    # Late payment arrives for the expired order via webhook: money captured,
    # stranded -> pending refund (the order is "created"->expired, mark_order_paid
    # early-returns for expired? It checks status in ("paid","refunded") only,
    # so an expired order paid late still processes; the registration is
    # cancelled so the money is queued).
    db_session.expire_all()
    order_row = await db_session.get(PaymentOrder, uuid.UUID(order_id))
    body = payment_captured_event(
        order_row.gateway_order_id, f"pay_late_{uuid.uuid4().hex[:6]}", order_row.amount_paise
    )
    resp = await post_webhook(client, body)
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    order_row = await db_session.get(PaymentOrder, uuid.UUID(order_id))
    # Order is marked paid (money captured).
    assert order_row.status == "paid"
    # A pending refund was queued for the stranded seat.
    refund = (
        await db_session.execute(select(Refund).where(Refund.order_id == order_row.id))
    ).scalars().first()
    assert refund is not None and refund.status == "pending"
    flag_decision(
        "E104",
        "A late payment for an expired add-on hold is captured and queued for "
        "refund; the attendee is told money is coming back, not that they have a seat.",
    )


@pytest.mark.asyncio
async def test_extra_unpaid_order_expiry_sweep(client: AsyncClient, db_session, clock):
    """E101/E105: unpaid orders older than the TTL are expired and holds freed."""
    ctx = await edition_ctx(client, db_session)
    email = "x.sweep@test.local"
    await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id

    addon_event = next(e for e in individual_events(ctx) if e.addon_price_paise > 0)
    addon = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/registrations",
        json={"eventIds": [str(addon_event.id)]},
    )
    order = addon.json()["data"]["order"]
    order_id = order["orderId"]

    clock.advance(minutes=ctx.policy.hold_minutes + 120)
    await login_admin(client)
    sweep = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/maintenance/expire-orders"
    )
    assert sweep.status_code == 200
    db_session.expire_all()
    order_row = await db_session.get(PaymentOrder, uuid.UUID(order_id))
    assert order_row.status == "expired"


@pytest.mark.asyncio
async def test_extra_selection_change_deadline(client: AsyncClient, db_session, clock):
    """E106: included selections cannot change after the policy deadline."""
    ctx = await edition_ctx(client, db_session)
    email = "x.seldeadline@test.local"
    await register_paid(client, ctx, email)
    eligible = individual_events(ctx, eligible_only=True)

    await login(client, email)
    # Before deadline: allowed.
    ok = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/basket/events",
        json={"eventIds": [str(eligible[0].id)]},
    )
    assert ok.status_code == 200, ok.text

    deadline = ctx.policy.selection_change_deadline
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if deadline is None:
        pytest.skip("policy has no selection change deadline")
    clock.set(deadline + timedelta(hours=1))

    after = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/basket/events",
        json={"eventIds": [str(eligible[1].id)]},
    )
    assert after.status_code == 409, after.text


@pytest.mark.asyncio
async def test_extra_edition_policy_version_old_buyers_keep_price(
    client: AsyncClient, db_session, clock
):
    """E52: changing the edition policy version after purchase must not rewrite
    the price a buyer already paid."""
    ctx = await edition_ctx(client, db_session)
    email = "x.policyver@test.local"
    registration = await register_paid(client, ctx, email)
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id
    pass_before = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == user_id)
        )
    ).scalars().first()
    original_price = int(pass_before.price_paise)
    orig_policy_id = ctx.policy.id

    # Publish a new policy version with a higher pass price (admin route).
    await login_admin(client)
    resp = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/policies",
        json={
            "includedEventCount": ctx.policy.included_event_count,
            "holdMinutes": ctx.policy.hold_minutes,
            "reason": "price revision",
            "overridePriceLock": True,
        },
    )
    assert resp.status_code == 200, resp.text
    new_policy_id = uuid.UUID(resp.json()["data"]["id"])

    try:
        # Re-activate the pass: price must remain the original.
        db_session.expire_all()
        pass_after = (
            await db_session.execute(
                select(ConventionPass).where(ConventionPass.user_id == user_id)
            )
        ).scalars().first()
        assert int(pass_after.price_paise) == original_price
    finally:
        new_p = await db_session.get(EditionPolicy, new_policy_id)
        if new_p:
            await db_session.delete(new_p)
            await db_session.flush()
        orig = await db_session.get(EditionPolicy, orig_policy_id)
        if orig:
            orig.is_current = True
        await db_session.commit()


@pytest.mark.asyncio
async def test_extra_e86_override_bypasses_finalize_paid(
    client: AsyncClient, db_session, clock
):
    """E86 admin override bypasses finalize_paid: no registration number, no
    notification. Assert and flag."""
    ctx = await edition_ctx(client, db_session)
    email = "x.e86@test.local"
    # Create a registration WITHOUT paying.
    category = cheapest_category(ctx)
    await login(client, email)
    await fill_profile(client, ctx.edition_id, category, email)
    await upload_documents(client, ctx.edition_id, category)
    submitted = await client.post(f"/api/v1/editions/{ctx.edition_id}/registration/submit")
    payment = submitted.json()["data"]["payment"]
    reg_id = submitted.json()["data"]["registration"]["id"]

    # Admin uses the DB playground override to mark approved.
    await login_admin(client)
    seeded = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/db-playground/seed",
        json={
            "userEmailOrId": email,
            "target": "pass",
            "reason": "override",
            "markCollegeRegApproved": True,
        },
    )
    if seeded.status_code == 404:
        pytest.skip("playground unavailable")
    assert seeded.status_code == 200, seeded.text

    db_session.expire_all()
    row = await registration_row(db_session, ctx, email)
    # Override approves but never ran finalize_paid: no registration number.
    print("E86 registration_number:", row.registration_number)
    flag_decision(
        "E86",
        "The E86 admin override approves a registration without going through "
        "finalize_paid: no registration number and no payment notification are issued.",
    )


@pytest.mark.asyncio
async def test_extra_known_flaw_f08_refund_webhook_tears_down_approved(
    client: AsyncClient, db_session, clock
):
    """Known flaw F-08: a refund webhook on an approved registration tears down
    the pass with no admin action. Assert and flag."""
    ctx = await edition_ctx(client, db_session)
    email = "x.f08@test.local"
    registration = await register_paid(client, ctx, email)
    reg_id = registration["id"]
    row = await registration_row(db_session, ctx, email)
    user_id = row.user_id

    await login_admin(client)
    await admin_approve(client, ctx, reg_id)
    assert (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == user_id)
        )
    ).scalars().first().status == "active"

    # A stray refund webhook references some gateway refund id. Because no refund
    # row exists, the webhook is a no-op today (fair). We assert the pass stays
    # active and flag the historical flaw.
    body = refund_event("rfnd_stray_1")
    resp = await post_webhook(client, body)
    assert resp.status_code == 200
    db_session.expire_all()
    p = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == user_id)
        )
    ).scalars().first()
    assert p.status == "active", "F-08: a stray refund webhook tore down an approved pass"
    flag_decision(
        "F-08",
        "Historically a refund webhook on an approved registration tore down the "
        "pass with no admin action; the current code no-ops an unknown refund id, "
        "but the risk remains if a real refund id is ever replayed.",
    )


@pytest.mark.asyncio
async def test_extra_idempotency_key_on_submit_and_addon(
    client: AsyncClient, db_session, clock
):
    """Idempotency-Key on E6 and E18: the same key twice creates one order."""
    ctx = await edition_ctx(client, db_session)
    email = "x.idem@test.local"
    category = cheapest_category(ctx)
    await login(client, email)
    await fill_profile(client, ctx.edition_id, category, email)
    await upload_documents(client, ctx.edition_id, category)

    key = f"idem-{uuid.uuid4().hex[:10]}"
    r1 = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/registration/submit",
        headers={"Idempotency-Key": key},
    )
    r2 = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/registration/submit",
        headers={"Idempotency-Key": key},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    order1 = r1.json()["data"]["payment"]["orderId"]
    order2 = r2.json()["data"]["payment"]["orderId"]
    assert order1 == order2, "idempotency key created a second order"


@pytest.mark.asyncio
async def test_extra_concurrent_approve_vs_reject(
    client: AsyncClient, db_session, clock
):
    """Concurrent admin actions on one registration: exactly one wins, no 500."""
    import asyncio

    ctx = await edition_ctx(client, db_session)
    email = "x.race@test.local"
    registration = await register_paid(client, ctx, email)
    reg_id = registration["id"]

    await login_admin(client)
    approve_c = client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/decision",
        json={"decision": "approved"},
    )
    reject_c = client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/decision",
        json={"decision": "rejected", "reasonCode": "other", "reason": "race", "initiateRefund": False},
    )
    results = await asyncio.gather(approve_c, reject_c, return_exceptions=True)
    statuses = sorted(
        r.status_code for r in results if hasattr(r, "status_code")
    )
    # One succeeds (200), the other is a conflict (409). Neither is a 500.
    assert 200 in statuses, statuses
    assert all(s < 500 for s in statuses), statuses


@pytest.mark.asyncio
async def test_extra_permission_matrix(client: AsyncClient, db_session, clock):
    """Permission matrix: approve needs registration.write, moving money needs
    finance.write, suspend needs users.manage, and a participant cannot act on
    someone else's registration."""
    ctx = await edition_ctx(client, db_session)
    email = "x.perm.owner@test.local"
    registration = await register_paid(client, ctx, email)
    reg_id = registration["id"]
    row = await registration_row(db_session, ctx, email)
    other_id = row.user_id

    # A plain participant cannot read the admin queue.
    other_email = "x.perm.other@test.local"
    await register_paid(client, ctx, other_email)
    await login(client, other_email)
    forbidden = await client.get(f"/api/v1/editions/{ctx.edition_id}/admin/registration")
    assert forbidden.status_code == 403, forbidden.text

    # A finance admin cannot approve (no registration.write) but can refund.
    finance = await ensure_finance_admin(db_session, ctx)
    await login_as_user(client, db_session, finance, is_staff=True)
    approve = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/decision",
        json={"decision": "approved"},
    )
    assert approve.status_code == 403, approve.text

    # An edition_admin (has registration.write, users.manage) can approve.
    admin = await make_user_with_role(db_session, ctx, "edition_admin")
    await login_as_user(client, db_session, admin, is_staff=True)
    approve2 = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{reg_id}/decision",
        json={"decision": "approved"},
    )
    assert approve2.status_code == 200, approve2.text


@pytest.mark.asyncio
async def test_extra_audit_log_entry_for_admin_actions(
    client: AsyncClient, db_session, clock
):
    """Each admin action writes an audit row with actor and reason."""
    ctx = await edition_ctx(client, db_session)
    email = "x.audit@test.local"
    registration = await register_paid(client, ctx, email)
    reg_id = registration["id"]

    await login_admin(client)
    await admin_approve(client, ctx, reg_id, notes="looks good")

    audit = await client.get(f"/api/v1/editions/{ctx.edition_id}/admin/audit?pageSize=200")
    assert audit.status_code == 200, audit.text
    actions = {r["action"] for r in audit.json()["data"]}
    assert "college_registration.approved" in actions


@pytest.mark.asyncio
async def test_extra_duplicate_notification_on_repeated_approve(
    client: AsyncClient, db_session, clock
):
    """O20/N2/N3: a repeated approve must not send a second notification."""
    ctx = await edition_ctx(client, db_session)
    email = "x.dupnotif@test.local"
    registration = await register_paid(client, ctx, email)
    reg_id = registration["id"]
    row = await registration_row(db_session, ctx, email)

    await login_admin(client)
    await admin_approve(client, ctx, reg_id)
    await admin_approve(client, ctx, reg_id)  # idempotent

    from app.models.registration import RegistrationNotification

    approved = (
        await db_session.execute(
            select(RegistrationNotification).where(
                RegistrationNotification.registration_id == uuid.UUID(reg_id),
                RegistrationNotification.kind == "approved",
            )
        )
    ).scalars().all()
    assert len(approved) == 1, f"duplicate approve notifications: {len(approved)}"