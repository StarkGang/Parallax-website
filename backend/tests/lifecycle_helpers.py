"""Shared fixtures and helpers for the registration / payment / refund / team suites.

The AUDIT/ folder this suite was specified against is no longer in the tree, so
the machine ids (M1-M30) and event ids (E1-E133) referenced in the task are
mapped here to the concrete columns and service functions they stand for:

    M1  CollegeRegistration        -> payment_status / verification_status /
                                      refund_status / category_change_status /
                                      overall_state() / registration_number /
                                      refund_amount_paise / additional_paid_paise
    M2  ConventionPass             -> status / price_paise
    M3  Registration (per event)   -> kind / status / fee_paise / cancelled_by
    M4  Team                       -> status / leader
    M5  TeamMember                 -> membership / is_leader
    M6  Ticket                     -> status
    M7  PaymentOrder               -> purpose / amount / status
    M8  PaymentTransaction         -> captured amount
    M9  Refund                     -> amount / status / gateway_refund_id
    M10 IncludedEventSelection     -> active included selections
    M12 RegistrationDocument       -> status
    M13 User.status
    M14 Session                    -> live sessions
    M24 RegistrationSettings.closes_at
    M26 EmailOutbox
    M28 RegistrationNotification

Everything here is data-driven: no names, colleges, events or prices are baked
in. Fees come from ``registration_categories`` and the pass price / included
event count come from the current ``EditionPolicy``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commerce import (
    ConventionPass,
    IncludedEventSelection,
    PaymentOrder,
    PaymentTransaction,
    Refund,
    Registration,
    Team,
    TeamMember,
    Ticket,
    AttendanceRecord,
    EmailOutbox,
)
from app.models.edition import ConventionEdition, EditionPolicy, Event
from app.models.registration import (
    CollegeRegistration,
    RegistrationCategory,
    RegistrationDocument,
    RegistrationNotification,
    RegistrationSettings,
)
from app.models.user import Session as UserSession, User

ADMIN_EMAIL = "owner@parallax.local"

# A tiny valid 1x1 PNG and a minimal PDF used for document uploads.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


# --------------------------------------------------------------------------- #
# Decision / flaw registry
# --------------------------------------------------------------------------- #
# Each entry is a behaviour the task calls out as ambiguous or unfair. A test
# that exercises one appends its id here so the end-of-run summary can print a
# "decisions needed" list. The registry is process-wide and reset by the
# reporting fixture in conftest-driven runs.
DECISIONS: list[dict[str, str]] = []


def flag_decision(code: str, summary: str) -> None:
    """Record an ambiguous/unfair behaviour for the end-of-run summary."""
    if not any(d["code"] == code for d in DECISIONS):
        DECISIONS.append({"code": code, "summary": summary})


# --------------------------------------------------------------------------- #
# Clock control
# --------------------------------------------------------------------------- #
# The services call ``datetime.now(UTC)`` directly (imported as
# ``from datetime import ... datetime``), so a single monkeypatch of the
# ``datetime`` name inside each service module freezes every deadline check.
# ``freeze`` is a small context manager installed per-test through a fixture.
_CLOCK_MODULES = (
    "app.services.college_registrations",
    "app.services.payments",
    "app.services.passes",
    "app.services.teams",
    "app.services.registrations",
    "app.services.events",
    "app.services.editions",
    "app.services.users",
    "app.api.v1.admin",
    "app.api.v1.admin_registration",
)


class FrozenClock:
    """A controllable ``datetime`` replacement with a movable ``now``."""

    def __init__(self, start: datetime | None = None):
        self.now = start or datetime.now(UTC)

    def __call__(self, *args, **kwargs):
        # Support datetime.now(tz), datetime.combine, etc. by delegating to the
        # real class but overriding now().
        return _FrozenDateTime(self.now)

    def set(self, value: datetime) -> None:
        self.now = value

    def advance(self, **timedelta_kwargs) -> datetime:
        self.now = self.now + timedelta(**timedelta_kwargs)
        return self.now


class _FrozenDateTime(datetime):
    """A datetime subclass whose ``now()`` always returns the frozen clock."""

    _frozen: datetime | None = None

    @classmethod
    def now(cls, tz=None):
        frozen = cls._frozen
        if frozen is None:
            return datetime.now(tz)
        if tz is None:
            return frozen.replace(tzinfo=None)
        return frozen.astimezone(tz)


@pytest.fixture
def clock(monkeypatch):
    """Install a movable clock across every service module.

    Usage::

        clock.set(datetime.now(UTC))
        ... run a request ...
        clock.advance(days=2)   # cross a deadline
    """
    frozen = FrozenClock()
    _FrozenDateTime._frozen = frozen.now

    class _Shim:
        """Wraps the real datetime module so ``datetime.now`` is frozen but the
        rest of the API (combine, fromisoformat, ...) is untouched."""

        def __getattr__(self, name):
            return getattr(datetime, name)

        def now(self, tz=None):
            return _FrozenDateTime.now(tz)

        def __call__(self, *args, **kwargs):
            return datetime(*args, **kwargs)

    import app.services.college_registrations as cr
    import app.services.payments as pay
    import app.services.passes as passes
    import app.services.teams as teams
    import app.services.registrations as regs
    import app.services.events as events
    import app.services.editions as editions
    import app.services.users as users
    import app.api.v1.admin as admin
    import app.api.v1.admin_registration as admin_reg

    shim = _Shim()
    for module in (cr, pay, passes, teams, regs, events, editions, users, admin, admin_reg):
        # Only patch modules that imported the name ``datetime`` directly.
        if hasattr(module, "datetime"):
            monkeypatch.setattr(module, "datetime", shim, raising=False)

    # Keep the frozen value in sync when the test moves the clock.
    original_set = frozen.set
    original_advance = frozen.advance

    def _set(value):
        original_set(value)
        _FrozenDateTime._frozen = value

    def _advance(**kwargs):
        result = original_advance(**kwargs)
        _FrozenDateTime._frozen = frozen.now
        return result

    frozen.set = _set  # type: ignore[method-assign]
    frozen.advance = _advance  # type: ignore[method-assign]

    yield frozen

    _FrozenDateTime._frozen = None


# --------------------------------------------------------------------------- #
# Factories (no hardcoded names / colleges / events / prices)
# --------------------------------------------------------------------------- #


@dataclass
class Ctx:
    """Per-test context: the seeded edition, its categories and current policy."""

    client: AsyncClient
    db: AsyncSession
    edition_id: str
    edition: ConventionEdition
    policy: EditionPolicy
    categories: list[RegistrationCategory]
    events: list[Event]

    @property
    def edition_uuid(self) -> uuid.UUID:
        return uuid.UUID(self.edition_id)


_counter = 0


def _unique_email(prefix: str = "user") -> str:
    global _counter
    _counter += 1
    return f"{prefix}.{uuid.uuid4().hex[:10]}.{_counter}@test.local"


async def edition_ctx(client: AsyncClient, db: AsyncSession) -> Ctx:
    """Resolve the seeded current edition, its categories, policy and events."""
    resp = await client.get("/api/v1/public/editions/current")
    assert resp.status_code == 200, resp.text
    edition_id = resp.json()["data"]["id"]
    edition = await db.get(ConventionEdition, uuid.UUID(edition_id))
    assert edition is not None
    policy = (
        await db.execute(
            select(EditionPolicy).where(
                EditionPolicy.edition_id == edition.id,
                EditionPolicy.is_current.is_(True),
            )
        )
    ).scalar_one()
    categories = list(
        (
            await db.execute(
                select(RegistrationCategory)
                .where(RegistrationCategory.edition_id == edition.id)
                .order_by(RegistrationCategory.display_order)
            )
        ).scalars()
    )
    events = list(
        (
            await db.execute(
                select(Event).where(Event.edition_id == edition.id)
            )
        ).scalars()
    )
    return Ctx(
        client=client,
        db=db,
        edition_id=edition_id,
        edition=edition,
        policy=policy,
        categories=categories,
        events=events,
    )


def category_by_code(ctx: Ctx, code: str) -> RegistrationCategory:
    return next(c for c in ctx.categories if c.code == code)


def cheapest_category(ctx: Ctx) -> RegistrationCategory:
    return min(ctx.categories, key=lambda c: c.fee_paise)


def priciest_category(ctx: Ctx) -> RegistrationCategory:
    return max(ctx.categories, key=lambda c: c.fee_paise)


def individual_events(ctx: Ctx, *, eligible_only: bool = False) -> list[Event]:
    rows = [e for e in ctx.events if e.format == "individual"]
    if eligible_only:
        rows = [e for e in rows if e.included_eligible]
    return sorted(rows, key=lambda e: (e.sort_order, e.starts_at))


def team_events(ctx: Ctx) -> list[Event]:
    return [e for e in ctx.events if e.format == "team"]


def event_by_slug(ctx: Ctx, slug: str) -> Event:
    return next(e for e in ctx.events if e.slug == slug)


def _random_profile(email: str) -> dict[str, Any]:
    """A profile with no fixed identity - all fields derived from the email."""
    local = email.split("@")[0]
    return {
        "fullName": local.title()[:150],
        "email": email,
        "phone": "9" + str(int(uuid.uuid4().int) % 10**9).zfill(9),
        "collegeName": f"College {uuid.uuid4().hex[:6]}",
        "course": "B.Tech",
        "branch": "Computer Science",
        "yearOfStudy": "3",
        "gender": "male",
        "foodPreference": "veg",
        "city": "Palakkad",
        "state": "Kerala",
    }


async def login(client: AsyncClient, email: str, role: str = "participant") -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "role": role, "fullName": email.split("@")[0].title()},
    )
    assert resp.status_code == 200, resp.text


class _FakeRequest:
    """Minimal request shim so ``create_session`` can run outside a real ASGI call."""

    def __init__(self, headers: dict | None = None):
        self.client = None
        self.headers = headers or {}


async def login_as_user(
    client: AsyncClient, db: AsyncSession, user: User, *, is_staff: bool = False
) -> None:
    """Create a server-side session for an arbitrary user and set the cookie.

    Direct login only grants admin to the configured owner email, so scenarios
    that need a *specific* role (e.g. an admin without ``finance.write``) build
    their user + membership directly and sign in through this helper.
    """
    from app.core.sessions import create_session, set_session_cookie

    # Clear any existing session cookie first.
    client.cookies.clear()
    _, token = await create_session(db, user, _FakeRequest(), is_staff=is_staff)
    await db.commit()
    settings_cookie = "px_session"
    # A host-only cookie (no domain) is sent to the test client's base_url.
    client.cookies.set(settings_cookie, token, path="/")


async def make_user_with_role(
    db: AsyncSession,
    ctx: Ctx,
    role: str,
    *,
    email: str | None = None,
    status: str = "active",
) -> User:
    """Create a user with a given edition role and return it."""
    from app.models.user import EditionMembership

    email = email or _unique_email(role)
    user = User(
        email=email,
        email_normalized=email,
        full_name=email.split("@")[0].title(),
        email_verified=True,
        status=status,
        google_sub=f"{role}-{uuid.uuid4().hex[:8]}",
    )
    db.add(user)
    await db.flush()
    db.add(
        EditionMembership(
            user_id=user.id,
            edition_id=ctx.edition_uuid,
            role=role,
            status="active",
        )
    )
    await db.commit()
    return user


async def login_admin(client: AsyncClient) -> None:
    await login(client, ADMIN_EMAIL, role="admin")


async def ensure_finance_admin(db: AsyncSession, ctx: Ctx) -> User:
    """Create a finance_admin membership user (needs finance.write) and return it.

    The seeded owner is a super_admin and already has finance.write; this is for
    scenarios that need a *second* actor who can move money but is not the owner.
    """
    email = _unique_email("finance")
    user = User(
        email=email,
        email_normalized=email,
        full_name="Finance Desk",
        email_verified=True,
        status="active",
        google_sub=f"fin-{uuid.uuid4().hex[:8]}",
    )
    db.add(user)
    await db.flush()
    from app.models.user import EditionMembership

    db.add(
        EditionMembership(
            user_id=user.id,
            edition_id=ctx.edition_uuid,
            role="finance_admin",
            status="active",
        )
    )
    await db.commit()
    return user


def _required_doc_types(category: RegistrationCategory) -> list[str]:
    types = [d.get("type") for d in (category.required_documents or []) if d.get("type")]
    # Every category implicitly carries the passport photo.
    if "photo" not in types:
        types.insert(0, "photo")
    return types


async def upload_documents(
    client: AsyncClient,
    edition_id: str,
    category: RegistrationCategory,
    *,
    only: list[str] | None = None,
) -> None:
    """Upload every required document for a category (real PNG/PDF bytes)."""
    doc_types = _required_doc_types(category)
    if only is not None:
        doc_types = [d for d in doc_types if d in only]
    for doc_type in doc_types:
        if doc_type == "photo":
            files = {"file": ("photo.png", PNG, "image/png")}
        else:
            files = {"file": (f"{doc_type}.pdf", PDF, "application/pdf")}
        resp = await client.post(
            f"/api/v1/editions/{edition_id}/registration/documents/{doc_type}",
            files=files,
        )
        assert resp.status_code == 200, resp.text


async def fill_profile(
    client: AsyncClient,
    edition_id: str,
    category: RegistrationCategory,
    email: str,
    *,
    college_name: str | None = None,
) -> dict:
    profile = _random_profile(email)
    if college_name:
        profile["collegeName"] = college_name
    resp = await client.put(
        f"/api/v1/editions/{edition_id}/registration/profile",
        json={"categoryId": str(category.id), **profile},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def submit_and_pay_mock(
    client: AsyncClient, edition_id: str
) -> tuple[dict, dict]:
    """Submit for payment and complete it through the mock pay path (E6/E7)."""
    submitted = await client.post(f"/api/v1/editions/{edition_id}/registration/submit")
    assert submitted.status_code == 200, submitted.text
    payment = submitted.json()["data"]["payment"]
    assert payment is not None, submitted.text
    paid = await client.post(
        f"/api/v1/editions/{edition_id}/registration/payments/{payment['orderId']}/mock"
    )
    assert paid.status_code == 200, paid.text
    return payment, paid.json()["data"]["registration"]


async def register_paid(
    client: AsyncClient,
    ctx: Ctx,
    email: str,
    category: RegistrationCategory | None = None,
) -> dict:
    """Full participant happy path up to a paid, unverified registration."""
    if category is None:
        category = cheapest_category(ctx)
    await login(client, email)
    await fill_profile(client, ctx.edition_id, category, email)
    await upload_documents(client, ctx.edition_id, category)
    _, registration = await submit_and_pay_mock(client, ctx.edition_id)
    return registration


async def admin_approve(client: AsyncClient, ctx: Ctx, registration_id: str, notes: str | None = None) -> dict:
    resp = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{registration_id}/decision",
        json={"decision": "approved", "notes": notes},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def admin_reject(
    client: AsyncClient,
    ctx: Ctx,
    registration_id: str,
    *,
    reason_code: str = "invalid_college_id",
    reason: str | None = "Document could not be verified.",
    initiate_refund: bool = True,
) -> dict:
    resp = await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{registration_id}/decision",
        json={
            "decision": "rejected",
            "reasonCode": reason_code,
            "reason": reason,
            "initiateRefund": initiate_refund,
        },
    )
    return resp


async def admin_request_documents(
    client: AsyncClient,
    ctx: Ctx,
    registration_id: str,
    documents: list[str],
    message: str = "Please re-upload a clearer document.",
) -> dict:
    return await client.post(
        f"/api/v1/editions/{ctx.edition_id}/admin/registration/{registration_id}/request-documents",
        json={"documents": documents, "message": message},
    )


async def registration_row(db: AsyncSession, ctx: Ctx, email: str) -> CollegeRegistration | None:
    return (
        await db.execute(
            select(CollegeRegistration)
            .where(
                CollegeRegistration.edition_id == ctx.edition_uuid,
                CollegeRegistration.email == email,
            )
            .execution_options(populate_existing=True)
        )
    ).scalars().first()


async def registration_row_for_user(db: AsyncSession, ctx: Ctx, user_id: uuid.UUID) -> CollegeRegistration | None:
    return (
        await db.execute(
            select(CollegeRegistration)
            .where(
                CollegeRegistration.edition_id == ctx.edition_uuid,
                CollegeRegistration.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
    ).scalars().first()


# --------------------------------------------------------------------------- #
# Webhook signing (real HMAC over the raw body)
# --------------------------------------------------------------------------- #

WEBHOOK_SECRET = "test_webhook_secret_at_least_16_bytes"


def sign_webhook(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def webhook_body(event: str, payload: dict, event_id: str | None = None) -> bytes:
    envelope = {
        "event": event,
        "event_id": event_id or f"evt_{uuid.uuid4().hex[:12]}",
        "payload": payload,
    }
    return json.dumps(envelope, separators=(",", ":")).encode()


async def post_webhook(client: AsyncClient, body: bytes, signature: str | None = None) -> Any:
    return await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": signature if signature is not None else sign_webhook(body),
            "Content-Type": "application/json",
        },
    )


def payment_captured_event(order_gateway_id: str, payment_id: str, amount_paise: int) -> bytes:
    return webhook_body(
        "payment.captured",
        {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_gateway_id,
                    "amount": amount_paise,
                    "status": "captured",
                }
            }
        },
    )


def refund_event(gateway_refund_id: str, *, failed: bool = False) -> bytes:
    return webhook_body(
        "refund.failed" if failed else "refund.processed",
        {"refund": {"entity": {"id": gateway_refund_id, "status": "failed" if failed else "processed"}}},
    )


def enable_payments(monkeypatch) -> None:
    """Flip ``payments_enabled`` on for the services that read it at call time.

    The test env runs with payments disabled (mock pay paths only). To exercise a
    real gateway code path (e.g. a failing gateway refund) a test enables
    payments *after* it has already registered and paid through the mock path, so
    no real network call is made for order creation.
    """
    from app.core.config import get_settings

    fake = get_settings().model_copy(update={"payments_enabled": True})

    import app.services.college_registrations as cr
    import app.services.payments as pay

    monkeypatch.setattr(cr, "get_settings", lambda: fake, raising=False)
    monkeypatch.setattr(pay, "get_settings", lambda: fake, raising=False)


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


@dataclass
class Snapshot:
    user: dict
    registration: dict | None
    pass_: dict | None
    event_registrations: list[dict]
    included: list[dict]
    tickets: list[dict]
    teams: list[dict]
    orders: list[dict]
    transactions: list[dict]
    refunds: list[dict]
    money: dict
    notifications: list[dict]
    emails: list[dict]

    def __str__(self) -> str:
        return (
            "SNAPSHOT\n"
            f"  user: {self.user}\n"
            f"  registration: {self._fmt(self.registration)}\n"
            f"  pass: {self._fmt(self.pass_)}\n"
            f"  event_registrations: {self._fmt_list(self.event_registrations)}\n"
            f"  included: {self._fmt_list(self.included)}\n"
            f"  tickets: {self._fmt_list(self.tickets)}\n"
            f"  teams: {self._fmt_list(self.teams)}\n"
            f"  orders: {self._fmt_list(self.orders)}\n"
            f"  transactions: {self._fmt_list(self.transactions)}\n"
            f"  refunds: {self._fmt_list(self.refunds)}\n"
            f"  money: {self.money}\n"
            f"  notifications: {[n['kind'] for n in self.notifications]}\n"
            f"  emails: {[e['template'] for e in self.emails]}"
        )

    @staticmethod
    def _fmt(value: dict | None) -> str:
        return "None" if value is None else json.dumps(value, default=str, sort_keys=True)

    @staticmethod
    def _fmt_list(values: list[dict]) -> str:
        return "[" + ", ".join(json.dumps(v, default=str, sort_keys=True) for v in values) + "]"


async def snapshot(
    db: AsyncSession,
    ctx: Ctx,
    user_id: uuid.UUID,
    *,
    email: str | None = None,
) -> Snapshot:
    # Read through a brand-new session so the snapshot always reflects the
    # freshly committed state. The test's own ``db`` session caches ORM objects
    # (expire_on_commit=False) and would otherwise return stale copies after the
    # HTTP app writes through its own session. A separate session also leaves
    # ``ctx``'s loaded objects untouched for reuse across loop iterations.
    from app.db.session import get_session_factory

    async with get_session_factory()() as fresh_db:
        return await _snapshot_impl(fresh_db, ctx, user_id, email=email)


async def _snapshot_impl(
    db: AsyncSession,
    ctx: Ctx,
    user_id: uuid.UUID,
    *,
    email: str | None = None,
) -> Snapshot:
    """Capture the full state the task asks to print after every step."""
    from app.services.college_registrations import overall_state

    edition_uuid = ctx.edition_uuid

    # User + live sessions
    user = await db.get(User, user_id)
    live_sessions = len(
        (
            await db.execute(
                select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.revoked_at.is_(None),
                )
            )
        ).scalars().all()
    )
    user_view = {
        "status": user.status if user else None,
        "live_sessions": live_sessions,
    }

    # Registration (M1)
    reg = await registration_row_for_user(db, ctx, user_id)
    registration_view: dict | None = None
    if reg is not None:
        registration_view = {
            "payment_status": reg.payment_status,
            "verification_status": reg.verification_status,
            "refund_status": reg.refund_status,
            "category_change_status": reg.category_change_status,
            "state": overall_state(reg),
            "registration_number": reg.registration_number,
            "refund_amount_paise": int(reg.refund_amount_paise or 0),
            "additional_paid_paise": int(reg.additional_paid_paise or 0),
            "fee_paise": int(reg.fee_paise or 0),
        }

    # Pass (M2)
    user_pass = (
        await db.execute(
            select(ConventionPass)
            .where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition_uuid,
            )
            .order_by(ConventionPass.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    pass_view: dict | None = None
    if user_pass is not None:
        pass_view = {
            "status": user_pass.status,
            "price_paise": int(user_pass.price_paise or 0),
            "policy_version": user_pass.policy_version,
        }

    # Event registrations (M3)
    event_regs = list(
        (
            await db.execute(
                select(Registration)
                .where(
                    Registration.user_id == user_id,
                    Registration.edition_id == edition_uuid,
                )
                .order_by(Registration.created_at)
            )
        ).scalars()
    )
    events_by_id = {e.id: e for e in ctx.events}
    event_registrations = [
        {
            "event": events_by_id[r.event_id].title if r.event_id in events_by_id else None,
            "event_slug": events_by_id[r.event_id].slug if r.event_id in events_by_id else None,
            "kind": r.kind,
            "status": r.status,
            "fee_paise": int(r.fee_paise or 0),
            "cancelled_by": r.cancelled_by,
            "cancellation_reason": r.cancellation_reason,
        }
        for r in event_regs
    ]

    # Included selections (M10)
    included = []
    if user_pass is not None:
        included = [
            {
                "event_slug": events_by_id[s.event_id].slug if s.event_id in events_by_id else None,
                "status": s.status,
                "value_paise": int(s.base_value_paise_snapshot or 0),
            }
            for s in (
                await db.execute(
                    select(IncludedEventSelection).where(
                        IncludedEventSelection.pass_id == user_pass.id
                    )
                )
            ).scalars()
        ]

    # Tickets (M6)
    tickets = [
        {
            "kind": "pass" if t.pass_id else "registration",
            "status": t.status,
            "event": (
                events_by_id[
                    (await db.get(Registration, t.registration_id)).event_id
                ].title
                if t.registration_id
                and (reg_row := await db.get(Registration, t.registration_id))
                and reg_row.event_id in events_by_id
                else None
            ),
        }
        for t in (
            await db.execute(
                select(Ticket).where(
                    Ticket.user_id == user_id,
                    Ticket.edition_id == edition_uuid,
                )
            )
        ).scalars()
    ]

    # Teams (M4/M5)
    team_rows = list(
        (
            await db.execute(
                select(Team).where(
                    Team.edition_id == edition_uuid,
                    Team.leader_id == user_id,
                )
            )
        ).scalars()
    )
    # Include teams the user is merely a member of.
    member_team_ids = list(
        (
            await db.execute(
                select(TeamMember.team_id).where(TeamMember.user_id == user_id)
            )
        ).scalars()
    )
    if member_team_ids:
        extra = list(
            (
                await db.execute(
                    select(Team).where(
                        Team.id.in_(member_team_ids),
                        Team.edition_id == edition_uuid,
                    )
                )
            ).scalars()
        )
        seen = {t.id for t in team_rows}
        team_rows.extend(t for t in extra if t.id not in seen)
    teams = []
    for t in team_rows:
        members = list(
            (
                await db.execute(
                    select(TeamMember, User)
                    .join(User, TeamMember.user_id == User.id)
                    .where(TeamMember.team_id == t.id)
                    .order_by(TeamMember.created_at)
                )
            ).all()
        )
        teams.append(
            {
                "team": t.name,
                "event": events_by_id[t.event_id].slug if t.event_id in events_by_id else None,
                "status": t.status,
                "leader": next(
                    (m_u.email for m_m, m_u in members if m_m.is_leader),
                    None,
                ),
                "members": sorted(
                    m_u.email or str(m_u.id) for m_m, m_u in members
                ),
            }
        )

    # Orders (M7)
    orders = [
        {
            "purpose": o.purpose,
            "amount_paise": int(o.amount_paise or 0),
            "status": o.status,
        }
        for o in (
            await db.execute(
                select(PaymentOrder)
                .where(
                    PaymentOrder.user_id == user_id,
                    PaymentOrder.edition_id == edition_uuid,
                )
                .order_by(PaymentOrder.created_at)
            )
        ).scalars()
    ]
    order_ids = list(
        (
            await db.execute(
                select(PaymentOrder.id).where(
                    PaymentOrder.user_id == user_id,
                    PaymentOrder.edition_id == edition_uuid,
                )
            )
        ).scalars()
    )

    # Transactions (M8)
    transactions = []
    if order_ids:
        transactions = [
            {
                "order_id": str(tx.order_id),
                "amount_paise": int(tx.amount_paise or 0),
                "status": tx.status,
            }
            for tx in (
                await db.execute(
                    select(PaymentTransaction)
                    .where(PaymentTransaction.order_id.in_(order_ids))
                    .order_by(PaymentTransaction.created_at)
                )
            ).scalars()
        ]

    # Refunds (M9)
    refunds = []
    if order_ids:
        refunds = [
            {
                "order_id": str(r.order_id),
                "amount_paise": int(r.amount_paise or 0),
                "status": r.status,
                "gateway_refund_id": r.gateway_refund_id,
            }
            for r in (
                await db.execute(
                    select(Refund)
                    .where(Refund.order_id.in_(order_ids))
                    .order_by(Refund.created_at)
                )
            ).scalars()
        ]

    # Money
    collected = sum(int(o["amount_paise"]) for o in orders if o["status"] in ("paid", "refunded"))
    captured = sum(int(t["amount_paise"]) for t in transactions if t["status"] == "captured")
    refunded = sum(int(r["amount_paise"]) for r in refunds if r["status"] == "processed")
    money = {
        "collected": collected,
        "captured": captured,
        "refunded": refunded,
        "net_kept": collected - refunded,
    }

    # Notifications (M28)
    notifications = [
        {"kind": n.kind, "title": n.title}
        for n in (
            await db.execute(
                select(RegistrationNotification)
                .where(
                    RegistrationNotification.user_id == user_id,
                    RegistrationNotification.edition_id == edition_uuid,
                )
                .order_by(RegistrationNotification.created_at)
            )
        ).scalars()
    ]

    # Email outbox rows (M26) created for this user
    email_filter = email or (user.email if user else None)
    emails = []
    if email_filter:
        emails = [
            {"template": e.template, "status": e.status}
            for e in (
                await db.execute(
                    select(EmailOutbox)
                    .where(EmailOutbox.recipient == email_filter)
                    .order_by(EmailOutbox.scheduled_at)
                )
            ).scalars()
        ]

    return Snapshot(
        user=user_view,
        registration=registration_view,
        pass_=pass_view,
        event_registrations=event_registrations,
        included=included,
        tickets=tickets,
        teams=teams,
        orders=orders,
        transactions=transactions,
        refunds=refunds,
        money=money,
        notifications=notifications,
        emails=emails,
    )


# --------------------------------------------------------------------------- #
# Invariants
# --------------------------------------------------------------------------- #


class InvariantFailure(AssertionError):
    def __init__(self, name: str, detail: str):
        self.name = name
        super().__init__(f"[{name}] {detail}")


def _fail(name: str, detail: str) -> None:
    raise InvariantFailure(name, detail)


def check_invariants(
    db: AsyncSession,
    ctx: Ctx,
    user_id: uuid.UUID,
    snap: Snapshot,
) -> None:
    """Run I1-I8. Raises InvariantFailure with the invariant name on breach.

    These invariants are intentionally run on *snapshot* data plus a few direct
    DB reads, so a step that corrupts state is caught immediately and names the
    rule it broke. The DB-backed check (I5) is run by ``assert_invariants``
    which is async; here we only run the snapshot-only checks.
    """
    _i1_orders_match_captured(snap)
    _i2_refunds_within_bounds(snap)
    _i3_payment_status_refunded(snap)
    _i4_cancelled_pass_teardown(snap)
    _i6_refund_rows_agree(snap)
    _i7_registration_number_iff_paid(snap)
    _i8_checkin_ready(snap)


async def check_invariants_async(
    db: AsyncSession,
    ctx: Ctx,
    user_id: uuid.UUID,
    snap: Snapshot,
) -> None:
    """Run all invariants I1-I8, including the DB-backed I5."""
    check_invariants(db, ctx, user_id, snap)
    await _i5_one_active_pass(db, ctx, user_id)


def _i1_orders_match_captured(snap: Snapshot) -> None:
    paid_orders = sum(
        int(o["amount_paise"]) for o in snap.orders if o["status"] in ("paid", "refunded")
    )
    captured = sum(
        int(t["amount_paise"]) for t in snap.transactions if t["status"] == "captured"
    )
    if paid_orders != captured:
        _fail(
            "I1",
            f"paid orders total {paid_orders} but captured transactions total {captured}",
        )
    if snap.money["collected"] != captured:
        _fail(
            "I1",
            f"money.collected {snap.money['collected']} != captured {captured}",
        )


def _i2_refunds_within_bounds(snap: Snapshot) -> None:
    collected = snap.money["collected"]
    refunded = snap.money["refunded"]
    if refunded > collected:
        _fail("I2", f"refunded {refunded} exceeds collected {collected}")
    # No single refund exceeds the order it belongs to.
    order_amounts = {o_order_id: None for o_order_id in ()}
    amounts_by_order: dict[str, int] = {}
    for o in snap.orders:
        amounts_by_order[str(o.get("order_id", ""))] = int(o["amount_paise"])
    # Reconstruct order ids from transactions/refunds when present.
    for r in snap.refunds:
        oid = r.get("order_id")
        # The snapshot orders don't expose ids directly; use collected as the
        # global cap and the per-order cap via refunds list where order_id maps
        # to a transaction's order.
    # Per-order cap using refunds grouped by order_id against transaction amounts.
    tx_by_order: dict[str, int] = {}
    for t in snap.transactions:
        oid = t.get("order_id")
        if oid:
            tx_by_order[oid] = tx_by_order.get(oid, 0) + int(t["amount_paise"])
    refund_by_order: dict[str, int] = {}
    for r in snap.refunds:
        oid = r.get("order_id")
        if oid and r["status"] in ("pending", "processing", "processed"):
            refund_by_order[oid] = refund_by_order.get(oid, 0) + int(r["amount_paise"])
    for oid, refunded_total in refund_by_order.items():
        paid_for_order = tx_by_order.get(oid, 0)
        if paid_for_order and refunded_total > paid_for_order:
            _fail(
                "I2",
                f"refunds on order {oid} total {refunded_total} exceed paid {paid_for_order}",
            )


def _i3_payment_status_refunded(snap: Snapshot) -> None:
    reg = snap.registration
    if reg is None:
        return
    if reg["payment_status"] == "refunded":
        # The registration's own collected = its base fee + any paid delta. This
        # is NOT the user's total collected, which also includes separate add-on
        # orders that are refunded on their own.
        reg_collected = int(reg["fee_paise"]) + int(reg["additional_paid_paise"])
        if reg["refund_amount_paise"] != reg_collected:
            _fail(
                "I3",
                f"payment_status=refunded but refund_amount_paise "
                f"{reg['refund_amount_paise']} != registration collected {reg_collected}",
            )


def _i4_cancelled_pass_teardown(snap: Snapshot) -> None:
    pass_status = (snap.pass_ or {}).get("status")
    reg = snap.registration or {}
    dead = (
        pass_status in ("cancelled", "refunded", "revoked")
        or reg.get("payment_status") == "refunded"
        or reg.get("verification_status") == "rejected"
    )
    if not dead:
        return
    live_events = [
        r for r in snap.event_registrations if r["status"] in ("confirmed", "reserved")
    ]
    active_tickets = [t for t in snap.tickets if t["status"] in ("active", "valid")]
    active_seats = [t for t in snap.teams if t["status"] in ("active", "forming", "locked")]
    active_included = [i for i in snap.included if i["status"] == "active"]
    if live_events:
        _fail("I4", f"dead pass but live event registrations remain: {live_events}")
    if active_tickets:
        _fail("I4", f"dead pass but active tickets remain: {active_tickets}")
    if active_seats:
        _fail("I4", f"dead pass but active team seats remain: {active_seats}")
    if active_included:
        _fail("I4", f"dead pass but active included selections remain: {active_included}")


async def _i5_one_active_pass(db: AsyncSession, ctx: Ctx, user_id: uuid.UUID) -> None:
    count = len(
        (
            await db.execute(
                select(ConventionPass).where(
                    ConventionPass.user_id == user_id,
                    ConventionPass.edition_id == ctx.edition_uuid,
                    ConventionPass.status == "active",
                )
            )
        ).scalars().all()
    )
    if count > 1:
        _fail("I5", f"{count} active passes for one user/edition")


def _i6_refund_rows_agree(snap: Snapshot) -> None:
    reg = snap.registration
    if reg is None:
        return
    # refund rows use "processed" / "failed" / "pending" / "processing"; the
    # registration's refund_status uses "completed" / "failed" / "initiated" /
    # "processing" / "not_initiated". Compare them correctly.
    rows = snap.refunds
    processed = [r for r in rows if r["status"] == "processed"]
    failed = [r for r in rows if r["status"] == "failed"]
    pending = [r for r in rows if r["status"] in ("pending", "processing")]
    reg_status = reg["refund_status"]
    if reg_status == "completed" and not processed:
        _fail("I6", "registration refund_status=completed but no processed refund row")
    # A gateway can fail before any refund row is written (refund_status=failed,
    # no rows); that is a data gap worth reporting, not an invariant breach.
    if processed and reg_status not in ("completed", "processing", "initiated"):
        _fail(
            "I6",
            f"processed refund rows exist but registration refund_status={reg_status}",
        )


def _i7_registration_number_iff_paid(snap: Snapshot) -> None:
    reg = snap.registration
    if reg is None:
        return
    has_number = bool(reg["registration_number"])
    ever_paid = snap.money["collected"] > 0 or reg["payment_status"] in ("paid", "refunded")
    if has_number and not ever_paid:
        _fail("I7", "registration_number present but no payment was ever completed")
    if ever_paid and not has_number:
        _fail("I7", "payment completed but registration_number is missing")


def _i8_checkin_ready(snap: Snapshot) -> None:
    """A user who can check in at the door must have a consistent setup.

    The door refuses entry when verification is rejected/resubmission even if the
    pass and ticket are still active (that refusal is asserted directly by the
    check-in tests). The snapshot-level guarantee is the converse: an account that
    is NOT active (suspended) must never simultaneously hold an active pass and an
    active ticket, because that combination would otherwise admit entry.
    """
    if snap.user["status"] != "active":
        pass_active = (snap.pass_ or {}).get("status") == "active"
        active_ticket = any(t["status"] in ("active", "valid") for t in snap.tickets)
        if pass_active and active_ticket:
            _fail(
                "I8",
                f"account status={snap.user['status']} holds an active pass and "
                "active ticket (would be admitted at the door)",
            )


async def assert_invariants(
    db: AsyncSession,
    ctx: Ctx,
    user_id: uuid.UUID,
    *,
    email: str | None = None,
    label: str = "",
) -> Snapshot:
    """Snapshot + invariant check in one call; prints both."""
    snap = await snapshot(db, ctx, user_id, email=email)
    print(f"\n=== {'STEP: ' + label if label else 'SNAPSHOT'} ===")
    print(snap)
    await check_invariants_async(db, ctx, user_id, snap)
    print("invariants: OK")
    return snap