import os
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class SettingsManager:
    def __init__(self):
        self.settings_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'settings.json')
        self.settings = self._load_settings()
        self._migrate_download_path_template()
        self._auto_set_default_roots()
        self._check_environment_variables()

    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
        return self._get_default_settings()

    def _migrate_download_path_template(self):
        """Migrate old download_path_template to new download_path_templates"""
        old_template = self.settings.get('download_path_template')
        templates = self.settings.get('download_path_templates')
        
        # If old template exists and new templates don't exist, migrate
        if old_template is not None and not templates:
            logger.info("Migrating download_path_template to download_path_templates")
            self.settings['download_path_templates'] = {
                'lora': old_template,
                'checkpoint': old_template,
                'embedding': old_template
            }
            # Remove old setting
            del self.settings['download_path_template']
            self._save_settings()
            logger.info("Migration completed")

    def _auto_set_default_roots(self):
        """Auto set default root paths if only one folder is present and default is empty."""
        folder_paths = self.settings.get('folder_paths', {})
        updated = False
        # loras
        loras = folder_paths.get('loras', [])
        if isinstance(loras, list) and len(loras) == 1 and not self.settings.get('default_lora_root'):
            self.settings['default_lora_root'] = loras[0]
            updated = True
        # checkpoints
        checkpoints = folder_paths.get('checkpoints', [])
        if isinstance(checkpoints, list) and len(checkpoints) == 1 and not self.settings.get('default_checkpoint_root'):
            self.settings['default_checkpoint_root'] = checkpoints[0]
            updated = True
        # embeddings
        embeddings = folder_paths.get('embeddings', [])
        if isinstance(embeddings, list) and len(embeddings) == 1 and not self.settings.get('default_embedding_root'):
            self.settings['default_embedding_root'] = embeddings[0]
            updated = True
        if updated:
            self._save_settings()

    def _check_environment_variables(self) -> None:
        """Check for environment variables and update settings if needed"""
        env_api_key = os.environ.get('CIVITAI_API_KEY')
        if env_api_key:  # Check if the environment variable exists and is not empty
            logger.info("Found CIVITAI_API_KEY environment variable")
            # Always use the environment variable if it exists
            self.settings['civitai_api_key'] = env_api_key
            self._save_settings()

    def refresh_environment_variables(self) -> None:
        """Refresh settings from environment variables"""
        self._check_environment_variables()

    def _get_default_settings(self) -> Dict[str, Any]:
        """Return default settings"""
        return {
            "civitai_api_key": "",
            "language": "en",
            "show_only_sfw": False,  # Show only SFW content
            "enable_metadata_archive_db": False,  # Enable metadata archive database
            "proxy_enabled": False,  # Enable app-level proxy
            "proxy_host": "",  # Proxy host
            "proxy_port": "",  # Proxy port  
            "proxy_username": "",  # Proxy username (optional)
            "proxy_password": "",  # Proxy password (optional)
            "proxy_type": "http"  # Proxy type: http, https, socks4, socks5
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value"""
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set setting value and save"""
        self.settings[key] = value
        self._save_settings()

    def delete(self, key: str) -> None:
        """Delete setting key and save"""
        if key in self.settings:
            del self.settings[key]
            self._save_settings()
            logger.info(f"Deleted setting: {key}")

    def _save_settings(self) -> None:
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

    def get_download_path_template(self, model_type: str) -> str:
        """Get download path template for specific model type
        
        Args:
            model_type: The type of model ('lora', 'checkpoint', 'embedding')
            
        Returns:
            Template string for the model type, defaults to '{base_model}/{first_tag}'
        """
        templates = self.settings.get('download_path_templates', {})
        
        # Handle edge case where templates might be stored as JSON string
        if isinstance(templates, str):
            try:
                # Try to parse JSON string
                parsed_templates = json.loads(templates)
                if isinstance(parsed_templates, dict):
                    # Update settings with parsed dictionary
                    self.settings['download_path_templates'] = parsed_templates
                    self._save_settings()
                    templates = parsed_templates
                    logger.info("Successfully parsed download_path_templates from JSON string")
                else:
                    raise ValueError("Parsed JSON is not a dictionary")
            except (json.JSONDecodeError, ValueError) as e:
                # If parsing fails, set default values
                logger.warning(f"Failed to parse download_path_templates JSON string: {e}. Setting default values.")
                default_template = '{base_model}/{first_tag}'
                templates = {
                    'lora': default_template,
                    'checkpoint': default_template,
                    'embedding': default_template
                }
                self.settings['download_path_templates'] = templates
                self._save_settings()
        
        # Ensure templates is a dictionary
        if not isinstance(templates, dict):
            default_template = '{base_model}/{first_tag}'
            templates = {
                'lora': default_template,
                'checkpoint': default_template,
                'embedding': default_template
            }
            self.settings['download_path_templates'] = templates
            self._save_settings()
        
        return templates.get(model_type, '{base_model}/{first_tag}')

settings = SettingsManager()
