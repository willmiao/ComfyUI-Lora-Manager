"""
Unit tests for the service layer components
"""
import os
import json
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, mock_open
from pathlib import Path

from py.services.model_metadata_service import ModelMetadataService
from py.services.model_file_service import ModelFileService
from py.services.model_preview_service import ModelPreviewService
from py.services.service_container import ServiceContainer, DefaultServiceContainer


class TestModelMetadataService:
    """Unit tests for ModelMetadataService"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.service = ModelMetadataService()
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"name": "Test Model", "base_model": "SD 1.5"}')
    async def test_load_local_metadata_success(self, mock_file, mock_exists):
        """Test successful metadata loading"""
        mock_exists.return_value = True
        
        result = await self.service.load_local_metadata('/test/metadata.json')
        
        assert result == {"name": "Test Model", "base_model": "SD 1.5"}
        mock_exists.assert_called_once_with('/test/metadata.json')
        mock_file.assert_called_once_with('/test/metadata.json', 'r', encoding='utf-8')
    
    @patch('os.path.exists')
    async def test_load_local_metadata_file_not_exists(self, mock_exists):
        """Test metadata loading when file doesn't exist"""
        mock_exists.return_value = False
        
        result = await self.service.load_local_metadata('/nonexistent/metadata.json')
        
        assert result == {}
        mock_exists.assert_called_once_with('/nonexistent/metadata.json')
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='invalid json')
    async def test_load_local_metadata_invalid_json(self, mock_file, mock_exists):
        """Test metadata loading with invalid JSON"""
        mock_exists.return_value = True
        
        result = await self.service.load_local_metadata('/test/invalid.json')
        
        assert result == {}  # Should return empty dict on JSON error
    
    def test_is_civitai_api_metadata(self):
        """Test CivitAI API metadata detection"""
        # Valid API metadata
        api_metadata = {
            'files': [{'name': 'model.safetensors'}],
            'images': [{'url': 'https://example.com/image.jpg'}],
            'source': 'api'
        }
        assert self.service.is_civitai_api_metadata(api_metadata) is True
        
        # Archive DB metadata (should return False)
        archive_metadata = {
            'files': [{'name': 'model.safetensors'}],
            'images': [{'url': 'https://example.com/image.jpg'}],
            'source': 'archive_db'
        }
        assert self.service.is_civitai_api_metadata(archive_metadata) is False
        
        # Missing required fields
        incomplete_metadata = {'files': []}
        assert self.service.is_civitai_api_metadata(incomplete_metadata) is False
        
        # Non-dict input
        assert self.service.is_civitai_api_metadata("not a dict") is False
    
    @patch('py.services.model_metadata_service.MetadataManager.save_metadata')
    async def test_update_model_metadata(self, mock_save):
        """Test model metadata update"""
        mock_save.return_value = None
        
        local_metadata = {'name': 'Old Name'}
        civitai_metadata = {
            'name': 'New Name',
            'baseModel': 'SD 1.5',
            'trainedWords': ['test'],
            'model': {
                'name': 'Model Name',
                'description': 'Model description'
            }
        }
        
        await self.service.update_model_metadata(
            '/test/metadata.json',
            local_metadata,
            civitai_metadata
        )
        
        # Check that local_metadata was updated
        assert local_metadata['civitai'] == civitai_metadata
        assert local_metadata['base_model'] == 'SD 1.5'
        assert local_metadata['model_name'] == 'Model Name'
        assert local_metadata['description'] == 'Model description'
        
        mock_save.assert_called_once()
    
    @patch('py.services.model_metadata_service.MetadataManager.save_metadata')
    async def test_update_metadata_preserves_existing_data(self, mock_save):
        """Test that metadata update preserves existing trained words and custom images"""
        mock_save.return_value = None
        
        local_metadata = {
            'civitai': {
                'trainedWords': ['existing', 'words'],
                'customImages': [{'url': 'existing.jpg'}]
            }
        }
        
        civitai_metadata = {
            'name': 'New Name',
            'baseModel': 'SD 1.5'
            # No trainedWords or customImages - should preserve existing
        }
        
        await self.service.update_model_metadata(
            '/test/metadata.json',
            local_metadata,
            civitai_metadata
        )
        
        # Should preserve existing trained words and custom images
        assert local_metadata['civitai']['trainedWords'] == ['existing', 'words']
        assert local_metadata['civitai']['customImages'] == [{'url': 'existing.jpg'}]
    
    def test_filter_civitai_data(self):
        """Test CivitAI data filtering"""
        full_data = {
            'id': 12345,
            'name': 'Test Model',
            'trainedWords': ['test'],
            'baseModel': 'SD 1.5',
            'description': 'Test description',
            'extra_field': 'should be removed',
            'another_extra': 'also removed'
        }
        
        # Test minimal filtering
        minimal_result = self.service.filter_civitai_data(full_data, minimal=True)
        expected_minimal_keys = {'id', 'name', 'trainedWords'}
        assert set(minimal_result.keys()).issubset(expected_minimal_keys)
        
        # Test full filtering
        full_result = self.service.filter_civitai_data(full_data, minimal=False)
        assert 'extra_field' not in full_result
        assert 'another_extra' not in full_result
        assert 'id' in full_result
        assert 'name' in full_result
        assert 'trainedWords' in full_result
        
        # Test with empty data
        assert self.service.filter_civitai_data({}) == {}
        assert self.service.filter_civitai_data(None) == {}
    
    @patch('py.services.model_metadata_service.get_default_metadata_provider')
    async def test_fetch_and_update_model_success(self, mock_provider):
        """Test successful model fetch and update"""
        # Setup mocks
        mock_metadata_provider = AsyncMock()
        mock_metadata_provider.get_model_by_hash.return_value = {
            'name': 'Test Model',
            'baseModel': 'SD 1.5'
        }
        mock_provider.return_value = mock_metadata_provider
        
        mock_update_cache = AsyncMock(return_value=True)
        
        with patch.object(self.service, 'load_local_metadata') as mock_load:
            mock_load.return_value = {}
            
            with patch.object(self.service, 'update_model_metadata') as mock_update:
                mock_update.return_value = None
                
                result = await self.service.fetch_and_update_model(
                    'a' * 64,  # SHA256
                    '/test/model.safetensors',
                    {},
                    mock_update_cache
                )
                
                assert result is True
                mock_metadata_provider.get_model_by_hash.assert_called_once()
                mock_update_cache.assert_called_once()
    
    @patch('py.services.model_metadata_service.get_default_metadata_provider')
    async def test_fetch_and_update_model_not_found(self, mock_provider):
        """Test model fetch when model not found on CivitAI"""
        mock_metadata_provider = AsyncMock()
        mock_metadata_provider.get_model_by_hash.return_value = None
        mock_provider.return_value = mock_metadata_provider
        
        mock_update_cache = AsyncMock()
        
        result = await self.service.fetch_and_update_model(
            'a' * 64,
            '/test/model.safetensors',
            {},
            mock_update_cache
        )
        
        assert result is False
        mock_update_cache.assert_not_called()


