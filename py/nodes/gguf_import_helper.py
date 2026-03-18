"""
Helper module to safely import ComfyUI-GGUF modules.

This module provides a robust way to import ComfyUI-GGUF functionality
regardless of how ComfyUI loaded it.
"""

import sys
import os
import importlib.util
import logging
from typing import Optional, Tuple, Any

logger = logging.getLogger(__name__)


def _get_gguf_path() -> str:
    """Get the path to ComfyUI-GGUF based on this file's location.

    Since ComfyUI-Lora-Manager and ComfyUI-GGUF are both in custom_nodes/,
    we can derive the GGUF path from our own location.
    """
    # This file is at: custom_nodes/ComfyUI-Lora-Manager/py/nodes/gguf_import_helper.py
    # ComfyUI-GGUF is at: custom_nodes/ComfyUI-GGUF
    current_file = os.path.abspath(__file__)
    # Go up 4 levels: nodes -> py -> ComfyUI-Lora-Manager -> custom_nodes
    custom_nodes_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    )
    return os.path.join(custom_nodes_dir, "ComfyUI-GGUF")


def _find_gguf_module() -> Optional[Any]:
    """Find ComfyUI-GGUF module in sys.modules.

    ComfyUI registers modules using the full path with dots replaced by _x_.
    """
    gguf_path = _get_gguf_path()
    sys_module_name = gguf_path.replace(".", "_x_")

    logger.debug(f"[GGUF Import] Looking for module '{sys_module_name}' in sys.modules")
    if sys_module_name in sys.modules:
        logger.info(f"[GGUF Import] Found module: '{sys_module_name}'")
        return sys.modules[sys_module_name]

    logger.debug(f"[GGUF Import] Module not found: '{sys_module_name}'")
    return None


def _load_gguf_modules_directly() -> Optional[Any]:
    """Load ComfyUI-GGUF modules directly from file paths."""
    gguf_path = _get_gguf_path()

    logger.info(f"[GGUF Import] Direct Load: Attempting to load from '{gguf_path}'")

    if not os.path.exists(gguf_path):
        logger.warning(f"[GGUF Import] Path does not exist: {gguf_path}")
        return None

    try:
        namespace = "ComfyUI_GGUF_Dynamic"
        init_path = os.path.join(gguf_path, "__init__.py")

        if not os.path.exists(init_path):
            logger.warning(f"[GGUF Import] __init__.py not found at '{init_path}'")
            return None

        logger.debug(f"[GGUF Import] Loading from '{init_path}'")
        spec = importlib.util.spec_from_file_location(namespace, init_path)
        if not spec or not spec.loader:
            logger.error(f"[GGUF Import] Failed to create spec for '{init_path}'")
            return None

        package = importlib.util.module_from_spec(spec)
        package.__path__ = [gguf_path]
        sys.modules[namespace] = package
        spec.loader.exec_module(package)
        logger.debug(f"[GGUF Import] Loaded main package '{namespace}'")

        # Load submodules
        loaded = []
        for submod_name in ["loader", "ops", "nodes"]:
            submod_path = os.path.join(gguf_path, f"{submod_name}.py")
            if os.path.exists(submod_path):
                submod_spec = importlib.util.spec_from_file_location(
                    f"{namespace}.{submod_name}", submod_path
                )
                if submod_spec and submod_spec.loader:
                    submod = importlib.util.module_from_spec(submod_spec)
                    submod.__package__ = namespace
                    sys.modules[f"{namespace}.{submod_name}"] = submod
                    submod_spec.loader.exec_module(submod)
                    setattr(package, submod_name, submod)
                    loaded.append(submod_name)
                    logger.debug(f"[GGUF Import] Loaded submodule '{submod_name}'")

        logger.info(f"[GGUF Import] Direct Load success: {loaded}")
        return package

    except Exception as e:
        logger.error(f"[GGUF Import] Direct Load failed: {e}", exc_info=True)
        return None


def get_gguf_modules() -> Tuple[Any, Any, Any]:
    """Get ComfyUI-GGUF modules (loader, ops, nodes).

    Returns:
        Tuple of (loader_module, ops_module, nodes_module)

    Raises:
        RuntimeError: If ComfyUI-GGUF cannot be found or loaded.
    """
    logger.debug("[GGUF Import] Starting module search...")

    # Try to find already loaded module first
    gguf_module = _find_gguf_module()

    if gguf_module is None:
        logger.info("[GGUF Import] Not found in sys.modules, trying direct load...")
        gguf_module = _load_gguf_modules_directly()

    if gguf_module is None:
        raise RuntimeError(
            "ComfyUI-GGUF is not installed. "
            "Please install from https://github.com/city96/ComfyUI-GGUF"
        )

    # Extract submodules
    loader = getattr(gguf_module, "loader", None)
    ops = getattr(gguf_module, "ops", None)
    nodes = getattr(gguf_module, "nodes", None)

    if loader is None or ops is None or nodes is None:
        missing = [
            name
            for name, mod in [("loader", loader), ("ops", ops), ("nodes", nodes)]
            if mod is None
        ]
        raise RuntimeError(f"ComfyUI-GGUF missing submodules: {missing}")

    logger.debug("[GGUF Import] All modules loaded successfully")
    return loader, ops, nodes


def get_gguf_sd_loader():
    """Get the gguf_sd_loader function from ComfyUI-GGUF."""
    loader, _, _ = get_gguf_modules()
    return getattr(loader, "gguf_sd_loader")


def get_ggml_ops():
    """Get the GGMLOps class from ComfyUI-GGUF."""
    _, ops, _ = get_gguf_modules()
    return getattr(ops, "GGMLOps")


def get_gguf_model_patcher():
    """Get the GGUFModelPatcher class from ComfyUI-GGUF."""
    _, _, nodes = get_gguf_modules()
    return getattr(nodes, "GGUFModelPatcher")
