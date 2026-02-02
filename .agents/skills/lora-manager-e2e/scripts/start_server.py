#!/usr/bin/env python3
"""
Start or restart LoRa Manager standalone server for E2E testing.
"""

import argparse
import subprocess
import sys
import time
import socket
import signal
import os


def find_server_process(port: int) -> list[int]:
    """Find PIDs of processes listening on the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            check=False
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
                check=False
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


def kill_server(port: int) -> None:
    """Kill processes using the specified port."""
    pids = find_server_process(port)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to process {pid}")
        except ProcessLookupError:
            pass
    
    # Wait for processes to terminate
    time.sleep(1)
    
    # Force kill if still running
    pids = find_server_process(port)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"Sent SIGKILL to process {pid}")
        except ProcessLookupError:
            pass


def is_server_ready(port: int, timeout: float = 0.5) -> bool:
    """Check if server is accepting connections."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def wait_for_server(port: int, timeout: int = 30) -> bool:
    """Wait for server to become ready."""
    start = time.time()
    while time.time() - start < timeout:
        if is_server_ready(port):
            return True
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
        help="Server port (default: 8188)"
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Kill existing server before starting"
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for server to be ready before exiting"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout for waiting (default: 30)"
    )
    
    args = parser.parse_args()
    
    # Get project root (parent of .agents directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(skill_dir)))
    
    # Restart if requested
    if args.restart:
        print(f"Killing existing server on port {args.port}...")
        kill_server(args.port)
        time.sleep(1)
    
    # Check if already running
    if is_server_ready(args.port):
        print(f"Server already running on port {args.port}")
        return 0
    
    # Start server
    print(f"Starting LoRa Manager standalone server on port {args.port}...")
    cmd = [sys.executable, "standalone.py", "--port", str(args.port)]
    
    # Start in background
    process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True
    )
    
    print(f"Server process started with PID {process.pid}")
    
    # Wait for ready if requested
    if args.wait:
        print(f"Waiting for server to be ready (timeout: {args.timeout}s)...")
        if wait_for_server(args.port, args.timeout):
            print(f"Server ready at http://127.0.0.1:{args.port}/loras")
            return 0
        else:
            print(f"Timeout waiting for server")
            return 1
    
    print(f"Server starting at http://127.0.0.1:{args.port}/loras")
    return 0


if __name__ == "__main__":
    sys.exit(main())
