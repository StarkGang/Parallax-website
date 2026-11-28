"""End-to-end tests for the college registration workflow.

Each scenario uses a distinct participant account against the same seeded
edition, exactly like the portal. Payment runs through the sandbox path so no
external credentials are required.
"""

from __future__ import annotations

import base64
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.commerce import PaymentOrder, PaymentTransaction
from app.models.registration import CollegeRegistration, RegistrationCategory

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

from tests.seat_helpers import buy_seat
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


async def _edition_id(client: AsyncClient) -> str:
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


async def _login(client: AsyncClient, email: str, role: str = "participant") -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "role": role, "fullName": email.split("@")[0].title()},
    )
    assert resp.status_code == 200, resp.text


async def _config(client: AsyncClient, edition_id: str) -> dict:
    resp = await client.get(f"/api/v1/editions/{edition_id}/registration")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _profile(
    client: AsyncClient, edition_id: str, category_id: str, email: str, college: str = "NSSCE"
) -> dict:
    resp = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": category_id,
            "fullName": "Test Participant",
            "email": email,
            "phone": "9876543210",
            "collegeName": college,
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
    return resp.json()["data"]


async def _upload(
    client: AsyncClient,
    edition_id: str,
    doc_type: str,
    *,
    filename: str = "id.png",
    data: bytes = PNG,
    content_type: str = "image/png",
) -> dict:
    return await client.post(
        f"/api/v1/editions/{edition_id}/registration/documents/{doc_type}",
        files={"file": (filename, data, content_type)},
    )


async def _register_paid(
    client: AsyncClient,
    edition_id: str,
    *,
    email: str,
    category_code: str,
) -> dict:
    config = await _config(client, edition_id)
    category = next(item for item in config["categories"] if item["code"] == category_code)
    await _profile(client, edition_id, category["id"], email)
    upload = await _upload(client, edition_id, "college_id")
    assert upload.status_code == 200, upload.text
    # The printed pass needs a passport photo, so every paid registration must
    # provide one before the server accepts payment.
    upload = await _upload(client, edition_id, "photo", filename="photo.png")
    assert upload.status_code == 200, upload.text
    if category_code == "iste_member":
        upload = await _upload(client, edition_id, "iste_card")
        assert upload.status_code == 200, upload.text
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    payment = submitted.json()["data"]["payment"]
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    return paid.json()["data"]["registration"]


