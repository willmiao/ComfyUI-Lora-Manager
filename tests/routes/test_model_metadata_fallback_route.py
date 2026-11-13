"""Route contract for the degraded ``/metadata`` response.

The model modal relies on the cached payload the service returns when the
sidecar is unreadable, together with the ``partial`` / ``offline`` flags that
tell the UI why the payload is incomplete.
"""

import json
import logging

from py.routes.handlers.model_handlers import ModelQueryHandler


class DummyRequest:
    def __init__(self, query=None):
        self.query = query or {}


class StubService:
    model_type = "lora"

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = []

    async def get_model_metadata_with_fallback(self, file_path):
        self.calls.append(file_path)
        if self._error is not None:
            raise self._error
        return self._result


def make_handler(service):
    return ModelQueryHandler(service=service, logger=logging.getLogger("test"))


async def test_returns_partial_payload_with_provenance_flags():
    service = StubService(
        result=(
            {
                "id": 42,
                "modelId": 7,
                "name": "v2.0",
                "creator": {"username": "artist"},
                "model": {"type": "LORA", "allowNoCredit": False},
            },
            True,
            True,
        )
    )
    response = await make_handler(service).get_model_metadata(
        DummyRequest({"file_path": "models/offline.safetensors"})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["success"] is True
    assert payload["partial"] is True
    assert payload["offline"] is True
    assert payload["metadata"]["creator"] == {"username": "artist"}
    assert service.calls == ["models/offline.safetensors"]


async def test_full_metadata_reports_no_degradation():
    service = StubService(result=({"name": "v1.0"}, False, False))
    response = await make_handler(service).get_model_metadata(
        DummyRequest({"file_path": "models/online.safetensors"})
    )
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["partial"] is False
    assert payload["offline"] is False


async def test_missing_everywhere_still_404s():
    service = StubService(result=(None, False, True))
    response = await make_handler(service).get_model_metadata(
        DummyRequest({"file_path": "models/gone.safetensors"})
    )

    assert response.status == 404


async def test_missing_file_path_is_rejected():
    service = StubService(result=({}, False, False))
    response = await make_handler(service).get_model_metadata(DummyRequest({}))

    assert response.status == 400


async def test_service_failure_maps_to_500():
    service = StubService(error=RuntimeError("boom"))
    response = await make_handler(service).get_model_metadata(
        DummyRequest({"file_path": "models/offline.safetensors"})
    )

    assert response.status == 500
