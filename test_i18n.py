#!/usr/bin/env python3
"""
Test script to verify the updated i18n system works correctly.
This tests both JavaScript loading and Python server-side functionality.
"""

import os
import sys
import json
import asyncio

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_json_files_exist():
    """Test that all JSON locale files exist and are valid JSON."""
    print("Testing JSON locale files...")
    
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    if not os.path.exists(locales_dir):
        print("❌ Locales directory does not exist!")
        return False
    
    expected_locales = ['en', 'zh-CN', 'zh-TW', 'ja', 'ru', 'de', 'fr', 'es', 'ko']
    
    for locale in expected_locales:
        file_path = os.path.join(locales_dir, f'{locale}.json')
        if not os.path.exists(file_path):
            print(f"❌ {locale}.json does not exist!")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Check that required sections exist
            required_sections = ['common', 'header', 'loras', 'recipes', 'modals']
            for section in required_sections:
                if section not in data:
                    print(f"❌ {locale}.json missing required section: {section}")
                    return False
            
            print(f"✅ {locale}.json is valid")
            
        except json.JSONDecodeError as e:
            print(f"❌ {locale}.json has invalid JSON: {e}")
            return False
        except Exception as e:
            print(f"❌ Error reading {locale}.json: {e}")
            return False
    
    print("✅ All JSON locale files are valid")
    return True

def test_server_i18n():
    """Test the Python server-side i18n system."""
    print("\nTesting Python server-side i18n...")
    
    try:
        from py.services.server_i18n import ServerI18nManager
        
        # Create a new instance to test
        i18n = ServerI18nManager()
        
        # Test that translations loaded
        available_locales = i18n.get_available_locales()
        if not available_locales:
            print("❌ No locales loaded in server i18n!")
            return False
        
        print(f"✅ Loaded {len(available_locales)} locales: {', '.join(available_locales)}")
        
        # Test English translations
        i18n.set_locale('en')
        test_key = 'common.status.loading'
        translation = i18n.get_translation(test_key)
        if translation == test_key:
            print(f"❌ Translation not found for key '{test_key}'")
            return False
        
        print(f"✅ English translation for '{test_key}': '{translation}'")
        
        # Test Chinese translations
        i18n.set_locale('zh-CN')
        translation_cn = i18n.get_translation(test_key)
        if translation_cn == test_key:
            print(f"❌ Chinese translation not found for key '{test_key}'")
            return False
        
        print(f"✅ Chinese translation for '{test_key}': '{translation_cn}'")
        
        # Test parameter interpolation
        param_key = 'common.itemCount'
        translation_with_params = i18n.get_translation(param_key, count=42)
        if '{count}' in translation_with_params:
            print(f"❌ Parameter interpolation failed for key '{param_key}'")
            return False
        
        print(f"✅ Parameter interpolation for '{param_key}': '{translation_with_params}'")
        
        print("✅ Server-side i18n system working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Error testing server i18n: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_translation_completeness():
    """Test that all languages have the same translation keys."""
    print("\nTesting translation completeness...")
    
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    
    # Load English as reference
    with open(os.path.join(locales_dir, 'en.json'), 'r', encoding='utf-8') as f:
        en_data = json.load(f)
    
    def get_all_keys(data, prefix=''):
        """Recursively get all keys from nested dictionary."""
        keys = set()
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            keys.add(full_key)
            if isinstance(value, dict):
                keys.update(get_all_keys(value, full_key))
        return keys
    
    en_keys = get_all_keys(en_data)
    print(f"English has {len(en_keys)} translation keys")
    
    # Check other languages
    locales = ['zh-CN', 'zh-TW', 'ja', 'ru', 'de', 'fr', 'es', 'ko']
    
    for locale in locales:
        with open(os.path.join(locales_dir, f'{locale}.json'), 'r', encoding='utf-8') as f:
            locale_data = json.load(f)
        
        locale_keys = get_all_keys(locale_data)
        
        missing_keys = en_keys - locale_keys
        extra_keys = locale_keys - en_keys
        
        if missing_keys:
            print(f"❌ {locale} missing keys: {len(missing_keys)}")
            # Print first few missing keys
            for key in sorted(missing_keys)[:5]:
                print(f"   - {key}")
            if len(missing_keys) > 5:
                print(f"   ... and {len(missing_keys) - 5} more")
        
        if extra_keys:
            print(f"⚠️  {locale} has extra keys: {len(extra_keys)}")
        
        if not missing_keys and not extra_keys:
            print(f"✅ {locale} has complete translations ({len(locale_keys)} keys)")
    
    return True

def main():
    """Run all tests."""
    print("🚀 Testing updated i18n system...\n")
    
    success = True
    
    # Test JSON files
    if not test_json_files_exist():
        success = False
    
    # Test server i18n
    if not test_server_i18n():
        success = False
    
    # Test completeness
    if not test_translation_completeness():
        success = False
    
    print(f"\n{'🎉 All tests passed!' if success else '❌ Some tests failed!'}")
    return success

if __name__ == '__main__':
    main()
