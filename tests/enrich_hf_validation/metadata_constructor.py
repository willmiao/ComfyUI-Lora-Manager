"""Construct initial ``.metadata.json`` sidecars for HF model repos.

Each HF repo + safetensors pair gets a minimal metadata file — no real model
file is needed.  The enrichment pipeline reads only the sidecar.

Data format (one line per entry)::

    repo_id, model_name.safetensors
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Tuple

from .config import CIVITAI_MODEL_TAGS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

# A validated entry parsed from the models file:
#   (repo_id, safetensors_name)
RepoEntry = Tuple[str, str]


def load_repo_ids(path: str, max_models: int | None = None) -> List[RepoEntry]:
    """Read ``repo_id, safetensors_name`` pairs from *path*.

    Format (one per line, blanks and ``#`` comments ignored)::

        user/repo-name, lora_zimage_turbo_myjs_alpha01.safetensors

    Returns a list of ``(repo_id, safetensors_name)`` tuples.
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Models file not found: {path}")

    entries: List[RepoEntry] = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # Split on the first comma
            if "," not in line:
                logger.warning("Skipping malformed line (no comma): %s", raw_line.rstrip())
                continue

            repo_id, safetensors_name = [part.strip() for part in line.split(",", 1)]
            if not repo_id or not safetensors_name:
                logger.warning("Skipping malformed line (empty fields): %s", raw_line.rstrip())
                continue
            if not safetensors_name.lower().endswith(".safetensors"):
                logger.warning(
                    "Skipping line — safetensors_name doesn't end with .safetensors: %s",
                    raw_line.rstrip(),
                )
                continue

            entries.append((repo_id, safetensors_name))

    if max_models is not None and max_models > 0:
        entries = entries[:max_models]

    logger.info("Loaded %d HF repo entries from %s", len(entries), path)
    return entries


def sanitize_repo_id(repo_id: str) -> str:
    """Turn ``user/repo-name`` into a safe directory name."""
    return repo_id.replace("/", "__").replace(".", "_")


def build_model_dir(output_dir: str, repo_id: str) -> str:
    """Return the per-model working directory."""
    return os.path.join(output_dir, "models", sanitize_repo_id(repo_id))


def build_model_path(model_dir: str, safetensors_name: str) -> str:
    """Return the model file path using the real safetensors filename."""
    return os.path.join(model_dir, safetensors_name)


def build_metadata_path(model_path: str) -> str:
    """Return the sidecar path for a model file.

    This MUST match the convention used by ``MetadataManager`` /
    ``apply_metadata_updates``, which derives the sidecar path via
    ``os.path.splitext(model_path)[0] + '.metadata.json'``.
    For a model file ``lora_x.safetensors`` the sidecar is
    ``lora_x.metadata.json`` — *not* ``lora_x.safetensors.metadata.json``.
    """
    return f"{os.path.splitext(model_path)[0]}.metadata.json"


def create_initial_metadata(
    output_dir: str,
    repo_id: str,
    safetensors_name: str,
) -> str:
    """Write a minimal ``.metadata.json`` for *repo_id* + *safetensors_name*.

    Args:
        output_dir: Root output directory.
        repo_id: HuggingFace repo identifier (``user/repo``).
        safetensors_name: The specific model file name (e.g.
            ``lora_zimage_turbo_myjs_alpha01.safetensors``).

    Returns the **model path** (the ``.safetensors`` path whose sidecar was
    written).  The caller passes this path to ``AgentService.execute_skill``.
    The basename (filename without extension) will match the real model file,
    so ``extract_relevant_section`` can reliably match against the README.
    """
    model_dir = build_model_dir(output_dir, repo_id)
    os.makedirs(model_dir, exist_ok=True)
    model_path = build_model_path(model_dir, safetensors_name)
    metadata_path = build_metadata_path(model_path)

    hf_url = f"https://huggingface.co/{repo_id}"
    file_name = safetensors_name

    metadata: Dict[str, Any] = {
        "file_name": file_name,
        "model_name": safetensors_name,
        "file_path": model_path.replace(os.sep, "/"),
        "size": 0,
        "modified": 0,
        "sha256": "",
        "base_model": "Unknown",
        "preview_url": "",
        "preview_nsfw_level": 0,
        "notes": "",
        "from_civitai": False,
        "civitai": {},
        "tags": [],
        "modelDescription": "",
        "civitai_deleted": False,
        "favorite": False,
        "exclude": False,
        "db_checked": False,
        "skip_metadata_refresh": False,
        "metadata_source": "",
        "last_checked_at": 0,
        "hash_status": "completed",
        "trainedWords": [],
        "hf_url": hf_url,
        "usage_tips": "{}",
    }

    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, ensure_ascii=False)

    logger.debug("Created initial metadata for %s -> %s", repo_id, metadata_path)
    return model_path


def create_all_initial_metadata(
    entries: List[RepoEntry],
    output_dir: str,
    *,
    skip_existing: bool = True,
) -> Tuple[List[str], List[str]]:
    """Create initial metadata for every repo entry.

    Args:
        entries: List of ``(repo_id, safetensors_name)`` tuples.
        output_dir: Root output directory.
        skip_existing: If True, skip repos whose metadata already exists.

    Returns:
        A tuple ``(model_paths, repo_ids)`` — two parallel lists in the same
        order as *entries*.  This keeps downstream code (enrichment runner,
        evaluation engine) unchanged.
    """
    model_paths: List[str] = []
    repo_ids: List[str] = []
    for repo_id, safetensors_name in entries:
        model_dir = build_model_dir(output_dir, repo_id)
        model_path = build_model_path(model_dir, safetensors_name)
        metadata_path = build_metadata_path(model_path)

        if skip_existing and os.path.exists(metadata_path):
            model_paths.append(model_path)
            repo_ids.append(repo_id)
            continue

        model_paths.append(create_initial_metadata(output_dir, repo_id, safetensors_name))
        repo_ids.append(repo_id)

    logger.info(
        "Constructed initial metadata for %d/%d repos",
        len(model_paths),
        len(entries),
    )
    return model_paths, repo_ids
