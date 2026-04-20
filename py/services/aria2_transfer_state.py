from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from typing import Any, Dict, Optional

from ..utils.cache_paths import get_cache_base_dir


def get_aria2_state_path() -> str:
    base_dir = get_cache_base_dir(create=True)
    state_dir = os.path.join(base_dir, "aria2")
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, "downloads.json")


class Aria2TransferStateStore:
    """Persist aria2 transfer metadata needed for restart recovery."""

    _locks_by_path: Dict[str, asyncio.Lock] = {}

    def __init__(self, state_path: Optional[str] = None) -> None:
        self._state_path = os.path.abspath(state_path or get_aria2_state_path())
        self._lock = self._locks_by_path.setdefault(self._state_path, asyncio.Lock())

    def _read_all_unlocked(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self._state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}

        if not isinstance(data, dict):
            return {}

        normalized: Dict[str, Dict[str, Any]] = {}
        for download_id, entry in data.items():
            if isinstance(download_id, str) and isinstance(entry, dict):
                normalized[download_id] = entry
        return normalized

    def _write_all_unlocked(self, data: Dict[str, Dict[str, Any]]) -> None:
        directory = os.path.dirname(self._state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        temp_path = f"{self._state_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)
        os.replace(temp_path, self._state_path)

    async def load_all(self) -> Dict[str, Dict[str, Any]]:
        async with self._lock:
            return deepcopy(self._read_all_unlocked())

    async def get(self, download_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return deepcopy(self._read_all_unlocked().get(download_id))

    async def upsert(self, download_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            data = self._read_all_unlocked()
            current = data.get(download_id, {})
            current.update(payload)
            data[download_id] = current
            self._write_all_unlocked(data)
            return deepcopy(current)

    async def remove(self, download_id: str) -> None:
        async with self._lock:
            data = self._read_all_unlocked()
            if download_id in data:
                del data[download_id]
                self._write_all_unlocked(data)

    async def find_by_save_path(
        self, save_path: str, *, exclude_download_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        normalized_target = os.path.abspath(save_path)
        async with self._lock:
            data = self._read_all_unlocked()
            for download_id, entry in data.items():
                if exclude_download_id and download_id == exclude_download_id:
                    continue
                candidate = entry.get("save_path")
                if isinstance(candidate, str) and os.path.abspath(candidate) == normalized_target:
                    result = dict(entry)
                    result["download_id"] = download_id
                    return result
        return None

    async def reassign(self, from_download_id: str, to_download_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            data = self._read_all_unlocked()
            existing = data.get(from_download_id)
            if existing is None:
                return None
            updated = dict(existing)
            updated["download_id"] = to_download_id
            data[to_download_id] = updated
            if from_download_id != to_download_id:
                data.pop(from_download_id, None)
            self._write_all_unlocked(data)
            return deepcopy(updated)
