"""LLM-powered metadata enrichment pipeline infrastructure.

This package provides the orchestration layer for LLM-powered features.
Skills define *what* to do (prompt template).  The :class:`AgentService`
handles *how* (LLM calls, context gathering, validation, progress).

NOTE: The current implementation is a code-driven pipeline, not a true
agent loop.  Future agent orchestration (LLM-driven tool selection) will
live alongside this package with its own namespace.
"""

from __future__ import annotations

from .skill_definition import SkillDefinition, SkillPermissions
from .skill_registry import SkillRegistry
from .agent_service import AgentService, AgentProgressReporter, SkillResult
from .post_processor import PostProcessor

__all__ = [
    "AgentProgressReporter",
    "AgentService",
    "PostProcessor",
    "SkillDefinition",
    "SkillPermissions",
    "SkillRegistry",
    "SkillResult",
]
