"""Agent-powered skill system for LoRA Manager.

This package provides the orchestration layer for LLM/agent-powered features.
Skills define *what* to do (prompt template).  The :class:`AgentService`
handles *how* (LLM calls, context gathering, validation, progress).
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
