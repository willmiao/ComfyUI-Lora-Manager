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


class RecipePersistenceError(RecipeServiceError):
    """Raised when a rematched recipe cannot be persisted to disk.

    Raised by the recipe rematch path when ``_save_recipe_persistently``
    returns False (JSON/EXIF/SQLite write failure). Callers translate it
    into a ``success: False`` summary with an ``error`` message key.
    """
