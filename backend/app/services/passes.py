"""Convention passes, bundled included selections and state transitions."""

import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models.commerce import (
    ConventionPass,
    IncludedEventSelection,
    PaymentOrder,
    Registration,
)
from app.models.edition import ConventionEdition, EditionPolicy, Event
from app.schemas.participant import SelectedEvent, SelectionState
from app.services.editions import aware


async def get_pass(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> ConventionPass | None:
    return (
        await db.execute(
            select(ConventionPass).where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition_id,
            )
        )
    ).scalar_one_or_none()


async def selections_for(db: AsyncSession, pass_id: uuid.UUID) -> list[uuid.UUID]:
    rows = list(
        (
            await db.execute(
                select(IncludedEventSelection.event_id).where(
                    IncludedEventSelection.pass_id == pass_id
                )
            )
        ).scalars()
    )
    return rows


def _count_valid(mode: str, count: int, required: int) -> bool:
    return count == required if mode == "exact" else count <= required


def _message(mode: str, count: int, required: int, cap_paise: int | None, value: int, cap_inclusive: bool) -> str | None:
    if _count_valid(mode, count, required):
        if cap_paise is None:
            return None
        within = value <= cap_paise if cap_inclusive else value < cap_paise
        if within:
            return None
        return "Those choices exceed the included-event value cap."
    if mode == "exact":
        return f"Select exactly {required} included event{'s' if required != 1 else ''}."
    return f"Select up to {required} included event{'s' if required != 1 else ''}."


async def selection_state(
    db: AsyncSession, user_pass: ConventionPass, policy: EditionPolicy
) -> SelectionState:
    chosen_ids = set(await selections_for(db, user_pass.id))

    events = list(
        (
            await db.execute(
                select(Event)
                .where(
                    Event.edition_id == user_pass.edition_id,
                    Event.included_eligible.is_(True),
                    Event.status.in_(["published", "open"]),
                )
                .order_by(Event.sort_order, Event.starts_at)
            )
        ).scalars()
    )

    selected_events = []
    total_val = 0
    count = 0
    for e in events:
        is_sel = e.id in chosen_ids
        if is_sel:
            count += 1
            total_val += e.base_value_paise
        selected_events.append(
            SelectedEvent(
                event_id=e.id,
                slug=e.slug,
                title=e.title,
                category=e.slug,
                format=e.format,
                base_value_paise=e.base_value_paise,
                addon_price_paise=e.addon_price_paise,
                starts_at=aware(e.starts_at),
                accent=e.accent,
                selected=is_sel,
                status=e.status,
            )
        )

    deadline = aware(policy.selection_change_deadline)
    locked = bool(deadline and datetime.now(UTC) > deadline)
    mode = policy.included_selection_mode or "exact"
    cap_paise = policy.included_value_cap_paise
    cap_inclusive = bool(policy.cap_inclusive)
    required = policy.included_event_count

    within_cap = cap_paise is None or (
        total_val <= cap_paise if cap_inclusive else total_val < cap_paise
    )
    valid = _count_valid(mode, count, required) and within_cap and not locked

    return SelectionState(
        pass_id=user_pass.id,
        pass_status=user_pass.status,
        selections=selected_events,
        count=count,
        value_paise=total_val,
        cap_paise=cap_paise,
        remaining_paise=(cap_paise - total_val) if cap_paise is not None else None,
        required_count=required,
        up_to=mode == "up_to",
        mode=mode,
        cap_inclusive=cap_inclusive,
        valid=valid,
        deadline=deadline,
        locked=locked,
        message=(
            "Included selections are locked after the change deadline."
            if locked
            else _message(mode, count, required, cap_paise, total_val, cap_inclusive)
        ),
    )


