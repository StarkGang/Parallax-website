"""Studio-issued ID cards: stored credentials, unique IDs, verifiable scans.

A custom card has no user account or registration. It is a row created by an
edition/super admin, resolvable by its printed ID or by a signed token, printable
again later and revocable when a badge is lost.
"""

from __future__ import annotations

import base64
import uuid

import pytest
from httpx import AsyncClient

from app.services import credentials as credential_service

pytestmark = pytest.mark.asyncio


async def _edition_id(client: AsyncClient) -> str:
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


async def _create(client: AsyncClient, edition_id: str, **payload) -> dict:
    body = {
        "name": "SANDRA H MENON",
        "role": "Finance Coordinator",
        "college": "NSS College of Engineering, Palakkad",
        "tier": "Core Team",
        "design": {"roleKey": "coordinator", "paletteIdx": 1},
        **payload,
    }
    resp = await client.post(
        f"/api/v1/editions/{edition_id}/admin/custom-credentials", json=body
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_admin_creates_card_with_generated_code_and_signed_token(
    admin_client: AsyncClient,
) -> None:
    edition_id = await _edition_id(admin_client)
    card = await _create(admin_client, edition_id)

    assert card["code"].startswith("PXC-")
    assert card["status"] == "active"
    assert card["token"].startswith("PXC-")
    # The token must be a real signature over the row id, not a formatted string.
    assert credential_service.parse_token(card["token"]) == uuid.UUID(card["id"])
    assert credential_service.token_is_valid(card["token"], uuid.UUID(card["id"]))

    listing = await admin_client.get(
        f"/api/v1/editions/{edition_id}/admin/custom-credentials"
    )
    assert listing.status_code == 200
    codes = [row["code"] for row in listing.json()["data"]]
    assert card["code"] in codes


async def test_duplicate_printed_id_is_rejected(admin_client: AsyncClient) -> None:
    edition_id = await _edition_id(admin_client)
    first = await _create(admin_client, edition_id, code="PXC-ABC234")

    resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/custom-credentials",
        json={"name": "OTHER PERSON", "role": "Operations", "code": first["code"]},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "CREDENTIAL_CODE_TAKEN"

    # Case and spacing are normalised, so the same ID cannot slip through.
    resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/custom-credentials",
        json={"name": "OTHER PERSON", "role": "Operations", "code": " pxc-abc234 "},
    )
    assert resp.status_code == 409, resp.text


async def test_scan_resolves_token_and_typed_code(admin_client: AsyncClient) -> None:
    edition_id = await _edition_id(admin_client)
    card = await _create(admin_client, edition_id, name="JISHNU J")

    by_token = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": card["token"], "day": "1"},
    )
    assert by_token.status_code == 200, by_token.text
    assert by_token.json()["data"]["result"] == "admitted"
    assert by_token.json()["data"]["participantName"] == "JISHNU J"

    by_code = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": card["code"].lower(), "day": "1"},
    )
    assert by_code.status_code == 200, by_code.text
    assert by_code.json()["data"]["credential"]["code"] == card["code"]

    # A token with a broken signature must not admit anyone. Flip the last
    # character instead of hard-coding "0": the signature is hex, so a card that
    # already ends in "0" would make the "tampered" token identical.
    tampered = f"{card['token'][:-1]}{'1' if card['token'][-1] != '1' else '2'}"
    bad = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": tampered},
    )
    assert bad.status_code == 404, bad.text


