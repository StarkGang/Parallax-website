"""Teams: creation, join via invite code, roster and membership rules."""

import secrets
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import hash_token
from app.models.commerce import ConventionPass, Registration, Team, TeamMember
from app.models.registration import CollegeRegistration
from app.models.edition import ConventionEdition, Event
from app.models.user import ParticipantProfile, User
from app.schemas.participant import TeamMemberView, TeamView
from app.services.editions import current_policy
from app.services.events import event_open
from app.services.tickets import issue_for_registration, revoke_for_registration


def invite_code() -> str:
    return secrets.token_hex(4).upper()


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
                    Team.status == "active",
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
    for t in teams:
        event = await db.get(Event, t.event_id)
        members_raw = list(
            (
                await db.execute(
                    select(TeamMember, User, ParticipantProfile)
                    .join(User, TeamMember.user_id == User.id)
                    .outerjoin(ParticipantProfile, ParticipantProfile.user_id == User.id)
                    .where(TeamMember.team_id == t.id)
                )
            ).all()
        )
        mem_views = [
            TeamMemberView(
                user_id=u.id,
                full_name=u.full_name,
                college_name=p.college_name if p else None,
                is_leader=m.is_leader,
            )
            for m, u, p in members_raw
        ]
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
                members=mem_views,
                invite_code=t.invite_code if t.leader_id == current_user_id else None,
            )
        )
    return views


