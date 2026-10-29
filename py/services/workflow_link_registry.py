"""In-memory registry of LM-linked workflows currently open in ComfyUI tabs.

The ComfyUI-side extension reports the active graph's provenance marker
(``extra.lm_source``: file path, document hash, dirty flag) whenever it
changes — load, tab switch, first edit, successful write-back. The LM web UI
consumes this to enable/disable the card context menu's "Update from
ComfyUI" entry, and to route the write-back request to the ComfyUI tab that
actually holds the workflow.

State is per ComfyUI client (browser tab, identified by its websocket sid)
and lives only in memory: a restarted server simply starts empty, and stale
entries are pruned against the live socket set on read.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkflowLinkRegistry:
    """Per-client state of LM-managed workflows open in ComfyUI."""

    _instance: Optional["WorkflowLinkRegistry"] = None
    _instance_lock: Optional[asyncio.Lock] = None

    def __init__(self) -> None:
        # sid -> {"file_path", "sha256", "dirty", "name", "reported_at"}
        self._states: Dict[str, Dict[str, Any]] = {}
        # request_id -> Future resolved by the collect-result endpoint
        self._collect_futures: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "WorkflowLinkRegistry":
        if cls._instance is None:
            if cls._instance_lock is None:
                cls._instance_lock = asyncio.Lock()
            async with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = WorkflowLinkRegistry()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Drop the singleton (test isolation)."""
        cls._instance = None

    async def report_state(
        self, sid: str, state: Optional[Dict[str, Any]]
    ) -> None:
        """Store (or clear, when ``state`` is None) a client's link state."""
        async with self._lock:
            if state is None:
                self._states.pop(sid, None)
                return
            self._states[sid] = {
                "file_path": state.get("file_path"),
                "sha256": state.get("sha256"),
                "dirty": bool(state.get("dirty")),
                "name": state.get("name") or "",
                "reported_at": time.time(),
            }

    async def get_states(
        self, active_sids: Optional[set] = None
    ) -> List[Dict[str, Any]]:
        """Return all known link states, pruning disconnected clients."""
        async with self._lock:
            if active_sids is not None:
                for sid in list(self._states):
                    if sid not in active_sids:
                        del self._states[sid]
            return [
                {"client_id": sid, **state}
                for sid, state in self._states.items()
            ]

    async def find_client_for(
        self, file_path: str, active_sids: Optional[set] = None
    ) -> Optional[str]:
        """Sid of a client holding *file_path*; dirty holders win."""
        states = await self.get_states(active_sids)
        fallback: Optional[str] = None
        for state in states:
            if state.get("file_path") != file_path:
                continue
            if state.get("dirty"):
                return state["client_id"]
            fallback = fallback or state["client_id"]
        return fallback

    def begin_collect(self) -> tuple[str, "asyncio.Future"]:
        """Create a pending collect request; the id rides the WS message."""
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._collect_futures[request_id] = future
        return request_id, future

    async def resolve_collect(
        self, request_id: str, result: Dict[str, Any]
    ) -> bool:
        """Resolve a pending collect request. False when unknown/expired."""
        future = self._collect_futures.pop(request_id, None)
        if future is None or future.done():
            return False
        future.set_result(result)
        return True

    async def await_collect(
        self, request_id: str, future: "asyncio.Future", timeout: float
    ) -> Dict[str, Any]:
        """Await a collect result; on timeout return a synthetic error."""
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._collect_futures.pop(request_id, None)
            return {"success": False, "error": "timeout"}
