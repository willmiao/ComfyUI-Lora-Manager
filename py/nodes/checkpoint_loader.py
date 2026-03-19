import logging
from typing import List, Tuple
import comfy.sd # type: ignore
import folder_paths # type: ignore
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
    def INPUT_TYPES(s):
        # Get list of checkpoint names from scanner (includes extra folder paths)
        checkpoint_names = s._get_checkpoint_names()
        return {
            "required": {
                "ckpt_name": (
                    checkpoint_names,
                    {"tooltip": "The name of the checkpoint (model) to load."},
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
                        if file_path:
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

    def load_checkpoint(self, ckpt_name: str) -> Tuple:
        """Load a checkpoint by name, supporting extra folder paths

        Args:
            ckpt_name: The name of the checkpoint to load (relative path with extension)

        Returns:
            Tuple of (MODEL, CLIP, VAE)
        """
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
