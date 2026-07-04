"""Execute the ``enrich_hf_metadata`` skill serially over a list of models.

Design decisions (local Ollama, no rate limits):

- Sequential execution: one model at a time.  100 models at ~30-90 s/call
  → roughly 1-2 h total.
- Progress persisted to a JSON checkpoint file so the run can be resumed
  with ``--resume``.
- Per-model timeout guards against a stuck Ollama inference.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SKILL_NAME = "enrich_hf_metadata"

# How long to wait for a single LLM call before marking it timed-out.
_PER_MODEL_TIMEOUT = 240  # seconds

# ---------------------------------------------------------------------------
# Progress checkpoint helpers
# ---------------------------------------------------------------------------

_PROGRESS_FILE = "progress.json"


def _load_progress(output_dir: str) -> Dict[str, Any]:
    path = os.path.join(output_dir, _PROGRESS_FILE)
    if os.path.exists(path):
        with open(path, "r") as fh:
            return json.load(fh)
    return {"completed": [], "failed": [], "timed_out": []}


def _save_progress(output_dir: str, progress: Dict[str, Any]) -> None:
    path = os.path.join(output_dir, _PROGRESS_FILE)
    with open(path, "w") as fh:
        json.dump(progress, fh, indent=2)


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


class EnrichmentRunner:
    """Serial enrichment runner with checkpoint resume."""

    def __init__(
        self,
        output_dir: str,
        *,
        per_model_timeout: int = _PER_MODEL_TIMEOUT,
    ) -> None:
        self._output_dir = output_dir
        self._per_model_timeout = per_model_timeout
        self._agent_service: Optional[Any] = None

    async def _ensure_agent_service(self) -> Any:
        """Lazy-init AgentService (expensive — needs LLMService init)."""
        if self._agent_service is not None:
            return self._agent_service
        from py.services.agent.agent_service import AgentService

        self._agent_service = await AgentService.get_instance()
        return self._agent_service

    async def run(
        self,
        model_paths: List[str],
        repos: List[str],
    ) -> Dict[str, Any]:
        """Run enrichment over *model_paths* (one-by-one).

        Args:
            model_paths: model paths in the same order as *repos*.
            repos: HF repo IDs (for display / checkpoint labelling).

        Returns:
            A dict with keys ``results``, ``progress``, ``durations``.
        """
        assert len(model_paths) == len(repos)

        progress = _load_progress(self._output_dir)
        completed_set = set(progress["completed"])
        failed_set = set(progress["failed"])
        timed_out_set = set(progress.get("timed_out", []))

        agent = await self._ensure_agent_service()
        results: List[Dict[str, Any]] = []
        durations: Dict[str, float] = {}

        total = len(model_paths)
        processed_before = len(completed_set | failed_set | timed_out_set)

        logger.info(
            "Enrichment runner: %d models total, %d already processed",
            total,
            processed_before,
        )

        for idx, (model_path, repo_id) in enumerate(zip(model_paths, repos)):
            if repo_id in completed_set:
                logger.info("[%d/%d] SKIP (already done): %s", idx + 1, total, repo_id)
                continue
            if repo_id in failed_set or repo_id in timed_out_set:
                logger.info(
                    "[%d/%d] SKIP (previously failed/timeout): %s",
                    idx + 1, total, repo_id,
                )
                continue

            logger.info(
                "[%d/%d] Enriching %s ...", idx + 1, total, repo_id,
            )
            t0 = time.perf_counter()

            try:
                result = await asyncio.wait_for(
                    agent.execute_skill(
                        skill_name=_SKILL_NAME,
                        input_data={"model_paths": [model_path]},
                        progress_callback=None,
                    ),
                    timeout=self._per_model_timeout,
                )

                elapsed = time.perf_counter() - t0
                durations[repo_id] = round(elapsed, 2)

                if result.success:
                    completed_set.add(repo_id)
                    progress["completed"].append(repo_id)
                    logger.info(
                        "  ✓ %s  (%.1f s) — %s",
                        repo_id, elapsed, result.summary,
                    )
                else:
                    failed_set.add(repo_id)
                    progress["failed"].append(repo_id)
                    logger.warning(
                        "  ✗ %s  (%.1f s) — %s",
                        repo_id, elapsed,
                        "; ".join(result.errors) if result.errors else result.summary,
                    )

                results.append({
                    "repo_id": repo_id,
                    "model_path": model_path,
                    "success": result.success,
                    "updated_fields": result.updated_models,
                    "errors": result.errors,
                    "summary": result.summary,
                    "duration_s": round(elapsed, 2),
                })

            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - t0
                durations[repo_id] = round(elapsed, 2)
                timed_out_set.add(repo_id)
                progress.setdefault("timed_out", []).append(repo_id)
                logger.warning(
                    "  ⏱ TIMEOUT %s  (%.1f s, limit=%ds)",
                    repo_id, elapsed, self._per_model_timeout,
                )
                results.append({
                    "repo_id": repo_id,
                    "model_path": model_path,
                    "success": False,
                    "errors": [f"Timeout after {self._per_model_timeout}s"],
                    "summary": "LLM call timed out",
                    "duration_s": round(elapsed, 2),
                })

            except Exception as exc:
                elapsed = time.perf_counter() - t0
                durations[repo_id] = round(elapsed, 2)
                failed_set.add(repo_id)
                progress["failed"].append(repo_id)
                logger.error(
                    "  ✗ %s  (%.1f s) — %s",
                    repo_id, elapsed, exc,
                )
                results.append({
                    "repo_id": repo_id,
                    "model_path": model_path,
                    "success": False,
                    "errors": [str(exc)],
                    "summary": f"Exception: {exc}",
                    "duration_s": round(elapsed, 2),
                })

            # Checkpoint after each model
            _save_progress(self._output_dir, progress)

        return {
            "results": results,
            "progress": progress,
            "durations": durations,
        }
