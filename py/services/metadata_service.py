import os
import logging
from .model_metadata_provider import (
    ModelMetadataProvider,
    ModelMetadataProviderManager,
    SQLiteModelMetadataProvider,
    CivitaiModelMetadataProvider,
    CivArchiveModelMetadataProvider,
    FallbackMetadataProvider,
    RateLimitRetryingProvider,
)
from .settings_manager import get_settings_manager
from .metadata_archive_manager import MetadataArchiveManager
from .service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

_PROVIDER_DISPLAY_NAMES = {
    "civitai_api": "CivitAI",
    "civarchive_api": "CivArchive",
    "sqlite": "Archive DB",
}

_PRESET_PROVIDER_ORDERS = {
    "civitai_archive_sqlite": ["civitai_api", "civarchive_api", "sqlite"],
    "civitai_sqlite_archive": ["civitai_api", "sqlite", "civarchive_api"],
}

async def initialize_metadata_providers():
    """Initialize and configure all metadata providers based on settings"""
    provider_manager = await ModelMetadataProviderManager.get_instance()
    
    # Clear existing providers to allow reinitialization
    provider_manager.providers.clear()
    provider_manager.default_provider = None
    
    # Get settings
    settings_manager = get_settings_manager()
    enable_archive_db = settings_manager.get('enable_metadata_archive_db', False)
    enable_civarchive_api = settings_manager.get('enable_civarchive_api', True)
    provider_order = settings_manager.get('metadata_provider_order', 'civitai_archive_sqlite')

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
                logger.info("Automatically disabling enable_metadata_archive_db setting")
                settings_manager.set('enable_metadata_archive_db', False)
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

    # Register CivArchive provider when enabled. Civitai API is always
    # preferred (better metadata); CivArchive mainly recovers metadata for
    # models deleted from Civitai, so it can be turned off to avoid its long
    # rate-limit windows entirely.
    if enable_civarchive_api:
        try:
            civarchive_client = await ServiceRegistry.get_civarchive_client()
            civarchive_provider = CivArchiveModelMetadataProvider(civarchive_client)
            provider_manager.register_provider('civarchive_api', civarchive_provider)
            providers.append(('civarchive_api', civarchive_provider))
            logger.debug("CivArchive metadata provider registered (also included in fallback)")
        except Exception as e:
            logger.error(f"Failed to initialize CivArchive metadata provider: {e}")
    else:
        logger.debug("CivArchive metadata provider disabled by setting 'enable_civarchive_api'")

    # Preset fallback orderings (see module-level _PRESET_PROVIDER_ORDERS).
    # civitai_api is always first (better metadata); the remaining providers
    # are arranged by the configured preset.  Providers that are not
    # registered (disabled/unavailable) are simply skipped, so each preset
    # degrades gracefully.
    desired_order = _PRESET_PROVIDER_ORDERS.get(
        provider_order, _PRESET_PROVIDER_ORDERS["civitai_archive_sqlite"]
    )

    # Set up fallback provider based on available providers
    if len(providers) > 1:
        ordered_providers: list[tuple[str, ModelMetadataProvider]] = []
        for name in desired_order:
            ordered_providers.extend([p for p in providers if p[0] == name])
        # Include any provider not covered by the preset (defensive) at the end
        for p in providers:
            if p not in ordered_providers:
                ordered_providers.append(p)

        if ordered_providers:
            fallback_provider = FallbackMetadataProvider(ordered_providers)
            provider_manager.register_provider('fallback', fallback_provider, is_default=True)
            logger.debug(
                "Metadata fallback provider order: %s",
                ", ".join(name for name, _ in ordered_providers),
            )
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
        enable_civarchive_api = settings_manager.get('enable_civarchive_api', True)
        provider_order = settings_manager.get('metadata_provider_order', 'civitai_archive_sqlite')
        
        # Reinitialize all providers with new settings
        provider_manager = await initialize_metadata_providers()
        
        # Build effective provider chain for logging (use actually-registered
        # providers, not just settings, so a failed init is reflected correctly)
        registered = set(provider_manager.providers.keys())
        desired = _PRESET_PROVIDER_ORDERS.get(
            provider_order, _PRESET_PROVIDER_ORDERS["civitai_archive_sqlite"]
        )
        chain = " → ".join(
            _PROVIDER_DISPLAY_NAMES[p]
            for p in desired
            if p in registered and p in _PROVIDER_DISPLAY_NAMES
        )
        
        logger.info(
            "Updated metadata providers: archive_db=%s, civarchive_api=%s, chain=%s",
            enable_archive_db,
            enable_civarchive_api,
            chain,
        )
        return provider_manager
    except Exception as e:
        logger.error(f"Failed to update metadata providers: {e}")
        return await ModelMetadataProviderManager.get_instance()

async def get_metadata_archive_manager():
    """Get metadata archive manager instance"""
    base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return MetadataArchiveManager(base_path)

def _wrap_provider_with_rate_limit(provider_name: str | None, provider: ModelMetadataProvider) -> ModelMetadataProvider:
    if isinstance(provider, (FallbackMetadataProvider, RateLimitRetryingProvider)):
        return provider
    return RateLimitRetryingProvider(provider, label=provider_name)


async def get_metadata_provider(provider_name: str = None):
    """Get a specific metadata provider or default provider with rate-limit handling."""

    provider_manager = await ModelMetadataProviderManager.get_instance()

    try:
        provider = (
            provider_manager._get_provider(provider_name)
            if provider_name
            else provider_manager._get_provider()
        )
    except ValueError as e:
        # Provider not initialized, attempt to initialize
        if "No default provider set" in str(e) or "not registered" in str(e):
            logger.warning(f"Metadata provider not initialized ({e}), initializing now...")
            await initialize_metadata_providers()
            provider_manager = await ModelMetadataProviderManager.get_instance()
            provider = (
                provider_manager._get_provider(provider_name)
                if provider_name
                else provider_manager._get_provider()
            )
        else:
            raise

    return _wrap_provider_with_rate_limit(provider_name, provider)

async def get_default_metadata_provider():
    """Get the default metadata provider (fallback or single provider)"""
    return await get_metadata_provider()
