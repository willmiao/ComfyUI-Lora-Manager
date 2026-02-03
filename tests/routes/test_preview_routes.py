import os
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from py.config import Config
from py.routes.handlers.preview_handlers import PreviewHandler


async def test_preview_handler_serves_preview_from_active_library(tmp_path):
    library_root = tmp_path / "library"
    library_root.mkdir()
    preview_file = library_root / "model.webp"
    preview_file.write_bytes(b"preview")

    config = Config()
    config.apply_library_settings(
        {
            "folder_paths": {
                "loras": [str(library_root)],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
            }
        }
    )

    handler = PreviewHandler(config=config)
    encoded_path = urllib.parse.quote(str(preview_file), safe="")
    request = make_mocked_request("GET", f"/api/lm/previews?path={encoded_path}")

    response = await handler.serve_preview(request)

    assert isinstance(response, web.FileResponse)
    assert response.status == 200
    assert Path(response._path) == preview_file

async def test_preview_handler_forbids_paths_outside_active_library(tmp_path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    forbidden_root = tmp_path / "forbidden"
    forbidden_root.mkdir()
    forbidden_file = forbidden_root / "sneaky.webp"
    forbidden_file.write_bytes(b"x")

    config = Config()
    config.apply_library_settings(
        {
            "folder_paths": {
                "loras": [str(allowed_root)],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
            }
        }
    )

    handler = PreviewHandler(config=config)
    encoded_path = urllib.parse.quote(str(forbidden_file), safe="")
    request = make_mocked_request("GET", f"/api/lm/previews?path={encoded_path}")

    with pytest.raises(web.HTTPForbidden):
        await handler.serve_preview(request)


async def test_config_updates_preview_roots_after_switch(tmp_path):
    first_root = tmp_path / "first"
    first_root.mkdir()
    second_root = tmp_path / "second"
    second_root.mkdir()

    first_preview = first_root / "model.webp"
    first_preview.write_bytes(b"a")
    second_preview = second_root / "model.webp"
    second_preview.write_bytes(b"b")

    config = Config()
    config.apply_library_settings(
        {
            "folder_paths": {
                "loras": [str(first_root)],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
            }
        }
    )

    assert config.is_preview_path_allowed(str(first_preview))
    assert not config.is_preview_path_allowed(str(second_preview))

    config.apply_library_settings(
        {
            "folder_paths": {
                "loras": [str(second_root)],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
            }
        }
    )

    assert config.is_preview_path_allowed(str(second_preview))
    assert not config.is_preview_path_allowed(str(first_preview))

    preview_url = config.get_preview_static_url(str(second_preview))
    assert preview_url.startswith("/api/lm/previews?path=")
    decoded = urllib.parse.unquote(preview_url.split("path=", 1)[1])
    assert decoded.replace("\\", "/").endswith("model.webp")


def test_is_preview_path_allowed_case_insensitive_on_windows(tmp_path):
    """Test that preview path validation is case-insensitive on Windows.

    On Windows, drive letters and paths are case-insensitive. This test verifies
    that paths like 'a:/folder/file' match roots stored as 'A:/folder'.

    See: https://github.com/willmiao/ComfyUI-Lora-Manager/issues/772
    See: https://github.com/willmiao/ComfyUI-Lora-Manager/issues/774
    """
    # Create actual files for the test
    library_root = tmp_path / "loras"
    library_root.mkdir()
    preview_file = library_root / "model.preview.jpeg"
    preview_file.write_bytes(b"preview")

    config = Config()

    # Simulate Windows behavior by mocking os.path.normcase to lowercase paths
    # and os.sep to backslash, regardless of the actual platform
    def windows_normcase(path):
        return path.lower().replace("/", "\\")

    with patch("py.config.os.path.normcase", side_effect=windows_normcase), \
         patch("py.config.os.sep", "\\"):

        # Manually set _preview_root_paths with uppercase drive letter style path
        uppercase_root = Path(str(library_root).upper())
        config._preview_root_paths = {uppercase_root}

        # Test: lowercase version of the path should still be allowed
        lowercase_path = str(preview_file).lower()
        assert config.is_preview_path_allowed(lowercase_path), \
            f"Path '{lowercase_path}' should be allowed when root is '{uppercase_root}'"

        # Test: mixed case should also work
        mixed_case_path = str(preview_file).swapcase()
        assert config.is_preview_path_allowed(mixed_case_path), \
            f"Path '{mixed_case_path}' should be allowed when root is '{uppercase_root}'"

        # Test: path outside root should still be rejected
        outside_path = str(tmp_path / "other" / "file.jpeg")
        assert not config.is_preview_path_allowed(outside_path), \
            f"Path '{outside_path}' should NOT be allowed"


def test_is_preview_path_allowed_rejects_prefix_without_separator(tmp_path):
    """Test that 'A:/folder' does not match 'A:/folderextra/file'.

    This ensures we check for the path separator after the root to avoid
    false positives with paths that share a common prefix.
    """
    library_root = tmp_path / "loras"
    library_root.mkdir()

    # Create a sibling folder that starts with the same prefix
    sibling_root = tmp_path / "loras_extra"
    sibling_root.mkdir()
    sibling_file = sibling_root / "model.jpeg"
    sibling_file.write_bytes(b"x")

    config = Config()
    config.apply_library_settings(
        {
            "folder_paths": {
                "loras": [str(library_root)],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
            }
        }
    )

    # The sibling path should NOT be allowed even though it shares a prefix
    assert not config.is_preview_path_allowed(str(sibling_file)), \
        f"Path in '{sibling_root}' should NOT be allowed when root is '{library_root}'"


async def test_preview_handler_serves_from_deep_symlink(tmp_path):
    """Test that previews under deep symlinks are served correctly."""
    library_root = tmp_path / "library"
    library_root.mkdir()

    # Create nested structure with deep symlink at second level
    subdir = library_root / "anime"
    subdir.mkdir()
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    deep_symlink = subdir / "styles"
    deep_symlink.symlink_to(external_dir, target_is_directory=True)

    # Create preview file under deep symlink
    preview_file = deep_symlink / "model.preview.webp"
    preview_file.write_bytes(b"preview_content")

    config = Config()
    config.apply_library_settings(
        {
            "folder_paths": {
                "loras": [str(library_root)],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
            }
        }
    )

    handler = PreviewHandler(config=config)
    encoded_path = urllib.parse.quote(str(preview_file), safe="")
    request = make_mocked_request("GET", f"/api/lm/previews?path={encoded_path}")

    response = await handler.serve_preview(request)

    assert isinstance(response, web.FileResponse)
    assert response.status == 200
    assert Path(response._path) == preview_file.resolve()


async def test_deep_symlink_discovered_on_first_access(tmp_path):
    """Test that deep symlinks are discovered on first preview access."""
    library_root = tmp_path / "library"
    library_root.mkdir()

    # Create nested structure with deep symlink at second level
    subdir = library_root / "category"
    subdir.mkdir()
    external_dir = tmp_path / "storage"
    external_dir.mkdir()
    deep_symlink = subdir / "models"
    deep_symlink.symlink_to(external_dir, target_is_directory=True)

    # Create preview file under deep symlink
    preview_file = deep_symlink / "test.png"
    preview_file.write_bytes(b"test_image")

    config = Config()
    config.apply_library_settings(
        {
            "folder_paths": {
                "loras": [str(library_root)],
                "checkpoints": [],
                "unet": [],
                "embeddings": [],
            }
        }
    )

    # Deep symlink should not be in mappings initially
    normalized_external = os.path.normpath(str(external_dir)).replace(os.sep, '/')
    assert normalized_external not in config._path_mappings

    handler = PreviewHandler(config=config)
    encoded_path = urllib.parse.quote(str(preview_file), safe="")
    request = make_mocked_request("GET", f"/api/lm/previews?path={encoded_path}")

    # First access should trigger symlink discovery and serve the preview
    response = await handler.serve_preview(request)

    assert isinstance(response, web.FileResponse)
    assert response.status == 200
    assert Path(response._path) == preview_file.resolve()

    # Deep symlink should now be in mappings
    assert normalized_external in config._path_mappings
