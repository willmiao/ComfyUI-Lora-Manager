#!/usr/bin/env python3
"""CLI entry point for the HF metadata enrichment validation suite.

Usage::

    # Full run (100 models, serial, ~1-2 h)
    python -m tests.enrich_hf_validation.run_validation \\
        --output /tmp/hf_enrich_validation

    # Quick smoke test with 2 models
    python -m tests.enrich_hf_validation.run_validation --sample 2

    # Resume from a previous partial run
    python -m tests.enrich_hf_validation.run_validation --resume

    # Custom settings file
    python -m tests.enrich_hf_validation.run_validation \\
        --settings /custom/path/settings.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

# Ensure the project root is on sys.path so that ``from py import ...`` works.
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tests.enrich_hf_validation.config import load_settings
from tests.enrich_hf_validation.metadata_constructor import (
    create_all_initial_metadata,
    load_repo_ids,
)
from tests.enrich_hf_validation.enrichment_runner import EnrichmentRunner
from tests.enrich_hf_validation.evaluation_engine import (
    aggregate_scores,
    evaluate_batch,
)
from tests.enrich_hf_validation.report_generator import (
    generate_markdown_report,
    save_json_report,
)

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)

    # Quiet noisy third-party loggers
    for name in ("aiohttp", "asyncio", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optimise HF metadata enrichment via LLM.",
    )
    parser.add_argument(
        "--models",
        default="~/Documents/hf_lora_models.txt",
        help="Path to the HF repo ID list (one per line)",
    )
    parser.add_argument(
        "--settings",
        default="~/.config/ComfyUI-LoRA-Manager/settings.json",
        help="Path to LoRA Manager settings.json",
    )
    parser.add_argument(
        "--output",
        default="/tmp/hf_enrich_validation",
        help="Output directory for reports and intermediate data",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Process only the first N models (for quick smoke tests)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous partial run (uses progress.json)",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip enrichment phase (evaluate existing metadata only)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=240,
        help="Per-model LLM timeout in seconds (default: 240)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------


def _phase_header(label: str) -> None:
    sep = "=" * 60
    print(f"\n{sep}", file=sys.stderr)
    print(f"  PHASE: {label}", file=sys.stderr)
    print(sep, file=sys.stderr)


async def _run_enrichment(
    model_paths: List[str],
    repos: List[str],
    output_dir: str,
    timeout: int,
    verbose: bool,
) -> Dict[str, Any]:
    """Execute the enrichment phase."""
    runner = EnrichmentRunner(
        output_dir=output_dir,
        per_model_timeout=timeout,
    )
    result = await runner.run(model_paths, repos)

    # Print quick summary
    progress = result["progress"]
    total_done = (
        len(progress.get("completed", []))
        + len(progress.get("failed", []))
        + len(progress.get("timed_out", []))
    )
    print(
        f"\n  Enrichment complete: {total_done} processed "
        f"({len(progress.get('completed', []))} ok, "
        f"{len(progress.get('failed', []))} failed, "
        f"{len(progress.get('timed_out', []))} timed out)",
        file=sys.stderr,
    )
    return result


def _collect_enriched_metadata(
    model_paths: List[str],
    repos: List[str],
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Read enriched .metadata.json for each model.

    Uses the same path convention as the rest of the codebase:
    ``os.path.splitext(model_path)[0] + '.metadata.json'``.

    Returns a list of dicts with keys: repo_id, model_path, success,
    errors, metadata.
    """
    enriched: List[Dict[str, Any]] = []
    # Build a lookup from repo_id → enrichment result
    result_lookup: Dict[str, Dict[str, Any]] = {}
    for r in results:
        result_lookup[r["repo_id"]] = r

    for model_path, repo_id in zip(model_paths, repos):
        res = result_lookup.get(repo_id, {})
        metadata_path = f"{os.path.splitext(model_path)[0]}.metadata.json"
        metadata: Dict[str, Any] = {}
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as fh:
                    metadata = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read %s: %s", metadata_path, exc)
        else:
            logger.warning(
                "Metadata file not found for %s (expected: %s)",
                repo_id, metadata_path,
            )

        enriched.append({
            "repo_id": repo_id,
            "model_path": model_path,
            "success": res.get("success", False),
            "errors": res.get("errors", []),
            "metadata": metadata,
        })

    return enriched


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(argv: List[str]) -> int:
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    output_dir = os.path.abspath(os.path.expanduser(args.output))
    os.makedirs(output_dir, exist_ok=True)

    settings = load_settings(args.settings)
    logger.info(
        "LLM config: provider=%s model=%s api_base=%s",
        settings["llm_provider"],
        settings["llm_model"],
        settings["llm_api_base"],
    )

    # ---- Phase 1: Load repo IDs & construct initial metadata ----
    _phase_header("Load repo IDs & construct initial metadata")
    repos = load_repo_ids(args.models, max_models=args.sample if args.sample > 0 else None)
    model_paths = create_all_initial_metadata(
        repos, output_dir, skip_existing=True,
    )
    print(f"  {len(model_paths)} repos ready", file=sys.stderr)

    # ---- Phase 2: Enrichment ----
    enrichment_results: List[Dict[str, Any]] = []
    t_start = time.perf_counter()
    if not args.no_enrich:
        _phase_header("Enrich metadata via LLM")
        enrichment_out = await _run_enrichment(
            model_paths, repos, output_dir, args.timeout, args.verbose,
        )
        enrichment_results = enrichment_out["results"]
    else:
        print("  Enrichment skipped (--no-enrich)", file=sys.stderr)

    t_enrich = time.perf_counter()

    # ---- Phase 3: Evaluation ----
    _phase_header("Evaluate enriched metadata")
    enriched = _collect_enriched_metadata(model_paths, repos, enrichment_results)
    scores = evaluate_batch(enriched)
    agg = aggregate_scores(scores)
    print(
        f"  Mean total score: {agg.get('total_score', {}).get('mean', 'N/A')} / 100",
        file=sys.stderr,
    )
    print(
        f"  Models scored: {agg.get('model_count', 0)}",
        file=sys.stderr,
    )

    # ---- Phase 4: Report generation ----
    _phase_header("Generate reports")
    duration_summary: Dict[str, Any] | None = None
    if enrichment_results:
        durations = [r.get("duration_s", 0) for r in enrichment_results if r.get("duration_s")]
        if durations:
            sorted_d = sorted(durations)
            m = len(sorted_d) // 2
            duration_summary = {
                "total_wall_s": round(t_enrich - t_start, 1),
                "mean_s": round(sum(durations) / len(durations), 1),
                "median_s": round(sorted_d[m] if len(sorted_d) % 2 else (sorted_d[m - 1] + sorted_d[m]) / 2, 1),
                "min_s": round(min(durations), 1),
                "max_s": round(max(durations), 1),
            }

    save_json_report(agg, scores, enrichment_results, output_dir, duration_summary)
    generate_markdown_report(agg, scores, output_dir, duration_summary)

    # ---- Final summary ----
    total_wall = time.perf_counter() - t_start
    print(f"\n  Done in {total_wall:.0f}s ({total_wall / 60:.1f} min)", file=sys.stderr)
    print(f"  Reports: {output_dir}/report.md, {output_dir}/report.json", file=sys.stderr)
    print(file=sys.stderr)

    return 0 if agg.get("success_count", 0) > 0 else 1


def entry_point() -> int:
    return asyncio.run(main(sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(entry_point())
