"""Replaceable adapter boundary for student ID verification providers."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    status: str
    reference: str | None = None
    message: str | None = None


class StudentIdVerifier(Protocol):
    async def verify(self, *, user_id: str, education_level: str, document: bytes) -> ProviderResult: ...


class UnsupportedIsteVerifier:
    """Honest no-provider stub; this never claims that a student was verified."""

    async def verify(self, *, user_id: str, education_level: str, document: bytes) -> ProviderResult:
        del user_id, education_level, document
        return ProviderResult(
            provider="iste-unconfigured",
            status="unavailable",
            message="No ISTE student ID verification provider is configured.",
        )


def get_student_verifier() -> StudentIdVerifier:
    return UnsupportedIsteVerifier()
