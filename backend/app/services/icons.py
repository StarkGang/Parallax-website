"""Icon library and the upload sanitiser (SVG allow-list, PNG re-encode)."""



import base64

import hashlib

import io

import re

import uuid

from datetime import UTC, datetime

from pathlib import Path



from fastapi import Request

from sqlalchemy import func, select

from sqlalchemy.ext.asyncio import AsyncSession

from defusedxml import ElementTree

from xml.etree import ElementTree as StdElementTree

from PIL import Image



from app.core.config import get_settings

from app.core.errors import Conflict, AppError, ValidationFailed

from app.core.logging import get_logger

from app.integrations.storage import get_storage

from app.models.edition import Event, Icon

from app.services.audit import record



ICON_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "icons"

# Icons belong in the object bucket next to the event banners, not in the
# database: a bytea column meant every icon render was a database round trip,
# backups carried megabytes of artwork, and the API had to stream images out
# of Postgres. The column stays only as a fallback for rows written before;
# new uploads are content-addressed objects.
ICON_EXTENSIONS = {"image/svg+xml": "svg", "image/png": "png"}


def icon_storage_key(edition_id: uuid.UUID, digest: str, mime: str) -> str:
    ext = ICON_EXTENSIONS.get(mime, "bin")
    return f"icons/{edition_id}/{digest}.{ext}"


async def store_icon_bytes(
    edition_id: uuid.UUID, payload: bytes, mime: str, digest: str
) -> str | None:
    """Upload the sanitised bytes; return the key, or None if the bucket is down.

    A storage outage must not lose an icon the organiser just uploaded, so the
    caller falls back to the column and the public route serves either.
    """
    key = icon_storage_key(edition_id, digest, mime)
    try:
        return await get_storage().put(key, payload, mime)
    except Exception as exc:  # noqa: BLE001 - any storage failure falls back
        logger.warning("icon_storage_failed", key=key, error=str(exc)[:200])
        return None

logger = get_logger("icons")



SVG_NS = "http://www.w3.org/2000/svg"

ALLOWED_ELEMENTS = {

    "svg",

    "g",

    "path",

    "circle",

    "ellipse",

    "rect",

    "line",

    "polyline",

    "polygon",

    "title",

}

ALLOWED_ATTRIBUTES = {

    "viewBox",

    "d",

    "fill",

    "stroke",

    "stroke-width",

    "stroke-linecap",

    "stroke-linejoin",

    "fill-rule",

    "clip-rule",

    "cx",

    "cy",

    "r",

    "rx",

    "ry",

    "x",

    "y",

    "x1",

    "y1",

    "x2",

    "y2",

    "points",

    "width",

    "height",

    "transform",

    "opacity",

    "xmlns",

}





def _local(tag: str) -> str:

    return tag.rsplit("}", 1)[-1]





def sanitize_svg(data: bytes, *, recolorable: bool) -> tuple[bytes, int, int]:

    settings = get_settings()

    if len(data) > settings.max_upload_bytes_icon_svg:

        raise AppError("SVG icons must be 64 KB or smaller.", code="FILE_TOO_LARGE", status_code=413)

    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:

        raise ValidationFailed("SVG documents with a DTD are not allowed.", code="ICON_REJECTED")

    try:

        root = ElementTree.fromstring(data)

    except Exception:

        raise ValidationFailed("That file is not valid SVG.", code="ICON_REJECTED")



    if _local(root.tag) != "svg":

        raise ValidationFailed("The root element must be <svg>.", code="ICON_REJECTED")

    view_box = root.attrib.get("viewBox")

    if not view_box:

        raise ValidationFailed("SVG icons need a viewBox.", code="ICON_REJECTED")

    try:

        min_x, min_y, width, height = (float(part) for part in view_box.replace(",", " ").split())

    except ValueError:

        raise ValidationFailed("The viewBox is not valid.", code="ICON_REJECTED")

    if width <= 0 or height <= 0:

        raise ValidationFailed("The viewBox must have a positive size.", code="ICON_REJECTED")

    if max(width, height) / min(width, height) > 2:

        raise ValidationFailed("Icons must have an aspect ratio of at most 2:1.", code="ICON_REJECTED")



    for element in root.iter():

        name = _local(element.tag)

        if name not in ALLOWED_ELEMENTS:

            raise ValidationFailed(

                f"<{name}> is not allowed in an icon.", details={"element": name}, code="ICON_REJECTED"

            )

        for attribute in list(element.attrib):

            if attribute.startswith("{") and not attribute.startswith(f"{{{SVG_NS}}}"):

                raise ValidationFailed(

                    f"Attribute {attribute} is not allowed.", details={"attribute": attribute}, code="ICON_REJECTED"

                )

            local = _local(attribute)

            if local.startswith("on") or local in ("href", "style", "class", "id"):

                raise ValidationFailed(

                    f"Attribute {local} is not allowed.", details={"attribute": local}, code="ICON_REJECTED"

                )

            if local not in ALLOWED_ATTRIBUTES:

                raise ValidationFailed(

                    f"Attribute {local} is not allowed.", details={"attribute": local}, code="ICON_REJECTED"

                )

        if recolorable and name != "svg":

            for key in ("fill", "stroke"):

                value = element.attrib.get(key)

                if value and value.lower() not in ("none", "currentcolor"):

                    element.attrib[key] = "currentColor"



    # Re-serialise from the parsed tree: comments, processing instructions and

    # anything outside the allow-list never reach the output.

    # register_namespace lives on the stdlib module only: defusedxml re-exports

    # the parsing and serialising helpers but not the prefix registry.

    StdElementTree.register_namespace("", SVG_NS)

    output = StdElementTree.tostring(root, encoding="utf-8")

    if b"<script" in output.lower() or b"javascript:" in output.lower():

        raise ValidationFailed("The icon contains executable content.", code="ICON_REJECTED")

    return output, int(round(width)), int(round(height))





