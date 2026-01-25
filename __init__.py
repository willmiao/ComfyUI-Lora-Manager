try:  # pragma: no cover - import fallback for pytest collection
    from .py.lora_manager import LoraManager
    from .py.nodes.lora_loader import LoraLoaderLM, LoraTextLoaderLM
    from .py.nodes.trigger_word_toggle import TriggerWordToggleLM
    from .py.nodes.prompt import PromptLM
    from .py.nodes.lora_stacker import LoraStackerLM
    from .py.nodes.save_image import SaveImageLM
    from .py.nodes.debug_metadata import DebugMetadataLM
    from .py.nodes.wanvideo_lora_select import WanVideoLoraSelectLM
    from .py.nodes.wanvideo_lora_select_from_text import WanVideoLoraTextSelectLM
    from .py.nodes.lora_pool import LoraPoolLM
    from .py.nodes.lora_randomizer import LoraRandomizerLM
    from .py.nodes.lora_cycler import LoraCyclerLM
    from .py.metadata_collector import init as init_metadata_collector
except (
    ImportError
):  # pragma: no cover - allows running under pytest without package install
    import importlib
    import pathlib
    import sys

    package_root = pathlib.Path(__file__).resolve().parent
    if str(package_root) not in sys.path:
        sys.path.append(str(package_root))

    PromptLM = importlib.import_module("py.nodes.prompt").PromptLM
    LoraManager = importlib.import_module("py.lora_manager").LoraManager
    LoraLoaderLM = importlib.import_module(
        "py.nodes.lora_loader"
    ).LoraLoaderLM
    LoraTextLoaderLM = importlib.import_module(
        "py.nodes.lora_loader"
    ).LoraTextLoaderLM
    TriggerWordToggleLM = importlib.import_module(
        "py.nodes.trigger_word_toggle"
    ).TriggerWordToggleLM
    LoraStackerLM = importlib.import_module("py.nodes.lora_stacker").LoraStackerLM
    SaveImageLM = importlib.import_module("py.nodes.save_image").SaveImageLM
    DebugMetadataLM = importlib.import_module("py.nodes.debug_metadata").DebugMetadataLM
    WanVideoLoraSelectLM = importlib.import_module(
        "py.nodes.wanvideo_lora_select"
    ).WanVideoLoraSelectLM
    WanVideoLoraTextSelectLM = importlib.import_module(
        "py.nodes.wanvideo_lora_select_from_text"
    ).WanVideoLoraTextSelectLM
    LoraPoolLM = importlib.import_module("py.nodes.lora_pool").LoraPoolLM
    LoraRandomizerLM = importlib.import_module(
        "py.nodes.lora_randomizer"
    ).LoraRandomizerLM
    LoraCyclerLM = importlib.import_module(
        "py.nodes.lora_cycler"
    ).LoraCyclerLM
    init_metadata_collector = importlib.import_module("py.metadata_collector").init

NODE_CLASS_MAPPINGS = {
    PromptLM.NAME: PromptLM,
    LoraLoaderLM.NAME: LoraLoaderLM,
    LoraTextLoaderLM.NAME: LoraTextLoaderLM,
    TriggerWordToggleLM.NAME: TriggerWordToggleLM,
    LoraStackerLM.NAME: LoraStackerLM,
    SaveImageLM.NAME: SaveImageLM,
    DebugMetadataLM.NAME: DebugMetadataLM,
    WanVideoLoraSelectLM.NAME: WanVideoLoraSelectLM,
    WanVideoLoraTextSelectLM.NAME: WanVideoLoraTextSelectLM,
    LoraPoolLM.NAME: LoraPoolLM,
    LoraRandomizerLM.NAME: LoraRandomizerLM,
    LoraCyclerLM.NAME: LoraCyclerLM,
}

WEB_DIRECTORY = "./web/comfyui"

# Check and build Vue widgets if needed (development mode)
try:
    from .py.vue_widget_builder import check_and_build_vue_widgets

    # Auto-build in development, warn only if fails
    check_and_build_vue_widgets(auto_build=True, warn_only=True)
except ImportError:
    # Fallback for pytest
    import importlib

    check_and_build_vue_widgets = importlib.import_module(
        "py.vue_widget_builder"
    ).check_and_build_vue_widgets
    check_and_build_vue_widgets(auto_build=True, warn_only=True)
except Exception as e:
    import logging

    logging.warning(f"[LoRA Manager] Vue widget build check skipped: {e}")

# Initialize metadata collector
init_metadata_collector()

# Register routes on import
LoraManager.add_routes()
__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]
