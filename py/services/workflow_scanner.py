"""Scanner for ComfyUI workflow resources (.json graph documents)."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from ..config import config
from ..utils.file_utils import (
    calculate_sha256,
    find_preview_file,
    normalize_path,
)
from ..utils.metadata_manager import MetadataManager
from ..utils.models import WorkflowMetadata
from ..utils.sidecar_paths import get_preview_dir
from ..utils.workflow_analysis import analyze_workflow_file
from .model_hash_index import ModelHashIndex
from .model_scanner import ModelScanner

logger = logging.getLogger(__name__)

# Sidecar files share the .json extension; they must never enter the library.
_SIDECAR_SUFFIXES = (".metadata.json",)


class WorkflowScanner(ModelScanner):
    """Scan and manage ComfyUI workflow JSON files.

    Unlike weight files, workflow JSON is cheap to hash (eager SHA256) and its
    "metadata" comes from parsing the graph itself rather than a safetensors
    header. Non-workflow JSON documents (settings, sidecars, ...) are rejected
    by format sniffing and never enter the cache.
    """

    def __init__(self):
        super().__init__(
            model_type="workflow",
            model_class=WorkflowMetadata,
            file_extensions={".json"},
            hash_index=ModelHashIndex(),
        )

    def _is_indexable_filename(self, filename: str) -> bool:
        lowered = filename.lower()
        return not lowered.endswith(_SIDECAR_SUFFIXES)

    def get_model_roots(self) -> List[str]:
        """Workflow roots (primary + extra), empty while the feature is off."""
        try:
            from .settings_manager import get_settings_manager

            if not get_settings_manager().is_workflows_enabled():
                return []
        except Exception:  # pragma: no cover - defensive; settings unavailable
            return []
        roots: List[str] = []
        roots.extend(config.workflows_roots or [])
        roots.extend(config.extra_workflows_roots or [])
        seen: set[str] = set()
        unique_roots: List[str] = []
        for root in roots:
            if root and root not in seen:
                seen.add(root)
                unique_roots.append(root)
        return unique_roots

    async def _create_default_metadata(
        self, file_path: str
    ) -> Optional[WorkflowMetadata]:
        """Create metadata by hashing the file and parsing the workflow graph.

        Returns None for JSON documents that are not ComfyUI workflows, so
        they stay out of the library.
        """
        try:
            real_path = os.path.realpath(file_path)
            if not os.path.exists(real_path):
                logger.error(f"File not found: {file_path}")
                return None

            analysis = analyze_workflow_file(real_path)
            if analysis is None:
                logger.debug(f"Skipping non-workflow JSON: {file_path}")
                return None

            base_name = os.path.splitext(os.path.basename(file_path))[0]
            preview_url = find_preview_file(base_name, get_preview_dir(file_path))
            sha256 = await calculate_sha256(real_path)
            if not sha256:
                logger.warning(
                    f"Skipping metadata creation for empty workflow file: {file_path}"
                )
                return None

            metadata = WorkflowMetadata(
                file_name=base_name,
                model_name=base_name,
                file_path=normalize_path(file_path),
                size=os.path.getsize(real_path),
                modified=datetime.now().timestamp(),
                sha256=sha256,
                base_model="Unknown",
                preview_url=normalize_path(preview_url),
                tags=[],
                modelDescription="",
                from_civitai=False,
                workflow_format=analysis.workflow_format,
                node_count=analysis.node_count,
                node_classes=analysis.node_classes,
                model_refs=analysis.model_refs,
                civitai_refs=analysis.civitai_refs,
            )

            logger.info(f"Creating workflow metadata for {file_path}")
            await MetadataManager.save_metadata(file_path, metadata)

            return metadata

        except Exception as e:
            logger.error(
                f"Error creating default workflow metadata for {file_path}: {e}"
            )
            return None
