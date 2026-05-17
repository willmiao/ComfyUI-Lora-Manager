"""
Auto-tag extraction service for model cards.

Extracts implicit model attributes (HIGH/LOW, I2V/T2V/TI2V, Lightning, Turbo)
from filename, base_model, and CivitAI version name — no manual tagging required.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set

# ── Tag category definitions ──────────────────────────────────────────
# Each category maps a display label to a regex pattern.
# Patterns are case-insensitive and matched against filename, base_model,
# and civitai version name.

# Use (?<![a-zA-Z0-9]) and (?![a-zA-Z0-9]) instead of \b because
# Python's \b treats underscore as a word character, so \bHIGH\b
# won't match '_HIGH_' in filenames.
_B = r"(?<![a-zA-Z0-9])"   # left boundary
_E = r"(?![a-zA-Z0-9])"    # right boundary

AUTO_TAG_CATEGORIES: Dict[str, str] = {
    "HIGH":      _B + r"HIGH" + _E,
    "LOW":       _B + r"(?<!F)LOW" + _E,
    "I2V":       _B + r"I2V" + _E,
    "T2V":       _B + r"T2V" + _E,
    "TI2V":      _B + r"TI2V" + _E,
    "Lightning": _B + r"Lightning" + _E,
    "Turbo":     _B + r"Turbo" + _E,
}

# Tags that belong to the "mode" group (HIGH/LOW)
MODE_TAGS = {"HIGH", "LOW"}

# Tags that belong to the "video mode" group (I2V/T2V/TI2V)
VIDEO_MODE_TAGS = {"I2V", "T2V", "TI2V"}

# Tags that belong to the "speed/optimization" group
SPEED_TAGS = {"Lightning", "Turbo"}

# ── Display category groups (for settings UI) ─────────────────────────

AUTO_TAG_GROUPS = {
    "mode":   {"HIGH", "LOW"},
    "video":  {"I2V", "T2V", "TI2V"},
    "speed":  {"Lightning", "Turbo"},
}

# Default enabled categories
DEFAULT_ENABLED_GROUPS = {"mode", "video"}


def _collect_sources(model_data: Dict) -> List[str]:
    """Collect all text sources from model data for tag matching."""
    sources: List[str] = []

    file_name = model_data.get("file_name", "")
    if file_name:
        sources.append(file_name)

    base_model = model_data.get("base_model", "")
    if base_model:
        sources.append(base_model)

    civitai = model_data.get("civitai", {})
    if isinstance(civitai, dict):
        version_name = civitai.get("name", "")
        if version_name:
            sources.append(version_name)

    return sources


def extract_auto_tags(model_data: Dict) -> List[str]:
    """Extract auto-detected tags from model metadata.

    Matches predefined patterns against filename, base_model, and
    CivitAI version name. Returns a sorted, deduplicated list of tag labels.

    HIGH/LOW tags are only returned when the base_model indicates a Wan
    family model — no other model architecture uses this distinction.

    Args:
        model_data: Model metadata dict with keys:
            file_name, base_model, civitai (with optional 'name' field).

    Returns:
        Sorted list of unique auto-tag strings (e.g. ["I2V"]).
    """
    sources = _collect_sources(model_data)
    if not sources:
        return []

    base_model = model_data.get("base_model", "")
    is_wan = "wan" in base_model.lower()

    found: Set[str] = set()

    for label, pattern in AUTO_TAG_CATEGORIES.items():
        # HIGH/LOW are Wan-specific — skip for non-Wan to avoid noise
        if label in ("HIGH", "LOW"):
            if not is_wan:
                continue
            # Use case-insensitive character class + case-sensitive boundary,
            # so "HighNoise" (camelCase) matches but "highlight" doesn't.
            # Boundary: not followed by lowercase letter (= word has ended).
            ci = "".join(f"[{c.lower()}{c.upper()}]" for c in label)
            if label == "LOW":
                regex = re.compile(r"(?<![Ff])" + ci + r"(?![a-z])")
            else:
                regex = re.compile(ci + r"(?![a-z])")
        else:
            regex = re.compile(pattern, re.IGNORECASE)
        for source in sources:
            if regex.search(source):
                found.add(label)
                break

    return sorted(found)
