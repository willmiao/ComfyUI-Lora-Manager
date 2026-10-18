"""Read intrinsic dimensions from video containers without external tooling.

PIL cannot open ``.mp4``/``.webm`` files, so example videos imported through
the "Add examples" flow used to fall back to a hardcoded ``720x1280`` (portrait)
entry, which forced the showcase viewer to letterbox landscape videos.

This module reads the dimensions out of the container headers themselves:

* ISO base media files (``.mp4``/``.mov``/``.m4v``) — ``moov/trak/tkhd``,
  falling back to the sample description of the video track.
* WebM/Matroska (``.webm``/``.mkv``) — ``Segment/Tracks/TrackEntry/Video``
  ``PixelWidth``/``PixelHeight``.
* Animated WebP (``RIFF``/``WEBP``) — handled because users routinely save
  animated examples with a video extension.

The container signature decides which reader runs, so a mislabelled file
(a ``.mp4`` that is really WebM) still reports the right dimensions.

Both readers stream over the file: only container headers are read, so a
multi-gigabyte ``mdat`` is never pulled into memory (it is seeked past).
"""

from __future__ import annotations

import functools
import logging
import os
import struct
from typing import BinaryIO, Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

ISO_MEDIA_EXTENSIONS = frozenset({".mp4", ".m4v", ".mov"})
EBML_MEDIA_EXTENSIONS = frozenset({".webm", ".mkv"})

_EBML_MAGIC = b"\x1a\x45\xdf\xa3"

# Cap recursion into nesting containers so a crafted/corrupt file cannot blow
# the Python stack.
_MAX_BOX_DEPTH = 12
_MAX_EBML_DEPTH = 12

# Header structs (``tkhd``, sample entries) are tiny; guard against a bogus
# size claiming the whole file.
_MAX_HEADER_PAYLOAD = 1024 * 1024

_WIDTH_HEIGHT_UNSET = (0, 0)


@functools.lru_cache(maxsize=4096)
def _get_video_dimensions_cached(
    path: str, _mtime_ns: int, _size: int
) -> Optional[Tuple[int, int]]:
    """Return ``(width, height)`` for ``path``, or ``None`` on any failure.

    ``_mtime_ns`` and ``_size`` participate in the cache key only so a replaced
    file is re-probed; they are never read by the parser.
    """
    try:
        return _read_video_dimensions(path)
    except Exception:
        logger.debug("Failed to read video dimensions for %s", path, exc_info=True)
        return None


def _read_video_dimensions(path: str) -> Optional[Tuple[int, int]]:
    """Dispatch to the ISO or EBML reader based on the container's magic bytes.

    Real libraries contain files whose extension lies about their container
    (a ``.mp4`` that is really WebM, typically), so the sniffed signature wins
    and the extension is only a fallback.
    """

    ext = os.path.splitext(path)[1].lower()
    file_size = os.path.getsize(path)

    with open(path, "rb") as stream:
        magic = stream.read(12)

        if _looks_like_iso_media(magic):
            return _read_iso_media_dimensions(stream, file_size)
        if magic[:4] == _EBML_MAGIC:
            return _read_ebml_dimensions(stream, file_size)
        if magic[:4] == b"RIFF" and magic[8:12] == b"WEBP":
            return _read_riff_webp_dimensions(stream, file_size)

        # Signature is inconclusive (truncated or unusual file): fall back to
        # the extension.
        if ext in EBML_MEDIA_EXTENSIONS:
            return _read_ebml_dimensions(stream, file_size)
        if ext in ISO_MEDIA_EXTENSIONS:
            return _read_iso_media_dimensions(stream, file_size)
        return None


def _looks_like_iso_media(magic: bytes) -> bool:
    """Return True when the leading bytes are an ISO base media box header."""

    return len(magic) >= 8 and magic[4:8] in {
        b"ftyp",
        b"moov",
        b"mdat",
        b"free",
        b"skip",
        b"wide",
    }


