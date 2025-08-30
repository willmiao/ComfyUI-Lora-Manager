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
        """Load all translation files from the static/js/i18n directory"""
        i18n_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            'static', 'js', 'i18n', 'locales'
        )
        
        if not os.path.exists(i18n_path):
            logger.warning(f"I18n directory not found: {i18n_path}")
            return
        
        # Load all available locale files
        for filename in os.listdir(i18n_path):
            if filename.endswith('.js'):
                locale_code = filename[:-3]  # Remove .js extension
                try:
                    self._load_locale_file(i18n_path, filename, locale_code)
                except Exception as e:
                    logger.error(f"Error loading locale file {filename}: {e}")
    
    def _load_locale_file(self, path: str, filename: str, locale_code: str):
        """Load a single locale file and extract translation data"""
        file_path = os.path.join(path, filename)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Look for export const pattern like: export const en = { ... }
            import re
            
            # Extract the variable name and object
            export_pattern = r'export\s+const\s+(\w+)\s*=\s*(\{.*\});?\s*$'
            match = re.search(export_pattern, content, re.DOTALL | re.MULTILINE)
            
            if not match:
                logger.warning(f"No export const found in {filename}")
                return
            
            var_name = match.group(1)
            js_object = match.group(2)
            
            # Convert JS object to JSON
            json_str = self._js_object_to_json(js_object)
            
            # Parse as JSON
            translations = json.loads(json_str)
            self.translations[locale_code] = translations
            
            logger.debug(f"Loaded translations for {locale_code} (variable: {var_name})")
            
        except Exception as e:
            logger.error(f"Error parsing locale file {filename}: {e}")
    
    def _js_object_to_json(self, js_obj: str) -> str:
        """Convert JavaScript object to JSON string"""
        import re
        
        # Remove comments (single line and multi-line)
        js_obj = re.sub(r'//.*?$', '', js_obj, flags=re.MULTILINE)
        js_obj = re.sub(r'/\*.*?\*/', '', js_obj, flags=re.DOTALL)
        
        # Replace unquoted object keys with quoted keys
        js_obj = re.sub(r'(\s*)([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'\1"\2":', js_obj)
        
        # Handle strings more robustly using regex
        # First, find all single-quoted strings and replace them with double-quoted ones
        def replace_single_quotes(match):
            content = match.group(1)
            # Escape any double quotes in the content
            content = content.replace('"', '\\"')
            # Handle escaped single quotes
            content = content.replace("\\'", "'")
            return f'"{content}"'
        
        # Replace single-quoted strings with double-quoted strings
        js_obj = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", replace_single_quotes, js_obj)
        
        return js_obj
    
    def set_locale(self, locale: str):
        """Set the current locale"""
        if locale in self.translations:
            self.current_locale = locale
        else:
            logger.warning(f"Locale {locale} not found, using 'en'")
            self.current_locale = 'en'
    
    def get_translation(self, key: str, params: Dict[str, Any] = None) -> str:
        """Get translation for a key with optional parameters"""
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
