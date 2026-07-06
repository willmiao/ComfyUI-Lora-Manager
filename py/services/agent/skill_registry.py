"""Discovery and loading of prompt-based skills.

Skills live in ``py/services/agent/skills/<name>/`` directories.  Each
directory must contain a ``prompt.md`` file with YAML frontmatter::

    ---
    name: my_skill
    title: "My Skill"
    description: "What this skill does"
    llm_required: true
    ---

    Prompt template with ``{{variable}}`` placeholders.

Legacy ``SKILL.md`` files are also supported for backward compatibility.

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

#: Preferred file names for prompt definition files (tried in order).
#: ``prompt.md`` is the current convention; ``SKILL.md`` is the legacy name
#: kept for backward compatibility.
_PROMPT_FILE_NAMES: tuple[str, ...] = ("prompt.md", "SKILL.md")


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?\n)---\s*\n?(.*)", re.DOTALL
)


def _parse_skill_file(path: Path) -> tuple[dict, str]:
    """Read a prompt definition file (``prompt.md`` or legacy ``SKILL.md``) and
    return (frontmatter_dict, body_text).

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

    @staticmethod
    def _find_prompt_file(skill_dir: Path) -> Path | None:
        """Return the first prompt definition file that exists in *skill_dir*.

        Tries ``_PROMPT_FILE_NAMES`` in order so that new conventions
        (``prompt.md``) take precedence while legacy ``SKILL.md`` files
        still load without changes.
        """
        for name in _PROMPT_FILE_NAMES:
            candidate = skill_dir / name
            if candidate.exists():
                return candidate
        return None

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
            prompt_file = self._find_prompt_file(entry)
            if prompt_file is None:
                continue
            try:
                definition = self._load_skill_definition(prompt_file)
                if definition is not None:
                    self._skills[definition.name] = definition
                    logger.debug("Loaded skill: %s", definition.name)
            except Exception as exc:
                logger.warning("Failed to load skill from %s: %s", prompt_file, exc)

        self._loaded = True
        logger.info("Discovered %d prompt-based skills", len(self._skills))

    def _load_skill_definition(self, path: Path) -> Optional[SkillDefinition]:
        """Parse a prompt definition file's frontmatter into a
        :class:`SkillDefinition`."""

        try:
            data, _body = _parse_skill_file(path)
        except (ValueError, yaml.YAMLError) as exc:
            logger.warning("Failed to parse prompt file %s: %s", path, exc)
            return None

        if "name" not in data:
            logger.warning("Prompt file %s missing required 'name' field", path)
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
        """Load and return the prompt template body for the named skill."""

        skill_dir = self._skills_dir / name
        skill_path = self._find_prompt_file(skill_dir)
        if skill_path is None:
            raise FileNotFoundError(
                f"Prompt file not found for skill '{name}' in {skill_dir} "
                f"(tried {list(_PROMPT_FILE_NAMES)})"
            )
        try:
            _frontmatter, body = _parse_skill_file(skill_path)
            return body
        except (ValueError, yaml.YAMLError) as exc:
            raise ValueError(f"Failed to parse prompt from {skill_path}: {exc}") from exc
