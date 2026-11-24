"""Every write the staff console makes must be accepted by the API contract.

The console builds its request bodies by hand, so a field that the API no longer
models (or a blank value for a NOT NULL column) used to surface as a 422
"Unprocessable Content" — or a 500 — only when an operator hit Save. These tests
replay the exact payloads ``frontend/src/pages/Admin*.jsx`` builds so the
contract stays honest.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.edition import Icon
from app.models.user import User

ISO = "%Y-%m-%dT%H:%M:%S.000Z"


def iso(dt: datetime) -> str:
    return dt.strftime(ISO)


async def _seeded_participant(db_session) -> User:
    """A real participant row: grants and desk writes need an existing account."""
    email = "panel-attendee@parallax.local"
    row = (
        await db_session.execute(select(User).where(User.email_normalized == email))
    ).scalars().first()
    if row is None:
        row = User(
            email=email,
            email_normalized=email,
            full_name="Panel Attendee",
            status="active",
            email_verified=True,
        )
        db_session.add(row)
        await db_session.commit()
    return row


async def _edition(client: AsyncClient) -> dict:
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _settings_payload(edition: dict) -> dict:
    """Exactly what AdminSettings.save() sends.

    If a field is added to that form and not to ``EditionUpdate``, this test is
    the place it fails instead of the live console.
    """
    return {
        "name": edition["name"],
        "tagline": edition.get("tagline") or "",
        "venue": edition["venue"],
        "city": edition["city"],
        "startsAt": edition["startsAt"],
        "endsAt": edition["endsAt"],
        "registrationOpensAt": edition.get("registrationOpensAt"),
        "registrationClosesAt": edition.get("registrationClosesAt"),
        "status": edition["status"],
        "contactEmail": edition.get("contactEmail"),
    }


@pytest.mark.asyncio
async def test_settings_panel_payload_saves(admin_client: AsyncClient):
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]

    payload = _settings_payload(edition)
    payload["tagline"] = "Replayed by the settings panel test"
    resp = await admin.patch(f"/api/v1/editions/{eid}/admin/settings", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["updated"] is True

    after = await admin.get(f"/api/v1/editions/{eid}/admin/settings")
    assert after.status_code == 200
    assert after.json()["data"]["tagline"] == "Replayed by the settings panel test"

    # Every key the form reads back must be in the response, or the form silently
    # resets a field to empty on the next render.
    for key in (
        "id",
        "slug",
        "name",
        "tagline",
        "venue",
        "city",
        "startsAt",
        "endsAt",
        "registrationOpensAt",
        "registrationClosesAt",
        "status",
        "contactEmail",
    ):
        assert key in after.json()["data"], key


@pytest.mark.asyncio
async def test_settings_rejects_a_field_the_api_does_not_have(admin_client: AsyncClient):
    """The old ghost field: the form sent allowedEmailDomains, nothing stored it."""
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]

    payload = _settings_payload(edition)
    payload["allowedEmailDomains"] = ["nssce.ac.in"]
    resp = await admin.patch(f"/api/v1/editions/{eid}/admin/settings", json=payload)
    assert resp.status_code == 422, resp.text
    details = resp.json()["error"]["details"]
    assert any("allowedEmailDomains" in str(item.get("field", "")) for item in details), details


@pytest.mark.asyncio
async def test_settings_blank_required_fields_are_readable_errors(admin_client: AsyncClient):
    """Clearing Name/Starts at must be a 422 with a message, never a 500."""
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]

    blank_name = await admin.patch(
        f"/api/v1/editions/{eid}/admin/settings", json={"name": "   "}
    )
    assert blank_name.status_code == 422, blank_name.text
    assert "name" in blank_name.json()["error"]["message"].lower()

    null_date = await admin.patch(
        f"/api/v1/editions/{eid}/admin/settings", json={"startsAt": None}
    )
    assert null_date.status_code == 422, null_date.text
    assert "starts" in null_date.json()["error"]["message"].lower()

    ends = datetime.fromisoformat(edition["endsAt"].replace("Z", "+00:00"))
    inverted = await admin.patch(
        f"/api/v1/editions/{eid}/admin/settings",
        json={"startsAt": (ends + timedelta(days=10)).strftime(ISO)},
    )
    assert inverted.status_code == 422, inverted.text
    assert "end after" in inverted.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_staff_role_grant_accepts_every_role_the_console_offers(
    admin_client: AsyncClient, db_session
):
    """The grant dropdown must not offer a role MembershipGrant rejects."""
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]
    attendee = await _seeded_participant(db_session)

    for role in ["edition_admin", "finance_admin", "event_coordinator", "checkin_staff"]:
        resp = await admin.post(
            f"/api/v1/editions/{eid}/admin/memberships",
            json={"email": attendee.email, "role": role},
        )
        assert resp.status_code in (200, 201), (role, resp.text)

        # One staff role per account: each later grant replaces the earlier one
        # instead of stacking a second permission set on the same person.
        listing = await admin.get(f"/api/v1/editions/{eid}/admin/memberships")
        mine = [row for row in listing.json()["data"] if row["userId"] == str(attendee.id)]
        assert [row["role"] for row in mine] == [role], mine

    # ``owner`` is a legacy label, not a grantable role: the console must not send it.
    owner = await admin.post(
        f"/api/v1/editions/{eid}/admin/memberships",
        json={"email": attendee.email, "role": "owner"},
    )
    assert owner.status_code == 422, owner.text


@pytest.mark.asyncio
async def test_event_category_and_policy_panels_accept_their_payloads(admin_client: AsyncClient):
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]

    # CategoryManager.submit()
    category = await admin.post(
        f"/api/v1/editions/{eid}/admin/categories",
        json={"name": "Panel Test", "slug": "panel-test", "accent": "cyan", "displayOrder": 3, "iconId": None},
    )
    assert category.status_code in (200, 201), category.text
    category_id = category.json()["data"]["id"] if "id" in category.json()["data"] else None
    if category_id is None:
        listing = await admin.get(f"/api/v1/editions/{eid}/admin/categories")
        category_id = next(
            row["id"] for row in listing.json()["data"] if row["slug"] == "panel-test"
        )

    updated = await admin.patch(
        f"/api/v1/editions/{eid}/admin/categories/{category_id}",
        json={"name": "Panel Test 2", "slug": "panel-test", "accent": "amber", "displayOrder": 4, "iconId": None},
    )
    assert updated.status_code == 200, updated.text

    # EventForm.submit()
    start = datetime.now(timezone.utc) + timedelta(days=30)
    event = await admin.post(
        f"/api/v1/editions/{eid}/admin/events",
        json={
            "categoryId": category_id,
            "slug": "panel-payload-event",
            "title": "Panel Payload Event",
            "summary": "Created by the payload contract test.",
            "descriptionMd": "",
            "rulesMd": "",
            "prizesMd": "",
            "format": "individual",
            "teamMinSize": 1,
            "teamMaxSize": 1,
            "baseValuePaise": 10000,
            "includedEligible": True,
            "addonPricePaise": 5000,
            "addonChargeBasis": "per_participant",
            "teamFeeBasis": "per_participant",
            "capacity": 50,
            "capacityUnit": "participants",
            "startsAt": iso(start),
            "endsAt": iso(start + timedelta(hours=3)),
            "venueRoom": "Hall A",
            "registrationOpensAt": iso(start - timedelta(days=5)),
            "registrationClosesAt": iso(start - timedelta(days=1)),
            "requiresApproval": False,
            "iconId": None,
            "bannerUrl": None,
            "accent": "cyan",
            "isFeatured": False,
            "sortOrder": 0,
            "status": "published",
            "changeReason": "Updated in the staff console",
        },
    )
    assert event.status_code in (200, 201), event.text

    # AdminPolicy.payloadFrom()
    policy = {
        "passPricePaise": 50000,
        "includedEventCount": 3,
        "includedSelectionMode": "up_to",
        "includedValueCapPaise": 45000,
        "capInclusive": True,
        "lunchIncludedDays": ["day1", "day2"],
        "addonRequiresPass": True,
        "teamMembersRequirePass": True,
        "teamFeeBasisDefault": "per_participant",
        "holdMinutes": 15,
        "selectionChangeDeadline": None,
        "gstNote": "Inclusive of all applicable taxes",
        "reason": "Panel payload contract test",
    }
    check = await admin.post(f"/api/v1/editions/{eid}/admin/policies/check", json=policy)
    assert check.status_code == 200, check.text
    created = await admin.post(f"/api/v1/editions/{eid}/admin/policies", json=policy)
    assert created.status_code in (200, 201), created.text


@pytest.mark.asyncio
async def test_announcement_icon_and_credential_panels_accept_their_payloads(
    admin_client: AsyncClient, db_session
):
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]

    # AdminAnnouncements.save()
    announcement = await admin.post(
        f"/api/v1/editions/{eid}/admin/announcements",
        json={"title": "Panel contract", "bodyMd": "Hello", "audience": "public", "status": "draft"},
    )
    assert announcement.status_code in (200, 201), announcement.text
    announcement_id = announcement.json()["data"]["id"]
    edited = await admin.patch(
        f"/api/v1/editions/{eid}/admin/announcements/{announcement_id}",
        json={"title": "Panel contract 2", "bodyMd": "Hello", "audience": "staff", "status": "published"},
    )
    assert edited.status_code == 200, edited.text
    removed = await admin.delete(f"/api/v1/editions/{eid}/admin/announcements/{announcement_id}")
    assert removed.status_code in (200, 204), removed.text

    # AdminSettings.uploadIcon(): FormData(file, name, recolorable)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8"/></svg>'
    icon = await admin.post(
        f"/api/v1/editions/{eid}/admin/icons",
        files={"file": ("panel.svg", svg, "image/svg+xml")},
        data={"name": "panel-icon", "recolorable": "false"},
    )
    assert icon.status_code in (200, 201), icon.text
    icon_id = icon.json()["data"]["id"]

    # Icons are objects in the bucket, not blobs in the database, and the public
    # route still serves whichever of the two an icon happens to live in.
    stored = (
        await db_session.execute(select(Icon).where(Icon.id == uuid.UUID(icon_id)))
    ).scalar_one()
    assert stored.storage_key, "icon upload did not write an object"
    assert stored.data is None, "icon bytes were written back into the database"
    served = await admin.get(f"/api/v1/public/icons/{icon_id}")
    assert served.status_code == 200, served.text
    assert served.headers["content-type"].startswith("image/svg+xml")

    # Archiving drops the object instead of leaving it in the bucket forever.
    key = stored.storage_key
    archived = await admin.delete(f"/api/v1/editions/{eid}/admin/icons/{icon_id}")
    assert archived.status_code in (200, 204), archived.text
    db_session.expire_all()
    after = (
        await db_session.execute(select(Icon).where(Icon.id == uuid.UUID(icon_id)))
    ).scalar_one()
    assert after.storage_key is None and after.data is None
    from app.integrations.storage import get_storage

    try:
        await get_storage().get(key)
        raise AssertionError("archived icon object still in the bucket")
    except FileNotFoundError:
        pass

    # AdminIdCardStudio.handleSaveCard() / handleRevokeCard()
    card = {
        "code": None,
        "registrationId": None,
        "name": "Payload Tester",
        "role": "Convention Delegate",
        "college": "NSS College of Engineering",
        "branch": "CSE",
        "tier": None,
        "gender": None,
        "foodPreference": None,
        "needsAccommodation": False,
        "design": {"roleKey": "delegate", "paletteIdx": 0, "kind": "waves"},
    }
    created_card = await admin.post(
        f"/api/v1/editions/{eid}/admin/custom-credentials", json=card
    )
    assert created_card.status_code in (200, 201), created_card.text
    card_id = created_card.json()["data"]["id"]

    card["name"] = "Payload Tester Two"
    updated_card = await admin.patch(
        f"/api/v1/editions/{eid}/admin/custom-credentials/{card_id}", json=card
    )
    assert updated_card.status_code == 200, updated_card.text

    revoked = await admin.post(
        f"/api/v1/editions/{eid}/admin/custom-credentials/{card_id}/revoke",
        json={"reason": "Revoked from the ID card studio"},
    )
    assert revoked.status_code == 200, revoked.text


@pytest.mark.asyncio
async def test_registration_config_panel_payload_saves(admin_client: AsyncClient):
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]

    current = await admin.get(f"/api/v1/editions/{eid}/admin/registration/config")
    assert current.status_code == 200, current.text
    config = current.json()["data"]
    settings = config["registration"]

    # AdminRegistrationSettings.buildPayload()
    payload = {
        "settings": {
            "registrationEnabled": settings["registrationEnabled"],
            "opensAt": settings["opensAt"],
            "closesAt": settings["closesAt"],
            "acceptedFormats": settings["acceptedFormats"] or ["pdf", "jpg", "jpeg", "png"],
            "maxUploadBytes": max(1024, settings["maxUploadBytes"]),
            "allowResubmission": settings["allowResubmission"],
            "helpdeskPhone": settings["helpdeskPhone"],
            "paymentInstructions": settings["paymentInstructions"] or None,
            "refundPolicy": settings["refundPolicy"] or None,
            "approvalMessage": settings["approvalMessage"] or None,
            "rejectionMessage": settings["rejectionMessage"] or None,
            "notificationTemplates": settings["notificationTemplates"] or {},
        },
        "categories": {
            category["code"]: {
                "name": category["name"],
                "description": category["description"] or None,
                "feePaise": category["feePaise"],
                "enabled": category["enabled"],
                "displayOrder": category["displayOrder"],
                "requiredDocuments": [
                    {
                        "type": document["type"],
                        "label": document["label"],
                        "required": bool(document.get("required", True)),
                    }
                    for document in category["requiredDocuments"]
                ],
            }
            for category in config["categories"]
        },
    }
    resp = await admin.patch(
        f"/api/v1/editions/{eid}/admin/registration/config", json=payload
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_desk_and_user_panels_accept_their_payloads(admin_client: AsyncClient, db_session):
    admin = admin_client
    edition = await _edition(admin)
    eid = edition["id"]
    attendee = await _seeded_participant(db_session)

    users = await admin.get(f"/api/v1/editions/{eid}/admin/users")
    assert users.status_code == 200
    rows = users.json()["data"]
    participant = next((row for row in rows if row["id"] == str(attendee.id)), None)
    assert participant is not None, "the panel attendee account is missing"

    # AdminUsers.apply()
    suspend = await admin.patch(
        f"/api/v1/editions/{eid}/admin/users/{participant['id']}/status",
        json={"status": "suspended", "reason": "Panel payload contract test"},
    )
    assert suspend.status_code == 200, suspend.text
    restore = await admin.patch(
        f"/api/v1/editions/{eid}/admin/users/{participant['id']}/status",
        json={"status": "active", "reason": None},
    )
    assert restore.status_code == 200, restore.text

    # AdminCheckin.handleManualMark()
    marked = await admin.post(
        f"/api/v1/editions/{eid}/admin/attendance/mark",
        json={
            "userId": participant["id"],
            "eventId": None,
            "day": "day1",
            "note": "host_manual_roster",
        },
    )
    assert marked.status_code in (200, 201, 409), marked.text

    # AdminPayments.submit(): the panel posts this body for a refund.
    payments = await admin.get(f"/api/v1/editions/{eid}/admin/payments")
    assert payments.status_code == 200
    paid = [row for row in payments.json()["data"] if row["status"] in ("paid", "captured")]
    if paid:
        refund = await admin.post(
            f"/api/v1/editions/{eid}/admin/refunds",
            json={
                "orderId": paid[0]["id"],
                "amountPaise": max(1, int(paid[0]["amountPaise"])),
                "reasonCode": "requested_by_participant",
                "reasonNote": None,
            },
        )
        # 200/201 accepted, 409 means the order is already refunded: both are
        # contract-correct answers, a 422 would mean the panel body is wrong.
        assert refund.status_code in (200, 201, 409), refund.text
