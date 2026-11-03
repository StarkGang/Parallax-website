"""Icon library and the upload sanitiser (SVG allow-list, PNG re-encode)."""



import base64

import hashlib

import io

import re

import uuid

from datetime import UTC, datetime

from pathlib import Path



from fastapi import Request

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from defusedxml import ElementTree

from PIL import Image



from app.core.config import get_settings

from app.core.errors import AppError, ValidationFailed

from app.core.logging import get_logger

from app.models.edition import Icon

from app.services.audit import record



ICON_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "icons"

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



    allowed = {"svg": ALLOWED_ATTRIBUTES}

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

    ElementTree.register_namespace("", SVG_NS)

    output = ElementTree.tostring(root, encoding="utf-8")

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



    icon = Icon(

        edition_id=edition_id,

        kind="upload",

        name=name[:120],

        mime=mime,

        data=payload,

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

    record(

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

                select(Icon).where(Icon.edition_id == edition_id, Icon.kind == "library")

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

        icon = Icon(

            edition_id=edition_id,

            kind="library",

            name=name,

            library_key=name,

            mime=mime,

            data=payload,

            size_bytes=len(payload),

            width=width,

            height=height,

            sha256=hashlib.sha256(payload).hexdigest(),

            recolorable=mime == "image/svg+xml",

            status="active",

        )

        db.add(icon)

        await db.flush()

        mapping[name] = icon.id

    return mapping





def icon_url(icon_id: uuid.UUID) -> str:

    return f"/api/v1/public/icons/{icon_id}"





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

        "url": icon_url(icon.id),

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
    icon.status = "archived"
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
