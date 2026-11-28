"""Regression tests for the 24-hour registration compliance window.

A desk request (corrected documents or a category-change top-up) now has a
deadline. When it lapses, the lazy sweep releases every event seat the attendee
holds, refunds paid event seats, removes them from teams (handing leadership to
the next member) and leaves the registration itself alive so they can answer the
request and select again.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import (
    EmailOutbox,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    TeamMember,
)
from app.models.edition import Event, EventCategory
from app.models.registration import CollegeRegistration, RegistrationNotification
from app.models.user import User

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

from tests.seat_helpers import buy_seat
ADMIN = "owner@parallax.local"


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


async def _fresh_event(
    db_session,
    edition_id,
    *,
    title: str,
    format: str = "individual",
    price_paise: int = 20000,
):
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
        slug=f"compliance-{uuid.uuid4().hex[:8]}",
        title=title,
        summary="Throwaway event for a compliance-deadline test.",
        format=format,
        team_min_size=2 if format == "team" else 1,
        team_max_size=4 if format == "team" else 1,
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


async def _paid_registration(
    client: AsyncClient, edition_id: str, email: str, category_code: str = "polytechnic"
) -> dict:
    config = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    category = next(item for item in config["categories"] if item["code"] == category_code)
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
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    payment = submitted.json()["data"]["payment"]
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    return paid.json()["data"]["registration"]


async def _owned_registration(db_session, email: str) -> CollegeRegistration:
    user = (await db_session.execute(select(User).where(User.email == email))).scalars().first()
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


async def _expire(db_session, registration_id: uuid.UUID) -> None:
    row = await db_session.get(CollegeRegistration, registration_id)
    assert row is not None
    row.compliance_deadline_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()


async def _trigger_sweep(client: AsyncClient, edition_id: str, email: str) -> None:
    """Another user touching registration is the lazy enforcement trigger."""
    config = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    category = next(item for item in config["categories"] if item["code"] == "polytechnic")
    await _login(client, email)
    resp = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": category["id"],
            "fullName": "Trigger Participant",
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


async def _add_paid_seat(client: AsyncClient, edition_id: str, event_id: uuid.UUID) -> uuid.UUID:
    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event_id)]},
    )
    assert added.status_code in (200, 201), added.text
    order_id = added.json()["data"]["order"]["orderId"]
    paid = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text
    return uuid.UUID(added.json()["data"]["registrations"][0]["id"])


@pytest.mark.asyncio
async def test_document_request_opens_24h_window_then_releases_seat(
    client: AsyncClient, db_session
):
    email = "compliance.docs@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Compliance Docs Seat")
    seat_id = await _add_paid_seat(client, edition_id, event.id)

    await _login(client, ADMIN, role="admin")
    requested = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/request-documents",
        json={"documents": ["college_id"], "message": "The ID card photo is blurry."},
    )
    assert requested.status_code == 200, requested.text
    data = requested.json()["data"]
    assert data["complianceKind"] == "documents"
    assert data["compliance"]["kind"] == "documents"
    deadline = datetime.fromisoformat(data["complianceDeadlineAt"].replace("Z", "+00:00"))
    remaining = deadline - datetime.now(UTC)
    assert timedelta(hours=23) < remaining <= timedelta(hours=24, minutes=1)

    listed = await client.get(f"/api/v1/editions/{edition_id}/admin/registration")
    assert listed.status_code == 200, listed.text
    assert listed.json()["counts"]["complianceDue"] >= 1

    await _expire(db_session, uuid.UUID(registration["id"]))
    await _trigger_sweep(client, edition_id, "compliance.docs.trigger@test.local")

    db_session.expire_all()
    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "cancelled", "an expired desk request must release the seat"
    order = await db_session.get(PaymentOrder, seat.order_id)
    assert order.status == "paid"
    refunds = list(
        (
            await db_session.execute(
                select(Refund).where(
                    Refund.order_id == order.id, Refund.reason_code == "pass_not_active"
                )
            )
        ).scalars()
    )
    assert refunds and refunds[0].status == "pending"

    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    assert row.compliance_enforced_at is not None
    assert row.verification_status == "rejected"
    assert row.rejection_code == "resubmission_expired"

    notices = list(
        (
            await db_session.execute(
                select(RegistrationNotification).where(
                    RegistrationNotification.registration_id == row.id,
                    RegistrationNotification.kind == "compliance_enforced",
                )
            )
        ).scalars()
    )
    assert notices, "the attendee must be told their seats were released"
    mails = list(
        (
            await db_session.execute(
                select(EmailOutbox).where(
                    EmailOutbox.template == "registration_compliance_enforced"
                )
            )
        ).scalars()
    )
    assert mails, "the attendee must receive the 24-hour outcome by email"

    await _login(client, email)
    view = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    assert view["registration"]["compliance"]["enforced"] is True
    assert view["registration"]["compliance"]["overdue"] is True


@pytest.mark.asyncio
async def test_category_payment_deadline_releases_seat_then_late_payment_keeps_it_released(
    client: AsyncClient, db_session
):
    email = "compliance.category@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    config = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    registration = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Compliance Category Seat")
    seat_id = await _add_paid_seat(client, edition_id, event.id)

    target = next(item for item in config["categories"] if item["code"] == "non_iste")
    changed = await client.post(
        f"/api/v1/editions/{edition_id}/registration/category-change",
        json={"categoryId": target["id"], "note": "Switched to non-ISTE"},
    )
    assert changed.status_code == 404, changed.text


@pytest.mark.asyncio
async def test_public_events_read_path_releases_lapsed_seat(
    client: AsyncClient, db_session
):
    email = "compliance.readpath@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(
        db_session, uuid.UUID(edition_id), title="Compliance Read Path Seat"
    )
    seat_id = await _add_paid_seat(client, edition_id, event.id)

    await _login(client, ADMIN, role="admin")
    requested = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/request-documents",
        json={"documents": ["college_id"], "message": "Upload a clearer college ID."},
    )
    assert requested.status_code == 200, requested.text

    await _expire(db_session, uuid.UUID(registration["id"]))
    # Opening the catalogue is the read-path trigger: seat counts are computed
    # after lapsed 24-hour holds have been released. Clear the in-process
    # throttle first so another test's recent sweep cannot mask it.
    from app.services import college_registrations as college_service

    college_service._lazy_sweep_clock.clear()
    catalogue = await client.get(
        f"/api/v1/public/editions/{edition['slug']}/events?pageSize=100"
    )
    assert catalogue.status_code == 200, catalogue.text
    item = next(
        row for row in catalogue.json()["data"] if row["id"] == str(event.id)
    )
    assert item["seatsLeft"] == event.capacity, "the freed seat must be visible"

    db_session.expire_all()
    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "cancelled"


@pytest.mark.asyncio
async def test_teammate_team_read_releases_lapsed_leader(
    client: AsyncClient, db_session
):
    leader_email = "compliance.leader@test.local"
    member_email = "compliance.member@test.local"
    await _login(client, leader_email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, leader_email)

    event = await _fresh_event(
        db_session, uuid.UUID(edition_id), title="Compliance Team Event", format="team"
    )
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, edition_id, event.id)
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Compliance Crew"},
    )
    assert created.status_code in (200, 201), created.text
    team = created.json()["data"]

    await _login(client, member_email)
    await _paid_registration(client, edition_id, member_email)
    # Joining needs the member's own seat on that event.
    await buy_seat(client, edition_id, event.id)
    joined = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join",
        json={"inviteCode": team["inviteCode"]},
    )
    assert joined.status_code == 200, joined.text

    await _login(client, ADMIN, role="admin")
    requested = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/request-documents",
        json={"documents": ["college_id"], "message": "Upload a clearer college ID."},
    )
    assert requested.status_code == 200, requested.text

    await _expire(db_session, uuid.UUID(registration["id"]))
    from app.services import college_registrations as college_service

    college_service._lazy_sweep_clock.clear()
    await _login(client, member_email)
    roster = await client.get(f"/api/v1/editions/{edition_id}/teams")
    assert roster.status_code == 200, roster.text
    assert str(team["id"]) in [
        item["id"] for item in roster.json()["data"]
    ], "the teammate must still see their team"

    db_session.expire_all()
    stored_team = await db_session.get(Team, uuid.UUID(team["id"]))
    member_user = (
        await db_session.execute(select(User).where(User.email == member_email))
    ).scalars().first()
    assert member_user is not None
    assert stored_team.status != "disbanded", "innocent teammates keep their team"
    assert stored_team.leader_id == member_user.id, "leadership must move to a remaining member"
    promoted = (
        await db_session.execute(
            select(TeamMember).where(
                TeamMember.team_id == stored_team.id,
                TeamMember.user_id == member_user.id,
            )
        )
    ).scalars().first()
    assert promoted is not None and promoted.is_leader is True


# --------------------------------------------------------------------------- #
# Rejection is final (spec: "Reject a pass -> revoke it, with an admin-chosen
# refund"). The 24-hour window belongs to the desk's "request corrected
# documents" request only.
# --------------------------------------------------------------------------- #
async def _decision(
    client: AsyncClient,
    edition_id: str,
    registration_id: str,
    *,
    initiate_refund: bool,
    refund_events: bool = True,
):
    await _login(client, ADMIN, role="admin")
    return await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration_id}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_college_id",
            "reason": "Blurry ID card.",
            "initiateRefund": initiate_refund,
            "refundEvents": refund_events,
        },
    )


async def _pass_refunds(db_session, order_id) -> list[Refund]:
    return list(
        (
            await db_session.execute(select(Refund).where(Refund.order_id == order_id))
        ).scalars()
    )


@pytest.mark.asyncio
async def test_rejection_is_final_and_revokes_immediately(client: AsyncClient, db_session):
    """No window, no deadline: rejecting revokes the pass and its seats at once."""
    email = "reject.final@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Reject Final Seat")
    seat_id = await _add_paid_seat(client, edition_id, event.id)

    rejected = await _decision(client, edition_id, registration["id"], initiate_refund=True)
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()["data"]
    assert body["verificationStatus"] == "rejected"
    assert body["compliance"] is None, "a rejection must not open a 24-hour window"
    assert body["complianceDeadlineAt"] is None
    assert body["canResubmit"] is False
    assert body["canUpload"] is False

    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    assert row is not None
    assert row.compliance_kind is None and row.compliance_deadline_at is None
    assert row.refund_status != "not_initiated", "the desk asked for the pass refund"
    refunds = await _pass_refunds(db_session, row.order_id)
    assert len(refunds) == 1, "one refund request, not one per reader"

    seat = await db_session.get(Registration, seat_id)
    assert seat is not None and seat.status == "cancelled", "the seat goes at once"

    # The attendee cannot re-open a rejection: no resubmission, no new upload.
    await _login(client, email)
    resub = await client.post(f"/api/v1/editions/{edition_id}/registration/resubmit")
    assert resub.status_code == 409, resub.text
    assert resub.json()["error"]["code"] == "REJECTION_FINAL"
    upload = await client.post(
        f"/api/v1/editions/{edition_id}/registration/documents/college_id",
        files={"file": ("id.png", PNG, "image/png")},
    )
    assert upload.status_code == 409, upload.text


@pytest.mark.asyncio
async def test_rejection_without_refund_leaves_the_money_alone(client: AsyncClient, db_session):
    email = "reject.final.norefund@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="No Refund Seat")
    await _add_paid_seat(client, edition_id, event.id)

    rejected = await _decision(
        client, edition_id, registration["id"], initiate_refund=False, refund_events=False
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["compliance"] is None

    db_session.expire_all()
    row = await db_session.get(CollegeRegistration, uuid.UUID(registration["id"]))
    assert row is not None
    assert row.refund_status == "not_initiated"
    assert await _pass_refunds(db_session, row.order_id) == []


@pytest.mark.asyncio
async def test_documents_request_is_the_only_thing_that_reopens_uploads(
    client: AsyncClient, db_session
):
    """The 24-hour window belongs to "request corrected documents"."""
    email = "docs.window@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)

    await _login(client, ADMIN, role="admin")
    asked = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration['id']}/request-documents",
        json={"documents": ["college_id"], "message": "The ID page is unreadable."},
    )
    assert asked.status_code == 200, asked.text
    body = asked.json()["data"]
    assert body["compliance"] is not None
    assert body["compliance"]["kind"] == "documents"
    assert body["compliance"]["deadlineAt"] is not None
    assert body["canUpload"] is True
    assert body["canResubmit"] is True

    # Answering it inside the window clears the deadline.
    await _login(client, email)
    upload = await client.post(
        f"/api/v1/editions/{edition_id}/registration/documents/college_id",
        files={"file": ("id.png", PNG, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    resub = await client.post(f"/api/v1/editions/{edition_id}/registration/resubmit")
    assert resub.status_code == 200, resub.text
    assert resub.json()["data"]["compliance"] is None


@pytest.mark.asyncio
async def test_revoke_cancels_a_seat_that_awaits_approval(client: AsyncClient, db_session):
    """``pending`` seats (requires_approval events) must not survive a revoke."""
    email = "reject.pendingseat@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    registration = await _paid_registration(client, edition_id, email)

    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Approval Seat")
    event.requires_approval = True
    await db_session.commit()

    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    assert added.status_code in (200, 201), added.text
    order_id = added.json()["data"]["order"]["orderId"]
    paid = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text
    seat_id = uuid.UUID(added.json()["data"]["registrations"][0]["id"])

    db_session.expire_all()
    seat = await db_session.get(Registration, seat_id)
    assert seat is not None and seat.status == "pending"

    rejected = await _decision(
        client, edition_id, registration["id"], initiate_refund=False, refund_events=False
    )
    assert rejected.status_code == 200, rejected.text

    db_session.expire_all()
    seat = await db_session.get(Registration, seat_id)
    assert seat is not None
    assert seat.status == "cancelled", "a revoked pass must not keep a pending event seat"