class TestModelFileService:
    """Unit tests for ModelFileService"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.service = ModelFileService()
    
    @patch('os.path.exists')
    @patch('os.remove')
    async def test_delete_model_files_success(self, mock_remove, mock_exists):
        """Test successful model file deletion"""
        # Setup: main file exists, some associated files exist
        def exists_side_effect(path):
            if path.endswith('.safetensors'):
                return True
            elif path.endswith('.metadata.json'):
                return True
            elif path.endswith('.jpg'):
                return True
            return False
        
        mock_exists.side_effect = exists_side_effect
        
        result = await self.service.delete_model_files('/test/dir', 'model')
        
        # Should have attempted to delete multiple files
        assert len(result) >= 1  # At least the main file
        assert any('.safetensors' in path for path in result)
        
        # Verify remove was called
        assert mock_remove.call_count >= 1
    
    @patch('os.path.exists')
    @patch('os.remove')
    async def test_delete_model_files_main_not_exists(self, mock_remove, mock_exists):
        """Test deletion when main file doesn't exist"""
        mock_exists.return_value = False
        
        result = await self.service.delete_model_files('/test/dir', 'model')
        
        # Should still try to delete associated files
        assert isinstance(result, list)
    
    @patch('os.path.exists')
    @patch('os.remove')
    async def test_delete_model_files_remove_error(self, mock_remove, mock_exists):
        """Test handling of file removal errors"""
        mock_exists.return_value = True
        mock_remove.side_effect = OSError("Permission denied")
        
        with pytest.raises(OSError):
            await self.service.delete_model_files('/test/dir', 'model')
    
    def test_get_multipart_ext(self):
        """Test multipart extension parsing"""
        assert self.service.get_multipart_ext('model.metadata.json') == '.metadata.json'
        assert self.service.get_multipart_ext('model.metadata.json.bak') == '.metadata.json.bak'
        assert self.service.get_multipart_ext('model.safetensors') == '.safetensors'
        assert self.service.get_multipart_ext('simple.txt') == '.txt'
    
    @patch('os.makedirs')
    @patch('os.rename')
    async def test_move_model_file_success(self, mock_rename, mock_makedirs):
        """Test successful model file move"""
        result = await self.service.move_model_file(
            '/source/model.safetensors',
            '/target/model.safetensors'
        )
        
        assert result is True
        mock_makedirs.assert_called_once()
        mock_rename.assert_called_once()
    
    @patch('os.makedirs')
    @patch('os.rename')
    async def test_move_model_file_error(self, mock_rename, mock_makedirs):
        """Test model file move with error"""
        mock_rename.side_effect = OSError("File in use")
        
        result = await self.service.move_model_file(
            '/source/model.safetensors',
            '/target/model.safetensors'
        )
        
        assert result is False
    
    @patch('shutil.copy2')
    @patch('os.makedirs')
    async def test_copy_model_file_success(self, mock_makedirs, mock_copy):
        """Test successful model file copy"""
        result = await self.service.copy_model_file(
            '/source/model.safetensors',
            '/target/model.safetensors'
        )
        
        assert result is True
        mock_makedirs.assert_called_once()
        mock_copy.assert_called_once()
    
    @patch('os.path.exists')
    @patch('os.path.isfile')
    def test_file_exists(self, mock_isfile, mock_exists):
        """Test file existence check"""
        mock_exists.return_value = True
        mock_isfile.return_value = True
        
        assert self.service.file_exists('/test/file.txt') is True
        
        mock_exists.return_value = False
        assert self.service.file_exists('/nonexistent/file.txt') is False
    
    @patch('os.path.getsize')
    def test_get_file_size(self, mock_getsize):
        """Test file size retrieval"""
        mock_getsize.return_value = 1024
        
        assert self.service.get_file_size('/test/file.txt') == 1024
        
        # Test with OSError
        mock_getsize.side_effect = OSError("File not found")
        assert self.service.get_file_size('/nonexistent/file.txt') == 0
    
    def test_sanitize_filename(self):
        """Test filename sanitization"""
        assert self.service.sanitize_filename('normal_file.txt') == 'normal_file.txt'
        assert self.service.sanitize_filename('file<>with:bad/chars') == 'file__with_bad_chars'
        assert self.service.sanitize_filename('  spaced  ') == 'spaced'
        assert self.service.sanitize_filename('') == 'untitled'
        assert self.service.sanitize_filename('...dots...') == 'dots'


