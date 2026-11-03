"""Private object storage for verification documents, images and assets (Supabase, S3 or local dev)."""

import base64
import hashlib
import hmac
import time
import uuid
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger("storage")


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    
    async def delete(self, key: str) -> None:
        clean_key = key.lstrip("/\\")
        target = self.root / clean_key
        if target.exists():
            target.unlink()

    async def get(self, key: str) -> bytes: ...
    async def signed_url(self, key: str, ttl_seconds: int | None = None, expires_in: int | None = None) -> str: ...
    def public_url(self, key: str) -> str: ...


def _local_root() -> Path:
    root = Path("var/private")
    root.mkdir(parents=True, exist_ok=True)
    return root


def local_signature(key: str, expires: int) -> str:
    settings = get_settings()
    message = f"{key}:{expires}".encode()
    digest = hmac.new(settings.server_secret_key.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def verify_local_signature(key: str, expires: int, signature: str) -> bool:
    if int(time.time()) > expires:
        return False
    return hmac.compare_digest(local_signature(key, expires), signature)


class LocalStorage:
    """Local filesystem storage: zero-configuration, ideal for local dev and automated tests."""

    def __init__(self, root: Path | str | None = None, base_dir: Path | str | None = None) -> None:
        r = root or base_dir
        self.root = Path(r) if r else _local_root()
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        clean_key = key.lstrip("/\\")
        target = self.root / clean_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return clean_key

    async def get(self, key: str) -> bytes:
        clean_key = key.lstrip("/\\")
        target = self.root / clean_key
        if not target.exists():
            raise FileNotFoundError(f"File {clean_key} not found")
        return target.read_bytes()

    async def delete(self, key: str) -> None:
        clean_key = key.lstrip("/\\")
        target = self.root / clean_key
        if target.exists():
            target.unlink()

    async def signed_url(self, key: str, ttl_seconds: int | None = None, expires_in: int | None = None) -> str:
        ttl_seconds = ttl_seconds or expires_in
        clean_key = key.lstrip("/\\")
        ttl = ttl_seconds or get_settings().signed_url_ttl_seconds
        expires = int(time.time()) + ttl
        signature = local_signature(clean_key, expires)
        return f"/api/v1/public/documents/{clean_key}?expires={expires}&signature={signature}"

    def public_url(self, key: str) -> str:
        clean_key = key.lstrip("/\\")
        return f"/api/v1/public/documents/{clean_key}"


class SupabaseStorage:
    """Supabase Storage via REST API (stores images, icons, and verification documents in Supabase buckets)."""

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/storage/v1"

    def __init__(self, url: str | None = None, key: str | None = None, bucket: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (url or settings.supabase_url or "").rstrip("/")
        self.api_key = key or settings.supabase_service_role_key or settings.supabase_key or ""
        self.bucket = bucket or settings.supabase_storage_bucket or "parallax"
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "apikey": self.api_key,
        }

    async def _ensure_bucket(self, client: httpx.AsyncClient) -> None:
        """Create the storage bucket if it does not yet exist."""
        try:
            resp = await client.post(
                f"{self.base_url}/storage/v1/bucket",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"id": self.bucket, "name": self.bucket, "public": True},
            )
            if resp.status_code in (200, 201, 409):
                logger.info("supabase_bucket_ready", bucket=self.bucket)
        except Exception as exc:
            logger.warning("supabase_ensure_bucket_failed", bucket=self.bucket, error=str(exc))

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        clean_key = key.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/{self.bucket}/{clean_key}"
        headers = {
            **self._headers,
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, content=data, headers=headers)
            if resp.status_code == 404 or "Bucket not found" in resp.text:
                await self._ensure_bucket(client)
                resp = await client.post(endpoint, content=data, headers=headers)
            if resp.status_code not in (200, 201):
                logger.error("supabase_storage_put_error", status=resp.status_code, body=resp.text)
                raise AppError(
                    f"Supabase storage upload failed: {resp.text}",
                    code="STORAGE_ERROR",
                    status_code=502,
                )
        return clean_key

    async def get(self, key: str) -> bytes:
        clean_key = key.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/authenticated/{self.bucket}/{clean_key}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(endpoint, headers=self._headers)
            if resp.status_code == 404:
                public_endpoint = f"{self.base_url}/storage/v1/object/public/{self.bucket}/{clean_key}"
                resp = await client.get(public_endpoint, headers=self._headers)
            if resp.status_code == 404:
                raise FileNotFoundError(f"Object {clean_key} not found in Supabase storage")
            if resp.status_code != 200:
                raise AppError(
                    f"Supabase storage get failed: {resp.text}",
                    code="STORAGE_ERROR",
                    status_code=502,
                )
            return resp.content

    async def signed_url(self, key: str, ttl_seconds: int | None = None, expires_in: int | None = None) -> str:
        ttl_seconds = ttl_seconds or expires_in
        clean_key = key.lstrip("/")
        ttl = ttl_seconds or get_settings().signed_url_ttl_seconds
        endpoint = f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{clean_key}"
        headers = {**self._headers, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(endpoint, json={"expiresIn": ttl}, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    signed_path = data.get("signedURL")
                    if signed_path:
                        if signed_path.startswith("http"):
                            return signed_path
                        return f"{self.base_url}{signed_path}" if signed_path.startswith("/storage/v1") else f"{self.base_url}/storage/v1{signed_path}"
        except Exception as exc:
            logger.warning("supabase_signed_url_failed", error=str(exc))
        return self.public_url(clean_key)

    def public_url(self, key: str) -> str:
        clean_key = key.lstrip("/")
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{clean_key}"


class S3Storage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket_private
        self.endpoint = settings.s3_endpoint_url
        self.access_key = settings.s3_access_key_id
        self.secret_key = settings.s3_secret_access_key

    def _client(self):
        import aioboto3

        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="auto",
        )

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        async with self._client() as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
        return key

    async def get(self, key: str) -> bytes:
        async with self._client() as client:
            response = await client.get_object(Bucket=self.bucket, Key=key)
            return await response["Body"].read()

    async def signed_url(self, key: str, ttl_seconds: int | None = None, expires_in: int | None = None) -> str:
        ttl_seconds = ttl_seconds or expires_in
        async with self._client() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=ttl_seconds or get_settings().signed_url_ttl_seconds,
            )

    def public_url(self, key: str) -> str:
        if self.endpoint:
            return f"{self.endpoint.rstrip('/')}/{self.bucket}/{key.lstrip('/')}"
        return f"https://{self.bucket}.s3.amazonaws.com/{key.lstrip('/')}"


def get_storage() -> Storage:
    settings = get_settings()
    backend = (settings.storage_backend or "auto").lower()

    if backend == "local":
        return LocalStorage()
    if backend == "supabase":
        if settings.supabase_storage_configured:
            return SupabaseStorage()
        logger.warning("supabase_storage_unconfigured_fallback_to_local")
        return LocalStorage()
    if backend == "s3":
        if settings.storage_configured:
            return S3Storage()
        logger.warning("s3_storage_unconfigured_fallback_to_local")
        return LocalStorage()

    # auto mode: check Supabase first, then S3, fallback to Local
    if settings.supabase_storage_configured:
        return SupabaseStorage()
    if settings.storage_configured:
        return S3Storage()
    return LocalStorage()


def document_key(filename: str | None = None) -> str:
    suffix = ".bin"
    if filename and "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()[:5]
    return f"verification/{uuid.uuid4().hex}{suffix}"
