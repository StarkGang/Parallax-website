"""Regression tests for the AUDIT03 fixes.

Each test pins one of the defects that the third audit found: priced team seats,
team teardown, individual seats on team events, replaced checkout orders, the
refund ledger that spans a category upgrade, refund settlement honesty, the
"completed" refund that used to start a new one, and the dashboard units.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    TeamMember,
    Ticket,
)
from app.models.registration import CollegeRegistration
try:
    from tests.test_teams_and_editions import (
        _edition,
        _fresh_event,
        _login,
        _paid_registration,
    )
except ImportError:
    from test_teams_and_editions import (
        _edition,
        _fresh_event,
        _login,
        _paid_registration,
    )


async def _priced_team_event(db_session, edition_id, *, price_paise: int, basis: str):
    event = await _fresh_event(
        db_session,
        edition_id,
        title=f"Priced team {basis}",
        format="team",
        price_paise=price_paise,
    )
    event.team_fee_basis = basis
    await db_session.commit()
    await db_session.refresh(event)
    return event


async def _profile_ready(client: AsyncClient, edition_id: str, email: str) -> dict:
    """Create the registration row and uploads, without paying it."""
    config = (await client.get(f"/api/v1/editions/{edition_id}/registration")).json()["data"]
    category = next(
        item for item in config["categories"] if item["code"] in ("polytechnic", "engineering")
    )
    profile = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": category["id"],
            "fullName": "Order Replacement",
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
    try:
        from tests.test_teams_and_editions import PNG
    except ImportError:
        from test_teams_and_editions import PNG

    for doc_type in ("college_id", "photo"):
        uploaded = await client.post(
            f"/api/v1/editions/{edition_id}/registration/documents/{doc_type}",
            files={"file": (f"{doc_type}.png", PNG, "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
    return category


def _payment_of(payload: dict) -> dict | None:
    return payload.get("payment")


@pytest.mark.asyncio
async def test_priced_team_seat_is_reserved_until_paid(client: AsyncClient, db_session):
    """A per-participant team event must charge every member (B3)."""
    email = "team.priced@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _priced_team_event(
        db_session, uuid.UUID(edition_id), price_paise=80000, basis="per_participant"
    )

    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Charging Five"},
    )
    assert created.status_code in (200, 201), created.text
    payment = _payment_of(created.json()["data"])
    assert payment is not None, "a priced team seat must hand back an order"
    assert payment["amountPaise"] == 80000

    seat = (
        await db_session.execute(
            select(Registration).where(
                Registration.event_id == event.id,
                Registration.status == "reserved",
            )
        )
    ).scalars().first()
    assert seat is not None and seat.fee_paise == 80000
    seat_id = seat.id
    assert (
        await db_session.execute(select(Ticket).where(Ticket.registration_id == seat_id))
    ).scalars().first() is None, "a reserved seat must not get a ticket yet"

    paid = await client.post(
        f"/api/v1/editions/{edition_id}/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    db_session.expire_all()
    seat = await db_session.get(Registration, seat_id)
    assert seat.status == "confirmed"
    ticket = (
        await db_session.execute(select(Ticket).where(Ticket.registration_id == seat_id))
    ).scalars().first()
    assert ticket is not None and ticket.status == "active"


@pytest.mark.asyncio
async def test_per_team_fee_is_charged_once(client: AsyncClient, db_session):
    """A per-team event charges the leader once and admits the members (B3)."""
    leader_email = "team.perteam.lead@test.local"
    member_email = "team.perteam.member@test.local"
    await _login(client, leader_email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, leader_email)
    event = await _priced_team_event(
        db_session, uuid.UUID(edition_id), price_paise=120000, basis="per_team"
    )
    event_id = event.id
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Per Team Five"},
    )
    assert created.status_code in (200, 201), created.text
    body = created.json()["data"]
    payment = _payment_of(body)
    assert payment is not None and payment["amountPaise"] == 120000
    # The invite code stays locked until the leader's team payment is in.
    assert body["inviteCode"] is None

    # The leader pays for the team; then the invite admits a member for free.
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    invite = (
        await db_session.execute(
            select(Team.invite_code).where(Team.id == uuid.UUID(body["id"]))
        )
    ).scalar_one()
    assert invite

    await _login(client, member_email)
    await _paid_registration(client, edition_id, member_email)
    joined = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert joined.status_code == 200, joined.text
    assert _payment_of(joined.json()["data"]) is None
    team_id = uuid.UUID(body["id"])

    db_session.expire_all()
    member_seat = (
        await db_session.execute(
            select(Registration).where(
                Registration.event_id == event_id,
                Registration.team_id == team_id,
                Registration.status == "confirmed",
            )
        )
    ).scalars().all()
    assert len(member_seat) == 2, "both seats are confirmed by one team payment"


@pytest.mark.asyncio
async def test_team_event_can_be_registered_solo(client: AsyncClient, db_session):
    """A team event no longer requires a team before you can register (D3)."""
    email = "team.individual@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _fresh_event(
        db_session,
        uuid.UUID(edition_id),
        title="No Lone Seats",
        format="team",
        price_paise=0,
    )

    booked = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [str(event.id)]},
    )
    assert booked.status_code == 200, booked.text
    row = booked.json()["data"]["registrations"][0]
    assert row["eventId"] == str(event.id)
    assert row["teamId"] is None, "solo is the default, no Team row is created"

    event_id = event.id
    db_session.expire_all()
    seats = (
        await db_session.execute(
            select(Registration).where(
                Registration.event_id == event_id,
                Registration.status == "confirmed",
            )
        )
    ).scalars().all()
    assert len(seats) == 1 and seats[0].team_id is None

    # A solo seat is a complete registration: no team was needed and no
    # team row was created behind the attendee's back.
    teams = (
        await db_session.execute(select(Team).where(Team.event_id == event_id))
    ).scalars().all()
    assert teams == []


@pytest.mark.asyncio
async def test_leader_leaving_promotes_the_elder(client: AsyncClient, db_session):
    """The leader leaving must hand over, not tear the roster down (D6)."""
    leader_email = "team.disband.lead@test.local"
    member_email = "team.disband.member@test.local"
    await _login(client, leader_email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, leader_email)
    event = await _fresh_event(
        db_session,
        uuid.UUID(edition_id),
        title="Disband Me",
        format="team",
        price_paise=0,
    )
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Disband Five"},
    )
    assert created.status_code in (200, 201), created.text
    team_id = uuid.UUID(created.json()["data"]["id"])
    invite = created.json()["data"]["inviteCode"]

    await _login(client, member_email)
    await _paid_registration(client, edition_id, member_email)
    joined = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert joined.status_code == 200, joined.text
    member_seat = (
        await db_session.execute(
            select(Registration).where(
                Registration.team_id == team_id, Registration.kind == "team"
            )
        )
    ).scalars().all()
    assert member_seat

    await _login(client, leader_email)
    left = await client.delete(f"/api/v1/editions/{edition_id}/teams/{team_id}")
    assert left.status_code == 200, left.text

    db_session.expire_all()
    team = await db_session.get(Team, team_id)
    assert team is not None and team.status != "disbanded", "members remain, so the team stays"
    members = (
        await db_session.execute(select(TeamMember).where(TeamMember.team_id == team_id))
    ).scalars().all()
    assert len(members) == 1
    assert members[0].is_leader is True
    assert team.leader_id == members[0].user_id

    # The remaining member keeps their seat and ticket.
    remaining = (
        await db_session.execute(
            select(Registration).where(
                Registration.team_id == team_id,
                Registration.user_id == members[0].user_id,
            )
        )
    ).scalars().all()
    assert remaining and all(s.status == "confirmed" for s in remaining)
    ticket_statuses = (
        await db_session.execute(
            select(Ticket.status).where(Ticket.registration_id.in_([s.id for s in remaining]))
        )
    ).scalars().all()
    assert all(status == "active" for status in ticket_statuses)


@pytest.mark.asyncio
async def test_replaced_checkout_order_stops_being_payable(client: AsyncClient, db_session):
    """A fee change must expire the order it replaces (B1)."""
    email = "replaced.order@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    category = await _profile_ready(client, edition_id, email)
    first = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert first.status_code == 200, first.text
    first_order = uuid.UUID(first.json()["data"]["payment"]["orderId"])

    # An admin edits the fee of the selected category.
    from app.models.registration import RegistrationCategory

    stored = await db_session.get(RegistrationCategory, uuid.UUID(category["id"]))
    stored.fee_paise = int(stored.fee_paise) + 10000
    await db_session.commit()

    second = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert second.status_code == 200, second.text
    assert uuid.UUID(second.json()["data"]["payment"]["orderId"]) != first_order

    db_session.expire_all()
    old = await db_session.get(PaymentOrder, first_order)
    assert old.status == "expired", "the replaced order must not stay payable"
    await db_session.refresh(stored)
    stored.fee_paise = int(stored.fee_paise) - 10000
    await db_session.commit()


@pytest.mark.asyncio
async def test_stale_order_payment_is_refunded_not_dropped(client: AsyncClient, db_session):
    """Money captured on a stale order is parked for refund (B1)."""
    email = "stale.paid@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    category = await _profile_ready(client, edition_id, email)
    first = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert first.status_code == 200, first.text
    stale_id = uuid.UUID(first.json()["data"]["payment"]["orderId"])

    from app.models.registration import RegistrationCategory

    stored = await db_session.get(RegistrationCategory, uuid.UUID(category["id"]))
    original_fee = int(stored.fee_paise)
    stored.fee_paise = original_fee + 10000
    await db_session.commit()
    second = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert second.status_code == 200, second.text

    # The attendee pays the order they still had open (the stale one).
    from app.services import payments as payment_service

    db_session.expire_all()
    stale = await db_session.get(PaymentOrder, stale_id)
    await payment_service.mark_order_paid(db_session, stale, transaction_id="pay_stale_1")
    await db_session.commit()

    db_session.expire_all()
    row = (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == email)
        )
    ).scalars().first()
    assert row.payment_status != "paid", "a stale capture must not pay the registration"
    refunds = (
        await db_session.execute(select(Refund).where(Refund.order_id == stale_id))
    ).scalars().all()
    assert refunds and refunds[0].status == "pending"

    stored = await db_session.get(RegistrationCategory, uuid.UUID(category["id"]))
    stored.fee_paise = original_fee
    await db_session.commit()


@pytest.mark.asyncio
async def test_full_refund_covers_the_upgrade_delta(client: AsyncClient, db_session):
    """Refunding base + upgrade money must end the pass, not leave it alive (B2)."""
    from app.services import college_registrations as cr_service

    email = "delta.refund@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    paid_registration = await _paid_registration(client, edition_id, email)
    row = await db_session.get(
        CollegeRegistration, uuid.UUID(paid_registration["id"])
    )
    assert row is not None
    base_order = await db_session.get(PaymentOrder, row.order_id)
    assert base_order is not None
    delta_order = PaymentOrder(
        edition_id=row.edition_id,
        user_id=row.user_id,
        purpose="college_registration_delta",
        amount_paise=25000,
        status="paid",
        linked_record_id=row.id,
        paid_at=datetime.now(UTC),
    )
    db_session.add(delta_order)
    row.additional_paid_paise = 25000
    await db_session.commit()
    await db_session.refresh(delta_order)

    refunded = await cr_service.initiate_refund(
        db_session,
        None,
        row,
        None,
        None,
        amount_paise=int(base_order.amount_paise) + 25000,
        note="Full refund including the upgrade",
    )
    await db_session.commit()
    assert refunded is not None

    # Both slices settle, exactly as the gateway webhooks report them.
    refunds = (
        await db_session.execute(
            select(Refund).where(
                Refund.order_id.in_([base_order.id, delta_order.id]),
                Refund.amount_paise > 0,
            )
        )
    ).scalars().all()
    for refund in refunds:
        refund.status = "processing"
        refund.gateway_refund_id = f"rfnd_{refund.id.hex[:10]}"
    await db_session.commit()
    for refund in refunds:
        await cr_service.sync_gateway_refund(db_session, refund.gateway_refund_id)
    await db_session.commit()
    # A duplicated delivery must not settle (or notify) twice.
    await cr_service.sync_gateway_refund(db_session, refunds[0].gateway_refund_id)
    await db_session.commit()
    row_id = row.id
    db_session.expire_all()
    stored = await db_session.get(CollegeRegistration, row_id)
    assert stored.payment_status == "refunded"
    assert stored.refund_status == "completed"
    live_pass = (
        await db_session.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == stored.user_id,
                ConventionPass.edition_id == stored.edition_id,
                ConventionPass.status == "active",
            )
        )
    ).scalars().first()
    assert live_pass is None, "a fully refunded registration must not keep a live pass"


@pytest.mark.asyncio
async def test_completed_refund_without_a_refund_is_refused(client: AsyncClient, db_session):
    """"Mark completed" must not start a gateway refund (B10)."""
    from app.services import college_registrations as cr_service

    email = "completed.guard@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    row = (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == email)
        )
    ).scalars().first()
    assert row is not None
    from app.core.errors import Conflict

    with pytest.raises(Conflict):
        await cr_service.refund_action(
            db_session,
            None,
            row,
            None,
            None,
            action="completed",
            amount_paise=None,
            note=None,
            gateway_refund_id="manual_ref_2",
        )


@pytest.mark.asyncio
async def test_dashboard_reports_capacity_per_unit(client: AsyncClient, db_session):
    """The dashboard must not add people and teams into one number (B11)."""
    await _login(client, "owner@parallax.local", role="admin")
    edition = await _edition(client)
    resp = await client.get(f"/api/v1/editions/{edition['id']}/admin/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "capacityByUnit" in data
    assert "seatsTakenByUnit" in data
    assert isinstance(data["capacityByUnit"], dict)


@pytest.mark.asyncio
async def test_included_seat_covers_a_per_team_entry(client: AsyncClient, db_session):
    """A pass-covered team entry is ₹0: team membership is not a price (D9)."""
    email = "team.included.lead@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _priced_team_event(
        db_session, uuid.UUID(edition_id), price_paise=60000, basis="per_team"
    )
    # A pass-covered seat on that event, as the included-selection flow would
    # have written it (the API refuses team events now, so the state is seeded
    # directly to exercise the waiver rule).
    from app.models.commerce import Registration as RegRow

    row = (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == email)
        )
    ).scalars().first()
    assert row is not None
    db_session.add(
        RegRow(
            edition_id=uuid.UUID(edition_id),
            user_id=row.user_id,
            event_id=event.id,
            kind="included",
            fee_paise=0,
            status="confirmed",
            registration_number=f"INC-{uuid.uuid4().hex[:8].upper()}",
        )
    )
    await db_session.commit()

    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Per Team Included"},
    )
    assert created.status_code in (200, 201), created.text
    payment = _payment_of(created.json()["data"])
    assert payment is None, "a pass-covered team entry must not ask for money"
    lead_user_id = row.user_id
    db_session.expire_all()
    team = (
        await db_session.execute(
            select(Team).where(Team.name == "Per Team Included")
        )
    ).scalars().first()
    assert team is not None and team.order_id is None
    seat = (
        await db_session.execute(
            select(Registration).where(
                Registration.team_id == team.id, Registration.user_id == lead_user_id
            )
        )
    ).scalars().first()
    assert seat is not None and seat.kind == "included" and seat.fee_paise == 0


@pytest.mark.asyncio
async def test_pass_level_scan_is_deduped(client: AsyncClient, db_session):
    """A second pass scan on the same day must say "duplicate", not admit twice (B8)."""
    from app.models.commerce import AttendanceRecord

    email = "scan.dedupe@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)

    row = (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == email)
        )
    ).scalars().first()
    assert row is not None
    from app.services.tickets import ticket_token_for

    ticket = (
        await db_session.execute(
            select(Ticket).where(
                Ticket.pass_id.in_(
                    select(ConventionPass.id).where(
                        ConventionPass.user_id == row.user_id,
                        ConventionPass.edition_id == row.edition_id,
                    )
                )
            )
        )
    ).scalars().first()
    assert ticket is not None
    token = ticket_token_for(ticket.id)

    await _login(client, "owner@parallax.local", role="admin")
    first = await client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin", json={"token": token}
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin", json={"token": token}
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["result"] == "duplicate"

    count = (
        await db_session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.user_id == row.user_id,
                AttendanceRecord.event_id.is_(None),
            )
        )
    ).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_blocked_rider_is_not_confirmed_on_a_team_payment(client: AsyncClient, db_session):
    """A suspended rider must not be admitted by someone else's payment (AUDIT07 F1)."""
    email = "team.blocked.lead@test.local"
    await _login(client, email)
    edition = await _edition(client)
    edition_id = edition["id"]
    await _paid_registration(client, edition_id, email)
    event = await _priced_team_event(
        db_session, uuid.UUID(edition_id), price_paise=40000, basis="per_team"
    )
    # This case is about a rider on somebody else's payment, so the entry must
    # actually be payable (not covered by the leader's pass allowance).
    event.included_eligible = False
    await db_session.commit()
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": str(event.id), "name": "Gated Roster"},
    )
    assert created.status_code in (200, 201), created.text
    payment = _payment_of(created.json()["data"])
    assert payment is not None

    # The leader pays first: only a paid team admits members at all.
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    invite = (
        await db_session.execute(
            select(Team.invite_code).where(
                Team.id == uuid.UUID(created.json()["data"]["id"])
            )
        )
    ).scalar_one()

    rider_email = "team.blocked.rider@test.local"
    await _login(client, rider_email)
    await _paid_registration(client, edition_id, rider_email)
    joined = await client.post(
        f"/api/v1/editions/{edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert joined.status_code == 200, joined.text

    lead_row = (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == email)
        )
    ).scalars().first()
    rider_row = (
        await db_session.execute(
            select(CollegeRegistration).where(CollegeRegistration.email == rider_email)
        )
    ).scalars().first()
    assert lead_row is not None and rider_row is not None

    lead_seat = (
        await db_session.execute(
            select(Registration).where(
                Registration.user_id == lead_row.user_id,
                Registration.event_id == event.id,
            )
        )
    ).scalars().first()
    assert lead_seat is not None
    order = (
        await db_session.execute(
            select(PaymentOrder).where(PaymentOrder.edition_id == uuid.UUID(edition_id))
            .where(PaymentOrder.purpose == "registration")
            .where(PaymentOrder.status == "paid")
        )
    ).scalars().first()
    assert order is not None

    # Suspending the rider must remove only that rider's seat and ticket.
    rider_pass = (
        await db_session.execute(
            select(ConventionPass).where(ConventionPass.user_id == rider_row.user_id)
        )
    ).scalars().first()
    assert rider_pass is not None
    rider_pass.status = "suspended"
    await db_session.commit()

    from app.services.passes import release_event_entitlements

    await release_event_entitlements(
        db_session,
        user_id=rider_row.user_id,
        edition_id=uuid.UUID(edition_id),
        reason="Suspended rider",
        try_gateway=False,
    )
    await db_session.commit()

    lead_seat_id, rider_seat_id = lead_seat.id, (
        await db_session.execute(
            select(Registration.id).where(
                Registration.user_id == rider_row.user_id,
                Registration.event_id == event.id,
            )
        )
    ).scalars().first()
    rows = (
        await db_session.execute(
            select(Registration.id, Registration.user_id, Registration.status).where(
                Registration.event_id == event.id,
                Registration.id.in_([lead_seat_id, rider_seat_id]),
            )
        )
    ).all()
    statuses = {row.id: row.status for row in rows}
    assert statuses[lead_seat_id] == "confirmed"
    assert statuses[rider_seat_id] == "cancelled"
    # The leader's own team payment survives the rider's removal.
    refreshed = await db_session.get(PaymentOrder, order.id)
    assert refreshed.status == "paid"
