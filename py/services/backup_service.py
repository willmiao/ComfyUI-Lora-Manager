from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from ..utils.cache_paths import CacheType, get_cache_base_dir, get_cache_file_path
from ..utils.settings_paths import get_settings_dir
from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


BACKUP_MANIFEST_VERSION = 1
DEFAULT_BACKUP_RETENTION_COUNT = 5
DEFAULT_BACKUP_INTERVAL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class BackupEntry:
    kind: str
    archive_path: str
    target_path: str
    sha256: str
    size: int
    mtime: float


class BackupService:
    """Create and restore user-state backup archives."""

    _instance: "BackupService | None" = None
    _instance_lock = asyncio.Lock()

    def __init__(self, *, settings_manager=None, backup_dir: str | None = None) -> None:
        self._settings = settings_manager or get_settings_manager()
        self._backup_dir = Path(backup_dir or self._resolve_backup_dir())
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._auto_task: asyncio.Task[None] | None = None

    @classmethod
    async def get_instance(cls) -> "BackupService":
        async with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            cls._instance._ensure_auto_snapshot_task()
            return cls._instance

    @staticmethod
    def _resolve_backup_dir() -> str:
        return os.path.join(get_settings_dir(create=True), "backups")

    def get_backup_dir(self) -> str:
        return str(self._backup_dir)

    def _ensure_auto_snapshot_task(self) -> None:
        if self._auto_task is not None and not self._auto_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        self._auto_task = loop.create_task(self._auto_backup_loop())

    def _get_setting_bool(self, key: str, default: bool) -> bool:
        try:
            return bool(self._settings.get(key, default))
        except Exception:
            return default

    def _get_setting_int(self, key: str, default: int) -> int:
        try:
            value = self._settings.get(key, default)
            return max(1, int(value))
        except Exception:
            return default

    def _settings_file_path(self) -> str:
        settings_file = getattr(self._settings, "settings_file", None)
        if settings_file:
            return str(settings_file)
        return os.path.join(get_settings_dir(create=True), "settings.json")

    def _download_history_path(self) -> str:
        base_dir = get_cache_base_dir(create=True)
        history_dir = os.path.join(base_dir, "download_history")
        os.makedirs(history_dir, exist_ok=True)
        return os.path.join(history_dir, "downloaded_versions.sqlite")

    def _model_update_dir(self) -> str:
        return str(Path(get_cache_file_path(CacheType.MODEL_UPDATE, create_dir=True)).parent)

    def _model_update_targets(self) -> list[tuple[str, str, str]]:
        """Return (kind, archive_path, target_path) tuples for backup."""

        targets: list[tuple[str, str, str]] = []

        settings_path = self._settings_file_path()
        targets.append(("settings", "settings/settings.json", settings_path))

        history_path = self._download_history_path()
        targets.append(
            (
                "download_history",
                "cache/download_history/downloaded_versions.sqlite",
                history_path,
            )
        )

        symlink_path = get_cache_file_path(CacheType.SYMLINK, create_dir=True)
        targets.append(
            (
                "symlink_map",
                "cache/symlink/symlink_map.json",
                symlink_path,
            )
        )

        model_update_dir = Path(self._model_update_dir())
        if model_update_dir.exists():
            for sqlite_file in sorted(model_update_dir.glob("*.sqlite")):
                targets.append(
                    (
                        "model_update",
                        f"cache/model_update/{sqlite_file.name}",
                        str(sqlite_file),
                    )
                )

        return targets

    @staticmethod
    def _hash_file(path: str) -> tuple[str, int, float]:
        digest = hashlib.sha256()
        total = 0
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                total += len(chunk)
                digest.update(chunk)
        mtime = os.path.getmtime(path)
        return digest.hexdigest(), total, mtime

    def _build_manifest(self, entries: Iterable[BackupEntry], *, snapshot_type: str) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        active_library = None
        try:
            active_library = self._settings.get_active_library_name()
        except Exception:
            active_library = None

        return {
            "manifest_version": BACKUP_MANIFEST_VERSION,
            "created_at": created_at,
            "snapshot_type": snapshot_type,
            "active_library": active_library,
            "files": [
                {
                    "kind": entry.kind,
                    "archive_path": entry.archive_path,
                    "target_path": entry.target_path,
                    "sha256": entry.sha256,
                    "size": entry.size,
                    "mtime": entry.mtime,
                }
                for entry in entries
            ],
        }

    def _write_archive(self, archive_path: str, entries: list[BackupEntry], manifest: dict[str, Any]) -> None:
        with zipfile.ZipFile(
            archive_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
            )
            for entry in entries:
                zf.write(entry.target_path, arcname=entry.archive_path)

    async def create_snapshot(self, *, snapshot_type: str = "manual", persist: bool = False) -> dict[str, Any]:
        """Create a backup archive.

        If ``persist`` is true, the archive is stored in the backup directory
        and retained according to the configured retention policy.
        """

        async with self._lock:
            raw_targets = self._model_update_targets()
            entries: list[BackupEntry] = []
            for kind, archive_path, target_path in raw_targets:
                if not os.path.exists(target_path):
                    continue
                sha256, size, mtime = self._hash_file(target_path)
                entries.append(
                    BackupEntry(
                        kind=kind,
                        archive_path=archive_path,
                        target_path=target_path,
                        sha256=sha256,
                        size=size,
                        mtime=mtime,
                    )
                )

            if not entries:
                raise FileNotFoundError("No backupable files were found")

            manifest = self._build_manifest(entries, snapshot_type=snapshot_type)
            archive_name = self._build_archive_name(snapshot_type=snapshot_type)
            fd, temp_path = tempfile.mkstemp(suffix=".zip", dir=str(self._backup_dir))
            os.close(fd)

            try:
                self._write_archive(temp_path, entries, manifest)
                if persist:
                    final_path = self._backup_dir / archive_name
                    os.replace(temp_path, final_path)
                    self._prune_snapshots()
                    return {
                        "archive_path": str(final_path),
                        "archive_name": final_path.name,
                        "manifest": manifest,
                    }

                with open(temp_path, "rb") as handle:
                    data = handle.read()
                return {
                    "archive_name": archive_name,
                    "archive_bytes": data,
                    "manifest": manifest,
                }
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(temp_path)

    def _build_archive_name(self, *, snapshot_type: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"lora-manager-backup-{timestamp}-{snapshot_type}.zip"

    def _prune_snapshots(self) -> None:
        retention = self._get_setting_int(
            "backup_retention_count", DEFAULT_BACKUP_RETENTION_COUNT
        )
        archives = sorted(
            self._backup_dir.glob("lora-manager-backup-*-auto.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in archives[retention:]:
            with contextlib.suppress(OSError):
                path.unlink()

    async def restore_snapshot(self, archive_path: str) -> dict[str, Any]:
        """Restore backup contents from a ZIP archive."""

        async with self._lock:
            try:
                zf = zipfile.ZipFile(archive_path, mode="r")
            except zipfile.BadZipFile as exc:
                raise ValueError("Backup archive is not a valid ZIP file") from exc

            with zf:
                try:
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                except KeyError as exc:
                    raise ValueError("Backup archive is missing manifest.json") from exc

                if not isinstance(manifest, dict):
                    raise ValueError("Backup manifest is invalid")
                if manifest.get("manifest_version") != BACKUP_MANIFEST_VERSION:
                    raise ValueError("Backup manifest version is not supported")

                files = manifest.get("files", [])
                if not isinstance(files, list):
                    raise ValueError("Backup manifest file list is invalid")

                extracted_paths: list[tuple[str, str]] = []
                temp_dir = Path(tempfile.mkdtemp(prefix="lora-manager-restore-"))
                try:
                    for item in files:
                        if not isinstance(item, dict):
                            continue
                        archive_member = item.get("archive_path")
                        if not isinstance(archive_member, str) or not archive_member:
                            continue
                        archive_member_path = Path(archive_member)
                        if archive_member_path.is_absolute() or ".." in archive_member_path.parts:
                            raise ValueError(f"Invalid archive member path: {archive_member}")

                        kind = item.get("kind")
                        target_path = self._resolve_restore_target(kind, archive_member)
                        if target_path is None:
                            continue

                        extracted_path = temp_dir / archive_member_path
                        extracted_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(archive_member) as source, open(
                            extracted_path, "wb"
                        ) as destination:
                            shutil.copyfileobj(source, destination)

                        expected_hash = item.get("sha256")
                        if isinstance(expected_hash, str) and expected_hash:
                            actual_hash, _, _ = self._hash_file(str(extracted_path))
                            if actual_hash != expected_hash:
                                raise ValueError(
                                    f"Checksum mismatch for {archive_member}"
                                )

                        extracted_paths.append((str(extracted_path), target_path))

                    for extracted_path, target_path in extracted_paths:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        os.replace(extracted_path, target_path)
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)

            return {
                "success": True,
                "restored_files": len(extracted_paths),
                "snapshot_type": manifest.get("snapshot_type"),
            }

    def _resolve_restore_target(self, kind: Any, archive_member: str) -> str | None:
        if kind == "settings":
            return self._settings_file_path()
        if kind == "download_history":
            return self._download_history_path()
        if kind == "symlink_map":
            return get_cache_file_path(CacheType.SYMLINK, create_dir=True)
        if kind == "model_update":
            filename = os.path.basename(archive_member)
            return str(Path(get_cache_file_path(CacheType.MODEL_UPDATE, create_dir=True)).parent / filename)
        return None

    async def create_auto_snapshot_if_due(self) -> Optional[dict[str, Any]]:
        if not self._get_setting_bool("backup_auto_enabled", True):
            return None

        latest = self.get_latest_auto_snapshot()
        now = time.time()
        if latest and now - latest["mtime"] < DEFAULT_BACKUP_INTERVAL_SECONDS:
            return None

        return await self.create_snapshot(snapshot_type="auto", persist=True)

    async def _auto_backup_loop(self) -> None:
        while True:
            try:
                await self.create_auto_snapshot_if_due()
                await asyncio.sleep(DEFAULT_BACKUP_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Automatic backup snapshot failed: %s", exc, exc_info=True)
                await asyncio.sleep(60)

    def get_available_snapshots(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for path in sorted(self._backup_dir.glob("lora-manager-backup-*.zip")):
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshots.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "is_auto": path.name.endswith("-auto.zip"),
                }
            )
        snapshots.sort(key=lambda item: item["mtime"], reverse=True)
        return snapshots

    def get_latest_auto_snapshot(self) -> Optional[dict[str, Any]]:
        autos = [snapshot for snapshot in self.get_available_snapshots() if snapshot["is_auto"]]
        if not autos:
            return None
        return autos[0]

    def get_status(self) -> dict[str, Any]:
        snapshots = self.get_available_snapshots()
        return {
            "backupDir": self.get_backup_dir(),
            "enabled": self._get_setting_bool("backup_auto_enabled", True),
            "retentionCount": self._get_setting_int(
                "backup_retention_count", DEFAULT_BACKUP_RETENTION_COUNT
            ),
            "snapshotCount": len(snapshots),
            "latestSnapshot": snapshots[0] if snapshots else None,
            "latestAutoSnapshot": self.get_latest_auto_snapshot(),
        }
