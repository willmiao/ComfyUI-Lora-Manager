"""ComfyUI workflow JSON sniffing and analysis.

Shared by the workflow scanner (library indexing) and, eventually, the recipe
parsers: both need to recognize ComfyUI workflow documents and extract the
models and node classes they reference.

Two on-disk shapes exist:

- UI format (``File > Save`` in ComfyUI): ``{"nodes": [...], "links": [...], ...}``
- API format (queue prompt payload): ``{"<node_id>": {"class_type": ..., "inputs": {...}}}``
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .constants import MODEL_FILE_EXTENSIONS

logger = logging.getLogger(__name__)

WORKFLOW_FORMAT_UI = "ui"
WORKFLOW_FORMAT_API = "api"

# Workflows are small JSON documents; anything larger is almost certainly not
# a graph (or is pathological) and is not worth parsing during a scan.
MAX_WORKFLOW_JSON_BYTES = 64 * 1024 * 1024

_CIVITAI_URN_PATTERN = re.compile(r"civitai:(\d+)@(\d+)")

# Loader input keys whose string values name a model file. Used for the API
# format; the UI format is handled by the generic extension scan below.
_LOADER_INPUT_KEYS = frozenset(
    {
        "lora_name",
        "ckpt_name",
        "unet_name",
        "vae_name",
        "clip_name",
        "control_net_name",
        "embedding_name",
        "model_name",
    }
)


@dataclass
class WorkflowAnalysis:
    """Structured facts extracted from a ComfyUI workflow document."""

    workflow_format: str
    node_count: int = 0
    node_classes: List[str] = field(default_factory=list)
    model_refs: List[str] = field(default_factory=list)
    civitai_refs: List[str] = field(default_factory=list)


def _sniff(data: Any) -> Optional[str]:
    """Return the workflow format for a parsed JSON document, or None."""
    if not isinstance(data, dict):
        return None
    nodes = data.get("nodes")
    links = data.get("links")
    if isinstance(nodes, list) and nodes and isinstance(links, list):
        return WORKFLOW_FORMAT_UI
    # API format: a non-empty mapping of node id -> {class_type, inputs}.
    if data and all(
        isinstance(value, dict) and "class_type" in value for value in data.values()
    ):
        return WORKFLOW_FORMAT_API
    return None


def sniff_workflow_text(text: str) -> Optional[str]:
    """Sniff raw JSON text; returns the workflow format or None."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    return _sniff(data)


def parse_workflow_text(text: str) -> Optional[Dict[str, Any]]:
    """Parse + sniff raw JSON text; return the document when it is a workflow."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if _sniff(data) is None:
        return None
    return data


def load_workflow_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Load and sniff a workflow JSON file.

    Returns the parsed document when it is a recognized ComfyUI workflow,
    None otherwise (unreadable, oversized, invalid JSON, or not a workflow).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            text = handle.read(MAX_WORKFLOW_JSON_BYTES + 1)
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Workflow file unreadable: %s (%s)", file_path, exc)
        return None
    if len(text) > MAX_WORKFLOW_JSON_BYTES:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if _sniff(data) is None:
        return None
    return data


def _walk_strings(value: Any, out: List[str], depth: int = 0) -> None:
    """Collect every string scalar in a JSON structure (bounded depth)."""
    if depth > 12 or len(out) > 10000:
        return
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _walk_strings(item, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk_strings(item, out, depth + 1)


def analyze_workflow(data: Dict[str, Any]) -> Optional[WorkflowAnalysis]:
    """Analyze a parsed workflow document. None when not a workflow."""
    workflow_format = _sniff(data)
    if workflow_format is None:
        return None

    node_classes: Set[str] = set()
    node_count = 0

    if workflow_format == WORKFLOW_FORMAT_API:
        node_count = len(data)
        for node in data.values():
            class_type = node.get("class_type")
            if isinstance(class_type, str) and class_type:
                node_classes.add(class_type)
    else:
        nodes = data.get("nodes") or []
        node_count = len(nodes)
        for node in nodes:
            if not isinstance(node, dict):
                continue
            class_type = node.get("type")
            if isinstance(class_type, str) and class_type:
                node_classes.add(class_type)

    strings: List[str] = []
    _walk_strings(data, strings)

    model_refs: Set[str] = set()
    civitai_refs: Set[str] = set()
    for value in strings:
        for match in _CIVITAI_URN_PATTERN.finditer(value):
            civitai_refs.add(f"civitai:{match.group(1)}@{match.group(2)}")
        lowered = value.lower()
        if any(lowered.endswith(ext) for ext in MODEL_FILE_EXTENSIONS):
            # Widget values are single model filenames; skip strings that
            # clearly carry more (URLs, prompts with punctuation-heavy tails
            # still end in an extension, so also bound the length).
            if len(value) <= 260 and " " not in value.strip():
                model_refs.add(value.strip())

    return WorkflowAnalysis(
        workflow_format=workflow_format,
        node_count=node_count,
        node_classes=sorted(node_classes),
        model_refs=sorted(model_refs),
        civitai_refs=sorted(civitai_refs),
    )


def analyze_workflow_file(file_path: str) -> Optional[WorkflowAnalysis]:
    """Load + analyze a workflow file; None when it is not a workflow."""
    data = load_workflow_file(file_path)
    if data is None:
        return None
    return analyze_workflow(data)
