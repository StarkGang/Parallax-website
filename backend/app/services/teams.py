"""Teams: an optional roster attached to a seat, never a precondition for one.

The attendee registers for an event first (solo by default). A ``Team`` row is
created only when they ask to create or join one. Creating or joining never
re-prices a seat: it goes through the same pricing quote as any other event, so
a pass-covered team entry costs ₹0 and a free team entry costs ₹0.

Leadership follows the roster, not the money. When the leader leaves, the
earliest-joined remaining member is promoted; the team disbands only when the
last member leaves. For ``per_team`` events the payment belongs to the team
(``Team.order_id``), so a leader change cannot orphan it.
"""

import logging
import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_pattern
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import hash_token
from app.models.commerce import (
    ConventionPass,
    PaymentOrder,
    Refund,
    Registration,
    Team,
    TeamMember,
)
from app.models.registration import CollegeRegistration
from app.models.edition import ConventionEdition, Event
from app.models.user import ParticipantProfile, User
from app.schemas.participant import TeamMemberView, TeamView
from app.services.editions import accepting_bookings, aware, current_policy
from app.services.events import LIVE_TEAM_STATUSES, event_open
from app.services.tickets import issue_for_registration, revoke_for_registration

logger = logging.getLogger(__name__)

TEAM_NAME_MIN = 3
TEAM_NAME_MAX = 48
_NAME_DROP = re.compile(r"[^\w\s&'.\-]", re.UNICODE)
_NAME_SPACE = re.compile(r"\s+")


def invite_code() -> str:
    return secrets.token_hex(4).upper()


