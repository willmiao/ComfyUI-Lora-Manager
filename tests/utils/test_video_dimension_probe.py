"""Tests for the container-level video dimension probe."""

from __future__ import annotations

import struct

from py.utils.video_metadata import get_video_dimensions


def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + box_type + payload


def _full_box(box_type: bytes, payload: bytes) -> bytes:
    """Build a box with a 4-byte version/flags header."""

    return _box(box_type, b"\x00\x00\x00\x00" + payload)


def build_mp4(width: int, height: int, *, with_stsd: bool = False) -> bytes:
    """Build a minimal but structurally valid MP4 holding one video track."""

    mvhd = _full_box(b"mvhd", b"\x00" * 96)

    hdlr = _full_box(b"hdlr", b"\x00" * 4 + b"vide" + b"\x00" * 12)

    tkhd_payload = struct.pack(">IIII", 0, 0, 0, 0) + b"\x00" * 52
    tkhd_payload += struct.pack(">II", width << 16, height << 16)
    tkhd = _full_box(b"tkhd", tkhd_payload)

    stbl_children = b""
    if with_stsd:
        sample_entry = (
            b"\x00" * 6 + struct.pack(">H", 1) + struct.pack(">HH", width, height)
        )
        stsd = _full_box(b"stsd", struct.pack(">I", 1) + _box(b"avc1", sample_entry))
        stbl_children = stsd

    minf = _box(b"minf", _box(b"stbl", stbl_children))
    mdia = _box(b"mdia", hdlr + minf)
    trak = _box(b"trak", tkhd + mdia)
    moov = _box(b"moov", mvhd + trak)
    ftyp = _box(b"ftyp", b"isom" + b"\x00\x00\x02\x00" + b"isomiso2avc1mp41")

    return ftyp + moov


def _ebml_vint(value: int) -> bytes:
    """Encode a value as a minimal-length EBML variable length integer."""

    for length in range(1, 9):
        if value < (1 << (7 * length)):
            encoded = value | (1 << (7 * length))
            return encoded.to_bytes(length, "big")
    raise ValueError("value too large for an EBML vint")


def _ebml_element(element_id: bytes, payload: bytes) -> bytes:
    return element_id + _ebml_vint(len(payload)) + payload


def _uint_element(element_id: int, value: int) -> bytes:
    length = max(1, (value.bit_length() + 7) // 8)
    return _ebml_element(
        element_id.to_bytes(2, "big") if element_id > 0xFF else element_id.to_bytes(1, "big"),
        value.to_bytes(length, "big"),
    )


def build_webm(width: int, height: int, *, track_type: int = 1) -> bytes:
    """Build a minimal WebM file holding one TrackEntry."""

    video = _ebml_element(b"\xe0", _uint_element(0xB0, width) + _uint_element(0xBA, height))
    track_entry = _ebml_element(
        b"\xae", _uint_element(0x83, track_type) + video
    )
    tracks = _ebml_element(b"\x16\x54\xae\x6b", track_entry)

    segment = _ebml_element(b"\x18\x53\x80\x67", tracks)
    ebml_header = _ebml_element(
        b"\x1a\x45\xdf\xa3",
        _uint_element(0x4286, 1) + _ebml_element(b"\x42\x82", b"webm"),
    )

    return ebml_header + segment


def test_mp4_dimensions_come_from_tkhd(tmp_path):
    video = tmp_path / "landscape.mp4"
    video.write_bytes(build_mp4(1280, 720))

    assert get_video_dimensions(str(video)) == (1280, 720)


def test_mp4_uses_stsd_when_tkhd_is_empty(tmp_path):
    video = tmp_path / "stsd-only.mp4"
    video.write_bytes(build_mp4(640, 480, with_stsd=True))

    assert get_video_dimensions(str(video)) == (640, 480)


def test_mp4_without_video_track_returns_none(tmp_path):
    # A moov whose only trak has no mdia box at all.
    tkhd = _full_box(b"tkhd", b"\x00" * 60)
    moov = _box(b"moov", _box(b"trak", tkhd))
    video = tmp_path / "audio-only.mp4"
    video.write_bytes(moov)

    assert get_video_dimensions(str(video)) is None


def test_webm_dimensions(tmp_path):
    video = tmp_path / "portrait.webm"
    video.write_bytes(build_webm(720, 1280))

    assert get_video_dimensions(str(video)) == (720, 1280)


def test_webm_non_video_track_is_ignored(tmp_path):
    video = tmp_path / "audio.webm"
    video.write_bytes(build_webm(720, 1280, track_type=2))

    assert get_video_dimensions(str(video)) is None


def test_container_signature_wins_over_extension(tmp_path):
    """A WebM file named ``.mp4`` is still parsed as WebM."""

    video = tmp_path / "actually-webm.mp4"
    video.write_bytes(build_webm(480, 832))

    assert get_video_dimensions(str(video)) == (480, 832)


def test_webp_renamed_to_mp4_is_read(tmp_path):
    """Animated WebP examples are frequently saved with a video extension."""

    vp8_payload = b"\x30\x36\x02" + b"\x9d\x01\x2a" + struct.pack("<HH", 450, 800)
    chunk = b"VP8 " + struct.pack("<I", len(vp8_payload)) + vp8_payload
    body = b"WEBP" + chunk
    riff = b"RIFF" + struct.pack("<I", len(body)) + body

    video = tmp_path / "animated.mp4"
    video.write_bytes(riff)

    assert get_video_dimensions(str(video)) == (450, 800)


def test_webp_vp8x_canvas_dimensions(tmp_path):
    vp8x_payload = b"\x00" * 4 + (449).to_bytes(3, "little") + (799).to_bytes(3, "little")
    chunk = b"VP8X" + struct.pack("<I", len(vp8x_payload)) + vp8x_payload
    body = b"WEBP" + chunk
    riff = b"RIFF" + struct.pack("<I", len(body)) + body

    video = tmp_path / "canvas.mp4"
    video.write_bytes(riff)

    assert get_video_dimensions(str(video)) == (450, 800)


def test_missing_file_returns_none(tmp_path):
    assert get_video_dimensions(str(tmp_path / "nope.mp4")) is None


def test_corrupt_file_returns_none(tmp_path):
    video = tmp_path / "corrupt.mp4"
    video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\xff" * 64)

    assert get_video_dimensions(str(video)) is None


def test_unsupported_extension_without_video_signature_returns_none(tmp_path):
    """A non-video file is not probed just because of a video-like name."""

    video = tmp_path / "clip.avi"
    video.write_bytes(b"RIFF\x00\x00\x00\x00AVI LIST\x00\x00\x00\x00")

    assert get_video_dimensions(str(video)) is None
