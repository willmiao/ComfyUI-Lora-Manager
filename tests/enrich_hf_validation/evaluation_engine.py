"""Evaluate enriched ``.metadata.json`` quality across multiple dimensions.

Scoring rubric (per field):

- **Completeness**: Is the field populated with meaningful content?
- **Validity**: Does the value conform to expected constraints (controlled
  vocab, non-placeholder, parsable JSON)?
- **Accuracy**: (sub-sample only — requires manual verification against
  the HF README).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

from .config import (
    CIVITAI_MODEL_TAGS,
    PLACEHOLDER_VALUES,
    SUPPORTED_BASE_MODELS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_MIN_TAGS = 1
_MAX_TAGS = 8
_MIN_DESC_LENGTH = 20
_MIN_NOTES_LENGTH = 30

# Tags that the LLM sometimes emits but which are not meaningful content tags.
_TECH_TAGS = frozenset({
    "lora", "dreambooth", "text-to-image", "diffusers", "flux",
    "sdxl", "checkpoint", "pytorch", "safetensors", "fine-tuning",
    "stable-diffusion", "training", "stablediffusion",
})


def _is_placeholder(val: str) -> bool:
    return val.strip().lower() in PLACEHOLDER_VALUES


def _is_valid_trigger_words(words: List[str]) -> bool:
    """Return True if *words* is a non-empty list of real trigger words."""
    if not words:
        return False
    cleaned = [w.strip() for w in words if w.strip()]
    if not cleaned:
        return False
    # Reject if ALL entries are placeholders
    non_placeholder = [w for w in cleaned if not _is_placeholder(w)]
    return len(non_placeholder) > 0


def _is_valid_tags(tags: List[str]) -> bool:
    """Return True if *tags* is a reasonable list of content tags."""
    if not tags:
        return False
    cleaned = [t.strip().lower() for t in tags if t.strip()]
    if not cleaned:
        return False
    # At least one tag that isn't a technical keyword
    meaningful = [t for t in cleaned if t not in _TECH_TAGS]
    return len(meaningful) >= _MIN_TAGS


def _tag_priority_coverage(tags: List[str]) -> float:
    """Fraction of tags that align with the user's priority tag vocabulary."""
    if not tags:
        return 0.0
    priority_lower = {t.lower() for t in CIVITAI_MODEL_TAGS}
    matched = sum(1 for t in tags if t.strip().lower() in priority_lower)
    return matched / len(tags)


# ---------------------------------------------------------------------------
# Per-model evaluation
# ---------------------------------------------------------------------------

# Type alias for a score record
ScoreRecord = Dict[str, Any]


