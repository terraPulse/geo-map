"""Tiny RGBA PNG encoder and header check. No GDAL and no network."""

import struct
import zlib


def encode_rgba(width, height, rgba):
    if len(rgba) != 4 or any(not isinstance(channel, int) or not 0 <= channel <= 255 for channel in rgba):
        raise ValueError("rgba")
    if width < 1 or height < 1 or width > 4096 or height > 4096:
        raise ValueError("size")
    row = b"\x00" + bytes(rgba) * width
    raw = row * height

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def png_size(blob):
    if not blob.startswith(b"\x89PNG\r\n\x1a\n") or len(blob) < 24:
        return None
    length = struct.unpack(">I", blob[8:12])[0]
    if blob[12:16] != b"IHDR" or length != 13:
        return None
    width, height, depth, color = struct.unpack(">IIBB", blob[16:26])
    if depth != 8 or color != 6:
        return None
    return width, height