async def set_selections(
    db: AsyncSession,
    request: Request,
    user_pass: ConventionPass,
    event_ids: list[uuid.UUID],
    policy: EditionPolicy,
) -> SelectionState:
    deadline = aware(policy.selection_change_deadline)
    if deadline and datetime.now(UTC) > deadline:
        raise Conflict("The deadline to change included event selections has passed.")

    unique_ids = list(dict.fromkeys(event_ids))
    if len(unique_ids) != len(event_ids):
        raise ValidationFailed("The same event was selected twice.")

    mode = policy.included_selection_mode or "exact"
    required = policy.included_event_count
    if not _count_valid(mode, len(unique_ids), required):
        raise ValidationFailed(
            f"Select exactly {required} included events."
            if mode == "exact"
            else f"Select up to {required} included events."
        )

    events: list[Event] = []
    if unique_ids:
        events = list(
            (
                await db.execute(
                    select(Event).where(
                        Event.id.in_(unique_ids),
                        Event.edition_id == user_pass.edition_id,
                    )
                )
            ).scalars()
        )
        if len(events) != len(unique_ids):
            raise NotFound("One or more events were not found.")
        for event in events:
            if not event.included_eligible or event.status not in ("published", "open"):
                raise ValidationFailed(f"'{event.title}' is not eligible for included selection.")

    total = sum(e.base_value_paise for e in events)
    if policy.included_value_cap_paise is not None:
        within = (
            total <= policy.included_value_cap_paise
            if policy.cap_inclusive
            else total < policy.included_value_cap_paise
        )
        if not within:
            raise ValidationFailed("Those choices exceed the included-event value cap.")

    await db.execute(
        delete(IncludedEventSelection).where(IncludedEventSelection.pass_id == user_pass.id)
    )

    snapshots = {e.id: e.base_value_paise for e in events}
    for eid in unique_ids:
        db.add(
            IncludedEventSelection(
                pass_id=user_pass.id,
                event_id=eid,
                base_value_paise_snapshot=snapshots.get(eid, 0),
                status="active",
            )
        )

    await db.flush()
    await sync_included_registrations(db, user_pass, unique_ids)
    return await selection_state(db, user_pass, policy)


async def sync_included_registrations(
    db: AsyncSession, user_pass: ConventionPass, event_ids: list[uuid.UUID]
) -> None:
    """Keep confirmed included registrations aligned with the saved selection."""
    if user_pass.status != "active":
        return

    keep = set(event_ids)
    existing = list(
        (
            await db.execute(
                select(Registration).where(
                    Registration.user_id == user_pass.user_id,
                    Registration.edition_id == user_pass.edition_id,
                    Registration.kind == "included",
                )
            )
        ).scalars()
    )
    by_event = {row.event_id: row for row in existing}

    for event_id, row in by_event.items():
        if event_id not in keep and row.status != "cancelled":
            row.status = "cancelled"
            row.cancelled_at = datetime.now(UTC)

    for eid in keep:
        if eid in by_event:
            continue
        db.add(
            Registration(
                edition_id=user_pass.edition_id,
                user_id=user_pass.user_id,
                event_id=eid,
                kind="included",
                fee_paise=0,
                status="confirmed",
                registration_number=f"INC-{uuid.uuid4().hex[:8].upper()}",
            )
        )
    await db.flush()


async def create_pass_order(
    db: AsyncSession,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    policy: EditionPolicy,
) -> tuple[ConventionPass, PaymentOrder]:
    existing = await get_pass(db, user_id, edition.id)
    if existing and existing.status == "active":
        raise Conflict("You already have an active pass for this edition.")

    if existing is None:
        existing = ConventionPass(
            edition_id=edition.id,
            user_id=user_id,
            policy_version=policy.version,
            price_paise=policy.pass_price_paise,
            lunch_days=policy.lunch_included_days or [],
            status="pending",
        )
        db.add(existing)
        await db.flush()

    order = PaymentOrder(
        edition_id=edition.id,
        user_id=user_id,
        purpose="pass",
        amount_paise=policy.pass_price_paise,
        status="created",
        linked_record_id=existing.id,
    )
    db.add(order)
    await db.flush()
    return existing, order


async def activate_mock_pass(db: AsyncSession, user_pass: ConventionPass) -> None:
    user_pass.status = "active"
    user_pass.paid_at = datetime.now(UTC)
    from app.services.tickets import issue_for_pass

    await issue_for_pass(db, user_pass)
    await db.flush()


async def change_pass_state(
    db: AsyncSession, user_pass: ConventionPass, new_status: str
) -> None:
    user_pass.status = new_status
    await db.flush()


__all__ = [
    "get_pass",
    "selections_for",
    "selection_state",
    "set_selections",
    "sync_included_registrations",
    "create_pass_order",
    "activate_mock_pass",
    "change_pass_state",
]
