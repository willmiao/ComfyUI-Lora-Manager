"""Shared exceptions for recipe services."""
from __future__ import annotations


class RecipeServiceError(Exception):
    """Base exception for recipe service failures."""


class RecipeValidationError(RecipeServiceError):
    """Raised when a request payload fails validation."""


class RecipeNotFoundError(RecipeServiceError):
    """Raised when a recipe resource cannot be located."""


class RecipeDownloadError(RecipeServiceError):
    """Raised when remote recipe assets cannot be downloaded."""


class RecipeConflictError(RecipeServiceError):
    """Raised when a conflicting recipe state is detected."""
