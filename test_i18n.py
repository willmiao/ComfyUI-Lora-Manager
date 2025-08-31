#!/usr/bin/env python3
"""
Test script to verify the updated i18n system works correctly.
This tests both JavaScript loading and Python server-side functionality.
"""

import os
import sys
import json
import re
import asyncio
import glob
from typing import Set, List, Dict

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_json_files_exist():
    """Test that all JSON locale files exist and are valid JSON."""
    print("Testing JSON locale files...")
    return test_json_structure_validation()

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
    
    en_keys = get_all_translation_keys(en_data)
    print(f"English has {len(en_keys)} translation keys")
    
    # Check other languages
    locales = ['zh-CN', 'zh-TW', 'ja', 'ru', 'de', 'fr', 'es', 'ko']
    
    for locale in locales:
        with open(os.path.join(locales_dir, f'{locale}.json'), 'r', encoding='utf-8') as f:
            locale_data = json.load(f)
        
        locale_keys = get_all_translation_keys(locale_data)
        
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


def extract_i18n_keys_from_js(file_path: str) -> Set[str]:
    """Extract translation keys from JavaScript files."""
    keys = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove comments to avoid false positives
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Pattern for translate() function calls - more specific
        # Matches: translate('key.name', ...) or translate("key.name", ...)
        # Must have opening parenthesis immediately after translate
        translate_pattern = r"\btranslate\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"]"
        translate_matches = re.findall(translate_pattern, content)
        
        # Filter out single words that are likely not translation keys
        # Translation keys should typically have dots or be in specific namespaces
        filtered_translate = [key for key in translate_matches if '.' in key or key in [
            'loading', 'error', 'success', 'warning', 'info', 'cancel', 'save', 'delete'
        ]]
        keys.update(filtered_translate)
        
        # Pattern for showToast() function calls - more specific
        # Matches: showToast('key.name', ...) or showToast("key.name", ...)
        showtoast_pattern = r"\bshowToast\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"]"
        showtoast_matches = re.findall(showtoast_pattern, content)
        
        # Filter showToast matches as well
        filtered_showtoast = [key for key in showtoast_matches if '.' in key or key in [
            'loading', 'error', 'success', 'warning', 'info', 'cancel', 'save', 'delete'
        ]]
        keys.update(filtered_showtoast)
        
        # Additional patterns for other i18n function calls you might have
        # Pattern for t() function calls (if used in JavaScript)
        t_pattern = r"\bt\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"]"
        t_matches = re.findall(t_pattern, content)
        filtered_t = [key for key in t_matches if '.' in key or key in [
            'loading', 'error', 'success', 'warning', 'info', 'cancel', 'save', 'delete'
        ]]
        keys.update(filtered_t)
        
    except Exception as e:
        print(f"⚠️  Error reading {file_path}: {e}")
    
    return keys


def extract_i18n_keys_from_html(file_path: str) -> Set[str]:
    """Extract translation keys from HTML template files."""
    keys = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove HTML comments to avoid false positives
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        
        # Pattern for t() function calls in Jinja2 templates
        # Matches: {{ t('key.name') }} or {% ... t('key.name') ... %}
        # More specific pattern that ensures we're in template context
        t_pattern = r"(?:\{\{|\{%)[^}]*\bt\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"][^}]*(?:\}\}|%\})"
        t_matches = re.findall(t_pattern, content)
        
        # Filter HTML matches
        filtered_t = [key for key in t_matches if '.' in key or key in [
            'loading', 'error', 'success', 'warning', 'info', 'cancel', 'save', 'delete'
        ]]
        keys.update(filtered_t)
        
        # Also check for translate() calls in script tags within HTML
        script_pattern = r'<script[^>]*>(.*?)</script>'
        script_matches = re.findall(script_pattern, content, flags=re.DOTALL)
        for script_content in script_matches:
            # Apply JavaScript extraction to script content
            translate_pattern = r"\btranslate\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"]"
            script_translate_matches = re.findall(translate_pattern, script_content)
            filtered_script = [key for key in script_translate_matches if '.' in key]
            keys.update(filtered_script)
        
    except Exception as e:
        print(f"⚠️  Error reading {file_path}: {e}")
    
    return keys


