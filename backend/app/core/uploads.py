"""Bounded stream reads for multipart uploads.

Content-Length checks are not enough: chunked requests can omit it. Every
upload handler must stop reading once its own limit is crossed so an attacker
cannot make the API buffer an arbitrarily large file in memory.
"""

from fastapi import UploadFile

from app.core.errors import AppError


async def read_upload_limited(
    file: UploadFile,
    limit: int,
    *,
    label: str = "File",
    chunk_size: int = 64 * 1024,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            size = (
                f"{limit / (1024 * 1024):.1f} MB"
                if limit >= 1024 * 1024
                else f"{limit // 1024} KB"
            )
            raise AppError(
                f"{label} is larger than {size}.",
                code="FILE_TOO_LARGE",
                status_code=413,
                details={"maxUploadBytes": limit},
            )
        chunks.append(chunk)
    return b"".join(chunks)


__all__ = ["read_upload_limited"]