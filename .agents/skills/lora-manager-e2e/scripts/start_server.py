#!/usr/bin/env python3
"""
Start or restart LoRa Manager standalone server for E2E testing.

Backward-compatible CLI: --port, --restart, --wait, --timeout all work as before.
New options: --detach (setsid-style fully detached launch, survives shell death).

Safety rules implemented here:
- Never kill processes the script did not start. The script tracks the PIDs it
  manages in a pidfile (/tmp/lora-manager-e2e-server-{PORT}.pid).
- If the port is held by an unrelated process (e.g. a live ComfyUI) the script
  reports the conflict and exits early instead of killing it.
- --restart only kills managed PIDs; if unrelated processes still hold the port
  afterwards, the script reports them and aborts.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time

PIDFILE_PREFIX = "/tmp/lora-manager-e2e-server"


def pidfile_path(port: int) -> str:
    """Path of the pidfile that records PIDs this script started for a port."""
    return f"{PIDFILE_PREFIX}-{port}.pid"


def read_managed_pids(port: int) -> list[int]:
    """Read PIDs this script previously managed for the port (may be stale)."""
    path = pidfile_path(port)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return [int(line.strip()) for line in fh if line.strip().isdigit()]
    except (OSError, ValueError):
        return []


def write_managed_pids(port: int, pids: list[int]) -> None:
    """Record PIDs this script manages for the port."""
    try:
        with open(pidfile_path(port), "w", encoding="utf-8") as fh:
            for pid in pids:
                fh.write(f"{pid}\n")
    except OSError as exc:
        print(f"Warning: could not write pidfile for port {port}: {exc}")


def clear_managed_pids(port: int) -> None:
    """Remove the pidfile for the port (no longer managed)."""
    path = pidfile_path(port)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        print(f"Warning: could not remove pidfile {path}: {exc}")


def process_alive(pid: int) -> bool:
    """Return True if a process with the given pid exists."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by someone else


