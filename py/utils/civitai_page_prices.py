"""Extract buzz prices from a public CivitAI model page.

CivitAI's public REST API deliberately omits prices: ``paidAccess`` is trimmed to
``{permanent, endsAt}`` because "pricing belongs to the purchase flow" (see the
upstream ``toPublicPaidAccessDto``). The model *page*, however, ships the site's
own ``model.getById`` result inside its server-rendered Next.js payload, and that
payload carries the full ``paidAccess.terms`` — download price, generation price,
sale and the Blue Buzz flag.

Reading it is a plain anonymous page fetch: no API key, no internal endpoint, no
forged ``Origin``. It is still page data rather than a contract, so nothing in
this module may raise: an unrecognized shape degrades to ``None`` and the caller
keeps whatever price it already stored.

Shape this understands (verified against civitai.com and civitai.red)::

    <script id="__NEXT_DATA__" type="application/json">
      {"props": {"pageProps": {"trpcState": {"json": {"queries": [
        {"queryKey": [["model", "getById"], {...}],
         "state": {"data": {"modelVersions": [
            {"id": 3379626, "paidAccess": {
                "endsAt": null, "timeframeDays": null,
                "terms": {"download": {"price": 5000},
                          "generation": {"price": 100, "trialLimit": 5}},
                "sale": null}}
         ]}}}
      ]}}}}}
    </script>
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterator, Mapping, Optional

from .paid_access import is_gate_active, normalize_paid_access

logger = logging.getLogger(__name__)

__all__ = ["parse_model_page_prices", "MAX_PAGE_BYTES"]

# Bound the payload before parsing: a model page is a few hundred KB, so anything
# far larger is not a page we want to hold in memory.
MAX_PAGE_BYTES = 8 * 1024 * 1024

_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)

# The procedure that carries per-version pricing on a model page.
_MODEL_QUERY_PATH = ("model", "getById")


def parse_model_page_prices(html: Any) -> Optional[Dict[int, Dict[str, Any]]]:
    """Return ``{version_id: price fields}`` for a model page, or None.

    Only versions with an *active* gate appear: the page payload also carries
    lapsed gates as tombstones (a version with ``endsAt`` in the past is freely
    downloadable), and those must not be reported as priced.

    Returns None when the page carries no usable payload at all (missing script
    tag, malformed JSON, unexpected structure, challenge page).
    """

    if not isinstance(html, str) or not html:
        return None
    if len(html) > MAX_PAGE_BYTES:
        logger.debug("CivitAI model page too large to parse (%d bytes)", len(html))
        return None

    match = _NEXT_DATA_RE.search(html)
    if match is None:
        return None

    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return None

    versions = _find_model_versions(payload)
    if versions is None:
        return None

    prices: Dict[int, Dict[str, Any]] = {}
    for entry in versions:
        if not isinstance(entry, Mapping):
            continue
        version_id = _coerce_int(entry.get("id"))
        if version_id is None:
            continue
        price_fields = _price_fields(entry.get("paidAccess"))
        if price_fields is not None:
            prices[version_id] = price_fields

    return prices


def _find_model_versions(payload: Any) -> Optional[list]:
    """Locate ``modelVersions`` inside the dehydrated tRPC state.

    The query order is not stable (several procedures are dehydrated per page), so
    the query is selected by key rather than position.
    """

    if not isinstance(payload, Mapping):
        return None

    for state in _iter_trpc_states(payload):
        queries = state.get("queries")
        if not isinstance(queries, list):
            continue
        for query in queries:
            if not isinstance(query, Mapping):
                continue
            if not _matches_model_query(query.get("queryKey")):
                continue
            data = (query.get("state") or {}).get("data")
            if isinstance(data, Mapping):
                versions = data.get("modelVersions")
                if isinstance(versions, list):
                    return versions
    return None


def _iter_trpc_states(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Yield the dehydrated tRPC state objects found under ``props.pageProps``."""

    props = payload.get("props")
    if not isinstance(props, Mapping):
        return
    page_props = props.get("pageProps")
    if not isinstance(page_props, Mapping):
        return

    candidates = [page_props.get("trpcState")]
    # Older/other Next.js builds keep the state one level deeper.
    dehydrated = page_props.get("dehydratedState")
    if dehydrated is not None:
        candidates.append(dehydrated)

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        for key in ("json", "superjson", "dehydratedState"):
            nested = candidate.get(key)
            if isinstance(nested, Mapping):
                yield nested
        yield candidate


def _matches_model_query(query_key: Any) -> bool:
    if not isinstance(query_key, (list, tuple)) or not query_key:
        return False
    first = query_key[0]
    if not isinstance(first, (list, tuple)) or len(first) < 2:
        return False
    return str(first[0]) == _MODEL_QUERY_PATH[0] and str(first[1]) == _MODEL_QUERY_PATH[1]


def _price_fields(raw_paid_access: Any) -> Optional[Dict[str, Any]]:
    """Build the price fields for one version, or None when it is not gated."""

    dto = _coerce_dto(raw_paid_access)
    if dto is None:
        return None

    info = normalize_paid_access(dto)
    if not info or not is_gate_active(info):
        return None

    terms = dto.get("terms")
    if not isinstance(terms, Mapping):
        terms = {}

    list_price = _download_price(terms)
    effective_price = list_price

    sale = dto.get("sale")
    sale_ends_at = None
    if isinstance(sale, Mapping):
        sale_ends_at = _coerce_str(sale.get("endsAt"))
        buyer_terms = sale.get("buyerTerms")
        if isinstance(buyer_terms, Mapping):
            sale_price = _download_price(buyer_terms)
            if sale_price is not None:
                effective_price = sale_price

    return {
        "price_buzz": effective_price,
        "list_price_buzz": list_price,
        "generation_price_buzz": _generation_price(terms),
        "accepts_blue_buzz": bool(terms.get("acceptsBlueBuzz")),
        "price_sale_ends_at": sale_ends_at,
    }


def _coerce_dto(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value if isinstance(value, Mapping) else None


def _download_price(terms: Mapping[str, Any]) -> Optional[int]:
    download = terms.get("download")
    if not isinstance(download, Mapping):
        return None
    return _coerce_price(download.get("price"))


def _generation_price(terms: Mapping[str, Any]) -> Optional[int]:
    generation = terms.get("generation")
    if not isinstance(generation, Mapping):
        return None
    # `{free: true}` has no price of its own, and a paid tier may omit `price` to
    # fall back to the download price — the download price is already captured
    # separately, so only an explicit number is reported here.
    return _coerce_price(generation.get("price"))


def _coerce_price(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        price = int(value)
        return price if price >= 0 else None
    if isinstance(value, str):
        try:
            price = int(float(value.strip()))
        except (TypeError, ValueError):
            return None
        return price if price >= 0 else None
    return None


def _coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return None
    return None


def _coerce_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
