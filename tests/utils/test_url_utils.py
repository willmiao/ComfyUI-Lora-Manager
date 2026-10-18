"""Tests for py/utils/url_utils.py relative_root_prefix."""

from __future__ import annotations

import pytest

from py.utils.url_utils import relative_root_prefix


@pytest.mark.parametrize(
    ("request_path", "expected"),
    [
        ("/", ""),
        ("/loras", ""),
        ("/checkpoints", ""),
        ("/statistics", ""),
        ("/loras/", ""),
        ("/loras/recipes", "../"),
        ("/loras/recipes/", "../"),
    ],
)
def test_relative_root_prefix(request_path: str, expected: str) -> None:
    assert relative_root_prefix(request_path) == expected