def normalize_team_name(value: str) -> str:
    """Collapse whitespace and drop characters a roster/export cannot carry."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _NAME_DROP.sub("", text)
    text = _NAME_SPACE.sub(" ", text).strip()
    return text[:TEAM_NAME_MAX]


def validate_team_name(value: str) -> str:
    name = normalize_team_name(value)
    if len(name) < TEAM_NAME_MIN:
        raise ValidationFailed(
            f"Team name must be at least {TEAM_NAME_MIN} characters.", code="TEAM_NAME"
        )
    if not any(ch.isalnum() for ch in name):
        raise ValidationFailed(
            "Team name must contain at least one letter or number.", code="TEAM_NAME"
        )
    return name


def default_team_name(full_name: str | None) -> str:
    first = (str(full_name or "").strip().split(" ") or ["Player"])[0]
    first = normalize_team_name(first)[:24] or "Player"
    return f"Team {first}"


def _team_live(team: Team) -> bool:
    return team.status in LIVE_TEAM_STATUSES


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> list[Team]:
    rows = list(
        (
            await db.execute(
                select(Team)
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(
                    TeamMember.user_id == user_id,
                    Team.edition_id == edition_id,
                    Team.status.in_(LIVE_TEAM_STATUSES),
                )
            )
        ).scalars()
    )
    return rows


async def serialize_teams(
    db: AsyncSession, teams: list[Team], current_user_id: uuid.UUID
) -> list[TeamView]:
    if not teams:
        return []
    views = []
    policy_cache: dict[uuid.UUID, object] = {}
    for t in teams:
        event = await db.get(Event, t.event_id)
        if t.edition_id not in policy_cache:
            policy_cache[t.edition_id] = await current_policy(db, t.edition_id)
        policy = policy_cache[t.edition_id]
        basis = team_fee_basis(event, policy) if event else "per_participant"
        price = team_seat_price(event, policy) if event else 0
        team_order = await _team_order(db, t) if basis == "per_team" and price > 0 else None
        # Nothing owed (free/included seat, no order) or the order is paid means
        # the team fee is settled. An open order means the invite stays locked.
        leader_paid = not (
            basis == "per_team"
            and price > 0
            and team_order is not None
            and team_order.status != "paid"
        )

        members_raw = list(
            (
                await db.execute(
                    select(TeamMember, User, ParticipantProfile)
                    .join(User, TeamMember.user_id == User.id)
                    .outerjoin(ParticipantProfile, ParticipantProfile.user_id == User.id)
                    .where(TeamMember.team_id == t.id)
                    .order_by(TeamMember.joined_at.asc())
                )
            ).all()
        )
        # Every roster member must hold a seat row for the team's event. The
        # badge surfaces a seat that failed to materialise instead of showing a
        # member who cannot be admitted at the door.
        seat_rows = list(
            (
                await db.execute(
                    select(Registration.user_id, Registration.status).where(
                        Registration.team_id == t.id,
                        Registration.event_id == t.event_id,
                    )
                )
            ).all()
        )
        seat_by_user = {uid: status for uid, status in seat_rows}
        mem_views = [
            TeamMemberView(
                user_id=u.id,
                full_name=u.full_name,
                college_name=p.college_name if p else None,
                is_leader=m.is_leader,
                seat_status=seat_by_user.get(u.id),
            )
            for m, u, p in members_raw
        ]
        can_see_invite = t.leader_id == current_user_id and leader_paid
        views.append(
            TeamView(
                id=t.id,
                name=t.name,
                event_id=t.event_id,
                event_title=event.title if event else "Event",
                event_slug=event.slug if event else "",
                leader_id=t.leader_id,
                is_leader=t.leader_id == current_user_id,
                status=t.status,
                max_size=event.team_max_size if event else 4,
                fee_basis=basis,
                fee_paise=price,
                leader_paid=leader_paid,
                members=mem_views,
                invite_code=t.invite_code if can_see_invite else None,
                invite_link=(
                    f"/team/{t.invite_code}" if can_see_invite else None
                ),
                formation_state=getattr(t, "formation_state", "forming"),
                min_size=event.team_min_size if event else 1,
                member_count=len(mem_views),
            )
        )
    return views


async def _pass_active(db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID) -> bool:
    """A paid pass in either pass model counts as an active pass."""
    user = await db.get(User, user_id)
    if user is not None and user.status == "suspended":
        return False

    pass_row = (
        await db.execute(
            select(ConventionPass)
            .where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition_id,
            )
            .order_by(ConventionPass.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if pass_row is not None:
        if pass_row.status in ("suspended", "cancelled", "revoked"):
            return False
        if pass_row.status == "active":
            return True
    paid = (
        await db.execute(
            select(CollegeRegistration.id).where(
                CollegeRegistration.user_id == user_id,
                CollegeRegistration.edition_id == edition_id,
                CollegeRegistration.payment_status == "paid",
                CollegeRegistration.verification_status != "rejected",
                CollegeRegistration.refund_status.not_in(
                    ["initiated", "processing", "completed"]
                ),
            )
        )
    ).scalar_one_or_none()
    return paid is not None


def team_fee_basis(event: Event, policy) -> str:
    basis = (
        event.team_fee_basis
        or getattr(policy, "team_fee_basis_default", None)
        or "per_participant"
    )
    return basis if basis in {"per_participant", "per_team"} else "per_participant"


def team_seat_price(event: Event, policy) -> int:
    return max(0, int(event.addon_price_paise or 0))


async def _live_seat(
    db: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID
) -> Registration | None:
    return (
        await db.execute(
            select(Registration)
            .where(
                Registration.user_id == user_id,
                Registration.event_id == event_id,
                Registration.status.in_(("confirmed", "reserved", "pending")),
            )
            .limit(1)
        )
    ).scalars().first()


async def _team_order(db: AsyncSession, team: Team) -> PaymentOrder | None:
    """The order that pays for this team (``per_team`` basis).

    It lives on ``Team.order_id`` so a leader change cannot orphan it. Older
    rows are still found through the creator's seat until the backfill runs.
    """
    if team.order_id is not None:
        return await db.get(PaymentOrder, team.order_id)
    leader_reg = (
        await db.execute(
            select(Registration).where(
                Registration.team_id == team.id,
                Registration.user_id == team.leader_id,
            )
        )
    ).scalars().first()
    if leader_reg is None or leader_reg.order_id is None:
        return None
    order = await db.get(PaymentOrder, leader_reg.order_id)
    if order is not None:
        team.order_id = order.id
        team.paid_by_user_id = team.paid_by_user_id or leader_reg.user_id
    return order


async def _new_seat_order(
    db: AsyncSession, team: Team, event: Event, user_id: uuid.UUID, amount_paise: int
) -> PaymentOrder:
    order = PaymentOrder(
        edition_id=team.edition_id,
        user_id=user_id,
        purpose="registration",
        amount_paise=amount_paise,
        status="created",
        notes={"teamId": str(team.id), "eventId": str(event.id), "kind": "team_seat"},
    )
    db.add(order)
    await db.flush()
    from app.services.payments import attach_gateway_order

    await attach_gateway_order(db, order)
    return order


async def _ensure_seat(
    db: AsyncSession,
    request: Request | None,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    event: Event,
) -> tuple[Registration | None, PaymentOrder | None]:
    """Attach the existing seat, or price and create one through the quote.

    This is what stops a team action from forcing a payment: a pass-covered or
    free event produces a ₹0 seat here, identical to the worklist.
    """
    seat = await _live_seat(db, user_id, event.id)
    if seat is not None:
        return seat, None

    from app.services import pricing

    policy = await current_policy(db, edition.id)
    # ``create_seat_now`` prices the single event but never expires the open
    # basket. Team formation must not make an unrelated event disappear.
    return await pricing.create_seat_now(
        db,
        user_id=user_id,
        edition=edition,
        policy=policy,
        event=event,
    )


async def _attach_seat(
    db: AsyncSession,
    *,
    team: Team,
    event: Event,
    user_id: uuid.UUID,
    seat: Registration | None,
    policy,
) -> tuple[Registration | None, PaymentOrder | None]:
    """Give the member one seat on this team, priced by the quote not the team."""
    basis = team_fee_basis(event, policy)
    if seat is None:
        seat, order = await _ensure_seat(
            db, None, user_id, await db.get(ConventionEdition, team.edition_id), event
        )
        if seat is None:
            return None, order
    else:
        order = None

    seat.team_id = team.id
    seat.price_basis = seat.price_basis or (
        "team_per_team" if basis == "per_team" else "team_per_participant"
    )
    # Keep ``included`` so the pass allowance still recognises the seat; every
    # other team seat is reported as a team seat even when it is free.
    if seat.kind != "included":
        seat.kind = "team"

    # A per-team entry is paid once. If the caller's seat already carries a paid
    # order, that order becomes the team order; a rider joins without paying.
    if basis == "per_team":
        team_order = await _team_order(db, team)
        if team_order is None and seat.order_id is not None:
            candidate = await db.get(PaymentOrder, seat.order_id)
            if candidate is not None:
                team.order_id = candidate.id
                team.paid_by_user_id = user_id
                team_order = candidate
        if team_order is not None:
            if team_order.status == "paid":
                seat.status = "confirmed"
                seat.reservation_expires_at = None
                if seat.order_id != team_order.id:
                    seat.fee_paise = 0
                    seat.order_id = None
                await issue_for_registration(db, seat)
                return seat, None
            if user_id != team.leader_id:
                # Ride the leader's open payment without being asked to pay it.
                seat.order_id = team_order.id
                seat.fee_paise = 0
                seat.status = "reserved"
                seat.reservation_expires_at = datetime.now(UTC) + timedelta(
                    minutes=int(getattr(policy, "hold_minutes", 30) or 30)
                )
                return seat, None
    return seat, order


def _require_member_seat(seat: Registration | None, *, event: Event, team: Team) -> None:
    """No roster member without an event registration, ever.

    A roster row without a seat would put somebody on the team list and the
    door list who has no booking for the event. Joining is refused (and the
    roster row rolled back with the request) instead of showing a member who
    cannot attend.
    """
    if (
        seat is None
        or seat.event_id != event.id
        or seat.team_id != team.id
        or seat.status not in ("confirmed", "reserved", "pending")
    ):
        raise ValidationFailed(
            "Every team member needs a registration for this event. "
            "Please try again or contact the organisers.",
            code="TEAM_SEAT_REQUIRED",
        )
    if not seat.registration_number:
        seat.registration_number = f"TM-{secrets.token_hex(4).upper()}"


async def _refresh_formation(db: AsyncSession, team: Team, event: Event | None = None) -> None:
    if event is None:
        event = await db.get(Event, team.event_id)
    count = (
        await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
        )
    ).scalar() or 0
    team.min_size = int(event.team_min_size if event else 1)
    if team.status == "locked":
        team.formation_state = "locked"
    elif count >= max(1, team.min_size):
        team.formation_state = "ready"
    else:
        team.formation_state = "forming"
    if count <= 0:
        team.formation_state = "disbanded"


async def pending_team_payment(
    db: AsyncSession, team: Team, user_id: uuid.UUID | None = None
) -> PaymentOrder | None:
    """The open order that confirms a seat on this team.

    For ``per_team`` events only the leader pays; an invited member never sees
    a bill or Pay button. For ``per_participant`` events every member pays their
    own seat, so the newest open seat order is returned when the caller has no
    order of their own.
    """
    event = await db.get(Event, team.event_id)
    policy = await current_policy(db, team.edition_id)
    basis = team_fee_basis(event, policy) if event else "per_participant"
    if basis == "per_team" and user_id is not None and user_id != team.leader_id:
        return None
    if team.order_id is not None:
        order = await db.get(PaymentOrder, team.order_id)
        if order is not None and order.status == "created":
            return order
        return None
    stmt = select(Registration).where(
        Registration.team_id == team.id,
        Registration.status == "reserved",
        Registration.order_id.is_not(None),
    )
    seat = None
    if user_id is not None:
        seat = (
            await db.execute(stmt.where(Registration.user_id == user_id))
        ).scalars().first()
    elif basis != "per_team":
        seat = (await db.execute(stmt)).scalars().first()
    if seat is None or seat.order_id is None:
        return None
    order = await db.get(PaymentOrder, seat.order_id)
    if order is None or order.status != "created":
        return None
    return order


# --------------------------------------------------------------------------- #
# Teardown and leadership
# --------------------------------------------------------------------------- #
async def _cancel_seat(
    db: AsyncSession,
    reg: Registration,
    *,
    reason: str,
    refunded_orders: set[uuid.UUID] | None = None,
    method: str = "refund",
    preserve_orders: set[uuid.UUID] | None = None,
) -> bool:
    """Cancel one team seat, revoke its ticket and settle its own money."""
    if reg.status != "cancelled":
        reg.status = "cancelled"
        reg.cancelled_at = datetime.now(UTC)
        reg.cancelled_by = "system"
        reg.cancellation_reason = reason[:500]
    await revoke_for_registration(db, reg.id)
    if reg.order_id is None:
        return False
    order = await db.get(PaymentOrder, reg.order_id)
    if order is None or order.status != "paid":
        return False
    if preserve_orders and order.id in preserve_orders:
        # The order pays for a team that is still running: the seat goes, the
        # money stays with the teammates who are still on the roster.
        return False
    # One order can pay for several seats (``per_team``): refund it only when no
    # other live seat still claims it.
    still_claimed = (
        await db.execute(
            select(func.count(Registration.id)).where(
                Registration.order_id == order.id,
                Registration.id != reg.id,
                Registration.status.in_(("confirmed", "reserved", "pending")),
            )
        )
    ).scalar() or 0
    if still_claimed:
        return False
    if refunded_orders is not None:
        if order.id in refunded_orders:
            return False
        refunded_orders.add(order.id)
    already_committed = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(
                    Refund.order_id == order.id,
                    Refund.status.in_(("pending", "processing", "processed")),
                )
            )
        ).scalar()
        or 0
    )
    available = max(0, int(order.amount_paise) - already_committed)
    if available <= 0:
        return True
    try:
        from app.services.payments import refund_order

        await refund_order(
            db,
            order,
            amount_paise=available,
            reason_code="team_disbanded",
            reason_note=reason[:500],
        )
        return True
    except Exception as exc:  # a gateway outage must not keep the money
        logger.warning(
            "team_seat_refund_failed order=%s error=%s", order.id, str(exc)[:200]
        )
        db.add(
            Refund(
                order_id=order.id,
                amount_paise=available,
                reason_code="team_disbanded",
                reason_note=f"{reason} (gateway refund failed: {str(exc)[:200]})"[:500],
                status="pending",
            )
        )
        return False


async def _teardown_team(db: AsyncSession, team: Team, *, reason: str) -> int:
    """Disband the team and detach member registrations without cancelling their events."""
    team.status = "disbanded"
    team.formation_state = "disbanded"
    seats = list(
        (
            await db.execute(
                select(Registration).where(Registration.team_id == team.id)
            )
        ).scalars()
    )
    for seat in seats:
        seat.team_id = None
    members = list(
        (
            await db.execute(select(TeamMember).where(TeamMember.team_id == team.id))
        ).scalars()
    )
    for row in members:
        await db.delete(row)
    await db.flush()
    _touch_caches()
    return len(seats)


async def disband_team(db: AsyncSession, team: Team, *, reason: str) -> int:
    """Explicit teardown. Kept for admin flows that really end a team."""
    return await _teardown_team(db, team, reason=reason)


async def promote_or_disband(
    db: AsyncSession, team: Team, *, leaving_user_id: uuid.UUID, reason: str
) -> uuid.UUID | None:
    """Elder-leads handover. Disband only when nobody remains.

    Every leader-exit path (leave, booking cancel, pass rejection/suspension,
    admin removal) must call this and nothing else, so no path can silently
    disband a team that still has members.
    """
    # Remove the leaver's membership row first (idempotent).
    own = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == leaving_user_id,
            )
        )
    ).scalar_one_or_none()
    if own is not None:
        await db.delete(own)
        await db.flush()

    remaining = list(
        (
            await db.execute(
                select(TeamMember)
                .where(TeamMember.team_id == team.id)
                .order_by(TeamMember.joined_at.asc(), TeamMember.id.asc())
            )
        ).scalars()
    )
    if not remaining:
        await _teardown_team(db, team, reason=reason)
        return None

    new_leader = remaining[0]
    for member in remaining:
        member.is_leader = member.id == new_leader.id
    team.leader_id = new_leader.user_id
    team.status = "active" if team.status == "disbanded" else team.status
    await _refresh_formation(db, team)

    from app.services.audit import record

    await record(
        db,
        None,
        action="team.leader_handover",
        resource_type="team",
        resource_id=str(team.id),
        after={
            "old_leader_id": str(leaving_user_id),
            "new_leader_id": str(new_leader.user_id),
            "reason": reason,
        },
    )
    await db.flush()
    _touch_caches()
    return new_leader.user_id


def _touch_caches() -> None:
    cache_delete_pattern("public:*")
    cache_delete_pattern("admin:dashboard:*")


# --------------------------------------------------------------------------- #
# Create / join / leave
# --------------------------------------------------------------------------- #
async def create_team(
    db: AsyncSession,
    request: Request,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    event_id: uuid.UUID,
    name: str,
) -> Team:
    event = await db.get(Event, event_id)
    if event is None or event.edition_id != edition.id:
        raise NotFound("Event not found.")
    if event.format != "team":
        raise ValidationFailed("This event is not a team event.")
    if not accepting_bookings(edition):
        raise Conflict("This convention is no longer accepting new bookings.")
    if not event_open(event):
        raise Conflict("This event is not open for team registration.")

    # One lock per attendee keeps two fast clicks from creating two teams.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())

    policy = await current_policy(db, edition.id)
    if policy.team_members_require_pass:
        if not await _pass_active(db, user_id, edition.id):
            raise ValidationFailed("You must hold an active pass to create a team.")

    existing_mem = (
        await db.execute(
            select(TeamMember)
            .join(Team, TeamMember.team_id == Team.id)
            .where(
                TeamMember.user_id == user_id,
                Team.event_id == event.id,
                Team.status.in_(LIVE_TEAM_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if existing_mem:
        raise Conflict("You are already part of a team for this event.")

    clean = validate_team_name(name)
    code = invite_code()
    team = Team(
        edition_id=edition.id,
        event_id=event.id,
        leader_id=user_id,
        name=clean,
        invite_code=code,
        invite_code_hash=hash_token(f"team-invite:{code}"),
        status="active",
        formation_state="forming",
        min_size=int(event.team_min_size),
        max_size=int(event.team_max_size),
    )
    db.add(team)
    await db.flush()

    member = TeamMember(team_id=team.id, user_id=user_id, is_leader=True)
    db.add(member)
    await db.flush()

    seat = await _live_seat(db, user_id, event.id)
    if seat is None:
        raise ValidationFailed(
            "Register for this event in Browse Events first before creating a team.",
            code="REGISTRATION_REQUIRED",
        )
    seat, _ = await _attach_seat(
        db, team=team, event=event, user_id=user_id, seat=seat, policy=policy
    )
    _require_member_seat(seat, event=event, team=team)
    await _refresh_formation(db, team, event)
    _touch_caches()
    return team


async def join_team(
    db: AsyncSession,
    request: Request,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    code: str,
) -> Team:
    needle = (code or "").strip()
    team = (
        await db.execute(
            select(Team).where(
                Team.invite_code == needle.upper(),
                Team.edition_id == edition.id,
                Team.status.in_(LIVE_TEAM_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if team is None:
        hashed = (
            await db.execute(
                select(Team).where(
                    Team.invite_code_hash == hash_token(f"team-invite:{needle.upper()}"),
                    Team.edition_id == edition.id,
                    Team.status.in_(LIVE_TEAM_STATUSES),
                )
            )
        ).scalar_one_or_none()
        team = hashed
    if team is None:
        raise NotFound("Team with that invite code not found.")

    # Lock the team row so a burst of joins cannot overshoot team_max_size.
    team = (
        await db.execute(select(Team).where(Team.id == team.id).with_for_update())
    ).scalar_one_or_none()
    if team is None or team.status not in LIVE_TEAM_STATUSES:
        raise NotFound("Team with that invite code not found.")

    if not accepting_bookings(edition):
        raise Conflict("This convention is no longer accepting new bookings.")
    event = await db.get(Event, team.event_id)
    if team.status == "locked":
        raise Conflict("This team roster has been locked by the team leader.")
    if event is None or not event_open(event):
        raise Conflict("Registration for this event is closed.")
    if event.starts_at:
        if datetime.now(UTC) >= aware(event.starts_at):
            raise Conflict("Team rosters are locked after the event begins.")
    policy = await current_policy(db, edition.id)
    if policy.team_members_require_pass:
        if not await _pass_active(db, user_id, edition.id):
            raise ValidationFailed("You must hold an active pass to join a team.")

    if (
        team_fee_basis(event, policy) == "per_team"
        and team_seat_price(event, policy) > 0
    ):
        # The team fee is paid once, by the leader. Until it is in, there is
        # nothing for a newcomer to ride on, so joining is refused rather than
        # silently opening a second invoice for the same team.
        team_order = await _team_order(db, team)
        if team_order is not None and team_order.status != "paid":
            raise Conflict(
                "The team leader must complete payment before members can join this team."
            )

    count = (
        await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
        )
    ).scalar() or 0
    if count >= int(event.team_max_size):
        raise Conflict("This team has reached maximum capacity.")

    existing_mem = (
        await db.execute(
            select(TeamMember)
            .join(Team, TeamMember.team_id == Team.id)
            .where(
                TeamMember.user_id == user_id,
                Team.event_id == team.event_id,
                Team.status.in_(LIVE_TEAM_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if existing_mem:
        if existing_mem.team_id == team.id:
            return team
        raise Conflict("You are already part of a team for this event.")

    seat = await _live_seat(db, user_id, event.id)
    if seat is None:
        raise ValidationFailed(
            "Register for this event in Browse Events first before joining a team.",
            code="REGISTRATION_REQUIRED",
        )
    db.add(TeamMember(team_id=team.id, user_id=user_id, is_leader=False))
    await db.flush()
    seat, _ = await _attach_seat(
        db, team=team, event=event, user_id=user_id, seat=seat, policy=policy
    )
    _require_member_seat(seat, event=event, team=team)
    await _refresh_formation(db, team, event)
    _touch_caches()
    return team


async def leave_team(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: uuid.UUID,
    *,
    disband: bool = False,
) -> uuid.UUID | None:
    team = await db.get(Team, team_id)
    if team is None:
        raise NotFound("Team not found.")
    if team.status == "locked":
        raise Conflict("This team roster is locked and cannot be modified.")
    mem = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if mem is None:
        raise NotFound("You are not in this team.")

    if disband:
        if not mem.is_leader:
            raise Conflict("Only the team leader can disband the team.")
        await _teardown_team(
            db, team, reason="Team disbanded: the leader disbanded the team"
        )
        await db.flush()
        _touch_caches()
        return None

    # Detach the leaver's registration from the team while keeping their
    # event registration in the same state as before they joined a team.
    mem_reg = (
        await db.execute(
            select(Registration).where(
                Registration.user_id == user_id,
                Registration.team_id == team_id,
            )
        )
    ).scalars().first()
    if mem_reg is not None:
        mem_reg.team_id = None

    new_leader = await promote_or_disband(
        db,
        team,
        leaving_user_id=user_id,
        reason="Member left the team",
    )
    await db.flush()
    _touch_caches()
    return new_leader


async def _seat_for(
    db: AsyncSession,
    *,
    team: Team,
    event: Event,
    user_id: uuid.UUID,
    policy,
    existing: Registration | None = None,
) -> tuple[Registration, PaymentOrder | None]:
    """Compatibility wrapper: attach a seat using the team's pricing rules."""
    seat, order = await _attach_seat(
        db,
        team=team,
        event=event,
        user_id=user_id,
        seat=existing,
        policy=policy,
    )
    if seat is None:
        raise ValidationFailed("Could not create a seat for this team.")
    return seat, order


