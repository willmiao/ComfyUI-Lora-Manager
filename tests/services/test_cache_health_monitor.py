"""
Unit tests for CacheHealthMonitor
"""

import pytest

from py.services.cache_health_monitor import (
    CacheHealthMonitor,
    CacheHealthStatus,
    HealthReport,
)


class TestCacheHealthMonitor:
    """Tests for CacheHealthMonitor class"""

    def test_check_health_all_valid_entries(self):
        """Test health check with 100% valid entries"""
        monitor = CacheHealthMonitor()

        entries = [
            {
                'file_path': f'/models/test{i}.safetensors',
                'sha256': f'hash{i}',
            }
            for i in range(100)
        ]

        report = monitor.check_health(entries, auto_repair=False)

        assert report.status == CacheHealthStatus.HEALTHY
        assert report.total_entries == 100
        assert report.valid_entries == 100
        assert report.invalid_entries == 0
        assert report.repaired_entries == 0
        assert report.corruption_rate == 0.0
        assert report.message == "Cache is healthy"

    def test_check_health_degraded_cache(self):
        """Test health check with 1-5% invalid entries (degraded)"""
        monitor = CacheHealthMonitor()

        # Create 100 entries, 2 invalid (2%)
        entries = [
            {
                'file_path': f'/models/test{i}.safetensors',
                'sha256': f'hash{i}',
            }
            for i in range(98)
        ]
        # Add 2 invalid entries
        entries.append({'file_path': '/models/invalid1.safetensors'})  # Missing sha256
        entries.append({'file_path': '/models/invalid2.safetensors'})  # Missing sha256

        report = monitor.check_health(entries, auto_repair=False)

        assert report.status == CacheHealthStatus.DEGRADED
        assert report.total_entries == 100
        assert report.valid_entries == 98
        assert report.invalid_entries == 2
        assert report.corruption_rate == 0.02
        # Message describes the issue without necessarily containing the word "degraded"
        assert 'invalid entries' in report.message.lower()

    def test_check_health_corrupted_cache(self):
        """Test health check with >5% invalid entries (corrupted)"""
        monitor = CacheHealthMonitor()

        # Create 100 entries, 10 invalid (10%)
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

        report = monitor.check_health(entries, auto_repair=False)

        assert report.status == CacheHealthStatus.CORRUPTED
        assert report.total_entries == 100
        assert report.valid_entries == 90
        assert report.invalid_entries == 10
        assert report.corruption_rate == 0.10
        assert 'corrupted' in report.message.lower()

    def test_check_health_empty_cache(self):
        """Test health check with empty cache"""
        monitor = CacheHealthMonitor()

        report = monitor.check_health([], auto_repair=False)

        assert report.status == CacheHealthStatus.HEALTHY
        assert report.total_entries == 0
        assert report.valid_entries == 0
        assert report.invalid_entries == 0
        assert report.corruption_rate == 0.0
        assert report.message == "Cache is empty"

    def test_check_health_single_invalid_entry(self):
        """Test health check with 1 invalid entry out of 1 (100% corruption)"""
        monitor = CacheHealthMonitor()

        entries = [{'file_path': '/models/invalid.safetensors'}]

        report = monitor.check_health(entries, auto_repair=False)

        assert report.status == CacheHealthStatus.CORRUPTED
        assert report.total_entries == 1
        assert report.valid_entries == 0
        assert report.invalid_entries == 1
        assert report.corruption_rate == 1.0

    def test_check_health_boundary_degraded_threshold(self):
        """Test health check at degraded threshold (1%)"""
        monitor = CacheHealthMonitor(degraded_threshold=0.01)

        # 100 entries, 1 invalid (exactly 1%)
        entries = [
            {
                'file_path': f'/models/test{i}.safetensors',
                'sha256': f'hash{i}',
            }
            for i in range(99)
        ]
        entries.append({'file_path': '/models/invalid.safetensors'})

        report = monitor.check_health(entries, auto_repair=False)

        assert report.status == CacheHealthStatus.DEGRADED
        assert report.corruption_rate == 0.01

    def test_check_health_boundary_corrupted_threshold(self):
        """Test health check at corrupted threshold (5%)"""
        monitor = CacheHealthMonitor(corrupted_threshold=0.05)

        # 100 entries, 5 invalid (exactly 5%)
        entries = [
            {
                'file_path': f'/models/test{i}.safetensors',
                'sha256': f'hash{i}',
            }
            for i in range(95)
        ]
        for i in range(5):
            entries.append({'file_path': f'/models/invalid{i}.safetensors'})

        report = monitor.check_health(entries, auto_repair=False)

        assert report.status == CacheHealthStatus.CORRUPTED
        assert report.corruption_rate == 0.05

    def test_check_health_below_degraded_threshold(self):
        """Test health check below degraded threshold (0%)"""
        monitor = CacheHealthMonitor(degraded_threshold=0.01)

        # All entries valid
        entries = [
            {
                'file_path': f'/models/test{i}.safetensors',
                'sha256': f'hash{i}',
            }
            for i in range(100)
        ]

        report = monitor.check_health(entries, auto_repair=False)

        assert report.status == CacheHealthStatus.HEALTHY
        assert report.corruption_rate == 0.0

    def test_check_health_auto_repair(self):
        """Test health check with auto_repair enabled"""
        monitor = CacheHealthMonitor()

        # 1 entry with all fields (won't be repaired), 1 entry with missing non-required fields (will be repaired)
        complete_entry = {
            'file_path': '/models/test1.safetensors',
            'sha256': 'hash1',
            'file_name': 'test1.safetensors',
            'model_name': 'Model 1',
            'folder': '',
            'size': 0,
            'modified': 0.0,
            'tags': ['tag1'],
            'preview_url': '',
            'base_model': '',
            'from_civitai': True,
            'favorite': False,
            'exclude': False,
            'db_checked': False,
            'preview_nsfw_level': 0,
            'notes': '',
            'usage_tips': '',
        }
        incomplete_entry = {
            'file_path': '/models/test2.safetensors',
            'sha256': 'hash2',
            # Missing many optional fields (will be repaired)
        }

        entries = [complete_entry, incomplete_entry]

        report = monitor.check_health(entries, auto_repair=True)

        assert report.status == CacheHealthStatus.HEALTHY
        assert report.total_entries == 2
        assert report.valid_entries == 2
        assert report.invalid_entries == 0
        assert report.repaired_entries == 1

    def test_should_notify_user_healthy(self):
        """Test should_notify_user for healthy cache"""
        monitor = CacheHealthMonitor()

        report = HealthReport(
            status=CacheHealthStatus.HEALTHY,
            total_entries=100,
            valid_entries=100,
            invalid_entries=0,
            repaired_entries=0,
            message="Cache is healthy"
        )

        assert monitor.should_notify_user(report) is False

    def test_should_notify_user_degraded(self):
        """Test should_notify_user for degraded cache"""
        monitor = CacheHealthMonitor()

        report = HealthReport(
            status=CacheHealthStatus.DEGRADED,
            total_entries=100,
            valid_entries=98,
            invalid_entries=2,
            repaired_entries=0,
            message="Cache is degraded"
        )

        assert monitor.should_notify_user(report) is True

    def test_should_notify_user_corrupted(self):
        """Test should_notify_user for corrupted cache"""
        monitor = CacheHealthMonitor()

        report = HealthReport(
            status=CacheHealthStatus.CORRUPTED,
            total_entries=100,
            valid_entries=90,
            invalid_entries=10,
            repaired_entries=0,
            message="Cache is corrupted"
        )

        assert monitor.should_notify_user(report) is True

    def test_get_notification_severity_degraded(self):
        """Test get_notification_severity for degraded cache"""
        monitor = CacheHealthMonitor()

        report = HealthReport(
            status=CacheHealthStatus.DEGRADED,
            total_entries=100,
            valid_entries=98,
            invalid_entries=2,
            repaired_entries=0,
            message="Cache is degraded"
        )

        assert monitor.get_notification_severity(report) == 'warning'

    def test_get_notification_severity_corrupted(self):
        """Test get_notification_severity for corrupted cache"""
        monitor = CacheHealthMonitor()

        report = HealthReport(
            status=CacheHealthStatus.CORRUPTED,
            total_entries=100,
            valid_entries=90,
            invalid_entries=10,
            repaired_entries=0,
            message="Cache is corrupted"
        )

        assert monitor.get_notification_severity(report) == 'error'

    def test_report_to_dict(self):
        """Test HealthReport to_dict conversion"""
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

    def test_report_corruption_rate_zero_division(self):
        """Test corruption_rate calculation with zero entries"""
        report = HealthReport(
            status=CacheHealthStatus.HEALTHY,
            total_entries=0,
            valid_entries=0,
            invalid_entries=0,
            repaired_entries=0,
            message="Cache is empty"
        )

        assert report.corruption_rate == 0.0

    def test_check_health_collects_invalid_paths(self):
        """Test health check collects invalid entry paths"""
        monitor = CacheHealthMonitor()

        entries = [
            {
                'file_path': '/models/valid.safetensors',
                'sha256': 'hash1',
            },
            {
                'file_path': '/models/invalid1.safetensors',
            },
            {
                'file_path': '/models/invalid2.safetensors',
            },
        ]

        report = monitor.check_health(entries, auto_repair=False)

        assert len(report.invalid_paths) == 2
        assert '/models/invalid1.safetensors' in report.invalid_paths
        assert '/models/invalid2.safetensors' in report.invalid_paths

    def test_report_to_dict_limits_invalid_paths(self):
        """Test that to_dict limits invalid_paths to first 10"""
        report = HealthReport(
            status=CacheHealthStatus.CORRUPTED,
            total_entries=15,
            valid_entries=0,
            invalid_entries=15,
            repaired_entries=0,
            invalid_paths=[f'/path{i}' for i in range(15)],
            message="Cache corrupted"
        )

        result = report.to_dict()

        assert len(result['invalid_paths']) == 10
        assert result['invalid_paths'][0] == '/path0'
        assert result['invalid_paths'][-1] == '/path9'
