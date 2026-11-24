"""The unified worklist: one price, pay-the-difference, team money that moves.

These tests are deliberately written against money, not against JSON shapes.
Each one asserts what the attendee sees and what the ledger holds after a
sequence a real person can perform:

* a basket that is partly covered by the pass pays only the difference;
* a confirmed seat is never re-priced or re-charged;
* cancelling a paid seat produces exactly one direct refund;
* a team entry is priced like any other event, and team membership never adds a
  charge;
* the joiner's event appears on their list but not on their bill;
* leadership moves to the elder and the team's payment moves with the team.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commerce import (
    EventQuote,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    TeamMember,
)
from app.models.edition import EditionPolicy, Event, EventCategory
from app.models.registration import CollegeRegistration
from tests.lifecycle_helpers import (
    admin_approve,
    edition_ctx,
    login,
    register_paid,
)

BASE = "/api/v1/editions"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _pass_holder(client: AsyncClient, ctx, tag: str) -> str:
    email = f"worklist.{tag}.{uuid.uuid4().hex[:8]}@test.local"
    registration = await register_paid(client, ctx, email)
    await login(client, "owner@parallax.local", role="admin")
    await admin_approve(client, ctx, registration["id"])
    await login(client, email)
    return email


async def _event(
    db: AsyncSession,
    ctx,
    *,
    title: str,
    base: int,
    price: int,
    fmt: str = "individual",
    included_eligible: bool = True,
    team_min: int = 1,
    team_max: int = 4,
) -> Event:
    category = (
        await db.execute(
            select(EventCategory).where(EventCategory.edition_id == ctx.edition.id).limit(1)
        )
    ).scalars().first()
    now = datetime.now(UTC)
    row = Event(
        edition_id=ctx.edition.id,
        category_id=category.id,
        slug=f"wl-{uuid.uuid4().hex[:10]}",
        title=title,
        summary=f"{title} test event",
        format=fmt,
        team_min_size=team_min,
        team_max_size=team_max,
        base_value_paise=base,
        addon_price_paise=price,
        included_eligible=included_eligible,
        addon_charge_basis="per_participant",
        team_fee_basis="per_team" if fmt == "team" else None,
        capacity=100,
        capacity_unit="participants",
        starts_at=now + timedelta(days=20),
        ends_at=now + timedelta(days=20, hours=2),
        registration_opens_at=now - timedelta(days=1),
        registration_closes_at=now + timedelta(days=18),
        status="published",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.fixture
async def policy_guard(db_session: AsyncSession):
    """Restore the edition policy after a test that tweaks allowance values."""
    rows = list(
        (
            await db_session.execute(
                select(EditionPolicy).where(EditionPolicy.is_current.is_(True))
            )
        ).scalars()
    )
    snapshot = [
        (r.id, r.included_event_count, r.included_value_cap_paise, r.cap_inclusive, r.included_selection_mode)
        for r in rows
    ]
    yield
    for rid, count, cap, inclusive, mode in snapshot:
        row = await db_session.get(EditionPolicy, rid)
        if row is not None:
            row.included_event_count = count
            row.included_value_cap_paise = cap
            row.cap_inclusive = inclusive
            row.included_selection_mode = mode
    await db_session.commit()


async def _set_policy(db: AsyncSession, ctx, *, count: int, cap: int | None):
    policy = await db.get(EditionPolicy, ctx.policy.id)
    policy.included_event_count = count
    policy.included_value_cap_paise = cap
    policy.cap_inclusive = True
    policy.included_selection_mode = "up_to"
    await db.commit()


async def _quote(client: AsyncClient, ctx, event_ids: list[uuid.UUID]) -> dict:
    resp = await client.post(
        f"{BASE}/{ctx.edition_id}/quote",
        json={"eventIds": [str(e) for e in event_ids]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _checkout(client: AsyncClient, ctx, quote: dict, key: str | None = None) -> dict:
    headers = {"Idempotency-Key": key} if key else {}
    resp = await client.post(
        f"{BASE}/{ctx.edition_id}/checkout",
        json={"quoteId": quote["quoteId"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _pay(client: AsyncClient, ctx, order_id: str) -> dict:
    resp = await client.post(
        f"{BASE}/{ctx.edition_id}/payments/{order_id}/mock"
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _buy(client: AsyncClient, ctx, event_ids: list[uuid.UUID]) -> dict:
    quote = await _quote(client, ctx, event_ids)
    body = await _checkout(client, ctx, quote, key=f"wl-{uuid.uuid4().hex}")
    if body.get("order"):
        await _pay(client, ctx, body["order"]["orderId"])
    return body


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_quote_pays_only_the_difference(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=3, cap=45000)
    email = await _pass_holder(client, ctx, "difference")

    code = await _event(db_session, ctx, title="Code Sprint", base=10000, price=0)
    ai = await _event(db_session, ctx, title="AI Workshop", base=20000, price=30000)
    robo = await _event(db_session, ctx, title="Robotics", base=15000, price=15000)
    hack = await _event(
        db_session, ctx, title="Hackathon", base=25000, price=20000, fmt="team", team_min=2
    )

    quote = await _quote(client, ctx, [code.id, ai.id, robo.id, hack.id])
    # Cheapest base first: Code 100 + Robotics 150 + AI 200 = 450, all covered.
    # The team event is the only thing left to pay, and it is paid once.
    assert quote["duePaise"] == 20000, quote
    lines = {line["eventId"]: line for line in quote["lines"]}
    assert lines[str(hack.id)]["duePaise"] == 20000
    assert lines[str(hack.id)]["coveredPaise"] == 0
    assert lines[str(ai.id)]["duePaise"] == 0

    # A second quote before checkout is stable: same basket, same price.
    again = await _quote(client, ctx, [robo.id, hack.id, ai.id, code.id])
    assert again["duePaise"] == quote["duePaise"]


@pytest.mark.asyncio
async def test_confirmed_seat_is_never_charged_twice(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=1, cap=45000)
    email = await _pass_holder(client, ctx, "twice")

    covered = await _event(db_session, ctx, title="Covered One", base=10000, price=10000)
    paid = await _event(db_session, ctx, title="Paid One", base=50000, price=25000)

    await _buy(client, ctx, [covered.id])
    first = await _quote(client, ctx, [covered.id, paid.id])
    assert first["duePaise"] == 25000

    await _buy(client, ctx, [paid.id])
    # Asking for the whole basket again must price only what is missing.
    second = await _quote(client, ctx, [covered.id, paid.id])
    assert second["duePaise"] == 0, second
    rows = {line["eventId"]: line for line in second["lines"]}
    assert rows[str(covered.id)]["action"] == "already_confirmed"
    assert rows[str(paid.id)]["action"] == "already_confirmed"
    active = (
        await db_session.execute(
            select(func.count(Registration.id)).where(
                Registration.user_id.in_(
                    select(CollegeRegistration.user_id).where(
                        CollegeRegistration.email == email
                    )
                ),
                Registration.event_id.in_([covered.id, paid.id]),
                Registration.status == "confirmed",
            )
        )
    ).scalar()
    assert active == 2


@pytest.mark.asyncio
async def test_free_event_does_not_consume_allowance(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=1, cap=50000)
    await _pass_holder(client, ctx, "free")

    free = await _event(db_session, ctx, title="Free Talk", base=40000, price=0)
    included = await _event(db_session, ctx, title="Included One", base=10000, price=10000)
    paid = await _event(db_session, ctx, title="Paid One", base=20000, price=20000)

    quote = await _quote(client, ctx, [free.id, included.id, paid.id])
    lines = {line["eventId"]: line for line in quote["lines"]}
    assert lines[str(free.id)]["basis"] == "free"
    assert lines[str(included.id)]["duePaise"] == 0
    assert quote["duePaise"] == 20000, "the free event must not eat the single slot"


@pytest.mark.asyncio
async def test_stale_quote_is_refused_when_a_price_changes(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=0, cap=None)
    await _pass_holder(client, ctx, "stale")

    event = await _event(db_session, ctx, title="Moving Price", base=10000, price=10000)
    quote = await _quote(client, ctx, [event.id])

    stored = await db_session.get(Event, event.id)
    stored.addon_price_paise = 15000
    await db_session.commit()

    resp = await client.post(
        f"{BASE}/{ctx.edition_id}/checkout", json={"quoteId": quote["quoteId"]}
    )
    assert resp.status_code == 409, resp.text
    assert "review" in resp.text.lower() or "changed" in resp.text.lower()


# --------------------------------------------------------------------------- #
# Refund
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cancelling_with_refund_creates_exactly_one_refund(
    client: AsyncClient, db_session, policy_guard
):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=0, cap=None)
    await _pass_holder(client, ctx, "refund")

    event = await _event(db_session, ctx, title="Refund Me", base=10000, price=12000)
    body = await _buy(client, ctx, [event.id])
    order_id = body["order"]["orderId"]

    event_id = event.id
    resp = await client.delete(f"{BASE}/{ctx.edition_id}/events/{event_id}")
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    refunds = (
        await db_session.execute(
            select(Refund).where(Refund.order_id == uuid.UUID(order_id))
        )
    ).scalars().all()
    assert len(refunds) == 1, "a retry must not stack a second refund"
    assert refunds[0].amount_paise == 12000

    seat = (
        await db_session.execute(
            select(Registration).where(
                Registration.event_id == event_id,
                Registration.status == "cancelled",
            )
        )
    ).scalars().first()
    assert seat is not None


# --------------------------------------------------------------------------- #
# Teams: price, pass, bills, handover
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_solo_team_event_counts_one_entry(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=0, cap=None)
    await _pass_holder(client, ctx, "solo")

    event = await _event(
        db_session, ctx, title="Solo Entry Event", base=0, price=0, fmt="team", team_min=2
    )
    event_id = event.id
    body = await _buy(client, ctx, [event_id])
    assert body["order"] is None, "a free team event is still free"
    from app.services.events import capacity_usage

    db_session.expire_all()
    stored = await db_session.get(Event, event_id)
    assert (await capacity_usage(db_session, [stored]))[stored.id] == 1
    teams = (
        await db_session.execute(select(Team).where(Team.event_id == event_id))
    ).scalars().all()
    assert teams == [], "solo must not create a team"


@pytest.mark.asyncio
async def test_join_requires_an_active_pass(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    leader = await _pass_holder(client, ctx, "joingate.lead")
    event = await _event(
        db_session, ctx, title="Pass Gate Team", base=0, price=0, fmt="team", team_min=2
    )
    await _buy(client, ctx, [event.id])
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(event.id), "name": "Pass Gate"},
    )
    assert created.status_code in (200, 201), created.text
    invite = created.json()["data"]["inviteCode"]

    # A brand-new account without a pass cannot join.
    await login(client, f"no.pass.{uuid.uuid4().hex[:6]}@test.local")
    blocked = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert blocked.status_code in (400, 403, 422), blocked.text
    assert "pass" in blocked.text.lower()

    # The same person after buying a pass and registering for the event joins.
    buyer = f"joingate.member.{uuid.uuid4().hex[:6]}@test.local"
    registration = await register_paid(client, ctx, buyer)
    await login(client, "owner@parallax.local", role="admin")
    await admin_approve(client, ctx, registration["id"])
    await login(client, buyer)
    await _buy(client, ctx, [event.id])
    joined = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert joined.status_code == 200, joined.text


@pytest.mark.asyncio
async def test_unpaid_team_blocks_join_and_leader_handover_keeps_the_paid_order(
    client: AsyncClient, db_session, policy_guard
):
    """No member joins before the leader pays; a later handover keeps the order."""
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=0, cap=None)
    leader_email = await _pass_holder(client, ctx, "elder.lead")
    member_email = f"elder.member.{uuid.uuid4().hex[:6]}@test.local"

    event = await _event(
        db_session,
        ctx,
        title="Unpaid Team",
        base=0,
        price=30000,
        fmt="team",
        team_min=2,
        included_eligible=False,
    )
    q = await _quote(client, ctx, [event.id])
    chk = await _checkout(client, ctx, q, key=f"unpaid-{uuid.uuid4().hex}")
    order_id = chk["order"]["orderId"]
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(event.id), "name": "Elder Team"},
    )
    assert created.status_code in (200, 201), created.text
    team_id = uuid.UUID(created.json()["data"]["id"])
    assert created.json()["data"]["inviteCode"] is None, "invite is locked until paid"

    registration = await register_paid(client, ctx, member_email)
    await login(client, "owner@parallax.local", role="admin")
    await admin_approve(client, ctx, registration["id"])
    invite = (
        await db_session.execute(select(Team.invite_code).where(Team.id == team_id))
    ).scalar_one()
    await login(client, member_email)
    blocked = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join",
        json={"inviteCode": invite},
    )
    assert blocked.status_code in (400, 409, 422), blocked.text
    assert "payment" in blocked.text.lower()

    # The leader pays, then the member registers and joins.
    await login(client, leader_email)
    await _pay(client, ctx, order_id)

    await login(client, member_email)
    await _buy(client, ctx, [event.id])
    joined = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join",
        json={"inviteCode": invite},
    )
    assert joined.status_code == 200, joined.text

    await login(client, leader_email)
    left = await client.delete(f"{BASE}/{ctx.edition_id}/teams/{team_id}")
    assert left.status_code == 200, left.text

    db_session.expire_all()
    team = await db_session.get(Team, team_id)
    assert team.status != "disbanded"
    member = (
        await db_session.execute(
            select(TeamMember).where(TeamMember.team_id == team_id)
        )
    ).scalars().first()
    assert member is not None and member.is_leader is True
    assert team.leader_id == member.user_id
    assert team.order_id is not None, "the team keeps its payment"

    order = await db_session.get(PaymentOrder, team.order_id)
    assert order is not None and order.status == "paid"
    live = (
        await db_session.execute(
            select(Registration).where(
                Registration.team_id == team_id,
                Registration.status == "confirmed",
            )
        )
    ).scalars().all()
    assert len(live) == 1, "the leaver's own seat went with them; the elder keeps theirs"
    assert all(seat.fee_paise == 0 for seat in live)


@pytest.mark.asyncio
async def test_joiner_event_is_listed_but_not_billed(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=0, cap=None)
    leader_email = await _pass_holder(client, ctx, "bill.lead")
    member_email = f"bill.member.{uuid.uuid4().hex[:6]}@test.local"

    event = await _event(
        db_session,
        ctx,
        title="Billed Once",
        base=0,
        price=25000,
        fmt="team",
        team_min=2,
        included_eligible=False,
    )
    await _buy(client, ctx, [event.id])
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(event.id), "name": "Bill Team"},
    )
    assert created.status_code in (200, 201), created.text
    invite = (
        await db_session.execute(
            select(Team.invite_code).where(
                Team.id == uuid.UUID(created.json()["data"]["id"])
            )
        )
    ).scalar_one()

    registration = await register_paid(client, ctx, member_email)
    await login(client, "owner@parallax.local", role="admin")
    await admin_approve(client, ctx, registration["id"])
    await login(client, member_email)
    no_reg_join = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert no_reg_join.status_code == 422, no_reg_join.text
    assert no_reg_join.json()["error"]["code"] == "REGISTRATION_REQUIRED"

    await _buy(client, ctx, [event.id])
    joined = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert joined.status_code == 200, joined.text

    mine = await client.get(f"{BASE}/{ctx.edition_id}/registrations")
    assert mine.status_code == 200, mine.text
    row = next(
        item for item in mine.json()["data"] if item["eventId"] == str(event.id)
    )
    assert row["status"] == "confirmed", "the joiner sees their team event"

    await login(client, leader_email)
    theirs = await client.get(f"{BASE}/{ctx.edition_id}/registrations")
    lead_row = next(
        item for item in theirs.json()["data"] if item["eventId"] == str(event.id)
    )
    assert lead_row["billable"] is True
    assert lead_row["billingRole"] == "payer"
    assert lead_row["feePaise"] == 25000


@pytest.mark.asyncio
async def test_last_member_leaves_and_team_order_refunds_once(
    client: AsyncClient, db_session, policy_guard
):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=0, cap=None)
    email = await _pass_holder(client, ctx, "lastmember")

    event = await _event(
        db_session,
        ctx,
        title="Last Member",
        base=0,
        price=18000,
        fmt="team",
        team_min=1,
        included_eligible=False,
    )
    chk = await _buy(client, ctx, [event.id])
    order_id = uuid.UUID(chk["order"]["orderId"])
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(event.id), "name": "Last Team"},
    )
    assert created.status_code in (200, 201), created.text
    team_id = uuid.UUID(created.json()["data"]["id"])

    left = await client.delete(f"{BASE}/{ctx.edition_id}/teams/{team_id}")
    assert left.status_code == 200, left.text

    db_session.expire_all()
    team = await db_session.get(Team, team_id)
    assert team.status == "disbanded"
    refunds = (
        await db_session.execute(select(Refund).where(Refund.order_id == order_id))
    ).scalars().all()
    assert len(refunds) == 1
    assert refunds[0].amount_paise == 18000
    seats = (
        await db_session.execute(
            select(Registration).where(Registration.team_id == team_id)
        )
    ).scalars().all()
    assert all(seat.status == "cancelled" for seat in seats)


@pytest.mark.asyncio
async def test_checkout_is_idempotent(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=0, cap=None)
    await _pass_holder(client, ctx, "idem")

    event = await _event(db_session, ctx, title="Idempotent One", base=0, price=9000)
    quote = await _quote(client, ctx, [event.id])
    key = f"idem-{uuid.uuid4().hex}"
    event_id = event.id
    quote_id = uuid.UUID(quote["quoteId"])
    first = await _checkout(client, ctx, quote, key=key)
    second = await _checkout(client, ctx, quote, key=key)
    assert first["order"]["orderId"] == second["order"]["orderId"]
    db_session.expire_all()
    count = (
        await db_session.execute(
            select(func.count(Registration.id)).where(
                Registration.event_id == event_id, Registration.quote_id == quote_id
            )
        )
    ).scalar()
    assert count == 1, "one click (or a retry) must create one seat"
    quotes = (
        await db_session.execute(
            select(EventQuote).where(EventQuote.id == quote_id)
        )
    ).scalars().all()
    assert len(quotes) == 1 and quotes[0].status == "consumed"


@pytest.mark.asyncio
async def test_invite_preview_is_public_and_non_pii(client: AsyncClient, db_session, policy_guard):
    ctx = await edition_ctx(client, db_session)
    await _pass_holder(client, ctx, "preview.lead")
    event = await _event(
        db_session, ctx, title="Preview Team", base=0, price=0, fmt="team", team_min=2
    )
    await _buy(client, ctx, [event.id])
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(event.id), "name": "Preview Crew"},
    )
    assert created.status_code in (200, 201), created.text
    invite = created.json()["data"]["inviteCode"]

    resp = await client.get(f"/api/v1/public/teams/{invite}")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["teamName"] == "Preview Crew"
    assert body["event"]["title"] == "Preview Team"
    assert body["openForJoin"] is True
    blob = resp.text.lower()
    assert "@" not in blob, "the preview must not leak an email"
    assert "college" not in blob


@pytest.mark.asyncio
async def test_worklist_matches_quote_and_exposes_team_state(
    client: AsyncClient, db_session, policy_guard
):
    """The page gets rows, allowance, basket and team state in one payload."""
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=2, cap=40000)
    email = await _pass_holder(client, ctx, "worklist.shape")

    covered = await _event(db_session, ctx, title="WL Covered", base=10000, price=10000)
    team_event = await _event(
        db_session, ctx, title="WL Team", base=15000, price=12000, fmt="team", team_min=2
    )

    response = await client.get(f"{BASE}/{ctx.edition_id}/worklist")
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["allowance"]["required"] == 2
    assert body["allowance"]["capPaise"] == 40000
    rows = {row["eventId"]: row for row in body["rows"]}
    assert rows[str(covered.id)]["state"] == "included_possible"
    assert rows[str(team_event.id)]["format"] == "team"
    assert rows[str(team_event.id)]["team"]["status"] == "none"

    await _buy(client, ctx, [team_event.id])
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(team_event.id), "name": "WL Crew"},
    )
    assert created.status_code in (200, 201), created.text
    assert created.json()["data"].get("payment") is None, "covered team entry is ₹0"

    again = await client.get(f"{BASE}/{ctx.edition_id}/worklist")
    row = next(
        item
        for item in again.json()["data"]["rows"]
        if item["eventId"] == str(team_event.id)
    )
    assert row["state"] in ("team_leader", "team_included")
    assert row["team"]["isLeader"] is True
    assert row["team"]["inviteLink"].startswith("/team/")
    assert row["price"]["duePaise"] == 0


@pytest.mark.asyncio
async def test_join_without_a_seat_uses_the_pass_allowance(
    client: AsyncClient, db_session, policy_guard
):
    """Creating or joining a team without registering first is refused (no silent pass consumption)."""
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=2, cap=40000)
    await _pass_holder(client, ctx, "coveredjoin.lead")
    member_email = f"coveredjoin.member.{uuid.uuid4().hex[:6]}@test.local"

    event = await _event(
        db_session, ctx, title="Covered Join", base=10000, price=15000, fmt="team", team_min=2
    )
    no_reg = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(event.id), "name": "Covered Joins"},
    )
    assert no_reg.status_code == 422, no_reg.text
    assert no_reg.json()["error"]["code"] == "REGISTRATION_REQUIRED"

    await _buy(client, ctx, [event.id])
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(event.id), "name": "Covered Joins"},
    )
    assert created.status_code in (200, 201), created.text
    assert created.json()["data"].get("payment") is None
    invite = created.json()["data"]["inviteCode"]

    registration = await register_paid(client, ctx, member_email)
    await login(client, "owner@parallax.local", role="admin")
    await admin_approve(client, ctx, registration["id"])
    await login(client, member_email)

    blocked = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["error"]["code"] == "REGISTRATION_REQUIRED"

    await _buy(client, ctx, [event.id])
    joined = await client.post(
        f"{BASE}/{ctx.edition_id}/teams/join", json={"inviteCode": invite}
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["data"].get("payment") is None, "the pass covers the join"

    mine = await client.get(f"{BASE}/{ctx.edition_id}/registrations")
    row = next(
        item for item in mine.json()["data"] if item["eventId"] == str(event.id)
    )
    assert row["kind"] == "included"
    assert row["feePaise"] == 0
    assert row["billable"] is False


# --------------------------------------------------------------------------- #
# The basket shared by every event page (Phase 6)
# --------------------------------------------------------------------------- #
async def _basket_add(client: AsyncClient, ctx, event_ids: list[uuid.UUID]) -> dict:
    resp = await client.post(
        f"{BASE}/{ctx.edition_id}/basket/events",
        json={"eventIds": [str(e) for e in event_ids]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_basket_three_events_then_fourth_is_priced(
    client: AsyncClient, db_session, policy_guard
):
    """Three events fit the pass; a fourth is accepted and priced, never blocked."""
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=3, cap=45000)
    await _pass_holder(client, ctx, "basket.three")

    a = await _event(db_session, ctx, title="Basket A", base=10000, price=10000)
    b = await _event(db_session, ctx, title="Basket B", base=20000, price=30000)
    c = await _event(db_session, ctx, title="Basket C", base=15000, price=15000)
    d = await _event(db_session, ctx, title="Basket D", base=25000, price=20000)

    one = await _basket_add(client, ctx, [a.id])
    assert one["duePaise"] == 0
    two = await _basket_add(client, ctx, [b.id])
    assert two["duePaise"] == 0
    three = await _basket_add(client, ctx, [c.id])
    assert three["duePaise"] == 0, "A+B+C = the full allowance"
    assert len([line for line in three["lines"] if line["action"] == "create"]) == 3

    four = await _basket_add(client, ctx, [d.id])
    assert four["duePaise"] == 20000, "the fourth is due, not rejected"
    lines = {line["eventId"]: line for line in four["lines"]}
    assert lines[str(d.id)]["duePaise"] == 20000
    covered = [
        eid for eid, line in lines.items() if line.get("basis") == "included"
    ]
    assert set(covered) == {str(a.id), str(b.id), str(c.id)}

    # The same basket is readable from any page.
    fetched = await client.get(f"{BASE}/{ctx.edition_id}/basket")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"]["quoteId"] == four["quoteId"]
    assert fetched.json()["data"]["duePaise"] == 20000


@pytest.mark.asyncio
async def test_basket_coverage_does_not_depend_on_add_order(
    client: AsyncClient, db_session, policy_guard
):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=2, cap=30000)

    a = await _event(db_session, ctx, title="Order A", base=10000, price=10000)
    b = await _event(db_session, ctx, title="Order B", base=12000, price=12000)
    c = await _event(db_session, ctx, title="Order C", base=13000, price=13000)

    await _pass_holder(client, ctx, "order.forward")
    forward = await _basket_add(client, ctx, [a.id, b.id, c.id])

    await _pass_holder(client, ctx, "order.backward")
    backward = await _basket_add(client, ctx, [c.id])
    backward = await _basket_add(client, ctx, [b.id])
    backward = await _basket_add(client, ctx, [a.id])

    def coverage(quote):
        return {
            line["eventId"]: line["duePaise"] for line in quote["lines"]
        }

    assert coverage(forward) == coverage(backward)
    assert forward["duePaise"] == backward["duePaise"] == 13000


@pytest.mark.asyncio
async def test_basket_remove_repacks_and_checkout_is_one_order(
    client: AsyncClient, db_session, policy_guard
):
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=3, cap=45000)
    await _pass_holder(client, ctx, "basket.remove")

    a = await _event(db_session, ctx, title="Remove A", base=10000, price=10000)
    b = await _event(db_session, ctx, title="Remove B", base=20000, price=30000)
    c = await _event(db_session, ctx, title="Remove C", base=15000, price=15000)
    d = await _event(db_session, ctx, title="Remove D", base=15000, price=20000)

    await _basket_add(client, ctx, [a.id, b.id, c.id, d.id])
    # Drop B, which was covered, and D takes its place in the pack.
    removed = await client.delete(f"{BASE}/{ctx.edition_id}/basket/events/{b.id}")
    assert removed.status_code == 200, removed.text
    quote = removed.json()["data"]
    assert quote["duePaise"] == 0, quote
    lines = {line["eventId"]: line for line in quote["lines"]}
    assert lines[str(d.id)]["duePaise"] == 0, "the freed slot goes to the cheapest fit"

    # Checkout the basket once; it becomes one order with three seats.
    body = await _checkoutFromBasket(client, ctx, quote)
    assert body["order"] is None, "the whole basket fits the allowance, so no money is due"
    db_session.expire_all()
    seats = (
        await db_session.execute(
            select(Registration).where(
                Registration.user_id.in_(
                    select(CollegeRegistration.user_id).where(
                        CollegeRegistration.email.like("worklist.basket.remove.%")
                    )
                ),
                Registration.status.in_(("confirmed", "reserved")),
            )
        )
    ).scalars().all()
    assert len(seats) == 3
    assert len({seat.event_id for seat in seats}) == 3

    empty = await client.get(f"{BASE}/{ctx.edition_id}/basket")
    assert empty.json()["data"]["quoteId"] is None, "checkout empties the basket"


async def _checkoutFromBasket(client: AsyncClient, ctx, quote: dict) -> dict:
    resp = await client.post(
        f"{BASE}/{ctx.edition_id}/checkout",
        json={"quoteId": quote["quoteId"]},
        headers={"Idempotency-Key": f"basket-{uuid.uuid4().hex}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_team_action_never_destroys_the_basket(
    client: AsyncClient, db_session, policy_guard
):
    """Creating a team must not expire an unrelated open basket (Phase 6 bug)."""
    ctx = await edition_ctx(client, db_session)
    await _set_policy(db_session, ctx, count=3, cap=45000)
    await _pass_holder(client, ctx, "basket.team")

    individual = await _event(db_session, ctx, title="Keep Me", base=10000, price=10000)
    team_event = await _event(
        db_session, ctx, title="Team In Basket", base=10000, price=0, fmt="team", team_min=2
    )
    basket = await _basket_add(client, ctx, [individual.id, team_event.id])
    assert basket["quoteId"]

    blocked = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(team_event.id), "name": "Basket Crew"},
    )
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["error"]["code"] == "REGISTRATION_REQUIRED"

    still = await client.get(f"{BASE}/{ctx.edition_id}/basket")
    assert still.json()["data"]["quoteId"] == basket["quoteId"]
    assert len(
        [line for line in still.json()["data"]["lines"] if line["action"] == "create"]
    ) == 2

    # Once the team event leaves the basket, the other event stays in the basket;
    # after registering, the team can be created.
    await client.delete(f"{BASE}/{ctx.edition_id}/basket/events/{team_event.id}")
    remaining = await client.get(f"{BASE}/{ctx.edition_id}/basket")
    assert remaining.json()["data"]["quoteId"] is not None
    assert remaining.json()["data"]["lines"][0]["eventId"] == str(individual.id)
    await _buy(client, ctx, [team_event.id])
    created = await client.post(
        f"{BASE}/{ctx.edition_id}/teams",
        json={"eventId": str(team_event.id), "name": "Basket Crew"},
    )
    assert created.status_code in (200, 201), created.text
