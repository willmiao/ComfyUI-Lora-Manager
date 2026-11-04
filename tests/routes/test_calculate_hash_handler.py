"""Tests for the on-demand hash calculation endpoint handler.

Checkpoint and other-model scans defer hashing (``hash_status="pending"``);
the model modal calls ``POST /api/lm/{prefix}/calculate-hash`` so the hash can
be shown and searched on other sites without waiting for a rescan.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from py.routes.handlers.model_handlers import ModelManagementHandler

FILE_PATH = "/models/checkpoints/demo.safetensors"
SHA256 = "a" * 64


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload
        self.query = {}

    async def json(self):
        return self._payload


class FakeJsonErrorRequest(FakeRequest):
    async def json(self):
        raise ValueError("invalid JSON")


class HashingScanner:
    """Scanner double implementing the lazy-hash scanner surface."""

    def __init__(self, entries, result=SHA256):
        self._cache = SimpleNamespace(raw_data=entries)
        self._result = result
        self.hash_calls = []
        self.persist_calls = 0

    async def get_cached_data(self, force_refresh: bool = False):
        return self._cache

    async def calculate_hash_for_model(self, file_path):
        self.hash_calls.append(file_path)
        return self._result

    async def _persist_current_cache(self):
        self.persist_calls += 1


class PlainScanner:
    """Scanner double without on-demand hashing (LoRA-style scanners)."""

    def __init__(self, entries):
        self._cache = SimpleNamespace(raw_data=entries)

    async def get_cached_data(self, force_refresh: bool = False):
        return self._cache


class FakeService:
    def __init__(self, scanner):
        self.scanner = scanner
        self.metadata_class = object

    async def format_response(self, model_data):
        return {
            "file_path": model_data["file_path"],
            "sha256": model_data.get("sha256", ""),
            "hash_status": model_data.get("hash_status", "completed"),
        }


def pending_entry() -> dict:
    return {"file_path": FILE_PATH, "sha256": "", "hash_status": "pending"}


def make_handler(scanner) -> ModelManagementHandler:
    return ModelManagementHandler(
        service=FakeService(scanner),
        logger=logging.getLogger(__name__),
        metadata_sync=None,
        preview_service=None,
        tag_update_service=None,
        lifecycle_service=None,
    )


@pytest.mark.asyncio
async def test_calculates_hash_and_persists_cache():
    scanner = HashingScanner([pending_entry()])
    handler = make_handler(scanner)

    response = await handler.calculate_model_hash(
        FakeRequest({"file_path": FILE_PATH})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["sha256"] == SHA256
    assert payload["hash_status"] == "completed"
    assert payload["metadata"]["sha256"] == SHA256
    assert payload["metadata"]["hash_status"] == "completed"
    assert scanner.hash_calls == [FILE_PATH]
    # The in-memory entry is refreshed so the list endpoint reflects the hash.
    assert scanner._cache.raw_data[0]["sha256"] == SHA256.lower()
    assert scanner._cache.raw_data[0]["hash_status"] == "completed"
    # The persistent cache is written so the hash survives a restart.
    assert scanner.persist_calls == 1


@pytest.mark.asyncio
async def test_returns_existing_hash_without_recalculating():
    scanner = HashingScanner(
        [{"file_path": FILE_PATH, "sha256": SHA256, "hash_status": "completed"}]
    )
    handler = make_handler(scanner)

    response = await handler.calculate_model_hash(
        FakeRequest({"file_path": FILE_PATH})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload == {
        "success": True,
        "sha256": SHA256,
        "hash_status": "completed",
    }
    assert scanner.hash_calls == []
    assert scanner.persist_calls == 0


@pytest.mark.asyncio
async def test_requires_file_path():
    handler = make_handler(HashingScanner([]))

    response = await handler.calculate_model_hash(FakeRequest({}))
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_tolerates_unparseable_body():
    handler = make_handler(HashingScanner([]))

    response = await handler.calculate_model_hash(FakeJsonErrorRequest(None))
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_unknown_model_returns_not_found():
    handler = make_handler(HashingScanner([]))

    response = await handler.calculate_model_hash(
        FakeRequest({"file_path": "/models/missing.safetensors"})
    )
    payload = json.loads(response.text)

    assert response.status == 404
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_unsupported_scanner_returns_client_error():
    scanner = PlainScanner([pending_entry()])
    handler = make_handler(scanner)

    response = await handler.calculate_model_hash(
        FakeRequest({"file_path": FILE_PATH})
    )
    payload = json.loads(response.text)

    assert response.status == 400
    assert payload["success"] is False
    assert "not supported" in payload["error"]


@pytest.mark.asyncio
async def test_failed_calculation_reports_failure():
    scanner = HashingScanner([pending_entry()], result=None)
    handler = make_handler(scanner)

    response = await handler.calculate_model_hash(
        FakeRequest({"file_path": FILE_PATH})
    )
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload["success"] is False
    assert payload["hash_status"] == "failed"
    assert scanner.persist_calls == 0
    assert scanner._cache.raw_data[0]["hash_status"] == "pending"
