import os

# Check if running in standalone mode
standalone_mode = os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1" or os.environ.get("HF_HUB_DISABLE_TELEMETRY", "0") == "0"

if not standalone_mode:
    from .metadata_hook import MetadataHook
    from .metadata_registry import MetadataRegistry

    def init():
        # Install hooks to collect metadata during execution
        MetadataHook.install()
        
        # Initialize registry
        registry = MetadataRegistry()
        
        print("ComfyUI Metadata Collector initialized")
        
    def get_metadata(prompt_id=None):
        """Helper function to get metadata from the registry"""
        registry = MetadataRegistry()
        return registry.get_metadata(prompt_id)
else:
    # Standalone mode - provide dummy implementations
    def init():
        print("ComfyUI Metadata Collector disabled in standalone mode")
        
    def get_metadata(prompt_id=None):
        """Dummy implementation for standalone mode"""
        return {}
