"""
Cache Entry Validator

Validates and repairs cache entries to prevent runtime errors from
missing or invalid critical fields.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single cache entry."""
    is_valid: bool
    repaired: bool
    errors: List[str] = field(default_factory=list)
    entry: Optional[Dict[str, Any]] = None


class CacheEntryValidator:
    """
    Validates and repairs cache entry core fields.

    Critical fields that cause runtime errors when missing:
    - file_path: KeyError in multiple locations
    - sha256: KeyError/AttributeError in hash operations

    Medium severity fields that may cause sorting/display issues:
    - size: KeyError during sorting
    - modified: KeyError during sorting
    - model_name: AttributeError on .lower() calls

    Low severity fields:
    - tags: KeyError/TypeError in recipe operations
    """

    # Field definitions: (default_value, is_required)
    CORE_FIELDS: Dict[str, Tuple[Any, bool]] = {
        'file_path': ('', True),
        'sha256': ('', True),
        'file_name': ('', False),
        'model_name': ('', False),
        'folder': ('', False),
        'size': (0, False),
        'modified': (0.0, False),
        'tags': ([], False),
        'preview_url': ('', False),
        'base_model': ('', False),
        'from_civitai': (True, False),
        'favorite': (False, False),
        'exclude': (False, False),
        'db_checked': (False, False),
        'preview_nsfw_level': (0, False),
        'notes': ('', False),
        'usage_tips': ('', False),
    }

    @classmethod
    def validate(cls, entry: Dict[str, Any], *, auto_repair: bool = True) -> ValidationResult:
        """
        Validate a single cache entry.

        Args:
            entry: The cache entry dictionary to validate
            auto_repair: If True, attempt to repair missing/invalid fields

        Returns:
            ValidationResult with validation status and optionally repaired entry
        """
        if entry is None:
            return ValidationResult(
                is_valid=False,
                repaired=False,
                errors=['Entry is None'],
                entry=None
            )

        if not isinstance(entry, dict):
            return ValidationResult(
                is_valid=False,
                repaired=False,
                errors=[f'Entry is not a dict: {type(entry).__name__}'],
                entry=None
            )

        errors: List[str] = []
        repaired = False
        working_entry = dict(entry) if auto_repair else entry

        for field_name, (default_value, is_required) in cls.CORE_FIELDS.items():
            value = working_entry.get(field_name)

            # Check if field is missing or None
            if value is None:
                if is_required:
                    errors.append(f"Required field '{field_name}' is missing or None")
                if auto_repair:
                    working_entry[field_name] = cls._get_default_copy(default_value)
                    repaired = True
                continue

            # Validate field type and value
            field_error = cls._validate_field(field_name, value, default_value)
            if field_error:
                errors.append(field_error)
                if auto_repair:
                    working_entry[field_name] = cls._get_default_copy(default_value)
                    repaired = True

        # Special validation: file_path must not be empty for required field
        file_path = working_entry.get('file_path', '')
        if not file_path or (isinstance(file_path, str) and not file_path.strip()):
            errors.append("Required field 'file_path' is empty")
            # Cannot repair empty file_path - entry is invalid
            return ValidationResult(
                is_valid=False,
                repaired=repaired,
                errors=errors,
                entry=working_entry if auto_repair else None
            )

        # Special validation: sha256 must not be empty for required field
        sha256 = working_entry.get('sha256', '')
        if not sha256 or (isinstance(sha256, str) and not sha256.strip()):
            errors.append("Required field 'sha256' is empty")
            # Cannot repair empty sha256 - entry is invalid
            return ValidationResult(
                is_valid=False,
                repaired=repaired,
                errors=errors,
                entry=working_entry if auto_repair else None
            )

        # Normalize sha256 to lowercase if needed
        if isinstance(sha256, str):
            normalized_sha = sha256.lower().strip()
            if normalized_sha != sha256:
                working_entry['sha256'] = normalized_sha
                repaired = True

        # Determine if entry is valid
        # Entry is valid if no critical required field errors remain after repair
        # Critical fields are file_path and sha256
        CRITICAL_REQUIRED_FIELDS = {'file_path', 'sha256'}
        has_critical_errors = any(
            "Required field" in error and
            any(f"'{field}'" in error for field in CRITICAL_REQUIRED_FIELDS)
            for error in errors
        )

        is_valid = not has_critical_errors

        return ValidationResult(
            is_valid=is_valid,
            repaired=repaired,
            errors=errors,
            entry=working_entry if auto_repair else entry
        )

    @classmethod
    def validate_batch(
        cls,
        entries: List[Dict[str, Any]],
        *,
        auto_repair: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate a batch of cache entries.

        Args:
            entries: List of cache entry dictionaries to validate
            auto_repair: If True, attempt to repair missing/invalid fields

        Returns:
            Tuple of (valid_entries, invalid_entries)
        """
        if not entries:
            return [], []

        valid_entries: List[Dict[str, Any]] = []
        invalid_entries: List[Dict[str, Any]] = []

        for entry in entries:
            result = cls.validate(entry, auto_repair=auto_repair)

            if result.is_valid:
                # Use repaired entry if available, otherwise original
                valid_entries.append(result.entry if result.entry else entry)
            else:
                invalid_entries.append(entry)
                # Log invalid entries for debugging
                file_path = entry.get('file_path', '<unknown>') if isinstance(entry, dict) else '<not a dict>'
                logger.warning(
                    f"Invalid cache entry for '{file_path}': {', '.join(result.errors)}"
                )

        return valid_entries, invalid_entries

    @classmethod
    def _validate_field(cls, field_name: str, value: Any, default_value: Any) -> Optional[str]:
        """
        Validate a specific field value.

        Returns an error message if invalid, None if valid.
        """
        expected_type = type(default_value)

        # Special handling for numeric types
        if expected_type == int:
            if not isinstance(value, (int, float)):
                return f"Field '{field_name}' should be numeric, got {type(value).__name__}"
        elif expected_type == float:
            if not isinstance(value, (int, float)):
                return f"Field '{field_name}' should be numeric, got {type(value).__name__}"
        elif expected_type == bool:
            # Be lenient with boolean fields - accept truthy/falsy values
            pass
        elif expected_type == str:
            if not isinstance(value, str):
                return f"Field '{field_name}' should be string, got {type(value).__name__}"
        elif expected_type == list:
            if not isinstance(value, (list, tuple)):
                return f"Field '{field_name}' should be list, got {type(value).__name__}"

        return None

    @classmethod
    def _get_default_copy(cls, default_value: Any) -> Any:
        """Get a copy of the default value to avoid shared mutable state."""
        if isinstance(default_value, list):
            return list(default_value)
        if isinstance(default_value, dict):
            return dict(default_value)
        return default_value

    @classmethod
    def get_file_path_safe(cls, entry: Dict[str, Any], default: str = '') -> str:
        """Safely get file_path from an entry."""
        if not isinstance(entry, dict):
            return default
        value = entry.get('file_path')
        if isinstance(value, str):
            return value
        return default

    @classmethod
    def get_sha256_safe(cls, entry: Dict[str, Any], default: str = '') -> str:
        """Safely get sha256 from an entry."""
        if not isinstance(entry, dict):
            return default
        value = entry.get('sha256')
        if isinstance(value, str):
            return value.lower()
        return default
