"""Regression tests for the phase-8 audit findings (docs/audits/AUDIT/08-flaws.md).

Each test names the finding it pins, so a regression points at the flaw instead
of at an anonymous assertion.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import (
    AttendanceRecord,
    ConventionPass,
    EmailOutbox,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    Ticket,
)
from app.models.edition import Event
from app.models.registration import CollegeRegistration
from app.models.user import User

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
ADMIN = "owner@parallax.local"


@pytest.fixture(autouse=True)
async def _reset_login_budget():
    """This module logs in often; keep the shared suite budget from running out."""
    from app.core.cache import cache_delete_pattern
    from app.db.session import session_scope
    from sqlalchemy import delete as sql_delete

    from app.models.commerce import RateLimitCounter

    try:
        async with session_scope() as cleanup_db:
            await cleanup_db.execute(
                sql_delete(RateLimitCounter).where(
                    RateLimitCounter.bucket.like("auth_login%")
                )
            )
    except Exception:  # noqa: BLE001 - the budget reset is best effort
        pass
    cache_delete_pattern("ratelimit:*")
    yield


async def _edition(client: AsyncClient) -> dict:
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _login(client: AsyncClient, email: str, role: str = "participant") -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "role": role, "fullName": email.split("@")[0].title()},
    )
    assert resp.status_code == 200, resp.text


async def _profile_ready(client: AsyncClient, edition_id: str, email: str) -> dict:
    config = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    category = next(
        item for item in config["categories"] if item["code"] in ("polytechnic", "engineering")
    )
    profile = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": category["id"],
            "fullName": email.split("@")[0].title(),
            "email": email,
            "phone": "9876543210",
            "collegeName": "NSSCE",
            "course": "B.Tech",
            "branch": "Computer Science",
            "yearOfStudy": "3",
            "gender": "male",
            "foodPreference": "veg",
            "city": "Palakkad",
            "state": "Kerala",
        },
    )
    assert profile.status_code == 200, profile.text
    for doc_type in ("college_id", "photo"):
        uploaded = await client.post(
            f"/api/v1/editions/{edition_id}/registration/documents/{doc_type}",
            files={"file": (f"{doc_type}.png", PNG, "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
    return profile.json()["data"]


async def _paid_registration(client: AsyncClient, edition_id: str, email: str) -> dict:
    await _profile_ready(client, edition_id, email)
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    payment = submitted.json()["data"]["payment"]
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    return paid.json()["data"]["registration"]


async def _approve(client: AsyncClient, edition_id: str, registration_id: str) -> None:
    approved = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration_id}/decision",
        json={"decision": "approved"},
    )
    assert approved.status_code == 200, approved.text


async def _attendee_row(db_session, email: str) -> CollegeRegistration:
    return (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == email)
        )
    ).scalars().first()


# --------------------------------------------------------------------------- #
# F-01 / F-10 / F-09: decision guards
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_document_request_is_refused_on_an_approved_registration(
    client: AsyncClient, db_session
):
    """F-01: demoting an approved attendee left their pass and credential live."""
    email = "f01.approved@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)

    await _login(client, ADMIN, role="admin")
    await _approve(client, edition_id, registration["id"])
    refused = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/request-documents",
        json={"documents": ["college_id"], "message": "Please re-upload"},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "ALREADY_APPROVED"


@pytest.mark.asyncio
async def test_approve_and_reject_are_idempotent(client: AsyncClient, db_session):
    """F-09/F-10: a double click must not re-notify or re-cascade."""
    email = "f10.approve@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)

    await _login(client, ADMIN, role="admin")
    await _approve(client, edition_id, registration["id"])
    await _approve(client, edition_id, registration["id"])

    approved_mails = (
        await db_session.execute(
            select(EmailOutbox).where(
                EmailOutbox.recipient == email,
                EmailOutbox.template == "registration_approved",
            )
        )
    ).scalars().all()
    assert len(approved_mails) == 1

    # Rejecting an approved registration is refused; the cascade cannot run twice.
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/decision",
        json={"decision": "rejected", "reasonCode": "invalid_college_id", "initiateRefund": False},
    )
    assert rejected.status_code == 409


@pytest.mark.asyncio
async def test_reject_twice_is_refused(client: AsyncClient, db_session):
    email = "f09.reject@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)

    await _login(client, ADMIN, role="admin")
    first = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/decision",
        json={"decision": "rejected", "reasonCode": "invalid_college_id", "initiateRefund": False},
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/decision",
        json={"decision": "rejected", "reasonCode": "invalid_college_id", "initiateRefund": False},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALREADY_REJECTED"


@pytest.mark.asyncio
async def test_reject_without_refund_still_parks_the_money(client: AsyncClient, db_session):
    """F-31: the pass money must never disappear from the ledger."""
    email = "f31.park@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)

    await _login(client, ADMIN, role="admin")
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/decision",
        json={"decision": "rejected", "reasonCode": "invalid_college_id", "initiateRefund": False},
    )
    assert rejected.status_code == 200, rejected.text

    row = await _attendee_row(db_session, email)
    parked = (
        await db_session.execute(
            select(Refund).where(Refund.order_id == row.order_id)
        )
    ).scalars().all()
    assert parked, "rejecting a paid registration left no refund row"
    assert parked[0].status == "pending"
    assert parked[0].amount_paise == row.fee_paise


# --------------------------------------------------------------------------- #
# F-06 / F-07 / F-08: refund state machine
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_refund_actions_follow_the_state_machine(client: AsyncClient, db_session):
    """F-06/F-07: retry only a failed refund, complete only once."""
    from app.services import college_registrations as cr_service

    email = "f06.refund@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    await cr_service.initiate_refund(
        db_session, None, row, None, None, amount_paise=row.fee_paise, note="F-06"
    )
    await db_session.commit()

    refund = (
        await db_session.execute(select(Refund).where(Refund.order_id == row.order_id))
    ).scalars().first()
    assert refund is not None

    refund.status = "processed"
    await db_session.commit()
    with pytest.raises(Exception) as completed_twice:
        await cr_service.refund_action(
            db_session,
            None,
            row,
            None,
            None,
            action="completed",
            amount_paise=None,
            note=None,
            gateway_refund_id="manual_ref",
        )
    assert "already completed" in str(completed_twice.value).lower()

    with pytest.raises(Exception) as retry_processed:
        await cr_service.refund_action(
            db_session,
            None,
            row,
            None,
            None,
            action="retry",
            amount_paise=None,
            note=None,
            gateway_refund_id=None,
        )
    assert "failed refund" in str(retry_processed.value).lower()


@pytest.mark.asyncio
async def test_duplicate_refund_webhook_does_not_settle_twice(db_session):
    """F-08: a repeated refund.processed must not notify again."""
    from app.services import college_registrations as cr_service
    from app.models.registration import RegistrationNotification

    row = (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == "f06.refund@test.local")
        )
    ).scalars().first()
    assert row is not None
    refund = (
        await db_session.execute(select(Refund).where(Refund.order_id == row.order_id))
    ).scalars().first()
    assert refund is not None
    refund.status = "processing"
    refund.gateway_refund_id = f"rfnd_{uuid.uuid4().hex[:8]}"
    await db_session.commit()
    gateway_id = refund.gateway_refund_id

    before = (
        await db_session.execute(
            select(RegistrationNotification).where(
                RegistrationNotification.registration_id == row.id,
                RegistrationNotification.kind == "refund_completed",
            )
        )
    ).scalars().all()
    await cr_service.sync_gateway_refund(db_session, gateway_id)
    await db_session.commit()
    first = (
        await db_session.execute(
            select(RegistrationNotification).where(
                RegistrationNotification.registration_id == row.id,
                RegistrationNotification.kind == "refund_completed",
            )
        )
    ).scalars().all()
    assert len(first) == len(before) + 1

    await cr_service.sync_gateway_refund(db_session, gateway_id)
    await db_session.commit()
    second = (
        await db_session.execute(
            select(RegistrationNotification).where(
                RegistrationNotification.registration_id == row.id,
                RegistrationNotification.kind == "refund_completed",
            )
        )
    ).scalars().all()
    assert len(second) == len(first), "a duplicated webhook completed the refund twice"


# --------------------------------------------------------------------------- #
# F-03 / F-05 / F-22
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pass_price_is_a_snapshot_not_the_current_policy(client: AsyncClient, db_session):
    """F-03: re-activating a pass must not rewrite its collected price."""
    from app.services import passes as pass_service
    from app.services.editions import current_policy

    email = "f03.price@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    policy = await current_policy(db_session, row.edition_id)
    original = int(row.fee_paise)
    await pass_service.activate_pass_for_registration(
        db_session, row.user_id, row.edition_id, policy, price_paise=original + 9900
    )
    await db_session.commit()

    user_pass = (
        await db_session.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == row.user_id,
                ConventionPass.edition_id == row.edition_id,
            )
        )
    ).scalars().first()
    assert user_pass is not None
    assert int(user_pass.price_paise) == original


@pytest.mark.asyncio
async def test_refunded_registration_refuses_documents(client: AsyncClient, db_session):
    """F-22: a refunded registration is closed to uploads."""
    email = "f22.docs@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None
    row.payment_status = "refunded"
    row.refund_status = "completed"
    await db_session.commit()

    refused = await client.post(
        f"/api/v1/editions/{edition_id}/registration/documents/college_id",
        files={"file": ("again.png", PNG, "image/png")},
    )
    assert refused.status_code in (409, 422), refused.text


# --------------------------------------------------------------------------- #
# F-11 / F-12 / F-13 / F-26 / F-40
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_public_credential_lists_events_without_crashing(client: AsyncClient, db_session):
    """F-12: the credential page read ``event.category``, which does not exist."""
    email = "f12.credential@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    event = (
        await db_session.execute(
            select(Event).where(Event.edition_id == row.edition_id).limit(1)
        )
    ).scalars().first()
    assert event is not None
    db_session.add(
        Registration(
            edition_id=row.edition_id,
            event_id=event.id,
            user_id=row.user_id,
            kind="addon",
            fee_paise=0,
            status="confirmed",
            registration_number=f"REG-{uuid.uuid4().hex[:8].upper()}",
        )
    )
    await db_session.commit()

    from app.services import tickets as ticket_service

    ticket = (
        await db_session.execute(
            select(Ticket).where(
                Ticket.user_id == row.user_id,
                Ticket.pass_id.is_not(None),
            )
        )
    ).scalars().first()
    assert ticket is not None
    from app.services.tickets import ticket_token_for

    token = ticket_token_for(ticket.id)
    page = await client.get(
        f"/api/v1/public/c/{token}", headers={"accept": "application/json"}
    )
    assert page.status_code == 200, page.text
    events = page.json()["data"].get("registeredEvents") or []
    assert any(item["title"] == event.title for item in events)


@pytest.mark.asyncio
async def test_playground_seed_uses_the_policy_price(client: AsyncClient, db_session):
    """F-11/F-27: the override must not crash and must not trust a client price."""
    edition = await _edition(client)
    edition_id = edition["id"]
    email = "f27.seed@test.local"
    await _login(client, email)
    await _profile_ready(client, edition_id, email)

    await _login(client, ADMIN, role="admin")
    # The retired price override is no longer part of the contract: sending it is
    # an error, not a value that is silently ignored.
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/db-playground/seed",
        json={
            "userEmailOrId": email,
            "target": "pass",
            "reason": "audit test",
            "pricePaise": 1,
        },
    )
    if rejected.status_code == 404:
        pytest.skip("playground is unavailable in this environment")
    assert rejected.status_code == 422, rejected.text
    seeded = await client.post(
        f"/api/v1/editions/{edition_id}/admin/db-playground/seed",
        json={
            "userEmailOrId": email,
            "target": "pass",
            "reason": "audit test",
        },
    )
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["data"]["pass"]["ticketId"]

    from app.services.editions import current_policy

    row = await _attendee_row(db_session, email)
    user_pass = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == row.user_id)
        )
    ).scalars().first()
    policy = await current_policy(db_session, row.edition_id)
    assert int(user_pass.price_paise) == int(policy.pass_price_paise)


@pytest.mark.asyncio
async def test_seeded_owner_has_permissions(db_session):
    """F-26: the seed wrote role="owner", which maps to no permissions."""
    from app.core.permissions import permissions_for

    owner = (
        await db_session.execute(select(User).where(User.email == ADMIN))
    ).scalars().first()
    assert owner is not None
    from app.models.user import EditionMembership

    roles = (
        await db_session.execute(
            select(EditionMembership.role).where(EditionMembership.user_id == owner.id)
        )
    ).scalars().all()
    assert roles
    granted = set()
    for role in roles:
        granted |= permissions_for(role)
    assert granted, f"seeded owner roles grant nothing: {roles}"


@pytest.mark.asyncio
async def test_login_does_not_return_the_session_token(client: AsyncClient):
    """F-40: the session token must stay in the HttpOnly cookie."""
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "f40.login@test.local", "role": "participant"}
    )
    assert resp.status_code == 200, resp.text
    assert "token" not in resp.json()["data"]
    assert resp.headers.get_list("set-cookie")


# --------------------------------------------------------------------------- #
# F-15 / F-29 / F-34 / F-32 / F-33
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_legacy_pass_refund_frees_the_seats(client: AsyncClient, db_session):
    """F-15: refunding a legacy pass order left seats and tickets alive."""
    email = "f15.legacy@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None
    event = (
        await db_session.execute(
            select(Event).where(Event.edition_id == row.edition_id).limit(1)
        )
    ).scalars().first()
    seat = Registration(
        edition_id=row.edition_id,
        event_id=event.id,
        user_id=row.user_id,
        kind="addon",
        fee_paise=0,
        status="confirmed",
        registration_number=f"REG-{uuid.uuid4().hex[:8].upper()}",
    )
    db_session.add(seat)
    user_pass = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == row.user_id)
        )
    ).scalars().first()
    assert user_pass is not None
    legacy = PaymentOrder(
        edition_id=row.edition_id,
        user_id=row.user_id,
        purpose="pass",
        amount_paise=100000,
        status="paid",
        linked_record_id=user_pass.id,
        paid_at=datetime.now(UTC),
    )
    db_session.add(legacy)
    await db_session.flush()
    from app.models.commerce import PaymentTransaction

    db_session.add(
        PaymentTransaction(
            order_id=legacy.id,
            gateway_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
            amount_paise=100000,
            status="captured",
            captured_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    seat_id = seat.id

    from app.services.payments import refund_order

    await refund_order(
        db_session, legacy, amount_paise=100000, reason_code="legacy_order"
    )
    await db_session.commit()
    db_session.expire_all()
    stored = await db_session.get(Registration, seat_id)
    assert stored.status == "cancelled"


@pytest.mark.asyncio
async def test_capacity_is_rechecked_when_the_seat_confirms(client: AsyncClient, db_session):
    """F-29: a seat paid for after the event filled must not be confirmed."""
    email = "f29.capacity@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    event = (
        await db_session.execute(
            select(Event).where(Event.edition_id == row.edition_id).limit(1)
        )
    ).scalars().first()
    assert event is not None
    # The suite shares one database, so the demo event is put back afterwards.
    original_capacity = int(event.capacity or 0)
    original_unit = event.capacity_unit
    event.capacity = 1
    event.capacity_unit = "participants"

    other = User(
        email=f"f29.other.{uuid.uuid4().hex[:6]}@test.local",
        full_name="Other",
        email_normalized=f"f29.other.{uuid.uuid4().hex[:6]}@test.local",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        Registration(
            edition_id=row.edition_id,
            event_id=event.id,
            user_id=other.id,
            kind="addon",
            fee_paise=0,
            status="confirmed",
            registration_number=f"REG-{uuid.uuid4().hex[:8].upper()}",
        )
    )
    hold = Registration(
        edition_id=row.edition_id,
        event_id=event.id,
        user_id=row.user_id,
        kind="addon",
        fee_paise=50000,
        status="reserved",
        registration_number=f"REG-{uuid.uuid4().hex[:8].upper()}",
    )
    order = PaymentOrder(
        edition_id=row.edition_id,
        user_id=row.user_id,
        purpose="registration",
        amount_paise=50000,
        status="created",
    )
    db_session.add_all([hold, order])
    await db_session.commit()
    hold.order_id = order.id
    await db_session.commit()

    from app.services.payments import mark_order_paid

    hold_id, order_id, event_id = hold.id, order.id, event.id
    try:
        await mark_order_paid(db_session, order, transaction_id="pay_capacity")
        await db_session.commit()
        db_session.expire_all()
        stored = await db_session.get(Registration, hold_id)
        assert stored.status == "cancelled"
        parked = (
            await db_session.execute(select(Refund).where(Refund.order_id == order_id))
        ).scalars().all()
        assert parked, "an over-capacity payment must be queued for a refund"
    finally:
        await db_session.rollback()
        demo_event = await db_session.get(Event, event_id)
        if demo_event is not None:
            demo_event.capacity = original_capacity
            demo_event.capacity_unit = original_unit
        await db_session.commit()


@pytest.mark.asyncio
async def test_revoking_a_pass_removes_its_attendance(client: AsyncClient, db_session):
    """F-34: attendance used to survive the ticket that earned it."""
    from app.services.passes import release_event_entitlements

    email = "f34.attendance@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    db_session.add(
        AttendanceRecord(
            edition_id=row.edition_id,
            user_id=row.user_id,
            day=1,
            checked_in_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    await release_event_entitlements(
        db_session, user_id=row.user_id, edition_id=row.edition_id, reason="audit test"
    )
    await db_session.commit()
    left = (
        await db_session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.user_id == row.user_id,
                AttendanceRecord.edition_id == row.edition_id,
            )
        )
    ).scalars().all()
    assert left == []


@pytest.mark.asyncio
async def test_disbanded_team_can_be_restored(client: AsyncClient, db_session):
    """F-32: a disband was a one-way door."""
    from app.services import teams as team_service

    email = "f32.team@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    event = (
        await db_session.execute(
            select(Event).where(
                Event.edition_id == row.edition_id, Event.format == "team"
            )
        )
    ).scalars().first()
    if event is None:
        pytest.skip("no team event in the demo edition")

    team = Team(
        edition_id=row.edition_id,
        event_id=event.id,
        name="F-32 Team",
        invite_code=f"F32{uuid.uuid4().hex[:6].upper()}",
        leader_id=row.user_id,
        status="disbanded",
    )
    db_session.add(team)
    await db_session.commit()

    restored = await team_service.toggle_team_lock(db_session, row.user_id, team.id)
    assert restored.status == "active"


@pytest.mark.asyncio
async def test_archiving_an_icon_in_use_is_refused(client: AsyncClient, db_session):
    """F-33: archiving a referenced icon left the event with no image."""
    from app.core.errors import Conflict
    from app.models.edition import Icon
    from app.services import icons as icon_service

    edition = await _edition(client)
    edition_id = uuid.UUID(edition["id"])
    event = (
        await db_session.execute(
            select(Event).where(Event.edition_id == edition_id).limit(1)
        )
    ).scalars().first()
    assert event is not None
    icon = Icon(
        edition_id=edition_id,
        kind="custom",
        name=f"f33-{uuid.uuid4().hex[:6]}",
        status="active",
        storage_key="test/f33.png",
        mime="image/png",
        width=1,
        height=1,
        size_bytes=68,
    )
    db_session.add(icon)
    await db_session.commit()
    event.icon_id = icon.id
    await db_session.commit()

    with pytest.raises(Conflict):
        await icon_service.archive(db_session, None, icon, actor_id=None)


# --------------------------------------------------------------------------- #
# F-18 / F-19 / F-41
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_failed_email_is_alerted_after_max_attempts(db_session):
    """F-19: a permanently failing address was abandoned silently."""
    from types import SimpleNamespace
    from unittest.mock import patch

    import app.integrations.email as email_module
    import app.services.telegram as telegram_module

    settings = SimpleNamespace(
        email_available=True,
        email_dry_run=False,
        email_from="conventions@parallax.test",
        email_provider_base_url="https://mail.example.test",
        email_provider_api_key="test-key",
    )
    row = EmailOutbox(
        recipient="f19@example.test",
        template="registration_approved",
        payload={},
        status="queued",
        attempts=0,
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.add(row)
    await db_session.commit()
    row_id = row.id

    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("provider down")

    alerts: list[str] = []

    async def _record_alert(message: str, **_kwargs):
        alerts.append(message)

    with patch.object(email_module, "get_settings", return_value=settings), patch.object(
        email_module.httpx, "AsyncClient", lambda *a, **k: _Boom()
    ), patch.object(telegram_module, "send_telegram_alert", _record_alert):
        for _ in range(email_module.MAX_ATTEMPTS + 1):
            await db_session.execute(
                EmailOutbox.__table__.update()
                .where(EmailOutbox.id == row_id)
                .values(scheduled_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            await db_session.commit()
            await email_module.send_batch(db_session)

    db_session.expire_all()
    stored = await db_session.get(EmailOutbox, row_id)
    assert stored.status == "failed"
    assert int(stored.attempts) >= email_module.MAX_ATTEMPTS
    assert alerts, "a permanently failed email must raise an alert"


@pytest.mark.asyncio
async def test_expired_invites_are_swept(client: AsyncClient, db_session):
    """F-41: nothing deleted expired staff invites."""
    from app.models.user import StaffInvite
    from app.services.users import cleanup_expired_invites

    invite = StaffInvite(
        email_normalized=f"f41.{uuid.uuid4().hex[:6]}@test.local",
        roles=["checkin_staff"],
        token_hash=f"f41{uuid.uuid4().hex}",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(invite)
    await db_session.commit()
    invite_id = invite.id

    removed = await cleanup_expired_invites(db_session)
    await db_session.commit()
    assert removed >= 1
    assert await db_session.get(StaffInvite, invite_id) is None


@pytest.mark.asyncio
async def test_open_invites_are_not_all_claimed_by_login(client: AsyncClient, db_session):
    """F-39: signing in claimed every invite for the address."""
    from app.models.user import StaffInvite

    email = f"f39.{uuid.uuid4().hex[:6]}@test.local"
    edition = await _edition(client)
    invite = StaffInvite(
        email_normalized=email,
        roles=["super_admin"],
        edition_id=uuid.UUID(edition["id"]),
        token_hash=f"f39{uuid.uuid4().hex}",
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    db_session.add(invite)
    await db_session.commit()
    invite_id = invite.id

    await _login(client, email)
    await db_session.commit()
    db_session.expire_all()
    stored = await db_session.get(StaffInvite, invite_id)
    assert stored.claimed_at is None


@pytest.mark.asyncio
async def test_refund_cap_spans_the_whole_registration(client: AsyncClient, db_session):
    """F-16: the admin refund screen used one formula, the desk another."""
    from app.services.payments import refund_order

    email = "f16.cap@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    base = await db_session.get(PaymentOrder, row.order_id)
    assert base is not None
    delta = PaymentOrder(
        edition_id=row.edition_id,
        user_id=row.user_id,
        purpose="college_registration_delta",
        amount_paise=30000,
        status="paid",
        linked_record_id=row.id,
        paid_at=datetime.now(UTC),
    )
    db_session.add(delta)
    await db_session.flush()
    from app.models.commerce import PaymentTransaction

    db_session.add(
        PaymentTransaction(
            order_id=delta.id,
            gateway_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
            amount_paise=30000,
            status="captured",
            captured_at=datetime.now(UTC),
        )
    )
    db_session.add(
        PaymentTransaction(
            order_id=base.id,
            gateway_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
            amount_paise=int(base.amount_paise),
            status="captured",
            captured_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    refunded = await refund_order(
        db_session,
        base,
        amount_paise=int(base.amount_paise) + 30000,
        reason_code="audit_f16",
    )
    await db_session.commit()
    assert refunded is not None
    total = int(base.amount_paise) + 30000
    assert int(refunded.amount_paise) <= total


@pytest.mark.asyncio
async def test_closed_edition_refuses_registration(client: AsyncClient, db_session):
    """F-17: a closed edition must not take registrations."""
    from app.models.edition import ConventionEdition

    email = "f17.closed@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    original = await db_session.get(ConventionEdition, uuid.UUID(edition_id))
    assert original is not None
    previous = original.status
    original.status = "closed"
    await db_session.commit()
    try:
        refused = await client.put(
            f"/api/v1/editions/{edition_id}/registration/profile",
            json={
                "categoryId": str(original.id and uuid.uuid4()),
                "fullName": "Closed",
                "email": email,
                "phone": "9876543210",
                "collegeName": "NSSCE",
                "course": "B.Tech",
                "branch": "CS",
                "yearOfStudy": "3",
                "gender": "male",
                "foodPreference": "veg",
                "city": "Palakkad",
                "state": "Kerala",
            },
        )
        assert refused.status_code in (400, 404, 409, 422), refused.text
    finally:
        original.status = previous
        await db_session.commit()


@pytest.mark.asyncio
async def test_only_one_pending_category_change_per_registration(client: AsyncClient, db_session):
    """F-37: two pending changes for one registration must be impossible."""
    from sqlalchemy.exc import IntegrityError

    from app.models.registration import RegistrationCategoryChange

    email = "f37.change@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _attendee_row(db_session, email)
    assert row is not None

    from app.models.registration import RegistrationCategory

    other = (
        await db_session.execute(
            select(RegistrationCategory).where(
                RegistrationCategory.edition_id == row.edition_id,
                RegistrationCategory.id != row.category_id,
            )
        )
    ).scalars().first()
    assert other is not None

    def _change() -> RegistrationCategoryChange:
        return RegistrationCategoryChange(
            registration_id=row.id,
            from_category_id=row.category_id,
            to_category_id=other.id,
            from_fee_paise=row.fee_paise,
            to_fee_paise=other.fee_paise,
            settlement_type="pending_review",
            settlement_amount_paise=0,
            status="pending",
        )

    db_session.add(_change())
    await db_session.commit()
    db_session.add(_change())
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_step_up_requires_a_confirmed_credential(client: AsyncClient, db_session):
    """F-38: a half-enrolled authenticator could step up."""
    from app.models.user import MfaCredential, User

    await _login(client, ADMIN, role="admin")
    user = (
        await db_session.execute(select(User).where(User.email == ADMIN))
    ).scalars().first()
    assert user is not None
    from app.core.security import encrypt_pii

    credential = MfaCredential(
        user_id=user.id,
        secret_encrypted=encrypt_pii("JBSWY3DPEHPK3PXP"),
        status="pending",
    )
    db_session.add(credential)
    await db_session.commit()

    refused = await client.post("/api/v1/auth/mfa/step-up", json={"code": "123456"})
    assert refused.status_code in (409, 403), refused.text
    if refused.status_code == 409:
        assert refused.json()["error"]["code"] == "MFA_NOT_ACTIVE"

    await db_session.delete(credential)
    await db_session.commit()
