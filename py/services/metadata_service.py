import os
import logging
from .model_metadata_provider import (
    ModelMetadataProvider,
    ModelMetadataProviderManager, 
    SQLiteModelMetadataProvider,
    CivitaiModelMetadataProvider,
    CivArchiveModelMetadataProvider,
    FallbackMetadataProvider
)
from .settings_manager import get_settings_manager
from .metadata_archive_manager import MetadataArchiveManager
from .service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

async def initialize_metadata_providers():
    """Initialize and configure all metadata providers based on settings"""
    provider_manager = await ModelMetadataProviderManager.get_instance()
    
    # Clear existing providers to allow reinitialization
    provider_manager.providers.clear()
    provider_manager.default_provider = None
    
    # Get settings
    settings_manager = get_settings_manager()
    enable_archive_db = settings_manager.get('enable_metadata_archive_db', False)
    
    providers = []
    
    # Initialize archive database provider if enabled
    if enable_archive_db:
        try:
            # Initialize archive manager
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            archive_manager = MetadataArchiveManager(base_path)
            
            db_path = archive_manager.get_database_path()
            if db_path and os.path.exists(db_path):
                sqlite_provider = SQLiteModelMetadataProvider(db_path)
                provider_manager.register_provider('sqlite', sqlite_provider)
                providers.append(('sqlite', sqlite_provider))
                logger.debug(f"SQLite metadata provider registered with database: {db_path}")
            else:
                logger.warning("Metadata archive database is enabled but database file not found")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite metadata provider: {e}")
    
    # Initialize Civitai API provider (always available as fallback)
    try:
        civitai_client = await ServiceRegistry.get_civitai_client()
        civitai_provider = CivitaiModelMetadataProvider(civitai_client)
        provider_manager.register_provider('civitai_api', civitai_provider)
        providers.append(('civitai_api', civitai_provider))
        logger.debug("Civitai API metadata provider registered")
    except Exception as e:
        logger.error(f"Failed to initialize Civitai API metadata provider: {e}")

    # Register CivArchive provider, and all add to fallback providers
    try:
        civarchive_client = await ServiceRegistry.get_civarchive_client()
        civarchive_provider = CivArchiveModelMetadataProvider(civarchive_client)
        provider_manager.register_provider('civarchive_api', civarchive_provider)
        providers.append(('civarchive_api', civarchive_provider))
        logger.debug("CivArchive metadata provider registered (also included in fallback)")
    except Exception as e:
        logger.error(f"Failed to initialize CivArchive metadata provider: {e}")

    # Set up fallback provider based on available providers
    if len(providers) > 1:
        # Always use Civitai API (it has better metadata), then CivArchive API, then Archive DB
        ordered_providers: list[tuple[str, ModelMetadataProvider]] = []
        ordered_providers.extend([p for p in providers if p[0] == 'civitai_api'])
        ordered_providers.extend([p for p in providers if p[0] == 'civarchive_api'])
        ordered_providers.extend([p for p in providers if p[0] == 'sqlite'])
        
        if ordered_providers:
            fallback_provider = FallbackMetadataProvider(ordered_providers)
            provider_manager.register_provider('fallback', fallback_provider, is_default=True)
    elif len(providers) == 1:
        # Only one provider available, set it as default
        provider_name, provider = providers[0]
        provider_manager.register_provider(provider_name, provider, is_default=True)
        logger.debug(f"Single metadata provider registered as default: {provider_name}")
    else:
        logger.warning("No metadata providers available - this may cause metadata lookup failures")
    
    return provider_manager

async def update_metadata_providers():
    """Update metadata providers based on current settings"""
    try:
        # Get current settings
        settings_manager = get_settings_manager()
        enable_archive_db = settings_manager.get('enable_metadata_archive_db', False)
        
        # Reinitialize all providers with new settings
        provider_manager = await initialize_metadata_providers()
        
        logger.info(f"Updated metadata providers, archive_db enabled: {enable_archive_db}")
        return provider_manager
    except Exception as e:
        logger.error(f"Failed to update metadata providers: {e}")
        return await ModelMetadataProviderManager.get_instance()

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

async def get_default_metadata_provider():
    """Get the default metadata provider (fallback or single provider)"""
    return await get_metadata_provider()