def sanitize_png(data: bytes) -> tuple[bytes, int, int]:

    settings = get_settings()

    if len(data) > settings.max_upload_bytes_icon_png:

        raise AppError("PNG icons must be 256 KB or smaller.", code="FILE_TOO_LARGE", status_code=413)

    try:

        with Image.open(io.BytesIO(data)) as image:

            image.verify()

        with Image.open(io.BytesIO(data)) as image:

            image = image.convert("RGBA")

            width, height = image.size

            if not (64 <= width <= 512 and 64 <= height <= 512):

                raise ValidationFailed(

                    "PNG icons must be between 64 and 512 pixels per side.", code="ICON_REJECTED"

                )

            buffer = io.BytesIO()

            image.save(buffer, format="PNG", optimize=True)

            return buffer.getvalue(), width, height

    except ValidationFailed:

        raise

    except Exception:

        raise ValidationFailed("That file is not a valid PNG.", code="ICON_REJECTED")





def detect(data: bytes) -> str:

    if data.startswith(b"\x89PNG\r\n\x1a\n"):

        return "image/png"

    head = data.lstrip()[:200].lower()

    if head.startswith(b"<svg") or head.startswith(b"<?xml") and b"<svg" in head:

        return "image/svg+xml"

    raise ValidationFailed("Only SVG and PNG icons are accepted.", code="ICON_REJECTED")





async def create_icon(

    db: AsyncSession,

    request: Request,

    *,

    edition_id: uuid.UUID,

    data: bytes,

    name: str,

    recolorable: bool,

    actor_id: uuid.UUID,

    actor_role: str | None,

) -> Icon:

    mime = detect(data)

    if mime == "image/svg+xml":

        payload, width, height = sanitize_svg(data, recolorable=recolorable)

    else:

        payload, width, height = sanitize_png(data)

        recolorable = False

    digest = hashlib.sha256(payload).hexdigest()



    existing = await db.scalar(

        select(Icon).where(Icon.edition_id == edition_id, Icon.sha256 == digest, Icon.status == "active")

    )

    if existing:

        return existing



    storage_key = await store_icon_bytes(edition_id, payload, mime, digest)

    icon = Icon(

        edition_id=edition_id,

        kind="upload",

        name=name[:120],

        mime=mime,

        data=None if storage_key else payload,

        storage_key=storage_key,

        size_bytes=len(payload),

        width=width,

        height=height,

        sha256=digest,

        recolorable=recolorable,

        status="active",

        uploaded_by=actor_id,

    )

    db.add(icon)

    await db.flush()

    await record(

        db,

        request,

        actor_id=actor_id,

        actor_role=actor_role,

        action="icon.uploaded",

        resource_type="icon",

        resource_id=str(icon.id),

        after={"name": icon.name, "mime": mime, "sizeBytes": icon.size_bytes},

    )

    return icon





_EMBEDDED_PNG = re.compile(r"data:img/png;base64,([A-Za-z0-9+/=\s]+)")