def evaluate_model(
    metadata: Dict[str, Any],
    model_path: str,
    repo_id: str,
    *,
    enrichment_success: bool,
    enrichment_errors: List[str],
) -> ScoreRecord:
    """Score a single enriched model's metadata.

    Returns a dict with per-field scores, a total score, and a list of
    flagged issues.
    """
    civitai = metadata.get("civitai") or {}
    trained_words: List[str] = civitai.get("trainedWords") or metadata.get("trainedWords") or []
    short_desc: str = civitai.get("description") or ""
    tags: List[str] = metadata.get("tags") or []
    notes: str = metadata.get("notes") or ""
    usage_tips_raw: str = metadata.get("usage_tips") or "{}"
    model_description: str = metadata.get("modelDescription") or ""
    base_model: str = metadata.get("base_model") or ""
    preview_url: str = metadata.get("preview_url") or ""
    confidence: str = metadata.get("_llm_confidence") or ""

    # --- base_model ---
    base_model_valid = base_model in SUPPORTED_BASE_MODELS
    base_model_filled = bool(base_model) and base_model != "Unknown"

    # --- trigger_words (trainedWords) ---
    triggers_valid = _is_valid_trigger_words(trained_words)

    # --- short_description (civitai.description) ---
    desc_filled = len(short_desc.strip()) >= _MIN_DESC_LENGTH

    # --- tags ---
    tags_valid = _is_valid_tags(tags)
    tags_priority_coverage = _tag_priority_coverage(tags)
    tags_no_technical = (
        sum(1 for t in tags if t.strip().lower() not in _TECH_TAGS) >= _MIN_TAGS
        if tags else False
    )

    # --- notes ---
    notes_filled = len(notes.strip()) >= _MIN_NOTES_LENGTH

    # --- usage_tips ---
    usage_tips_valid = False
    if usage_tips_raw.strip() and usage_tips_raw.strip() != "{}":
        try:
            parsed = json.loads(usage_tips_raw)
            if isinstance(parsed, dict) and len(parsed) > 0:
                usage_tips_valid = True
        except (json.JSONDecodeError, TypeError):
            pass

    # --- modelDescription (README → HTML) ---
    desc_html_filled = len(model_description.strip()) > 100

    # --- preview_url ---
    preview_filled = bool(preview_url) and os.path.exists(preview_url)

    # ------------------------------------------------------------------
    # Composite score (0-100)
    # ------------------------------------------------------------------

    field_scores = {
        "base_model": _score_bool(base_model_filled and base_model_valid, weight=15),
        "trigger_words": _score_bool(triggers_valid, weight=15),
        "short_description": _score_bool(desc_filled, weight=10),
        "tags": _score_bool(tags_valid, weight=15),
        "tags_priority_coverage": _score_continuous(tags_priority_coverage, weight=5),
        "notes": _score_bool(notes_filled, weight=5),
        "usage_tips": _score_bool(usage_tips_valid, weight=5),
        "modelDescription_html": _score_bool(desc_html_filled, weight=10),
        "preview_downloaded": _score_bool(preview_filled, weight=10),
    }

    # Deduct points for enrichment-level failures
    penalty = 0
    if enrichment_errors:
        penalty += 10
    if not enrichment_success:
        penalty += 20

    total_raw = sum(field_scores.values())
    total = max(0, min(100, total_raw - penalty))

    # ------------------------------------------------------------------
    # Flagged issues
    # ------------------------------------------------------------------

    issues: List[str] = []
    if not base_model_filled:
        issues.append("base_model is empty or 'Unknown'")
    elif not base_model_valid:
        issues.append(f"base_model '{base_model}' not in SUPPORTED_BASE_MODELS")
    if not triggers_valid:
        issues.append("trigger_words are missing or contain only placeholders")
    if not desc_filled:
        issues.append("short_description is too short or empty")
    if not tags_valid:
        issues.append("tags are missing, too few, or purely technical")
    if tags_valid and tags_priority_coverage < 0.5:
        issues.append("tags have low overlap with priority_tags (< 50%)")
    if not notes_filled:
        issues.append("notes are too short or empty")
    if not usage_tips_valid:
        issues.append("usage_tips is empty or invalid JSON")
    if not desc_html_filled:
        issues.append("modelDescription is too short (README may not have been converted)")
    if not preview_filled:
        issues.append("preview image not downloaded (URL missing or download failed)")

    return {
        "repo_id": repo_id,
        "model_path": model_path,
        "enrichment_success": enrichment_success,
        "total_score": total,
        "field_scores": field_scores,
        "issues": issues,
        "confidence_from_llm": confidence,
        "raw_values": {
            "base_model": base_model,
            "trigger_words": trained_words,
            "short_description": short_desc,
            "tags": tags,
            "notes": notes,
            "usage_tips": usage_tips_raw,
            "preview_url": preview_url,
            "has_modelDescription": len(model_description) > 0,
        },
    }


def _score_bool(condition: bool, weight: int = 10) -> int:
    return weight if condition else 0


def _score_continuous(value: float, weight: int = 10) -> int:
    """Linear interpolation: value 0.0 → 0, value 1.0 → *weight*."""
    return int(round(value * weight))


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------


