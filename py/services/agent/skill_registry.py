"""Discovery and loading of agent skills.

Skills live in ``py/services/agent/skills/<name>/`` directories.  Each
directory must contain a ``SKILL.md`` file with YAML frontmatter::

    ---
    name: my_skill
    title: "My Skill"
    description: "What this skill does"
    llm_required: true
    ---

    Prompt template with ``{{variable}}`` placeholders.

The registry scans the skills directory on first access and caches results.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .skill_definition import SkillDefinition, SkillPermissions

logger = logging.getLogger(__name__)

# Directory where built-in skills are stored
_SKILLS_DIR = Path(__file__).parent / "skills"


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?\n)---\s*\n?(.*)", re.DOTALL
)


def _parse_skill_file(path: Path) -> tuple[dict, str]:
    """Read a ``SKILL.md`` file and return (frontmatter_dict, body_text).

    Raises ``ValueError`` if the file lacks valid YAML frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"Missing or invalid YAML frontmatter in {path}")
    frontmatter = yaml.safe_load(m.group(1))
    if not isinstance(frontmatter, dict):
        raise ValueError(f"Frontmatter in {path} is not a mapping")
    body = m.group(2).strip()
    return frontmatter, body


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
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                definition = self._load_skill_definition(skill_md)
                if definition is not None:
                    self._skills[definition.name] = definition
                    logger.debug("Loaded skill: %s", definition.name)
            except Exception as exc:
                logger.warning("Failed to load skill from %s: %s", skill_md, exc)

        self._loaded = True
        logger.info("Discovered %d agent skills", len(self._skills))

    def _load_skill_definition(self, path: Path) -> Optional[SkillDefinition]:
        """Parse a ``SKILL.md`` frontmatter into a :class:`SkillDefinition`."""

        try:
            data, _body = _parse_skill_file(path)
        except (ValueError, yaml.YAMLError) as exc:
            logger.warning("Failed to parse SKILL.md %s: %s", path, exc)
            return None

        if "name" not in data:
            logger.warning("SKILL.md missing required 'name' field: %s", path)
            return None

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
        """Load and return the prompt template body from a skill's ``SKILL.md``."""

        skill_dir = self._skills_dir / name
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"SKILL.md not found: {skill_path}")
        try:
            _frontmatter, body = _parse_skill_file(skill_path)
            return body
        except (ValueError, yaml.YAMLError) as exc:
            raise ValueError(f"Failed to parse prompt from {skill_path}: {exc}") from exc
