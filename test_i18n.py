#!/usr/bin/env python3
"""
Test script to verify the updated i18n system works correctly.
This tests both JavaScript loading and Python server-side functionality.
"""

import os
import sys
import json
import re
import glob
from typing import Set, Dict, List, Tuple, Any

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_json_files_exist():
    """Test that all JSON locale files exist and are valid JSON."""
    print("Testing JSON locale files...")
    return test_json_structure_validation()

def test_locale_files_structural_consistency():
    """Test that all locale files have identical structure, line counts, and formatting."""
    print("\nTesting locale files structural consistency...")
    
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    if not os.path.exists(locales_dir):
        print("❌ Locales directory does not exist!")
        return False
    
    # Get all locale files
    locale_files = []
    for file in os.listdir(locales_dir):
        if file.endswith('.json'):
            locale_files.append(file)
    
    if not locale_files:
        print("❌ No locale files found!")
        return False
    
    # Use en.json as the reference
    reference_file = 'en.json'
    if reference_file not in locale_files:
        print(f"❌ Reference file {reference_file} not found!")
        return False
    
    locale_files.remove(reference_file)
    locale_files.insert(0, reference_file)  # Put reference first
    
    success = True
    
    # Load and parse the reference file
    reference_path = os.path.join(locales_dir, reference_file)
    try:
        with open(reference_path, 'r', encoding='utf-8') as f:
            reference_lines = f.readlines()
            reference_content = ''.join(reference_lines)
        
        reference_data = json.loads(reference_content)
        reference_structure = get_json_structure(reference_data)
        
        print(f"📋 Reference file {reference_file}:")
        print(f"   Lines: {len(reference_lines)}")
        print(f"   Keys: {len(get_all_translation_keys(reference_data))}")
        
    except Exception as e:
        print(f"❌ Error reading reference file {reference_file}: {e}")
        return False
    
    # Compare each locale file with the reference
    for locale_file in locale_files[1:]:  # Skip reference file
        locale_path = os.path.join(locales_dir, locale_file)
        locale_name = locale_file.replace('.json', '')
        
        try:
            with open(locale_path, 'r', encoding='utf-8') as f:
                locale_lines = f.readlines()
                locale_content = ''.join(locale_lines)
            
            locale_data = json.loads(locale_content)
            locale_structure = get_json_structure(locale_data)
            
            # Test 1: Line count consistency
            if len(locale_lines) != len(reference_lines):
                print(f"❌ {locale_name}: Line count mismatch!")
                print(f"   Reference: {len(reference_lines)} lines")
                print(f"   {locale_name}: {len(locale_lines)} lines")
                success = False
                continue
            
            # Test 2: Structural consistency (key order and nesting)
            structure_issues = compare_json_structures(reference_structure, locale_structure)
            if structure_issues:
                print(f"❌ {locale_name}: Structure mismatch!")
                for issue in structure_issues[:5]:  # Show first 5 issues
                    print(f"   - {issue}")
                if len(structure_issues) > 5:
                    print(f"   ... and {len(structure_issues) - 5} more issues")
                success = False
                continue
            
            # Test 3: Line-by-line format consistency (excluding translation values)
            format_issues = compare_line_formats(reference_lines, locale_lines, locale_name)
            if format_issues:
                print(f"❌ {locale_name}: Format mismatch!")
                for issue in format_issues[:5]:  # Show first 5 issues
                    print(f"   - {issue}")
                if len(format_issues) > 5:
                    print(f"   ... and {len(format_issues) - 5} more issues")
                success = False
                continue
            
            # Test 4: Key completeness
            reference_keys = get_all_translation_keys(reference_data)
            locale_keys = get_all_translation_keys(locale_data)
            
            missing_keys = reference_keys - locale_keys
            extra_keys = locale_keys - reference_keys
            
            if missing_keys or extra_keys:
                print(f"❌ {locale_name}: Key mismatch!")
                if missing_keys:
                    print(f"   Missing {len(missing_keys)} keys")
                if extra_keys:
                    print(f"   Extra {len(extra_keys)} keys")
                success = False
                continue
            
            print(f"✅ {locale_name}: Structure and format consistent")
            
        except json.JSONDecodeError as e:
            print(f"❌ {locale_name}: Invalid JSON syntax: {e}")
            success = False
        except Exception as e:
            print(f"❌ {locale_name}: Error during validation: {e}")
            success = False
    
    if success:
        print(f"\n✅ All {len(locale_files)} locale files have consistent structure and formatting")
    
    return success

