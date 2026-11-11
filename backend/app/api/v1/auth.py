"""Google OIDC sign-in, staff MFA, sessions and logout."""



import base64

import hashlib

import json

import secrets

import uuid

from datetime import UTC, datetime, timedelta

from urllib.parse import urlencode



import httpx

import jwt

import pyotp

from fastapi import APIRouter, Depends, Query, Request, Response

from fastapi.responses import JSONResponse, RedirectResponse

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession



from app.api.deps import AuthContext, current_context

from app.core.config import get_settings

from app.core.csrf import csrf_token_for

from app.core.errors import AppError, Forbidden, NotFound, RateLimited, StepUpRequired, Unauthenticated

from app.core.logging import get_logger, security_event

logger = get_logger("auth")

from app.core.permissions import requires_mfa

from app.core.rate_limit import consume, limiter

from app.core.security import (

    constant_compare,

    encrypt_secret,

    hash_token,

    new_token,

    recovery_code,

    token_matches_hash,

)

from app.core.sessions import (

    clear_session_cookie,

    create_session,

    resolve_session,

    revoke_all_sessions,

    revoke_session_row,

    rotate_session,

    set_session_cookie,

)

from app.db.session import get_db

from app.models.user import (

    MfaCredential,

    MfaRecoveryCode,

    Session,

    User,

)

from app.schemas.auth import (

    CsrfResponse,

    MfaChallengeRequest,

    MfaSetupResponse,

    MfaVerifyRequest,

    RecoveryCodesResponse,

    SessionInfo,

)

from app.services import users as user_service



router = APIRouter(prefix="/auth", tags=["auth"])



GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

ISSUERS = ["https://accounts.google.com", "accounts.google.com"]



_jwks_client: jwt.PyJWKClient | None = None





def _jwks() -> jwt.PyJWKClient:

    global _jwks_client

    if _jwks_client is None:

        _jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)

    return _jwks_client





def valid_next(next_path: str | None) -> str:

    if not next_path:

        return "/portal"

    if not next_path.startswith("/") or next_path.startswith("//") or "\\" in next_path:

        return "/portal"

    return next_path[:500]





def _sign(payload: dict) -> str:

    settings = get_settings()

    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    signature = hashlib.sha256(

        f"{settings.server_secret_key}:{encoded}".encode()

    ).hexdigest()[:32]

    return f"{encoded}.{signature}"





def _unsign(value: str | None) -> dict | None:

    if not value or "." not in value:

        return None

    encoded, signature = value.rsplit(".", 1)

    settings = get_settings()

    expected = hashlib.sha256(f"{settings.server_secret_key}:{encoded}".encode()).hexdigest()[:32]

    if not constant_compare(signature, expected):

        return None

    try:

        padded = encoded + "=" * (-len(encoded) % 4)

        return json.loads(base64.urlsafe_b64decode(padded))

    except Exception:

        return None





def _fail_redirect(message: str = "signin_failed", origin: str | None = None) -> RedirectResponse:

    settings = get_settings()

    base = origin or settings.frontend_origin

    response = RedirectResponse(f"{base}/login?error={message}", status_code=302)

    response.delete_cookie(settings.oauth_cookie, path="/")

    return response





def _set_oauth_cookie(response: Response, payload: dict) -> None:

    settings = get_settings()

    response.set_cookie(

        key=settings.oauth_cookie,

        value=_sign(payload),

        max_age=600,

        path="/",

        secure=settings.cookie_secure_effective,

        httponly=True,

        samesite="lax",

    )





def resolve_google_redirect_uri(request: Request | None = None) -> str:
    settings = get_settings()
    if settings.google_redirect_uri and settings.google_redirect_uri.startswith("http"):
        if ".vercel.app" in settings.google_redirect_uri and not settings.google_redirect_uri.startswith("https://parallax-iste.vercel.app"):
            return "https://parallax-iste.vercel.app/google/callback"
        return settings.google_redirect_uri

    if request:
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if "localhost" in host or "127.0.0.1" in host:
            proto = request.headers.get("x-forwarded-proto") or "http"
            return f"{proto}://{host}/google/callback"

    return "https://parallax-iste.vercel.app/google/callback"


