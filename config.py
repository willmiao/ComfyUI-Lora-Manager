import os
import folder_paths # type: ignore
from typing import List

class Config:
    """Global configuration for LoRA Manager"""
    
    def __init__(self):
        self.loras_roots = self._init_lora_paths()
        self.templates_path = os.path.join(os.path.dirname(__file__), 'templates')
        self.static_path = os.path.join(os.path.dirname(__file__), 'static')
        self.metadata_providers = {
            "civitai": {
                "enabled": True,
                "api_key": None  # Optional
            }
        }

    def _init_lora_paths(self) -> List[str]:
        """Initialize and validate LoRA paths from ComfyUI settings"""
        paths = list(set(path.replace(os.sep, "/") 
                for path in folder_paths.get_folder_paths("loras") 
                if os.path.exists(path)))
        print("Found LoRA roots:", "\n - " + "\n - ".join(paths))
        
        if not paths:
            raise ValueError("No valid loras folders found in ComfyUI configuration")
        
        return paths

    def get_preview_static_url(self, preview_path: str) -> str:
        """Convert local preview path to static URL"""
        if not preview_path:
            return ""
            
        for idx, root in enumerate(self.loras_roots, start=1):
            if preview_path.startswith(root):
                relative_path = os.path.relpath(preview_path, root)
                return f'/loras_static/root{idx}/preview/{relative_path.replace(os.sep, "/")}'
        
        return ""

# Global config instance
config = Config()
