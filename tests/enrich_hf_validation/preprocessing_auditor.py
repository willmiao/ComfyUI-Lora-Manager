"""Preprocessing audit for the HF metadata enrichment validation pipeline.

Phase 1.5 — runs between Phase 1 (metadata creation) and Phase 2 (enrichment).

Audits the README preprocessing pipeline (section extraction + cleaning)
for each repo in the dataset, capturing intermediate outputs so we can
distinguish between:

    (A) Preprocessing failed → LLM never saw the right content
    (B) Preprocessing succeeded → LLM/prompt needs improvement

This prevents wasted effort optimizing prompts when the actual problem is
that ``extract_relevant_section`` or ``clean_readme_for_llm`` removed or
misaligned the content the LLM needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------


@dataclass
class AuditRecord:
    """Preprocessing audit for a single repo entry."""

    # Identity
    repo_id: str
    safetensors_name: str
    basename: str  # filename without .safetensors

    # Raw README stats
    raw_readme_length: int
    raw_readme_line_count: int
    has_yaml_frontmatter: bool
    yaml_has_base_model: bool
    yaml_has_tags: bool

    # Section extraction
    section_extraction_activated: bool  # output < 95% of input length
    section_length: int
    section_line_count: int
    basename_in_section: bool  # basename appears in extracted section text

    # Cleaning
    cleaned_length: int
    cleaned_line_count: int
    compression_pct: float  # (1 - cleaned/raw) * 100

    # Widget section (stripped by _strip_widget_section)
    widget_section_found: bool
    widget_section_length: int

    # Flags (list of anomaly descriptions)
    flags: List[str] = field(default_factory=list)

    # Local file path to the saved raw README (for cross-reference)
    readme_file: str = ""

    # Staged intermediate output for report detail
    raw_readme_preview: str = ""  # first 200 chars
    section_preview: str = ""  # first 300 chars


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HF_RAW_URL = "https://huggingface.co/{repo_id}/raw/main/README.md"

# Thresholds for flagging
_SECTION_ACTIVATION_RATIO = 0.95
_MIN_CLEANED_LENGTH = 100
_MAX_COMPRESSION_PCT = 99.0
_MIN_SECTION_LINES = 3


# ---------------------------------------------------------------------------
# Module loader — bypasses parent-package __init__ that imports ComfyUI
# ---------------------------------------------------------------------------

_readme_processor_module = None


def _load_readme_processor():
    """Import ``readme_processor`` without triggering ``folder_paths`` import.

    The normal import path (``py.services.agent.skills.enrich_hf_metadata.
    readme_processor``) triggers ``py.services.agent.__init__`` which
    imports ``agent_service.py`` → ``py/config.py`` → ComfyUI's
    ``folder_paths``, which is not available in standalone mode.
    """
    global _readme_processor_module
    if _readme_processor_module is not None:
        return _readme_processor_module

    import importlib.util

    _RP_PATH = os.path.join(
        os.path.dirname(__file__),  # tests/enrich_hf_validation/
        "..", "..",
        "py", "services", "agent", "skills", "enrich_hf_metadata",
        "readme_processor.py",
    )
    rp_path = os.path.normpath(_RP_PATH)
    if not os.path.exists(rp_path):
        logger.error("readme_processor.py not found at %s", rp_path)
        return None

    spec = importlib.util.spec_from_file_location(
        "readme_processor", rp_path,
    )
    if spec is None or spec.loader is None:
        logger.error("Could not create spec for readme_processor.py")
        return None

    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        logger.error("Failed to load readme_processor.py: %s", exc)
        return None

    _readme_processor_module = mod
    return mod


# ---------------------------------------------------------------------------
# HF README fetcher
# ---------------------------------------------------------------------------


async def _fetch_readme(repo_id: str, session: aiohttp.ClientSession) -> str:
    """Fetch the raw README.md from HuggingFace."""
    url = _HF_RAW_URL.format(repo_id=repo_id)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.text()
            logger.warning("Failed to fetch README for %s: HTTP %d", repo_id, resp.status)
            return ""
    except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
        logger.warning("Failed to fetch README for %s: %s", repo_id, exc)
        return ""


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def _has_yaml_frontmatter(text: str) -> bool:
    return bool(text.strip().startswith("---"))


def _extract_yaml_field(text: str, field: str) -> bool:
    """Check if the given YAML field exists in the frontmatter."""
    lines = text.split("\n")
    if not lines or not lines[0].strip().startswith("---"):
        return False
    end = 1
    while end < len(lines):
        if lines[end].strip().startswith("---"):
            break
        end += 1
    if end >= len(lines):
        return False
    frontmatter = "\n".join(lines[1:end])
    pattern = rf"^{field}:"
    return bool(re.search(pattern, frontmatter, re.MULTILINE))


def _find_widget_section_length(text: str) -> int:
    """Find the ``widget:`` YAML section and return its length (0 if none)."""
    if not _has_yaml_frontmatter(text):
        return 0
    frontmatter_end = text.find("---", 3)
    if frontmatter_end == -1:
        return 0
    frontmatter = text[3:frontmatter_end]

    # Match widget: through to the next top-level key or frontmatter end
    m = re.search(r"\nwidget:", frontmatter)
    if not m:
        return 0
    # Length from widget: to end of frontmatter (the next \n\w+: or \n---)
    return len(frontmatter[m.start():])


# ---------------------------------------------------------------------------
# Core auditor
# ---------------------------------------------------------------------------


async def run_audit(
    entries: List[Tuple[str, str]],
    *,
    concurrency: int = 10,
    readmes_dir: str | None = None,
) -> Tuple[List[AuditRecord], Dict[str, Any]]:
    """Run the preprocessing audit over all repo entries.

    Args:
        entries: List of ``(repo_id, safetensors_name)``.
        concurrency: Max parallel fetches to HuggingFace.
        readmes_dir: If set, saves each fetched README as
            ``{sanitized_repo_id}.md`` in this directory for offline
            cross-reference against audit results.

    Returns:
        Tuple of ``(records, summary)`` where *summary* is a dict with
        aggregate statistics.
    """
    semaphore = asyncio.Semaphore(concurrency)
    records: List[AuditRecord] = []
    flag_counter: Dict[str, int] = {}

    if readmes_dir:
        os.makedirs(readmes_dir, exist_ok=True)

    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_audit_one(entry, session, semaphore, readmes_dir=readmes_dir) for entry in entries]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        for entry, result in zip(entries, gathered):
            if isinstance(result, Exception):
                logger.error("Audit failed for %s: %s", entry[0], result)
                records.append(
                    AuditRecord(
                        repo_id=entry[0],
                        safetensors_name=entry[1],
                        basename=os.path.splitext(entry[1])[0],
                        raw_readme_length=0,
                        raw_readme_line_count=0,
                        has_yaml_frontmatter=False,
                        yaml_has_base_model=False,
                        yaml_has_tags=False,
                        section_extraction_activated=False,
                        section_length=0,
                        section_line_count=0,
                        basename_in_section=False,
                        cleaned_length=0,
                        cleaned_line_count=0,
                        compression_pct=0.0,
                        widget_section_found=False,
                        widget_section_length=0,
                        readme_file="",
                        flags=[f"Audit exception: {result}"],
                    )
                )
                continue

            # The continue above ensures result is AuditRecord here
            assert isinstance(result, AuditRecord)
            records.append(result)
            for flag in result.flags:
                flag_counter[flag] = flag_counter.get(flag, 0) + 1

    summary = _build_summary(records, flag_counter)
    return records, summary


def _sanitize_repo_id(repo_id: str) -> str:
    """Turn ``user/repo-name`` into a safe filename."""
    return repo_id.replace("/", "__").replace(".", "_")


async def _audit_one(
    entry: Tuple[str, str],
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    *,
    readmes_dir: str | None = None,
) -> AuditRecord:
    """Audit a single repo entry."""
    repo_id, safetensors_name = entry
    basename = os.path.splitext(safetensors_name)[0]

    async with semaphore:
        # Import production preprocessing functions.
        # Use importlib to bypass py.services.agent.__init__ which triggers
        # ComfyUI's folder_paths module (not available in standalone mode).
        _rp = _load_readme_processor()
        if _rp is None:
            return AuditRecord(
                repo_id=repo_id,
                safetensors_name=safetensors_name,
                basename=basename,
                raw_readme_length=0, raw_readme_line_count=0,
                has_yaml_frontmatter=False, yaml_has_base_model=False, yaml_has_tags=False,
                readme_file="",
                section_extraction_activated=False, section_length=0, section_line_count=0,
                basename_in_section=False, cleaned_length=0, cleaned_line_count=0,
                compression_pct=0.0, widget_section_found=False, widget_section_length=0,
                flags=["IMPORT_FAILED"],
            )
        clean_readme_for_llm = _rp.clean_readme_for_llm
        extract_relevant_section = _rp.extract_relevant_section

        # Step 1: Fetch the raw README
        raw_text = await _fetch_readme(repo_id, session)
        if not raw_text:
            return AuditRecord(
                repo_id=repo_id,
                safetensors_name=safetensors_name,
                basename=basename,
                raw_readme_length=0,
                raw_readme_line_count=0,
                has_yaml_frontmatter=False,
                yaml_has_base_model=False,
                yaml_has_tags=False,
                section_extraction_activated=False,
                section_length=0,
                section_line_count=0,
                basename_in_section=False,
                readme_file="",
                cleaned_length=0,
                cleaned_line_count=0,
                compression_pct=0.0,
                widget_section_found=False,
                widget_section_length=0,
                flags=["README_FETCH_FAILED"],
            )

        # Save the raw README to disk for offline cross-reference
        readme_path = ""
        if readmes_dir:
            safe_name = _sanitize_repo_id(repo_id)
            readme_path = os.path.join(readmes_dir, f"{safe_name}.md")
            try:
                with open(readme_path, "w", encoding="utf-8") as fh:
                    fh.write(raw_text)
            except OSError as exc:
                logger.warning("Failed to save README for %s: %s", repo_id, exc)
                readme_path = ""

        raw_lines = raw_text.split("\n")
        raw_len = len(raw_text)
        raw_line_count = len(raw_lines)

        # Step 2: Analyze raw README
        yaml_fm = _has_yaml_frontmatter(raw_text)
        yaml_has_bm = _extract_yaml_field(raw_text, "base_model") if yaml_fm else False
        yaml_has_tg = _extract_yaml_field(raw_text, "tags") if yaml_fm else False
        widget_len = _find_widget_section_length(raw_text)

        # Step 3: Section extraction
        section = extract_relevant_section(raw_text, basename)
        section_len = len(section)
        section_line_count = len(section.split("\n"))
        section_activated = section_len < raw_len * _SECTION_ACTIVATION_RATIO
        basename_in_sec = basename.lower() in section.lower()

        # Step 4: Cleaning for LLM
        cleaned = clean_readme_for_llm(section)
        cleaned_len = len(cleaned)
        cleaned_line_count = len(cleaned.split("\n"))
        compression_pct = round((1 - cleaned_len / raw_len) * 100, 1) if raw_len else 0.0

        # Step 5: Flag anomalies
        flags: List[str] = []
        if not raw_text.strip():
            flags.append("README_EMPTY")
        if not yaml_fm:
            flags.append("NO_YAML_FRONTMATTER")
        if not section_activated:
            # Check if basename is extremely short/generic (likely synthetic)
            if len(basename) <= 5:
                flags.append("BASENAME_TOO_SHORT_SECTION_NOT_EXPECTED")
            else:
                flags.append("SECTION_EXTRACTION_NOT_ACTIVATED")
        elif not basename_in_sec:
            flags.append("BASENAME_NOT_IN_EXTRACTED_SECTION")
        if widget_len == 0:
            # Not necessarily a problem — many repos lack a widget section
            pass
        if cleaned_len < _MIN_CLEANED_LENGTH:
            flags.append("CLEANED_README_TOO_SHORT")
        if compression_pct > _MAX_COMPRESSION_PCT:
            flags.append("EXTREME_COMPRESSION")
        if section_activated and section_line_count < _MIN_SECTION_LINES:
            flags.append("SECTION_TOO_SMALL")

        return AuditRecord(
            repo_id=repo_id,
            safetensors_name=safetensors_name,
            basename=basename,
            raw_readme_length=raw_len,
            raw_readme_line_count=raw_line_count,
            has_yaml_frontmatter=yaml_fm,
            yaml_has_base_model=yaml_has_bm,
            yaml_has_tags=yaml_has_tg,
            section_extraction_activated=section_activated,
            section_length=section_len,
            section_line_count=section_line_count,
            basename_in_section=basename_in_sec,
            cleaned_length=cleaned_len,
            cleaned_line_count=cleaned_line_count,
            compression_pct=compression_pct,
            widget_section_found=widget_len > 0,
            widget_section_length=widget_len,
            readme_file=readme_path,
            flags=flags,
            raw_readme_preview=raw_text[:200],
            section_preview=section[:300],
        )


def _build_summary(
    records: List[AuditRecord],
    flag_counter: Dict[str, int],
) -> Dict[str, Any]:
    """Aggregate audit statistics."""
    n = len(records)
    if n == 0:
        return {"error": "no records", "model_count": 0}

    activated = sum(1 for r in records if r.section_extraction_activated)
    basename_hit = sum(1 for r in records if r.basename_in_section)
    with_yaml = sum(1 for r in records if r.has_yaml_frontmatter)
    with_widget = sum(1 for r in records if r.widget_section_found)
    fetch_failed = sum(1 for r in records if "README_FETCH_FAILED" in r.flags)

    avg_compression = round(
        sum(r.compression_pct for r in records if r.raw_readme_length > 0) / max(n - fetch_failed, 1),
        1,
    )
    avg_cleaned = round(
        sum(r.cleaned_length for r in records if r.raw_readme_length > 0) / max(n - fetch_failed, 1),
    )

    top_flags = sorted(flag_counter.items(), key=lambda x: -x[1])[:10]

    return {
        "model_count": n,
        "fetch_failed_count": fetch_failed,
        "section_extraction_activated": activated,
        "section_extraction_pct": round(activated / max(n - fetch_failed, 1) * 100, 1),
        "basename_in_section": basename_hit,
        "basename_in_section_pct": round(basename_hit / max(n - fetch_failed, 1) * 100, 1),
        "with_yaml_frontmatter": with_yaml,
        "with_yaml_frontmatter_pct": round(with_yaml / max(n - fetch_failed, 1) * 100, 1),
        "with_widget_section": with_widget,
        "avg_compression_pct": avg_compression,
        "avg_cleaned_length": avg_cleaned,
        "top_flags": top_flags,
    }


def audit_records_to_serializable(records: List[AuditRecord]) -> List[Dict[str, Any]]:
    """Convert AuditRecord dataclasses to plain dicts for JSON serialization."""
    return [asdict(r) for r in records]