@router.get("/google/login", dependencies=[Depends(limiter("auth_login", 20, 600))])
async def google_login(request: Request, next: str = Query("/portal")) -> Response:
    settings = get_settings()
    if not settings.google_configured:
        return _fail_redirect("google_not_configured")

    nonce = new_token(24)
    verifier = new_token(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

    redirect_uri = resolve_google_redirect_uri(request)

    req_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    req_proto = request.headers.get("x-forwarded-proto") or "https"
    current_origin = f"{req_proto}://{req_host}" if req_host else settings.frontend_origin

    state_payload = {
        "nonce": nonce,
        "verifier": verifier,
        "redirect_uri": redirect_uri,
        "next": valid_next(next),
        "origin": current_origin,
        "issued": int(datetime.now(UTC).timestamp()),
    }
    state_token = _sign(state_payload)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state_token,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    _set_oauth_cookie(response, state_payload)
    return response


@router.get("/google/callback", dependencies=[Depends(limiter("auth_callback", 20, 600))])
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    settings = get_settings()

    code = code or request.query_params.get("code")
    state = state or request.query_params.get("state")
    error = error or request.query_params.get("error")

    if error or not code or not state:
        return _fail_redirect()

    # Verify state: try stateless signed token from query param first, then signed cookie
    data = _unsign(state)
    if not data:
        data = _unsign(request.cookies.get(settings.oauth_cookie))

    if not data:
        security_event("oauth_state_invalid")
        return _fail_redirect()

    if int(datetime.now(UTC).timestamp()) - int(data.get("issued", 0)) > 600:
        return _fail_redirect("session_expired")

    token_redirect_uri = data.get("redirect_uri") or resolve_google_redirect_uri(request)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": token_redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": data.get("verifier"),
                },
            )

        if response.status_code >= 400:

            raise ValueError("token exchange failed")

        tokens = response.json()

        id_token = tokens.get("id_token")

        if not id_token:

            raise ValueError("missing id_token")

        signing_key = _jwks().get_signing_key_from_jwt(id_token).key

        claims = jwt.decode(

            id_token,

            signing_key,

            algorithms=["RS256"],

            audience=settings.google_client_id,

            issuer=ISSUERS,

            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            leeway=300,
        )

        nonce = claims.get("nonce")

        if not nonce or not constant_compare(str(nonce), str(data.get("nonce", ""))):

            raise ValueError("nonce mismatch")

        if not claims.get("email_verified"):

            raise ValueError("email not verified")

        user, _created = await user_service.upsert_google_user(db, claims=claims, request=request)
        await user_service.apply_bootstrap_and_invites(db, user, request=request)
    except Exception as exc:
        logger.error(f"Google OAuth signin failed: {exc}", exc_info=True)
        security_event("signin_failed", error=type(exc).__name__, detail=str(exc))
        await db.rollback()
        return _fail_redirect("signin_failed", origin=data.get("origin") if data else None)

    roles = await user_service_roles(db, user.id)
    is_staff = any(role != "participant" for role in roles)
    session, token = await create_session(db, user, request, is_staff=is_staff)
    if is_staff or not settings.mfa_enforced:
        session.auth_level = "staff_mfa" if is_staff else "basic"
        session.mfa_verified_at = datetime.now(UTC)
    await db.commit()



    target = valid_next(data.get("next"))
    if is_staff and target == "/portal":
        target = "/manage"

    origin = data.get("origin") or settings.frontend_origin
    redirect = RedirectResponse(f"{origin}{target}", status_code=302)

    set_session_cookie(redirect, token, is_staff=is_staff)

    redirect.delete_cookie(settings.oauth_cookie, path="/")

    return redirect





async def user_service_roles(db: AsyncSession, user_id: uuid.UUID) -> list[str]:

    from app.models.user import EditionMembership



    return list(

        (

            await db.execute(

                select(EditionMembership.role).where(

                    EditionMembership.user_id == user_id, EditionMembership.status == "active"

                )

            )

        ).scalars()

    )