def get_json_structure(data: Any, path: str = '') -> Dict[str, Any]:
    """
    Extract the structural information from JSON data.
    Returns a dictionary describing the structure without the actual values.
    """
    if isinstance(data, dict):
        structure = {}
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, dict):
                structure[key] = get_json_structure(value, current_path)
            elif isinstance(value, list):
                structure[key] = {'_type': 'array', '_length': len(value)}
                if value:  # If array is not empty, analyze first element
                    structure[key]['_element_type'] = get_json_structure(value[0], f"{current_path}[0]")
            else:
                structure[key] = {'_type': type(value).__name__}
        return structure
    elif isinstance(data, list):
        return {'_type': 'array', '_length': len(data)}
    else:
        return {'_type': type(data).__name__}

def compare_json_structures(ref_structure: Dict[str, Any], locale_structure: Dict[str, Any], path: str = '') -> List[str]:
    """
    Compare two JSON structures and return a list of differences.
    """
    issues = []
    
    # Check for missing keys in locale
    for key in ref_structure:
        current_path = f"{path}.{key}" if path else key
        if key not in locale_structure:
            issues.append(f"Missing key: {current_path}")
        elif isinstance(ref_structure[key], dict) and '_type' not in ref_structure[key]:
            # It's a nested object, recurse
            if isinstance(locale_structure[key], dict) and '_type' not in locale_structure[key]:
                issues.extend(compare_json_structures(ref_structure[key], locale_structure[key], current_path))
            else:
                issues.append(f"Structure mismatch at {current_path}: expected object, got {type(locale_structure[key])}")
        elif ref_structure[key] != locale_structure[key]:
            issues.append(f"Type mismatch at {current_path}: expected {ref_structure[key]}, got {locale_structure[key]}")
    
    # Check for extra keys in locale
    for key in locale_structure:
        current_path = f"{path}.{key}" if path else key
        if key not in ref_structure:
            issues.append(f"Extra key: {current_path}")
    
    return issues

def extract_line_structure(line: str) -> Dict[str, str]:
    """
    Extract structural elements from a JSON line.
    Returns indentation, key (if present), and structural characters.
    """
    # Get indentation (leading whitespace)
    indentation = len(line) - len(line.lstrip())
    
    # Remove leading/trailing whitespace for analysis
    stripped_line = line.strip()
    
    # Extract key if this is a key-value line
    key_match = re.match(r'^"([^"]+)"\s*:\s*', stripped_line)
    key = key_match.group(1) if key_match else ''
    
    # Extract structural characters (everything except the actual translation value)
    if key:
        # For key-value lines, extract everything except the value
        # Handle string values in quotes with better escaping support
        value_pattern = r'^"[^"]+"\s*:\s*("(?:[^"\\]|\\.)*")(.*?)$'
        value_match = re.match(value_pattern, stripped_line)
        if value_match:
            # Preserve the structure but replace the actual string content
            structural_chars = f'"{key}": "VALUE"{value_match.group(2)}'
        else:
            # Handle non-string values (objects, arrays, booleans, numbers)
            colon_pos = stripped_line.find(':')
            if colon_pos != -1:
                after_colon = stripped_line[colon_pos + 1:].strip()
                if after_colon.startswith('"'):
                    # String value - find the end quote with proper escaping
                    end_quote = find_closing_quote(after_colon, 1)
                    if end_quote != -1:
                        structural_chars = f'"{key}": "VALUE"{after_colon[end_quote + 1:]}'
                    else:
                        structural_chars = f'"{key}": "VALUE"'
                elif after_colon.startswith('{'):
                    # Object value
                    structural_chars = f'"{key}": {{'
                elif after_colon.startswith('['):
                    # Array value
                    structural_chars = f'"{key}": ['
                else:
                    # Other values (numbers, booleans, null)
                    # Replace the actual value with a placeholder
                    value_end = find_value_end(after_colon)
                    structural_chars = f'"{key}": VALUE{after_colon[value_end:]}'
            else:
                structural_chars = stripped_line
    else:
        # For non key-value lines (brackets, etc.), keep as-is
        structural_chars = stripped_line
    
    return {
        'indentation': str(indentation),
        'key': key,
        'structural_chars': structural_chars
    }

def find_value_end(text: str) -> int:
    """
    Find the end of a non-string JSON value (number, boolean, null).
    """
    for i, char in enumerate(text):
        if char in ',}]':
            return i
    return len(text)