def get_video_dimensions(path: str) -> Optional[Tuple[int, int]]:
    """Return the intrinsic ``(width, height)`` of a local video file.

    Returns ``None`` when the extension is unsupported, the file is missing or
    corrupt, or the dimensions cannot be determined. Never raises.
    """
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return _get_video_dimensions_cached(path, stat.st_mtime_ns, stat.st_size)


def _clear_video_dimensions_cache() -> None:
    """Drop the dimension cache (used by tests)."""

    _get_video_dimensions_cached.cache_clear()


# --------------------------------------------------------------------------- #
# ISO base media (MP4 / MOV)
# --------------------------------------------------------------------------- #


def _iter_boxes(
    stream: BinaryIO, end: int, depth: int = 0
) -> Iterator[Tuple[bytes, int, int]]:
    """Yield ``(type, payload_start, box_end)`` for boxes in ``[tell, end)``.

    The stream is left at the next box boundary after each yielded box.
    """
    if depth > _MAX_BOX_DEPTH:
        return

    while True:
        start = stream.tell()
        if start + 8 > end:
            return

        header = stream.read(8)
        if len(header) < 8:
            return

        size, box_type = struct.unpack(">I4s", header)
        header_size = 8

        if size == 1:
            # 64-bit ``largesize`` follows the type.
            extended = stream.read(8)
            if len(extended) < 8:
                return
            size = struct.unpack(">Q", extended)[0]
            header_size = 16
        elif size == 0:
            # Box extends to the end of the enclosing container.
            size = end - start

        if size < header_size or start + size > end:
            return

        yield box_type, start + header_size, start + size
        stream.seek(start + size)


def _read_iso_media_dimensions(
    stream: BinaryIO, file_size: int
) -> Optional[Tuple[int, int]]:
    """Walk ``moov`` looking for the video track's dimensions."""

    stream.seek(0)
    moov: Optional[Tuple[int, int]] = None
    for box_type, payload_start, box_end in _iter_boxes(stream, file_size):
        if box_type == b"moov":
            moov = (payload_start, box_end)
            break

    if moov is None:
        return None

    stream.seek(moov[0])
    for box_type, payload_start, box_end in _iter_boxes(stream, moov[1], depth=1):
        if box_type != b"trak":
            continue
        dimensions = _read_trak_dimensions(stream, payload_start, box_end)
        if dimensions is not None:
            return dimensions

    return None


def _read_trak_dimensions(
    stream: BinaryIO, trak_start: int, trak_end: int
) -> Optional[Tuple[int, int]]:
    """Return the dimensions of a ``trak`` when it describes a video track."""

    stream.seek(trak_start)

    is_video = False
    tkhd_dimensions = _WIDTH_HEIGHT_UNSET
    stsd_dimensions = _WIDTH_HEIGHT_UNSET

    for box_type, payload_start, box_end in _iter_boxes(stream, trak_end, depth=2):
        if box_type == b"tkhd":
            tkhd_dimensions = _parse_tkhd(stream, payload_start, box_end)
        elif box_type == b"mdia":
            stream.seek(payload_start)
            media = _read_mdia_dimensions(stream, payload_start, box_end)
            if media is not None:
                is_video, stsd_dimensions = media

    if not is_video:
        return None

    # ``tkhd`` is preferred: it is display space, and its 16.16 fixed point
    # encoding keeps non-integer dimensions (odd crops produce those).
    for width, height in (tkhd_dimensions, stsd_dimensions):
        if width > 0 and height > 0:
            return int(round(width)), int(round(height))
    return None


def _read_mdia_dimensions(
    stream: BinaryIO, mdia_start: int, mdia_end: int
) -> Optional[Tuple[bool, Tuple[float, float]]]:
    """Return ``(is_video, dimensions)`` for a ``mdia`` box."""

    handler_type = b""
    stsd_dimensions = _WIDTH_HEIGHT_UNSET

    for box_type, payload_start, box_end in _iter_boxes(stream, mdia_end, depth=3):
        if box_type == b"hdlr":
            handler_type = _parse_handler_type(stream, payload_start, box_end)
        elif box_type == b"minf":
            stream.seek(payload_start)
            stsd_dimensions = _read_minf_dimensions(stream, payload_start, box_end)

    return handler_type == b"vide", stsd_dimensions