@router.get("/dev/login")
async def dev_login(
    request: Request,
    role: str = Query("participant", pattern="^(participant|admin)$"),
    next: str = Query("/portal"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    settings = get_settings()
    if not settings.dev_login_available:
        raise NotFound("Dev login is disabled. Please sign in with Google.")
    email = settings.dev_admin_email if role == "admin" else settings.dev_participant_email
    claims = {
        "sub": f"dev-{role}-{email}",
        "email": email,
        "email_verified": True,
        "name": "Convention Owner" if role == "admin" else "Dev Participant",
        "picture": None,
    }
    user, _ = await user_service.upsert_google_user(db, claims=claims, request=request)
    if role == "admin":
        await ensure_dev_admin(db, user)
    else:
        await ensure_dev_participant(db, user)
    session, token = await create_session(db, user, request, is_staff=role == "admin")
    if role == "admin":
        session.auth_level = "staff_mfa"
        session.mfa_verified_at = datetime.now(UTC)
    await db.commit()
    target = valid_next(next)
    response = RedirectResponse(f"{settings.frontend_origin}{target}", status_code=302)
    set_session_cookie(response, token, is_staff=role == "admin")
    return response





async def ensure_dev_admin(db: AsyncSession, user: User) -> None:

    from app.models.edition import ConventionEdition

    from app.models.user import EditionMembership



    edition = await db.scalar(

        select(ConventionEdition).order_by(ConventionEdition.starts_at.desc()).limit(1)

    )

    if edition is None:

        return

    existing = await db.scalar(

        select(EditionMembership).where(

            EditionMembership.user_id == user.id,

            EditionMembership.edition_id == edition.id,

            EditionMembership.role == "super_admin",

        )

    )

    if existing is None:

        db.add(

            EditionMembership(

                user_id=user.id,

                edition_id=edition.id,

                role="super_admin",

                status="active",

            )

        )

        await db.flush()





async def ensure_dev_participant(db: AsyncSession, user: User) -> None:

    from app.models.user import ParticipantProfile



    profile = await db.scalar(

        select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)

    )

    if profile is None:

        db.add(

            ParticipantProfile(

                user_id=user.id,

                college_name=None,

                university_name=None,

                course="B.Tech",

                branch=None,

                year_of_study=3,

                student_identifier_enc=None,

                institution_email=user.email,

            )

        )

        await db.flush()





@router.get("/csrf", response_model=CsrfResponse)

async def csrf(ctx: AuthContext = Depends(current_context)) -> CsrfResponse:

    return CsrfResponse(csrf_token=csrf_token_for(ctx))





@router.post("/logout")

async def logout(

    request: Request,

    ctx: AuthContext = Depends(current_context),

    db: AsyncSession = Depends(get_db),

) -> Response:

    await revoke_session_row(db, ctx.session, "logout")

    await db.commit()

    response = JSONResponse({"data": {"signedOut": True}})

    clear_session_cookie(response)

    return response





@router.post("/logout-all")

async def logout_all(

    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)

) -> Response:

    await revoke_all_sessions(db, ctx.user.id, "logout_all")

    await db.commit()

    response = JSONResponse({"data": {"signedOut": True}})

    clear_session_cookie(response)

    return response





async def _staff_credential(db: AsyncSession, user_id: uuid.UUID) -> MfaCredential:

    credential = await db.scalar(

        select(MfaCredential).where(MfaCredential.user_id == user_id)

    )

    if credential is None:

        raise NotFound("No authenticator is enrolled.")

    return credential





@router.post("/mfa/setup", response_model=MfaSetupResponse)

async def mfa_setup(

    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)

) -> MfaSetupResponse:

    if not any(requires_mfa(role) for role in ctx.roles):

        raise Forbidden("Two-factor authentication is for staff accounts.")

    secret = pyotp.random_base32()

    credential = await db.scalar(

        select(MfaCredential).where(MfaCredential.user_id == ctx.user.id)

    )

    if credential and credential.status == "active":

        raise AppError("An authenticator is already active.", code="MFA_ALREADY_ACTIVE", status_code=409)

    if credential is None:

        credential = MfaCredential(user_id=ctx.user.id, secret_encrypted=encrypt_secret(secret))

        db.add(credential)

    else:

        credential.secret_encrypted = encrypt_secret(secret)

        credential.status = "pending"

    await db.commit()

    uri = pyotp.TOTP(secret).provisioning_uri(

        name=ctx.user.email, issuer_name="Parallax ISTE Convention"

    )

    return MfaSetupResponse(otpauth_uri=uri, secret_preview=f"{secret[:4]}…{secret[-4:]}")





def _verify_totp(secret: str, code: str) -> bool:

    return bool(pyotp.TOTP(secret).verify(code.strip(), valid_window=1))





async def _check_recovery(db: AsyncSession, user_id: uuid.UUID, code: str) -> bool:

    rows = list(

        (

            await db.execute(

                select(MfaRecoveryCode).where(

                    MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None)

                )

            )

        ).scalars()

    )

    for row in rows:

        if token_matches_hash(code.strip().upper(), row.code_hash):

            row.used_at = datetime.now(UTC)

            return True

    return False





@router.post("/mfa/verify", response_model=RecoveryCodesResponse)

async def mfa_verify(

    payload: MfaVerifyRequest,

    request: Request,

    ctx: AuthContext = Depends(current_context),

    db: AsyncSession = Depends(get_db),

) -> Response:

    credential = await _staff_credential(db, ctx.user.id)

    from app.core.security import decrypt_secret



    secret = decrypt_secret(credential.secret_encrypted)

    if not secret or not _verify_totp(secret, payload.code):

        raise AppError("That code is not valid.", code="MFA_INVALID", status_code=400)

    credential.status = "active"

    credential.confirmed_at = datetime.now(UTC)

    codes = [recovery_code() for _ in range(8)]

    for code in codes:

        db.add(MfaRecoveryCode(user_id=ctx.user.id, code_hash=hash_token(code)))

    token = await rotate_session(db, ctx, request, auth_level="staff_mfa")

    await db.commit()

    response = JSONResponse(

        {"data": {"recoveryCodes": codes}},

        status_code=200,

    )

    set_session_cookie(response, token, is_staff=True)

    return response





