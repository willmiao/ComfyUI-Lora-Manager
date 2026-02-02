#!/usr/bin/env python3
"""
Wait for LoRa Manager server to become ready.
"""

import argparse
import socket
import sys
import time


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
        description="Wait for LoRa Manager server to become ready"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8188,
        help="Server port (default: 8188)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds (default: 30)"
    )
    
    args = parser.parse_args()
    
    print(f"Waiting for server on port {args.port} (timeout: {args.timeout}s)...")
    
    if wait_for_server(args.port, args.timeout):
        print(f"Server ready at http://127.0.0.1:{args.port}/loras")
        return 0
    else:
        print(f"Timeout: Server not ready after {args.timeout}s")
        return 1


if __name__ == "__main__":
    sys.exit(main())
