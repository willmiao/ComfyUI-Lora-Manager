import logging
import os
import random
from typing import Any, List, Optional, Tuple
import comfy.sd  # pyright: ignore[reportMissingImports]
import folder_paths  # pyright: ignore[reportMissingImports]
from ..utils.utils import get_checkpoint_info_absolute, _format_model_name_for_comfyui

logger = logging.getLogger(__name__)


class CheckpointLoaderLM:
    """Checkpoint Loader with support for extra folder paths

    Loads checkpoints from both standard ComfyUI folders and LoRA Manager's
    extra folder paths, providing a unified interface for checkpoint loading.
    """

    NAME = "Checkpoint Loader (LoraManager)"
    CATEGORY = "Lora Manager/loaders"

    @classmethod
    def INPUT_TYPES(cls):
        # Get list of checkpoint names from scanner (includes extra folder paths)
        checkpoint_names = cls._get_checkpoint_names()
        base_models = cls._get_available_base_models()
        return {
            "required": {
                "ckpt_name": (
                    checkpoint_names,
                    {"tooltip": "The name of the checkpoint (model) to load."},
                ),
                "select_at_random": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "Ignore ckpt_name and pick a random checkpoint from the "
                            "pool (optionally filtered by base_model) on every run."
                        ),
                    },
                ),
                "base_model": (
                    base_models,
                    {
                        "default": "Any",
                        "tooltip": "Restrict random selection to this base model. 'Any' uses the full pool.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE")
    OUTPUT_TOOLTIPS = (
        "The model used for denoising latents.",
        "The CLIP model used for encoding text prompts.",
        "The VAE model used for encoding and decoding images to and from latent space.",
    )
    FUNCTION = "load_checkpoint"

    @classmethod
    def IS_CHANGED(cls, ckpt_name, select_at_random=False, base_model="Any"):
        # Force re-execution on every run while randomizing, since the widget
        # values themselves don't change between queue runs.
        if select_at_random:
            return float("nan")
        return ckpt_name

    @staticmethod
    def _run_async(coro_fn):
        """Run an async fetcher, handling the case where an event loop is already running."""
        import asyncio

        try:
            asyncio.get_running_loop()
            import concurrent.futures

            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro_fn())
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        except RuntimeError:
            return asyncio.run(coro_fn())

    @classmethod
    def _get_checkpoint_names(cls, base_model: Optional[str] = None) -> List[str]:
        """Get list of checkpoint names from scanner cache in ComfyUI format (relative path with extension)

        Args:
            base_model: If given (and not "Any"), only include checkpoints matching this base model.
        """
        try:
            from ..services.service_registry import ServiceRegistry

            async def _get_names():
                scanner = await ServiceRegistry.get_checkpoint_scanner()
                cache = await scanner.get_cached_data()

                # Get all model roots for calculating relative paths
                model_roots = scanner.get_model_roots()

                # Filter only checkpoint type (not diffusion_model) and format names
                names = []
                for item in cache.raw_data:
                    if item.get("sub_type") != "checkpoint":
                        continue
                    if (
                        base_model
                        and base_model != "Any"
                        and item.get("base_model") != base_model
                    ):
                        continue
                    file_path = item.get("file_path", "")
                    # Only offer models that still exist on disk so ComfyUI
                    # flags missing checkpoints at queue time via
                    # "value not in list" (the scanner cache can be stale).
                    if file_path and os.path.exists(file_path):
                        # Format using relative path with OS-native separator
                        formatted_name = _format_model_name_for_comfyui(
                            file_path, model_roots
                        )
                        if formatted_name:
                            names.append(formatted_name)

                return sorted(names)

            return cls._run_async(_get_names)
        except Exception as e:
            logger.error(f"Error getting checkpoint names: {e}")
            return []

    @classmethod
    def _get_available_base_models(cls) -> List[str]:
        """Get distinct base_model values present among indexed checkpoints, for the random-selection filter."""
        try:
            from ..services.service_registry import ServiceRegistry

            async def _get_base_models():
                scanner = await ServiceRegistry.get_checkpoint_scanner()
                cache = await scanner.get_cached_data()

                base_models = set()
                for item in cache.raw_data:
                    if item.get("sub_type") != "checkpoint":
                        continue
                    base_model = item.get("base_model")
                    file_path = item.get("file_path", "")
                    if base_model and file_path and os.path.exists(file_path):
                        base_models.add(base_model)

                return sorted(base_models)

            return ["Any"] + cls._run_async(_get_base_models)
        except Exception as e:
            logger.error(f"Error getting available base models: {e}")
            return ["Any"]

    def load_checkpoint(
        self,
        ckpt_name: str,
        select_at_random: bool = False,
        base_model: str = "Any",
    ) -> Tuple[Any, Any, Any]:
        """Load a checkpoint by name, supporting extra folder paths

        Args:
            ckpt_name: The name of the checkpoint to load (relative path with extension)
            select_at_random: If True, ignore ckpt_name and pick randomly from the pool
            base_model: Restricts random selection to this base model ("Any" = no filter)

        Returns:
            Tuple of (MODEL, CLIP, VAE)
        """
        if select_at_random:
            pool = self._get_checkpoint_names(base_model)
            if not pool:
                raise FileNotFoundError(
                    f"No checkpoints found for base model '{base_model}'. "
                    "Pick a different base model or disable 'select_at_random'."
                )
            ckpt_name = random.choice(pool)
            logger.info(
                f"[CheckpointLoaderLM] Randomly selected checkpoint: {ckpt_name}"
            )

        # Get absolute path from cache using ComfyUI-style name
        ckpt_path, metadata = get_checkpoint_info_absolute(ckpt_name)

        if metadata is None:
            raise FileNotFoundError(
                f"Checkpoint '{ckpt_name}' not found in LoRA Manager cache. "
                "Make sure the checkpoint is indexed and try again."
            )

        # Load regular checkpoint using ComfyUI's API
        logger.info(f"Loading checkpoint from: {ckpt_path}")
        out = comfy.sd.load_checkpoint_guess_config(
            ckpt_path,
            output_vae=True,
            output_clip=True,
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
        )
        return out[:3]
