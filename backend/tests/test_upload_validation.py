import io

import pytest
from PIL import Image

from app.core.errors import AppError
from app.services.verification import validate_and_sanitize_upload


def test_upload_rejects_mime_spoofing():
    with pytest.raises(AppError) as error:
        validate_and_sanitize_upload(b"%PDF-1.7\n", "image/jpeg")
    assert error.value.status_code == 415


def test_upload_accepts_pdf_magic_bytes():
    data = b"%PDF-1.7\nsmall test file"
    assert validate_and_sanitize_upload(data, "application/pdf") == (data, "application/pdf")


def test_upload_reencodes_image_and_removes_exif():
    source = Image.new("RGB", (3, 3), "navy")
    exif = Image.Exif()
    exif[315] = "private-camera-metadata"
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif)

    cleaned, mime_type = validate_and_sanitize_upload(buffer.getvalue(), "image/jpeg")
    assert mime_type == "image/jpeg"
    with Image.open(io.BytesIO(cleaned)) as result:
        assert 315 not in result.getexif()

