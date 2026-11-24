"""Regression tests for the workflow guards that keep data consistent.

These run after the other suites, so the participant used here may already hold
a paid pass from the pass-flow test.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    PaymentTransaction,
    Registration,
    Ticket,
)
from app.models.edition import ConventionEdition, Event
from app.models.user import User
from app.services.editions import current_policy
from app.services.passes import activate_pass_for_registration
from app.services.tickets import ticket_token_for
from app.services.users import upsert_google_user


async def _current_edition(client: AsyncClient) -> dict:
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _ensure_active_pass(
    client: AsyncClient, db_session, edition_id: str
) -> dict:
    """Give the participant an active pass via the college-registration bridge."""
    current = (await client.get(f"/api/v1/editions/{edition_id}/pass")).json()["data"]
    if current and current["status"] == "active":
        return current
    user = (
        (
            await db_session.execute(
                select(User).where(
                    User.email_normalized == "participant@parallax.local"
                )
            )
        )
        .scalars()
        .first()
    )
    if user is None:
        # Admin-only test runs never log the participant in, so create them.
        user, _ = await upsert_google_user(
            db_session,
            claims={
                "sub": "dev-participant-participant@parallax.local",
                "email": "participant@parallax.local",
                "email_verified": True,
                "name": "Dev Participant",
                "picture": None,
            },
        )
    policy = await current_policy(db_session, uuid.UUID(edition_id))
    user_pass = await activate_pass_for_registration(
        db_session, user.id, uuid.UUID(edition_id), policy, 50000
    )
    await db_session.commit()
    assert user_pass.status == "active"
    # Verify in the DB (the caller may be an admin client, whose /pass view is
    # for their own user and would legitimately be empty).
    refreshed = (
        (
            await db_session.execute(
                select(ConventionPass).where(
                    ConventionPass.user_id == user.id,
                    ConventionPass.edition_id == uuid.UUID(edition_id),
                )
            )
        )
        .scalars()
        .first()
    )
    assert refreshed is not None and refreshed.status == "active"
    return {"id": str(refreshed.id), "status": refreshed.status}


@pytest.mark.asyncio
async def test_event_upsert_rejects_inconsistent_schedule(admin_client: AsyncClient):
    client = admin_client
    edition = await _current_edition(client)
    edition_id = edition["id"]
    categories = (
        await client.get(f"/api/v1/editions/{edition_id}/admin/categories")
    ).json()["data"]
    assert categories
    starts = datetime.now(UTC) + timedelta(days=3)
    ends = starts - timedelta(hours=2)

    base = {
        "categoryId": categories[0]["id"],
        "slug": "guard-test-event",
        "title": "Guard test event",
        "summary": "Checks the schedule guards.",
        "format": "individual",
        "startsAt": starts.isoformat(),
        "endsAt": ends.isoformat(),
        "status": "draft",
    }
    backwards = await client.post(
        f"/api/v1/editions/{edition_id}/admin/events", json=base
    )
    assert backwards.status_code == 422, backwards.text

    published = await client.post(
        f"/api/v1/editions/{edition_id}/admin/events",
        json={**base, "status": "published"},
    )
    assert published.status_code == 422, published.text

    window = await client.post(
        f"/api/v1/editions/{edition_id}/admin/events",
        json={
            **base,
            "slug": "guard-test-window",
            "endsAt": (starts + timedelta(hours=2)).isoformat(),
            "registrationOpensAt": (starts + timedelta(days=1)).isoformat(),
            "registrationClosesAt": starts.isoformat(),
        },
    )
    assert window.status_code == 422, window.text


@pytest.mark.asyncio
async def test_selections_issue_event_tickets_and_cancel_revokes(
    participant_client: AsyncClient, db_session
):
    client = participant_client
    edition = await _current_edition(client)
    edition_id = edition["id"]
    await _ensure_active_pass(client, db_session, edition_id)

    cap = (edition.get("policy") or {}).get("includedValueCapPaise") or 10**9
    event = (
        (
            await db_session.execute(
                select(Event)
                .where(
                    Event.edition_id == uuid.UUID(edition_id),
                    Event.status.in_(["published", "open"]),
                    Event.included_eligible.is_(True),
                    Event.format == "individual",
                    Event.base_value_paise <= cap,
                    Event.starts_at > datetime.now(UTC) + timedelta(hours=25),
                )
                .order_by(Event.sort_order)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    assert event is not None, "seed has no included-eligible event"

    saved = await client.put(
        f"/api/v1/editions/{edition_id}/pass/selections",
        json={"eventIds": [str(event.id)]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["valid"] is True

    tickets = (await client.get(f"/api/v1/editions/{edition_id}/tickets")).json()["data"]
    assert any(
        t["kind"] == "registration" and t["title"] == event.title for t in tickets
    ), "included event ticket was not issued"

    registrations = (
        await client.get(f"/api/v1/editions/{edition_id}/registrations")
    ).json()["data"]
    included = [
        r
        for r in registrations
        if r["kind"] == "included" and r["eventId"] == str(event.id)
    ]
    assert included, "included registration was not created"

    removed = await client.delete(
        f"/api/v1/editions/{edition_id}/registrations/{included[0]['id']}"
    )
    assert removed.status_code == 200, removed.text

    after = (await client.get(f"/api/v1/editions/{edition_id}/tickets")).json()["data"]
    assert not any(t["title"] == event.title for t in after)
    state = (await client.get(f"/api/v1/editions/{edition_id}/pass")).json()["data"]
    assert state["selection"]["count"] == 0


@pytest.mark.asyncio
async def test_checkin_rejects_pass_ticket_for_unregistered_event(
    admin_client: AsyncClient, db_session
):
    client = admin_client
    edition = await _current_edition(client)
    edition_id = uuid.UUID(edition["id"])

    user_pass = (
        (
            await db_session.execute(
                select(ConventionPass)
                .where(
                    ConventionPass.edition_id == edition_id,
                    ConventionPass.status == "active",
                )
                .order_by(ConventionPass.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert user_pass is not None

    ticket = (
        (
            await db_session.execute(
                select(Ticket).where(
                    Ticket.pass_id == user_pass.id,
                    Ticket.status.in_(["active", "valid"]),
                )
            )
        )
        .scalars()
        .first()
    )
    assert ticket is not None, "active pass has no ticket"

    registered_event_ids = set(
        (
            await db_session.execute(
                select(Registration.event_id).where(
                    Registration.user_id == user_pass.user_id,
                    Registration.edition_id == edition_id,
                    Registration.status.in_(["confirmed", "reserved"]),
                )
            )
        ).scalars()
    )
    events = (
        await client.get(f"/api/v1/editions/{edition['id']}/admin/events")
    ).json()["data"]
    candidate = next(
        (e for e in events if uuid.UUID(e["id"]) not in registered_event_ids), None
    )
    assert candidate is not None

    mismatch = await client.post(
        f"/api/v1/editions/{edition['id']}/admin/checkin",
        json={"token": ticket_token_for(ticket.id), "eventId": candidate["id"]},
    )
    assert mismatch.status_code == 409, mismatch.text


@pytest.mark.asyncio
async def test_refund_revokes_entitlement_and_validates_amount(
    admin_client: AsyncClient, db_session
):
    client = admin_client
    edition = await _current_edition(client)
    edition_id = uuid.UUID(edition["id"])

    user_pass = (
        (
            await db_session.execute(
                select(ConventionPass)
                .where(
                    ConventionPass.edition_id == edition_id,
                    ConventionPass.status == "active",
                )
                .order_by(ConventionPass.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert user_pass is not None

    # The college-registration flow no longer mints purpose="pass" orders; seed
    # the paid order (plus its captured transaction) the refund endpoint expects.
    order = PaymentOrder(
        edition_id=user_pass.edition_id,
        user_id=user_pass.user_id,
        purpose="pass",
        amount_paise=user_pass.price_paise,
        status="paid",
        linked_record_id=user_pass.id,
        paid_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        PaymentTransaction(
            order_id=order.id,
            gateway_payment_id=f"pay_test_{uuid.uuid4().hex[:12]}",
            amount_paise=order.amount_paise,
            status="captured",
        )
    )
    await db_session.commit()
    assert order is not None

    first = await client.post(
        f"/api/v1/editions/{edition['id']}/admin/refunds",
        json={
            "orderId": str(order.id),
            "amountPaise": order.amount_paise,
            "reasonCode": "test_refund",
        },
    )
    assert first.status_code == 200, first.text

    await db_session.commit()
    statuses = list(
        (
            await db_session.execute(
                select(Ticket.status).where(Ticket.pass_id == user_pass.id)
            )
        ).scalars()
    )
    assert statuses and all(status == "revoked" for status in statuses)

    second = await client.post(
        f"/api/v1/editions/{edition['id']}/admin/refunds",
        json={
            "orderId": str(order.id),
            "amountPaise": 1,
            "reasonCode": "test_refund",
        },
    )
    assert second.status_code == 422, second.text


@pytest.mark.asyncio
async def test_admin_registrations_report_total(admin_client: AsyncClient):
    client = admin_client
    edition = await _current_edition(client)
    body = (
        await client.get(
            f"/api/v1/editions/{edition['id']}/admin/registrations?page=1&page_size=1"
        )
    ).json()
    assert "total" in body
    assert len(body["data"]) <= 1
    assert body["total"] >= len(body["data"])


@pytest.mark.asyncio
async def test_suspended_pass_blocks_event_selection_and_addons(
    participant_client: AsyncClient, db_session
):
    client = participant_client
    edition = await _current_edition(client)
    await _ensure_active_pass(client, db_session, edition["id"])

    # Locate participant user and pass
    user = (
        (
            await db_session.execute(
                select(User).where(User.email_normalized == "participant@parallax.local")
            )
        )
        .scalars()
        .first()
    )
    assert user is not None
    pass_row = (
        (
            await db_session.execute(
                select(ConventionPass).where(
                    ConventionPass.user_id == user.id,
                    ConventionPass.edition_id == uuid.UUID(edition["id"]),
                ).order_by(ConventionPass.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert pass_row is not None

    # Suspend pass
    pass_row.status = "suspended"
    await db_session.commit()

    # 1. GET /pass must return "suspended" and must NOT resurrect into "active"
    pass_res = (await client.get(f"/api/v1/editions/{edition['id']}/pass")).json()
    assert pass_res["data"]["status"] == "suspended"

    # Get an event to test selection / addons
    events_res = (
        await client.get(f"/api/v1/public/editions/{edition['slug']}/events?pageSize=5")
    ).json()
    event_id = events_res["data"][0]["id"]

    # 2. PUT /pass/selections must be rejected with 409 Conflict
    sel_res = await client.put(
        f"/api/v1/editions/{edition['id']}/pass/selections",
        json={"eventIds": [event_id]},
    )
    assert sel_res.status_code == 409, sel_res.text
    assert sel_res.json()["error"]["code"] == "PASS_BLOCKED"
    assert "suspended" in sel_res.json()["error"]["message"].lower()

    # 3. POST /registrations (addons) must be rejected with 409 Conflict
    addon_res = await client.post(
        f"/api/v1/editions/{edition['id']}/registrations",
        json={"eventIds": [event_id]},
    )
    assert addon_res.status_code == 409, addon_res.text
    assert addon_res.json()["error"]["code"] == "PASS_BLOCKED"
    assert "suspended" in addon_res.json()["error"]["message"].lower()

    # Restore pass to active
    pass_row.status = "active"
    await db_session.commit()