async def _pass_active(db: AsyncSession, user_id: uuid.UUID, edition_id: uuid.UUID) -> bool:
    """A paid pass in either pass model counts as an active pass.

    College registration is the current purchase flow, but it writes a
    CollegeRegistration row rather than the legacy ConventionPass, so checking
    only ConventionPass wrongly blocked team creation for paying attendees.
    """
    row = (
        await db.execute(
            select(ConventionPass.id).where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition_id,
                ConventionPass.status == "active",
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return True
    paid = (
        await db.execute(
            select(CollegeRegistration.id).where(
                CollegeRegistration.user_id == user_id,
                CollegeRegistration.edition_id == edition_id,
                CollegeRegistration.payment_status.in_(["paid", "completed"]),
            )
        )
    ).scalar_one_or_none()
    return paid is not None


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
    if not event_open(event):
        raise Conflict("This event is not open for team registration.")

    # One lock per attendee keeps two fast clicks from creating two teams for
    # the same event.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())

    policy = await current_policy(db, edition.id)
    if policy.team_members_require_pass:
        if not await _pass_active(db, user_id, edition.id):
            raise ValidationFailed("You must hold an active pass to create a team.")

    # Check if already in a team for this event
    existing_mem = (
        await db.execute(
            select(TeamMember)
            .join(Team, TeamMember.team_id == Team.id)
            .where(
                TeamMember.user_id == user_id,
                Team.event_id == event.id,
                Team.status == "active",
            )
        )
    ).scalar_one_or_none()
    if existing_mem:
        raise Conflict("You are already part of a team for this event.")

    code = invite_code()
    team = Team(
        edition_id=edition.id,
        event_id=event.id,
        leader_id=user_id,
        name=name.strip(),
        invite_code=code,
        invite_code_hash=hash_token(f"team-invite:{code}"),
        status="active",
    )
    db.add(team)
    await db.flush()

    member = TeamMember(
        team_id=team.id,
        user_id=user_id,
        is_leader=True,
    )
    db.add(member)
    await db.flush()
    await _maybe_register_team(db, team, event)
    return team


async def join_team(
    db: AsyncSession,
    request: Request,
    user_id: uuid.UUID,
    edition: ConventionEdition,
    code: str,
) -> Team:
    team = (
        await db.execute(
            select(Team).where(
                Team.invite_code == code.strip().upper(),
                Team.edition_id == edition.id,
                Team.status == "active",
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise NotFound("Team with that invite code not found.")

    # Lock the team row so a burst of joins cannot overshoot team_max_size.
    team = (
        await db.execute(
            select(Team).where(Team.id == team.id).with_for_update()
        )
    ).scalar_one_or_none()
    if team is None or team.status != "active":
        raise NotFound("Team with that invite code not found.")

    event = await db.get(Event, team.event_id)
    if team.status == "locked":
        raise Conflict("This team roster has been locked by the team leader.")
    if event and event.starts_at:
        now_dt = datetime.now(UTC)
        ev_start = event.starts_at if event.starts_at.tzinfo else event.starts_at.replace(tzinfo=UTC)
        if now_dt >= ev_start:
            raise Conflict("Team rosters are locked after the event begins.")
    policy = await current_policy(db, edition.id)
    if policy.team_members_require_pass:
        if not await _pass_active(db, user_id, edition.id):
            raise ValidationFailed("You must hold an active pass to join a team.")

    count = (
        await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team.id)
        )
    ).scalar() or 0

    if event and count >= event.team_max_size:
        raise Conflict("This team has reached maximum capacity.")

    existing_mem = (
        await db.execute(
            select(TeamMember)
            .join(Team, TeamMember.team_id == Team.id)
            .where(
                TeamMember.user_id == user_id,
                Team.event_id == team.event_id,
                Team.status == "active",
            )
        )
    ).scalar_one_or_none()
    if existing_mem:
        raise Conflict("You are already part of a team for this event.")

    mem = TeamMember(
        team_id=team.id,
        user_id=user_id,
        is_leader=False,
    )
    db.add(mem)
    await db.flush()

    # Link existing registration or issue a team event registration for the new member
    existing_mem_reg = (
        await db.execute(
            select(Registration).where(
                Registration.user_id == user_id,
                Registration.event_id == team.event_id,
                Registration.status.in_(["confirmed", "reserved"]),
            )
        )
    ).scalars().first()
    if existing_mem_reg is not None:
        existing_mem_reg.team_id = team.id
        await issue_for_registration(db, existing_mem_reg)
    else:
        reg_num = f"TM-{secrets.token_hex(4).upper()}"
        mem_reg = Registration(
            edition_id=team.edition_id,
            user_id=user_id,
            event_id=team.event_id,
            team_id=team.id,
            kind="team",
            fee_paise=0,
            status="confirmed",
            registration_number=reg_num,
        )
        db.add(mem_reg)
        await db.flush()
        await issue_for_registration(db, mem_reg)

    return team


async def _maybe_register_team(db: AsyncSession, team: Team, event: Event) -> None:
    # Check if leader already has a confirmed registration for this event (e.g. from pass selection)
    existing = (
        await db.execute(
            select(Registration).where(
                Registration.user_id == team.leader_id,
                Registration.event_id == team.event_id,
                Registration.status.in_(["confirmed", "reserved"]),
            )
        )
    ).scalars().first()
    if existing is not None:
        existing.team_id = team.id
        await issue_for_registration(db, existing)
        return

    # Automatic registration record for team leader
    team_reg = (
        await db.execute(
            select(Registration).where(
                Registration.team_id == team.id,
                Registration.user_id == team.leader_id,
            )
        )
    ).scalar_one_or_none()
    if team_reg is None:
        reg_num = f"TM-{secrets.token_hex(4).upper()}"
        team_reg = Registration(
            edition_id=team.edition_id,
            user_id=team.leader_id,
            event_id=team.event_id,
            team_id=team.id,
            kind="team",
            fee_paise=0,
            status="confirmed",
            registration_number=reg_num,
        )
        db.add(team_reg)
        await db.flush()
        await issue_for_registration(db, team_reg)


async def leave_team(db: AsyncSession, user_id: uuid.UUID, team_id: uuid.UUID) -> None:
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
    if mem.is_leader:
        # Disbanding must release the team's booking and everyone's membership.
        from datetime import UTC, datetime

        team.status = "disbanded"
        reg = await team_registration(db, team.id)
        if reg is not None and reg.status != "cancelled":
            reg.status = "cancelled"
            reg.cancelled_at = datetime.now(UTC)
            await revoke_for_registration(db, reg.id)
        members = list(
            (
                await db.execute(
                    select(TeamMember).where(TeamMember.team_id == team.id)
                )
            ).scalars()
        )
        for row in members:
            await db.delete(row)
        await db.flush()
        return
    # If leaving member had an event registration for this team, revoke it or unlink team
    from datetime import UTC, datetime
    mem_reg = (
        await db.execute(
            select(Registration).where(
                Registration.user_id == user_id,
                Registration.team_id == team_id,
            )
        )
    ).scalars().first()
    if mem_reg is not None:
        if mem_reg.kind == "team":
            mem_reg.status = "cancelled"
            mem_reg.cancelled_at = datetime.now(UTC)
            await revoke_for_registration(db, mem_reg.id)
        else:
            mem_reg.team_id = None
    await db.delete(mem)
    await db.flush()


async def rotate_invite(db: AsyncSession, team: Team) -> str:
    team.invite_code = invite_code()
    await db.flush()
    return team.invite_code


async def get_team(db: AsyncSession, team_id: uuid.UUID) -> Team:
    row = await db.get(Team, team_id)
    if row is None:
        raise NotFound("Team not found.")
    return row


async def team_registration(db: AsyncSession, team_id: uuid.UUID) -> Registration | None:
    return (
        await db.execute(
            select(Registration).where(Registration.team_id == team_id)
        )
    ).scalar_one_or_none()


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
            .where(Team.event_id == event_id, Team.status == "active")
        )
    ).scalar() or 0


async def toggle_team_lock(db: AsyncSession, user_id: uuid.UUID, team_id: uuid.UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None:
        raise NotFound("Team not found.")
    if team.leader_id != user_id:
        raise Conflict("Only the team leader can lock or unlock the roster.")
    team.status = "forming" if team.status == "locked" else "locked"
    await db.flush()
    return team


__all__ = [
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
]

