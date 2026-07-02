"""Skill definition data structures.

Each skill is described by a :class:`SkillDefinition` that declares its
input/output schemas, whether it needs an LLM call, and what permissions
its post-processor has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SkillPermissions:
    """Declarative permission scope for a skill's post-processor.

    These are auditable constraints — the :class:`AgentService` checks them
    before invoking the handler.  They are defense-in-depth, not a sandbox.
    """

    write_metadata: bool = True
    write_previews: bool = True
    network_domains: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillDefinition:
    """Immutable description of an agent skill."""

    name: str
    title: str
    description: str
    llm_required: bool
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    model_type_filter: Optional[List[str]] = None
    permissions: SkillPermissions = field(default_factory=SkillPermissions)

    def applies_to_model_type(self, model_type: str) -> bool:
        """Return ``True`` if this skill can run on the given model type."""

        if self.model_type_filter is None:
            return True
        return model_type in self.model_type_filter
