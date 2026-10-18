"""In-memory store for the LoRA Manager page's active filters.

The manager page keeps its filter state in localStorage for its own
restoration, but the ComfyUI node autocomplete runs in a potentially
different browser/origin (or Electron shell) where that storage is not
shared. This store mirrors the active filters server-side so the
``/api/lm/{prefix}/relative-paths`` endpoint can inject them into
autocomplete searches regardless of which client set them.

State is process-local and intentionally not persisted; the manager page
re-pushes its restored state on load.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Keys copied from the manager page's persisted filter snapshot.
_FILTER_KEYS = (
    "baseModel",
    "tags",
    "autoTags",
    "modelTypes",
    "tagLogic",
    "license",
)


class ActiveFiltersStore:
    """Process-local store of active filters, keyed by model type."""

    _instance: Optional["ActiveFiltersStore"] = None

    def __init__(self) -> None:
        self._filters: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "ActiveFiltersStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Drop the singleton (test isolation)."""
        cls._instance = None

    def set_filters(self, model_type: str, payload: Dict[str, Any]) -> None:
        """Replace the stored active filters for a model type.

        Only recognized keys are kept; everything else is discarded.
        """
        filters = payload.get("filters")
        sanitized: Dict[str, Any] = {
            "activeFolder": payload.get("activeFolder"),
            "recursiveSearch": bool(payload.get("recursiveSearch", True)),
            "filters": (
                {key: filters[key] for key in _FILTER_KEYS if key in filters}
                if isinstance(filters, dict)
                else None
            ),
        }
        self._filters[model_type] = sanitized

    def get_filters(self, model_type: str) -> Optional[Dict[str, Any]]:
        """Return the stored payload for a model type, or None if unset."""
        return self._filters.get(model_type)

    def clear(self, model_type: str) -> None:
        self._filters.pop(model_type, None)


def active_filters_to_query_kwargs(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map a stored active-filters payload to ``search_relative_paths`` kwargs.

    Mirrors the query-param mapping that the ComfyUI autocomplete used to
    build client-side from localStorage (web/comfyui/autocomplete.js).
    """
    kwargs: Dict[str, Any] = {}
    if not payload:
        return kwargs

    active_folder = payload.get("activeFolder")
    recursive = payload.get("recursiveSearch", True)

    if active_folder and active_folder != "null":
        kwargs["folder"] = active_folder
    elif not recursive:
        # Root folder with recursion disabled mirrors the page list,
        # which matches only root-level files via folder=''.
        kwargs["folder"] = ""

    filters = payload.get("filters")
    if isinstance(filters, dict):
        base_models = filters.get("baseModel")
        if isinstance(base_models, list):
            kwargs["base_models"] = [m for m in base_models if m]

        for source_key, target_key in (("tags", "tags"), ("autoTags", "auto_tags")):
            states = filters.get(source_key)
            if isinstance(states, dict):
                mapped = {
                    tag: state
                    for tag, state in states.items()
                    if state in ("include", "exclude")
                }
                if mapped:
                    kwargs[target_key] = mapped

        model_types = filters.get("modelTypes")
        if isinstance(model_types, list):
            kwargs["model_types"] = [t for t in model_types if t]

        tag_logic = filters.get("tagLogic")
        if tag_logic:
            kwargs["tag_logic"] = tag_logic

        license_filter = filters.get("license")
        if isinstance(license_filter, dict):
            no_credit = license_filter.get("noCredit")
            if no_credit == "include":
                kwargs["credit_required"] = False
            elif no_credit == "exclude":
                kwargs["credit_required"] = True
            allow_selling = license_filter.get("allowSelling")
            if allow_selling == "include":
                kwargs["allow_selling_generated_content"] = True
            elif allow_selling == "exclude":
                kwargs["allow_selling_generated_content"] = False

    kwargs["recursive"] = recursive
    return kwargs
