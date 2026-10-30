"""Resolve a workflow's base model from the models its graph references.

Workflows are JSON documents — they carry model file names (and sometimes
CivitAI URNs), never a base model label. The label is derived here:

1. Names pulled from known checkpoint/diffusion loader nodes
   (``WorkflowAnalysis.primary_model_refs``) are looked up in the local
   checkpoint library; the matched entries vote on the base model.
2. When no local checkpoint matches, every referenced model file name is tried
   against the local LoRA library and the matched LoRAs vote (mirrors
   ``RecipeScanner._determine_base_model``).
3. Optionally (one-off user actions only, never bulk scans), CivitAI URNs
   embedded in the graph are resolved through the metadata provider.

Only known library answers feed the votes, so an Unknown entry in the library
never drowns out a known one.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from ..utils.model_utils import determine_base_model

logger = logging.getLogger(__name__)


def _known_base_model(value: Any) -> Optional[str]:
    """Return the base model string when it is actually known, else None."""
    text = str(value or "").strip()
    if not text or text.casefold() == "unknown":
        return None
    return text


def _majority_vote(votes: Dict[str, int]) -> Optional[str]:
    """Pick the most voted base model; ties break alphabetically (stable)."""
    if not votes:
        return None
    return sorted(votes.items(), key=lambda item: (-item[1], item[0]))[0][0]


async def _vote_from_scanner(refs: Sequence[str], scanner: Any) -> Dict[str, int]:
    """Match refs against a scanner's cache and tally known base models."""
    votes: Dict[str, int] = {}
    if scanner is None:
        return votes
    for ref in refs:
        try:
            matches = await scanner.find_models_by_name(ref)
        except Exception:
            logger.debug("Model name lookup failed for %r", ref, exc_info=True)
            continue
        for match in matches:
            base_model = _known_base_model(match.get("base_model"))
            if base_model:
                votes[base_model] = votes.get(base_model, 0) + 1
    return votes


async def _resolve_from_civitai_refs(
    civitai_refs: Sequence[str], provider: Any = None
) -> Optional[str]:
    """Resolve the base model from the first CivitAI URN that answers."""
    refs = [ref for ref in civitai_refs if isinstance(ref, str)]
    if not refs:
        return None
    if provider is None:
        try:
            from .metadata_service import get_default_metadata_provider

            provider = await get_default_metadata_provider()
        except Exception:
            logger.debug("No metadata provider for workflow base model", exc_info=True)
            return None
    if provider is None:
        return None

    for ref in refs:
        # Refs look like "civitai:{model_id}@{version_id}".
        body = ref[len("civitai:"):] if ref.startswith("civitai:") else ref
        if "@" not in body:
            continue
        version_id = body.rsplit("@", 1)[-1].strip()
        if not version_id.isdigit():
            continue
        try:
            result = await provider.get_model_version_info(version_id)
        except Exception:
            logger.debug(
                "CivitAI base model lookup failed for %s", ref, exc_info=True
            )
            continue
        version_info = result[0] if isinstance(result, tuple) else result
        if not isinstance(version_info, dict):
            continue
        base_model = _known_base_model(
            determine_base_model(version_info.get("baseModel", ""))
        )
        if base_model:
            return base_model
    return None


async def resolve_workflow_base_model(
    *,
    primary_model_refs: Sequence[str],
    model_refs: Sequence[str],
    civitai_refs: Sequence[str] = (),
    checkpoint_name_hint: Optional[str] = None,
    checkpoint_scanner: Any = None,
    lora_scanner: Any = None,
    include_remote: bool = False,
    metadata_provider: Any = None,
) -> Optional[str]:
    """Resolve the base model for a workflow's referenced models.

    ``checkpoint_name_hint`` is the primary checkpoint observed at generation
    time (from the metadata collector's primary-sampler tracing); when given
    it outranks the static votes, since it names the model that actually fed
    the sampler. A hint that does not resolve locally is ignored, not treated
    as an override. Returns None when nothing resolves — callers keep the
    stored value (or the "Unknown" default) in that case. ``include_remote``
    enables the CivitAI URN fallback and must stay off for bulk/scan paths.
    """
    if checkpoint_scanner is None or lora_scanner is None:
        try:
            from .service_registry import ServiceRegistry

            if checkpoint_scanner is None:
                checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
            if lora_scanner is None:
                lora_scanner = await ServiceRegistry.get_lora_scanner()
        except Exception:
            logger.debug(
                "Model scanners unavailable for base model resolution", exc_info=True
            )

    if checkpoint_name_hint:
        hint_votes = await _vote_from_scanner([checkpoint_name_hint], checkpoint_scanner)
        winner = _majority_vote(hint_votes)
        if winner:
            return winner

    checkpoint_votes = await _vote_from_scanner(primary_model_refs, checkpoint_scanner)
    winner = _majority_vote(checkpoint_votes)
    if winner:
        return winner

    lora_votes = await _vote_from_scanner(model_refs, lora_scanner)
    winner = _majority_vote(lora_votes)
    if winner:
        return winner

    if include_remote:
        return await _resolve_from_civitai_refs(civitai_refs, metadata_provider)
    return None

