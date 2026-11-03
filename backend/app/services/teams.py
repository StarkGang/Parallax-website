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
from app.models.edition import ConventionEdition, Event
from app.models.user import ParticipantProfile, User
from app.schemas.participant import TeamMemberView, TeamView
from app.services.editions import current_policy


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
    row = (
        await db.execute(
            select(ConventionPass.id).where(
                ConventionPass.user_id == user_id,
                ConventionPass.edition_id == edition_id,
                ConventionPass.status == "active",
            )
        )
    ).scalar_one_or_none()
    return row is not None


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

    event = await db.get(Event, team.event_id)
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
    return team


async def _maybe_register_team(db: AsyncSession, team: Team, event: Event) -> None:
    # Automatic registration record for team
    existing = (
        await db.execute(
            select(Registration).where(
                Registration.team_id == team.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        reg_num = f"TM-{secrets.token_hex(4).upper()}"
        reg = Registration(
            edition_id=team.edition_id,
            user_id=team.leader_id,
            event_id=team.event_id,
            team_id=team.id,
            kind="addon",
            fee_paise=0,
            status="confirmed",
            registration_number=reg_num,
        )
        db.add(reg)
        await db.flush()


async def leave_team(db: AsyncSession, user_id: uuid.UUID, team_id: uuid.UUID) -> None:
    team = await db.get(Team, team_id)
    if team is None:
        raise NotFound("Team not found.")
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
        team.status = "disbanded"
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


__all__ = [
    "invite_code",
    "list_for_user",
    "serialize_teams",
    "_pass_active",
    "create_team",
    "join_team",
    "_maybe_register_team",
    "leave_team",
    "rotate_invite",
    "get_team",
    "team_registration",
    "member_counts",
    "team_seats",
]

