"""Tests for LocalStorage and SupabaseStorage."""

import pytest
from app.integrations.storage import (
    LocalStorage,
    SupabaseStorage,
    get_storage,
    verify_local_signature,
)


@pytest.mark.asyncio
async def test_local_storage_put_get_delete(tmp_path):
    storage = LocalStorage(base_dir=tmp_path / "files")
    test_data = b"Hello, Parallax Storage!"
    key = "documents/test_doc.pdf"

    # Put
    res_key = await storage.put(key, test_data, content_type="application/pdf")
    assert res_key == key

    # Get
    retrieved = await storage.get(key)
    assert retrieved == test_data

    # Signed URL
    url = await storage.signed_url(key, expires_in=300)
    assert "expires=" in url
    assert "signature=" in url

    # Parse expires and signature from signed URL
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    expires = int(qs["expires"][0])
    sig = qs["signature"][0]
    assert verify_local_signature(key, expires, sig) is True
    assert verify_local_signature(key, expires, "invalid_signature") is False

    # Delete
    await storage.delete(key)
    with pytest.raises(FileNotFoundError):
        await storage.get(key)


def test_supabase_storage_client_init():
    supa = SupabaseStorage(
        url="https://abcproject.supabase.co",
        key="test-api-key",
        bucket="parallax-test",
    )
    assert supa.endpoint == "https://abcproject.supabase.co/storage/v1"
    pub_url = supa.public_url("icons/demo.svg")
    assert pub_url == "https://abcproject.supabase.co/storage/v1/object/public/parallax-test/icons/demo.svg"


def test_get_storage_returns_local_in_test():
    storage = get_storage()
    assert isinstance(storage, LocalStorage)
