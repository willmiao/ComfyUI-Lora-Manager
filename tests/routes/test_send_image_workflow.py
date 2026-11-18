"""Tests for sending LoRA Manager images to ComfyUI image nodes."""

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from py.routes.handlers import misc_handlers
from py.routes.handlers.misc_handlers import NodeRegistry, NodeRegistryHandler


class FakeRequest:
    def __init__(self, *, json_data=None):
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data


class RecordingPromptServer:
    sent = []

    class Instance:
        sockets = {}

        def send_sync(self, event, payload, sid=None):
            RecordingPromptServer.sent.append((event, payload))

    instance = Instance()


def _json_payload(response):
    return json.loads(response.text)


def _png_bytes(color=(255, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def prompt_server():
    RecordingPromptServer.sent = []
    return RecordingPromptServer


@pytest.fixture
def handler(tmp_path, monkeypatch, prompt_server):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    import folder_paths

    monkeypatch.setattr(
        folder_paths,
        "get_input_directory",
        lambda: str(input_dir),
        raising=False,
    )
    monkeypatch.setattr(
        misc_handlers.config,
        "is_preview_path_allowed",
        lambda _path: True,
    )

    return NodeRegistryHandler(
        node_registry=NodeRegistry(),
        prompt_server=prompt_server,  # pyright: ignore[reportArgumentType]
        standalone_mode=False,
    )


@pytest.mark.asyncio
async def test_send_image_materializes_and_broadcasts(handler, tmp_path, prompt_server):
    source = tmp_path / "source.png"
    source.write_bytes(_png_bytes())

    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {"path": str(source)},
                "node_ids": [{"node_id": 7, "graph_id": "root"}],
            }
        )
    )
    payload = _json_payload(response)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["value"].startswith("lm_")
    assert (tmp_path / "input" / payload["value"]).is_file()

    assert len(prompt_server.sent) == 1
    event, message = prompt_server.sent[0]
    assert event == "lm_widget_update"
    assert message == {
        "id": 7,
        "graph_id": "root",
        "action": "set_image",
        "value": payload["value"],
    }


@pytest.mark.asyncio
async def test_send_image_deduplicates_by_content(handler, tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(_png_bytes())

    request = FakeRequest(  # pyright: ignore[reportArgumentType]
        json_data={
            "source": {"path": str(source)},
            "node_ids": [{"node_id": 7, "graph_id": "root"}],
        }
    )

    first = _json_payload(await handler.send_image_to_workflow(request))
    second = _json_payload(await handler.send_image_to_workflow(request))

    assert first["value"] == second["value"]
    files = [
        path
        for path in (tmp_path / "input").iterdir()
        if path.is_file() and path.suffix == ".png"
    ]
    assert len(files) == 1


@pytest.mark.asyncio
async def test_send_image_reuses_file_already_in_input(handler, tmp_path):
    input_dir = tmp_path / "input"
    existing = input_dir / "existing.png"
    existing.write_bytes(_png_bytes())

    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {"path": str(existing)},
                "node_ids": [{"node_id": 3, "graph_id": "root"}],
            }
        )
    )
    payload = _json_payload(response)

    assert response.status == 200
    assert payload["value"] == "existing.png"
    assert not any(path.name.startswith("lm_") for path in input_dir.iterdir())


@pytest.mark.asyncio
async def test_send_image_resolves_example_static_url(
    handler, tmp_path, monkeypatch
):
    example_root = tmp_path / "examples"
    image_path = example_root / "model" / "image_0.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(_png_bytes())

    monkeypatch.setattr(
        misc_handlers,
        "get_settings_manager",
        lambda: SimpleNamespace(get=lambda key, default=None: str(example_root)),
    )

    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {
                    "url": "/example_images_static/model/image_0.png"
                },
                "node_ids": [{"node_id": 1, "graph_id": "root"}],
            }
        )
    )

    assert response.status == 200
    assert _json_payload(response)["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8188/image.png",
        "http://localhost/image.png",
        "http://10.0.0.5/image.png",
        "http://192.168.1.20/image.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/image.png",
        "http://[::ffff:127.0.0.1]/image.png",
        "http://metadata.google.internal/image.png",
    ],
)
async def test_send_image_rejects_private_remote_host(handler, url):
    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {"url": url},
                "node_ids": [{"node_id": 1, "graph_id": "root"}],
            }
        )
    )

    assert response.status == 400
    assert "private network" in _json_payload(response)["error"]


class _FakeDownloader:
    def __init__(self, content):
        self._content = content
        self.requested = []

    async def download_to_memory(
        self, url, use_auth=False, return_headers=False
    ):
        self.requested.append(url)
        return True, self._content, {"content-type": "image/png"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        # Example images come from whatever host the model metadata points at:
        # CivitAI, Hugging Face, ModelScope, or an arbitrary README image host.
        "https://huggingface.co/ntc-ai/repo/resolve/main/images/example.png",
        "https://modelscope.cn/models/owner/repo/resolve/master/example.png",
        "https://example.com/image.png",
    ],
)
async def test_send_image_downloads_public_remote_image(
    handler, tmp_path, monkeypatch, url
):
    downloader = _FakeDownloader(_png_bytes())

    async def _get_downloader():
        return downloader

    monkeypatch.setattr(misc_handlers, "get_downloader", _get_downloader)

    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {"url": url},
                "node_ids": [{"node_id": 5, "graph_id": "root"}],
            }
        )
    )
    payload = _json_payload(response)

    assert response.status == 200
    assert payload["success"] is True
    assert downloader.requested == [url]
    assert (tmp_path / "input" / payload["value"]).is_file()


@pytest.mark.asyncio
async def test_send_image_rejects_non_image_bytes(handler, tmp_path):
    source = tmp_path / "not-an-image.png"
    source.write_bytes(b"not an image")

    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {"path": str(source)},
                "node_ids": [{"node_id": 1, "graph_id": "root"}],
            }
        )
    )

    assert response.status == 400
    assert "supported image" in _json_payload(response)["error"]


@pytest.mark.asyncio
async def test_send_image_rejects_example_path_traversal(
    handler, tmp_path, monkeypatch
):
    example_root = tmp_path / "examples"
    example_root.mkdir()
    (tmp_path / "secret.png").write_bytes(_png_bytes())

    monkeypatch.setattr(
        misc_handlers,
        "get_settings_manager",
        lambda: SimpleNamespace(get=lambda key, default=None: str(example_root)),
    )

    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {
                    "url": "/example_images_static/../secret.png"
                },
                "node_ids": [{"node_id": 1, "graph_id": "root"}],
            }
        )
    )

    assert response.status == 400


@pytest.mark.asyncio
async def test_send_image_is_disabled_in_standalone_mode(prompt_server):
    handler = NodeRegistryHandler(
        node_registry=NodeRegistry(),
        prompt_server=prompt_server,  # pyright: ignore[reportArgumentType]
        standalone_mode=True,
    )

    response = await handler.send_image_to_workflow(
        FakeRequest(  # pyright: ignore[reportArgumentType]
            json_data={
                "source": {"path": "/tmp/image.png"},
                "node_ids": [{"node_id": 1, "graph_id": "root"}],
            }
        )
    )

    assert response.status == 503
    assert _json_payload(response)["error"] == "Standalone Mode Active"