def _read_minf_dimensions(
    stream: BinaryIO, minf_start: int, minf_end: int
) -> Tuple[float, float]:
    """Return the sample-entry dimensions declared under ``minf/stbl/stsd``."""

    for box_type, payload_start, box_end in _iter_boxes(stream, minf_end, depth=4):
        if box_type != b"stbl":
            continue
        stream.seek(payload_start)
        for inner_type, inner_start, inner_end in _iter_boxes(
            stream, box_end, depth=5
        ):
            if inner_type == b"stsd":
                return _parse_stsd(stream, inner_start, inner_end)
    return _WIDTH_HEIGHT_UNSET


def _parse_tkhd(
    stream: BinaryIO, payload_start: int, box_end: int
) -> Tuple[float, float]:
    """Parse the 16.16 fixed point width/height trailer of a ``tkhd`` box."""

    size = box_end - payload_start
    if size < 8 or size > _MAX_HEADER_PAYLOAD:
        return _WIDTH_HEIGHT_UNSET

    stream.seek(box_end - 8)
    trailer = stream.read(8)
    if len(trailer) < 8:
        return _WIDTH_HEIGHT_UNSET

    width, height = struct.unpack(">II", trailer)
    return width / 65536.0, height / 65536.0


def _parse_handler_type(
    stream: BinaryIO, payload_start: int, box_end: int
) -> bytes:
    """Parse the handler type from an ``hdlr`` box.

    Layout: version/flags (4) + pre_defined (4) + handler_type (4).
    """

    if box_end - payload_start < 12:
        return b""
    stream.seek(payload_start)
    data = stream.read(12)
    if len(data) < 12:
        return b""
    return data[8:12]


def _parse_stsd(
    stream: BinaryIO, payload_start: int, box_end: int
) -> Tuple[float, float]:
    """Parse the visual sample entry dimensions from an ``stsd`` box.

    Only the first entry is inspected: video tracks are single-entry in every
    container we import from.
    """

    if box_end - payload_start < 16:
        return _WIDTH_HEIGHT_UNSET

    stream.seek(payload_start)
    header = stream.read(8)  # version/flags + entry_count
    if len(header) < 8:
        return _WIDTH_HEIGHT_UNSET

    entry_start = payload_start + 8
    if entry_start + 8 > box_end:
        return _WIDTH_HEIGHT_UNSET

    stream.seek(entry_start)
    entry_header = stream.read(8)
    if len(entry_header) < 8:
        return _WIDTH_HEIGHT_UNSET

    entry_size = struct.unpack(">I", entry_header[:4])[0]
    header_size = 8

    if entry_size == 1:
        extended = stream.read(8)
        if len(extended) < 8:
            return _WIDTH_HEIGHT_UNSET
        entry_size = struct.unpack(">Q", extended)[0]
        header_size = 16
    elif entry_size == 0:
        entry_size = box_end - entry_start

    if entry_size < header_size + 8 or entry_start + entry_size > box_end:
        return _WIDTH_HEIGHT_UNSET

    # Visual sample entries: 6 bytes reserved + 2 bytes data_reference_index,
    # then width (2) and height (2).
    stream.seek(entry_start + header_size + 6 + 2)
    dimensions = stream.read(4)
    if len(dimensions) < 4:
        return _WIDTH_HEIGHT_UNSET

    width, height = struct.unpack(">HH", dimensions)
    return float(width), float(height)


# --------------------------------------------------------------------------- #
# WebM / Matroska (EBML)
# --------------------------------------------------------------------------- #

