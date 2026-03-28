#!/usr/bin/env python3
"""
Batch Import Feature Installer for ComfyUI LoRA Manager

Usage:
  python install_batch_import.py "C:\path\to\lora-manager" [--dry-run] [--backup]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
import re


PACKAGE_ROOT = Path(__file__).resolve().parent
NEW_FILES_ROOT = PACKAGE_ROOT / "new_files"


class Installer:
    def __init__(self, repo_path: Path, dry_run: bool = False, backup: bool = False) -> None:
        self.repo_path = repo_path
        self.dry_run = dry_run
        self.backup = backup
        self.backup_dir: Path | None = None
        self.changes: list[str] = []
        self.errors: list[str] = []

        if self.backup:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.backup_dir = self.repo_path / f".batch-import-backup-{stamp}"

    def log(self, msg: str) -> None:
        print(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        print(f"ERROR: {msg}")

    def validate_repo(self) -> bool:
        required = [
            "py",
            "static",
            "templates",
            "standalone.py",
            "static/js/recipes.js",
            "templates/recipes.html",
            "py/services/server_i18n.py",
        ]
        missing = []
        for rel in required:
            if not (self.repo_path / rel).exists():
                missing.append(rel)
        if missing:
            self.error("Missing required paths: " + ", ".join(missing))
            return False
        return True

    def backup_file(self, path: Path) -> None:
        if not self.backup or self.dry_run:
            return
        if self.backup_dir is None:
            return
        dest = self.backup_dir / path.relative_to(self.repo_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)

    def copy_new_files(self) -> None:
        if not NEW_FILES_ROOT.exists():
            self.error(f"new_files directory not found at {NEW_FILES_ROOT}")
            return
        for src in NEW_FILES_ROOT.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(NEW_FILES_ROOT)
            dest = self.repo_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if self.dry_run:
                self.log(f"[DRY-RUN] copy {rel}")
                continue
            if dest.exists():
                # Skip if identical
                try:
                    if dest.read_bytes() == src.read_bytes():
                        continue
                except Exception:
                    pass
            shutil.copy2(src, dest)
            self.changes.append(f"copied {rel}")

    def patch_standalone(self) -> None:
        path = self.repo_path / "standalone.py"
        self.backup_file(path)
        content = path.read_text(encoding="utf-8")

        if "BatchImportRoutes" not in content:
            # Insert import
            content, import_count = re.subn(
                r"^from py\.routes\.recipe_routes import RecipeRoutes\s*$",
                "from py.routes.recipe_routes import RecipeRoutes\nfrom py.routes.batch_import_routes import BatchImportRoutes",
                content,
                flags=re.MULTILINE,
            )
            if import_count == 0:
                self.error("Could not insert BatchImportRoutes import into standalone.py")
                return

        if "BatchImportRoutes.setup_routes" not in content:
            content, setup_count = re.subn(
                r"^(\s*RecipeRoutes\.setup_routes\(app\)\s*)$",
                "\\1\n        BatchImportRoutes.setup_routes(app)",
                content,
                flags=re.MULTILINE,
            )
            if setup_count == 0:
                self.error("Could not insert BatchImportRoutes setup into standalone.py")
                return

        if self.dry_run:
            self.log("[DRY-RUN] patch standalone.py")
        else:
            path.write_text(content, encoding="utf-8")
            self.changes.append("patched standalone.py")

    def patch_recipes_html(self) -> None:
        path = self.repo_path / "templates" / "recipes.html"
        self.backup_file(path)
        content = path.read_text(encoding="utf-8")

        if "components/batch_import_modal.html" not in content:
            content = content.replace(
                "{% include 'components/import_modal.html' %}",
                "{% include 'components/import_modal.html' %}\n{% include 'components/batch_import_modal.html' %}",
            )

        if "batchImportManager.openBatchImportModal" not in content:
            insert_block = (
                "            <div title=\"{{ t('recipes.controls.batchImport.tooltip', {}, 'Batch import multiple recipes') }}\" class=\"control-group\">\n"
                "                <button class=\"batch-import-button\" onclick=\"batchImportManager.openBatchImportModal()\"><i class=\"fas fa-layer-group\"></i> {{\n"
                "                    t('recipes.controls.batchImport.buttonLabel', {}, 'Batch Import') }}</button>\n"
                "            </div>\n"
            )
            content, count = re.subn(
                r"^(\s*<div class=\"controls-right\">\s*)$",
                "\\1\n" + insert_block,
                content,
                flags=re.MULTILINE,
            )
            if count == 0:
                self.error("Could not insert Batch Import button into recipes.html")
                return

        if self.dry_run:
            self.log("[DRY-RUN] patch templates/recipes.html")
        else:
            path.write_text(content, encoding="utf-8")
            self.changes.append("patched templates/recipes.html")

    def patch_recipes_js(self) -> None:
        path = self.repo_path / "static" / "js" / "recipes.js"
        self.backup_file(path)
        content = path.read_text(encoding="utf-8")

        # Import
        if "BatchImportManager" not in content or "import { BatchImportManager" not in content:
            if "// import { BatchImportManager" in content:
                content = content.replace(
                    "// import { BatchImportManager } from './managers/BatchImportManager.js';",
                    "import { BatchImportManager } from './managers/BatchImportManager.js';",
                )
            else:
                content = content.replace(
                    "import { ImportManager } from './managers/ImportManager.js';",
                    "import { ImportManager } from './managers/ImportManager.js';\nimport { BatchImportManager } from './managers/BatchImportManager.js';",
                )

        # Initialization
        if "this.batchImportManager" not in content:
            if "// this.batchImportManager = new BatchImportManager" in content:
                content = content.replace(
                    "// this.batchImportManager = new BatchImportManager(this.importManager);",
                    "this.batchImportManager = new BatchImportManager(this.importManager);",
                )
            else:
                content = content.replace(
                    "this.importManager = new ImportManager();",
                    "this.importManager = new ImportManager();\n\n        // Initialize BatchImportManager\n        this.batchImportManager = new BatchImportManager(this.importManager);",
                )

        # Global exposure
        if "window.batchImportManager" not in content:
            if "// window.batchImportManager" in content:
                content = content.replace(
                    "// window.batchImportManager = this.batchImportManager;",
                    "window.batchImportManager = this.batchImportManager;",
                )
            else:
                content = content.replace(
                    "window.importManager = this.importManager;",
                    "window.importManager = this.importManager;\n        window.batchImportManager = this.batchImportManager;",
                )

        if self.dry_run:
            self.log("[DRY-RUN] patch static/js/recipes.js")
        else:
            path.write_text(content, encoding="utf-8")
            self.changes.append("patched static/js/recipes.js")

    def patch_server_i18n(self) -> None:
        path = self.repo_path / "py" / "services" / "server_i18n.py"
        self.backup_file(path)
        content = path.read_text(encoding="utf-8")

        # If already supports default, skip
        match = re.search(r"def get_translation\([^\)]*default", content)
        if match:
            return

        lines = content.splitlines()
        start_idx = None
        indent = ""
        for i, line in enumerate(lines):
            if line.lstrip().startswith("def get_translation") or line.lstrip().startswith("def get_translation("):
                if line.startswith("    def get_translation"):
                    start_idx = i
                    indent = line[: len(line) - len(line.lstrip())]
                    break
        if start_idx is None:
            self.error("Could not find get_translation in server_i18n.py")
            return

        # Find end of method
        end_idx = len(lines)
        for j in range(start_idx + 1, len(lines)):
            if lines[j].startswith(indent + "def "):
                end_idx = j
                break

        updated_block = [
            f"{indent}def get_translation(",
            f"{indent}    self,",
            f"{indent}    key: str,",
            f"{indent}    params: Optional[Dict[str, Any]] = None,",
            f"{indent}    default: Optional[str] = None,",
            f"{indent}    **kwargs,",
            f"{indent}) -> str:",
            f"{indent}    \"\"\"Get translation by key with optional params and optional fallback default.\"\"\"",
            f"{indent}    # Backward compatibility: support legacy calls like t('key', 'fallback').",
            f"{indent}    if params is not None and not isinstance(params, dict):",
            f"{indent}        if default is None:",
            f"{indent}            default = str(params)",
            f"{indent}        params = {}",
            "",
            f"{indent}    # Merge kwargs into params for convenience.",
            f"{indent}    resolved_params: Dict[str, Any] = dict(params or {})",
            f"{indent}    if kwargs:",
            f"{indent}        resolved_params.update(kwargs)",
            "",
            f"{indent}    if self.current_locale not in self.translations:",
            f"{indent}        return default if default is not None else key",
            "",
            f"{indent}    # Navigate through nested object using dot notation",
            f"{indent}    keys = key.split('.')",
            f"{indent}    value = self.translations[self.current_locale]",
            "",
            f"{indent}    for k in keys:",
            f"{indent}        if isinstance(value, dict) and k in value:",
            f"{indent}            value = value[k]",
            f"{indent}        else:",
            f"{indent}            # Fallback to English if current locale doesn't have the key",
            f"{indent}            if self.current_locale != 'en' and 'en' in self.translations:",
            f"{indent}                en_value = self.translations['en']",
            f"{indent}                for fallback_key in keys:",
            f"{indent}                    if isinstance(en_value, dict) and fallback_key in en_value:",
            f"{indent}                        en_value = en_value[fallback_key]",
            f"{indent}                    else:",
            f"{indent}                        return default if default is not None else key",
            f"{indent}                value = en_value",
            f"{indent}            else:",
            f"{indent}                return default if default is not None else key",
            f"{indent}            break",
            "",
            f"{indent}    if not isinstance(value, str):",
            f"{indent}        return default if default is not None else key",
            "",
            f"{indent}    # Replace parameters if provided",
            f"{indent}    if resolved_params:",
            f"{indent}        for param_key, param_value in resolved_params.items():",
            f"{indent}            placeholder = f\"{{{param_key}}}\"",
            f"{indent}            double_placeholder = f\"{{{{{param_key}}}}}\"",
            f"{indent}            value = value.replace(placeholder, str(param_value))",
            f"{indent}            value = value.replace(double_placeholder, str(param_value))",
            "",
            f"{indent}    return value",
        ]

        lines = lines[:start_idx] + updated_block + lines[end_idx:]

        # Ensure Optional is imported
        if "Optional" not in content:
            lines = self._ensure_optional_import(lines)

        new_content = "\n".join(lines) + "\n"

        if self.dry_run:
            self.log("[DRY-RUN] patch py/services/server_i18n.py")
        else:
            path.write_text(new_content, encoding="utf-8")
            self.changes.append("patched py/services/server_i18n.py")

    def _ensure_optional_import(self, lines: list[str]) -> list[str]:
        for i, line in enumerate(lines):
            if line.startswith("from typing import "):
                if "Optional" in line:
                    return lines
                # Insert Optional into import list
                parts = line.replace("from typing import ", "").split(",")
                parts = [p.strip() for p in parts if p.strip()]
                parts.append("Optional")
                parts = sorted(set(parts))
                lines[i] = "from typing import " + ", ".join(parts)
                return lines
        return lines

    def run(self) -> bool:
        if not self.validate_repo():
            return False

        self.copy_new_files()
        self.patch_standalone()
        self.patch_recipes_html()
        self.patch_recipes_js()
        self.patch_server_i18n()

        if self.backup_dir and not self.dry_run:
            self.log(f"Backups stored in {self.backup_dir}")

        if self.errors:
            self.log("\nErrors encountered:")
            for err in self.errors:
                self.log(f"- {err}")
            return False

        self.log("\nInstall complete. Changes applied:")
        for change in self.changes:
            self.log(f"- {change}")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch Import feature installer")
    parser.add_argument("repo_path", help="Path to unaltered LoRA Manager repo")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    parser.add_argument("--backup", action="store_true", help="Create backups of modified files")

    args = parser.parse_args()
    repo_path = Path(args.repo_path).resolve()
    if not repo_path.exists():
        print(f"Repo path does not exist: {repo_path}")
        sys.exit(1)

    installer = Installer(repo_path, dry_run=args.dry_run, backup=args.backup)
    ok = installer.run()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