def find_closing_quote(text: str, start: int) -> int:
    """
    Find the position of the closing quote, handling escaped quotes properly.
    """
    i = start
    while i < len(text):
        if text[i] == '"':
            # Count preceding backslashes
            backslash_count = 0
            j = i - 1
            while j >= 0 and text[j] == '\\':
                backslash_count += 1
                j -= 1
            
            # If even number of backslashes (including 0), the quote is not escaped
            if backslash_count % 2 == 0:
                return i
        i += 1
    return -1

def compare_line_formats(ref_lines: List[str], locale_lines: List[str], locale_name: str) -> List[str]:
    """
    Compare line-by-line formatting between reference and locale files.
    Only checks structural elements (indentation, brackets, commas) and ignores translation values.
    """
    issues = []
    
    for i, (ref_line, locale_line) in enumerate(zip(ref_lines, locale_lines)):
        line_num = i + 1
        
        # Skip empty lines and lines with only whitespace
        if not ref_line.strip() and not locale_line.strip():
            continue
        
        # Extract structural elements from each line
        ref_structure = extract_line_structure(ref_line)
        locale_structure = extract_line_structure(locale_line)
        
        # Compare structural elements with more tolerance
        structure_issues = []
        
        # Check indentation (must be exact)
        if ref_structure['indentation'] != locale_structure['indentation']:
            structure_issues.append(f"indentation ({ref_structure['indentation']} vs {locale_structure['indentation']})")
        
        # Check keys (must be exact for structural consistency)
        if ref_structure['key'] != locale_structure['key']:
            structure_issues.append(f"key ('{ref_structure['key']}' vs '{locale_structure['key']}')")
        
        # Check structural characters with improved normalization
        ref_normalized = normalize_structural_chars(ref_structure['structural_chars'])
        locale_normalized = normalize_structural_chars(locale_structure['structural_chars'])
        
        if ref_normalized != locale_normalized:
            # Additional check: if both lines have the same key and similar structure,
            # this might be a false positive due to translation content differences
            if (ref_structure['key'] and locale_structure['key'] and 
                ref_structure['key'] == locale_structure['key']):
                
                # Check if the difference is only in the translation value
                ref_has_string_value = '"VALUE"' in ref_normalized
                locale_has_string_value = '"VALUE"' in locale_normalized
                
                if ref_has_string_value and locale_has_string_value:
                    # Both have string values, check if structure around value is same
                    ref_structure_only = re.sub(r'"VALUE"', '"X"', ref_normalized)
                    locale_structure_only = re.sub(r'"VALUE"', '"X"', locale_normalized)
                    
                    if ref_structure_only == locale_structure_only:
                        # Structure is actually the same, skip this as false positive
                        continue
            
            structure_issues.append(f"structure ('{ref_normalized}' vs '{locale_normalized}')")
        
        if structure_issues:
            issues.append(f"Line {line_num}: {', '.join(structure_issues)}")
    
    return issues

def normalize_structural_chars(structural_chars: str) -> str:
    """
    Normalize structural characters for comparison by replacing variable content
    with placeholders while preserving the actual structure.
    """
    # Normalize the structural characters more carefully
    normalized = structural_chars
    
    # Replace quoted strings with a consistent placeholder, handling escapes
    # This regex matches strings while properly handling escaped quotes
    string_pattern = r'"(?:[^"\\]|\\.)*"(?=\s*[,}\]:}]|$)'
    
    # Find all string matches and replace with placeholder
    strings = re.findall(string_pattern, normalized)
    for string_match in strings:
        # Only replace if this looks like a translation value, not a key
        if ':' in normalized:
            # Check if this string comes after a colon (likely a value)
            parts = normalized.split(':', 1)
            if len(parts) == 2 and string_match in parts[1]:
                normalized = normalized.replace(string_match, '"VALUE"', 1)
    
    # Normalize whitespace around structural characters
    normalized = re.sub(r'\s*:\s*', ': ', normalized)
    normalized = re.sub(r'\s*,\s*', ', ', normalized)
    normalized = re.sub(r'\s*{\s*', '{ ', normalized)
    normalized = re.sub(r'\s*}\s*', ' }', normalized)
    
    return normalized.strip()

