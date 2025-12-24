import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from py.services.recipe_scanner import RecipeScanner
from types import SimpleNamespace

# We define these here to help with spec= if needed
class MockCivitaiClient:
    async def get_image_info(self, image_id):
        pass

class MockPersistenceService:
    async def save_recipe(self, recipe):
        pass

@pytest.fixture
def mock_civitai_client():
    client = MagicMock(spec=MockCivitaiClient)
    client.get_image_info = AsyncMock()
    return client

@pytest.fixture
def mock_metadata_provider():
    provider = MagicMock()
    provider.get_model_version_info = AsyncMock(return_value=(None, None))
    provider.get_model_by_hash = AsyncMock(return_value=(None, None))
    return provider

@pytest.fixture
def recipe_scanner():
    lora_scanner = MagicMock()
    lora_scanner.get_cached_data = AsyncMock(return_value=SimpleNamespace(raw_data=[]))
    
    scanner = RecipeScanner(lora_scanner=lora_scanner)
    return scanner

@pytest.fixture
def setup_scanner(recipe_scanner, mock_civitai_client, mock_metadata_provider, monkeypatch):
    monkeypatch.setattr(recipe_scanner, "_get_civitai_client", AsyncMock(return_value=mock_civitai_client))
    
    # Wrap the real method with a mock so we can check calls but still execute it
    real_save = recipe_scanner._save_recipe_persistently
    mock_save = AsyncMock(side_effect=real_save)
    monkeypatch.setattr(recipe_scanner, "_save_recipe_persistently", mock_save)
    
    monkeypatch.setattr("py.recipes.enrichment.get_default_metadata_provider", AsyncMock(return_value=mock_metadata_provider))
    
    # Mock get_recipe_json_path to avoid file system issues in tests
    recipe_scanner.get_recipe_json_path = AsyncMock(return_value="/tmp/test_recipe.json")
    # Mock open to avoid actual file writing
    monkeypatch.setattr("builtins.open", MagicMock())
    monkeypatch.setattr("json.dump", MagicMock())
    monkeypatch.setattr("os.path.exists", MagicMock(return_value=False)) # avoid EXIF logic
    
    return recipe_scanner, mock_civitai_client, mock_metadata_provider

@pytest.mark.asyncio
async def test_repair_all_recipes_skip_up_to_date(setup_scanner):
    recipe_scanner, _, _ = setup_scanner
    
    recipe_scanner._cache = SimpleNamespace(raw_data=[
        {"id": "r1", "repair_version": RecipeScanner.REPAIR_VERSION, "title": "Up to date"}
    ])
    
    # Run
    results = await recipe_scanner.repair_all_recipes()
    
    # Verify
    assert results["repaired"] == 0
    assert results["skipped"] == 1
    recipe_scanner._save_recipe_persistently.assert_not_called()

@pytest.mark.asyncio
async def test_repair_all_recipes_with_enriched_checkpoint_id(setup_scanner):
    recipe_scanner, mock_civitai_client, mock_metadata_provider = setup_scanner
    
    recipe = {
        "id": "r1",
        "title": "Old Recipe",
        "source_url": "https://civitai.com/images/12345",
        "checkpoint": None,
        "gen_params": {"prompt": ""}
    }
    recipe_scanner._cache = SimpleNamespace(raw_data=[recipe])
    
    # Mock image info returning modelVersionId
    mock_civitai_client.get_image_info.return_value = {
        "modelVersionId": 5678,
        "meta": {"prompt": "a beautiful forest", "Checkpoint": "basic_name.safetensors"}
    }
    
    # Mock metadata provider returning full info
    mock_metadata_provider.get_model_version_info.return_value = ({
        "id": 5678,
        "modelId": 1234,
        "name": "v1.0",
        "model": {"name": "Full Model Name"},
        "baseModel": "SDXL 1.0",
        "images": [{"url": "https://image.url/thumb.jpg"}],
        "files": [{"type": "Model", "hashes": {"SHA256": "ABCDEF"}, "name": "full_filename.safetensors"}]
    }, None)
    
    # Run
    results = await recipe_scanner.repair_all_recipes()
    
    # Verify
    assert results["repaired"] == 1
    mock_metadata_provider.get_model_version_info.assert_called_with("5678")
    
    saved_recipe = recipe_scanner._save_recipe_persistently.call_args[0][0]
    checkpoint = saved_recipe["checkpoint"]
    assert checkpoint["modelName"] == "Full Model Name"
    assert checkpoint["modelVersionName"] == "v1.0"
    assert checkpoint["modelId"] == 1234
    assert checkpoint["modelVersionId"] == 5678
    assert checkpoint["type"] == "checkpoint"
    assert "name" not in checkpoint
    assert "version" not in checkpoint
    assert "hash" not in checkpoint
    assert "file_name" not in checkpoint

