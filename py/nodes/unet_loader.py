import logging
import os
from typing import List, Tuple
import torch
import comfy.sd
from ..utils.utils import get_checkpoint_info_absolute, _format_model_name_for_comfyui

logger = logging.getLogger(__name__)


class UNETLoaderLM:
    """UNET Loader with support for extra folder paths

    Loads diffusion models/UNets from both standard ComfyUI folders and LoRA Manager's
    extra folder paths, providing a unified interface for UNET loading.
    Supports both regular diffusion models and GGUF format models.
    """

    NAME = "UNETLoaderLM"
    CATEGORY = "Lora Manager/loaders"

    @classmethod
    def INPUT_TYPES(s):
        # Get list of unet names from scanner (includes extra folder paths)
        unet_names = s._get_unet_names()
        return {
            "required": {
                "unet_name": (
                    unet_names,
                    {"tooltip": "The name of the diffusion model to load."},
                ),
                "weight_dtype": (
                    ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"],
                    {"tooltip": "The dtype to use for the model weights."},
                ),
            }
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("MODEL",)
    OUTPUT_TOOLTIPS = ("The model used for denoising latents.",)
    FUNCTION = "load_unet"

    @classmethod
    def _get_unet_names(cls) -> List[str]:
        """Get list of diffusion model names from scanner cache in ComfyUI format (relative path with extension)"""
        try:
            from ..services.service_registry import ServiceRegistry
            import asyncio

            async def _get_names():
                scanner = await ServiceRegistry.get_checkpoint_scanner()
                cache = await scanner.get_cached_data()

                # Get all model roots for calculating relative paths
                model_roots = scanner.get_model_roots()

                # Filter only diffusion_model type and format names
                names = []
                for item in cache.raw_data:
                    if item.get("sub_type") == "diffusion_model":
                        file_path = item.get("file_path", "")
                        if file_path:
                            # Format as ComfyUI-style: "folder/model_name.ext"
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
            logger.error(f"Error getting unet names: {e}")
            return []

    def load_unet(self, unet_name: str, weight_dtype: str) -> Tuple:
        """Load a diffusion model by name, supporting extra folder paths

        Args:
            unet_name: The name of the diffusion model to load (format: "folder/model_name.ext")
            weight_dtype: The dtype to use for model weights

        Returns:
            Tuple of (MODEL,)
        """
        # Get absolute path from cache using ComfyUI-style name
        unet_path, metadata = get_checkpoint_info_absolute(unet_name)

        if metadata is None:
            raise FileNotFoundError(
                f"Diffusion model '{unet_name}' not found in LoRA Manager cache. "
                "Make sure the model is indexed and try again."
            )

        # Check if it's a GGUF model
        if unet_path.endswith(".gguf"):
            return self._load_gguf_unet(unet_path, unet_name, weight_dtype)

        # Load regular diffusion model using ComfyUI's API
        logger.info(f"Loading diffusion model from: {unet_path}")

        # Build model options based on weight_dtype
        model_options = {}
        if weight_dtype == "fp8_e4m3fn":
            model_options["dtype"] = torch.float8_e4m3fn
        elif weight_dtype == "fp8_e4m3fn_fast":
            model_options["dtype"] = torch.float8_e4m3fn
            model_options["fp8_optimizations"] = True
        elif weight_dtype == "fp8_e5m2":
            model_options["dtype"] = torch.float8_e5m2

        model = comfy.sd.load_diffusion_model(unet_path, model_options=model_options)
        return (model,)

    def _load_gguf_unet(
        self, unet_path: str, unet_name: str, weight_dtype: str
    ) -> Tuple:
        """Load a GGUF format diffusion model

        Args:
            unet_path: Absolute path to the GGUF file
            unet_name: Name of the model for error messages
            weight_dtype: The dtype to use for model weights

        Returns:
            Tuple of (MODEL,)
        """
        try:
            # Try to import ComfyUI-GGUF modules
            from custom_nodes.ComfyUI_GGUF.loader import gguf_sd_loader
            from custom_nodes.ComfyUI_GGUF.ops import GGMLOps
            from custom_nodes.ComfyUI_GGUF.nodes import GGUFModelPatcher
        except ImportError:
            raise RuntimeError(
                f"Cannot load GGUF model '{unet_name}'. "
                "ComfyUI-GGUF is not installed. "
                "Please install ComfyUI-GGUF from https://github.com/city96/ComfyUI-GGUF "
                "to load GGUF format models."
            )

        logger.info(f"Loading GGUF diffusion model from: {unet_path}")

        try:
            # Load GGUF state dict
            sd, extra = gguf_sd_loader(unet_path)

            # Prepare kwargs for metadata if supported
            kwargs = {}
            import inspect

            valid_params = inspect.signature(
                comfy.sd.load_diffusion_model_state_dict
            ).parameters
            if "metadata" in valid_params:
                kwargs["metadata"] = extra.get("metadata", {})

            # Setup custom operations with GGUF support
            ops = GGMLOps()

            # Handle weight_dtype for GGUF models
            if weight_dtype in ("default", None):
                ops.Linear.dequant_dtype = None
            elif weight_dtype in ["target"]:
                ops.Linear.dequant_dtype = weight_dtype
            else:
                ops.Linear.dequant_dtype = getattr(torch, weight_dtype, None)

            # Load the model
            model = comfy.sd.load_diffusion_model_state_dict(
                sd, model_options={"custom_operations": ops}, **kwargs
            )

            if model is None:
                raise RuntimeError(
                    f"Could not detect model type for GGUF diffusion model: {unet_path}"
                )

            # Wrap with GGUFModelPatcher
            model = GGUFModelPatcher.clone(model)

            return (model,)

        except Exception as e:
            logger.error(f"Error loading GGUF diffusion model '{unet_name}': {e}")
            raise RuntimeError(
                f"Failed to load GGUF diffusion model '{unet_name}': {str(e)}"
            )
