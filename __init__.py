try:  # pragma: no cover - import fallback for pytest collection
    from .py.lora_manager import LoraManager
    from .py.nodes.lora_loader import LoraLoaderLM, LoraTextLoaderLM
    from .py.nodes.checkpoint_loader import CheckpointLoaderLM
    from .py.nodes.unet_loader import UNETLoaderLM
    from .py.nodes.trigger_word_toggle import TriggerWordToggleLM
    from .py.nodes.prompt import PromptLM
    from .py.nodes.text import TextLM
    from .py.nodes.lora_stacker import LoraStackerLM
    from .py.nodes.lora_stack_combiner import LoraStackCombinerLM
    from .py.nodes.save_image import SaveImageLM
    from .py.nodes.debug_metadata import DebugMetadataLM
    from .py.nodes.wanvideo_lora_select import WanVideoLoraSelectLM
    from .py.nodes.wanvideo_lora_select_from_text import WanVideoLoraTextSelectLM
    from .py.nodes.lora_pool import LoraPoolLM
    from .py.nodes.lora_randomizer import LoraRandomizerLM
    from .py.nodes.lora_cycler import LoraCyclerLM
    from .py.nodes.lora_info import LoraInfoLM
    from .py.nodes.lora_syntax_to_path import LoraSyntaxToPath
    from .py.nodes.create_hook_lora import CreateHookLoraLM
    from .py.nodes.load_image_metadata import LoadImageMetadataLM
    from .py.nodes.metadata_overwrite import MetadataOverwriteLM
    from .py.metadata_collector import init as init_metadata_collector
except (
    ImportError
):  # pragma: no cover - allows running under pytest without package install
    import pathlib
    import sys

    package_root = pathlib.Path(__file__).resolve().parent
    if str(package_root) not in sys.path:
        sys.path.append(str(package_root))

    # pytest collects this file as a top-level module: its Package collector walks
    # up from tests/ while __init__.py exists, so the repo root becomes a package
    # node and this file is imported without one. Relative imports cannot resolve
    # there, so pull the same objects through the top-level "py" package that the
    # sys.path entry above makes importable.
    from py.lora_manager import LoraManager
    from py.nodes.lora_loader import LoraLoaderLM, LoraTextLoaderLM
    from py.nodes.checkpoint_loader import CheckpointLoaderLM
    from py.nodes.unet_loader import UNETLoaderLM
    from py.nodes.trigger_word_toggle import TriggerWordToggleLM
    from py.nodes.prompt import PromptLM
    from py.nodes.text import TextLM
    from py.nodes.lora_stacker import LoraStackerLM
    from py.nodes.lora_stack_combiner import LoraStackCombinerLM
    from py.nodes.save_image import SaveImageLM
    from py.nodes.debug_metadata import DebugMetadataLM
    from py.nodes.wanvideo_lora_select import WanVideoLoraSelectLM
    from py.nodes.wanvideo_lora_select_from_text import WanVideoLoraTextSelectLM
    from py.nodes.lora_pool import LoraPoolLM
    from py.nodes.lora_randomizer import LoraRandomizerLM
    from py.nodes.lora_cycler import LoraCyclerLM
    from py.nodes.lora_info import LoraInfoLM
    from py.nodes.lora_syntax_to_path import LoraSyntaxToPath
    from py.nodes.create_hook_lora import CreateHookLoraLM
    from py.nodes.load_image_metadata import LoadImageMetadataLM
    from py.nodes.metadata_overwrite import MetadataOverwriteLM
    from py.metadata_collector import init as init_metadata_collector

NODE_CLASS_MAPPINGS = {
    PromptLM.NAME: PromptLM,
    TextLM.NAME: TextLM,
    LoraLoaderLM.NAME: LoraLoaderLM,
    LoraTextLoaderLM.NAME: LoraTextLoaderLM,
    CheckpointLoaderLM.NAME: CheckpointLoaderLM,
    UNETLoaderLM.NAME: UNETLoaderLM,
    TriggerWordToggleLM.NAME: TriggerWordToggleLM,
    LoraStackerLM.NAME: LoraStackerLM,
    LoraStackCombinerLM.NAME: LoraStackCombinerLM,
    SaveImageLM.NAME: SaveImageLM,
    DebugMetadataLM.NAME: DebugMetadataLM,
    WanVideoLoraSelectLM.NAME: WanVideoLoraSelectLM,
    WanVideoLoraTextSelectLM.NAME: WanVideoLoraTextSelectLM,
    LoraPoolLM.NAME: LoraPoolLM,
    LoraRandomizerLM.NAME: LoraRandomizerLM,
    LoraCyclerLM.NAME: LoraCyclerLM,
    LoraInfoLM.NAME: LoraInfoLM,
    LoraSyntaxToPath.NAME: LoraSyntaxToPath,
    CreateHookLoraLM.NAME: CreateHookLoraLM,
    MetadataOverwriteLM.NAME: MetadataOverwriteLM,
    LoadImageMetadataLM.NAME: LoadImageMetadataLM,
}

WEB_DIRECTORY = "./web/comfyui"

# Check and build Vue widgets if needed (development mode)
try:
    from .py.vue_widget_builder import check_and_build_vue_widgets

    # Auto-build in development, warn only if fails
    check_and_build_vue_widgets(auto_build=True, warn_only=True)
except ImportError:
    # Fallback for pytest (see the note in the import block above): go through the
    # top-level "py" package, which that block has already put on sys.path.
    from py.vue_widget_builder import check_and_build_vue_widgets

    check_and_build_vue_widgets(auto_build=True, warn_only=True)
except Exception as e:
    import logging

    logging.warning(f"[LoRA Manager] Vue widget build check skipped: {e}")

# Initialize metadata collector
init_metadata_collector()

# Register routes on import
LoraManager.add_routes()
__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]
