"""Snapshot tests for API response formats using Syrupy.

These tests verify that API responses maintain consistent structure and format
by comparing against stored snapshots. This catches unexpected changes to
response schemas.
"""

from __future__ import annotations

import json
import pytest
from types import SimpleNamespace
from syrupy import SnapshotAssertion

from py.routes.handlers.misc_handlers import (
    ModelLibraryHandler,
    NodeRegistry,
    NodeRegistryHandler,
    ServiceRegistryAdapter,
    SettingsHandler,
)
from py.utils.utils import calculate_recipe_fingerprint, sanitize_folder_name


class FakeRequest:
    """Fake HTTP request for testing."""

    def __init__(self, *, json_data=None, query=None):
        self._json_data = json_data or {}
        self.query = query or {}

    async def json(self):
        return self._json_data


class DummySettings:
    """Dummy settings service for testing."""

    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


async def noop_async(*_args, **_kwargs):
    """No-op async function."""
    return None


class FakePromptServer:
    """Fake prompt server for testing."""

    sent = []

    class Instance:
        def send_sync(self, event, payload):
            FakePromptServer.sent.append((event, payload))

    instance = Instance()


class TestSettingsHandlerSnapshots:
    """Snapshot tests for SettingsHandler responses."""

    @pytest.mark.asyncio
    async def test_get_settings_response_format(self, snapshot: SnapshotAssertion):
        """Verify get_settings response format matches snapshot."""
        settings_service = DummySettings({
            "civitai_api_key": "test-key",
            "language": "en",
            "theme": "dark"
        })
        handler = SettingsHandler(
            settings_service=settings_service,
            metadata_provider_updater=noop_async,
            downloader_factory=lambda: None,
        )

        response = await handler.get_settings(FakeRequest())
        payload = json.loads(response.text)

        assert payload == snapshot

    @pytest.mark.asyncio
    async def test_update_settings_success_response(self, snapshot: SnapshotAssertion):
        """Verify successful update_settings response format."""
        settings_service = DummySettings()
        handler = SettingsHandler(
            settings_service=settings_service,
            metadata_provider_updater=noop_async,
            downloader_factory=lambda: None,
        )

        request = FakeRequest(json_data={"language": "zh"})
        response = await handler.update_settings(request)
        payload = json.loads(response.text)

        assert payload == snapshot


class TestNodeRegistryHandlerSnapshots:
    """Snapshot tests for NodeRegistryHandler responses."""

    @pytest.mark.asyncio
    async def test_register_nodes_success_response(self, snapshot: SnapshotAssertion):
        """Verify successful register_nodes response format."""
        node_registry = NodeRegistry()
        handler = NodeRegistryHandler(
            node_registry=node_registry,
            prompt_server=FakePromptServer,
            standalone_mode=False,
        )

        request = FakeRequest(
            json_data={
                "nodes": [
                    {
                        "node_id": 1,
                        "graph_id": "root",
                        "type": "Lora Loader (LoraManager)",
                        "title": "Test Loader",
                    }
                ]
            }
        )

        response = await handler.register_nodes(request)
        payload = json.loads(response.text)

        assert payload == snapshot

    @pytest.mark.asyncio
    async def test_register_nodes_error_response(self, snapshot: SnapshotAssertion):
        """Verify error register_nodes response format."""
        node_registry = NodeRegistry()
        handler = NodeRegistryHandler(
            node_registry=node_registry,
            prompt_server=FakePromptServer,
            standalone_mode=False,
        )

        request = FakeRequest(json_data={"nodes": []})
        response = await handler.register_nodes(request)
        payload = json.loads(response.text)

        assert payload == snapshot


class TestUtilityFunctionSnapshots:
    """Snapshot tests for utility function outputs."""

    def test_sanitize_folder_name_various_inputs(self, snapshot: SnapshotAssertion):
        """Verify sanitize_folder_name produces expected outputs."""
        test_inputs = [
            "normal_folder",
            "folder with spaces",
            "folder/with/slashes",
            'folder\\with\\backslashes',
            'folder<with>brackets',
            'folder"with"quotes',
            'folder|with|pipes',
            'folder?with?questions',
            'folder*with*asterisks',
            '',
            '   spaces   ',
            'folder.with.dots',
            '___underscores___',
        ]

        results = {input_name: sanitize_folder_name(input_name) for input_name in test_inputs}
        assert results == snapshot

    def test_calculate_recipe_fingerprint_various_inputs(self, snapshot: SnapshotAssertion):
        """Verify calculate_recipe_fingerprint produces expected outputs."""
        test_cases = [
            [],
            [{"hash": "abc123", "strength": 1.0}],
            [
                {"hash": "abc123", "strength": 1.0},
                {"hash": "def456", "strength": 0.75},
            ],
            [
                {"hash": "DEF456", "strength": 1.0},
                {"hash": "ABC123", "strength": 0.5},
            ],
            [{"hash": "abc123", "weight": 0.8}],
            [{"modelVersionId": 12345, "strength": 1.0}],
            [{"hash": "abc123", "exclude": True, "strength": 1.0}],
            [{"hash": "", "strength": 1.0}],
            [{"strength": 1.0}],
        ]

        results = [calculate_recipe_fingerprint(loras) for loras in test_cases]
        assert results == snapshot


class TestModelLibraryHandlerSnapshots:
    """Snapshot tests for ModelLibraryHandler responses."""

    @pytest.mark.asyncio
    async def test_check_model_exists_empty_response(self, snapshot: SnapshotAssertion):
        """Verify check_model_exists with no versions response format."""

        class EmptyVersionScanner:
            async def check_model_version_exists(self, _version_id):
                return False

            async def get_model_versions_by_id(self, _model_id):
                return []

        async def scanner_factory():
            return EmptyVersionScanner()

        handler = ModelLibraryHandler(
            ServiceRegistryAdapter(
                get_lora_scanner=scanner_factory,
                get_checkpoint_scanner=scanner_factory,
                get_embedding_scanner=scanner_factory,
            ),
            metadata_provider_factory=lambda: None,
        )

        response = await handler.check_model_exists(FakeRequest(query={"modelId": "1"}))
        payload = json.loads(response.text)

        assert payload == snapshot