# EBML element IDs (stored with their length marker, as they appear on disk).
_ID_SEGMENT = 0x18538067
_ID_TRACKS = 0x1654AE6B
_ID_TRACK_ENTRY = 0xAE
_ID_TRACK_TYPE = 0x83
_ID_VIDEO = 0xE0
_ID_PIXEL_WIDTH = 0xB0
_ID_PIXEL_HEIGHT = 0xBA

# Nested containers we descend into while hunting for video dimensions.
_EBML_CONTAINER_IDS = frozenset({_ID_SEGMENT, _ID_TRACKS, _ID_TRACK_ENTRY})


def _read_ebml_vint(stream: BinaryIO, *, keep_marker: bool) -> Optional[Tuple[int, int]]:
    """Read an EBML variable-length integer.

    Returns ``(value, byte_length)``. For element IDs the marker bit is kept
    (``keep_marker=True``) because IDs are compared in their on-disk form; for
    sizes the marker is stripped to yield the actual payload length.
    """

    first = stream.read(1)
    if not first:
        return None

    first_byte = first[0]
    if first_byte == 0:
        return None

    length = 1
    mask = 0x80
    while not first_byte & mask:
        mask >>= 1
        length += 1
        if length > 8:
            return None

    value = first_byte if keep_marker else first_byte & (mask - 1)
    remaining = length - 1

    if remaining:
        extra = stream.read(remaining)
        if len(extra) < remaining:
            return None
        for byte in extra:
            value = (value << 8) | byte

    return value, length


def _read_ebml_dimensions(
    stream: BinaryIO, file_size: int
) -> Optional[Tuple[int, int]]:
    """Parse ``Segment/Tracks`` for the first video ``TrackEntry``."""

    stream.seek(0)
    header = stream.read(4)
    if header != _EBML_MAGIC:
        return None

    return _walk_ebml(stream, 0, file_size, depth=0)


def _walk_ebml(
    stream: BinaryIO, start: int, end: int, *, depth: int
) -> Optional[Tuple[int, int]]:
    """Recursively scan EBML elements in ``[start, end)`` for video dimensions."""

    if depth > _MAX_EBML_DEPTH:
        return None

    stream.seek(start)

    while stream.tell() < end:
        element_start = stream.tell()

        element_id = _read_ebml_vint(stream, keep_marker=True)
        if element_id is None:
            return None
        element_id_value = element_id[0]

        size_field = _read_ebml_vint(stream, keep_marker=False)
        if size_field is None:
            return None
        payload_size, size_length = size_field

        payload_start = element_start + element_id[1] + size_length

        # A size field of all-ones marks an unknown-size element, which is
        # legal for Segment/Tracks; treat it as "until the parent ends".
        unknown_size = payload_size == (1 << (7 * size_length)) - 1
        payload_end = end if unknown_size else payload_start + payload_size

        if payload_end > end:
            return None

        if element_id_value == _ID_VIDEO:
            dimensions = _read_ebml_video(stream, payload_start, min(payload_end, end))
            if dimensions is not None:
                return dimensions
        elif element_id_value == _ID_TRACK_ENTRY:
            track = _read_ebml_track_entry(
                stream, payload_start, min(payload_end, end)
            )
            if track is not None:
                return track
        elif element_id_value in _EBML_CONTAINER_IDS:
            found = _walk_ebml(
                stream, payload_start, min(payload_end, end), depth=depth + 1
            )
            if found is not None:
                return found

        if unknown_size:
            # Cannot resume after an unknown-size element; its siblings cannot
            # be located reliably, so stop scanning this level.
            return None

        stream.seek(payload_end)

    return None


