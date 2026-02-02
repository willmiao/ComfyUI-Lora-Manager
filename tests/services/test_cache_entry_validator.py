"""
Unit tests for CacheEntryValidator
"""

import pytest

from py.services.cache_entry_validator import (
    CacheEntryValidator,
    ValidationResult,
)


class TestCacheEntryValidator:
    """Tests for CacheEntryValidator class"""

    def test_validate_valid_entry(self):
        """Test validation of a valid cache entry"""
        entry = {
            'file_path': '/models/test.safetensors',
            'sha256': 'abc123def456',
            'file_name': 'test.safetensors',
            'model_name': 'Test Model',
            'size': 1024,
            'modified': 1234567890.0,
            'tags': ['tag1', 'tag2'],
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is True
        assert result.repaired is False
        assert len(result.errors) == 0
        assert result.entry == entry

    def test_validate_missing_required_field_sha256(self):
        """Test validation fails when required sha256 field is missing"""
        entry = {
            'file_path': '/models/test.safetensors',
            # sha256 missing
            'file_name': 'test.safetensors',
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is False
        assert result.repaired is False
        assert any('sha256' in error for error in result.errors)

    def test_validate_missing_required_field_file_path(self):
        """Test validation fails when required file_path field is missing"""
        entry = {
            # file_path missing
            'sha256': 'abc123def456',
            'file_name': 'test.safetensors',
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is False
        assert result.repaired is False
        assert any('file_path' in error for error in result.errors)

    def test_validate_empty_required_field_sha256(self):
        """Test validation fails when sha256 is empty string"""
        entry = {
            'file_path': '/models/test.safetensors',
            'sha256': '',  # Empty string
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is False
        assert result.repaired is False
        assert any('sha256' in error for error in result.errors)

    def test_validate_empty_required_field_file_path(self):
        """Test validation fails when file_path is empty string"""
        entry = {
            'file_path': '',  # Empty string
            'sha256': 'abc123def456',
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is False
        assert result.repaired is False
        assert any('file_path' in error for error in result.errors)

    def test_validate_none_required_field(self):
        """Test validation fails when required field is None"""
        entry = {
            'file_path': None,
            'sha256': 'abc123def456',
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is False
        assert result.repaired is False
        assert any('file_path' in error for error in result.errors)

    def test_validate_none_entry(self):
        """Test validation handles None entry"""
        result = CacheEntryValidator.validate(None, auto_repair=False)

        assert result.is_valid is False
        assert result.repaired is False
        assert any('None' in error for error in result.errors)
        assert result.entry is None

    def test_validate_non_dict_entry(self):
        """Test validation handles non-dict entry"""
        result = CacheEntryValidator.validate("not a dict", auto_repair=False)

        assert result.is_valid is False
        assert result.repaired is False
        assert any('not a dict' in error for error in result.errors)
        assert result.entry is None

    def test_auto_repair_missing_non_required_field(self):
        """Test auto-repair adds missing non-required fields"""
        entry = {
            'file_path': '/models/test.safetensors',
            'sha256': 'abc123def456',
            # file_name, model_name, tags missing
        }

        result = CacheEntryValidator.validate(entry, auto_repair=True)

        assert result.is_valid is True
        assert result.repaired is True
        assert result.entry['file_name'] == ''
        assert result.entry['model_name'] == ''
        assert result.entry['tags'] == []

    def test_auto_repair_wrong_type_field(self):
        """Test auto-repair fixes fields with wrong type"""
        entry = {
            'file_path': '/models/test.safetensors',
            'sha256': 'abc123def456',
            'size': 'not a number',  # Should be int
            'tags': 'not a list',  # Should be list
        }

        result = CacheEntryValidator.validate(entry, auto_repair=True)

        assert result.is_valid is True
        assert result.repaired is True
        assert result.entry['size'] == 0  # Default value
        assert result.entry['tags'] == []  # Default value

    def test_normalize_sha256_lowercase(self):
        """Test sha256 is normalized to lowercase"""
        entry = {
            'file_path': '/models/test.safetensors',
            'sha256': 'ABC123DEF456',  # Uppercase
        }

        result = CacheEntryValidator.validate(entry, auto_repair=True)

        assert result.is_valid is True
        assert result.entry['sha256'] == 'abc123def456'

    def test_validate_batch_all_valid(self):
        """Test batch validation with all valid entries"""
        entries = [
            {
                'file_path': '/models/test1.safetensors',
                'sha256': 'abc123',
            },
            {
                'file_path': '/models/test2.safetensors',
                'sha256': 'def456',
            },
        ]

        valid, invalid = CacheEntryValidator.validate_batch(entries, auto_repair=False)

        assert len(valid) == 2
        assert len(invalid) == 0

    def test_validate_batch_mixed_validity(self):
        """Test batch validation with mixed valid/invalid entries"""
        entries = [
            {
                'file_path': '/models/test1.safetensors',
                'sha256': 'abc123',
            },
            {
                'file_path': '/models/test2.safetensors',
                # sha256 missing - invalid
            },
            {
                'file_path': '/models/test3.safetensors',
                'sha256': 'def456',
            },
        ]

        valid, invalid = CacheEntryValidator.validate_batch(entries, auto_repair=False)

        assert len(valid) == 2
        assert len(invalid) == 1
        # invalid list contains the actual invalid entries (not by index)
        assert invalid[0]['file_path'] == '/models/test2.safetensors'

    def test_validate_batch_empty_list(self):
        """Test batch validation with empty list"""
        valid, invalid = CacheEntryValidator.validate_batch([], auto_repair=False)

        assert len(valid) == 0
        assert len(invalid) == 0

    def test_get_file_path_safe(self):
        """Test safe file_path extraction"""
        entry = {'file_path': '/models/test.safetensors', 'sha256': 'abc123'}
        assert CacheEntryValidator.get_file_path_safe(entry) == '/models/test.safetensors'

    def test_get_file_path_safe_missing(self):
        """Test safe file_path extraction when missing"""
        entry = {'sha256': 'abc123'}
        assert CacheEntryValidator.get_file_path_safe(entry) == ''

    def test_get_file_path_safe_not_dict(self):
        """Test safe file_path extraction from non-dict"""
        assert CacheEntryValidator.get_file_path_safe(None) == ''
        assert CacheEntryValidator.get_file_path_safe('string') == ''

    def test_get_sha256_safe(self):
        """Test safe sha256 extraction"""
        entry = {'file_path': '/models/test.safetensors', 'sha256': 'ABC123'}
        assert CacheEntryValidator.get_sha256_safe(entry) == 'abc123'

    def test_get_sha256_safe_missing(self):
        """Test safe sha256 extraction when missing"""
        entry = {'file_path': '/models/test.safetensors'}
        assert CacheEntryValidator.get_sha256_safe(entry) == ''

    def test_get_sha256_safe_not_dict(self):
        """Test safe sha256 extraction from non-dict"""
        assert CacheEntryValidator.get_sha256_safe(None) == ''
        assert CacheEntryValidator.get_sha256_safe('string') == ''

    def test_validate_with_all_optional_fields(self):
        """Test validation with all optional fields present"""
        entry = {
            'file_path': '/models/test.safetensors',
            'sha256': 'abc123',
            'file_name': 'test.safetensors',
            'model_name': 'Test Model',
            'folder': 'test_folder',
            'size': 1024,
            'modified': 1234567890.0,
            'tags': ['tag1', 'tag2'],
            'preview_url': 'http://example.com/preview.jpg',
            'base_model': 'SD1.5',
            'from_civitai': True,
            'favorite': True,
            'exclude': False,
            'db_checked': True,
            'preview_nsfw_level': 1,
            'notes': 'Test notes',
            'usage_tips': 'Test tips',
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is True
        assert result.repaired is False
        assert result.entry == entry

    def test_validate_numeric_field_accepts_float_for_int(self):
        """Test that numeric fields accept float for int type"""
        entry = {
            'file_path': '/models/test.safetensors',
            'sha256': 'abc123',
            'size': 1024.5,  # Float for int field
            'modified': 1234567890.0,
        }

        result = CacheEntryValidator.validate(entry, auto_repair=False)

        assert result.is_valid is True
        assert result.repaired is False