async def _maybe_register_team(
    db: AsyncSession, team: Team, event: Event, policy=None
) -> None:
    if policy is None:
        policy = await current_policy(db, team.edition_id)
    seat, _order = await _ensure_seat(
        db, None, team.leader_id, await db.get(ConventionEdition, team.edition_id), event
    )
    if seat is not None:
        await _attach_seat(
            db,
            team=team,
            event=event,
            user_id=team.leader_id,
            seat=seat,
            policy=policy,
        )


async def on_team_registration_cancelled(
    db: AsyncSession, reg: Registration
) -> uuid.UUID | None:
    """Sync team membership when a seat is cancelled.

    If the cancelled booking belonged to the leader, leadership is handed to the
    earliest remaining member. The team is torn down only when nobody remains.
    """
    if reg.team_id is None:
        return None
    team = await db.get(Team, reg.team_id)
    if team is None:
        return None
    mem = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == reg.user_id,
            )
        )
    ).scalar_one_or_none()
    if mem is None:
        return None
    new_leader = await promote_or_disband(
        db,
        team,
        leaving_user_id=reg.user_id,
        reason="A team member's booking was cancelled",
    )
    await db.flush()
    _touch_caches()
    return new_leader


async def purge_user_from_teams(
    db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID
) -> None:
    """Remove an attendee from every team roster in an edition.

    Leadership moves to the earliest remaining member instead of disbanding the
    team, so innocent teammates keep their roster and their seats.
    """
    memberships = list(
        (
            await db.execute(
                select(TeamMember)
                .where(
                    TeamMember.user_id == user_id,
                    TeamMember.team_id.in_(
                        select(Team.id).where(
                            Team.event_id.in_(
                                select(Event.id).where(Event.edition_id == edition_id)
                            )
                        )
                    ),
                )
            )
        ).scalars()
    )
    for mem in memberships:
        team = await db.get(Team, mem.team_id)
        if team is None:
            await db.delete(mem)
            continue
        await promote_or_disband(
            db,
            team,
            leaving_user_id=user_id,
            reason="Member removed from the roster",
        )
    await db.flush()
    _touch_caches()


