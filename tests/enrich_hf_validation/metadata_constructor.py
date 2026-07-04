"""Construct initial ``.metadata.json`` sidecars for HF model repos.

Each HF repo ID gets a minimal metadata file — no real model file is needed.
The enrichment pipeline reads only the sidecar.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List

from .config import CIVITAI_MODEL_TAGS

logger = logging.getLogger(__name__)


def load_repo_ids(path: str, max_models: int | None = None) -> List[str]:
    """Read HF repo IDs from *path* (one per line, ignoring blanks/comments)."""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Models file not found: {path}")

    repos: List[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            repos.append(line)

    if max_models is not None and max_models > 0:
        repos = repos[:max_models]

    logger.info("Loaded %d HF repo IDs from %s", len(repos), path)
    return repos


def sanitize_repo_id(repo_id: str) -> str:
    """Turn ``user/repo-name`` into a safe directory name."""
    return repo_id.replace("/", "__").replace(".", "_")


def build_model_dir(output_dir: str, repo_id: str) -> str:
    """Return the per-model working directory."""
    return os.path.join(output_dir, "models", sanitize_repo_id(repo_id))


def build_model_path(model_dir: str) -> str:
    """Return a synthetic model file path (no real file will exist)."""
    return os.path.join(model_dir, "model.safetensors")


def build_metadata_path(model_path: str) -> str:
    """Return the sidecar path for a model file.

    This MUST match the convention used by ``MetadataManager`` /
    ``apply_metadata_updates``, which derives the sidecar path via
    ``os.path.splitext(model_path)[0] + '.metadata.json'``.
    For a model file ``model.safetensors`` the sidecar is
    ``model.metadata.json`` — *not* ``model.safetensors.metadata.json``.
    """
    return f"{os.path.splitext(model_path)[0]}.metadata.json"


def create_initial_metadata(
    output_dir: str,
    repo_id: str,
) -> str:
    """Write a minimal ``.metadata.json`` for *repo_id*.

    Returns the **model path** (the ``.safetensors`` path whose sidecar was
    written).  The caller passes this path to ``AgentService.execute_skill``.
    """
    model_dir = build_model_dir(output_dir, repo_id)
    os.makedirs(model_dir, exist_ok=True)
    model_path = build_model_path(model_dir)
    metadata_path = build_metadata_path(model_path)

    hf_url = f"https://huggingface.co/{repo_id}"
    file_name = repo_id.split("/")[-1]

    metadata: Dict = {
        "file_name": file_name,
        "model_name": file_name,
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
    repos: List[str],
    output_dir: str,
    *,
    skip_existing: bool = True,
) -> List[str]:
    """Create initial metadata for every repo in *repos*.

    Returns a list of model paths in the same order as *repos*.
    ``skip_existing=True`` skips repos whose metadata already exists,
    allowing safe re-run.
    """
    model_paths: List[str] = []
    for repo_id in repos:
        model_dir = build_model_dir(output_dir, repo_id)
        model_path = build_model_path(model_dir)
        metadata_path = build_metadata_path(model_path)

        if skip_existing and os.path.exists(metadata_path):
            model_paths.append(model_path)
            continue

        model_paths.append(create_initial_metadata(output_dir, repo_id))

    logger.info(
        "Constructed initial metadata for %d/%d repos",
        len(model_paths),
        len(repos),
    )
    return model_paths
