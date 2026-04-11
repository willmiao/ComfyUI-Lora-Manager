from __future__ import annotations

import logging
import os
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_SESSION_HANDLER_NAME = "lora_manager_standalone_session_memory"
_FILE_HANDLER_NAME = "lora_manager_standalone_session_file"
_session_state: "StandaloneSessionLogState | None" = None
_session_lock = threading.Lock()


@dataclass
class StandaloneSessionLogState:
    started_at: str
    session_id: str
    log_file_path: str | None
    memory_handler: "StandaloneSessionMemoryHandler"


class StandaloneSessionMemoryHandler(logging.Handler):
    def __init__(self, capacity: int = 4000) -> None:
        super().__init__()
        self._entries: deque[str] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            rendered = self.format(record)
        except Exception:
            rendered = record.getMessage()

        with self._lock:
            self._entries.append(rendered)

    def render(self, max_lines: int | None = None) -> str:
        with self._lock:
            entries = list(self._entries)

        if max_lines is not None and max_lines > 0:
            entries = entries[-max_lines:]

        if not entries:
            return ""

        return "\n".join(entries) + "\n"


def _build_log_file_path(settings_file: str | None, started_at: datetime) -> str | None:
    if not settings_file:
        return None

    settings_dir = os.path.dirname(os.path.abspath(settings_file))
    log_dir = os.path.join(settings_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(log_dir, f"standalone-session-{timestamp}.log")


def setup_standalone_session_logging(settings_file: str | None) -> StandaloneSessionLogState:
    global _session_state

    with _session_lock:
        if _session_state is not None:
            return _session_state

        started_dt = datetime.now(timezone.utc)
        started_at = started_dt.replace(microsecond=0).isoformat()
        session_id = f"{started_dt.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        formatter = logging.Formatter(LOG_FORMAT)
        root_logger = logging.getLogger()
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)

        memory_handler = StandaloneSessionMemoryHandler()
        memory_handler.set_name(_SESSION_HANDLER_NAME)
        memory_handler.setFormatter(formatter)
        root_logger.addHandler(memory_handler)

        log_file_path = _build_log_file_path(settings_file, started_dt)
        if log_file_path:
            file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
            file_handler.set_name(_FILE_HANDLER_NAME)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

        _session_state = StandaloneSessionLogState(
            started_at=started_at,
            session_id=session_id,
            log_file_path=log_file_path,
            memory_handler=memory_handler,
        )

    logger = logging.getLogger("lora-manager-standalone")
    logger.info("LoRA Manager standalone startup time: %s", started_at)
    logger.info("LoRA Manager standalone session id: %s", session_id)
    if log_file_path:
        logger.info("LoRA Manager standalone session log path: %s", log_file_path)

    return _session_state


def get_standalone_session_log_snapshot(max_lines: int = 2000) -> dict[str, Any] | None:
    state = _session_state
    if state is None:
        return None

    return {
        "started_at": state.started_at,
        "session_id": state.session_id,
        "log_file_path": state.log_file_path,
        "in_memory_text": state.memory_handler.render(max_lines=max_lines),
    }


def reset_standalone_session_logging_for_tests() -> None:
    global _session_state

    with _session_lock:
        root_logger = logging.getLogger()
        handlers_to_remove = [
            handler
            for handler in root_logger.handlers
            if handler.get_name() in {_SESSION_HANDLER_NAME, _FILE_HANDLER_NAME}
        ]
        for handler in handlers_to_remove:
            root_logger.removeHandler(handler)
            handler.close()
        _session_state = None
