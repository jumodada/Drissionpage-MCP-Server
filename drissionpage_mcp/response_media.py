"""Media metadata helpers for MCP tool responses."""

import base64
import logging
import struct
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_screenshot_metadata(
    image_data: str | bytes | None = None,
    *,
    path: str = "",
    safe_relative_path: str = "",
    full_page: bool | None = None,
    inline: bool | None = None,
) -> dict[str, Any]:
    """Return compact metadata for an MCP screenshot result."""

    raw = _image_bytes(image_data) if image_data is not None else None
    if raw is None and path:
        raw = _path_bytes(path)
    width, height = _png_dimensions(raw)

    metadata: dict[str, Any] = {
        "mime_type": "image/png",
    }
    if inline is not None:
        metadata["inline"] = inline
    elif image_data is not None:
        metadata["inline"] = True
    if image_data is not None and metadata.get("inline", True):
        metadata["encoding"] = "base64"
    if safe_relative_path:
        metadata["safe_relative_path"] = safe_relative_path
    if full_page is not None:
        metadata["full_page"] = full_page
    if raw is not None:
        metadata["bytes"] = len(raw)
    if width is not None and height is not None:
        metadata["width"] = width
        metadata["height"] = height
    return metadata


def _image_bytes(image_data: str | bytes) -> bytes | None:
    if isinstance(image_data, bytes):
        return image_data
    try:
        return base64.b64decode(image_data, validate=True)
    except Exception:
        logger.debug("Could not decode screenshot base64 metadata")
        return None


def _path_bytes(path: str) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except OSError:
        logger.debug("Could not read screenshot file metadata")
        return None


def _png_dimensions(raw: bytes | None) -> tuple[int | None, int | None]:
    if not raw or len(raw) < 24:
        return None, None
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        return None, None
    width, height = struct.unpack(">II", raw[16:24])
    return width, height