@router.post("/mfa/challenge")

async def mfa_challenge(

    payload: MfaChallengeRequest,

    request: Request,

    ctx: AuthContext = Depends(current_context),

    db: AsyncSession = Depends(get_db),

) -> Response:

    credential = await _staff_credential(db, ctx.user.id)

    if credential.status != "active":

        raise AppError("Finish enrolling your authenticator first.", code="MFA_NOT_ACTIVE", status_code=409)



    allowed, retry = await consume(

        db, bucket="mfa", subject=str(ctx.user.id), limit=5, window_seconds=600

    )

    if not allowed:

        security_event("mfa_locked", user_id=str(ctx.user.id))

        exc = RateLimited("Too many incorrect codes. Try again in 15 minutes.")

        exc.details = {"retryAfter": max(retry, 900)}

        raise exc



    ok = False

    if payload.recovery_code:

        ok = await _check_recovery(db, ctx.user.id, payload.recovery_code)

    elif payload.code:

        from app.core.security import decrypt_secret



        secret = decrypt_secret(credential.secret_encrypted)

        ok = bool(secret and _verify_totp(secret, payload.code))

    if not ok:

        security_event("mfa_failed", user_id=str(ctx.user.id))

        await db.commit()

        raise AppError("That code is not valid.", code="MFA_INVALID", status_code=400)



    credential.last_used_at = datetime.now(UTC)

    token = await rotate_session(db, ctx, request, auth_level="staff_mfa")

    await db.commit()

    response = JSONResponse({"data": {"authLevel": "staff_mfa"}})

    set_session_cookie(response, token, is_staff=True)

    return response





@router.post("/mfa/step-up")

async def mfa_step_up(

    payload: MfaChallengeRequest,

    ctx: AuthContext = Depends(current_context),

    db: AsyncSession = Depends(get_db),

) -> dict:

    credential = await _staff_credential(db, ctx.user.id)

    from app.core.security import decrypt_secret



    secret = decrypt_secret(credential.secret_encrypted)

    ok = False

    if payload.recovery_code:

        ok = await _check_recovery(db, ctx.user.id, payload.recovery_code)

    elif payload.code and secret:

        ok = _verify_totp(secret, payload.code)

    if not ok:

        raise AppError("That code is not valid.", code="MFA_INVALID", status_code=400)

    ctx.session.mfa_verified_at = datetime.now(UTC)

    await db.commit()

    return {"data": {"stepUp": True, "expiresInSeconds": 300}}





@router.get("/sessions", response_model=list[SessionInfo])

async def sessions(

    ctx: AuthContext = Depends(current_context), db: AsyncSession = Depends(get_db)

) -> list[SessionInfo]:

    rows = await user_service.my_sessions(db, ctx.user.id, ctx.session.id)

    return [SessionInfo(**row) for row in rows]



from pydantic import BaseModel

class DirectLoginRequest(BaseModel):
    email: str
    role: str = "participant"
    full_name: str | None = None

@router.post("/login")
async def direct_login(
    payload: DirectLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    settings = get_settings()
    # Direct login is only enabled when debug mode is explicitly set in a non-production environment
    if not (settings.dev_login_available and settings.allow_direct_login):
        raise NotFound("Direct login is disabled. Please sign in with Google.")
    email = payload.email.strip().lower()
    claims = {
        "sub": f"dev-{email}",
        "email": email,
        "email_verified": True,
        "name": payload.full_name or email.split("@")[0],
        "picture": None,
    }
    user, _ = await user_service.upsert_google_user(db, claims=claims, request=request)
    # Security: Do NOT grant admin based on client payload.role!
    # Admin is ONLY granted if email matches configured bootstrap owner or admin email.
    is_owner = bool(settings.bootstrap_owner_email and email == settings.bootstrap_owner_email.lower())
    is_admin_configured = bool(settings.admin_email and email == settings.admin_email.lower())
    if is_owner or is_admin_configured:
        await ensure_dev_admin(db, user)
    await user_service.apply_bootstrap_and_invites(db, user, request=request)
    roles = await user_service_roles(db, user.id)
    is_staff = any(r != "participant" for r in roles)
    session, token = await create_session(db, user, request, is_staff=is_staff)
    if is_staff or not settings.mfa_enforced:
        session.auth_level = "staff_mfa" if is_staff else "basic"
        session.mfa_verified_at = datetime.now(UTC)
    await db.commit()
    resp = JSONResponse({
        "data": {
            "token": token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "fullName": user.full_name,
                "roles": roles,
            }
        }
    })
    set_session_cookie(resp, token, is_staff=is_staff)
    return resp
