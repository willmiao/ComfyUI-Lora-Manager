"""Errors raised by LoRA compatibility adapters."""


class LoraCompatibilityError(ValueError):
    """Raised when a LoRA cannot be applied to the connected model's layout."""