def find_server_process(port: int) -> list[int]:
    """Find PIDs of processes listening on the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [int(pid) for pid in result.stdout.strip().split("\n") if pid]
    except FileNotFoundError:
        # lsof not available, try netstat
        try:
            result = subprocess.run(
                ["netstat", "-tlnp"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = []
            for line in result.stdout.split("\n"):
                if f":{port}" in line:
                    parts = line.split()
                    for part in parts:
                        if "/" in part:
                            try:
                                pid = int(part.split("/")[0])
                                pids.append(pid)
                            except ValueError:
                                pass
            return pids
        except FileNotFoundError:
            pass
    return []


def describe_processes(pids: list[int]) -> str:
    """Human-readable description of a pid list (pid + command line)."""
    descriptions = []
    for pid in pids:
        cmdline = ""
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                raw = fh.read().replace(b"\x00", b" ").decode("utf-8", "replace")
                cmdline = raw.strip()
        except OSError:
            pass
        descriptions.append(f"pid {pid}{' (' + cmdline + ')' if cmdline else ''}")
    return ", ".join(descriptions) if descriptions else "none"


def kill_pids(pids: list[int], what: str) -> None:
    """Send SIGTERM (then SIGKILL) to the given PIDs, only after reporting."""
    for pid in pids:
        print(f"Sent SIGTERM to {what} pid {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    # Wait for processes to terminate
    deadline = time.time() + 5
    while time.time() < deadline:
        if not any(process_alive(pid) for pid in pids):
            break
        time.sleep(0.2)

    # Force kill if still running
    for pid in pids:
        if process_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"Sent SIGKILL to {what} pid {pid}")
            except ProcessLookupError:
                pass


def is_server_ready(port: int, timeout: float = 2.0) -> bool:
    """Check if server is accepting connections."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def wait_for_server(port: int, timeout: int = 30) -> bool:
    """Wait for server to become ready."""
    start = time.time()
    last_report = 0.0
    while time.time() - start < timeout:
        if is_server_ready(port):
            return True
        # Report progress every ~5s so a slow boot is visible, not silent.
        elapsed = time.time() - start
        if elapsed - last_report >= 5:
            print(f"  ...still waiting ({int(elapsed)}s/{timeout}s)")
            last_report = elapsed
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start LoRa Manager standalone server for E2E testing"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8188,
        help="Server port (default: 8188)",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Kill the E2E server previously managed by this script for the port "
        "(tracked via pidfile) before starting; refuse to kill unrelated processes",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for server to be ready before exiting",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout for waiting (default: 30)",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Launch the server fully detached (setsid-style) so it survives shell "
        "death. REQUIRED for E2E: a plain background process dies with the shell",
    )
    parser.add_argument(
        "--settings-path",
        type=str,
        default=None,
        metavar="DIR",
        help="Explicit settings directory passed to standalone.py (--settings-path, "
        "equivalent to LORA_MANAGER_SETTINGS_DIR). settings.json, cache/, "
        "wildcards/, backups/, logs/, stats/ all live under this directory instead "
        "of the project root or the user config dir. Recommended for sandboxed E2E "
        "so the real instance and the repo stay untouched",
    )

    args = parser.parse_args()

    # Get project root (parent of .agents directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(skill_dir)))

    managed_pids = read_managed_pids(args.port)

    # Restart if requested: kill ONLY managed PIDs.
    if args.restart:
        alive_managed = [pid for pid in managed_pids if process_alive(pid)]
        if alive_managed:
            print(
                f"Killing E2E server previously started by this script on port "
                f"{args.port} ({describe_processes(alive_managed)})..."
            )
            kill_pids(alive_managed, "managed E2E server")
        else:
            print(
                f"No live managed E2E server for port {args.port} "
                f"(pidfile: {pidfile_path(args.port)})"
            )
        time.sleep(1)
        # Refuse to kill anything the script did not manage.
        remaining = find_server_process(args.port)
        if remaining:
            print(
                f"ERROR: port {args.port} is still held by process(es) this script "
                f"did not start: {describe_processes(remaining)}."
            )
            print(
                "These may be unrelated (e.g. a live ComfyUI). The script will NOT "
                "kill them. Pick a different --port, or stop them manually if you "
                "are certain they are stale E2E servers."
            )
            return 2
        clear_managed_pids(args.port)

    # Port conflict check before starting: never blind-kill.
    port_pids = find_server_process(args.port)
    if port_pids:
        alive_managed = [pid for pid in port_pids if pid in managed_pids]
        unmanaged = [pid for pid in port_pids if pid not in managed_pids]
        if alive_managed and not unmanaged:
            print(
                f"Server already running on port {args.port} "
                f"({describe_processes(alive_managed)}, started by this script). "
                f"Use --restart to recycle it."
            )
            return 0
        print(
            f"ERROR: port {args.port} is already in use by process(es): "
            f"{describe_processes(port_pids)}."
        )
        print(
            "This is likely an unrelated process (e.g. a live ComfyUI holding 8188). "
            "The script will NOT kill it. Pick a free port with --port, e.g. 8199."
        )
        return 2

    # Start server
    print(f"Starting LoRa Manager standalone server on port {args.port}...")
    cmd = [
        sys.executable,
        "standalone.py",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
    ]
    if args.settings_path:
        settings_dir = os.path.abspath(os.path.expanduser(args.settings_path))
        if os.path.exists(settings_dir) and not os.path.isdir(settings_dir):
            print(
                f"ERROR: --settings-path '{settings_dir}' exists but is not a directory."
            )
            return 2
        os.makedirs(settings_dir, exist_ok=True)
        cmd.extend(["--settings-path", settings_dir])
        print(f"Settings directory: {settings_dir}")

    if args.detach:
        # Fully detached launch: new session (setsid), no controlling terminal,
        # stdin from /dev/null, stdout/stderr to a log file. Survives the shell.
        log_dir = os.path.join(script_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"server-{args.port}.log")
        with open(log_path, "ab") as log_fh:
            process = subprocess.Popen(
                cmd,
                cwd=project_root,
                stdin=subprocess.DEVNULL,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        print(f"Detached server process started with PID {process.pid} (setsid)")
        print(f"Log: {log_path}")
    else:
        # Plain background process (legacy behavior): dies with the shell.
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        print(f"Server process started with PID {process.pid}")
        print(
            "NOTE: not detached — this process dies when the launching shell exits. "
            "For E2E use --detach."
        )

    write_managed_pids(args.port, [process.pid])

    # Wait for ready if requested
    if args.wait:
        print(f"Waiting for server to be ready (timeout: {args.timeout}s)...")
        if wait_for_server(args.port, args.timeout):
            print(f"Server ready at http://127.0.0.1:{args.port}/loras")
            return 0
        print(f"Timeout waiting for server on port {args.port}")
        return 1

    print(f"Server starting at http://127.0.0.1:{args.port}/loras")
    return 0


if __name__ == "__main__":
    sys.exit(main())
