"""Account endpoints: identity, profile, own sessions and deletion request."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, current_context
from app.core.errors import NotFound
from app.core.errors import AppError, Conflict
from app.integrations.storage import document_key, get_storage
from app.models.user import ParticipantProfile
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
from app.services.verification import validate_and_sanitize_upload
from app.core.config import get_settings

router = APIRouter(tags=["account"])
DOCUMENT_RETENTION_DAYS = 365


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


@router.post("/me/profile/documents")
async def upload_profile_document(
    kind: str = Form(pattern="^(college_id|iste_proof)$"),
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(current_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes_document + 1)
    if not data:
        raise AppError("Choose a file to upload.", code="VALIDATION_FAILED", status_code=422)
    if len(data) > settings.max_upload_bytes_document:
        raise AppError("The document is larger than 5 MB.", code="FILE_TOO_LARGE", status_code=413)
    profile = await db.scalar(
        select(ParticipantProfile).where(ParticipantProfile.user_id == ctx.user.id)
    )
    if profile is None:
        profile = ParticipantProfile(user_id=ctx.user.id)
        db.add(profile)
        await db.flush()
    if kind == "iste_proof" and not profile.iste_member:
        raise Conflict("ISTE proof is only required when ISTE membership is selected.")
    clean_data, mime_type = validate_and_sanitize_upload(data, file.content_type)
    key = document_key(file.filename)
    storage = get_storage()
    await storage.put(key, clean_data, mime_type)
    field = "college_id_document_key" if kind == "college_id" else "iste_proof_document_key"
    old_key = getattr(profile, field)
    setattr(profile, field, key)
    profile.documents_retention_until = datetime.now(UTC) + timedelta(days=DOCUMENT_RETENTION_DAYS)
    await db.commit()
    if old_key:
        try:
            await storage.delete(old_key)
        except Exception:
            pass
    return {"data": {"kind": kind, "uploaded": True, "retentionDays": DOCUMENT_RETENTION_DAYS}}


@router.get("/me/sessions")
async def my_sessions(
    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)
) -> dict:
    rows = await user_service.my_sessions(db, ctx.user.id, ctx.session.id)
    return ok([SessionInfo(**row).model_dump(by_alias=True) for row in rows])


@router.post("/me/deletion-request")
async def request_account_deletion(
    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)
) -> dict:
    await user_service.request_deletion(db, ctx.user)
    await db.commit()
    return ok({"status": "deletion_requested"})
