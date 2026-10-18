"""End-to-end regression for issue #1112.

Importing a third-party ``.civitai.info`` sidecar (a migration path) must keep
the local, dotted file name intact instead of cutting it at the model-version
dot (``lora-sd1.5-backlight_slider_v10`` -> ``lora-sd1``).
"""

import json
import os
from pathlib import Path

import pytest

from py.services import model_scanner
from py.services.lora_scanner import LoraScanner
from py.services.model_scanner import ModelScanner

DOTTED_STEM = "lora-sd1.5-backlight_slider_v10"

CIVITAI_INFO = {
    "id": 12345,
    "baseModel": "SD 1.5",
    "name": "v1.0",
    "model": {
        "id": 999,
        "name": "Light Control",
        "type": "LORA",
        "description": "",
        "tags": ["lighting"],
    },
    "files": [
        {
            "id": 1,
            # Remote name from the CivitAI payload; the local file was renamed.
            "name": "backlight_slider_v10.safetensors",
            "primary": True,
            "sizeKB": 1024,
            "hashes": {"SHA256": "a" * 64},
        }
    ],
}


def _normalize(path: Path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.mark.asyncio
async def test_civitai_info_migration_keeps_dotted_local_name(tmp_path, monkeypatch):
    loras_root = tmp_path / "loras"
    loras_root.mkdir()

    model_file = loras_root / f"{DOTTED_STEM}.safetensors"
    model_file.write_text("fake lora weights", encoding="utf-8")
    (loras_root / f"{DOTTED_STEM}.civitai.info").write_text(
        json.dumps(CIVITAI_INFO), encoding="utf-8"
    )

    normalized_root = _normalize(loras_root)
    monkeypatch.setattr(
        model_scanner.config, "loras_roots", [normalized_root], raising=False
    )
    monkeypatch.setattr(
        model_scanner.config, "extra_loras_roots", [], raising=False
    )

    scanner = LoraScanner()
    entry = await scanner._process_model_file(_normalize(model_file), normalized_root)

    assert entry is not None
    assert entry["file_name"] == DOTTED_STEM
    assert entry["model_name"] == "Light Control"

    sidecar = loras_root / f"{DOTTED_STEM}.metadata.json"
    assert sidecar.exists()
    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert saved["file_name"] == DOTTED_STEM
    assert saved["model_name"] == "Light Control"
    # The migration must not silently drop the CivitAI payload.
    assert saved["civitai"]["name"] == "v1.0"
