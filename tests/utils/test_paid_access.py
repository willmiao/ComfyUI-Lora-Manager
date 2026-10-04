"""Tests for the shared CivitAI paidAccess interpretation.

These rules decide both the Paid/Early Access badges and whether a download is
warned about, so the interesting cases are the boundary shapes CivitAI actually
emits.
"""

from datetime import datetime, timezone

import pytest

from py.utils.paid_access import (
    is_early_access_deadline_active,
    is_gate_active,
    is_permanent_paid,
    normalize_paid_access,
    parse_civitai_timestamp,
)

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("{not json", None),
        ("[1, 2]", None),
        ({}, None),
        ({"unknown": 1}, None),
        # A non-null DTO from CivitAI's public API is always an active gate, so a
        # timed gate with no recorded end must survive normalization.
        ({"permanent": False, "endsAt": None}, {"permanent": False, "endsAt": None}),
        ({"permanent": True, "endsAt": None}, {"permanent": True, "endsAt": None}),
        (
            {"permanent": False, "endsAt": "2026-10-10T13:10:17.404Z"},
            {"permanent": False, "endsAt": "2026-10-10T13:10:17.404Z"},
        ),
    ],
)
def test_normalize_paid_access_shapes(value, expected):
    assert normalize_paid_access(value) == expected


def test_normalize_paid_access_accepts_json_text():
    """The by-hash enrichment path can carry the DTO as a JSON string."""

    assert normalize_paid_access('{"permanent": true, "endsAt": null}') == {
        "permanent": True,
        "endsAt": None,
    }


def test_normalize_paid_access_blank_ends_at_is_none():
    assert normalize_paid_access({"permanent": False, "endsAt": "  "}) == {
        "permanent": False,
        "endsAt": None,
    }


def test_is_permanent_paid():
    assert is_permanent_paid({"permanent": True, "endsAt": None}) is True
    assert is_permanent_paid({"permanent": False, "endsAt": None}) is False
    assert is_permanent_paid(None) is False


@pytest.mark.parametrize(
    "paid_access,expected",
    [
        (None, False),
        ({"permanent": False, "endsAt": None}, True),
        ({"permanent": True, "endsAt": None}, True),
        # A permanent gate with a stale endsAt stays active.
        ({"permanent": True, "endsAt": "2020-01-01T00:00:00.000Z"}, True),
        ({"permanent": False, "endsAt": "2026-10-10T13:10:17.404Z"}, True),
        ({"permanent": False, "endsAt": "2026-08-27T16:56:57.438Z"}, False),
        ({"permanent": False, "endsAt": "not-a-date"}, True),
    ],
)
def test_is_gate_active(paid_access, expected):
    assert is_gate_active(paid_access, now=NOW) is expected


@pytest.mark.parametrize(
    "ends_at,expected",
    [
        (None, False),
        ("", False),
        ("2026-10-10T13:10:17.404Z", True),
        ("2026-08-27T16:56:57.438Z", False),
        ("garbage", True),
    ],
)
def test_is_early_access_deadline_active(ends_at, expected):
    assert is_early_access_deadline_active(ends_at, now=NOW) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (123, None),
        ("", None),
        ("garbage", None),
        ("2026-10-10T13:10:17.404Z", datetime(2026, 10, 10, 13, 10, 17, 404000, tzinfo=timezone.utc)),
        # Naive timestamps are assumed UTC.
        ("2026-10-10T13:10:17", datetime(2026, 10, 10, 13, 10, 17, tzinfo=timezone.utc)),
    ],
)
def test_parse_civitai_timestamp(value, expected):
    assert parse_civitai_timestamp(value) == expected
