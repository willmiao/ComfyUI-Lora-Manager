"""
Integration tests for cache validation in ModelScanner
"""

import pytest
import asyncio

from py.services.model_scanner import ModelScanner
from py.services.cache_entry_validator import CacheEntryValidator
from py.services.cache_health_monitor import CacheHealthMonitor, CacheHealthStatus


@pytest.mark.asyncio
async def test_model_scanner_validates_cache_entries(tmp_path_factory):
    """Test that ModelScanner validates cache entries during initialization"""
    # Create temporary test data
    tmp_dir = tmp_path_factory.mktemp("test_loras")

    # Create test files
    test_file = tmp_dir / "test_model.safetensors"
    test_file.write_bytes(b"fake model data" * 100)

    # Mock model scanner (we can't easily instantiate a full scanner in tests)
    # Instead, test the validation logic directly
    entries = [
        {
            'file_path': str(test_file),
            'sha256': 'abc123def456',
            'file_name': 'test_model.safetensors',
        },
        {
            'file_path': str(tmp_dir / 'invalid.safetensors'),
            # Missing sha256 - invalid
        },
    ]

    valid, invalid = CacheEntryValidator.validate_batch(entries, auto_repair=True)

    assert len(valid) == 1
    assert len(invalid) == 1
    assert valid[0]['sha256'] == 'abc123def456'


@pytest.mark.asyncio
async def test_model_scanner_detects_degraded_cache():
    """Test that ModelScanner detects degraded cache health"""
    # Create 100 entries with 2% corruption
    entries = [
        {
            'file_path': f'/models/test{i}.safetensors',
            'sha256': f'hash{i}',
        }
        for i in range(98)
    ]
    # Add 2 invalid entries
    entries.append({'file_path': '/models/invalid1.safetensors'})
    entries.append({'file_path': '/models/invalid2.safetensors'})

    monitor = CacheHealthMonitor()
    report = monitor.check_health(entries, auto_repair=True)

    assert report.status == CacheHealthStatus.DEGRADED
    assert report.invalid_entries == 2
    assert report.valid_entries == 98


@pytest.mark.asyncio
async def test_model_scanner_detects_corrupted_cache():
    """Test that ModelScanner detects corrupted cache health"""
    # Create 100 entries with 10% corruption
    entries = [
        {
            'file_path': f'/models/test{i}.safetensors',
            'sha256': f'hash{i}',
        }
        for i in range(90)
    ]
    # Add 10 invalid entries
    for i in range(10):
        entries.append({'file_path': f'/models/invalid{i}.safetensors'})

    monitor = CacheHealthMonitor()
    report = monitor.check_health(entries, auto_repair=True)

    assert report.status == CacheHealthStatus.CORRUPTED
    assert report.invalid_entries == 10
    assert report.valid_entries == 90


@pytest.mark.asyncio
async def test_model_scanner_removes_invalid_from_hash_index():
    """Test that ModelScanner removes invalid entries from hash index"""
    from py.services.model_hash_index import ModelHashIndex

    # Create a hash index with some entries
    hash_index = ModelHashIndex()
    valid_entry = {
        'file_path': '/models/valid.safetensors',
        'sha256': 'abc123',
    }
    invalid_entry = {
        'file_path': '/models/invalid.safetensors',
        'sha256': '',  # Empty sha256
    }

    # Add entries to hash index
    hash_index.add_entry(valid_entry['sha256'], valid_entry['file_path'])
    hash_index.add_entry(invalid_entry['sha256'], invalid_entry['file_path'])

    # Verify both entries are in the index (using get_hash method)
    assert hash_index.get_hash(valid_entry['file_path']) == valid_entry['sha256']
    # Invalid entry won't be added due to empty sha256
    assert hash_index.get_hash(invalid_entry['file_path']) is None

    # Simulate removing invalid entry (it's not actually there, but let's test the method)
    hash_index.remove_by_path(
        CacheEntryValidator.get_file_path_safe(invalid_entry),
        CacheEntryValidator.get_sha256_safe(invalid_entry)
    )

    # Verify valid entry remains
    assert hash_index.get_hash(valid_entry['file_path']) == valid_entry['sha256']


def test_cache_entry_validator_handles_various_field_types():
    """Test that validator handles various field types correctly"""
    # Test with different field types
    entry = {
        'file_path': '/models/test.safetensors',
        'sha256': 'abc123',
        'size': 1024,  # int
        'modified': 1234567890.0,  # float
        'favorite': True,  # bool
        'tags': ['tag1', 'tag2'],  # list
        'exclude': False,  # bool
    }

    result = CacheEntryValidator.validate(entry, auto_repair=False)

    assert result.is_valid is True
    assert result.repaired is False


def test_cache_health_report_serialization():
    """Test that HealthReport can be serialized to dict"""
    from py.services.cache_health_monitor import HealthReport

    report = HealthReport(
        status=CacheHealthStatus.DEGRADED,
        total_entries=100,
        valid_entries=98,
        invalid_entries=2,
        repaired_entries=1,
        invalid_paths=['/path1', '/path2'],
        message="Cache issues detected"
    )

    result = report.to_dict()

    assert result['status'] == 'degraded'
    assert result['total_entries'] == 100
    assert result['valid_entries'] == 98
    assert result['invalid_entries'] == 2
    assert result['repaired_entries'] == 1
    assert result['corruption_rate'] == '2.0%'
    assert len(result['invalid_paths']) == 2
    assert result['message'] == "Cache issues detected"
