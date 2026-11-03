"""Idempotent demo seed for local development.

Prices, caps, event rules, icons and copy all live here.
"""

from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.edition import (
    Announcement,
    ConventionEdition,
    EditionPolicy,
    Event,
    EventCategory,
    Icon,
)
from app.models.user import EditionMembership, User
from app.services import icons as icon_service

EDITION_SLUG = "parallax-2026"

CATEGORIES = (
    ("computing", "Computing", "cyan", 1),
    ("engineering", "Engineering", "amber", 2),
    ("robotics", "Robotics", "lime", 3),
    ("electronics", "Electronics", "orange", 4),
    ("design", "Design", "violet", 5),
)

EVENTS = (
    (
        "paper-presentation",
        "Paper Presentation",
        "computing",
        "individual",
        10000,
        15000,
        "paper-presentation",
        True,
        60,
        (1, 1),
    ),
    (
        "coding-competition",
        "Coding Competition",
        "computing",
        "individual",
        10000,
        15000,
        "coding-competition",
        True,
        80,
        (1, 1),
    ),
    (
        "circuit-debugging",
        "Circuit Debugging",
        "electronics",
        "individual",
        10000,
        15000,
        "circuit-debugging",
        False,
        50,
        (1, 1),
    ),
    (
        "cad-designing",
        "CAD Designing",
        "design",
        "individual",
        10000,
        15000,
        "cad-designing",
        False,
        40,
        (1, 1),
    ),
    (
        "soldering",
        "Soldering Sprint",
        "electronics",
        "individual",
        10000,
        15000,
        "soldering",
        False,
        40,
        (1, 1),
    ),
    (
        "data-analytics",
        "Data Analytics Sprint",
        "computing",
        "individual",
        15000,
        20000,
        "data-analytics",
        False,
        50,
        (1, 1),
    ),
    (
        "project-expo",
        "Project Expo",
        "engineering",
        "team",
        20000,
        30000,
        "project-expo",
        True,
        30,
        (2, 4),
    ),
    (
        "hackathon",
        "Hackathon",
        "computing",
        "team",
        20000,
        30000,
        "hackathon",
        True,
        25,
        (3, 4),
    ),
    (
        "line-follower",
        "Line Follower",
        "robotics",
        "team",
        15000,
        25000,
        "line-follower",
        True,
        35,
        (2, 3),
    ),
    (
        "maze-solving",
        "Maze Solving",
        "robotics",
        "team",
        15000,
        25000,
        "maze-solving",
        False,
        30,
        (2, 3),
    ),
    (
        "arduino-car-workshop",
        "Arduino Car Workshop",
        "robotics",
        "team",
        20000,
        35000,
        "arduino-car-workshop",
        False,
        25,
        (2, 2),
    ),
    (
        "ai-tools-for-everything",
        "AI Tools for Everything",
        "computing",
        "individual",
        10000,
        15000,
        "ai-tools-for-everything",
        False,
        60,
        (1, 1),
    ),
)

SUMMARIES = {
    "paper-presentation": "Present original research to faculty and industry judges. 12 minutes, 8 slides, no fluff.",
    "coding-competition": "Three algorithmic problems, ninety minutes, individual test-case scoring with partial credit.",
    "circuit-debugging": "Diagnose analog and digital faults on live test boards under strict clock pressure.",
    "cad-designing": "Parametric 3D mechanical modelling to strict functional assembly tolerances.",
    "soldering": "Surface mount and through-hole soldering speed, precision and inspection test.",
    "data-analytics": "Clean, model and extract insights from raw noisy datasets before the deadline.",
    "project-expo": "Showcase your working engineering prototype or hardware deployment to delegates.",
    "hackathon": "Twenty-four hours of rapid product prototyping and deployment. Midnight caffeine provided.",
    "line-follower": "Autonomous PID path tracing robots on high-curvature high-contrast race tracks.",
    "maze-solving": "Micromouse maze traversal algorithm competition with dynamic path planning.",
    "arduino-car-workshop": "Hands-on chassis fabrication, motor drivers and microcontroller programming.",
    "ai-tools-for-everything": "Practical generative AI, agents and local LLM workflows for modern engineers.",
}


def _at(days_from_now: int, hour: int = 9, minute: int = 0) -> datetime:
    base = datetime(2026, 11, 3, 0, 0, 0, tzinfo=UTC)
    return base + timedelta(days=days_from_now, hours=hour, minutes=minute)


