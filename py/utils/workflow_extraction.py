"""Extraction of the ComfyUI workflow document from a library artifact.

The workflow library keeps the original uploaded file byte-identical — its
SHA256 is the identity CivitAI hashed (by-hash lookup and version tracking
depend on it). Consumers (send-to-ComfyUI, graph analysis) work on the
extracted workflow document instead:

- ``.json`` artifacts ARE the document; they are validated and read in place.
- ``.zip`` / ``.png`` / ``.webp`` containers get the document materialized
  once into an LM-owned derived sidecar ``<name>.workflow.json`` inside the
  artifact's sidecar directory. Scanners exclude the suffix from the library
  walk; lifecycle operations (move/rename/delete) carry it like any other
  sidecar.
"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from typing import Any, Dict, List, Optional

from .sidecar_paths import get_sidecar_dir
from .workflow_analysis import (
    MAX_WORKFLOW_JSON_BYTES,
    load_workflow_file,
    parse_workflow_text,
)

logger = logging.getLogger(__name__)

WORKFLOW_DOCUMENT_SUFFIX = ".workflow.json"

# Image containers whose metadata chunks can embed a ComfyUI workflow.
IMAGE_CONTAINER_EXTENSIONS = frozenset({".png", ".webp"})

# Every file type the workflow library accepts.
WORKFLOW_ARTIFACT_EXTENSIONS = frozenset({".json", ".zip"} | IMAGE_CONTAINER_EXTENSIONS)

# Bounds for zip exploration: workflow archives are user uploads with no
# structural contract, so candidate discovery is capped rather than exhaustive.
_MAX_ZIP_JSON_CANDIDATES = 64


def get_workflow_document_path(artifact_path: str) -> str:
    """Return the path of the extracted workflow document for an artifact.

    ``.json`` artifacts are their own document; containers map to the
    derived ``<name>.workflow.json`` in the artifact's sidecar directory
    (alongside the artifact or in the centralized mirror).
    """

    if os.path.splitext(artifact_path)[1].lower() == ".json":
        return artifact_path
    base_name = os.path.splitext(os.path.basename(artifact_path))[0]
    return os.path.join(
        get_sidecar_dir(artifact_path), base_name + WORKFLOW_DOCUMENT_SUFFIX
    )


def _zip_json_candidates(archive: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    """Return the archive's plausible workflow documents, best first."""

    candidates: List[zipfile.ZipInfo] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        parts = info.filename.replace("\\", "/").split("/")
        # Skip macOS resource forks and hidden files/directories.
        if any(part == "__MACOSX" or part.startswith(".") for part in parts):
            continue
        if not parts[-1].lower().endswith(".json"):
            continue
        if info.file_size > MAX_WORKFLOW_JSON_BYTES:
            continue
        candidates.append(info)
        if len(candidates) >= _MAX_ZIP_JSON_CANDIDATES:
            break
    # Prefer shallow, small documents: the workflow is typically the
    # archive's headline content, not a bundled config deep in a subfolder.
    candidates.sort(key=lambda info: (len(info.filename.split("/")), info.file_size))
    return candidates


def _extract_from_zip(archive_path: str) -> Optional[Dict[str, Any]]:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in _zip_json_candidates(archive):
                try:
                    with archive.open(info) as handle:
                        raw = handle.read(MAX_WORKFLOW_JSON_BYTES + 1)
                    text = raw.decode("utf-8")
                except (OSError, UnicodeDecodeError, zipfile.BadZipFile):
                    continue
                document = parse_workflow_text(text)
                if document is not None:
                    return document
    except (OSError, zipfile.BadZipFile) as exc:
        logger.debug("Workflow archive unreadable: %s (%s)", archive_path, exc)
    return None


def _extract_from_image(image_path: str) -> Optional[Dict[str, Any]]:
    # Local import: PIL/piexif are heavy and only needed for image artifacts.
    from .exif_utils import ExifUtils

    try:
        metadata = ExifUtils.load_structured_metadata(image_path)
    except Exception as exc:
        logger.debug("Workflow image metadata unreadable: %s (%s)", image_path, exc)
        return None
    # The UI-format document ("workflow") is what ComfyUI's loadGraphData
    # consumes; fall back to the API-format "prompt" payload.
    for key in ("workflow", "prompt"):
        text = metadata.get(key)
        if not text:
            continue
        document = parse_workflow_text(text)
        if document is not None:
            return document
    return None


def extract_workflow_document(artifact_path: str) -> Optional[Dict[str, Any]]:
    """Extract the ComfyUI workflow document from an artifact.

    Returns the parsed document when the artifact carries a recognizable
    workflow, ``None`` otherwise (unreadable file, unknown extension, no
    workflow inside). Never raises.
    """

    extension = os.path.splitext(artifact_path)[1].lower()
    try:
        if extension == ".json":
            return load_workflow_file(artifact_path)
        if extension == ".zip":
            return _extract_from_zip(artifact_path)
        if extension in IMAGE_CONTAINER_EXTENSIONS:
            return _extract_from_image(artifact_path)
    except Exception as exc:  # defensive: extraction must never break a scan
        logger.debug("Workflow extraction failed for %s: %s", artifact_path, exc)
    return None


def materialize_workflow_document(
    artifact_path: str, *, read_path: Optional[str] = None
) -> Optional[str]:
    """Ensure the extracted workflow document exists on disk.

    Returns the document path, or ``None`` when the artifact carries no
    recognizable workflow. ``.json`` artifacts are their own document (the
    path is returned after validation; nothing is written). Containers get
    the document written to the derived sidecar path; an up-to-date derived
    file is reused without re-extracting.

    ``read_path`` overrides the path the artifact bytes are read from (the
    scanner hashes/extracts via the real path while sidecar locations derive
    from the business path).
    """

    read_path = read_path or artifact_path

    if os.path.splitext(artifact_path)[1].lower() == ".json":
        return artifact_path if load_workflow_file(read_path) is not None else None

    document_path = get_workflow_document_path(artifact_path)
    try:
        if os.path.exists(document_path) and os.path.getmtime(
            document_path
        ) >= os.path.getmtime(read_path):
            return document_path
    except OSError:
        pass

    document = extract_workflow_document(read_path)
    if document is None:
        return None

    try:
        os.makedirs(os.path.dirname(document_path), exist_ok=True)
        with open(document_path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False)
    except OSError as exc:
        logger.warning(
            "Failed to write workflow document %s: %s", document_path, exc
        )
        return None
    return document_path


def load_artifact_workflow_document(artifact_path: str) -> Optional[Dict[str, Any]]:
    """Load the workflow document for a library artifact.

    Reads the derived sidecar for containers (materializing it on demand
    when missing or stale) and the artifact itself for bare JSON.
    """

    document_path = materialize_workflow_document(artifact_path)
    if document_path is None:
        return None
    return load_workflow_file(document_path)
