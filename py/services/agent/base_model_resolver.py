"""Map a site-reported base model onto this system's canonical vocabulary.

Model sites name base models in their own terms: ModelScope publishes
``krea/Krea-2-Turbo`` and ``KREA_2_TURBO`` where this system expects the
canonical ``Krea 2``.  Turning one into the other is normally the LLM's job;
this module resolves the cases that can be decided safely so the canonical
field is still populated when the LLM returns nothing usable for it.

The resolver is deliberately strict, because a wrong base model written with
apparent authority is worse than no value at all:

* it only ever returns a name that is already present in *known_names*;
* matching is on the normalised form (lowercased, non-alphanumerics removed),
  so separators and casing are ignored but nothing is inferred;
* a bounded set of published variant suffixes may be stripped, and only when
  the remainder still matches a known name exactly.

Anything it cannot decide returns ``""``, and the caller falls back to the LLM.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

#: Variant suffixes sites append to a base-model *family* name.  Stripping one
#: is only attempted when the remainder matches a known name exactly, so an
#: unrecognised suffix can never produce a bogus match.
_VARIANT_SUFFIXES: tuple[str, ...] = (
    "turbo",
    "schnell",
    "lightning",
    "dev",
    "beta",
    "alpha",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(value: str) -> str:
    """Return the comparison form of *value*.

    Lowercases and drops every non-alphanumeric character, so ``KREA_2``,
    ``Krea 2``, ``krea-2`` and ``krea.2`` all collapse to ``krea2``.
    """

    return _NON_ALNUM.sub("", (value or "").lower())


def resolve_base_model(
    hints: Iterable[str], known_names: Sequence[str]
) -> str:
    """Return the canonical base model that *hints* refers to, or ``""``.

    Args:
        hints: Site-reported names, best first (e.g. an architecture enum
            before a link-style repository id).
        known_names: The canonical vocabulary; only these are ever returned.

    Returns:
        One of *known_names*, or ``""`` when nothing matches exactly.
    """

    normalized: dict[str, str] = {}
    for name in known_names:
        key = _normalize(name)
        if key and key not in normalized:
            normalized[key] = name
    if not normalized:
        return ""

    ordered = [hint for hint in hints if hint]

    # 1. Exact normalised match — the unambiguous case.
    for hint in ordered:
        candidate = _normalize(hint)
        if candidate in normalized:
            return normalized[candidate]

    # 2. Drop one published variant suffix and retry exactly.
    for hint in ordered:
        candidate = _normalize(hint)
        for suffix in _VARIANT_SUFFIXES:
            if not candidate.endswith(suffix) or candidate == suffix:
                continue
            stem = candidate[: -len(suffix)]
            if stem in normalized:
                return normalized[stem]

    return ""


__all__ = ["resolve_base_model"]
