"""Extraction of the ComfyUI workflow document from a library artifact.

The workflow library keeps the original uploaded file byte-identical — its
SHA256 is the identity CivitAI hashed (by-hash lookup and version tracking
depend on it). Consumers (send-to-ComfyUI, graph analysis) work on the
extracted workflow document instead:

- ``.json`` artifacts ARE the document; they are validated and read in place.
- ``.png`` / ``.webp`` containers get the document materialized once into an
  LM-owned derived ``.workflow.json`` sidecar inside the artifact's sidecar
  directory. A ``.zip`` may carry the document as a JSON member, or bundle an
  image whose embedded metadata contains it (a common CivitAI Workflow
  archive shape). Scanners exclude the suffix from the library walk;
  lifecycle operations (move/rename/delete) carry it like any other sidecar.
"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from typing import Any, Dict, List, Optional

from .sidecar_paths import get_sidecar_base_name, get_sidecar_dir
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
# Archives may bundle the workflow only as an image's embedded metadata.
# Decoding images is far more expensive than parsing JSON, so the fallback is
# capped tightly and prefers the full-size generation screenshot over
# thumbnails (site-generated thumbnails are re-encoded and metadata-free).
_MAX_ZIP_IMAGE_CANDIDATES = 16
_MAX_ZIP_IMAGE_BYTES = 32 * 1024 * 1024


def get_workflow_document_path(artifact_path: str) -> str:
    """Return the path of the extracted workflow document for an artifact.

    ``.json`` artifacts are their own document; containers map to a derived
    ``.workflow.json`` sidecar in the artifact's sidecar directory (alongside
    the artifact or in the centralized mirror). Workflow-library containers
    include their original extension in the sidecar name to keep same-stem
    artifacts independent.
    """

    if os.path.splitext(artifact_path)[1].lower() == ".json":
        return artifact_path
    base_name = get_sidecar_base_name(artifact_path)
    return os.path.join(
        get_sidecar_dir(artifact_path), base_name + WORKFLOW_DOCUMENT_SUFFIX
    )


def _zip_candidates(archive: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    """Return the archive's plausible workflow documents, best first.

    JSON members come first: parsing them is cheap and a single-workflow
    Config archive is the common shape. Image members follow as the fallback
    for archives that only bundle a screenshot carrying the embedded ComfyUI
    metadata.
    """

    json_candidates: List[zipfile.ZipInfo] = []
    image_candidates: List[zipfile.ZipInfo] = []

    for info in archive.infolist():
        if info.is_dir():
            continue
        parts = info.filename.replace("\\", "/").split("/")
        # Skip macOS resource forks and hidden files/directories.
        if any(part == "__MACOSX" or part.startswith(".") for part in parts):
            continue
        extension = os.path.splitext(parts[-1])[1].lower()
        if extension == ".json":
            if (
                info.file_size <= MAX_WORKFLOW_JSON_BYTES
                and len(json_candidates) < _MAX_ZIP_JSON_CANDIDATES
            ):
                json_candidates.append(info)
        elif extension in IMAGE_CONTAINER_EXTENSIONS:
            if (
                info.file_size <= _MAX_ZIP_IMAGE_BYTES
                and len(image_candidates) < _MAX_ZIP_IMAGE_CANDIDATES
            ):
                image_candidates.append(info)

    def depth(info: zipfile.ZipInfo) -> int:
        return len(info.filename.replace("\\", "/").split("/"))

    # Prefer shallow, small documents: the workflow is typically the
    # archive's headline content, not a bundled config deep in a subfolder.
    json_candidates.sort(key=lambda info: (depth(info), info.file_size))
    # Prefer shallow, large images: the metadata rides the full-size
    # generation image, not a thumbnail re-encoded by the site.
    image_candidates.sort(key=lambda info: (depth(info), -info.file_size))
    return json_candidates + image_candidates


def _extract_from_zip(archive_path: str) -> Optional[Dict[str, Any]]:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in _zip_candidates(archive):
                is_image = (
                    os.path.splitext(info.filename)[1].lower()
                    in IMAGE_CONTAINER_EXTENSIONS
                )
                limit = (
                    _MAX_ZIP_IMAGE_BYTES if is_image else MAX_WORKFLOW_JSON_BYTES
                )
                try:
                    with archive.open(info) as handle:
                        raw = handle.read(limit + 1)
                except Exception:
                    # Corrupt, encrypted or unsupported member: try the next
                    # candidate rather than losing the whole archive.
                    continue
                if len(raw) > limit:
                    continue
                if is_image:
                    document = _extract_from_image_bytes(raw)
                else:
                    try:
                        document = parse_workflow_text(raw.decode("utf-8"))
                    except UnicodeDecodeError:
                        continue
                if document is not None:
                    logger.debug(
                        "Workflow archive %s: using member %s",
                        archive_path,
                        info.filename,
                    )
                    return document
    except (OSError, zipfile.BadZipFile) as exc:
        logger.debug("Workflow archive unreadable: %s (%s)", archive_path, exc)
    return None


def _document_from_image_metadata(
    metadata: Dict[str, Optional[str]],
) -> Optional[Dict[str, Any]]:
    """Pick the workflow document out of structured image metadata.

    The UI-format document ("workflow") is what ComfyUI's loadGraphData
    consumes; fall back to the API-format "prompt" payload.
    """

    for key in ("workflow", "prompt"):
        text = metadata.get(key)
        if not text:
            continue
        document = parse_workflow_text(text)
        if document is not None:
            return document
    return None


def _extract_from_image(image_path: str) -> Optional[Dict[str, Any]]:
    # Local import: PIL/piexif are heavy and only needed for image artifacts.
    from .exif_utils import ExifUtils

    try:
        metadata = ExifUtils.load_structured_metadata(image_path)
    except Exception as exc:
        logger.debug("Workflow image metadata unreadable: %s (%s)", image_path, exc)
        return None
    return _document_from_image_metadata(metadata)


def _extract_from_image_bytes(raw: bytes) -> Optional[Dict[str, Any]]:
    """Extract a workflow from an image's bytes (e.g. a zip member).

    Reading the member into memory keeps the archive untouched and avoids
    materializing bundled screenshots on disk just to inspect their metadata.
    """

    # Local import: PIL/piexif are heavy and only needed for image artifacts.
    from .exif_utils import ExifUtils

    try:
        metadata = ExifUtils.load_structured_metadata(raw)
    except Exception as exc:
        logger.debug("Workflow image member metadata unreadable: %s", exc)
        return None
    return _document_from_image_metadata(metadata)


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
