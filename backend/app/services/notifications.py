"""Operational alerts for the organising desk.

Everything that costs money or changes an entitlement is reported to the
configured Telegram chat: pass purchases, event add-on payments, college
registration payments, refunds, cancellations and privileged admin actions.

Messages are queued on the session and dispatched only after the surrounding
transaction commits, so an alert can never announce a write that rolled back.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.commerce import ConventionPass, Registration
from app.models.edition import ConventionEdition, Event
from app.models.registration import CollegeRegistration
from app.models.user import User
from app.services.telegram import send_telegram_message

logger = structlog.get_logger()

QUEUE_KEY = "px_telegram_notifications"

# Admin/action pairs that are worth waking someone up for. Participant self
# service actions are handled by the payment and cancellation hooks instead.
ADMIN_ACTION_TITLES: dict[str, str] = {
    "registration.force_cancelled": "Registration force-cancelled",
    # registration.refunded is covered by notify_refund, which has the amount
    # and the participant; alerting here too would double-post.
    "college_registration.approved": "College registration approved",
    "college_registration.rejected": "College registration rejected",
    "college_registration.refund_initiated": "College registration refund started",
    "college_registration.category_change_approved": "Category change approved",
    "college_registration.category_change_rejected": "Category change rejected",
    "college_registration.config_updated": "Registration desk configuration changed",
    "college_registration.category_updated": "Registration category changed",
    "user.status_updated": "Participant account status changed",
    "staff.invited": "Staff invitation sent",
    "membership.granted": "Staff access granted",
    "policy.created": "Pricing policy changed",
    "event.upserted": "Event updated",
    "announcement.upserted": "Announcement published",
    "announcement.deleted": "Announcement deleted",
}

_SAFE_AFTER_KEYS = (
    "reason",
    "reasonCode",
    "amountPaise",
    "status",
    "registrationNumber",
    "transactionId",
    "decision",
)

_tasks: set[asyncio.Task] = set()


# --------------------------------------------------------------------- helpers --


def _money(paise: int | None) -> str:
    value = int(paise or 0)
    return f"INR {value / 100:,.2f}"


def _short(value: Any, limit: int = 80) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def queue(
    db: AsyncSession,
    title: str,
    fields: list[tuple[str, Any]],
    *,
    tag: str = "ops",
) -> None:
    """Queue a message that is sent only if the current transaction commits."""
    pending = db.info.setdefault(QUEUE_KEY, [])
    pending.append((title, [(label, value) for label, value in fields], tag))


def _schedule(items: list[tuple[str, list[tuple[str, Any]], str]]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - only outside an async request
        logger.warning("telegram_queue_without_loop", count=len(items))
        return

    for title, fields, tag in items:
        task = loop.create_task(send_telegram_message(title, fields, tag=tag))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    items = session.info.pop(QUEUE_KEY, None)
    if items:
        _schedule(items)


@event.listens_for(Session, "after_rollback")
def _discard_after_rollback(session: Session) -> None:
    session.info.pop(QUEUE_KEY, None)


# ------------------------------------------------------------------ builders --


async def notify_order_paid(db: AsyncSession, order: Any) -> None:
    """Payment captured: pass, event add-ons or college registration."""
    try:
        user = await db.get(User, order.user_id)
        edition = await db.get(ConventionEdition, order.edition_id)

        fields: list[tuple[str, Any]] = [
            ("Attendee", (user.full_name if user else None) or "Unknown"),
            ("Email", user.email if user else None),
            ("Amount", _money(order.amount_paise)),
            ("Edition", edition.name if edition else None),
            ("Order", _short(getattr(order, "id", ""), 40)),
        ]

        purpose = str(getattr(order, "purpose", "") or "")

        if purpose == "pass":
            title = "🎟 Convention pass purchased"
            if order.linked_record_id:
                user_pass = await db.get(ConventionPass, order.linked_record_id)
                if user_pass is not None:
                    fields.append(("Pass price", _money(user_pass.price_paise)))
        elif purpose == "registration":
            title = "🎯 Event add-on paid"
            rows = list(
                (
                    await db.execute(
                        select(Registration, Event.title)
                        .join(Event, Event.id == Registration.event_id, isouter=True)
                        .where(Registration.order_id == order.id)
                    )
                ).all()
            )
            if rows:
                fields.append(
                    ("Events", ", ".join(title_text or "Event" for _, title_text in rows))
                )
                fields.append(("Seats", len(rows)))
        elif purpose in {"college_registration", "college_registration_delta"}:
            title = (
                "🎓 Category change paid"
                if purpose.endswith("_delta")
                else "🎓 College registration paid"
            )
            record = (
                await db.execute(
                    select(CollegeRegistration).where(
                        CollegeRegistration.order_id == order.id
                    )
                )
            ).scalar_one_or_none()
            if record is not None:
                fields.append(("Registration", record.registration_number or "pending"))
                fields.append(("Category", record.category_name))
                fields.append(("College", record.college_name))
        else:
            title = "💳 Payment received"

        queue(db, title, fields, tag="payment")
    except Exception as exc:  # pragma: no cover - notifications never block money
        logger.warning("telegram_payment_notify_failed", error=str(exc))


async def notify_free_registrations(db: AsyncSession, regs: list[Registration]) -> None:
    """Free add-ons are confirmed immediately; report them once, together."""
    if not regs:
        return
    try:
        first = regs[0]
        user = await db.get(User, first.user_id)
        edition = await db.get(ConventionEdition, first.edition_id)
        titles = []
        for reg in regs:
            event = await db.get(Event, reg.event_id)
            titles.append(event.title if event else "Event")
        queue(
            db,
            "🎯 Event registration confirmed",
            [
                ("Attendee", (user.full_name if user else None) or "Unknown"),
                ("Email", user.email if user else None),
                ("Events", ", ".join(titles)),
                ("Amount", "Free"),
                ("Edition", edition.name if edition else None),
            ],
            tag="registration",
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("telegram_registration_notify_failed", error=str(exc))


async def notify_registration_cancelled(
    db: AsyncSession,
    reg: Registration,
    *,
    actor: str,
    reason: str | None = None,
) -> None:
    try:
        user = await db.get(User, reg.user_id)
        event = await db.get(Event, reg.event_id)
        queue(
            db,
            "❌ Event registration cancelled",
            [
                ("Attendee", (user.full_name if user else None) or "Unknown"),
                ("Email", user.email if user else None),
                ("Event", event.title if event else None),
                ("Registration", reg.registration_number),
                ("By", actor),
                ("Reason", reason),
                ("Amount", _money(reg.fee_paise)),
            ],
            tag="registration",
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("telegram_cancel_notify_failed", error=str(exc))


async def notify_refund(
    db: AsyncSession,
    order: Any,
    *,
    amount_paise: int,
    reason_code: str,
    reason_note: str | None = None,
) -> None:
    try:
        user = await db.get(User, order.user_id)
        edition = await db.get(ConventionEdition, order.edition_id)
        queue(
            db,
            "💸 Refund processed",
            [
                ("Attendee", (user.full_name if user else None) or "Unknown"),
                ("Email", user.email if user else None),
                ("Amount", _money(amount_paise)),
                ("Order", _short(getattr(order, "id", ""), 40)),
                ("Purpose", order.purpose),
                ("Reason", reason_code),
                ("Note", reason_note),
                ("Edition", edition.name if edition else None),
            ],
            tag="refund",
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("telegram_refund_notify_failed", error=str(exc))


def queue_admin_action(
    db: AsyncSession,
    *,
    action: str,
    actor_role: str | None,
    resource_type: str | None,
    resource_id: uuid.UUID | str | None,
    after: dict[str, Any] | None = None,
) -> None:
    """Privileged office actions, one compact alert each."""
    if not actor_role or actor_role in {"participant"}:
        return
    title = ADMIN_ACTION_TITLES.get(action)
    if not title:
        return

    fields: list[tuple[str, Any]] = [
        ("By", actor_role),
        ("Resource", resource_type or "record"),
        ("ID", _short(resource_id, 40)),
    ]
    for key in _SAFE_AFTER_KEYS:
        if after and after.get(key) not in (None, ""):
            fields.append((key, _short(after[key], 120)))
    queue(db, f"🛠 {title}", fields, tag="admin")


__all__ = [
    "queue",
    "notify_order_paid",
    "notify_free_registrations",
    "notify_registration_cancelled",
    "notify_refund",
    "queue_admin_action",
]