def evaluate_batch(
    enriched: List[Dict[str, Any]],
) -> List[ScoreRecord]:
    """Evaluate a list of enrichment results.

    Each entry in *enriched* should have keys:
      ``repo_id``, ``model_path``, ``metadata`` (the enriched dict),
      ``success``, ``errors``.
    """
    scores: List[ScoreRecord] = []
    for entry in enriched:
        record = evaluate_model(
            metadata=entry.get("metadata", {}),
            model_path=entry.get("model_path", ""),
            repo_id=entry.get("repo_id", ""),
            enrichment_success=entry.get("success", False),
            enrichment_errors=entry.get("errors", []),
        )
        scores.append(record)
    return scores


# ---------------------------------------------------------------------------
# Aggregate statistics
# ---------------------------------------------------------------------------


def aggregate_scores(scores: List[ScoreRecord]) -> Dict[str, Any]:
    """Compute aggregate stats across all scored models."""
    n = len(scores)
    if n == 0:
        return {"error": "no scores to aggregate"}

    field_names = [
        "base_model", "trigger_words", "short_description", "tags",
        "tags_priority_coverage", "notes", "usage_tips",
        "modelDescription_html", "preview_downloaded",
    ]
    possible = {f: 15 if f == "base_model" or f == "trigger_words" or f == "tags" else
                   10 if f == "short_description" or f == "modelDescription_html" or f == "preview_downloaded" else
                   5
                for f in field_names}

    # Per-field aggregate
    field_agg: Dict[str, Any] = {}
    for fn in field_names:
        vals = [s["field_scores"].get(fn, 0) for s in scores]
        max_per_field = possible[fn]
        field_agg[fn] = {
            "mean": round(sum(vals) / n, 1) if n else 0,
            "fill_rate_pct": round(
                sum(1 for v in vals if v >= max_per_field) / n * 100, 1
            ) if n else 0.0,
            "partial_rate_pct": round(
                sum(1 for v in vals if 0 < v < max_per_field) / n * 100, 1
            ) if n else 0.0,
            "empty_rate_pct": round(
                sum(1 for v in vals if v == 0) / n * 100, 1
            ) if n else 0.0,
        }

    # Total score distribution
    total_scores = [s["total_score"] for s in scores]
    total_agg = {
        "mean": round(sum(total_scores) / n, 1) if n else 0,
        "median": _median(total_scores),
        "min": min(total_scores) if total_scores else 0,
        "max": max(total_scores) if total_scores else 0,
        "bins": {
            "excellent_80+": sum(1 for s in total_scores if s >= 80),
            "good_60_79": sum(1 for s in total_scores if 60 <= s < 80),
            "fair_40_59": sum(1 for s in total_scores if 40 <= s < 60),
            "poor_20_39": sum(1 for s in total_scores if 20 <= s < 40),
            "bad_0_19": sum(1 for s in total_scores if s < 20),
        },
    }

    # Issue frequency
    issue_counter: Dict[str, int] = {}
    for s in scores:
        for issue in s["issues"]:
            issue_counter[issue] = issue_counter.get(issue, 0) + 1
    top_issues = sorted(issue_counter.items(), key=lambda x: -x[1])

    # Confidence distribution
    conf_counter: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "": 0}
    for s in scores:
        c = (s.get("confidence_from_llm") or "").strip().lower()
        if c in conf_counter:
            conf_counter[c] += 1
        else:
            conf_counter[""] += 1

    # Success / timeout / failure stats
    success_count = sum(1 for s in scores if s["enrichment_success"])
    fail_count = n - success_count

    return {
        "model_count": n,
        "success_count": success_count,
        "fail_count": fail_count,
        "total_score": total_agg,
        "field_aggregates": field_agg,
        "top_issues": top_issues[:15],
        "confidence_distribution": conf_counter,
    }


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    m = len(sorted_v) // 2
    if len(sorted_v) % 2 == 0:
        return round((sorted_v[m - 1] + sorted_v[m]) / 2, 1)
    return round(sorted_v[m], 1)
