import os
import logging
from .model_metadata_provider import (
    ModelMetadataProviderManager, 
    SQLiteModelMetadataProvider,
    CivitaiModelMetadataProvider,
    FallbackMetadataProvider
)
from .settings_manager import settings
from .metadata_archive_manager import MetadataArchiveManager
from .service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

async def initialize_metadata_providers():
    """Initialize and configure all metadata providers based on settings"""
    provider_manager = await ModelMetadataProviderManager.get_instance()
    
    # Get settings
    enable_archive_db = settings.get('enable_metadata_archive_db', False)
    priority = settings.get('metadata_provider_priority', 'archive_db')
    
    providers = []
    
    # Initialize archive database provider if enabled
    if enable_archive_db:
        # Initialize archive manager
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        archive_manager = MetadataArchiveManager(base_path)
        
        db_path = archive_manager.get_database_path()
        if db_path:
            try:
                sqlite_provider = SQLiteModelMetadataProvider(db_path)
                provider_manager.register_provider('sqlite', sqlite_provider)
                providers.append(('sqlite', sqlite_provider))
                logger.info(f"SQLite metadata provider registered with database: {db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize SQLite metadata provider: {e}")
        else:
            logger.warning("Metadata archive database is enabled but not available")
    
    # Initialize Civitai API provider
    try:
        civitai_client = await ServiceRegistry.get_civitai_client()
        civitai_provider = CivitaiModelMetadataProvider(civitai_client)
        provider_manager.register_provider('civitai_api', civitai_provider)
        providers.append(('civitai_api', civitai_provider))
        logger.info("Civitai API metadata provider registered")
    except Exception as e:
        logger.error(f"Failed to initialize Civitai API metadata provider: {e}")
    
    # Set up fallback provider based on priority
    if len(providers) > 1:
        # Order providers based on priority setting
        if priority == 'archive_db':
            # Archive DB first, then Civitai API
            ordered_providers = [p[1] for p in providers if p[0] == 'sqlite'] + [p[1] for p in providers if p[0] == 'civitai_api']
        else:
            # Civitai API first, then Archive DB
            ordered_providers = [p[1] for p in providers if p[0] == 'civitai_api'] + [p[1] for p in providers if p[0] == 'sqlite']
        
        if ordered_providers:
            fallback_provider = FallbackMetadataProvider(ordered_providers)
            provider_manager.register_provider('fallback', fallback_provider, is_default=True)
            logger.info(f"Fallback metadata provider registered with priority: {priority}")
    elif len(providers) == 1:
        # Only one provider available, set it as default
        provider_name, provider = providers[0]
        provider_manager.register_provider(provider_name, provider, is_default=True)
        logger.info(f"Single metadata provider registered as default: {provider_name}")
    else:
        logger.warning("No metadata providers available")
    
    return provider_manager

async def update_metadata_provider_priority():
    """Update metadata provider priority based on current settings"""
    provider_manager = await ModelMetadataProviderManager.get_instance()
    
    # Get current settings
    enable_archive_db = settings.get('enable_metadata_archive_db', False)
    priority = settings.get('metadata_provider_priority', 'archive_db')
    
    # Rebuild providers with new priority
    await initialize_metadata_providers()
    
    logger.info(f"Updated metadata provider priority to: {priority}")

async def get_metadata_archive_manager():
    """Get metadata archive manager instance"""
    base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return MetadataArchiveManager(base_path)

async def get_metadata_provider(provider_name: str = None):
    """Get a specific metadata provider or default provider"""
    provider_manager = await ModelMetadataProviderManager.get_instance()
    
    if provider_name:
        return provider_manager._get_provider(provider_name)
    
    return provider_manager._get_provider()
