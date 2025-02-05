from abc import ABC, abstractmethod
from typing import Dict, Optional

class MetadataProvider(ABC):
    """Abstract base class for metadata providers"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name"""
        pass
        
    @abstractmethod
    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        """Get model metadata by hash"""
        pass
        
    @abstractmethod
    async def download_preview(self, preview_url: str, save_path: str) -> bool:
        """Download preview image"""
        pass
        
    @abstractmethod 
    def format_metadata(self, data: Dict) -> Dict:
        """Format raw API response into standard metadata format"""
        pass
        
    @abstractmethod
    async def close(self):
        """Clean up resources"""
        pass
