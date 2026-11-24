"""Gender, meal and accommodation: asked at purchase, shown at the door.

The pass form collects them, the registration row stores them, the desk sees
them on a scan. A paid attendee may still change the logistics later; identity
fields stay locked as before.
"""

from __future__ import annotations

import base64

import pytest
from httpx import AsyncClient

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

pytestmark = pytest.mark.asyncio


async def _edition_id(client: AsyncClient) -> str:
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


async def _login(client: AsyncClient, email: str, role: str = "participant") -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "role": role, "fullName": "Logistics Tester"},
    )
    assert resp.status_code == 200, resp.text


async def _category(client: AsyncClient, edition_id: str) -> dict:
    resp = await client.get(f"/api/v1/editions/{edition_id}/registration")
    assert resp.status_code == 200, resp.text
    return next(item for item in resp.json()["data"]["categories"] if item["enabled"])


async def _category_id(client: AsyncClient, edition_id: str) -> str:
    return (await _category(client, edition_id))["id"]


async def _profile(client: AsyncClient, edition_id: str, category_id: str, **overrides):
    body = {
        "categoryId": category_id,
        "fullName": "Meera Suresh",
        "email": "meera.suresh@example.test",
        "phone": "9876543210",
        "collegeName": "NSS College of Engineering",
        "course": "B.Tech",
        "branch": "Computer Science",
        "yearOfStudy": "3",
        "city": "Palakkad",
        "state": "Kerala",
        "gender": "female",
        "foodPreference": "veg",
        "needsAccommodation": True,
        **overrides,
    }
    return await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile", json=body
    )


async def test_profile_stores_and_returns_logistics(client: AsyncClient) -> None:
    await _login(client, "logistics-one@example.test")
    edition_id = await _edition_id(client)
    category_id = await _category_id(client, edition_id)

    resp = await _profile(client, edition_id, category_id)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["gender"] == "female"
    assert data["foodPreference"] == "veg"
    assert data["needsAccommodation"] is True

    # Editing them later is a normal update, not an identity change.
    resp = await _profile(
        client, edition_id, category_id, foodPreference="non_veg", needsAccommodation=False
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["foodPreference"] == "non_veg"
    assert data["needsAccommodation"] is False


async def test_unknown_gender_or_meal_is_rejected(client: AsyncClient) -> None:
    await _login(client, "logistics-two@example.test")
    edition_id = await _edition_id(client)
    category_id = await _category_id(client, edition_id)

    bad_gender = await _profile(client, edition_id, category_id, gender="robot")
    assert bad_gender.status_code == 422, bad_gender.text

    bad_meal = await _profile(client, edition_id, category_id, foodPreference="seafood")
    assert bad_meal.status_code == 422, bad_meal.text


async def test_desk_scan_reports_the_same_values(client: AsyncClient, admin_client: AsyncClient) -> None:
    await _login(client, "logistics-three@example.test")
    edition_id = await _edition_id(client)
    category_id = await _category_id(client, edition_id)
    saved = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-three@example.test",
        gender="male",
        foodPreference="non_veg",
        needsAccommodation=False,
    )
    assert saved.status_code == 200, saved.text

    # A ticket only exists once the pass is paid, so drive the mock gateway.
    category = await _category(client, edition_id)
    for requirement in category["requiredDocuments"]:
        resp = await client.post(
            f"/api/v1/editions/{edition_id}/registration/documents/{requirement['type']}",
            files={"file": ("id.png", PNG, "image/png")},
        )
        assert resp.status_code == 200, resp.text
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    order_id = submitted.json()["data"]["payment"]["orderId"]
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{order_id}/mock"
    )
    assert paid.status_code == 200, paid.text

    tickets = await client.get(f"/api/v1/editions/{edition_id}/tickets")
    assert tickets.status_code == 200, tickets.text
    items = tickets.json()["data"]
    assert items, tickets.text

    # Same HTTP client: switch the session to the desk before scanning.
    await _login(admin_client, "owner@parallax.local", role="admin")
    scan = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": items[0]["token"]},
    )
    assert scan.status_code == 200, scan.text
    data = scan.json()["data"]
    assert data["gender"] == "male"
    assert data["foodPreference"] == "non_veg"
    assert data["needsAccommodation"] is False


async def test_codes_are_stored_as_small_integers(
    client: AsyncClient, db_session
) -> None:
    """The column holds 0/1, the API hands back the word. Two spellings, one row."""
    from sqlalchemy import select

    from app.models.registration import CollegeRegistration

    await _login(client, "logistics-codes@example.test")
    edition_id = await _edition_id(client)
    category_id = await _category_id(client, edition_id)
    resp = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-codes@example.test",
        gender="female",
        foodPreference="veg",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["gender"] == "female"
    assert resp.json()["data"]["foodPreference"] == "veg"

    row = (
        await db_session.execute(
            select(CollegeRegistration).where(
                CollegeRegistration.email == "logistics-codes@example.test"
            )
        )
    ).scalar_one()
    assert row.gender == 1
    assert row.food_preference == 0

