"""Account endpoints: identity, profile, own sessions and deletion request."""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, current_context
from app.core.errors import NotFound
from app.core.sessions import revoke_session_row
from app.db.session import get_db
from app.schemas.auth import (
    DeletionRequestResponse,
    MeEnvelope,
    MeResponse,
    ProfilePatch,
    ProfileResponse,
    SessionInfo,
)
from app.schemas.common import ok
from app.services import users as user_service

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeEnvelope)
async def me(
    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)
) -> dict:
    resp = await user_service.me_payload(db, ctx.user, ctx.session)
    return ok(resp.model_dump(by_alias=True))


@router.patch("/me/profile")
async def update_profile(
    payload: ProfilePatch,
    request: Request,
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await user_service.update_profile(
        db, request, ctx.user, payload.model_dump(by_alias=True, exclude_unset=True)
    )
    await db.commit()
    return ok(
        ProfileResponse(**data).model_dump(by_alias=True)
        | {"verificationReset": bool(data.get("verificationReset"))}
    )


@router.get("/me/profile")
async def get_profile(
    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)
) -> dict:
    data = await user_service.profile_payload(db, ctx.user)
    return ok(ProfileResponse(**data).model_dump(by_alias=True))


@router.get("/me/sessions")
async def my_sessions(
    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)
) -> dict:
    rows = await user_service.my_sessions(db, ctx.user.id, ctx.session.id)
    return ok([SessionInfo(**row).model_dump(by_alias=True) for row in rows])
