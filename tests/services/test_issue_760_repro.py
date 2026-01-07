import asyncio
import json
import pytest
from pathlib import Path
from py.services.settings_manager import get_settings_manager
from py.utils import example_images_download_manager as download_module

class RecordingWebSocketManager:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
    async def broadcast(self, payload: dict) -> None:
        self.payloads.append(payload)

class StubScanner:
    def __init__(self, models: list[dict]) -> None:
        self.raw_data = models
    async def get_cached_data(self):
        class Cache:
            def __init__(self, data): self.raw_data = data
        return Cache(self.raw_data)

@pytest.mark.asyncio
async def test_reprocessing_triggered_when_folder_missing(monkeypatch, tmp_path):
    # Setup paths
    images_root = tmp_path / "examples"
    images_root.mkdir()
    
    settings_manager = get_settings_manager()
    monkeypatch.setitem(settings_manager.settings, "example_images_path", str(images_root))
    monkeypatch.setitem(settings_manager.settings, "libraries", {"default": {}})
    monkeypatch.setitem(settings_manager.settings, "active_library", "default")
    
    model_hash = "f" * 64
    model_name = "Issue 760 Model"
    
    # Create a progress file where this model is already processed
    progress_file = images_root / ".download_progress.json"
    progress_file.write_text(json.dumps({
        "processed_models": [model_hash],
        "failed_models": []
    }))
    
    # But the model folder is missing! (repro condition)
    
    model_data = {
        "sha256": model_hash,
        "model_name": model_name,
        "file_path": str(tmp_path / "model.safetensors"),
        "file_name": "model.safetensors",
        "civitai": {"images": [{"url": "https://example.com/img.png"}]}
    }
    
    scanner = StubScanner([model_data])
    async def mock_get_lora_scanner():
        return scanner
    monkeypatch.setattr(download_module.ServiceRegistry, "get_lora_scanner", mock_get_lora_scanner)
    
    # Mock downloader and processor to avoid actual network/file ops
    async def fake_get_downloader():
        class MockDownloader:
            async def download_to_memory(self, *args, **kwargs):
                return True, b"data", {"content-type": "image/png"}
        return MockDownloader()
        
    monkeypatch.setattr(download_module, "get_downloader", fake_get_downloader)
    
    process_called = False
    async def fake_process_local_examples(*args):
        nonlocal process_called
        process_called = True
        return False # Fallback to remote
        
    monkeypatch.setattr(download_module.ExampleImagesProcessor, "process_local_examples", fake_process_local_examples)
    
    async def fake_download_model_images(*args):
        # Create the directory so it's "fixed"
        model_dir = args[3]
        Path(model_dir).mkdir(parents=True, exist_ok=True)
        (Path(model_dir) / "image_0.png").write_text("fixed")
        return True, False, []
        
    monkeypatch.setattr(download_module.ExampleImagesProcessor, "download_model_images_with_tracking", fake_download_model_images)
    
    # Run the manager
    ws_manager = RecordingWebSocketManager()
    manager = download_module.DownloadManager(ws_manager=ws_manager)
    
    result = await manager.start_download({"model_types": ["lora"], "delay": 0})
    assert result["success"] is True
    
    # Wait for completion
    if manager._download_task:
        await asyncio.wait_for(manager._download_task, timeout=2)
        
    # Verify reprocessing was triggered
    assert model_hash in manager._progress["reprocessed_models"]
    assert model_hash in manager._progress["processed_models"] # Should be back in processed
    
    # Verify the progress was saved (discarding reprocessed in memory, but summary logged)
    saved_progress = json.loads(progress_file.read_text())
    assert model_hash in saved_progress["processed_models"]
