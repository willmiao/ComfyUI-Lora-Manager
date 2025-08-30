import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ServerI18nManager:
    """Server-side internationalization manager for template rendering"""
    
    def __init__(self):
        self.translations = {}
        self.current_locale = 'en'
        self._load_translations()
    
    def _load_translations(self):
        """Load all translation files from the locales directory"""
        i18n_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            'locales'
        )
        
        if not os.path.exists(i18n_path):
            logger.warning(f"I18n directory not found: {i18n_path}")
            return
        
        # Load all available locale files
        for filename in os.listdir(i18n_path):
            if filename.endswith('.json'):
                locale_code = filename[:-5]  # Remove .json extension
                try:
                    self._load_locale_file(i18n_path, filename, locale_code)
                except Exception as e:
                    logger.error(f"Error loading locale file {filename}: {e}")
    
    def _load_locale_file(self, path: str, filename: str, locale_code: str):
        """Load a single locale JSON file"""
        file_path = os.path.join(path, filename)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                translations = json.load(f)
                
            self.translations[locale_code] = translations
            logger.debug(f"Loaded translations for {locale_code} from {filename}")
            
        except Exception as e:
            logger.error(f"Error parsing locale file {filename}: {e}")
    
    def set_locale(self, locale: str):
        """Set the current locale"""
        if locale in self.translations:
            self.current_locale = locale
        else:
            logger.warning(f"Locale {locale} not found, using 'en'")
            self.current_locale = 'en'
    
    def get_translation(self, key: str, params: Dict[str, Any] = None, **kwargs) -> str:
        """Get translation for a key with optional parameters (supports both dict and keyword args)"""
        # Merge kwargs into params for convenience
        if params is None:
            params = {}
        if kwargs:
            params = {**params, **kwargs}
        
        if self.current_locale not in self.translations:
            return key
        
        # Navigate through nested object using dot notation
        keys = key.split('.')
        value = self.translations[self.current_locale]
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                # Fallback to English if current locale doesn't have the key
                if self.current_locale != 'en' and 'en' in self.translations:
                    en_value = self.translations['en']
                    for k in keys:
                        if isinstance(en_value, dict) and k in en_value:
                            en_value = en_value[k]
                        else:
                            return key
                    value = en_value
                else:
                    return key
                break
        
        if not isinstance(value, str):
            return key
        
        # Replace parameters if provided
        if params:
            for param_key, param_value in params.items():
                placeholder = f"{{{param_key}}}"
                double_placeholder = f"{{{{{param_key}}}}}"
                value = value.replace(placeholder, str(param_value))
                value = value.replace(double_placeholder, str(param_value))
        
        return value
    
    def get_available_locales(self) -> list:
        """Get list of available locales"""
        return list(self.translations.keys())
    
    def create_template_filter(self):
        """Create a Jinja2 filter function for templates"""
        def t_filter(key: str, **params) -> str:
            return self.get_translation(key, params)
        return t_filter

# Create global instance
server_i18n = ServerI18nManager()
