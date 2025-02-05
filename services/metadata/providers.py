from typing import Dict, Type
from .base import MetadataProvider

class MetadataProviderManager:
    """Manages metadata providers"""
    
    _providers: Dict[str, Type[MetadataProvider]] = {}
    _instances: Dict[str, MetadataProvider] = {}
    
    @classmethod
    def register(cls, provider_class: Type[MetadataProvider]):
        """Register a new provider"""
        cls._providers[provider_class.name] = provider_class
        
    @classmethod
    async def get_provider(cls, name: str) -> MetadataProvider:
        """Get or create provider instance"""
        if name not in cls._instances:
            if name not in cls._providers:
                raise ValueError(f"Unknown provider: {name}")
            cls._instances[name] = cls._providers[name]()
        return cls._instances[name]

    @classmethod
    async def close_all(cls):
        """Close all provider instances"""
        for provider in cls._instances.values():
            await provider.close()
        cls._instances.clear()
