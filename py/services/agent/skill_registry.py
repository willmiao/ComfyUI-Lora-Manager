"""Discovery and loading of agent skills.

Skills live in ``py/services/agent/skills/<name>/`` directories.  Each
directory must contain:

- ``skill.yaml`` — metadata (name, title, description, schemas, permissions)
- ``prompt.md`` — LLM system prompt template (Jinja2-style ``{{variable}}`` placeholders)
- ``handler.py`` — async ``prepare`` and ``post_process`` functions

The registry scans the skills directory on first access and caches results.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .skill_definition import SkillDefinition, SkillPermissions

logger = logging.getLogger(__name__)

# Directory where built-in skills are stored
_SKILLS_DIR = Path(__file__).parent / "skills"


class SkillRegistry:
    """Discover and load agent skills from the filesystem."""

    _instance: Optional["SkillRegistry"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, skills_dir: Path = _SKILLS_DIR) -> None:
        self._skills_dir = skills_dir
        self._skills: Dict[str, SkillDefinition] = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    async def get_instance(cls) -> "SkillRegistry":
        """Return the lazily-initialised global ``SkillRegistry``."""

        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    registry = cls()
                    registry._discover()
                    cls._instance = registry
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the cached singleton — primarily for tests."""

        cls._instance = None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:
        """Scan the skills directory and load all valid skill definitions."""

        self._skills.clear()
        if not self._skills_dir.is_dir():
            logger.warning("Skills directory does not exist: %s", self._skills_dir)
            self._loaded = True
            return

        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_yaml = entry / "skill.yaml"
            if not skill_yaml.exists():
                continue
            try:
                definition = self._load_skill_yaml(skill_yaml)
                if definition is not None:
                    self._skills[definition.name] = definition
                    logger.debug("Loaded skill: %s", definition.name)
            except Exception as exc:
                logger.warning("Failed to load skill from %s: %s", skill_yaml, exc)

        self._loaded = True
        logger.info("Discovered %d agent skills", len(self._skills))

    def _load_skill_yaml(self, path: Path) -> Optional[SkillDefinition]:
        """Parse a skill.yaml file into a :class:`SkillDefinition`."""

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "name" not in data:
            logger.warning("skill.yaml missing required 'name' field: %s", path)
            return None

        # Parse permissions
        perm_data = data.get("permissions", {})
        permissions = SkillPermissions(
            write_metadata=perm_data.get("write_metadata", True),
            write_previews=perm_data.get("write_previews", True),
            network_domains=tuple(perm_data.get("network_domains", [])),
        )

        return SkillDefinition(
            name=data["name"],
            title=data.get("title", data["name"]),
            description=data.get("description", ""),
            llm_required=data.get("llm_required", False),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            model_type_filter=data.get("model_type_filter"),
            permissions=permissions,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_skills(self) -> List[SkillDefinition]:
        """Return all discovered skill definitions."""

        if not self._loaded:
            self._discover()
        return list(self._skills.values())

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Return the skill definition for ``name``, or ``None`` if not found."""

        if not self._loaded:
            self._discover()
        return self._skills.get(name)

    def load_prompt(self, name: str) -> str:
        """Load and return the prompt template for a skill."""

        skill_dir = self._skills_dir / name
        prompt_path = skill_dir / "prompt.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    def load_handler(self, name: str) -> Dict[str, Callable]:
        """Dynamically import a skill's handler module and return its functions.

        Returns a dict with ``prepare`` and ``post_process`` callables.
        ``prepare`` may be absent (the skill doesn't need pre-LLM data gathering).
        """

        skill_dir = self._skills_dir / name
        handler_path = skill_dir / "handler.py"
        if not handler_path.exists():
            raise FileNotFoundError(f"Handler not found: {handler_path}")

        # Use importlib to load the module by file path
        # Important: use a fully-qualified module name so that absolute imports
        # (e.g. ``from py.utils.metadata_manager import MetadataManager``) resolve correctly.
        module_name = f"py.services.agent.skills.{name}.handler"
        spec = importlib.util.spec_from_file_location(module_name, handler_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load handler module from {handler_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        result: Dict[str, Callable] = {}
        if hasattr(module, "prepare"):
            result["prepare"] = module.prepare
        if hasattr(module, "post_process"):
            result["post_process"] = module.post_process
        else:
            raise AttributeError(
                f"Skill handler {name} is missing required 'post_process' function"
            )
        return result
