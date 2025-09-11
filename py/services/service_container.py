"""
Service container for dependency injection and service management
"""
import logging
from typing import Dict, Any, Optional, Type, TypeVar

from ..services.model_metadata_service import ModelMetadataService
from ..services.model_file_service import ModelFileService
from ..services.model_preview_service import ModelPreviewService
from ..services.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ServiceContainer:
    """Container for managing service dependencies and injection"""
    
    def __init__(self):
        """Initialize the service container"""
        self._services: Dict[str, Any] = {}
        self._singletons: Dict[str, Any] = {}
        self._factories: Dict[str, callable] = {}
    
    def register_singleton(self, service_name: str, service_instance: Any) -> None:
        """Register a singleton service instance
        
        Args:
            service_name: Name to register the service under
            service_instance: Service instance to register
        """
        self._singletons[service_name] = service_instance
        logger.debug(f"Registered singleton service: {service_name}")
    
    def register_factory(self, service_name: str, factory_func: callable) -> None:
        """Register a factory function for creating service instances
        
        Args:
            service_name: Name to register the factory under
            factory_func: Function that creates the service instance
        """
        self._factories[service_name] = factory_func
        logger.debug(f"Registered factory for service: {service_name}")
    
    def get_service(self, service_name: str) -> Optional[Any]:
        """Get a service instance by name
        
        Args:
            service_name: Name of the service to retrieve
            
        Returns:
            Service instance or None if not found
        """
        # Check singletons first
        if service_name in self._singletons:
            return self._singletons[service_name]
        
        # Check if we have a factory for this service
        if service_name in self._factories:
            factory = self._factories[service_name]
            instance = factory()
            # Cache as singleton after first creation
            self._singletons[service_name] = instance
            return instance
        
        logger.warning(f"Service not found: {service_name}")
        return None
    
    def get_or_create(self, service_name: str, service_class: Type[T], *args, **kwargs) -> T:
        """Get an existing service or create a new one
        
        Args:
            service_name: Name of the service
            service_class: Class to instantiate if service doesn't exist
            *args: Arguments to pass to the service constructor
            **kwargs: Keyword arguments to pass to the service constructor
            
        Returns:
            Service instance
        """
        service = self.get_service(service_name)
        if service is None:
            service = service_class(*args, **kwargs)
            self.register_singleton(service_name, service)
        return service
    
    def clear(self) -> None:
        """Clear all registered services"""
        self._services.clear()
        self._singletons.clear()
        self._factories.clear()
        logger.info("Cleared all services from container")


class DefaultServiceContainer(ServiceContainer):
    """Default service container with pre-configured common services"""
    
    def __init__(self):
        """Initialize with default services"""
        super().__init__()
        self._setup_default_services()
    
    def _setup_default_services(self):
        """Setup default service registrations"""
        try:
            # Register core services as singletons
            self.register_singleton('metadata_service', ModelMetadataService())
            self.register_singleton('file_service', ModelFileService())
            self.register_singleton('preview_service', ModelPreviewService())
            
            # Register factories for scanner services that need async initialization
            self.register_factory('lora_scanner', self._create_lora_scanner)
            self.register_factory('checkpoint_scanner', self._create_checkpoint_scanner)
            self.register_factory('embedding_scanner', self._create_embedding_scanner)
            
            logger.info("Set up default services in container")
            
        except Exception as e:
            logger.error(f"Error setting up default services: {e}", exc_info=True)
            raise
    
    async def _create_lora_scanner(self):
        """Factory function for LoRA scanner"""
        return await ServiceRegistry.get_lora_scanner()
    
    async def _create_checkpoint_scanner(self):
        """Factory function for Checkpoint scanner"""
        return await ServiceRegistry.get_checkpoint_scanner()
    
    async def _create_embedding_scanner(self):
        """Factory function for Embedding scanner"""
        return await ServiceRegistry.get_embedding_scanner()
    
    def get_metadata_service(self) -> ModelMetadataService:
        """Get the metadata service instance"""
        return self.get_service('metadata_service')
    
    def get_file_service(self) -> ModelFileService:
        """Get the file service instance"""
        return self.get_service('file_service')
    
    def get_preview_service(self) -> ModelPreviewService:
        """Get the preview service instance"""
        return self.get_service('preview_service')
    
    async def get_lora_scanner(self):
        """Get the LoRA scanner instance"""
        scanner = self.get_service('lora_scanner')
        if scanner is None:
            scanner = await self._create_lora_scanner()
            self.register_singleton('lora_scanner', scanner)
        return scanner
    
    async def get_checkpoint_scanner(self):
        """Get the Checkpoint scanner instance"""
        scanner = self.get_service('checkpoint_scanner')
        if scanner is None:
            scanner = await self._create_checkpoint_scanner()
            self.register_singleton('checkpoint_scanner', scanner)
        return scanner
    
    async def get_embedding_scanner(self):
        """Get the Embedding scanner instance"""
        scanner = self.get_service('embedding_scanner')
        if scanner is None:
            scanner = await self._create_embedding_scanner()
            self.register_singleton('embedding_scanner', scanner)
        return scanner


# Global service container instance
default_container = DefaultServiceContainer()


def get_default_container() -> DefaultServiceContainer:
    """Get the default service container instance
    
    Returns:
        DefaultServiceContainer: The global service container
    """
    return default_container


def setup_services_container(container: Optional[ServiceContainer] = None) -> ServiceContainer:
    """Setup the services container
    
    Args:
        container: Optional custom container to use instead of default
        
    Returns:
        ServiceContainer: The configured container
    """
    if container is None:
        container = default_container
    
    logger.info("Services container is ready")
    return container
