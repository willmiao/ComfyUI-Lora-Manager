#!/usr/bin/env python3
"""
Test runner script for ComfyUI-Lora-Manager.

This script runs pytest from the tests directory to avoid import issues
with the root __init__.py file.
"""
import subprocess
import sys
import os
from pathlib import Path

# Set environment variable to indicate standalone mode
# HF_HUB_DISABLE_TELEMETRY is from ComfyUI main.py
standalone_mode = os.environ.get("HF_HUB_DISABLE_TELEMETRY", "0") == "0"

def main():
    """Run pytest from the tests directory to avoid import issues."""
    # Get the script directory
    script_dir = Path(__file__).parent.absolute()
    tests_dir = script_dir / "tests"
    
    if not tests_dir.exists():
        print(f"Error: Tests directory not found at {tests_dir}")
        return 1
    
    # Change to tests directory
    original_cwd = os.getcwd()
    os.chdir(tests_dir)
    
    try:
        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            "-v",
            "--rootdir=.",
        ] + sys.argv[1:]  # Pass any additional arguments
        
        print(f"Running: {' '.join(cmd)}")
        print(f"Working directory: {tests_dir}")
        
        # Run pytest
        result = subprocess.run(cmd, cwd=tests_dir)
        return result.returncode
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

if __name__ == "__main__":
    sys.exit(main())