def _read_ebml_track_entry(
    stream: BinaryIO, start: int, end: int
) -> Optional[Tuple[int, int]]:
    """Return dimensions when a ``TrackEntry`` is a video track."""

    track_type: Optional[int] = None
    dimensions: Optional[Tuple[int, int]] = None

    stream.seek(start)
    while stream.tell() < end:
        element_start = stream.tell()

        element_id = _read_ebml_vint(stream, keep_marker=True)
        if element_id is None:
            return None

        size_field = _read_ebml_vint(stream, keep_marker=False)
        if size_field is None:
            return None
        payload_size, size_length = size_field

        payload_start = element_start + element_id[1] + size_length
        payload_end = min(payload_start + payload_size, end)

        if element_id[0] == _ID_TRACK_TYPE:
            track_type = _read_ebml_uint(stream, payload_start, payload_end)
        elif element_id[0] == _ID_VIDEO:
            dimensions = _read_ebml_video(stream, payload_start, payload_end)

        stream.seek(payload_end)

    # Track type 1 is video.
    if track_type == 1 and dimensions is not None:
        return dimensions
    return None


def _read_ebml_video(
    stream: BinaryIO, start: int, end: int
) -> Optional[Tuple[int, int]]:
    """Return ``PixelWidth``/``PixelHeight`` from a ``Video`` element."""

    width: Optional[int] = None
    height: Optional[int] = None

    stream.seek(start)
    while stream.tell() < end:
        element_start = stream.tell()

        element_id = _read_ebml_vint(stream, keep_marker=True)
        if element_id is None:
            return None

        size_field = _read_ebml_vint(stream, keep_marker=False)
        if size_field is None:
            return None
        payload_size, size_length = size_field

        payload_start = element_start + element_id[1] + size_length
        payload_end = min(payload_start + payload_size, end)

        if element_id[0] == _ID_PIXEL_WIDTH:
            width = _read_ebml_uint(stream, payload_start, payload_end)
        elif element_id[0] == _ID_PIXEL_HEIGHT:
            height = _read_ebml_uint(stream, payload_start, payload_end)

        stream.seek(payload_end)

    if width and height and width > 0 and height > 0:
        return width, height
    return None


def _read_ebml_uint(stream: BinaryIO, start: int, end: int) -> Optional[int]:
    """Read an unsigned big-endian integer element payload."""

    length = end - start
    if length <= 0 or length > 8:
        return None

    stream.seek(start)
    raw = stream.read(length)
    if len(raw) < length:
        return None

    value = 0
    for byte in raw:
        value = (value << 8) | byte
    return value


# --------------------------------------------------------------------------- #
# RIFF / WebP (animated examples are often renamed to ``.mp4``)
# --------------------------------------------------------------------------- #


def _read_riff_webp_dimensions(
    stream: BinaryIO, file_size: int
) -> Optional[Tuple[int, int]]:
    """Return dimensions from a WebP file's first dimension-bearing chunk."""

    stream.seek(12)

    while stream.tell() + 8 <= file_size:
        header = stream.read(8)
        if len(header) < 8:
            return None

        fourcc, chunk_size = struct.unpack("<4sI", header)
        payload_start = stream.tell()

        if fourcc == b"VP8X":
            payload = stream.read(10)
            if len(payload) < 10:
                return None
            # Canvas size is stored minus one, as 24-bit little endian values.
            width = int.from_bytes(payload[4:7], "little") + 1
            height = int.from_bytes(payload[7:10], "little") + 1
            return width, height

        if fourcc == b"VP8 ":
            # Frame tag (3 bytes, bit 0 = key frame) then the key frame start
            # code 0x9d 0x01 0x2a and the 16-bit dimensions.
            payload = stream.read(10)
            if len(payload) < 10:
                return None
            start = payload.find(b"\x9d\x01\x2a")
            if start < 0 or start + 7 > len(payload):
                return None
            width, height = struct.unpack("<HH", payload[start + 3 : start + 7])
            return width & 0x3FFF, height & 0x3FFF

        if fourcc == b"VP8L":
            payload = stream.read(5)
            if len(payload) < 5 or payload[0] != 0x2F:
                return None
            bits = int.from_bytes(payload[1:5], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1

        # Skip this chunk (payloads are padded to an even byte boundary).
        stream.seek(payload_start + chunk_size + (chunk_size & 1))

    return None