def get_all_translation_keys(data: dict, prefix: str = '') -> Set[str]:
    """Recursively get all translation keys from nested dictionary."""
    keys = set()
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        keys.add(full_key)
        if isinstance(value, dict):
            keys.update(get_all_translation_keys(value, full_key))
    return keys


def test_static_code_analysis():
    """Test static code analysis to detect missing translation keys."""
    print("\nTesting static code analysis for translation keys...")
    
    # Load English translations as reference
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    with open(os.path.join(locales_dir, 'en.json'), 'r', encoding='utf-8') as f:
        en_data = json.load(f)
    
    available_keys = get_all_translation_keys(en_data)
    print(f"Available translation keys in en.json: {len(available_keys)}")
    
    # Known false positives to exclude from analysis
    # These are typically HTML attributes, CSS classes, or other non-translation strings
    false_positives = {
        'checkpoint', 'civitai_api_key', 'div', 'embedding', 'lora', 'show_only_sfw',
        'model', 'type', 'name', 'value', 'id', 'class', 'style', 'src', 'href',
        'data', 'width', 'height', 'size', 'format', 'version', 'url', 'path',
        'file', 'folder', 'image', 'text', 'number', 'boolean', 'array', 'object'
    }
    
    # Extract keys from JavaScript files
    js_dir = os.path.join(os.path.dirname(__file__), 'static', 'js')
    js_files = []
    if os.path.exists(js_dir):
        # Recursively find all JS files
        for root, dirs, files in os.walk(js_dir):
            for file in files:
                if file.endswith('.js'):
                    js_files.append(os.path.join(root, file))
    
    js_keys = set()
    js_files_with_keys = []
    for js_file in js_files:
        file_keys = extract_i18n_keys_from_js(js_file)
        # Filter out false positives
        file_keys = file_keys - false_positives
        js_keys.update(file_keys)
        if file_keys:
            rel_path = os.path.relpath(js_file, os.path.dirname(__file__))
            js_files_with_keys.append((rel_path, len(file_keys)))
            print(f"  Found {len(file_keys)} keys in {rel_path}")
    
    print(f"Total unique keys found in JavaScript files: {len(js_keys)}")
    
    # Extract keys from HTML template files
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    html_files = []
    if os.path.exists(templates_dir):
        html_files = glob.glob(os.path.join(templates_dir, '*.html'))
        # Also check for HTML files in subdirectories
        html_files.extend(glob.glob(os.path.join(templates_dir, '**', '*.html'), recursive=True))
    
    html_keys = set()
    html_files_with_keys = []
    for html_file in html_files:
        file_keys = extract_i18n_keys_from_html(html_file)
        # Filter out false positives
        file_keys = file_keys - false_positives
        html_keys.update(file_keys)
        if file_keys:
            rel_path = os.path.relpath(html_file, os.path.dirname(__file__))
            html_files_with_keys.append((rel_path, len(file_keys)))
            print(f"  Found {len(file_keys)} keys in {rel_path}")
    
    print(f"Total unique keys found in HTML templates: {len(html_keys)}")
    
    # Combine all used keys
    all_used_keys = js_keys.union(html_keys)
    print(f"Total unique keys used in code: {len(all_used_keys)}")
    
    # Check for missing keys
    missing_keys = all_used_keys - available_keys
    unused_keys = available_keys - all_used_keys
    
    success = True
    
    if missing_keys:
        print(f"\n❌ Found {len(missing_keys)} missing translation keys:")
        for key in sorted(missing_keys):
            print(f"   - {key}")
        success = False
        
        # Group missing keys by category for better analysis
        key_categories = {}
        for key in missing_keys:
            category = key.split('.')[0] if '.' in key else 'root'
            if category not in key_categories:
                key_categories[category] = []
            key_categories[category].append(key)
        
        print(f"\n   Missing keys by category:")
        for category, keys in sorted(key_categories.items()):
            print(f"     {category}: {len(keys)} keys")
            
        # Provide helpful suggestion
        print(f"\n💡 If these are false positives, add them to the false_positives set in test_static_code_analysis()")
    else:
        print("\n✅ All translation keys used in code are available in en.json")
    
    if unused_keys:
        print(f"\n⚠️  Found {len(unused_keys)} unused translation keys in en.json:")
        # Only show first 20 to avoid cluttering output
        for key in sorted(unused_keys)[:20]:
            print(f"   - {key}")
        if len(unused_keys) > 20:
            print(f"   ... and {len(unused_keys) - 20} more")

        # Group unused keys by category for better analysis
        unused_categories = {}
        for key in unused_keys:
            category = key.split('.')[0] if '.' in key else 'root'
            if category not in unused_categories:
                unused_categories[category] = []
            unused_categories[category].append(key)
        
        print(f"\n   Unused keys by category:")
        for category, keys in sorted(unused_categories.items()):
            print(f"     {category}: {len(keys)} keys")
    
    # Summary statistics
    print(f"\n📊 Static Code Analysis Summary:")
    print(f"   JavaScript files analyzed: {len(js_files)}")
    print(f"   JavaScript files with translations: {len(js_files_with_keys)}")
    print(f"   HTML template files analyzed: {len(html_files)}")
    print(f"   HTML template files with translations: {len(html_files_with_keys)}")
    print(f"   Translation keys in en.json: {len(available_keys)}")
    print(f"   Translation keys used in code: {len(all_used_keys)}")
    print(f"   Usage coverage: {len(all_used_keys)/len(available_keys)*100:.1f}%")
    
    return success


