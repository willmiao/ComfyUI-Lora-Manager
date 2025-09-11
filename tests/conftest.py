"""
pytest configuration file for the new architecture tests
"""
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, AsyncMock
from aiohttp import web

# Global test configuration
pytest_plugins = []


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config():
    """Mock configuration for tests"""
    mock = Mock()
    mock.templates_path = str(project_root / "templates")
    mock.static_path = str(project_root / "static")
    mock.models_path = str(project_root / "models")
    return mock


@pytest.fixture
def mock_logger():
    """Mock logger for tests"""
    return Mock()


@pytest.fixture
def sample_lora_data():
    """Sample LoRA data for testing"""
    return {
        'file_path': '/models/loras/test_lora.safetensors',
        'name': 'Test LoRA',
        'hash': 'a' * 64,
        'size': 1024 * 1024,  # 1MB
        'civitai': {
            'id': 12345,
            'name': 'Test LoRA',
            'trainedWords': ['test', 'anime'],
            'baseModel': 'SD 1.5'
        },
        'metadata': {
            'description': 'A test LoRA model',
            'tags': ['anime', 'character']
        }
    }


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing"""
    return {
        'name': 'Test Model',
        'description': 'A test model for unit testing',
        'base_model': 'SD 1.5',
        'tags': ['test', 'sample'],
        'civitai': {
            'id': 12345,
            'modelId': 12345,
            'name': 'Test Model',
            'trainedWords': ['test', 'sample'],
            'baseModel': 'SD 1.5',
            'images': [
                {'url': 'https://example.com/preview.jpg'}
            ]
        },
        'preview_url': '/static/previews/test.jpg'
    }


@pytest.fixture
def temp_model_files(tmp_path):
    """Create temporary model files for testing"""
    models_dir = tmp_path / "models" / "loras"
    models_dir.mkdir(parents=True)
    
    # Create test files
    model_file = models_dir / "test_model.safetensors"
    model_file.write_bytes(b"fake model data")
    
    metadata_file = models_dir / "test_model.metadata.json"
    metadata_file.write_text('{"name": "Test Model", "description": "Test"}')
    
    preview_file = models_dir / "test_model.jpg"
    preview_file.write_bytes(b"fake image data")
    
    return {
        'models_dir': models_dir,
        'model_file': model_file,
        'metadata_file': metadata_file,
        'preview_file': preview_file
    }


@pytest.fixture
def mock_websocket_manager():
    """Mock websocket manager"""
    mock = Mock()
    mock.send_message = AsyncMock()
    return mock


@pytest.fixture
def mock_civitai_response():
    """Mock CivitAI API response"""
    return {
        'id': 12345,
        'modelId': 12345,
        'name': 'Test Model',
        'description': 'A test model from CivitAI',
        'baseModel': 'SD 1.5',
        'trainedWords': ['test', 'sample'],
        'images': [
            {
                'url': 'https://example.com/preview.jpg',
                'nsfw': 'None',
                'width': 512,
                'height': 512
            }
        ],
        'files': [
            {
                'name': 'test_model.safetensors',
                'type': 'Model',
                'primary': True,
                'sizeKB': 1024,
                'hashes': {
                    'SHA256': 'a' * 64
                }
            }
        ],
        'model': {
            'name': 'Test Model',
            'description': 'Model description',
            'creator': {
                'username': 'testuser'
            }
        }
    }


# Test markers
def pytest_configure(config):
    """Configure custom pytest markers"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as a performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Custom test collection
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically"""
    for item in items:
        # Add unit marker to tests in unit test classes
        if "Unit" in item.cls.__name__ if item.cls else False:
            item.add_marker(pytest.mark.unit)
        
        # Add integration marker to tests in integration test classes  
        elif "Integration" in item.cls.__name__ if item.cls else False:
            item.add_marker(pytest.mark.integration)
        
        # Add performance marker to performance tests
        elif "Performance" in item.cls.__name__ if item.cls else False:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)