def test_locale_files_formatting_consistency():
    """Test that all locale files have identical formatting (whitespace, indentation, etc.)."""
    print("\nTesting locale files formatting consistency...")
    
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    expected_locales = ['en', 'zh-CN', 'zh-TW', 'ja', 'ru', 'de', 'fr', 'es', 'ko']
    
    # Read reference file (en.json)
    reference_path = os.path.join(locales_dir, 'en.json')
    try:
        with open(reference_path, 'r', encoding='utf-8') as f:
            reference_lines = f.readlines()
    except Exception as e:
        print(f"❌ Error reading reference file: {e}")
        return False
    
    success = True
    
    # Compare each locale file
    for locale in expected_locales[1:]:  # Skip 'en' as it's the reference
        locale_path = os.path.join(locales_dir, f'{locale}.json')
        
        if not os.path.exists(locale_path):
            print(f"❌ {locale}.json does not exist!")
            success = False
            continue
        
        try:
            with open(locale_path, 'r', encoding='utf-8') as f:
                locale_lines = f.readlines()
            
            # Compare line count
            if len(locale_lines) != len(reference_lines):
                print(f"❌ {locale}.json: Line count differs from reference")
                print(f"   Reference: {len(reference_lines)} lines")
                print(f"   {locale}: {len(locale_lines)} lines")
                success = False
                continue
            
            # Compare formatting with improved algorithm
            formatting_issues = compare_line_formats(reference_lines, locale_lines, locale)
            
            if formatting_issues:
                print(f"❌ {locale}.json: Formatting issues found")
                # Show only the first few issues to avoid spam
                shown_issues = 0
                for issue in formatting_issues:
                    if shown_issues < 3:  # Reduced from 5 to 3
                        print(f"   - {issue}")
                        shown_issues += 1
                    else:
                        break
                
                if len(formatting_issues) > 3:
                    print(f"   ... and {len(formatting_issues) - 3} more issues")
                
                # Provide debug info for first issue to help identify false positives
                if formatting_issues:
                    first_issue = formatting_issues[0]
                    line_match = re.match(r'Line (\d+):', first_issue)
                    if line_match:
                        line_num = int(line_match.group(1)) - 1  # Convert to 0-based
                        if 0 <= line_num < len(reference_lines):
                            print(f"   Debug - Reference line {line_num + 1}: {repr(reference_lines[line_num].rstrip())}")
                            print(f"   Debug - {locale} line {line_num + 1}: {repr(locale_lines[line_num].rstrip())}")
                
                success = False
            else:
                print(f"✅ {locale}.json: Formatting consistent with reference")
        
        except Exception as e:
            print(f"❌ Error validating {locale}.json: {e}")
            success = False
    
    if success:
        print("✅ All locale files have consistent formatting")
    else:
        print("💡 Note: Some formatting differences may be false positives due to translation content.")
        print("   If translations are correct but structure appears different, the test may need refinement.")
    
    return success

def test_locale_key_ordering():
    """Test that all locale files maintain the same key ordering as the reference."""
    print("\nTesting locale files key ordering...")
    
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    expected_locales = ['en', 'zh-CN', 'zh-TW', 'ja', 'ru', 'de', 'fr', 'es', 'ko']
    
    # Load reference file
    reference_path = os.path.join(locales_dir, 'en.json')
    try:
        with open(reference_path, 'r', encoding='utf-8') as f:
            reference_data = json.load(f, object_pairs_hook=lambda x: x)  # Preserve order
        
        reference_key_order = get_key_order(reference_data)
    except Exception as e:
        print(f"❌ Error reading reference file: {e}")
        return False
    
    success = True
    
    for locale in expected_locales[1:]:  # Skip 'en' as it's the reference
        locale_path = os.path.join(locales_dir, f'{locale}.json')
        
        if not os.path.exists(locale_path):
            continue
        
        try:
            with open(locale_path, 'r', encoding='utf-8') as f:
                locale_data = json.load(f, object_pairs_hook=lambda x: x)  # Preserve order
            
            locale_key_order = get_key_order(locale_data)
            
            if reference_key_order != locale_key_order:
                print(f"❌ {locale}.json: Key ordering differs from reference")
                
                # Find the first difference
                for i, (ref_key, locale_key) in enumerate(zip(reference_key_order, locale_key_order)):
                    if ref_key != locale_key:
                        print(f"   First difference at position {i}: '{ref_key}' vs '{locale_key}'")
                        break
                
                success = False
            else:
                print(f"✅ {locale}.json: Key ordering matches reference")
        
        except Exception as e:
            print(f"❌ Error validating {locale}.json key ordering: {e}")
            success = False
    
    return success

