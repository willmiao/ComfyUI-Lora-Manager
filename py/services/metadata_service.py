import os
import logging
from .model_metadata_provider import ModelMetadataProviderManager, SQLiteModelMetadataProvider

logger = logging.getLogger(__name__)

async def initialize_metadata_providers():
    """Initialize and configure all metadata providers"""
    provider_manager = await ModelMetadataProviderManager.get_instance()
    
    # Use hardcoded SQLite DB path if not set in settings
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'civitai', 'civitai.sqlite'
    )
    if db_path and os.path.exists(db_path):
        try:
            sqlite_provider = SQLiteModelMetadataProvider(db_path)
            provider_manager.register_provider('sqlite', sqlite_provider)
            logger.info(f"SQLite metadata provider registered with database: {db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite metadata provider: {e}")
    
    return provider_manager

async def get_metadata_provider(provider_name: str = None):
    """Get a specific metadata provider or default provider"""
    provider_manager = await ModelMetadataProviderManager.get_instance()
    
    if provider_name:
        return provider_manager._get_provider(provider_name)
    
    return provider_manager._get_provider()