async def rotate_invite(db: AsyncSession, team: Team) -> str:
    team.invite_code = invite_code()
    team.invite_code_hash = hash_token(f"team-invite:{team.invite_code}")
    await db.flush()
    return team.invite_code


async def get_team(db: AsyncSession, team_id: uuid.UUID) -> Team:
    row = await db.get(Team, team_id)
    if row is None:
        raise NotFound("Team not found.")
    return row


async def team_registration(db: AsyncSession, team_id: uuid.UUID) -> Registration | None:
    team = await db.get(Team, team_id)
    stmt = select(Registration).where(Registration.team_id == team_id)
    if team is not None:
        leader_row = (
            await db.execute(stmt.where(Registration.user_id == team.leader_id))
        ).scalars().first()
        if leader_row is not None:
            return leader_row
    return (await db.execute(stmt)).scalars().first()


async def member_counts(db: AsyncSession, team_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not team_ids:
        return {}
    rows = list(
        (
            await db.execute(
                select(TeamMember.team_id, func.count(TeamMember.id))
                .where(TeamMember.team_id.in_(team_ids))
                .group_by(TeamMember.team_id)
            )
        ).all()
    )
    return {tid: count for tid, count in rows}


async def team_seats(db: AsyncSession, event_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count(TeamMember.id))
            .join(Team, TeamMember.team_id == Team.id)
            .where(Team.event_id == event_id, Team.status.in_(LIVE_TEAM_STATUSES))
        )
    ).scalar() or 0