async def seed_if_empty(db: AsyncSession) -> None:
    ext = (
        await db.execute(
            select(ConventionEdition).where(ConventionEdition.slug == EDITION_SLUG)
        )
    ).scalar_one_or_none()

    if ext is None:
        # Seed edition
        edition = ConventionEdition(
            slug=EDITION_SLUG,
            name="Parallax 2026",
            hero_headline="Parallax 2026",
            hero_subtitle="Two days of engineering, argued in public.",
            theme="Engineering in Public",
            organizer="ISTE Student Chapter, NSSCE",
            host="NSS College of Engineering, Palakkad",
            venue="NSSCE Campus, Palakkad",
            city="Palakkad, Kerala",
            starts_at=_at(1, 9, 0),
            ends_at=_at(2, 18, 0),
            registration_opens_at=_at(-30, 0, 0),
            registration_closes_at=_at(1, 12, 0),
            status="published",
            contact_email="iste@nssce.ac.in",
            allowed_email_domains=["nssce.ac.in", "gmail.com"],
        )
        db.add(edition)
        await db.flush()

        policy = EditionPolicy(
            edition_id=edition.id,
            version=1,
            is_current=True,
            pass_price_paise=35000,
            included_event_count=3,
            lunch_included_days=["day1", "day2"],
            included_selection_mode="up_to",
            included_value_cap_paise=45000,
            cap_inclusive=True,
            addon_requires_pass=True,
            team_members_require_pass=True,
            team_fee_basis_default="per_participant",
            hold_minutes=15,
            selection_change_deadline=_at(1, 10, 0),
            refund_rules={"allowed": True, "deadlineHours": 48},
            gst_note="Inclusive of all applicable taxes",
            reason="Initial policy for Parallax 2026",
        )
        db.add(policy)
        await db.flush()

        # Seed icons
        try:
            await icon_service.ensure_library_icons(db, edition.id)
        except Exception:
            pass

        icon_rows = (
            await db.execute(select(Icon).where(Icon.edition_id == edition.id))
        ).scalars().all()
        icons_by_name = {i.name: i.id for i in icon_rows}

        # Seed categories
        cats = {}
        for slug, name, accent, order in CATEGORIES:
            cat = EventCategory(
                edition_id=edition.id,
                slug=slug,
                name=name,
                accent=accent,
                display_order=order,
            )
            db.add(cat)
            await db.flush()
            cats[slug] = cat

        # Schedule distribution across Day 1 (Nov 4) and Day 2 (Nov 5) at NSSCE
        event_schedules = {
            "paper-presentation": (1, 9, 30, 13, 0, "CS Seminar Hall"),
            "coding-competition": (1, 10, 0, 12, 30, "Central Computing Facility"),
            "circuit-debugging": (1, 11, 0, 13, 30, "Electronics Lab 1"),
            "cad-designing": (1, 14, 0, 17, 0, "Mechanical CAD Complex"),
            "soldering": (1, 14, 30, 16, 30, "Instrumentation Lab"),
            "data-analytics": (1, 15, 0, 18, 0, "CCF Lab 2"),
            "project-expo": (2, 9, 30, 14, 0, "Main Auditorium"),
            "hackathon": (2, 10, 0, 18, 0, "Main Seminar Hall"),
            "line-follower": (2, 11, 0, 13, 30, "Robotics Arena"),
            "maze-solving": (2, 14, 0, 16, 30, "Robotics Arena"),
            "arduino-car-workshop": (2, 14, 30, 17, 30, "IoT & Embedded Systems Lab"),
            "ai-tools-for-everything": (2, 15, 0, 17, 30, "Auditorium Gallery Hall"),
        }

        # Seed events
        for (
            slug,
            title,
            cat_slug,
            fmt,
            base_val,
            addon_pr,
            icon_name,
            featured,
            cap,
            team_sz,
        ) in EVENTS:
            day_num, s_hr, s_min, e_hr, e_min, room = event_schedules.get(
                slug, (1, 10, 0, 13, 0, "Seminar Hall A")
            )
            ev = Event(
                edition_id=edition.id,
                category_id=cats[cat_slug].id,
                icon_id=icons_by_name.get(icon_name),
                slug=slug,
                title=title,
                summary=SUMMARIES.get(slug, title),
                description_md=f"# {title}\n\nDetailed guidelines for {title}.",
                rules_md="1. Follow standard code of conduct.\n2. Decisions of judges are final.",
                prizes_md="1st Prize: Rs. 10,000\n2nd Prize: Rs. 5,000",
                format=fmt,
                team_min_size=team_sz[0],
                team_max_size=team_sz[1],
                base_value_paise=base_val,
                included_eligible=True,
                addon_price_paise=addon_pr,
                capacity=cap,
                starts_at=_at(day_num, s_hr, s_min),
                ends_at=_at(day_num, e_hr, e_min),
                registration_opens_at=_at(-30, 0, 0),
                registration_closes_at=_at(day_num, s_hr - 1, 0),
                venue_room=room,
                status="published",
                is_featured=featured,
                accent=cats[cat_slug].accent,
            )
            db.add(ev)

        # Seed announcements
        a = Announcement(
            edition_id=edition.id,
            title="Welcome to Parallax 2026!",
            body_md="Registrations are officially open for all technical and robotics events at NSS College of Engineering.",
            audience="public",
            published_at=_at(0, 8, 0),
        )
        db.add(a)
    else:
        edition = ext

    # Seed administrator / owner (configurable via env BOOTSTRAP_OWNER_EMAIL or DEV_ADMIN_EMAIL)
    settings = get_settings()
    admin_email = (
        settings.bootstrap_owner_email
        or settings.dev_admin_email
        or "owner@parallax.local"
    ).strip().lower()

    existing_owner = (
        await db.execute(select(User).where(User.email_normalized == admin_email))
    ).scalar_one_or_none()

    if existing_owner is None:
        admin_user = User(
            email=admin_email,
            email_normalized=admin_email,
            full_name="Convention Administrator",
            email_verified=True,
            status="active",
            google_sub=f"seed-admin-{admin_email}",
        )
        db.add(admin_user)
        await db.flush()
    else:
        admin_user = existing_owner

    # Ensure admin has owner membership for this edition
    existing_mem = (
        await db.execute(
            select(EditionMembership).where(
                EditionMembership.user_id == admin_user.id,
                EditionMembership.edition_id == edition.id,
            )
        )
    ).scalar_one_or_none()

    if existing_mem is None:
        db.add(
            EditionMembership(
                user_id=admin_user.id,
                edition_id=edition.id,
                role="owner",
                status="active",
            )
        )

    await db.commit()


async def main() -> None:
    from app.db.base import Base
    from app.db.session import get_engine, session_scope

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_scope() as db:
        await seed_if_empty(db)
    print("Database seeding completed successfully.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
