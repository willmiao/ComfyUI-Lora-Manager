#!/usr/bin/env python3
"""
Translation Key Synchronization Script

This script synchronizes new translation keys from en.json to all other locale files
while maintaining exact formatting consistency to pass test_i18n.py validation.

Features:
- Preserves exact line-by-line formatting
- Maintains proper indentation and structure
- Adds missing keys with placeholder translations
- Handles nested objects correctly
- Ensures all locale files have identical structure

Usage:
    python scripts/sync_translation_keys.py [--dry-run] [--verbose]
"""

import os
import sys
import json
import re
import argparse
from typing import Dict, List, Set, Tuple, Any, Optional
from collections import OrderedDict

# Add the parent directory to the path so we can import modules if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

class TranslationKeySynchronizer:
    """Synchronizes translation keys across locale files while maintaining formatting."""
    
    def __init__(self, locales_dir: str, verbose: bool = False):
        self.locales_dir = locales_dir
        self.verbose = verbose
        self.reference_locale = 'en'
        self.target_locales = ['zh-CN', 'zh-TW', 'ja', 'ru', 'de', 'fr', 'es', 'ko']
        
    def log(self, message: str, level: str = 'INFO'):
        """Log a message if verbose mode is enabled."""
        if self.verbose or level == 'ERROR':
            print(f"[{level}] {message}")
    
    def load_json_preserve_order(self, file_path: str) -> Tuple[Dict[str, Any], List[str]]:
        """
        Load a JSON file preserving the exact order and formatting.
        Returns both the parsed data and the original lines.
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            content = ''.join(lines)
        
        # Parse JSON while preserving order
        data = json.loads(content, object_pairs_hook=OrderedDict)
        return data, lines
    
    def get_all_leaf_keys(self, data: Any, prefix: str = '') -> Dict[str, Any]:
        """
        Extract all leaf keys (non-object values) with their full paths.
        Returns a dictionary mapping full key paths to their values.
        """
        keys = {}
        
        if isinstance(data, (dict, OrderedDict)):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                
                if isinstance(value, (dict, OrderedDict)):
                    # Recursively get nested keys
                    keys.update(self.get_all_leaf_keys(value, full_key))
                else:
                    # Leaf node - actual translatable value
                    keys[full_key] = value
                    
        return keys
    
    def merge_json_structures(self, reference_data: Dict[str, Any], target_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge the reference JSON structure with existing target translations.
        This creates a new structure that matches the reference exactly but preserves 
        existing translations where available. Keys not in reference are removed.
        """
        def merge_recursive(ref_obj, target_obj):
            if isinstance(ref_obj, (dict, OrderedDict)):
                result = OrderedDict()
                # Only include keys that exist in the reference
                for key, ref_value in ref_obj.items():
                    if key in target_obj and isinstance(target_obj[key], type(ref_value)):
                        # Key exists in target with same type
                        if isinstance(ref_value, (dict, OrderedDict)):
                            # Recursively merge nested objects
                            result[key] = merge_recursive(ref_value, target_obj[key])
                        else:
                            # Use existing translation
                            result[key] = target_obj[key]
                    else:
                        # Key missing in target or type mismatch
                        if isinstance(ref_value, (dict, OrderedDict)):
                            # Recursively handle nested objects
                            result[key] = merge_recursive(ref_value, {})
                        else:
                            # Create placeholder translation
                            result[key] = f"[TODO: Translate] {ref_value}"
                return result
            else:
                # For non-dict values, use reference (this shouldn't happen at root level)
                return ref_obj
        
        return merge_recursive(reference_data, target_data)
    
    def format_json_like_reference(self, data: Dict[str, Any], reference_lines: List[str]) -> List[str]:
        """
        Format the merged JSON data to match the reference file's formatting exactly.
        """
        # Use json.dumps with proper formatting to match the reference style
        formatted_json = json.dumps(data, indent=4, ensure_ascii=False, separators=(',', ': '))
        
        # Split into lines and ensure consistent line endings
        formatted_lines = [line + '\n' for line in formatted_json.split('\n')]
        
        # Make sure the last line doesn't have extra newlines
        if formatted_lines and formatted_lines[-1].strip() == '':
            formatted_lines = formatted_lines[:-1]
        
        # Ensure the last line ends with just a newline
        if formatted_lines and not formatted_lines[-1].endswith('\n'):
            formatted_lines[-1] += '\n'
        
        return formatted_lines
    
    def synchronize_locale_simple(self, locale: str, reference_data: Dict[str, Any], 
                                  reference_lines: List[str], dry_run: bool = False) -> bool:
        """
        Synchronize a locale file using JSON structure merging.
        Handles both addition of missing keys and removal of obsolete keys.
        """
        locale_file = os.path.join(self.locales_dir, f'{locale}.json')
        
        if not os.path.exists(locale_file):
            self.log(f"Locale file {locale_file} does not exist!", 'ERROR')
            return False
        
        try:
            target_data, _ = self.load_json_preserve_order(locale_file)
        except Exception as e:
            self.log(f"Error loading {locale_file}: {e}", 'ERROR')
            return False
        
        # Get keys to check for differences
        ref_keys = self.get_all_leaf_keys(reference_data)
        target_keys = self.get_all_leaf_keys(target_data)
        missing_keys = set(ref_keys.keys()) - set(target_keys.keys())
        obsolete_keys = set(target_keys.keys()) - set(ref_keys.keys())
        
        if not missing_keys and not obsolete_keys:
            self.log(f"Locale {locale} is already up to date")
            return False
        
        # Report changes
        if missing_keys:
            self.log(f"Found {len(missing_keys)} missing keys in {locale}:")
            for key in sorted(missing_keys):
                self.log(f"  + {key}")
        
        if obsolete_keys:
            self.log(f"Found {len(obsolete_keys)} obsolete keys in {locale}:")
            for key in sorted(obsolete_keys):
                self.log(f"  - {key}")
        
        if dry_run:
            total_changes = len(missing_keys) + len(obsolete_keys)
            self.log(f"DRY RUN: Would update {locale} with {len(missing_keys)} additions and {len(obsolete_keys)} deletions ({total_changes} total changes)")
            return True
        
        # Merge the structures (this will both add missing keys and remove obsolete ones)
        try:
            merged_data = self.merge_json_structures(reference_data, target_data)
            
            # Format to match reference style
            new_lines = self.format_json_like_reference(merged_data, reference_lines)
            
            # Validate that the result is valid JSON
            reconstructed_content = ''.join(new_lines)
            json.loads(reconstructed_content)  # This will raise an exception if invalid
            
            # Write the updated file
            with open(locale_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            total_changes = len(missing_keys) + len(obsolete_keys)
            self.log(f"Successfully updated {locale} with {len(missing_keys)} additions and {len(obsolete_keys)} deletions ({total_changes} total changes)")
            return True
            
        except json.JSONDecodeError as e:
            self.log(f"Generated invalid JSON for {locale}: {e}", 'ERROR')
            return False
        except Exception as e:
            self.log(f"Error updating {locale_file}: {e}", 'ERROR')
            return False
    
    def synchronize_all(self, dry_run: bool = False) -> bool:
        """
        Synchronize all locale files with the reference.
        Returns True if all operations were successful.
        """
        # Load reference file
        reference_file = os.path.join(self.locales_dir, f'{self.reference_locale}.json')
        
        if not os.path.exists(reference_file):
            self.log(f"Reference file {reference_file} does not exist!", 'ERROR')
            return False
        
        try:
            reference_data, reference_lines = self.load_json_preserve_order(reference_file)
            reference_keys = self.get_all_leaf_keys(reference_data)
        except Exception as e:
            self.log(f"Error loading reference file: {e}", 'ERROR')
            return False
        
        self.log(f"Loaded reference file with {len(reference_keys)} keys")
        
        success = True
        changes_made = False
        
        # Synchronize each target locale
        for locale in self.target_locales:
            try:
                if self.synchronize_locale_simple(locale, reference_data, reference_lines, dry_run):
                    changes_made = True
            except Exception as e:
                self.log(f"Error synchronizing {locale}: {e}", 'ERROR')
                success = False
        
        if changes_made:
            self.log("Synchronization completed with changes")
        else:
            self.log("All locale files are already up to date")
            
        return success

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Synchronize translation keys from en.json to all other locale files'
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true',
        help='Show what would be changed without making actual changes'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--locales-dir',
        default=None,
        help='Path to locales directory (default: auto-detect from script location)'
    )
    
    args = parser.parse_args()
    
    # Determine locales directory
    if args.locales_dir:
        locales_dir = args.locales_dir
    else:
        # Auto-detect based on script location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        locales_dir = os.path.join(os.path.dirname(script_dir), 'locales')
    
    if not os.path.exists(locales_dir):
        print(f"ERROR: Locales directory not found: {locales_dir}")
        sys.exit(1)
    
    print(f"Translation Key Synchronization")
    print(f"Locales directory: {locales_dir}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print("-" * 50)
    
    # Create synchronizer and run
    synchronizer = TranslationKeySynchronizer(locales_dir, args.verbose)
    
    try:
        success = synchronizer.synchronize_all(args.dry_run)
        
        if success:
            print("\n✅ Synchronization completed successfully!")
            if not args.dry_run:
                print("💡 Run 'python test_i18n.py' to verify formatting consistency")
        else:
            print("\n❌ Synchronization completed with errors!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
