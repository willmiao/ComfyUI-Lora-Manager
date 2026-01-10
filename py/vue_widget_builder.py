"""
Vue Widget Build Checker and Auto-builder

This module checks if Vue widgets are built and attempts to build them if needed.
Useful for development mode where source code might be newer than build output.
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VueWidgetBuilder:
    """Manages Vue widget build checking and auto-building."""

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize the builder.

        Args:
            project_root: Project root directory. If None, auto-detects.
        """
        if project_root is None:
            # Auto-detect project root (where __init__.py is)
            project_root = Path(__file__).parent.parent

        self.project_root = Path(project_root)
        self.vue_widgets_dir = self.project_root / "vue-widgets"
        self.build_output_dir = self.project_root / "web" / "comfyui" / "vue-widgets"
        self.src_dir = self.vue_widgets_dir / "src"

    def check_build_exists(self) -> bool:
        """
        Check if build output exists.

        Returns:
            True if at least one built .js file exists
        """
        if not self.build_output_dir.exists():
            return False

        js_files = list(self.build_output_dir.glob("*.js"))
        return len(js_files) > 0

    def check_build_outdated(self) -> bool:
        """
        Check if source code is newer than build output.

        Returns:
            True if source is newer, False otherwise or if can't determine
        """
        if not self.src_dir.exists():
            return False

        if not self.check_build_exists():
            return True

        try:
            # Get newest file in source directory
            src_files = [f for f in self.src_dir.rglob("*") if f.is_file()]
            if not src_files:
                return False

            newest_src_time = max(f.stat().st_mtime for f in src_files)

            # Get oldest file in build directory
            build_files = [f for f in self.build_output_dir.rglob("*.js") if f.is_file()]
            if not build_files:
                return True

            oldest_build_time = min(f.stat().st_mtime for f in build_files)

            return newest_src_time > oldest_build_time

        except Exception as e:
            logger.debug(f"Error checking build timestamps: {e}")
            return False

    def check_node_available(self) -> bool:
        """
        Check if Node.js is available.

        Returns:
            True if node/npm are available
        """
        try:
            result = subprocess.run(
                ["npm", "--version"],
                capture_output=True,
                timeout=5,
                check=False
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def build_widgets(self, force: bool = False) -> bool:
        """
        Build Vue widgets.

        Args:
            force: If True, build even if not needed

        Returns:
            True if build succeeded or not needed, False if failed
        """
        if not force and self.check_build_exists() and not self.check_build_outdated():
            logger.debug("Vue widgets build is up to date")
            return True

        if not self.vue_widgets_dir.exists():
            logger.warning(f"Vue widgets directory not found: {self.vue_widgets_dir}")
            return False

        if not self.check_node_available():
            logger.warning(
                "Node.js/npm not found. Cannot build Vue widgets. "
                "Please install Node.js or build manually: cd vue-widgets && npm run build"
            )
            return False

        logger.info("Building Vue widgets...")

        try:
            # Check if node_modules exists, if not run npm install first
            node_modules = self.vue_widgets_dir / "node_modules"
            if not node_modules.exists():
                logger.info("Installing npm dependencies...")
                install_result = subprocess.run(
                    ["npm", "install"],
                    cwd=self.vue_widgets_dir,
                    capture_output=True,
                    timeout=300,  # 5 minutes for install
                    check=False
                )

                if install_result.returncode != 0:
                    logger.error(f"npm install failed: {install_result.stderr.decode()}")
                    return False

            # Run build
            build_result = subprocess.run(
                ["npm", "run", "build"],
                cwd=self.vue_widgets_dir,
                capture_output=True,
                timeout=120,  # 2 minutes for build
                check=False
            )

            if build_result.returncode == 0:
                logger.info("✓ Vue widgets built successfully")
                return True
            else:
                logger.error(f"Build failed: {build_result.stderr.decode()}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Build timed out")
            return False
        except Exception as e:
            logger.error(f"Build error: {e}")
            return False

    def ensure_built(self, auto_build: bool = True, warn_only: bool = True) -> bool:
        """
        Ensure Vue widgets are built, optionally auto-building if needed.

        Args:
            auto_build: If True, attempt to build if needed
            warn_only: If True, only warn on failure instead of raising

        Returns:
            True if widgets are available (built or successfully auto-built)

        Raises:
            RuntimeError: If warn_only=False and build is missing/failed
        """
        if self.check_build_exists():
            # Build exists, check if outdated
            if self.check_build_outdated():
                logger.info("Vue widget source code is newer than build")
                if auto_build:
                    return self.build_widgets()
                else:
                    logger.warning(
                        "Vue widget build is outdated. "
                        "Please rebuild: cd vue-widgets && npm run build"
                    )
            return True

        # No build exists
        logger.warning("Vue widget build not found")

        if auto_build:
            if self.build_widgets():
                return True
            else:
                msg = (
                    "Failed to build Vue widgets. "
                    "Please build manually: cd vue-widgets && npm install && npm run build"
                )
                if warn_only:
                    logger.warning(msg)
                    return False
                else:
                    raise RuntimeError(msg)
        else:
            msg = "Vue widgets not built. Please run: cd vue-widgets && npm install && npm run build"
            if warn_only:
                logger.warning(msg)
                return False
            else:
                raise RuntimeError(msg)


def check_and_build_vue_widgets(
    auto_build: bool = True,
    warn_only: bool = True,
    force: bool = False
) -> bool:
    """
    Convenience function to check and build Vue widgets.

    Args:
        auto_build: If True, attempt to build if needed
        warn_only: If True, only warn on failure instead of raising
        force: If True, force rebuild even if up to date

    Returns:
        True if widgets are available
    """
    builder = VueWidgetBuilder()

    if force:
        return builder.build_widgets(force=True)

    return builder.ensure_built(auto_build=auto_build, warn_only=warn_only)
