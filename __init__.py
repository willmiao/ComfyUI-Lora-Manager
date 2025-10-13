try:  # pragma: no cover - import fallback for pytest collection
    from .py.lora_manager import LoraManager
    from .py.nodes.lora_loader import LoraManagerLoader, LoraManagerTextLoader
    from .py.nodes.trigger_word_toggle import TriggerWordToggle
    from .py.nodes.prompt import PromptLoraManager
    from .py.nodes.lora_stacker import LoraStacker
    from .py.nodes.save_image import SaveImage
    from .py.nodes.debug_metadata import DebugMetadata
    from .py.nodes.wanvideo_lora_select import WanVideoLoraSelect
    from .py.nodes.wanvideo_lora_select_from_text import WanVideoLoraSelectFromText
    from .py.metadata_collector import init as init_metadata_collector
except ImportError:  # pragma: no cover - allows running under pytest without package install
    import importlib
    import pathlib
    import sys

    package_root = pathlib.Path(__file__).resolve().parent
    if str(package_root) not in sys.path:
        sys.path.append(str(package_root))

    PromptLoraManager = importlib.import_module("py.nodes.prompt").PromptLoraManager
    LoraManager = importlib.import_module("py.lora_manager").LoraManager
    LoraManagerLoader = importlib.import_module("py.nodes.lora_loader").LoraManagerLoader
    LoraManagerTextLoader = importlib.import_module("py.nodes.lora_loader").LoraManagerTextLoader
    TriggerWordToggle = importlib.import_module("py.nodes.trigger_word_toggle").TriggerWordToggle
    LoraStacker = importlib.import_module("py.nodes.lora_stacker").LoraStacker
    SaveImage = importlib.import_module("py.nodes.save_image").SaveImage
    DebugMetadata = importlib.import_module("py.nodes.debug_metadata").DebugMetadata
    WanVideoLoraSelect = importlib.import_module("py.nodes.wanvideo_lora_select").WanVideoLoraSelect
    WanVideoLoraSelectFromText = importlib.import_module("py.nodes.wanvideo_lora_select_from_text").WanVideoLoraSelectFromText
    init_metadata_collector = importlib.import_module("py.metadata_collector").init

NODE_CLASS_MAPPINGS = {
    PromptLoraManager.NAME: PromptLoraManager,
    LoraManagerLoader.NAME: LoraManagerLoader,
    LoraManagerTextLoader.NAME: LoraManagerTextLoader,
    TriggerWordToggle.NAME: TriggerWordToggle,
    LoraStacker.NAME: LoraStacker,
    SaveImage.NAME: SaveImage,
    DebugMetadata.NAME: DebugMetadata,
    WanVideoLoraSelect.NAME: WanVideoLoraSelect,
    WanVideoLoraSelectFromText.NAME: WanVideoLoraSelectFromText
}

WEB_DIRECTORY = "./web/comfyui"

# Initialize metadata collector
init_metadata_collector()

# Register routes on import
LoraManager.add_routes()
__all__ = ['NODE_CLASS_MAPPINGS', 'WEB_DIRECTORY']