async def test_revoked_card_is_denied_and_listed(admin_client: AsyncClient) -> None:
    edition_id = await _edition_id(admin_client)
    card = await _create(admin_client, edition_id)

    resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/custom-credentials/{card['id']}/revoke",
        json={"reason": "Badge lost"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "revoked"

    denied = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin",
        json={"token": card["token"]},
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "CREDENTIAL_REVOKED"

    # Editing a revoked card is refused; the row stays as the audit trail.
    edit = await admin_client.patch(
        f"/api/v1/editions/{edition_id}/admin/custom-credentials/{card['id']}",
        json={"name": "RENAMED", "role": "Operations", "code": card["code"]},
    )
    assert edit.status_code == 409, edit.text


async def test_public_verification_page_accepts_custom_token(
    admin_client: AsyncClient,
) -> None:
    edition_id = await _edition_id(admin_client)
    card = await _create(admin_client, edition_id, name="ANIRUDH R")

    resp = await admin_client.get(f"/api/v1/public/c/{card['token']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["valid"] is True
    assert body["kind"] == "custom_credential"
    assert body["name"] == "ANIRUDH R"

    html = await admin_client.get(
        f"/api/v1/public/c/{card['code']}",
        headers={"accept": "text/html"},
    )
    assert html.status_code == 200
    assert "VALID CREDENTIAL" in html.text


async def test_token_shape_skips_the_ticket_lookup(admin_client: AsyncClient) -> None:
    edition_id = await _edition_id(admin_client)
    card = await _create(admin_client, edition_id, name="RESHMA P")

    assert credential_service.looks_like_token(card["token"])
    assert not credential_service.looks_like_token(card["code"])
    assert not credential_service.looks_like_token("PX-0123456789ABCDEF0123456789ABCDEF-0123456789")
    # A /c/ URL scanned from a phone still dispatches to the credential path.
    assert credential_service.looks_like_token(f"https://example.test/c/{card['token']}")


async def test_scan_reports_gender_meal_and_accommodation(admin_client: AsyncClient) -> None:
    edition_id = await _edition_id(admin_client)
    card = await _create(
        admin_client,
        edition_id,
        name="FATHIMA N",
        gender="female",
        food_preference="veg",
        needs_accommodation=True,
    )

    resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin", json={"token": card["token"]}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["gender"] == "female"
    assert data["foodPreference"] == "veg"
    assert data["needsAccommodation"] is True
    assert data["credential"]["foodPreference"] == "veg"


async def test_blank_name_or_role_is_refused_by_the_api(admin_client: AsyncClient) -> None:
    """A badge with no name identifies nobody, so the API refuses it.

    The studio already blocks the save button; this proves the rule does not
    live only in the browser.
    """
    edition_id = await _edition_id(admin_client)
    url = f"/api/v1/editions/{edition_id}/admin/custom-credentials"

    blank = await admin_client.post(
        url, json={"name": "   ", "role": "Volunteer", "design": {}}
    )
    assert blank.status_code == 422, blank.text

    no_role = await admin_client.post(url, json={"name": "SOMEONE", "role": "", "design": {}})
    assert no_role.status_code == 422, no_role.text

    too_long = await admin_client.post(
        url, json={"name": "X" * 121, "role": "Volunteer", "design": {}}
    )
    assert too_long.status_code == 422, too_long.text

    # Trimming happens before the row is written, so the stored name is clean.
    card = await _create(admin_client, edition_id, name="  RENJITH K  ")
    assert card["name"] == "RENJITH K"


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def test_card_photo_upload_returns_a_durable_url(admin_client: AsyncClient) -> None:
    """The photo must outlive the browser tab that uploaded it.

    It used to be a blob: URL created in the studio, which stopped rendering as
    soon as the tab closed; a card reprinted later had no face on it.
    """
    edition_id = await _edition_id(admin_client)
    url = f"/api/v1/editions/{edition_id}/admin/custom-credentials/photo"

    ok = await admin_client.post(url, files={"file": ("face.png", PNG_BYTES, "image/png")})
    assert ok.status_code == 200, ok.text
    stored = ok.json()["data"]["url"]
    # Local storage hands back a path the app serves, object storage an absolute
    # URL; both survive the tab, which a blob: URL does not.
    assert not stored.startswith("blob:"), stored
    assert not stored.startswith("data:"), stored
    assert "/credentials/" in stored or "credentials%2F" in stored, stored

    not_an_image = await admin_client.post(
        url, files={"file": ("notes.png", b"<html>not a photo</html>", "image/png")}
    )
    assert not_an_image.status_code == 415, not_an_image.text


async def test_registered_attendee_card_links_and_reuses_its_qr(
    admin_client: AsyncClient, db_session
) -> None:
    """Saving an attendee's card again reopens the same card and QR.

    The studio loaded a registered attendee's number as the printed ID, which
    the server refused (the number already belongs to that registration), so the
    save failed and the QR never appeared. A card built from a registration is
    linked to it: the number is allowed and the second save reuses the row.
    """
    from sqlalchemy import select

    from app.models.registration import CollegeRegistration, RegistrationCategory
    from app.models.user import User

    edition_id = await _edition_id(admin_client)
    user = (await db_session.execute(select(User).limit(1))).scalars().first()
    category = (
        await db_session.execute(
            select(RegistrationCategory).where(
                RegistrationCategory.edition_id == uuid.UUID(edition_id)
            )
        )
    ).scalars().first()
    assert user is not None and category is not None

    registration = CollegeRegistration(
        edition_id=uuid.UUID(edition_id),
        user_id=user.id,
        category_id=category.id,
        category_code=category.code,
        category_name=category.name,
        full_name="ADITHYA R",
        email="adithya@example.test",
        college_name="NSS College of Engineering, Palakkad",
        fee_paise=category.fee_paise,
        payment_status="paid",
        verification_status="approved",
        registration_number="PX-LINK0001",
    )
    db_session.add(registration)
    await db_session.commit()
    reg_number = registration.registration_number
    url = f"/api/v1/editions/{edition_id}/admin/custom-credentials"

    # Without the link the number stays reserved for the registration.
    unlinked = await admin_client.post(
        url, json={"name": "SOMEONE ELSE", "role": "Volunteer", "code": reg_number}
    )
    assert unlinked.status_code == 409, unlinked.text

    first = await admin_client.post(
        url,
        json={
            "name": "ADITHYA R",
            "role": "College Student",
            "code": reg_number,
            "registrationId": str(registration.id),
            "design": {"roleKey": "delegate"},
        },
    )
    assert first.status_code == 200, first.text
    card = first.json()["data"]
    assert first.json().get("reused") is False
    assert card["code"] == reg_number
    assert card["registrationId"] == str(registration.id)
    assert card["token"].startswith("PXC-")

    again = await admin_client.post(
        url,
        json={
            "name": "ADITHYA R",
            "role": "College Student",
            "code": reg_number,
            "registrationId": str(registration.id),
            "design": {"roleKey": "delegate", "paletteIdx": 3},
        },
    )
    assert again.status_code == 200, again.text
    reopened = again.json()["data"]
    assert again.json().get("reused") is True
    assert reopened["id"] == card["id"]
    assert reopened["token"] == card["token"]
    assert reopened["design"]["paletteIdx"] == 3

    # The reopened card's QR is still a signed, scannable token.
    scan = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/checkin", json={"token": card["token"]}
    )
    assert scan.status_code == 200, scan.text
    assert scan.json()["data"]["participantName"] == "ADITHYA R"


async def test_linked_card_qr_is_the_attendees_own_pass(
    admin_client: AsyncClient, db_session
) -> None:
    """A linked card carries the attendee's pass, not a token of its own.

    Scanning it must land on the normal ticket path, which is what actually
    records attendance and applies suspension, payment and event rules. The card
    never gets rights the registration does not have, and an unpaid registration
    has no pass yet, so its card prints no working QR at all.
    """
    from sqlalchemy import select

    from app.models.registration import RegistrationCategory
    from tests.lifecycle_helpers import (
        edition_ctx,
        fill_profile,
        login,
        login_admin,
        register_paid,
    )

    ctx = await edition_ctx(admin_client, db_session)
    email = "linked.card@test.local"
    registration = await register_paid(admin_client, ctx, email)
    await login_admin(admin_client)
    url = f"/api/v1/editions/{ctx.edition_id}/admin/custom-credentials"

    paid_card = await admin_client.post(
        url,
        json={
            "name": registration["fullName"].upper(),
            "role": "College Student",
            "code": registration["registrationNumber"],
            "registrationId": registration["id"],
        },
    )
    assert paid_card.status_code == 200, paid_card.text
    card = paid_card.json()["data"]
    assert card["token"].startswith("PXC-")
    # The pass ticket is what the portal prints, so the card prints the same one.
    assert card["entryQr"] and "/c/PX-" in card["entryQr"]
    assert card["token"] not in card["entryQr"]

    # The desk list carries it too, so the studio can build the card from a row.
    listing = await admin_client.get(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration?pageSize=200"
    )
    assert listing.status_code == 200, listing.text
    row = next(item for item in listing.json()["data"] if item["id"] == registration["id"])
    assert row["entryQr"] == card["entryQr"]

    # Scanning the card's QR is scanning the attendee's pass: attendance is
    # recorded by the ticket path, not by anything credential-specific.
    scan = await admin_client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/checkin",
        json={"token": card["entryQr"], "day": "1"},
    )
    assert scan.status_code == 200, scan.text
    assert scan.json()["data"]["participantName"] == registration["fullName"]

    # An unlinked card keeps its own token and never carries an entry payload.
    staff = await _create(admin_client, str(ctx.edition_id), name="SPONSOR GUEST")
    assert staff["entryQr"] is None
    assert staff["token"].startswith("PXC-")

    # A registration that has not paid yet has no pass, so no entry QR.
    unpaid_email = "unpaid.card@test.local"
    unpaid_category = (
        await db_session.execute(
            select(RegistrationCategory).where(
                RegistrationCategory.edition_id == uuid.UUID(str(ctx.edition_id)),
                RegistrationCategory.enabled.is_(True),
            )
        )
    ).scalars().first()
    assert unpaid_category is not None
    await login(admin_client, unpaid_email)
    await fill_profile(admin_client, str(ctx.edition_id), unpaid_category, unpaid_email)
    await login_admin(admin_client)
    unpaid_view = await admin_client.get(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration?q={unpaid_email}"
    )
    assert unpaid_view.status_code == 200, unpaid_view.text
    unpaid_row = unpaid_view.json()["data"][0]
    unpaid_card = await admin_client.post(
        url,
        json={
            "name": unpaid_row["fullName"].upper(),
            "role": "College Student",
            "registrationId": unpaid_row["id"],
        },
    )
    assert unpaid_card.status_code == 200, unpaid_card.text
    assert unpaid_card.json()["data"]["entryQr"] is None

    # Scanning an unpaid linked card's token or code at check-in must be refused.
    unpaid_checkin = await admin_client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/checkin",
        json={"token": unpaid_card.json()["data"]["token"]},
    )
    assert unpaid_checkin.status_code == 409, unpaid_checkin.text
    assert unpaid_checkin.json()["error"]["code"] == "PASS_NOT_ACTIVE"

    # Revoking a linked card and re-issuing for the same registration reactivates it cleanly.
    revoked = await admin_client.post(
        f"{url}/{card['id']}/revoke", json={"reason": "Lost card"}
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["status"] == "revoked"

    reissued = await admin_client.post(
        url,
        json={
            "name": registration["fullName"].upper(),
            "role": "College Student",
            "code": registration["registrationNumber"],
            "registrationId": registration["id"],
        },
    )
    assert reissued.status_code == 200, reissued.text
    assert reissued.json()["data"]["id"] == card["id"]
    assert reissued.json()["data"]["status"] == "active"


async def test_oversized_card_design_is_refused(admin_client: AsyncClient) -> None:
    """Design is presentation only, so a bloated payload has no reason to exist."""
    edition_id = await _edition_id(admin_client)
    resp = await admin_client.post(
        f"/api/v1/editions/{edition_id}/admin/custom-credentials",
        json={
            "name": "BIG DESIGN",
            "role": "Volunteer",
            "design": {"roleKey": "volunteer", "junk": "x" * 5000},
        },
    )
    assert resp.status_code in (409, 422), resp.text
    assert "too large" in resp.text.lower(), resp.text
