"""Regression tests for team lifecycle and edition cancellation (AUDIT02 A1/A2/A5/A8/A12).

Each test covers a transition that used to change a label while the dependent
flows (locking, joining, archiving, cancelling) kept running as if nothing had
happened.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import ConventionPass, Refund, Registration
from app.models.edition import ConventionEdition, Event, EventCategory
from app.services.tickets import issue_for_pass

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

from tests.seat_helpers import buy_seat


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
    """Create a throwaway published event so no seeded event is disturbed."""
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
        slug=f"team-{uuid.uuid4().hex[:8]}",
        title=title,
        summary="Throwaway event for a team/edition cascade test.",
        format=format,
        team_min_size=2,
        team_max_size=4,
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


async def _paid_registration(client: AsyncClient, edition_id: str, email: str) -> dict:
    """Complete a paid convention registration so the attendee holds a pass."""
    config = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    category = next(
        item for item in config["categories"] if item["code"] in ("polytechnic", "engineering")
    )
    profile = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": category["id"],
            "fullName": "Team Participant",
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


@pytest.mark.asyncio
async def test_locked_team_stays_visible_and_counted(client: AsyncClient, db_session):
    """Locking a roster must not hide the team from the portal or seat counts."""
    from app.services.events import capacity_usage

    email = "team.lock@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _fresh_event(
        db_session, uuid.UUID(edition_id), title="Team Lock Event", format="team"
    )

    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, edition_id, event.id)
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Locked Llamas"},
    )
    assert created.status_code in (200, 201), created.text
    team_id = created.json()["data"]["id"]

    locked = await client.post(f"/api/v1/editions/{edition_id}/teams/{team_id}/lock")
    assert locked.status_code == 200, locked.text
    assert locked.json()["data"]["status"] == "locked"

    # Every read used to filter status == "active": the team disappeared and its
    # seats stopped counting towards capacity.
    listed = await client.get(f"/api/v1/editions/{edition_id}/teams")
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["data"]] == [team_id]

    event_id = event.id
    db_session.expire_all()
    stored = await db_session.get(Event, event_id)
    assert (await capacity_usage(db_session, [stored]))[stored.id] == 1

    unlocked = await client.post(f"/api/v1/editions/{edition_id}/teams/{team_id}/lock")
    assert unlocked.status_code == 200, unlocked.text
    assert unlocked.json()["data"]["status"] == "active"


@pytest.mark.asyncio
async def test_leader_can_leave_a_multi_member_team(client: AsyncClient, db_session):
    """A leader of a 2+ member team must not hit MultipleResultsFound (500)."""
    leader = "team.leader@test.local"
    member = "team.member@test.local"
    await _login(client, leader)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, leader)
    event = await _fresh_event(
        db_session, uuid.UUID(edition_id), title="Team Leave Event", format="team"
    )
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, edition_id, event.id)
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Busy Badgers"},
    )
    assert created.status_code in (200, 201), created.text
    team = created.json()["data"]

    await _login(client, member)
    await _paid_registration(client, edition_id, member)
    # Joining needs the member's own seat on that event.
    await buy_seat(client, edition_id, event.id)
    joined = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join",
        json={"inviteCode": team["inviteCode"]},
    )
    assert joined.status_code == 200, joined.text

    # Two team rows match (leader + member); team_registration() used to raise.
    await _login(client, leader)
    left = await client.delete(f"/api/v1/editions/{edition_id}/teams/{team['id']}")
    assert left.status_code == 200, left.text


@pytest.mark.asyncio
async def test_join_team_refuses_a_closed_event(client: AsyncClient, db_session):
    """An invite code must not admit anyone to a closed or cancelled event."""
    leader = "team.closedleader@test.local"
    member = "team.closedmember@test.local"
    await _login(client, leader)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, leader)
    event = await _fresh_event(
        db_session, uuid.UUID(edition_id), title="Team Close Event", format="team"
    )
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, edition_id, event.id)
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Closing Coyotes"},
    )
    assert created.status_code in (200, 201), created.text
    team = created.json()["data"]

    stored = await db_session.get(Event, event.id)
    stored.status = "closed"
    await db_session.commit()

    await _login(client, member)
    await _paid_registration(client, edition_id, member)
    joined = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join",
        json={"inviteCode": team["inviteCode"]},
    )
    stored.status = "published"
    await db_session.commit()
    assert joined.status_code == 409, joined.text


@pytest.mark.asyncio
async def test_cancelling_an_edition_cascades_money_and_access(client: AsyncClient, db_session):
    """Cancelling a convention must close events, passes and paid orders."""
    from app.services.editions import cancel_edition

    email = "edition.cancel@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Edition Cancel Event")
    added = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    assert added.status_code in (200, 201), added.text
    order_id = uuid.UUID(added.json()["data"]["order"]["orderId"])
    seat_id = uuid.UUID(added.json()["data"]["registrations"][0]["id"])
    paid = await client.post(f"/api/v1/editions/{edition_id}/payments/{order_id}/mock")
    assert paid.status_code == 200, paid.text

    db_session.expire_all()
    stored_edition = await db_session.get(ConventionEdition, uuid.UUID(edition_id))
    # The suite shares one database file and cancelling closes every event and
    # pass of the edition, so snapshot what has to be handed back afterwards -
    # otherwise every later test sees a convention with no live events.
    event_statuses = {
        row.id: row.status
        for row in (
            await db_session.execute(
                select(Event).where(Event.edition_id == uuid.UUID(edition_id))
            )
        ).scalars()
    }
    pass_statuses = {
        row.id: row.status
        for row in (
            await db_session.execute(
                select(ConventionPass).where(ConventionPass.edition_id == uuid.UUID(edition_id))
            )
        ).scalars()
    }
    previous_status = stored_edition.status
    try:
        result = await cancel_edition(db_session, None, stored_edition, reason="Venue flooded")
        assert result["eventsClosed"] >= 1
        assert result["refundRequestsQueued"] >= 1

        db_session.expire_all()
        seat = await db_session.get(Registration, seat_id)
        assert seat.status == "cancelled"

        refunds = list(
            (
                await db_session.execute(select(Refund).where(Refund.order_id == order_id))
            ).scalars()
        )
        assert refunds and all(refund.status == "pending" for refund in refunds)

        passes = list(
            (
                await db_session.execute(
                    select(ConventionPass).where(
                        ConventionPass.edition_id == uuid.UUID(edition_id)
                    )
                )
            ).scalars()
        )
        assert passes and all(
            user_pass.status in ("cancelled", "refunded") for user_pass in passes
        )
    finally:
        stored_edition.status = previous_status
        for event_id, status in event_statuses.items():
            row = await db_session.get(Event, event_id)
            if row is not None:
                row.status = status
        for pass_id, status in pass_statuses.items():
            row = await db_session.get(ConventionPass, pass_id)
            if row is not None:
                row.status = status
                if status == "active":
                    await issue_for_pass(db_session, row)
        await db_session.commit()


@pytest.mark.asyncio
async def test_archiving_an_edition_stops_new_bookings(client: AsyncClient, db_session):
    """An archived convention must not keep selling add-on seats."""
    email = "edition.archive@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _fresh_event(db_session, uuid.UUID(edition_id), title="Edition Archive Event")

    stored = await db_session.get(ConventionEdition, uuid.UUID(edition_id))
    previous = stored.status
    stored.status = "archived"
    await db_session.commit()
    try:
        blocked = await client.post(
            f"/api/v1/editions/{edition_id}/registrations",
            json={"eventIds": [str(event.id)]},
        )
    finally:
        stored.status = previous
        await db_session.commit()
    assert blocked.status_code == 409, blocked.text