async def _pay(client: AsyncClient, edition_id: str) -> None:
    """Drive a real checkout as far as mock payment."""
    category = await _category(client, edition_id)
    for requirement in category["requiredDocuments"]:
        resp = await client.post(
            f"/api/v1/editions/{edition_id}/registration/documents/{requirement['type']}",
            files={"file": ("id.png", PNG, "image/png")},
        )
        assert resp.status_code == 200, resp.text
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    order_id = submitted.json()["data"]["payment"]["orderId"]
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{order_id}/mock"
    )
    assert paid.status_code == 200, paid.text


async def test_paying_without_gender_or_meal_is_rejected(client: AsyncClient) -> None:
    """The form is not the only gate: the money endpoint refuses too.

    The kitchen and the hostel allocate from these two answers, so a pass that
    skipped them is a booking the organisers cannot serve.
    """
    await _login(client, "logistics-four@example.test")
    edition_id = await _edition_id(client)
    category_id = await _category_id(client, edition_id)

    saved = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-four@example.test",
        gender=None,
        foodPreference=None,
    )
    assert saved.status_code == 200, saved.text

    category = await _category(client, edition_id)
    for requirement in category["requiredDocuments"]:
        resp = await client.post(
            f"/api/v1/editions/{edition_id}/registration/documents/{requirement['type']}",
            files={"file": ("id.png", PNG, "image/png")},
        )
        assert resp.status_code == 200, resp.text

    blocked = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert blocked.status_code in (409, 422), blocked.text
    body = blocked.json()
    missing = body.get("details", {}).get("missingFields") or body.get("error", {}).get(
        "details", {}
    ).get("missingFields")
    assert missing, blocked.text
    assert "Gender" in missing and "Meal Preference" in missing, missing

    # Answering them unblocks the same checkout, nothing else was wrong.
    answered = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-four@example.test",
        gender="male",
        foodPreference="non_veg",
    )
    assert answered.status_code == 200, answered.text
    await _pay(client, edition_id)


async def test_paid_pass_refuses_a_blank_logistics_edit(
    client: AsyncClient,
) -> None:
    """A paid booking cannot have its meal or gender removed afterwards.

    The profile endpoint is a full replace, so a missing or null answer is a
    request to remove it. The stored answer survives and the caller is told,
    instead of getting a 200 for an edit that was never applied.
    """
    await _login(client, "logistics-five@example.test")
    edition_id = await _edition_id(client)
    category_id = await _category_id(client, edition_id)

    saved = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-five@example.test",
        gender="female",
        foodPreference="veg",
    )
    assert saved.status_code == 200, saved.text
    await _pay(client, edition_id)

    # Leaving the answers out of the replace is the same request as nulling them.
    omitted = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": category_id,
            "fullName": "Meera Suresh",
            "email": "logistics-five@example.test",
            "phone": "9876543210",
            "collegeName": "NSS College of Engineering",
            "branch": "Computer Science",
            "yearOfStudy": "3",
        },
    )
    assert omitted.status_code == 409, omitted.text
    assert omitted.json()["error"]["code"] == "REGISTRATION_LOCKED"

    # So is an explicit null.
    blanked = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-five@example.test",
        gender=None,
        foodPreference=None,
    )
    assert blanked.status_code == 409, blanked.text
    assert blanked.json()["error"]["code"] == "REGISTRATION_LOCKED"

    # The meal answer is guarded the same way.
    meal = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-five@example.test",
        gender="female",
        foodPreference=None,
    )
    assert meal.status_code == 409, meal.text
    assert meal.json()["error"]["code"] == "REGISTRATION_LOCKED"

    # The row still carries what the kitchen and the hostel were told.
    current = await client.get(f"/api/v1/editions/{edition_id}/registration")
    assert current.status_code == 200, current.text
    view = current.json()["data"]["registration"]
    assert view["gender"] == "female"
    assert view["foodPreference"] == "veg"

    # Changing meal or accommodation after payment is also locked for the user.
    changed = await _profile(
        client,
        edition_id,
        category_id,
        email="logistics-five@example.test",
        gender="female",
        foodPreference="non_veg",
        needsAccommodation=False,
    )
    assert changed.status_code == 409, changed.text
    assert changed.json()["error"]["code"] == "REGISTRATION_LOCKED"
