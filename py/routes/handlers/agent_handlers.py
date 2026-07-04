"""HTTP route handlers for agent skill endpoints.

These handlers expose the :class:`AgentService` via HTTP, allowing the
frontend to list available skills and execute them on selected models.
Progress is reported via WebSocket broadcast.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from aiohttp import web

from ...services.agent import AgentService, AgentProgressReporter
from ...services.llm_service import LLMNotConfiguredError

logger = logging.getLogger(__name__)


class AgentHandler:
    """HTTP handler for agent skill operations."""

    def __init__(self, agent_service: AgentService | None = None) -> None:
        self._agent_service = agent_service

    async def _ensure_service(self) -> AgentService:
        if self._agent_service is None:
            self._agent_service = await AgentService.get_instance()
        return self._agent_service

    # ------------------------------------------------------------------
    # GET /api/lm/agent/skills
    # ------------------------------------------------------------------

    async def get_agent_skills(self, request: web.Request) -> web.Response:
        """Return a list of available agent skills."""

        service = await self._ensure_service()
        skills = await service.list_skills()
        return web.json_response({"skills": skills})

    # ------------------------------------------------------------------
    # POST /api/lm/agent/execute/{skill_name}
    # ------------------------------------------------------------------

    async def execute_agent_skill(self, request: web.Request) -> web.Response:
        """Execute an agent skill on the provided model paths.

        Request body::

            {"model_paths": ["/path/to/model1.safetensors", ...], "options": {}}

        Returns immediately with a task ID.  Execution runs in the
        background; progress and completion are pushed via WebSocket
        events of type ``agent_progress``.
        """

        skill_name = request.match_info.get("skill_name", "")
        if not skill_name:
            return web.json_response(
                {"error": "Skill name is required"}, status_code=400
            )

        try:
            body = await request.json()
        except Exception:
            return web.json_response(
                {"error": "Invalid JSON body"}, status_code=400
            )

        model_paths = body.get("model_paths", [])
        if not model_paths or not isinstance(model_paths, list):
            return web.json_response(
                {"error": "model_paths must be a non-empty array"},
                status_code=400,
            )

        service = await self._ensure_service()

        # Validate LLM configuration early for skills that need it
        # (fail fast rather than after starting background work)
        try:
            from ...services.llm_service import LLMService

            llm = await LLMService.get_instance()
            if not llm.is_configured():
                return web.json_response(
                    {
                        "error": "LLM provider is not configured. "
                        "Enable it in Settings → AI Provider.",
                    },
                    status=400,
                )
        except Exception as exc:
            logger.error("Failed to check LLM configuration: %s", exc)

        # Launch execution in the background
        progress_reporter = AgentProgressReporter()
        logger.info(
            "LLM enrichment '%s' starting for %d model(s) in background task",
            skill_name, len(model_paths),
        )

        async def _run() -> None:
            logger.info("Background task started for enrichment '%s'", skill_name)
            try:
                result = await service.execute_skill(
                    skill_name=skill_name,
                    input_data={"model_paths": model_paths},
                    progress_callback=progress_reporter,
                )
                logger.info(
                    "LLM enrichment '%s' finished: success=%s, summary='%s', errors=%s",
                    skill_name, result.success, result.summary, result.errors,
                )
            except LLMNotConfiguredError as exc:
                logger.warning("LLM enrichment '%s' not configured: %s", skill_name, exc)
                await progress_reporter.on_progress(
                    {
                        "type": "agent_progress",
                        "skill": skill_name,
                        "status": "error",
                        "error": str(exc),
                    }
                )
            except Exception as exc:
                logger.error("LLM enrichment '%s' failed: %s", skill_name, exc, exc_info=True)
                await progress_reporter.on_progress(
                    {
                        "type": "agent_progress",
                        "skill": skill_name,
                        "status": "error",
                        "error": str(exc),
                    }
                )

        # Fire and forget — progress comes via WebSocket
        task = asyncio.create_task(_run())
        logger.info("LLM enrichment '%s' background task created (id=%s)", skill_name, task)

        return web.json_response(
            {
                "status": "started",
                "skill": skill_name,
                "model_count": len(model_paths),
            }
        )

    # ------------------------------------------------------------------
    # POST /api/lm/agent/cancel
    # ------------------------------------------------------------------

    async def cancel_agent_skill(self, request: web.Request) -> web.Response:
        """Cancel a running agent skill.

        NOTE: Cancellation is a stub for now — the AgentService processes
        models sequentially and does not yet support mid-execution
        cancellation.  This endpoint exists for API completeness.
        """

        # TODO: implement cooperative cancellation in AgentService
        return web.json_response(
            {"status": "acknowledged", "note": "Cancellation not yet implemented"},
            status_code=200,
        )