def test_json_structure_validation():
    """Test JSON file structure and syntax validation."""
    print("\nTesting JSON file structure and syntax validation...")
    
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    if not os.path.exists(locales_dir):
        print("❌ Locales directory does not exist!")
        return False
    
    expected_locales = ['en', 'zh-CN', 'zh-TW', 'ja', 'ru', 'de', 'fr', 'es', 'ko']
    success = True
    
    for locale in expected_locales:
        file_path = os.path.join(locales_dir, f'{locale}.json')
        if not os.path.exists(file_path):
            print(f"❌ {locale}.json does not exist!")
            success = False
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check for valid JSON structure
            if not isinstance(data, dict):
                print(f"❌ {locale}.json root must be an object/dictionary")
                success = False
                continue
            
            # Check that required sections exist
            required_sections = ['common', 'header', 'loras', 'recipes', 'modals']
            missing_sections = []
            for section in required_sections:
                if section not in data:
                    missing_sections.append(section)
            
            if missing_sections:
                print(f"❌ {locale}.json missing required sections: {', '.join(missing_sections)}")
                success = False
            
            # Check for empty values
            empty_values = []
            def check_empty_values(obj, path=''):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        current_path = f"{path}.{key}" if path else key
                        if isinstance(value, dict):
                            check_empty_values(value, current_path)
                        elif isinstance(value, str) and not value.strip():
                            empty_values.append(current_path)
                        elif value is None:
                            empty_values.append(current_path)
            
            check_empty_values(data)
            
            if empty_values:
                print(f"⚠️  {locale}.json has {len(empty_values)} empty translation values:")
                for path in empty_values[:5]:  # Show first 5
                    print(f"   - {path}")
                if len(empty_values) > 5:
                    print(f"   ... and {len(empty_values) - 5} more")
            
            print(f"✅ {locale}.json structure is valid")
            
        except json.JSONDecodeError as e:
            print(f"❌ {locale}.json has invalid JSON syntax: {e}")
            success = False
        except Exception as e:
            print(f"❌ Error validating {locale}.json: {e}")
            success = False
    
    return success

def main():
    """Run all tests."""
    print("🚀 Testing updated i18n system...\n")
    
    success = True
    
    # Test JSON files structure and syntax
    if not test_json_files_exist():
        success = False
    
    # Test server i18n
    if not test_server_i18n():
        success = False
    
    # Test translation completeness
    if not test_translation_completeness():
        success = False
    
    # Test static code analysis
    if not test_static_code_analysis():
        success = False
    
    print(f"\n{'🎉 All tests passed!' if success else '❌ Some tests failed!'}")
    return success

if __name__ == '__main__':
    main()
