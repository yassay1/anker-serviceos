import struct
import zlib

from serviceos_api.application.image_safety import PROPOSAL_MAX_IMAGE_BYTES, inspect_image, sniff_media_type


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def png_image(width: int = 1, height: int = 1) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(width * 3) for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b"")


def jpeg_image() -> bytes:
    sof = bytes([0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00])
    sos = bytes([0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00])
    return b"\xff\xd8" + sof + sos + b"\xff\xd9"


def webp_image() -> bytes:
    payload = bytes([0x2F, 0x00, 0x00, 0x00, 0x00])
    chunk = b"VP8L" + len(payload).to_bytes(4, "little") + payload + b"\x00"
    body = b"WEBP" + chunk
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def test_accepts_structurally_valid_proposal_types():
    assert sniff_media_type(png_image()) == "image/png"
    assert inspect_image("image/png", png_image()) is None
    assert inspect_image("image/jpeg", jpeg_image()) is None
    assert inspect_image("image/webp", webp_image()) is None


def test_rejects_trailing_payload_oversize_dimensions_and_foreign_types():
    assert inspect_image("image/png", png_image() + b"<script>alert(1)</script>") == "trailing_data"
    assert inspect_image("image/jpeg", jpeg_image() + b"<?php") == "trailing_data"
    assert inspect_image("image/png", b"GIF89a" + b"\x00" * 16) == "media_mismatch"
    assert inspect_image("image/png", png_image(width=9000)) == "dimensions"
    assert len(b"\xff\xd8\xff" + b"\x00" * PROPOSAL_MAX_IMAGE_BYTES) > PROPOSAL_MAX_IMAGE_BYTES
