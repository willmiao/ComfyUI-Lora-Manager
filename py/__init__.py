"""Project namespace package."""

# pytest's internal compatibility layer still imports ``py.path.local`` from the
# historical ``py`` dependency.  Because this project reuses the ``py`` package
# name, we expose a minimal shim so ``py.path.local`` resolves to ``pathlib.Path``
# during test runs without pulling in the external dependency.
from pathlib import Path
from types import SimpleNamespace

path = SimpleNamespace(local=Path)

__all__ = ["path"]
