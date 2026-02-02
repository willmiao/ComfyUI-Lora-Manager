"""
Cache Health Monitor

Monitors cache health status and determines when user intervention is needed.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from .cache_entry_validator import CacheEntryValidator, ValidationResult

logger = logging.getLogger(__name__)


class CacheHealthStatus(Enum):
    """Health status of the cache."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CORRUPTED = "corrupted"


@dataclass
class HealthReport:
    """Report of cache health check."""
    status: CacheHealthStatus
    total_entries: int
    valid_entries: int
    invalid_entries: int
    repaired_entries: int
    invalid_paths: List[str] = field(default_factory=list)
    message: str = ""

    @property
    def corruption_rate(self) -> float:
        """Calculate the percentage of invalid entries."""
        if self.total_entries <= 0:
            return 0.0
        return self.invalid_entries / self.total_entries

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'status': self.status.value,
            'total_entries': self.total_entries,
            'valid_entries': self.valid_entries,
            'invalid_entries': self.invalid_entries,
            'repaired_entries': self.repaired_entries,
            'corruption_rate': f"{self.corruption_rate:.1%}",
            'invalid_paths': self.invalid_paths[:10],  # Limit to first 10
            'message': self.message,
        }


class CacheHealthMonitor:
    """
    Monitors cache health and determines appropriate status.

    Thresholds:
    - HEALTHY: 0% invalid entries
    - DEGRADED: 0-5% invalid entries (auto-repaired, user should rebuild)
    - CORRUPTED: >5% invalid entries (significant data loss likely)
    """

    # Threshold percentages
    DEGRADED_THRESHOLD = 0.01   # 1% - show warning
    CORRUPTED_THRESHOLD = 0.05  # 5% - critical warning

    def __init__(
        self,
        *,
        degraded_threshold: float = DEGRADED_THRESHOLD,
        corrupted_threshold: float = CORRUPTED_THRESHOLD
    ):
        """
        Initialize the health monitor.

        Args:
            degraded_threshold: Corruption rate threshold for DEGRADED status
            corrupted_threshold: Corruption rate threshold for CORRUPTED status
        """
        self.degraded_threshold = degraded_threshold
        self.corrupted_threshold = corrupted_threshold

    def check_health(
        self,
        entries: List[Dict[str, Any]],
        *,
        auto_repair: bool = True
    ) -> HealthReport:
        """
        Check the health of cache entries.

        Args:
            entries: List of cache entry dictionaries to check
            auto_repair: If True, attempt to repair entries during validation

        Returns:
            HealthReport with status and statistics
        """
        if not entries:
            return HealthReport(
                status=CacheHealthStatus.HEALTHY,
                total_entries=0,
                valid_entries=0,
                invalid_entries=0,
                repaired_entries=0,
                message="Cache is empty"
            )

        total_entries = len(entries)
        valid_entries: List[Dict[str, Any]] = []
        invalid_entries: List[Dict[str, Any]] = []
        repaired_count = 0
        invalid_paths: List[str] = []

        for entry in entries:
            result = CacheEntryValidator.validate(entry, auto_repair=auto_repair)

            if result.is_valid:
                valid_entries.append(result.entry if result.entry else entry)
                if result.repaired:
                    repaired_count += 1
            else:
                invalid_entries.append(entry)
                # Extract file path for reporting
                file_path = CacheEntryValidator.get_file_path_safe(entry, '<unknown>')
                invalid_paths.append(file_path)

        invalid_count = len(invalid_entries)
        valid_count = len(valid_entries)

        # Determine status based on corruption rate
        corruption_rate = invalid_count / total_entries if total_entries > 0 else 0.0

        if invalid_count == 0:
            status = CacheHealthStatus.HEALTHY
            message = "Cache is healthy"
        elif corruption_rate >= self.corrupted_threshold:
            status = CacheHealthStatus.CORRUPTED
            message = (
                f"Cache is corrupted: {invalid_count} invalid entries "
                f"({corruption_rate:.1%}). Rebuild recommended."
            )
        elif corruption_rate >= self.degraded_threshold or invalid_count > 0:
            status = CacheHealthStatus.DEGRADED
            message = (
                f"Cache has {invalid_count} invalid entries "
                f"({corruption_rate:.1%}). Consider rebuilding cache."
            )
        else:
            # This shouldn't happen, but handle gracefully
            status = CacheHealthStatus.HEALTHY
            message = "Cache is healthy"

        # Log the health check result
        if status != CacheHealthStatus.HEALTHY:
            logger.warning(
                f"Cache health check: {status.value} - "
                f"{invalid_count}/{total_entries} invalid, "
                f"{repaired_count} repaired"
            )
            if invalid_paths:
                logger.debug(f"Invalid entry paths: {invalid_paths[:5]}")

        return HealthReport(
            status=status,
            total_entries=total_entries,
            valid_entries=valid_count,
            invalid_entries=invalid_count,
            repaired_entries=repaired_count,
            invalid_paths=invalid_paths,
            message=message
        )

    def should_notify_user(self, report: HealthReport) -> bool:
        """
        Determine if the user should be notified about cache health.

        Args:
            report: The health report to evaluate

        Returns:
            True if user should be notified
        """
        return report.status != CacheHealthStatus.HEALTHY

    def get_notification_severity(self, report: HealthReport) -> str:
        """
        Get the severity level for user notification.

        Args:
            report: The health report to evaluate

        Returns:
            Severity string: 'warning' or 'error'
        """
        if report.status == CacheHealthStatus.CORRUPTED:
            return 'error'
        return 'warning'