@pytest.mark.asyncio
async def test_repair_all_recipes_with_enriched_checkpoint_hash(setup_scanner):
    recipe_scanner, mock_civitai_client, mock_metadata_provider = setup_scanner
    
    recipe = {
        "id": "r1",
        "title": "Embedded Only",
        "checkpoint": None,
        "gen_params": {
            "prompt": "",
            "Model hash": "hash123"
        }
    }
    recipe_scanner._cache = SimpleNamespace(raw_data=[recipe])
    
    # Mock metadata provider lookup by hash
    mock_metadata_provider.get_model_by_hash.return_value = ({
        "id": 999,
        "modelId": 888,
        "name": "v2.0",
        "model": {"name": "Hashed Model"},
        "baseModel": "SD 1.5",
        "files": [{"type": "Model", "hashes": {"SHA256": "hash123"}, "name": "hashed.safetensors"}]
    }, None)
    
    # Run
    results = await recipe_scanner.repair_all_recipes()
    
    # Verify
    assert results["repaired"] == 1
    mock_metadata_provider.get_model_by_hash.assert_called_with("hash123")
    
    saved_recipe = recipe_scanner._save_recipe_persistently.call_args[0][0]
    checkpoint = saved_recipe["checkpoint"]
    assert checkpoint["modelName"] == "Hashed Model"
    assert checkpoint["modelVersionName"] == "v2.0"
    assert checkpoint["modelId"] == 888
    assert checkpoint["type"] == "checkpoint"

@pytest.mark.asyncio
async def test_repair_all_recipes_fallback_to_basic(setup_scanner):
    recipe_scanner, mock_civitai_client, mock_metadata_provider = setup_scanner
    
    recipe = {
        "id": "r1",
        "title": "No Meta Lookup",
        "checkpoint": None,
        "gen_params": {
            "prompt": "",
            "Checkpoint": "just_a_name.safetensors"
        }
    }
    recipe_scanner._cache = SimpleNamespace(raw_data=[recipe])
    
    # Mock metadata provider returning nothing
    mock_metadata_provider.get_model_by_hash.return_value = (None, "Model not found")
    
    # Run
    results = await recipe_scanner.repair_all_recipes()
    
    # Verify
    assert results["repaired"] == 1
    saved_recipe = recipe_scanner._save_recipe_persistently.call_args[0][0]
    assert saved_recipe["checkpoint"]["modelName"] == "just_a_name.safetensors"
    assert saved_recipe["checkpoint"]["type"] == "checkpoint"
    assert "modelId" not in saved_recipe["checkpoint"]

@pytest.mark.asyncio
async def test_repair_all_recipes_progress_callback(setup_scanner):
    recipe_scanner, _, _ = setup_scanner
    
    recipe_scanner._cache = SimpleNamespace(raw_data=[
        {"id": "r1", "title": "R1", "checkpoint": None},
        {"id": "r2", "title": "R2", "checkpoint": None}
    ])
    
    progress_calls = []
    async def progress_callback(data):
        progress_calls.append(data)
    
    # Run
    await recipe_scanner.repair_all_recipes(
        progress_callback=progress_callback
    )
    
    # Verify
    assert len(progress_calls) >= 2
    assert progress_calls[-1]["status"] == "completed"
    assert progress_calls[-1]["total"] == 2
    assert progress_calls[-1]["repaired"] == 2

@pytest.mark.asyncio
async def test_repair_all_recipes_strips_runtime_fields(setup_scanner):
    recipe_scanner, mock_civitai_client, mock_metadata_provider = setup_scanner
    
    # Recipe with runtime fields
    recipe = {
        "id": "r1",
        "title": "Cleanup Test",
        "checkpoint": {
            "name": "CP",
            "inLibrary": True,
            "localPath": "/path/to/cp",
            "thumbnailUrl": "thumb.jpg"
        },
        "loras": [
            {
                "name": "L1",
                "weight": 0.8,
                "inLibrary": True,
                "localPath": "/path/to/l1",
                "preview_url": "p.jpg"
            }
        ],
        "gen_params": {"prompt": ""}
    }
    recipe_scanner._cache = SimpleNamespace(raw_data=[recipe])
    # Set high version to trigger repair if needed (or just ensure it processes)
    recipe["repair_version"] = 0 
    
    # Run
    await recipe_scanner.repair_all_recipes()
    
    # Verify sanitation
    assert recipe_scanner._save_recipe_persistently.called
    saved_recipe = recipe_scanner._save_recipe_persistently.call_args[0][0]
    
    # 1. Check LORA
    lora = saved_recipe["loras"][0]
    assert "inLibrary" not in lora
    assert "localPath" not in lora
    assert "preview_url" not in lora
    assert "strength" in lora # weight renamed to strength
    assert lora["strength"] == 0.8
    
    # 2. Check Checkpoint
    cp = saved_recipe["checkpoint"]
    assert "inLibrary" not in cp
    assert "localPath" not in cp
    assert "thumbnailUrl" not in cp

@pytest.mark.asyncio
async def test_sanitize_recipe_for_storage(recipe_scanner):

    recipe = {
        "loras": [{"name": "L1", "inLibrary": True, "weight": 0.5}],
        "checkpoint": {"name": "CP", "localPath": "/tmp/cp"}
    }
    
    clean = recipe_scanner._sanitize_recipe_for_storage(recipe)
    
    assert "inLibrary" not in clean["loras"][0]
    assert "strength" in clean["loras"][0]
    assert clean["loras"][0]["strength"] == 0.5
    assert "localPath" not in clean["checkpoint"]
    # Testing based on what enricher would produce if it ran, 
    # but here we are just testing the sanitizer which handles what is ALREADY there.
    # However, the sanitizer doesn't rename fields, it just removes runtime ones.
    # Since we changed the enricher to NOT put 'name' anymore, this test case 
    # should probably reflect the new fields if it's simulating a real recipe.
    assert clean["checkpoint"]["name"] == "CP"
