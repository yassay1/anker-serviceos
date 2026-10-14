"""Local structural checks for uploaded images.

Limits and scan thresholds come from the unconfirmed stage-4 proposal. They are
not a finalized product contract, a malware engine, or a multimodal model.
"""

from __future__ import annotations

# Proposal values recorded in contracts/proposed/v1/README.md.
PROPOSAL_MAX_IMAGE_BYTES = 10 * 1024 * 1024
PROPOSAL_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")
# Defensive decode bounds. Also unconfirmed; they only stop obvious bombs.
PROPOSAL_MAX_EDGE = 8192
PROPOSAL_MAX_PIXELS = 16_000_000

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sniff_media_type(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(_PNG_SIGNATURE):
        return "image/png"
    if len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image/webp"
    return None


def inspect_image(media_type: str, payload: bytes) -> str | None:
    """Return a stable rejection code, or None when the structure is acceptable."""
    if media_type not in PROPOSAL_MEDIA_TYPES:
        return "unsupported_media"
    if not payload or len(payload) > PROPOSAL_MAX_IMAGE_BYTES:
        return "invalid_payload"
    sniffed = sniff_media_type(payload)
    if sniffed != media_type:
        return "media_mismatch"
    if media_type == "image/jpeg":
        return _inspect_jpeg(payload)
    if media_type == "image/png":
        return _inspect_png(payload)
    return _inspect_webp(payload)


def _dimensions_ok(width: int, height: int) -> bool:
    return 1 <= width <= PROPOSAL_MAX_EDGE and 1 <= height <= PROPOSAL_MAX_EDGE and width * height <= PROPOSAL_MAX_PIXELS


def _inspect_jpeg(data: bytes) -> str | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return "invalid_jpeg"
    index = 2
    seen_frame = False
    while index < len(data):
        if data[index] != 0xFF:
            return "invalid_jpeg"
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return "invalid_jpeg"
        marker = data[index]
        index += 1
        if marker == 0xD9:
            if index != len(data):
                return "trailing_data"
            return None if seen_frame else "missing_frame"
        if marker in {0x01} or 0xD0 <= marker <= 0xD8:
            continue
        if index + 2 > len(data):
            return "invalid_jpeg"
        length = int.from_bytes(data[index:index + 2], "big")
        if length < 2 or index + length > len(data):
            return "invalid_jpeg"
        if marker in {0xC0, 0xC1, 0xC2}:
            if length < 8:
                return "invalid_jpeg"
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            if not _dimensions_ok(width, height):
                return "dimensions"
            seen_frame = True
        if marker == 0xDA:
            if not seen_frame:
                return "missing_frame"
            return _jpeg_entropy(data, index + length)
        index += length
    return "invalid_jpeg"


def _jpeg_entropy(data: bytes, start: int) -> str | None:
    index = start
    while index < len(data) - 1:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker == 0x00 or marker == 0xFF:
            index += 2 if marker == 0x00 else 1
            continue
        if marker == 0xD9:
            return None if index + 2 == len(data) else "trailing_data"
        if 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        return "invalid_jpeg"
    return "invalid_jpeg"


def _inspect_png(data: bytes) -> str | None:
    import zlib

    if not data.startswith(_PNG_SIGNATURE):
        return "invalid_png"
    index = len(_PNG_SIGNATURE)
    seen_header = False
    while index + 12 <= len(data):
        length = int.from_bytes(data[index:index + 4], "big")
        tag = data[index + 4:index + 8]
        end = index + 12 + length
        if end > len(data):
            return "invalid_png"
        chunk = data[index + 8:index + 8 + length]
        expected = int.from_bytes(data[index + 8 + length:end], "big")
        if zlib.crc32(tag + chunk) & 0xFFFFFFFF != expected:
            return "bad_crc"
        if tag == b"IHDR":
            if seen_header or length != 13:
                return "invalid_png"
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
            if not _dimensions_ok(width, height):
                return "dimensions"
            seen_header = True
        if tag == b"IEND":
            if length != 0 or not seen_header:
                return "invalid_png"
            return None if end == len(data) else "trailing_data"
        index = end
    return "invalid_png"


def _inspect_webp(data: bytes) -> str | None:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return "invalid_webp"
    declared = int.from_bytes(data[4:8], "little")
    if declared != len(data) - 8:
        return "trailing_data" if declared < len(data) - 8 else "invalid_webp"
    index = 12
    saw_bitmap = False
    while index < len(data):
        if index + 8 > len(data):
            return "invalid_webp"
        tag = data[index:index + 4]
        size = int.from_bytes(data[index + 4:index + 8], "little")
        start = index + 8
        end = start + size
        if end > len(data):
            return "invalid_webp"
        payload = data[start:end]
        dimensions = None
        if tag == b"VP8X" and len(payload) >= 10:
            dimensions = (1 + int.from_bytes(payload[4:7], "little"), 1 + int.from_bytes(payload[7:10], "little"))
        elif tag == b"VP8 ":
            dimensions = _vp8_dimensions(payload)
            if dimensions is None:
                return "invalid_webp"
            saw_bitmap = True
        elif tag == b"VP8L":
            dimensions = _vp8l_dimensions(payload)
            if dimensions is None:
                return "invalid_webp"
            saw_bitmap = True
        if dimensions is not None and not _dimensions_ok(*dimensions):
            return "dimensions"
        index = end + (size & 1)
    if index != len(data) or not saw_bitmap:
        return "invalid_webp"
    return None


def _vp8_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
        return None
    width = int.from_bytes(payload[6:8], "little") & 0x3FFF
    height = int.from_bytes(payload[8:10], "little") & 0x3FFF
    if width < 1 or height < 1:
        return None
    return width, height


def _vp8l_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 5 or payload[0] != 0x2F:
        return None
    bits = int.from_bytes(payload[1:5], "little")
    return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
