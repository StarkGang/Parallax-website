"""The permission catalogue and the single role -> permission map.

Roles are stored in the database; this map decides what each role may do.
A CI test walks the OpenAPI route table and fails any route without a declared
dependency, so deny-by-default is enforced rather than assumed.
"""

from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    EDITION_ADMIN = "edition_admin"
    FINANCE_ADMIN = "finance_admin"
    ELIGIBILITY_VERIFIER = "eligibility_verifier"
    EVENT_COORDINATOR = "event_coordinator"
    CHECKIN_STAFF = "checkin_staff"
    PARTICIPANT = "participant"


STAFF_ROLES = {
    Role.SUPER_ADMIN,
    Role.EDITION_ADMIN,
    Role.FINANCE_ADMIN,
    Role.ELIGIBILITY_VERIFIER,
    Role.EVENT_COORDINATOR,
    Role.CHECKIN_STAFF,
}

MFA_REQUIRED_ROLES = {
    Role.SUPER_ADMIN,
    Role.EDITION_ADMIN,
    Role.FINANCE_ADMIN,
    Role.ELIGIBILITY_VERIFIER,
}

ALL_PERMISSIONS = {
    "edition.read",
    "edition.write",
    "event.read",
    "event.write",
    "event.publish",
    "policy.read",
    "policy.write",
    "icon.write",
    "user.read",
    "user.read_pii",
    "user.write",
    "membership.write",
    "payment.read",
    "refund.request",
    "refund.approve",
    "verification.review",
    "registration.read",
    "registration.write",
    "team.read",
    "team.manage",
    "ticket.issue",
    "checkin.scan",
    "checkin.manage",
    "attendance.read",
    "attendance.write",
    "announcement.write",
    "certificate.write",
    "report.read",
    "audit.read",
    "export.data",
    "stats.read",
    "settings.manage",
    # Permission names used by the admin router. They are kept in the catalogue
    # so role grants and route checks share a single vocabulary.
    "policy.manage",
    "events.read",
    "events.write",
    "users.read",
    "users.manage",
    "staff.manage",
    "finance.read",
    "finance.write",
    "announcements.read",
    "announcements.write",
    "checkin.read",
    "checkin.write",
}

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.SUPER_ADMIN: set(ALL_PERMISSIONS),
    Role.EDITION_ADMIN: ALL_PERMISSIONS
    - {"refund.approve", "export.data"}
    | {"export.data"},
    Role.FINANCE_ADMIN: {
        "edition.read",
        "event.read",
        "events.read",
        "policy.read",
        "user.read",
        "users.read",
        "payment.read",
        "finance.read",
        "finance.write",
        "refund.request",
        "refund.approve",
        "registration.read",
        "report.read",
        "audit.read",
        "export.data",
        "stats.read",
    },
    Role.ELIGIBILITY_VERIFIER: {
        "edition.read",
        "event.read",
        "events.read",
        "user.read",
        "users.read",
        "user.read_pii",
        "verification.review",
        "registration.read",
        "report.read",
    },
    Role.EVENT_COORDINATOR: {
        "edition.read",
        "event.read",
        "event.write",
        "events.read",
        "events.write",
        "users.read",
        "registration.read",
        "team.read",
        "checkin.scan",
        "checkin.manage",
        "attendance.read",
        "attendance.write",
        "checkin.read",
        "checkin.write",
        "announcements.read",
        "announcement.write",
        "announcements.write",
        "report.read",
        "stats.read",
    },
    Role.CHECKIN_STAFF: {
        "edition.read",
        "event.read",
        "events.read",
        "registration.read",
        "ticket.issue",
        "checkin.scan",
        "checkin.manage",
        "checkin.read",
        "checkin.write",
        "attendance.read",
        "attendance.write",
    },
    Role.PARTICIPANT: set(),
}

# Roles that need a fresh TOTP step-up for sensitive writes.
STEP_UP_ACTIONS = {
    "policy.write",
    "event.write",
    "refund.approve",
    "membership.write",
    "export.data",
    "icon.write",
    "edition.write",
}


def permissions_for(role: str) -> set[str]:
    try:
        r = Role(role)
        if r == Role.SUPER_ADMIN:
            return set(ALL_PERMISSIONS)
        return ROLE_PERMISSIONS[r]
    except ValueError:
        if role == "super_admin":
            return set(ALL_PERMISSIONS)
        return set()


def has_permission(role: str, permission: str) -> bool:
    if role in {Role.SUPER_ADMIN, "super_admin"}:
        return True
    return permission in permissions_for(role)


def requires_mfa(role: str) -> bool:
    try:
        return Role(role) in MFA_REQUIRED_ROLES
    except ValueError:
        return False
