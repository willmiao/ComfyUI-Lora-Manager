"""Shared interpretation of CivitAI's ``paidAccess`` DTO.

One rule for the whole backend: the update service (badges, update filters, price
tracking) and the download gate both ask these helpers, so a version can never be
"paid" for one consumer and "free" for another.

Why the rules look like this
----------------------------
CivitAI's public v1 API only returns a non-null DTO for an *active* gate: a lapsed
gate stays in the database as a tombstone but is filtered out server-side
(``toPublicPaidAccessDto`` in civitai's ``server/services/paid-access.service.ts``).
A timed gate whose end time has not been recorded yet is reported as
``{"permanent": false, "endsAt": null}`` and is still enforced — such a version
reports ``canDownload: false`` on the model page — so it must NOT be discarded.
Dropping it (the previous behaviour) hid real gates, which is the class of bug
reported in issue #1060.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

__all__ = [
    "normalize_paid_access",
    "is_permanent_paid",
    "is_gate_active",
    "is_early_access_deadline_active",
    "parse_civitai_timestamp",
]

# A DTO that carries neither key is not a gate signal at all (defensive: CivitAI
# never emits a bare ``{}``, but other metadata sources might).
_PAID_ACCESS_KEYS = ("permanent", "endsAt")


def parse_civitai_timestamp(value: Any) -> Optional[datetime]:
    """Parse a CivitAI ISO-8601 timestamp into an aware UTC datetime.

    Returns None for anything that is not a parsable string. Naive timestamps are
    assumed to be UTC, matching CivitAI's serialization.
    """

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_paid_access(value: Any) -> Optional[dict]:
    """Normalize a ``paidAccess`` value into ``{"permanent": bool, "endsAt": str|None}``.

    Accepts a mapping, a JSON string (the by-hash enrichment path carries the DTO as
    text), or None. Returns None when the value carries no gate signal.

    Note that ``{"permanent": False, "endsAt": None}`` is a *gate*: CivitAI reports
    it for a timed gate whose window end is not set yet, and enforces it.
    """

    if value is None:
        return None

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        value = parsed

    if not isinstance(value, Mapping):
        return None

    if not any(key in value for key in _PAID_ACCESS_KEYS):
        return None

    ends_at = value.get("endsAt")
    normalized_ends_at = ends_at.strip() if isinstance(ends_at, str) and ends_at.strip() else None
    return {
        "permanent": bool(value.get("permanent")),
        "endsAt": normalized_ends_at,
    }


def is_permanent_paid(paid_access: Optional[Mapping[str, Any]]) -> bool:
    """True when the gate never expires (a permanent paid version)."""

    return bool(paid_access and paid_access.get("permanent"))


def is_gate_active(
    paid_access: Optional[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """True when a normalized ``paidAccess`` gate is currently in force.

    Active means permanent, or a timed gate whose end is either still in the future
    or not recorded yet (CivitAI enforces the latter too). An unparsable end time is
    treated as active rather than free: the download would fail anyway, so the
    conservative reading matches what the user will experience.
    """

    if not paid_access:
        return False
    if paid_access.get("permanent"):
        return True

    ends_at = paid_access.get("endsAt")
    if not ends_at:
        # Timed gate with no recorded end — CivitAI still gates the download.
        return True

    parsed = parse_civitai_timestamp(ends_at)
    if parsed is None:
        return True

    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return parsed > reference


def is_early_access_deadline_active(
    ends_at: Any,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """True when a legacy ``earlyAccessEndsAt`` deadline is still in the future.

    Kept separate from :func:`is_gate_active` because the legacy field is a bare
    timestamp rather than a DTO. A present-but-unparsable value is treated as active,
    matching the previous conservative behaviour.
    """

    if not ends_at:
        return False

    parsed = parse_civitai_timestamp(ends_at)
    if parsed is None:
        return True

    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return parsed > reference