def _bundled_payload(path: Path) -> tuple[bytes, str, int, int]:

    """Bundled brochure art is PNG wrapped in an SVG shell; store the PNG itself."""

    raw = path.read_bytes()

    match = _EMBEDDED_PNG.search(raw.decode("utf-8", "ignore"))

    if match:

        try:

            png = base64.b64decode(re.sub(r"\s+", "", match.group(1)))

            data, width, height = sanitize_png(png)

            return data, "image/png", width, height

        except Exception:

            pass

    data, width, height = sanitize_svg(raw, recolorable=True)

    return data, "image/svg+xml", width, height





def library_icons() -> list[tuple[str, Path]]:

    if not ICON_ASSETS.exists():

        return []

    return [(path.stem, path) for path in sorted(ICON_ASSETS.glob("*.svg"))]





async def ensure_library_icons(db: AsyncSession, edition_id: uuid.UUID) -> dict[str, uuid.UUID]:

    """Seed the bundled icon set once per edition; idempotent by library_key."""

    if not ICON_ASSETS.exists():

        return {}

    ICON_ASSETS.mkdir(parents=True, exist_ok=True)

    existing = {

        icon.name: icon

        for icon in (

            await db.execute(

                select(Icon).where(
                    Icon.edition_id == edition_id,
                    Icon.kind == "library",
                    # An archived icon must not be resurrected as active on the
                    # next boot; it keeps its archived status and id.
                    Icon.status != "deleted",
                )

            )

        ).scalars()

    }

    mapping: dict[str, uuid.UUID] = {}

    for name, path in library_icons():

        if name in existing:

            mapping[name] = existing[name].id

            continue

        try:

            payload, mime, width, height = _bundled_payload(path)

        except AppError as exc:

            # A bundled asset that fails validation is skipped, never fatal at boot.

            logger.warning("icon_skipped", name=name, reason=exc.code)

            continue

        digest = hashlib.sha256(payload).hexdigest()

        storage_key = await store_icon_bytes(edition_id, payload, mime, digest)

        icon = Icon(

            edition_id=edition_id,

            kind="library",

            name=name,

            library_key=name,

            mime=mime,

            data=None if storage_key else payload,

            storage_key=storage_key,

            size_bytes=len(payload),

            width=width,

            height=height,

            sha256=digest,

            recolorable=mime == "image/svg+xml",

            status="active",

        )

        db.add(icon)

        await db.flush()

        mapping[name] = icon.id

    return mapping





def icon_url(icon: Icon) -> str:

    """Where the browser fetches this icon.


    Storage-backed icons go straight to the bucket/CDN; rows written before
    the move (and uploads made while the bucket was down) are still served by
    the API route out of ``data``.
    """

    if icon.storage_key:

        url = get_storage().public_url(icon.storage_key)

        if url.startswith("http"):

            return url

    return f"/api/v1/public/icons/{icon.id}"





def icon_payload(icon: Icon) -> dict:

    return {

        "id": str(icon.id),

        "name": icon.name,

        "kind": icon.kind,

        "mime": icon.mime,

        "sizeBytes": icon.size_bytes,

        "recolorable": icon.recolorable,

        "status": icon.status,

        "libraryKey": icon.library_key,

        "url": icon_url(icon),

    }





async def listed(db: AsyncSession, edition_id: uuid.UUID) -> list[dict]:
    rows = list(
        (
            await db.execute(
                select(Icon)
                .where(Icon.edition_id == edition_id, Icon.status == "active")
                .order_by(Icon.kind, Icon.name)
            )
        ).scalars()
    )
    return [icon_payload(row) for row in rows]


async def archive(
    db: AsyncSession,
    request: Request,
    icon: Icon,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> None:
    # Archiving an icon that an event still renders leaves that event with a
    # missing image, and the boot seeder would re-create the icon as active.
    in_use = (
        await db.execute(
            select(func.count())
            .select_from(Event)
            .where(Event.icon_id == icon.id)
        )
    ).scalar() or 0
    if in_use:
        raise Conflict(
            f"{in_use} event(s) still use this icon. Change them first.",
            code="ICON_IN_USE",
        )
    icon.status = "archived"

    # The bytes are no longer referenced, so drop the object too: an archived
    # icon used to keep its blob forever.
    if icon.storage_key:
        try:
            await get_storage().delete(icon.storage_key)
        except Exception as exc:  # noqa: BLE001 - archival must not fail on storage
            logger.warning(
                "icon_storage_delete_failed", key=icon.storage_key, error=str(exc)[:200]
            )
        icon.storage_key = None
    icon.data = None

    await record(
        db,
        request,
        actor_id=actor_id,
        actor_role=actor_role,
        action="icon.archived",
        resource_type="icon",
        resource_id=str(icon.id),
        after={"archivedAt": datetime.now(UTC).isoformat()},
    )
    await db.flush()
