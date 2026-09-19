"""Validate four ordered reference images without uploading them anywhere."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from urllib.parse import urlsplit

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def validate_https_url(value: str) -> str:
    """Accept HTTPS URLs without embedded credentials or control characters."""
    if not isinstance(value, str) or not value or any(ord(c) <= 32 for c in value):
        raise ValueError("Expected a nonempty HTTPS URL without whitespace.")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
        # Accessing port also validates malformed port numbers.
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Expected an HTTPS URL without credentials or a fragment.")
    return value


def prepare_images(images: list[str]) -> list[str]:
    """Return four HTTPS URLs/data URIs, preserving order (front view first).

    Local files must have a PNG/JPEG extension and matching file signature.
    Data URIs are accepted after strict base64, MIME, signature and size checks.
    This is a conservative tool-side size limit, not a claim about Meshy's limit.
    Remote image formats and sizes are validated by Meshy when it fetches them.
    """
    if not isinstance(images, list) or len(images) != 4:
        raise ValueError("Exactly four images are required, with the front view first.")
    prepared: list[str] = []
    for index, value in enumerate(images, start=1):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Image {index} must be a local path or HTTPS URL.")
        if value.startswith("data:"):
            prepared.append(_prepare_data_uri(value, index))
            continue
        if "://" in value or value.lower().startswith(("http:", "https:", "data:")):
            try:
                prepared.append(validate_https_url(value))
            except ValueError:
                raise ValueError(f"Image {index} must use HTTPS without credentials.") from None
            continue
        path = Path(value).expanduser()
        suffix = path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg"}:
            raise ValueError(f"Image {index} must be a PNG or JPEG file.")
        try:
            with path.open("rb") as source:
                data = source.read(MAX_IMAGE_BYTES + 1)
        except OSError:
            raise ValueError(f"Image {index} could not be read as a local file.") from None
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"Image {index} exceeds the 20 MiB local image limit.")
        if suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        else:
            raise ValueError(f"Image {index} has an invalid or mismatched PNG/JPEG signature.")
        prepared.append(f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}")
    return prepared


def _prepare_data_uri(value: str, index: int) -> str:
    header, separator, encoded = value.partition(",")
    signatures = {
        "data:image/png;base64": b"\x89PNG\r\n\x1a\n",
        "data:image/jpeg;base64": b"\xff\xd8\xff",
    }
    if not separator or header not in signatures:
        raise ValueError(f"Image {index} must use a PNG/JPEG base64 data URI.")
    if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValueError(f"Image {index} exceeds the 20 MiB image data limit.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError(f"Image {index} contains invalid base64 image data.") from None
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image {index} exceeds the 20 MiB image data limit.")
    if not data.startswith(signatures[header]):
        raise ValueError(f"Image {index} has an invalid or mismatched PNG/JPEG signature.")
    return f"{header},{base64.b64encode(data).decode('ascii')}"
