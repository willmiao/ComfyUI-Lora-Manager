from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import aiohttp

from .downloader import DownloadProgress, get_downloader
from .aria2_transfer_state import Aria2TransferStateStore
from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)

CIVITAI_DOWNLOAD_URL_PREFIXES = (
    "https://civitai.com/api/download/",
    "https://civitai.red/api/download/",
)


class Aria2Error(RuntimeError):
    """Raised when aria2 integration fails."""


@dataclass
class Aria2Transfer:
    """Track an aria2 download registered by the Python coordinator."""

    gid: str
    save_path: str


class Aria2Downloader:
    """Manage an aria2 RPC daemon for experimental model downloads."""

    _instance = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "Aria2Downloader":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._process: Optional[asyncio.subprocess.Process] = None
        self._rpc_port: Optional[int] = None
        self._rpc_secret = ""
        self._rpc_url = ""
        self._rpc_session: Optional[aiohttp.ClientSession] = None
        self._rpc_session_lock = asyncio.Lock()
        self._process_lock = asyncio.Lock()
        self._transfers: Dict[str, Aria2Transfer] = {}
        self._poll_interval = 0.5
        self._state_store = Aria2TransferStateStore()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def download_file(
        self,
        url: str,
        save_path: str,
        *,
        download_id: str,
        progress_callback=None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str]:
        """Download a file using aria2 RPC and wait for completion."""

        await self._ensure_process()
        save_path = os.path.abspath(save_path)
        transfer = self._transfers.get(download_id)
        if transfer is None or os.path.abspath(transfer.save_path) != save_path:
            gid = await self._schedule_download(
                url,
                save_path,
                download_id=download_id,
                headers=headers,
            )
            transfer = Aria2Transfer(gid=gid, save_path=save_path)
            self._transfers[download_id] = transfer

        try:
            while True:
                status = await self.get_status(download_id)
                if status is None:
                    return False, "aria2 download not found"

                snapshot = self._build_progress_snapshot(status)
                if progress_callback is not None:
                    await self._dispatch_progress(progress_callback, snapshot)

                state = status.get("status", "")
                if state == "complete":
                    completed_path = self._resolve_completed_path(status, save_path)
                    return True, completed_path
                if state == "error":
                    return False, status.get("errorMessage") or "aria2 download failed"
                if state == "removed":
                    return False, "Download was cancelled"

                await asyncio.sleep(self._poll_interval)
        finally:
            self._transfers.pop(download_id, None)

    async def _schedule_download(
        self,
        url: str,
        save_path: str,
        *,
        download_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        save_dir = os.path.dirname(save_path)
        out_name = os.path.basename(save_path)

        Path(save_dir).mkdir(parents=True, exist_ok=True)

        resolved_url = url
        request_headers = headers
        if headers and url.startswith(CIVITAI_DOWNLOAD_URL_PREFIXES):
            resolved_url = await self._resolve_authenticated_redirect_url(url, headers)
            if resolved_url != url:
                request_headers = None
                logger.debug(
                    "Resolved Civitai download %s to signed URL for aria2",
                    download_id,
                )

        options: Dict[str, str] = {
            "dir": save_dir,
            "out": out_name,
            "continue": "true",
            "max-connection-per-server": "4",
            "split": "4",
            "min-split-size": "1M",
            "allow-overwrite": "true",
            "auto-file-renaming": "false",
            "file-allocation": "none",
        }
        if request_headers:
            options["header"] = [
                f"{key}: {value}" for key, value in request_headers.items()
            ]

        logger.debug(
            "Submitting aria2 download %s -> %s (auth=%s, civitai_signed=%s)",
            download_id,
            save_path,
            bool(request_headers),
            resolved_url != url,
        )

        try:
            gid = await self._rpc_call("aria2.addUri", [[resolved_url], options])
        except Exception as exc:
            raise Aria2Error(f"Failed to schedule aria2 download: {exc}") from exc

        logger.debug("aria2 accepted download %s with gid %s", download_id, gid)
        await self._state_store.upsert(
            download_id,
            {
                "gid": gid,
                "save_path": save_path,
                "status": "downloading",
                "url": url,
            },
        )
        return gid

    async def get_status(self, download_id: str) -> Optional[Dict[str, Any]]:
        """Return the raw aria2 status payload for a known download."""

        transfer = self._transfers.get(download_id)
        if transfer is None:
            return None

        keys = [
            "gid",
            "status",
            "totalLength",
            "completedLength",
            "downloadSpeed",
            "errorMessage",
            "files",
        ]
        try:
            status = await self._rpc_call("aria2.tellStatus", [transfer.gid, keys])
        except Exception as exc:
            raise Aria2Error(f"Failed to query aria2 download status: {exc}") from exc

        if isinstance(status, dict):
            return status
        return None

    async def get_status_by_gid(self, gid: str) -> Optional[Dict[str, Any]]:
        keys = [
            "gid",
            "status",
            "totalLength",
            "completedLength",
            "downloadSpeed",
            "errorMessage",
            "files",
        ]
        try:
            status = await self._rpc_call("aria2.tellStatus", [gid, keys])
        except Exception as exc:
            message = str(exc)
            if "cannot be found" in message.lower() or "not found" in message.lower():
                return None
            raise Aria2Error(f"Failed to query aria2 download status: {exc}") from exc

        if isinstance(status, dict):
            return status
        return None

    async def restore_transfer(self, download_id: str, gid: str, save_path: str) -> None:
        await self._ensure_process()
        self._transfers[download_id] = Aria2Transfer(
            gid=gid,
            save_path=os.path.abspath(save_path),
        )

    async def reassign_transfer(
        self, from_download_id: str, to_download_id: str
    ) -> Optional[Aria2Transfer]:
        transfer = self._transfers.get(from_download_id)
        if transfer is None:
            return None

        self._transfers[to_download_id] = transfer
        if from_download_id != to_download_id:
            self._transfers.pop(from_download_id, None)
        return transfer

    async def has_transfer(self, download_id: str) -> bool:
        return download_id in self._transfers

    async def pause_download(self, download_id: str) -> Dict[str, Any]:
        transfer = self._transfers.get(download_id)
        if transfer is None:
            return {"success": False, "error": "Download task not found"}

        try:
            await self._rpc_call("aria2.forcePause", [transfer.gid])
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        await self._state_store.upsert(download_id, {"status": "paused"})
        return {"success": True, "message": "Download paused successfully"}

    async def resume_download(self, download_id: str) -> Dict[str, Any]:
        transfer = self._transfers.get(download_id)
        if transfer is None:
            return {"success": False, "error": "Download task not found"}

        try:
            await self._rpc_call("aria2.unpause", [transfer.gid])
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        await self._state_store.upsert(download_id, {"status": "downloading"})
        return {"success": True, "message": "Download resumed successfully"}

    async def cancel_download(self, download_id: str) -> Dict[str, Any]:
        transfer = self._transfers.get(download_id)
        if transfer is None:
            return {"success": False, "error": "Download task not found"}

        try:
            await self._rpc_call("aria2.forceRemove", [transfer.gid])
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        await self._state_store.remove(download_id)
        return {"success": True, "message": "Download cancelled successfully"}

    async def close(self) -> None:
        """Shut down the RPC process and session."""

        if self._rpc_session is not None:
            await self._rpc_session.close()
            self._rpc_session = None

        process = self._process
        self._process = None
        self._transfers.clear()

        if process is None:
            return

        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def _dispatch_progress(self, callback, snapshot: DownloadProgress) -> None:
        try:
            result = callback(snapshot, snapshot)
        except TypeError:
            result = callback(snapshot.percent_complete)

        if asyncio.iscoroutine(result):
            await result
        elif hasattr(result, "__await__"):
            await result

    def _build_progress_snapshot(self, status: Dict[str, Any]) -> DownloadProgress:
        completed = self._parse_int(status.get("completedLength"))
        total = self._parse_int(status.get("totalLength"))
        speed = float(self._parse_int(status.get("downloadSpeed")))
        percent = 0.0
        if total > 0:
            percent = (completed / total) * 100.0

        return DownloadProgress(
            percent_complete=max(0.0, min(percent, 100.0)),
            bytes_downloaded=completed,
            total_bytes=total or None,
            bytes_per_second=speed,
            timestamp=datetime.now().timestamp(),
        )

    def _resolve_completed_path(self, status: Dict[str, Any], default_path: str) -> str:
        files = status.get("files")
        if isinstance(files, list) and files:
            first = files[0]
            if isinstance(first, dict):
                candidate = first.get("path")
                if isinstance(candidate, str) and candidate:
                    return candidate
        return default_path

    @staticmethod
    def _parse_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    async def _resolve_authenticated_redirect_url(
        self,
        url: str,
        headers: Dict[str, str],
    ) -> str:
        downloader = await get_downloader()
        session = await downloader.session
        request_headers = dict(downloader.default_headers)
        request_headers.update(headers)
        request_headers["Accept-Encoding"] = "identity"

        try:
            async with session.get(
                url,
                headers=request_headers,
                allow_redirects=False,
                proxy=downloader.proxy_url,
            ) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if location:
                        return location
                    raise Aria2Error(
                        "Authenticated Civitai redirect did not include a Location header"
                    )

                if response.status == 200:
                    return url

                body = await response.text()
                raise Aria2Error(
                    f"Failed to resolve authenticated Civitai redirect: status={response.status} body={body[:300]}"
                )
        except aiohttp.ClientError as exc:
            raise Aria2Error(
                f"Failed to resolve authenticated Civitai redirect: {exc}"
            ) from exc

    async def _ensure_process(self) -> None:
        async with self._process_lock:
            if self.is_running and await self._ping():
                return

            await self.close()

            executable = self._resolve_executable()
            self._rpc_port = self._find_free_port()
            self._rpc_secret = secrets.token_hex(16)
            self._rpc_url = f"http://127.0.0.1:{self._rpc_port}/jsonrpc"

            command = [
                executable,
                "--enable-rpc=true",
                "--rpc-listen-all=false",
                f"--rpc-listen-port={self._rpc_port}",
                f"--rpc-secret={self._rpc_secret}",
                "--check-certificate=true",
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
                "--file-allocation=none",
                "--max-concurrent-downloads=5",
                "--continue=true",
                "--daemon=false",
                "--quiet=true",
                f"--stop-with-process={os.getpid()}",
            ]

            logger.info("Starting aria2 RPC daemon from %s", executable)
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            await self._wait_until_ready()

    def _resolve_executable(self) -> str:
        settings = get_settings_manager()
        configured_path = (settings.get("aria2c_path") or "").strip()
        candidate = configured_path or "aria2c"

        resolved = shutil.which(candidate)
        if resolved:
            return resolved

        if configured_path and os.path.isfile(configured_path) and os.access(
            configured_path, os.X_OK
        ):
            return configured_path

        raise Aria2Error(
            "aria2c executable was not found. Install aria2 or configure aria2c_path."
        )

    async def _wait_until_ready(self) -> None:
        assert self._process is not None

        start_time = asyncio.get_running_loop().time()
        last_error = ""
        while asyncio.get_running_loop().time() - start_time < 10.0:
            if self._process.returncode is not None:
                stderr_output = ""
                if self._process.stderr is not None:
                    try:
                        stderr_output = (
                            await asyncio.wait_for(self._process.stderr.read(), timeout=0.2)
                        ).decode("utf-8", errors="replace")
                    except Exception:
                        stderr_output = ""
                raise Aria2Error(
                    f"aria2 RPC process exited early with code {self._process.returncode}: {stderr_output.strip()}"
                )

            try:
                if await self._ping():
                    return
            except Exception as exc:  # pragma: no cover - startup race
                last_error = str(exc)

            await asyncio.sleep(0.2)

        raise Aria2Error(
            f"Timed out waiting for aria2 RPC to become ready{': ' + last_error if last_error else ''}"
        )

    async def _ping(self) -> bool:
        try:
            result = await self._rpc_call("aria2.getVersion", [])
        except Exception:
            return False

        return isinstance(result, dict)

    async def _rpc_call(self, method: str, params: list[Any]) -> Any:
        if not self._rpc_url:
            raise Aria2Error("aria2 RPC endpoint is not initialized")

        session = await self._get_rpc_session()
        payload = {
            "jsonrpc": "2.0",
            "id": secrets.token_hex(8),
            "method": method,
            "params": [f"token:{self._rpc_secret}", *params],
        }

        async with session.post(self._rpc_url, json=payload) as response:
            text = await response.text()

        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = None

        if body is None:
            if response.status != 200:
                raise Aria2Error(
                    f"aria2 RPC returned status {response.status} with non-JSON body: {text}"
                )
            raise Aria2Error(f"Invalid aria2 RPC response: {text}")

        if "error" in body:
            error = body["error"] or {}
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else str(error)
            logger.error(
                "aria2 RPC %s failed with HTTP %s, code=%s, message=%s",
                method,
                response.status,
                code,
                message,
            )
            status_message = (
                f"aria2 RPC {method} failed with status {response.status}: {message}"
                if response.status != 200
                else message
            )
            raise Aria2Error(status_message or "Unknown aria2 RPC error")

        if response.status != 200:
            logger.error(
                "aria2 RPC %s returned unexpected HTTP status %s without error payload: %s",
                method,
                response.status,
                body,
            )
            raise Aria2Error(
                f"aria2 RPC {method} returned unexpected status {response.status}"
            )

        return body.get("result")

    async def _get_rpc_session(self) -> aiohttp.ClientSession:
        if self._rpc_session is None or self._rpc_session.closed:
            async with self._rpc_session_lock:
                if self._rpc_session is None or self._rpc_session.closed:
                    timeout = aiohttp.ClientTimeout(total=30)
                    self._rpc_session = aiohttp.ClientSession(timeout=timeout)
        return self._rpc_session

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            return int(sock.getsockname()[1])


async def get_aria2_downloader() -> Aria2Downloader:
    """Get the singleton aria2 downloader."""

    return await Aria2Downloader.get_instance()