class TestModelPreviewService:
    """Unit tests for ModelPreviewService"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.service = ModelPreviewService()
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('base64.b64decode')
    @patch('py.services.model_preview_service.config')
    async def test_replace_preview_with_base64(self, mock_config, mock_b64decode, mock_file):
        """Test preview replacement with base64 data"""
        mock_config.static_path = '/app/static'
        mock_b64decode.return_value = b'fake image data'
        
        result = await self.service.replace_preview(
            '/models/test.safetensors',
            'data:image/jpeg;base64,/9j/4AAQSkZJRg...'
        )
        
        assert result['success'] is True
        assert 'preview_url' in result
        mock_file.assert_called_once()
        mock_b64decode.assert_called_once()
    
    @patch('aiohttp.ClientSession')
    @patch('py.services.model_preview_service.config')
    async def test_replace_preview_with_url(self, mock_config, mock_session):
        """Test preview replacement with URL"""
        mock_config.static_path = '/app/static'
        
        # Setup mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read.return_value = b'fake image data'
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        with patch('builtins.open', mock_open()):
            result = await self.service.replace_preview(
                '/models/test.safetensors',
                'https://example.com/image.jpg'
            )
        
        assert result['success'] is True
        assert 'preview_url' in result
    
    async def test_replace_preview_with_invalid_data(self):
        """Test preview replacement with invalid data"""
        result = await self.service.replace_preview(
            '/models/test.safetensors',
            'invalid_data_format'
        )
        
        assert result['success'] is False
        assert 'error' in result
    
    @patch('os.path.exists')
    def test_get_preview_path(self, mock_exists):
        """Test preview path retrieval"""
        # Setup: .jpg file exists
        def exists_side_effect(path):
            return path.endswith('.jpg')
        
        mock_exists.side_effect = exists_side_effect
        
        result = self.service.get_preview_path('/models/test.safetensors')
        
        assert result.endswith('.jpg')
        assert 'test' in result
    
    @patch('os.path.exists')
    def test_get_preview_path_not_found(self, mock_exists):
        """Test preview path when no preview exists"""
        mock_exists.return_value = False
        
        result = self.service.get_preview_path('/models/test.safetensors')
        
        assert result is None
    
    @patch('py.services.model_preview_service.config')
    def test_get_preview_url(self, mock_config):
        """Test preview URL generation"""
        mock_config.static_path = '/app/static'
        
        with patch.object(self.service, 'get_preview_path') as mock_get_path:
            mock_get_path.return_value = '/app/static/previews/test.jpg'
            
            result = self.service.get_preview_url('/models/test.safetensors')
            
            assert result == '/static/previews/test.jpg'
    
    def test_has_preview(self):
        """Test preview existence check"""
        with patch.object(self.service, 'get_preview_path') as mock_get_path:
            mock_get_path.return_value = '/path/to/preview.jpg'
            assert self.service.has_preview('/models/test.safetensors') is True
            
            mock_get_path.return_value = None
            assert self.service.has_preview('/models/test.safetensors') is False
    
    @patch('os.remove')
    async def test_delete_preview_success(self, mock_remove):
        """Test successful preview deletion"""
        with patch.object(self.service, 'get_preview_path') as mock_get_path:
            mock_get_path.return_value = '/path/to/preview.jpg'
            
            result = await self.service.delete_preview('/models/test.safetensors')
            
            assert result is True
            mock_remove.assert_called_once_with('/path/to/preview.jpg')
    
    @patch('os.remove')
    async def test_delete_preview_no_file(self, mock_remove):
        """Test preview deletion when no preview exists"""
        with patch.object(self.service, 'get_preview_path') as mock_get_path:
            mock_get_path.return_value = None
            
            result = await self.service.delete_preview('/models/test.safetensors')
            
            assert result is False
            mock_remove.assert_not_called()


class TestServiceContainer:
    """Unit tests for ServiceContainer"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.container = ServiceContainer()
    
    def test_register_and_get_singleton(self):
        """Test singleton registration and retrieval"""
        service = Mock()
        self.container.register_singleton('test_service', service)
        
        retrieved = self.container.get_service('test_service')
        
        assert retrieved is service
        
        # Should return the same instance
        retrieved2 = self.container.get_service('test_service')
        assert retrieved2 is service
    
    def test_register_and_get_factory(self):
        """Test factory registration and retrieval"""
        service_instance = Mock()
        factory = Mock(return_value=service_instance)
        
        self.container.register_factory('factory_service', factory)
        
        # First call should invoke factory
        retrieved = self.container.get_service('factory_service')
        
        assert retrieved is service_instance
        factory.assert_called_once()
        
        # Second call should return cached instance
        retrieved2 = self.container.get_service('factory_service')
        assert retrieved2 is service_instance
        factory.assert_called_once()  # Still only called once
    
    def test_get_nonexistent_service(self):
        """Test retrieving non-existent service"""
        result = self.container.get_service('nonexistent')
        
        assert result is None
    
    def test_get_or_create(self):
        """Test get_or_create functionality"""
        # First call should create new instance
        service1 = self.container.get_or_create('test_service', Mock, 'arg1', kwarg='kwarg1')
        
        # Second call should return existing instance
        service2 = self.container.get_or_create('test_service', Mock, 'arg2', kwarg='kwarg2')
        
        assert service1 is service2
    
    def test_clear(self):
        """Test container clearing"""
        self.container.register_singleton('test_service', Mock())
        
        assert self.container.get_service('test_service') is not None
        
        self.container.clear()
        
        assert self.container.get_service('test_service') is None
    
    @patch('py.services.service_container.ServiceRegistry')
    def test_default_service_container(self, mock_registry):
        """Test DefaultServiceContainer initialization"""
        container = DefaultServiceContainer()
        
        # Should have default services registered
        assert container.get_metadata_service() is not None
        assert container.get_file_service() is not None
        assert container.get_preview_service() is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
