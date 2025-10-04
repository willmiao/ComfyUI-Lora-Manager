import urllib.parse
from pathlib import Path

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
