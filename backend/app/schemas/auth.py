import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import CamelModel


class RoleGrant(CamelModel):
    edition_id: uuid.UUID | None
    edition_name: str | None = None
    role: str


class MeResponse(CamelModel):
    id: uuid.UUID
    full_name: str
    email: str
    picture_url: str | None = None
    status: str
    phone: str | None = None
    roles: list[RoleGrant] = []
    auth_level: str
    mfa_enabled: bool = False
    mfa_required: bool = False
    profile_complete: bool = False
    student_verified: bool = False
    current_edition_id: uuid.UUID | None = None
    verification_status: str | None = "unverified"
    created_at: datetime | None = None


class MeEnvelope(CamelModel):
    data: MeResponse


class DevLoginRequest(CamelModel):
    role: str = "participant"
    email: str | None = None


class CsrfResponse(CamelModel):
    csrf_token: str


class SessionInfo(CamelModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    auth_level: str
    ip_prefix: str | None = None
    user_agent_hash: str | None = None
    current: bool = False


class ProfilePatch(CamelModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=24)
    college_name: str | None = Field(default=None, max_length=200)
    university_name: str | None = Field(default=None, max_length=200)
    course: str | None = Field(default=None, max_length=120)
    education_level: str | None = Field(default=None, pattern="^(B\\.Tech|Polytechnic)$")
    iste_member: bool | None = None
    accommodation_needed: bool | None = None
    privacy_consent: bool | None = None
    branch: str | None = Field(default=None, max_length=120)
    year_of_study: int | None = Field(default=None, ge=1, le=4)
    student_identifier: str | None = Field(default=None, max_length=60)
    institution_email: str | None = Field(default=None, max_length=320)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        digits = value.replace(" ", "").replace("-", "")
        if not digits.startswith("+") or not digits[1:].isdigit() or not 8 <= len(digits) <= 16:
            raise ValueError("Use an international phone number such as +919876543210")
        return digits


class ProfileResponse(CamelModel):
    full_name: str
    email: str
    phone: str | None = None
    college_name: str | None = None
    university_name: str | None = None
    course: str | None = None
    education_level: str | None = None
    iste_member: bool = False
    accommodation_needed: bool = False
    privacy_consent: bool = False
    college_id_uploaded: bool = False
    iste_proof_uploaded: bool = False
    branch: str | None = None
    year_of_study: int | None = None
    student_identifier_last4: str | None = None
    institution_email: str | None = None
    profile_complete: bool
    verification_required: bool = True


class MfaSetupResponse(CamelModel):
    otpauth_uri: str
    secret_preview: str


class MfaVerifyRequest(CamelModel):
    code: str = Field(min_length=6, max_length=8)


class MfaChallengeRequest(CamelModel):
    code: str | None = Field(default=None, max_length=8)
    recovery_code: str | None = Field(default=None, max_length=24)


class RecoveryCodesResponse(CamelModel):
    recovery_codes: list[str]


class DeletionRequestResponse(CamelModel):
    requested: bool
    message: str


class AdminInviteCreate(CamelModel):
    email: EmailStr
    roles: list[str] = Field(min_length=1)
    edition_id: uuid.UUID | None = None


class AdminInviteResponse(CamelModel):
    invite_url: str
    expires_at: datetime
    email: str


class MembershipGrant(CamelModel):
    email: EmailStr
    role: str
    edition_id: uuid.UUID | None = None
    status: str = "active"


__all__ = [
    "RoleGrant",
    "MeResponse",
    "MeEnvelope",
    "DevLoginRequest",
    "CsrfResponse",
    "SessionInfo",
    "ProfilePatch",
    "ProfileResponse",
    "MfaSetupResponse",
    "MfaVerifyRequest",
    "MfaChallengeRequest",
    "RecoveryCodesResponse",
    "DeletionRequestResponse",
    "AdminInviteCreate",
    "AdminInviteResponse",
    "MembershipGrant",
]