async def toggle_team_lock(db: AsyncSession, user_id: uuid.UUID, team_id: uuid.UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None:
        raise NotFound("Team not found.")
    if team.leader_id != user_id:
        raise Conflict("Only the team leader can lock or unlock the roster.")
    if team.status == "disbanded":
        team.status = "active"
        await _refresh_formation(db, team)
        await db.flush()
        return team
    team.status = "active" if team.status == "locked" else "locked"
    team.formation_state = "locked" if team.status == "locked" else "ready"
    await db.flush()
    return team


async def invite_preview(db: AsyncSession, code: str) -> dict:
    """Non-PII invite data for the public landing page.

    Returns enough to decide whether to join: event, team name, roster size, the
    price outcome (included/free/₹X) and the reason a join would fail.
    """
    needle = (code or "").strip().upper()
    team = (
        await db.execute(
            select(Team).where(
                Team.invite_code == needle,
                Team.status.in_(LIVE_TEAM_STATUSES),
            )
        )
    ).scalars().first()
    if team is None:
        raise NotFound("This invite link is no longer valid.")
    event = await db.get(Event, team.event_id)
    if event is None:
        raise NotFound("This invite link is no longer valid.")
    edition = await db.get(ConventionEdition, team.edition_id)
    policy = await current_policy(db, team.edition_id)
    member_count = (
        await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
        )
    ).scalar() or 0
    leader = await db.get(User, team.leader_id)
    open_for_join = (
        _team_live(team)
        and team.status != "locked"
        and event_open(event)
        and team.formation_state not in ("locked", "disbanded")
    )
    return {
        "code": team.invite_code,
        "teamName": team.name,
        "memberCount": int(member_count),
        "minSize": int(event.team_min_size),
        "maxSize": int(event.team_max_size),
        "status": team.status,
        "formationState": team.formation_state,
        "openForJoin": bool(open_for_join) and member_count < int(event.team_max_size),
        "leaderName": (leader.full_name.split(" ")[0] if leader and leader.full_name else "A teammate"),
        "requiresPass": bool(policy.team_members_require_pass),
        "event": {
            "id": str(event.id),
            "slug": event.slug,
            "title": event.title,
            "summary": event.summary,
            "format": event.format,
            "startsAt": aware(event.starts_at).isoformat() if event.starts_at else None,
            "venue": event.venue_room,
            "baseValuePaise": int(event.base_value_paise or 0),
            "listPaise": int(event.addon_price_paise or 0),
            "teamBasis": team_fee_basis(event, policy),
        },
        "edition": {"id": str(edition.id) if edition else None, "slug": edition.slug if edition else None},
    }


__all__ = [
    "TEAM_NAME_MAX",
    "TEAM_NAME_MIN",
    "default_team_name",
    "disband_team",
    "invite_preview",
    "normalize_team_name",
    "pending_team_payment",
    "promote_or_disband",
    "team_fee_basis",
    "team_seat_price",
    "invite_code",
    "list_for_user",
    "serialize_teams",
    "_pass_active",
    "create_team",
    "join_team",
    "_maybe_register_team",
    "leave_team",
    "toggle_team_lock",
    "rotate_invite",
    "get_team",
    "team_registration",
    "member_counts",
    "team_seats",
    "validate_team_name",
]
