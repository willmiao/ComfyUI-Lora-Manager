"""Tests for the models_changed WebSocket broadcast helper."""

import asyncio

import pytest

from py.routes.handlers import model_handlers


@pytest.mark.asyncio
async def test_broadcast_models_changed_payload(monkeypatch):
    """The helper must broadcast the models_changed event to all clients."""
    sent = []

    async def fake_broadcast(data):
        sent.append(data)

    monkeypatch.setattr(
        "py.services.websocket_manager.ws_manager.broadcast", fake_broadcast
    )
    # Give the create_task a chance to run.
    for _ in range(10):
        await asyncio.sleep(0)

    model_handlers._broadcast_models_changed()
    await asyncio.sleep(0)
    assert sent == [{"type": "models_changed"}]


@pytest.mark.asyncio
async def test_broadcast_models_changed_survives_broadcast_failure(monkeypatch):
    """A failing broadcast must not raise out of the mutation handler."""
    async def fake_broadcast(data):
        raise RuntimeError("socket closed")

    monkeypatch.setattr(
        "py.services.websocket_manager.ws_manager.broadcast", fake_broadcast
    )
    model_handlers._broadcast_models_changed()
    await asyncio.sleep(0)
