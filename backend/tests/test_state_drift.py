"""Regression tests for state-drift guards.

Each test here failed (or was impossible to write) before the audit fixes:
one entity changed state, and a dependent flow kept going as if it had not.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import ConventionPass, PaymentOrder, Refund, Registration, Ticket
from app.models.registration import CollegeRegistration
from app.services import payments as payment_service
from app.services.passes import pass_gate_blocked
from app.services.tickets import resolve as resolve_ticket

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _fresh_event(db_session, edition_id, *, title: str, price_paise: int = 20000):
    """Create a throwaway published event so no seeded event is disturbed."""
    from app.models.edition import Event, EventCategory

    category = (
        await db_session.execute(
            select(EventCategory).where(EventCategory.edition_id == edition_id).limit(1)
        )
    ).scalars().first()
    assert category is not None
    now = datetime.now(UTC)
    event = Event(
        edition_id=edition_id,
        category_id=category.id,
        slug=f"drift-{uuid.uuid4().hex[:8]}",
        title=title,
        summary="Throwaway event for a state-drift test.",
        format="individual",
        base_value_paise=price_paise,
        addon_price_paise=price_paise,
        capacity=50,
        starts_at=now + timedelta(days=20),
        ends_at=now + timedelta(days=20, hours=2),
        registration_opens_at=now - timedelta(days=1),
        registration_closes_at=now + timedelta(days=18),
        status="published",
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


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


async def _profile(client: AsyncClient, edition_id: str, category_id: str, email: str) -> None:
    resp = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": category_id,
            "fullName": "Drift Participant",
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
    assert resp.status_code == 200, resp.text


async def _upload(client: AsyncClient, edition_id: str, doc_type: str) -> None:
    resp = await client.post(
        f"/api/v1/editions/{edition_id}/registration/documents/{doc_type}",
        files={"file": (f"{doc_type}.png", PNG, "image/png")},
    )
    assert resp.status_code == 200, resp.text


async def _paid_registration(
    client: AsyncClient, edition_id: str, email: str, category_code: str = "polytechnic"
) -> tuple[dict, dict]:
    config = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    category = next(item for item in config["categories"] if item["code"] == category_code)
    await _profile(client, edition_id, category["id"], email)
    await _upload(client, edition_id, "college_id")
    await _upload(client, edition_id, "photo")
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    payment = submitted.json()["data"]["payment"]
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    return paid.json()["data"]["registration"], payment


@pytest.mark.asyncio
async def test_closing_event_cascades_seats_tickets_and_refund(client: AsyncClient, db_session):
    """Closing an event must not leave paid seats, live tickets and no refund."""
    email = "drift.event@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    # The pass is the precondition for buying an add-on seat.
    await _paid_registration(client, edition_id, email)

    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Drift Throwaway")
    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    assert added.status_code in (200, 201), added.text
    registration_id = added.json()["data"]["registrations"][0]["id"]
    order_id = added.json()["data"]["order"]["orderId"]
    paid = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text

    await _login(client, "owner@parallax.local", role="admin")
    detail = (
        await client.get(f"/api/v1/editions/{edition_id}/admin/events/{event.id}")
    ).json()["data"]
    keys = ("categoryId", "slug", "title", "summary", "format", "startsAt", "endsAt")
    payload = {key: detail.get(key) for key in keys}
    payload["status"] = "cancelled"
    payload["changeReason"] = "Venue unavailable"
    closed = await client.patch(
        f"/api/v1/editions/{edition_id}/admin/events/{event.id}", json=payload
    )
    # Before the fix this was a guaranteed 500 from the str-args .in_() call.
    assert closed.status_code == 200, closed.text

    db_session.expire_all()
    row = await db_session.get(Registration, uuid.UUID(registration_id))
    assert row.status == "cancelled"
    assert row.cancelled_by == "admin"

    pending = list(
        (
            await db_session.execute(
                select(Refund).where(Refund.reason_code == "event_cancelled")
            )
        ).scalars()
    )
    assert pending, "closing a paid event must queue a refund for attendees"
    assert all(refund.status == "pending" for refund in pending)

    seat_ticket = (
        await db_session.execute(
            select(Ticket).where(Ticket.registration_id == row.id)
        )
    ).scalars().first()
    assert seat_ticket is None or seat_ticket.status != "active", (
        "the cancelled seat's ticket must not stay scannable"
    )


@pytest.mark.asyncio
async def test_reject_then_late_payment_is_refunded_not_revived(client: AsyncClient, db_session):
    """Money arriving for a rejected registration becomes a refund, never access."""
    email = "drift.late@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration, _ = await _paid_registration(client, edition_id, email)

    await _login(client, "owner@parallax.local", role="admin")
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_college_id",
            "reason": "Not a real college id.",
            "initiateRefund": False,
        },
    )
    assert rejected.status_code == 200, rejected.text

    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    order_id = row.order_id
    # Pretend the gateway settles the (already expired) order anyway.
    order = await db_session.get(PaymentOrder, order_id)
    order.status = "created"
    await db_session.commit()

    await payment_service.mark_order_paid(
        db_session,
        order,
        transaction_id=f"pay_late_{uuid.uuid4().hex[:10]}",
    )
    await db_session.commit()
    db_session.expire_all()

    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    assert row.verification_status == "rejected", "a late payment must not un-reject"
    stored_pass = (
        await db_session.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == row.user_id,
                ConventionPass.edition_id == row.edition_id,
            )
        )
    ).scalars().first()
    assert stored_pass is None or stored_pass.status != "active"

    refunds = list(
        (
            await db_session.execute(
                select(Refund).where(Refund.order_id == order_id)
            )
        ).scalars()
    )
    assert any(refund.status == "pending" for refund in refunds), (
        "the late payment must be parked in the refund ledger"
    )


@pytest.mark.asyncio
async def test_submit_after_refund_is_refused(client: AsyncClient, db_session):
    """A refunded registration cannot be pushed back into checkout."""
    email = "drift.refunded@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration, _ = await _paid_registration(client, edition_id, email)

    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    row.payment_status = "refunded"
    row.refund_status = "completed"
    await db_session.commit()

    await _login(client, email)
    resubmit = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert resubmit.status_code in (409, 403), resubmit.text


@pytest.mark.asyncio
async def test_partial_refund_keeps_pass_valid(client: AsyncClient, db_session):
    """A partial refund refunds money, not the seat."""
    email = "drift.partial@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration, _ = await _paid_registration(client, edition_id, email)

    await _login(client, "owner@parallax.local", role="admin")
    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    half = row.fee_paise // 2
    refund = await client.post(
        f"/api/v1/editions/{edition_id}/admin/refunds",
        json={
            "orderId": str(row.order_id),
            "amountPaise": half,
            "reasonCode": "partial_goodwill",
        },
    )
    assert refund.status_code == 200, refund.text

    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    detail = await client.get(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}"
    )
    state = detail.json()["data"]["state"]
    assert state == "partially_refunded", state
    blocked = await pass_gate_blocked(db_session, row.user_id, row.edition_id)
    assert not blocked, "a participant who kept their seat must still get in"

    stored_pass = (
        await db_session.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == row.user_id,
                ConventionPass.edition_id == row.edition_id,
            )
        )
    ).scalars().first()
    assert stored_pass is None or stored_pass.status == "active"


@pytest.mark.asyncio
async def test_registration_number_only_resolves_to_pass_ticket(client: AsyncClient, db_session):
    """Scanning a registration number must never admit on an event ticket."""
    email = "drift.scan@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = uuid.UUID(edition["id"])
    registration, _ = await _paid_registration(client, str(edition_id), email)

    event = await _fresh_event(db_session, edition_id, title="Drift Scan")
    await client.post(
        f"/api/v1/editions/{edition_id}/registrations", json={"eventIds": [str(event.id)]}
    )
    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    ticket = await resolve_ticket(db_session, row.registration_number, edition_id)
    if ticket is not None:
        assert ticket.pass_id is not None


@pytest.mark.asyncio
async def test_pass_sync_does_not_revive_closed_event_seat(client: AsyncClient, db_session):
    """A selection saved before the event closed must not re-issue the seat."""
    from app.models.commerce import IncludedEventSelection
    from app.models.edition import Event
    from app.services.events import close_event
    from app.services.passes import selections_for, sync_included_registrations

    edition = await _edition(client)
    edition_id = uuid.UUID(edition["id"])
    event = await _fresh_event(db_session, edition_id, title="Drift Sync")

    from app.services.editions import current_policy
    from app.services.users import upsert_google_user

    owner, _ = await upsert_google_user(
        db_session,
        claims={
            "sub": f"drift-seat-{uuid.uuid4().hex[:8]}",
            "email": f"drift.seat.{uuid.uuid4().hex[:6]}@test.local",
            "email_verified": True,
        },
    )
    policy = await current_policy(db_session, edition_id)
    stored_pass = ConventionPass(
        edition_id=edition_id,
        user_id=owner.id,
        price_paise=policy.pass_price_paise or 0,
        policy_version=policy.version,
        lunch_days=policy.lunch_included_days or [],
        status="active",
        paid_at=datetime.now(UTC),
    )
    db_session.add(stored_pass)
    await db_session.flush()
    # A real pass always comes with an entry ticket; later suites scan for one.
    from app.services.tickets import issue_for_pass

    await issue_for_pass(db_session, stored_pass)

    seat = Registration(
        edition_id=edition_id,
        user_id=owner.id,
        event_id=event.id,
        kind="included",
        fee_paise=0,
        status="confirmed",
        registration_number=f"REG-SEAT-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(seat)
    db_session.add(
        IncludedEventSelection(
            pass_id=stored_pass.id,
            event_id=event.id,
            base_value_paise_snapshot=0,
            status="active",
        )
    )
    await db_session.commit()

    pass_id, seat_id = stored_pass.id, seat.id
    event.status = "cancelled"
    await close_event(db_session, None, event, reason="Test cancellation")
    await db_session.commit()
    db_session.expire_all()
    stored_pass = await db_session.get(ConventionPass, pass_id)

    # Any later pass sync (approval, selection save, price change) must hold.
    await sync_included_registrations(
        db_session, stored_pass, await selections_for(db_session, stored_pass.id)
    )
    await db_session.commit()
    db_session.expire_all()

    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "cancelled"


async def _owned_registration(db_session, email: str) -> CollegeRegistration:
    from app.models.user import User

    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalars().first()
    assert user is not None
    row = (
        await db_session.execute(
            select(CollegeRegistration)
            .where(CollegeRegistration.user_id == user.id)
            .order_by(CollegeRegistration.created_at.desc())
        )
    ).scalars().first()
    assert row is not None
    return row


@pytest.mark.asyncio
async def test_suspension_frees_seats_and_refunds_event_purchases(
    client: AsyncClient, db_session
):
    """Suspending an account must not leave confirmed seats and paid seats behind."""
    email = "drift.suspend@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)

    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Suspension Seat")
    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    assert added.status_code in (200, 201), added.text
    seat_id = uuid.UUID(added.json()["data"]["registrations"][0]["id"])
    order_id = uuid.UUID(added.json()["data"]["order"]["orderId"])
    paid = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text

    row = await _owned_registration(db_session, email)
    user_id = row.user_id

    await _login(client, "owner@parallax.local", role="admin")
    suspended = await client.patch(
        f"/api/v1/editions/{edition_id}/admin/users/{user_id}/status",
        json={"status": "suspended", "reason": "Chargeback investigation"},
    )
    assert suspended.status_code == 200, suspended.text

    db_session.expire_all()
    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "cancelled", "a suspended account must not hold a seat"
    assert seat.cancelled_by == "admin"

    seat_ticket = (
        await db_session.execute(select(Ticket).where(Ticket.registration_id == seat_id))
    ).scalars().first()
    assert seat_ticket is None or seat_ticket.status != "active"

    addon_order = await db_session.get(PaymentOrder, order_id)
    assert addon_order.status == "refunded", "the paid seat's money must come back"
    refunds = list(
        (
            await db_session.execute(
                select(Refund).where(
                    Refund.order_id == order_id, Refund.reason_code == "pass_not_active"
                )
            )
        ).scalars()
    )
    assert refunds and refunds[0].status == "processed"

    stored_pass = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == user_id)
        )
    ).scalars().first()
    assert stored_pass.status == "suspended"


@pytest.mark.asyncio
async def test_reactivation_does_not_revive_a_refunded_pass(client: AsyncClient, db_session):
    """Un-suspending must not hand back a pass that was refunded meanwhile."""
    email = "drift.revive@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = await _owned_registration(db_session, email)
    user_id = row.user_id

    await _login(client, "owner@parallax.local", role="admin")
    await client.patch(
        f"/api/v1/editions/{edition_id}/admin/users/{user_id}/status",
        json={"status": "suspended", "reason": "Investigation"},
    )
    # The desk refunds the registration while the account is suspended.
    registration_id = row.id
    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, registration_id)
    row.payment_status = "refunded"
    row.refund_status = "completed"
    await db_session.commit()

    reactivated = await client.patch(
        f"/api/v1/editions/{edition_id}/admin/users/{user_id}/status",
        json={"status": "active", "reason": "Cleared"},
    )
    assert reactivated.status_code == 200, reactivated.text

    db_session.expire_all()
    stored_pass = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == user_id)
        )
    ).scalars().first()
    assert stored_pass.status != "active", "a refunded pass must not be revived"

    live_tickets = list(
        (
            await db_session.execute(
                select(Ticket).where(
                    Ticket.user_id == user_id,
                    Ticket.pass_id.is_not(None),
                    Ticket.status.in_(["active", "valid"]),
                )
            )
        ).scalars()
    )
    assert not live_tickets, "no fresh entry ticket may be issued for a refunded pass"


@pytest.mark.asyncio
async def test_my_registrations_excludes_teammates(client: AsyncClient, db_session):
    """The portal list is the attendee's own seats, not the whole roster's."""
    edition = await _edition(client)
    edition_id = edition["id"]
    slug = edition["slug"]

    await _login(client, "drift.leader@test.local")
    await _paid_registration(client, edition_id, "drift.leader@test.local")
    team_event = next(
        event
        for event in (
            await client.get(
                f"/api/v1/public/editions/{slug}/events?format=team&pageSize=100"
            )
        ).json()["data"]
    )
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": team_event["id"], "name": "Drift Squad"},
    )
    assert created.status_code == 200, created.text
    code = created.json()["data"]["inviteCode"]
    leader_rows = (await client.get(f"/api/v1/editions/{edition_id}/registrations")).json()["data"]
    leader_ids = {row["id"] for row in leader_rows}

    await _login(client, "drift.member@test.local")
    await _paid_registration(client, edition_id, "drift.member@test.local")
    joined = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join", json={"inviteCode": code}
    )
    assert joined.status_code == 200, joined.text

    member_rows = (await client.get(f"/api/v1/editions/{edition_id}/registrations")).json()["data"]
    member_ids = {row["id"] for row in member_rows}

    assert member_ids.isdisjoint(leader_ids), "teammates must not see each other's seats"
    assert all(row["eventId"] == team_event["id"] for row in member_rows if row["kind"] == "team")


@pytest.mark.asyncio
async def test_reject_without_refund_still_queues_addon_money(client: AsyncClient, db_session):
    """A cancellation that frees a paid seat must leave its money in the ledger."""
    email = "drift.norefund@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration, _ = await _paid_registration(client, edition_id, email)

    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Unrefunded Seat")
    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    assert added.status_code in (200, 201), added.text
    seat_id = uuid.UUID(added.json()["data"]["registrations"][0]["id"])
    order_id = uuid.UUID(added.json()["data"]["order"]["orderId"])
    paid = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text

    await _login(client, "owner@parallax.local", role="admin")
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_college_id",
            "reason": "Chargeback-adjacent case, refund deferred.",
            "initiateRefund": False,
        },
    )
    assert rejected.status_code == 200, rejected.text

    db_session.expire_all()
    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "cancelled"

    queued = list(
        (
            await db_session.execute(
                select(Refund).where(
                    Refund.order_id == order_id, Refund.status == "pending"
                )
            )
        ).scalars()
    )
    assert queued, "the paid seat's money must be queued for the finance desk"
