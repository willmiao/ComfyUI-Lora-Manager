import logging
import os
from typing import Any, List, Tuple
import comfy.sd  # pyright: ignore[reportMissingImports]
import folder_paths  # pyright: ignore[reportMissingImports]
from ..utils.utils import get_checkpoint_info_absolute, _format_model_name_for_comfyui

logger = logging.getLogger(__name__)


class CheckpointLoaderLM:
    """Checkpoint Loader with support for extra folder paths

    Loads checkpoints from both standard ComfyUI folders and LoRA Manager's
    extra folder paths, providing a unified interface for checkpoint loading.
    The ckpt_name combo supports ComfyUI's control_after_generate, letting
    users pick a random checkpoint on every run; the base_model input narrows
    the random pool through a front-end extension that filters the combo
    options.
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
                    {
                        "tooltip": (
                            "The name of the checkpoint (model) to load. Use "
                            "control_after_generate to pick a random model on "
                            "every run."
                        ),
                        "control_after_generate": "fixed",
                    },
                ),
                "base_model": (
                    base_models,
                    {
                        "default": "Any",
                        "tooltip": (
                            "Restrict the random selection pool to this base "
                            "model. 'Any' uses the full pool."
                        ),
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
    def _get_checkpoint_names(cls) -> List[str]:
        """Get list of checkpoint names from scanner cache in ComfyUI format (relative path with extension)"""
        try:
            from ..services.service_registry import ServiceRegistry
            import asyncio

            async def _get_names():
                scanner = await ServiceRegistry.get_checkpoint_scanner()
                cache = await scanner.get_cached_data()

                # Get all model roots for calculating relative paths
                model_roots = scanner.get_model_roots()

                # Filter only checkpoint type (not diffusion_model) and format names
                names = []
                for item in cache.raw_data:
                    if item.get("sub_type") == "checkpoint":
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

            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures

                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_get_names())
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result()
            except RuntimeError:
                return asyncio.run(_get_names())
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

    def load_checkpoint(
        self, ckpt_name: str, base_model: str = "Any"
    ) -> Tuple[Any, Any, Any]:
        """Load a checkpoint by name, supporting extra folder paths

        Args:
            ckpt_name: The name of the checkpoint to load (relative path with extension)
            base_model: Only used by the front-end to filter the random pool

        Returns:
            Tuple of (MODEL, CLIP, VAE)
        """
        del base_model
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