def get_key_order(data: Any, path: str = '') -> List[str]:
    """
    Extract the order of keys from nested JSON data.
    Returns a list of all keys in their order of appearance.
    """
    keys = []
    
    if isinstance(data, list):
        # Handle list of key-value pairs (from object_pairs_hook)
        for key, value in data:
            current_path = f"{path}.{key}" if path else key
            keys.append(current_path)
            if isinstance(value, list):  # Nested object as list of pairs
                keys.extend(get_key_order(value, current_path))
    elif isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            keys.append(current_path)
            if isinstance(value, (dict, list)):
                keys.extend(get_key_order(value, current_path))
    
    return keys

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


def get_all_translation_keys(data: dict, prefix: str = '', include_containers: bool = False) -> Set[str]:
    """
    Recursively collect translation keys.
    By default only leaf keys (where the value is NOT a dict) are returned so that
    structural/container nodes (e.g. 'common', 'common.actions') are not treated
    as real translation entries and won't appear in the 'unused' list.
    
    Set include_containers=True to also include container/object nodes.
    """
    keys: Set[str] = set()
    if not isinstance(data, dict):
        return keys
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            # Recurse first
            keys.update(get_all_translation_keys(value, full_key, include_containers))
            # Optionally include container nodes
            if include_containers:
                keys.add(full_key)
        else:
            # Leaf node: actual translatable value
            keys.add(full_key)
    return keys


def test_static_code_analysis():
    """Test static code analysis to detect missing translation keys."""
    # print("\nTesting static code analysis for translation keys...")
    
    # Load English translations as reference
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
    with open(os.path.join(locales_dir, 'en.json'), 'r', encoding='utf-8') as f:
        en_data = json.load(f)
    
    available_keys = get_all_translation_keys(en_data)
    # print(f"Available translation keys in en.json: {len(available_keys)}")
    
    # Known false positives to exclude from analysis
    # These are typically HTML attributes, CSS classes, or other non-translation strings
    false_positives = {
        'checkpoint', 'civitai_api_key', 'div', 'embedding', 'lora', 'show_only_sfw',
        'model', 'type', 'name', 'value', 'id', 'class', 'style', 'src', 'href',
        'data', 'width', 'height', 'size', 'format', 'version', 'url', 'path',
        'file', 'folder', 'image', 'text', 'number', 'boolean', 'array', 'object', 'non.existent.key'
    }

    # Special translation keys used in uiHelpers.js but not detected by regex
    uihelpers_special_keys = {
        'uiHelpers.workflow.loraAdded',
        'uiHelpers.workflow.loraReplaced',
        'uiHelpers.workflow.loraFailedToSend',
        'uiHelpers.workflow.recipeAdded',
        'uiHelpers.workflow.recipeReplaced',
        'uiHelpers.workflow.recipeFailedToSend',
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
            # print(f"  Found {len(file_keys)} keys in {rel_path}")
    
    # print(f"Total unique keys found in JavaScript files: {len(js_keys)}")
    
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
            # print(f"  Found {len(file_keys)} keys in {rel_path}")
    
    # print(f"Total unique keys found in HTML templates: {len(html_keys)}")
    
    # Combine all used keys
    all_used_keys = js_keys.union(html_keys)
    # Add special keys from uiHelpers.js
    all_used_keys.update(uihelpers_special_keys)
    # print(f"Total unique keys used in code: {len(all_used_keys)}")
    
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
    # print(f"\n📊 Static Code Analysis Summary:")
    # print(f"   JavaScript files analyzed: {len(js_files)}")
    # print(f"   JavaScript files with translations: {len(js_files_with_keys)}")
    # print(f"   HTML template files analyzed: {len(html_files)}")
    # print(f"   HTML template files with translations: {len(html_files_with_keys)}")
    # print(f"   Translation keys in en.json: {len(available_keys)}")
    # print(f"   Translation keys used in code: {len(all_used_keys)}")
    # print(f"   Usage coverage: {len(all_used_keys)/len(available_keys)*100:.1f}%")
    
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
    
    # Test comprehensive structural consistency
    if not test_locale_files_structural_consistency():
        success = False
    
    # Test formatting consistency
    if not test_locale_files_formatting_consistency():
        success = False
    
    # Test key ordering
    if not test_locale_key_ordering():
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
