"""
Configuration for controlling architecture migration and rollback
"""
import logging

logger = logging.getLogger(__name__)


class ArchitectureConfig:
    """Configuration for managing architecture migration"""
    
    def __init__(self):
        """Initialize architecture configuration"""
        # Migration settings
        self.use_new_architecture = True
        self.rollback_on_error = False
        
        # Model type specific settings
        self.model_type_configs = {
            'lora': {
                'use_new_controller': True,
                'fallback_to_legacy': False
            },
            'checkpoint': {
                'use_new_controller': True,
                'fallback_to_legacy': False
            },
            'embedding': {
                'use_new_controller': True,
                'fallback_to_legacy': False
            }
        }
        
        # Debug settings
        self.debug_mode = False
        self.log_performance_metrics = False
    
    def should_use_new_controller(self, model_type: str) -> bool:
        """Check if should use new controller for a model type
        
        Args:
            model_type: The model type to check
            
        Returns:
            bool: True if should use new controller
        """
        if not self.use_new_architecture:
            return False
        
        config = self.model_type_configs.get(model_type, {})
        return config.get('use_new_controller', False)
    
    def should_fallback_to_legacy(self, model_type: str) -> bool:
        """Check if should fallback to legacy routes on error
        
        Args:
            model_type: The model type to check
            
        Returns:
            bool: True if should fallback to legacy
        """
        config = self.model_type_configs.get(model_type, {})
        return config.get('fallback_to_legacy', False)
    
    def enable_selective_rollback(self, model_type: str):
        """Enable rollback for a specific model type
        
        Args:
            model_type: The model type to rollback
        """
        if model_type in self.model_type_configs:
            self.model_type_configs[model_type]['use_new_controller'] = False
            logger.info(f"Rolled back {model_type} to legacy architecture")
    
    def enable_selective_migration(self, model_type: str):
        """Enable new architecture for a specific model type
        
        Args:
            model_type: The model type to migrate
        """
        if model_type in self.model_type_configs:
            self.model_type_configs[model_type]['use_new_controller'] = True
            logger.info(f"Migrated {model_type} to new architecture")
    
    def get_migration_status(self) -> dict:
        """Get current migration status
        
        Returns:
            dict: Migration status for all model types
        """
        status = {}
        for model_type, config in self.model_type_configs.items():
            status[model_type] = {
                'using_new_controller': config.get('use_new_controller', False),
                'fallback_enabled': config.get('fallback_to_legacy', False)
            }
        return status


# Global architecture configuration
arch_config = ArchitectureConfig()


def get_architecture_config() -> ArchitectureConfig:
    """Get the global architecture configuration
    
    Returns:
        ArchitectureConfig: The global configuration
    """
    return arch_config
