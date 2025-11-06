"""Utilities for working with Civitai assets."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Dict, Iterable, Mapping, Sequence
from urllib.parse import urlparse, urlunparse


class CommercialUseLevel(IntEnum):
    """Enumerate supported commercial use permission levels."""

    NONE = 0
    IMAGE = 1
    RENT_CIVIT = 2
    RENT = 3
    SELL = 4


_DEFAULT_ALLOW_COMMERCIAL_USE: Sequence[str] = ("Sell",)
_LICENSE_DEFAULTS: Dict[str, Any] = {
    "allowNoCredit": True,
    "allowCommercialUse": _DEFAULT_ALLOW_COMMERCIAL_USE,
    "allowDerivatives": True,
    "allowDifferentLicense": True,
}
_COMMERCIAL_VALUE_TO_LEVEL = {
    "none": CommercialUseLevel.NONE,
    "image": CommercialUseLevel.IMAGE,
    "rentcivit": CommercialUseLevel.RENT_CIVIT,
    "rent": CommercialUseLevel.RENT,
    "sell": CommercialUseLevel.SELL,
}


def _normalize_commercial_values(value: Any) -> Sequence[str]:
    """Return a normalized list of commercial permissions preserving source values."""

    if value is None:
        return list(_DEFAULT_ALLOW_COMMERCIAL_USE)

    if isinstance(value, str):
        return [value]

    if isinstance(value, Iterable):
        result = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                result.append(item)
                continue
            result.append(str(item))
        if result:
            return result

    return list(_DEFAULT_ALLOW_COMMERCIAL_USE)


def _to_bool(value: Any, fallback: bool) -> bool:
    if value is None:
        return fallback
    return bool(value)


def resolve_license_payload(model_data: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Extract license fields from model metadata applying documented defaults."""

    payload: Dict[str, Any] = {}

    allow_no_credit = payload["allowNoCredit"] = _to_bool(
        (model_data or {}).get("allowNoCredit"),
        _LICENSE_DEFAULTS["allowNoCredit"],
    )

    commercial = _normalize_commercial_values(
        (model_data or {}).get("allowCommercialUse"),
    )
    payload["allowCommercialUse"] = list(commercial)

    allow_derivatives = payload["allowDerivatives"] = _to_bool(
        (model_data or {}).get("allowDerivatives"),
        _LICENSE_DEFAULTS["allowDerivatives"],
    )

    allow_different_license = payload["allowDifferentLicense"] = _to_bool(
        (model_data or {}).get("allowDifferentLicense"),
        _LICENSE_DEFAULTS["allowDifferentLicense"],
    )

    # Ensure booleans are plain bool instances
    payload["allowNoCredit"] = bool(allow_no_credit)
    payload["allowDerivatives"] = bool(allow_derivatives)
    payload["allowDifferentLicense"] = bool(allow_different_license)

    return payload


def _resolve_commercial_level(values: Sequence[str]) -> CommercialUseLevel:
    level = CommercialUseLevel.NONE
    for value in values:
        normalized = str(value).strip().lower().replace("_", "")
        normalized = normalized.replace("-", "")
        candidate = _COMMERCIAL_VALUE_TO_LEVEL.get(normalized)
        if candidate is None:
            continue
        if candidate > level:
            level = candidate
    return level


def build_license_flags(payload: Mapping[str, Any] | None) -> int:
    """Encode license payload into a compact bitset for cache storage."""

    resolved = resolve_license_payload(payload or {})

    flags = 0
    if resolved.get("allowNoCredit", True):
        flags |= 1 << 0

    commercial_level = _resolve_commercial_level(resolved.get("allowCommercialUse", ()))
    flags |= (int(commercial_level) & 0b111) << 1

    if resolved.get("allowDerivatives", True):
        flags |= 1 << 4

    if resolved.get("allowDifferentLicense", True):
        flags |= 1 << 5

    return flags


def resolve_license_info(model_data: Mapping[str, Any] | None) -> tuple[Dict[str, Any], int]:
    """Return normalized license payload and its encoded bitset."""

    payload = resolve_license_payload(model_data)
    return payload, build_license_flags(payload)


def rewrite_preview_url(source_url: str | None, media_type: str | None = None) -> tuple[str | None, bool]:
    """Rewrite Civitai preview URLs to use optimized renditions.

    Args:
        source_url: Original preview URL from the Civitai API.
        media_type: Optional media type hint (e.g. ``"image"`` or ``"video"``).

    Returns:
        A tuple of the potentially rewritten URL and a flag indicating whether the
        replacement occurred. When the URL is not rewritten, the original value is
        returned with ``False``.
    """
    if not source_url:
        return source_url, False

    try:
        parsed = urlparse(source_url)
    except ValueError:
        return source_url, False

    if parsed.netloc.lower() != "image.civitai.com":
        return source_url, False

    replacement = "/width=450,optimized=true"
    if (media_type or "").lower() == "video":
        replacement = "/transcode=true,width=450,optimized=true"

    if "/original=true" not in parsed.path:
        return source_url, False

    updated_path = parsed.path.replace("/original=true", replacement, 1)
    if updated_path == parsed.path:
        return source_url, False

    rewritten = urlunparse(parsed._replace(path=updated_path))
    return rewritten, True


__all__ = [
    "CommercialUseLevel",
    "build_license_flags",
    "resolve_license_payload",
    "resolve_license_info",
    "rewrite_preview_url",
]