@pytest.mark.asyncio
async def test_iste_member_registration_approval_and_notification(client: AsyncClient):
    edition_id = await _edition_id(client)
    await _login(client, "iste.student@test.local")
    config = await _config(client, edition_id)
    iste = next(item for item in config["categories"] if item["code"] == "iste_member")
    assert iste["feePaise"] == 50000
    assert {doc["type"] for doc in iste["requiredDocuments"]} == {
        "college_id",
        "iste_card",
        "photo",
    }

    registration = await _register_paid(
        client, edition_id, email="iste.student@test.local", category_code="iste_member"
    )
    assert registration["paymentStatus"] == "paid"
    assert registration["verificationStatus"] == "pending_verification"
    assert registration["feePaise"] == 50000
    assert registration["registrationNumber"].startswith("PX-")
    assert registration["transactionId"]

    # The money moved, but nothing is approved automatically.
    await _login(client, "owner@parallax.local", role="admin")
    listing = await client.get(
        f"/api/v1/editions/{edition_id}/admin/registration?category=iste_member&state=pending_verification"
    )
    assert listing.status_code == 200, listing.text
    row = next(
        item
        for item in listing.json()["data"]
        if item["email"] == "iste.student@test.local"
    )
    detail = await client.get(
        f"/api/v1/editions/{edition_id}/admin/registration/{row['id']}"
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()["data"]
    assert len(body["documents"]) == 3
    assert body["documents"][0]["mime"] == "image/png"

    # Documents are only readable through the authenticated route.
    document = body["documents"][0]
    content = await client.get(
        f"/api/v1/editions/{edition_id}/admin/registration/{body['id']}/documents/{document['id']}/content"
    )
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/")

    approved = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{body['id']}/decision",
        json={"decision": "approved", "notes": "ISTE card matches the membership number."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["verificationStatus"] == "approved"
    assert approved.json()["data"]["adminNotes"]

    await _login(client, "iste.student@test.local")
    mine = await _config(client, edition_id)
    assert mine["registration"]["verificationStatus"] == "approved"
    assert any(n["kind"] == "approved" for n in mine["notifications"])
    confirmation = await client.get(
        f"/api/v1/editions/{edition_id}/registration/confirmation",
        follow_redirects=False,
    )
    assert confirmation.status_code == 303
    assert confirmation.headers["location"] == "/portal/registration"


@pytest.mark.asyncio
async def test_non_iste_and_polytechnic_pricing(client: AsyncClient):
    edition_id = await _edition_id(client)
    await _login(client, "noniste.student@test.local")
    non_iste = await _register_paid(
        client, edition_id, email="noniste.student@test.local", category_code="non_iste"
    )
    assert non_iste["feePaise"] == 60000
    assert {doc["type"] for doc in non_iste["documentRequirements"]} == {
        "college_id",
        "photo",
    }

    await _login(client, "poly.student@test.local")
    poly = await _register_paid(
        client, edition_id, email="poly.student@test.local", category_code="polytechnic"
    )
    assert poly["feePaise"] == 29900
    assert {doc["type"] for doc in poly["documentRequirements"]} == {
        "college_id",
        "photo",
    }


@pytest.mark.asyncio
async def test_fake_iste_claim_rejection_and_refund_tracking(
    client: AsyncClient, db_session
):
    edition_id = await _edition_id(client)
    await _login(client, "fake.iste@test.local")
    registration = await _register_paid(
        client, edition_id, email="fake.iste@test.local", category_code="iste_member"
    )
    registration_id = registration["id"]

    await _login(client, "owner@parallax.local", role="admin")
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration_id}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_iste_card",
            "reason": "The uploaded card is a college library card, not an ISTE card.",
            "initiateRefund": True,
        },
    )
    assert rejected.status_code == 200, rejected.text
    detail = rejected.json()["data"]
    assert detail["verificationStatus"] == "rejected"
    assert "ISTE" in detail["rejectionReason"]
    # Money has been requested back, but is NOT reported as complete.
    assert detail["refundStatus"] == "initiated"
    assert detail["refund"]["status"] == "pending"
    assert detail["paymentStatus"] == "paid"

    completed_without_reference = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration_id}/refund",
        json={"action": "completed"},
    )
    assert completed_without_reference.status_code == 422

    completed = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration_id}/refund",
        json={"action": "completed", "gatewayRefundId": "UTR-TEST-12345", "note": "Manual bank transfer confirmed."},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["data"]["refundStatus"] == "completed"
    assert completed.json()["data"]["state"] == "refunded"

    await _login(client, "fake.iste@test.local")
    mine = await _config(client, edition_id)
    assert mine["registration"]["refundStatus"] == "completed"
    assert any(n["kind"] == "rejected" for n in mine["notifications"])
    assert any(n["kind"] == "refund_completed" for n in mine["notifications"])


