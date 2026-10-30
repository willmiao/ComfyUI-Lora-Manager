"""Scanner for ComfyUI workflow resources (.json documents and containers)."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from ..config import config
from ..utils.constants import PREVIEW_EXTENSIONS
from ..utils.file_utils import (
    calculate_sha256,
    find_preview_file,
    normalize_path,
)
from ..utils.metadata_manager import MetadataManager
from ..utils.models import WorkflowMetadata
from ..utils.sidecar_paths import get_preview_dir
from ..utils.workflow_analysis import analyze_workflow_file
from ..utils.workflow_extraction import (
    IMAGE_CONTAINER_EXTENSIONS,
    WORKFLOW_ARTIFACT_EXTENSIONS,
    WORKFLOW_DOCUMENT_SUFFIX,
    materialize_workflow_document,
)
from .model_hash_index import ModelHashIndex
from .model_scanner import ModelScanner

logger = logging.getLogger(__name__)

# Sidecar files share the .json extension; they must never enter the library.
_SIDECAR_SUFFIXES = (".metadata.json", WORKFLOW_DOCUMENT_SUFFIX)

# LM-generated preview sidecars (``<workflow>.preview.webp``) share the image
# artifact extensions, so they must be filtered by name before the workflow
# extraction step. Without this, a preview that embeds a workflow (e.g. one
# written with preserve_metadata) would land in the library as a second entry.
_PREVIEW_SUFFIXES = tuple(
    ext for ext in PREVIEW_EXTENSIONS if ext.startswith(".preview.")
)


class WorkflowScanner(ModelScanner):
    """Scan and manage ComfyUI workflow artifacts.

    Library entries are the original uploaded files, kept byte-identical so
    their SHA256 stays the CivitAI identity (by-hash lookup and version
    tracking depend on it). ``.json`` artifacts carry the graph directly;
    ``.zip``/``.png``/``.webp`` containers get the workflow document
    extracted into a derived ``.workflow.json`` sidecar that every consumer
    (graph analysis, send-to-ComfyUI) reads. Files from which no workflow
    document can be extracted never enter the library — this keeps settings
    JSON and plain preview images out.
    """

    def __init__(self):
        super().__init__(
            model_type="workflow",
            model_class=WorkflowMetadata,
            file_extensions=set(WORKFLOW_ARTIFACT_EXTENSIONS),
            hash_index=ModelHashIndex(),
        )

    def _is_indexable_filename(self, filename: str) -> bool:
        lowered = filename.lower()
        if lowered.endswith(_SIDECAR_SUFFIXES):
            return False
        # Preview assets share the artifact image extensions (.webp/.png), so
        # a preview sidecar named "<workflow>.preview.webp" must never be
        # indexed as an image artifact of its own.
        if lowered.endswith(_PREVIEW_SUFFIXES):
            return False
        return True

    def get_model_roots(self) -> List[str]:
        """Return the configured workflow library root (empty while disabled)."""
        try:
            from .settings_manager import get_settings_manager

            if not get_settings_manager().is_workflows_enabled():
                return []
        except Exception:  # pragma: no cover - defensive; settings unavailable
            return []
        return [root for root in (config.workflows_roots or []) if root]

    @staticmethod
    def _is_image_artifact(file_path: str) -> bool:
        return os.path.splitext(file_path)[1].lower() in IMAGE_CONTAINER_EXTENSIONS

    def adjust_metadata(self, metadata, file_path, root_path):
        """Fill workflow analysis fields when they are missing.

        Runs on every scan and on the post-download path. The extraction
        result is cached in the derived ``.workflow.json`` sidecar, so the
        steady-state cost is one small JSON parse per entry whose analysis
        fields have not been populated yet.
        """
        if not isinstance(metadata, WorkflowMetadata) or metadata.workflow_format:
            return metadata
        try:
            document_path = materialize_workflow_document(file_path)
            analysis = (
                analyze_workflow_file(document_path) if document_path else None
            )
        except Exception as exc:
            logger.debug(
                "Workflow analysis refresh failed for %s: %s", file_path, exc
            )
            return metadata
        if analysis is None:
            return metadata
        metadata.workflow_format = analysis.workflow_format
        metadata.node_count = analysis.node_count
        metadata.node_classes = analysis.node_classes
        metadata.model_refs = analysis.model_refs
        metadata.civitai_refs = analysis.civitai_refs
        metadata.primary_model_refs = analysis.primary_model_refs
        return metadata

    async def _create_default_metadata(
        self,
        file_path: str,
        *,
        include_remote: bool = False,
        checkpoint_name_hint: Optional[str] = None,
    ) -> Optional[WorkflowMetadata]:
        """Create metadata by hashing the artifact and analyzing its workflow.

        Returns None for files that carry no ComfyUI workflow document, so
        they stay out of the library. The base model is resolved from the
        workflow's referenced models against the local library;
        ``include_remote`` (one-off user actions only, never scans) also
        allows the CivitAI URN fallback. ``checkpoint_name_hint`` names the
        primary checkpoint observed at generation time and outranks the
        static votes when it resolves locally.
        """
        try:
            real_path = os.path.realpath(file_path)
            if not os.path.exists(real_path):
                logger.error(f"File not found: {file_path}")
                return None

            document_path = materialize_workflow_document(
                file_path, read_path=real_path
            )
            analysis = (
                analyze_workflow_file(document_path) if document_path else None
            )
            if analysis is None:
                logger.debug(f"Skipping artifact without a workflow: {file_path}")
                return None

            base_name = os.path.splitext(os.path.basename(file_path))[0]
            preview_url = find_preview_file(base_name, get_preview_dir(file_path))
            if not preview_url and self._is_image_artifact(file_path):
                # An image artifact doubles as its own preview.
                preview_url = file_path
            sha256 = await calculate_sha256(real_path)
            if not sha256:
                logger.warning(
                    f"Skipping metadata creation for empty workflow file: {file_path}"
                )
                return None

            try:
                from .workflow_base_model import resolve_workflow_base_model

                base_model = await resolve_workflow_base_model(
                    primary_model_refs=analysis.primary_model_refs,
                    model_refs=analysis.model_refs,
                    civitai_refs=analysis.civitai_refs,
                    include_remote=include_remote,
                    checkpoint_name_hint=checkpoint_name_hint,
                )
            except Exception:
                logger.debug(
                    "Base model resolution failed for %s", file_path, exc_info=True
                )
                base_model = None

            metadata = WorkflowMetadata(
                file_name=base_name,
                model_name=base_name,
                file_path=normalize_path(file_path),
                size=os.path.getsize(real_path),
                modified=datetime.now().timestamp(),
                sha256=sha256,
                base_model=base_model or "Unknown",
                preview_url=normalize_path(preview_url),
                tags=[],
                modelDescription="",
                from_civitai=False,
                workflow_format=analysis.workflow_format,
                node_count=analysis.node_count,
                node_classes=analysis.node_classes,
                model_refs=analysis.model_refs,
                civitai_refs=analysis.civitai_refs,
                primary_model_refs=analysis.primary_model_refs,
            )

            logger.info(f"Creating workflow metadata for {file_path}")
            await MetadataManager.save_metadata(file_path, metadata)

            return metadata

        except Exception as e:
            logger.error(
                f"Error creating default workflow metadata for {file_path}: {e}"
            )
            return None

    async def register_local_artifact(
        self,
        file_path: str,
        *,
        checkpoint_name_hint: Optional[str] = None,
    ) -> Optional[WorkflowMetadata]:
        """Create metadata and cache entry for a workflow written by LM.

        Used by the "Create LM-managed workflow" flow: the file is already on
        disk, so this reuses the scanner's metadata builder (analysis fields,
        preview lookup, sidecar write) and then inserts/updates the cache entry
        without forcing a full rescan. Being a one-off user action, base model
        resolution here may also consult CivitAI URNs embedded in the graph.
        ``checkpoint_name_hint`` names the primary checkpoint observed at
        generation time and outranks the static votes when it resolves locally.
        """
        metadata = await self._create_default_metadata(
            file_path, include_remote=True, checkpoint_name_hint=checkpoint_name_hint
        )
        if metadata is None:
            return None
        await self.sync_cache_from_metadata(file_path, metadata.to_dict())
        return metadata
