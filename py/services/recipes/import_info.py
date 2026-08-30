"""Import provenance helpers for recipes.

Builds the ``import_info`` block persisted on a recipe: the import channel
(batch import / single URL / local file / upload / widget) and, when the
recipe ended up with no LoRAs, a machine-readable reason plus the diagnostic
details that led to it. The recipe modal renders this block in a collapsed
"Why no LoRAs?" panel; legacy recipes without ``import_info`` fall back to a
frontend heuristic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Import channels (how the recipe entered the library).
CHANNEL_BATCH_IMPORT_URL = "batch_import_url"
CHANNEL_BATCH_IMPORT_LOCAL = "batch_import_local"
CHANNEL_URL = "url"
CHANNEL_LOCAL = "local"
CHANNEL_UPLOAD = "upload"
CHANNEL_WIDGET = "widget"
CHANNEL_REIMPORT_URL = "reimport_url"
CHANNEL_REIMPORT_LOCAL = "reimport_local"

_URL_CHANNELS = frozenset(
    {CHANNEL_BATCH_IMPORT_URL, CHANNEL_URL, CHANNEL_REIMPORT_URL}
)

# No-LoRA reason codes (persisted, consumed by the recipe modal).
REASON_NO_LORAS_USED = "no_loras_used"
REASON_API_NO_LORA_RESOURCES = "api_meta_no_lora_resources"
REASON_API_META_MISSING = "api_meta_missing"
REASON_NO_EMBEDDED_METADATA = "no_embedded_metadata"
REASON_WORKFLOW_METADATA_LIMITED = "workflow_metadata_limited"
REASON_VIDEO_NO_METADATA = "video_no_metadata"
REASON_METADATA_UNSUPPORTED = "metadata_unsupported"
REASON_UNKNOWN = "unknown"

_COMFY_PARSER_NAME = "ComfyMetadataParser"

# Cap for api_meta_keys kept in details — enough for the UI bullet without
# bloating the recipe JSON.
_MAX_DETAIL_KEYS = 12


def compute_no_loras_reason(
    channel: str, diagnostics: Optional[Dict[str, Any]]
) -> str:
    """Classify why an import produced no LoRA entries.

    Args:
        channel: One of the CHANNEL_* constants.
        diagnostics: Signals collected during analysis (see
            ``RecipeAnalysisService``), or None for channels without analysis
            (e.g. widget saves).
    """
    diag = diagnostics or {}

    if diag.get("is_video"):
        return REASON_VIDEO_NO_METADATA

    # Embedded metadata that is a ComfyUI workflow: LoRA extraction from
    # workflows is limited, so report that specifically.
    parser = diag.get("exif_parser") or diag.get("parser")
    if parser == _COMFY_PARSER_NAME:
        return REASON_WORKFLOW_METADATA_LIMITED

    if channel in _URL_CHANNELS:
        if not diag.get("civitai_image"):
            # Generic (non-CivitAI) URL: only embedded metadata is available.
            if not diag.get("exif_present"):
                return REASON_NO_EMBEDDED_METADATA
            return (
                REASON_NO_LORAS_USED if parser else REASON_METADATA_UNSUPPORTED
            )
        # NOTE: no "parsed EXIF means no LoRAs were used" shortcut here.
        # CivitAI's onsite generator writes A1111-style EXIF (prompt, seed,
        # steps, ...) WITHOUT LoRA references — LoRA usage lives only in
        # CivitAI-internal data — so cleanly parsed EXIF cannot prove the
        # generation used no LoRAs. Report the API meta shape instead.
        api_keys = diag.get("api_meta_keys") or []
        api_mvids = diag.get("api_model_version_ids") or 0
        if api_keys or api_mvids:
            return REASON_API_NO_LORA_RESOURCES
        return REASON_API_META_MISSING

    if channel == CHANNEL_WIDGET:
        return REASON_NO_LORAS_USED

    # Local file / upload / local re-import: embedded metadata only.
    if not diag.get("exif_present"):
        return REASON_NO_EMBEDDED_METADATA
    return REASON_NO_LORAS_USED if parser else REASON_METADATA_UNSUPPORTED


def build_import_info(
    channel: str,
    diagnostics: Optional[Dict[str, Any]],
    loras: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Build the ``import_info`` block persisted on a recipe.

    Always records the import channel; adds ``reason`` and ``details`` only
    when the recipe has no LoRAs.
    """
    info: Dict[str, Any] = {"channel": channel}
    if loras:
        return info

    info["reason"] = compute_no_loras_reason(channel, diagnostics)

    diag = diagnostics or {}
    details: Dict[str, Any] = {}
    api_keys = diag.get("api_meta_keys")
    if api_keys:
        details["api_meta_keys"] = list(api_keys)[:_MAX_DETAIL_KEYS]
    api_mvids = diag.get("api_model_version_ids")
    if api_mvids is not None:
        details["api_model_version_ids"] = api_mvids
    if "exif_present" in diag:
        details["exif_present"] = bool(diag.get("exif_present"))
    if diag.get("exif_parser"):
        details["exif_parser"] = diag["exif_parser"]
    if diag.get("is_video"):
        details["is_video"] = True
    if details:
        info["details"] = details

    return info