@pytest.mark.asyncio
async def test_document_validation_and_cross_user_access(
    client: AsyncClient, db_session
):
    edition_id = await _edition_id(client)
    await _login(client, "docs.one@test.local")
    config = await _config(client, edition_id)
    iste = next(item for item in config["categories"] if item["code"] == "iste_member")
    await _profile(client, edition_id, iste["id"], "docs.one@test.local")

    missing = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert missing.status_code == 422, missing.text
    assert missing.json()["error"]["code"] == "DOCUMENTS_MISSING"

    unsupported = await _upload(
        client, edition_id, "college_id", filename="id.txt", data=b"hello", content_type="text/plain"
    )
    assert unsupported.status_code == 415, unsupported.text

    mismatch = await _upload(
        client,
        edition_id,
        "college_id",
        filename="id.png",
        data=PDF,
        content_type="image/png",
    )
    assert mismatch.status_code == 415, mismatch.text

    ok = await _upload(client, edition_id, "college_id")
    assert ok.status_code == 200, ok.text
    document_id = ok.json()["data"]["document"]["id"]

    await _login(client, "docs.two@test.local")
    other_config = await _config(client, edition_id)
    assert other_config["registration"] is None
    stolen = await client.get(
        f"/api/v1/editions/{edition_id}/registration/documents/{document_id}/content"
    )
    assert stolen.status_code == 404

    # Oversized uploads are rejected before they reach storage.
    await _login(client, "docs.one@test.local")
    # The configured registration limit is 5 MB; 6 MB must be rejected by
    # the document validator, not silently accepted or cut off by middleware.
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (6 * 1024 * 1024) + b"IEND"
    too_big = await _upload(client, edition_id, "college_id", data=big)
    assert too_big.status_code in {413, 415}, too_big.text


@pytest.mark.asyncio
async def test_server_side_amount_and_duplicate_callback(
    client: AsyncClient, db_session
):
    edition_id = await _edition_id(client)
    await _login(client, "amount.test@test.local")
    config = await _config(client, edition_id)
    non_iste = next(item for item in config["categories"] if item["code"] == "non_iste")
    await _profile(client, edition_id, non_iste["id"], "amount.test@test.local")
    assert (await _upload(client, edition_id, "college_id")).status_code == 200
    assert (await _upload(client, edition_id, "photo")).status_code == 200

    # A manipulated amount in the request body is ignored: the endpoint has no
    # amount input and the fee comes from the category row.
    submitted = await client.post(
        f"/api/v1/editions/{edition_id}/registration/submit",
        json={"amountPaise": 1, "feePaise": 1},
    )
    assert submitted.status_code == 200, submitted.text
    payment = submitted.json()["data"]["payment"]
    assert payment["amountPaise"] == 60000

    order = await db_session.get(PaymentOrder, uuid.UUID(payment["orderId"]))
    assert order is not None and order.amount_paise == 60000

    first = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert first.status_code == 200, first.text
    duplicate = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert duplicate.status_code == 200
    count = (
        await db_session.execute(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.order_id == order.id
            )
        )
    ).scalar()
    assert count == 1

    other = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{uuid.uuid4()}/mock"
    )
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_user_edits_resubmission_and_category_change(client: AsyncClient):
    edition_id = await _edition_id(client)
    await _login(client, "edit.student@test.local")
    config = await _config(client, edition_id)
    iste = next(item for item in config["categories"] if item["code"] == "iste_member")
    non_iste = next(item for item in config["categories"] if item["code"] == "non_iste")
    poly = next(item for item in config["categories"] if item["code"] == "polytechnic")

    # Before payment the category can change and the fee follows the database.
    await _profile(client, edition_id, non_iste["id"], "edit.student@test.local")
    switched = await _profile(client, edition_id, poly["id"], "edit.student@test.local")
    assert switched["feePaise"] == 29900

    # Complete payment in the polytechnic category (the cheapest tier).
    await _profile(client, edition_id, poly["id"], "edit.student@test.local")
    assert (await _upload(client, edition_id, "college_id")).status_code == 200
    assert (await _upload(client, edition_id, "photo")).status_code == 200
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    payment = submitted.json()["data"]["payment"]
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text

    # Identity and fee cannot be rewritten after payment.
    locked = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={
            "categoryId": poly["id"],
            "fullName": "Someone Else",
            "email": "edit.student@test.local",
            "collegeName": "Another College",
            "course": "B.Tech",
        },
    )
    assert locked.status_code == 409, locked.text

    changed = await client.post(
        f"/api/v1/editions/{edition_id}/registration/category-change",
        json={"categoryId": non_iste["id"], "note": "I moved to a B.Tech programme."},
    )
    assert changed.status_code == 404, changed.text


async def _config_admin(client: AsyncClient, edition_id: str) -> dict:
    """Return this participant's registration through the admin detail endpoint."""
    listing = await client.get(f"/api/v1/editions/{edition_id}/admin/registration")
    assert listing.status_code == 200, listing.text
    rows = [r for r in listing.json()["data"] if r["email"] == "edit.student@test.local"]
    assert rows, listing.text
    return rows[0]


@pytest.mark.asyncio
async def test_rejection_is_final_until_the_desk_approves(client: AsyncClient):
    """A rejection revokes the registration; the attendee cannot re-upload into it."""
    edition_id = await _edition_id(client)
    await _login(client, "resubmit.student@test.local")
    registration = await _register_paid(
        client, edition_id, email="resubmit.student@test.local", category_code="polytechnic"
    )
    registration_id = registration["id"]

    await _login(client, "owner@parallax.local", role="admin")
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration_id}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_college_id",
            "reason": "Photo page is unreadable.",
            "initiateRefund": False,
        },
    )
    assert rejected.status_code == 200, rejected.text
    rejected_data = rejected.json()["data"]
    assert rejected_data["verificationStatus"] == "rejected"
    assert rejected_data["canResubmit"] is False
    assert rejected_data["canUpload"] is False
    assert rejected_data["compliance"] is None, "a rejection opens no 24-hour window"
    assert rejected_data["complianceDeadlineAt"] is None

    await _login(client, "resubmit.student@test.local")
    replacement = await _upload(
        client, edition_id, "college_id", filename="corrected.png"
    )
    assert replacement.status_code == 409, replacement.text
    resubmitted = await client.post(f"/api/v1/editions/{edition_id}/registration/resubmit")
    assert resubmitted.status_code == 409, resubmitted.text
    assert resubmitted.json()["error"]["code"] == "REJECTION_FINAL"
    assert resubmitted.json()["data"]["verificationStatus"] if "data" in resubmitted.json() else True

    # The only way back is the desk approving a rejection it made by mistake.
    await _login(client, "owner@parallax.local", role="admin")
    approved = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{registration_id}/decision",
        json={"decision": "approved"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["state"] == "approved"


@pytest.mark.asyncio
async def test_admin_configuration_persists_and_is_audited(client: AsyncClient):
    edition_id = await _edition_id(client)
    await _login(client, "owner@parallax.local", role="admin")
    original = (
        await client.get(f"/api/v1/editions/{edition_id}/admin/registration/config")
    ).json()["data"]
    try:
        response = await client.patch(
            f"/api/v1/editions/{edition_id}/admin/registration/config",
            json={
                "settings": {
                    "maxUploadBytes": 2_097_152,
                    "allowResubmission": False,
                    "notificationTemplates": {
                        "approved": "Custom approval for {registrationId}"
                    },
                },
                "categories": {
                    "non_iste": {
                        "feePaise": 65000,
                        "name": "B.Tech – Non-ISTE (updated)",
                        "requiredDocuments": [
                            {
                                "type": "college_id",
                                "label": "College ID card",
                                "required": True,
                            },
                            {
                                "type": "iste_card",
                                "label": "ISTE Card (optional)",
                                "required": False,
                            },
                        ],
                    },
                    "polytechnic": {"enabled": False},
                },
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        updated = next(c for c in data["categories"] if c["code"] == "non_iste")
        assert updated["feePaise"] == 65000
        # The printed-pass photo is always appended, even when a category is
        # configured with only the college ID.
        assert len(updated["requiredDocuments"]) == 3
        assert {doc["type"] for doc in updated["requiredDocuments"]} == {
            "college_id",
            "iste_card",
            "photo",
        }
        poly = next(c for c in data["categories"] if c["code"] == "polytechnic")
        assert poly["enabled"] is False
        assert data["registration"]["allowResubmission"] is False

        persisted = (
            await client.get(f"/api/v1/editions/{edition_id}/admin/registration/config")
        ).json()["data"]
        assert persisted["registration"]["maxUploadBytes"] == 2_097_152

        audit = (
            await client.get(f"/api/v1/editions/{edition_id}/admin/audit")
        ).json()["data"]
        actions = {row["action"] for row in audit}
        assert "college_registration.config_updated" in actions
        assert "college_registration.config_category_updated" in actions
        entry = next(
            row
            for row in audit
            if row["action"] == "college_registration.config_category_updated"
            and row["before"] and row["before"].get("code") == "non_iste"
        )
        assert entry["before"]["feePaise"] == 60000
        assert entry["after"]["feePaise"] == 65000
    finally:
        restore = await client.patch(
            f"/api/v1/editions/{edition_id}/admin/registration/config",
            json={
                "settings": {
                    "maxUploadBytes": 5_242_880,
                    "allowResubmission": True,
                    "notificationTemplates": {},
                },
                "categories": {
                    "non_iste": {
                        "feePaise": 60000,
                        "name": "B.Tech – Non-ISTE Member",
                        "requiredDocuments": [
                            {
                                "type": "college_id",
                                "label": "College / University ID card",
                                "required": True,
                            }
                        ],
                    },
                    "polytechnic": {"enabled": True},
                },
            },
        )
        assert restore.status_code == 200, restore.text


@pytest.mark.asyncio
async def test_participant_cannot_read_admin_registration_queue(client: AsyncClient):
    edition_id = await _edition_id(client)
    await _login(client, "not.staff@test.local")
    forbidden = await client.get(
        f"/api/v1/editions/{edition_id}/admin/registration"
    )
    assert forbidden.status_code == 403, forbidden.text
    config_forbidden = await client.get(
        f"/api/v1/editions/{edition_id}/admin/registration/config"
    )
    assert config_forbidden.status_code == 403, config_forbidden.text


@pytest.mark.asyncio
async def test_paid_registration_unlocks_pass_ticket_events_and_teams(
    client: AsyncClient,
):
    """A paid college registration must behave exactly like an active pass.

    This is the regression guard for the portal: buying the pass through the
    registration checkout has to issue an entry ticket, unlock included-event
    selection and allow team registration without a second purchase.
    """
    edition_id = await _edition_id(client)
    await _login(client, "unlock.flow@test.local")
    registration = await _register_paid(
        client, edition_id, email="unlock.flow@test.local", category_code="polytechnic"
    )
    assert registration["paymentStatus"] == "paid"

    # The registration is mirrored into an active convention pass.
    pass_view = (await client.get(f"/api/v1/editions/{edition_id}/pass")).json()["data"]
    assert pass_view["status"] == "active"

    # An entry ticket is issued for the pass.
    tickets = (await client.get(f"/api/v1/editions/{edition_id}/tickets")).json()["data"]
    assert any(ticket["kind"] == "pass" for ticket in tickets)

    # Receipt and pass card redirect to the frontend portal where they render interactively.
    receipt = await client.get(
        f"/api/v1/editions/{edition_id}/registration/receipt",
        follow_redirects=False,
    )
    assert receipt.status_code == 303
    assert receipt.headers["location"] == "/portal/registration"

    pass_card = await client.get(
        f"/api/v1/editions/{edition_id}/registration/pass-card",
        follow_redirects=False,
    )
    assert pass_card.status_code == 303
    assert pass_card.headers["location"] == "/portal/registration"

    # Included-event selection works with the activated pass.
    slug = (await client.get("/api/v1/public/editions/current")).json()["data"]["slug"]
    individual = [
        event
        for event in (
            await client.get(
                f"/api/v1/public/editions/{slug}/events?pageSize=100"
            )
        ).json()["data"]
        if event["format"] == "individual"
    ][:2]
    assert individual
    selection = await client.post(
        f"/api/v1/editions/{edition_id}/basket/events",
        json={"eventIds": [event["id"] for event in individual]},
    )
    assert selection.status_code == 200, selection.text
    basket = selection.json()["data"]
    assert len([l for l in basket["lines"] if l.get("action") == "create"]) == 2

    # Team registration works once the pass is active.
    team_event = next(
        event
        for event in (
            await client.get(
                f"/api/v1/public/editions/{slug}/events?format=team&pageSize=100"
            )
        ).json()["data"]
    )
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, edition_id, team_event["id"])
    created = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": team_event["id"], "name": "Unlock Squad"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["inviteCode"]


@pytest.mark.asyncio
async def test_rejected_pass_stays_dead_no_resurrection_or_booking(client: AsyncClient, db_session):
    """After a rejection the pass must stay dead: no resurrection on the next
    portal visit, no event selection, no add-on purchase, no team creation,
    and no document-correction detour that would un-reject the registration.
    """
    edition_id = await _edition_id(client)
    email = "rejected.gate@test.local"
    await _login(client, email)
    registration = await _register_paid(
        client, edition_id, email=email, category_code="polytechnic"
    )
    reg_id = registration["id"]

    slug = (await client.get("/api/v1/public/editions/current")).json()["data"]["slug"]
    events = (await client.get(f"/api/v1/public/editions/{slug}/events?pageSize=100")).json()["data"]
    individual = [e for e in events if e["format"] == "individual"]
    team_event = next(e for e in events if e["format"] == "team")

    # The attendee forms a team while their pass is still active.
    # Team creation needs an existing seat: buy one first.
    await buy_seat(client, edition_id, team_event["id"])
    created_team = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": team_event["id"], "name": "Doomed Squad"},
    )
    assert created_team.status_code == 200, created_team.text

    # Admin rejects WITHOUT refund.
    await _login(client, "owner@parallax.local", role="admin")
    rejected = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{reg_id}/decision",
        json={
            "decision": "rejected",
            "reasonCode": "invalid_document",
            "reason": "Proof unreadable.",
            "initiateRefund": False,
        },
    )
    assert rejected.status_code == 200, rejected.text

    # Back as the participant: the pass must not resurrect on read...
    await _login(client, email)
    pass_view = (await client.get(f"/api/v1/editions/{edition_id}/pass")).json()["data"]
    assert pass_view["status"] == "cancelled"

    # ...event selection is blocked...
    selection = await client.post(
        f"/api/v1/editions/{edition_id}/basket/events",
        json={"eventIds": [e["id"] for e in individual[:2]]},
    )
    assert selection.status_code == 409, selection.text
    assert selection.json()["error"]["code"] == "PASS_BLOCKED"

    # ...paid add-on booking is blocked...
    addon = await client.post(
        f"/api/v1/editions/{edition_id}/registrations",
        json={"eventIds": [individual[0]["id"]]},
    )
    assert addon.status_code == 409, addon.text
    assert addon.json()["error"]["code"] == "PASS_BLOCKED"

    # ...and team creation is blocked.
    team = await client.post(
        f"/api/v1/editions/{edition_id}/teams",
        json={"eventId": team_event["id"], "name": "Dead Pass Squad"},
    )
    assert team.status_code in (403, 409, 422), team.text

    # A team that existed BEFORE the rejection is disbanded: a rejected
    # attendee cannot stay on a roster.
    teams_after = (await client.get(f"/api/v1/editions/{edition_id}/teams")).json()["data"]
    assert all(t["status"] == "disbanded" for t in teams_after)

    # The desk cannot un-reject via "request documents".
    await _login(client, "owner@parallax.local", role="admin")
    docs = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{reg_id}/request-documents",
        json={"documents": ["college_id"], "message": "Send a clearer scan."},
    )
    assert docs.status_code == 409, docs.text
    assert docs.json()["error"]["code"] == "ALREADY_REJECTED"

    # Approving after a rejection is the legitimate undo path: it must bring
    # the pass back to active.
    approved = await client.post(
        f"/api/v1/editions/{edition_id}/admin/registration/{reg_id}/decision",
        json={"decision": "approved", "notes": "Reconsidered: document was legible."},
    )
    assert approved.status_code == 200, approved.text

    await _login(client, email)
    pass_view = (await client.get(f"/api/v1/editions/{edition_id}/pass")).json()["data"]
    assert pass_view["status"] == "active"
    selection = await client.post(
        f"/api/v1/editions/{edition_id}/basket/events",
        json={"eventIds": [e["id"] for e in individual[:2]]},
    )
    assert selection.status_code == 200, selection.text
