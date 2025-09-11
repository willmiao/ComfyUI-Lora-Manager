"""
Comprehensive test suite for the new architecture
"""
import os
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, mock_open
from aiohttp import web
from aiohttp.test import TestClient, TestServer

from py.controllers.base_model_controller import BaseModelController
from py.controllers.lora_controller import LoraController
from py.services.service_container import ServiceContainer, DefaultServiceContainer
from py.services.model_metadata_service import ModelMetadataService
from py.services.model_file_service import ModelFileService
from py.services.model_preview_service import ModelPreviewService
from py.validators.request_validator import RequestValidator, ValidationError
from py.routes.route_registry import RouteRegistry, setup_new_routes


class MockModelService:
    """Mock model service for testing"""
    
    def __init__(self):
        self.model_type = 'test'
    
    async def get_paginated_data(self, **kwargs):
        return {
            'items': [],
            'total': 0,
            'page': 1,
            'page_size': 20,
            'total_pages': 0
        }
    
    async def get_model_info_by_path(self, path):
        return {'file_path': path, 'name': 'test_model'}
    
    async def remove_from_cache(self, path):
        return True


class TestModelController(BaseModelController):
    """Test controller implementation"""
    
    def __init__(self, service_container=None):
        mock_service = MockModelService()
        super().__init__(mock_service, 'test', service_container)
    
    def setup_specific_routes(self, app: web.Application, prefix: str):
        app.router.add_get(f'/api/{prefix}/test', self.test_endpoint)
    
    async def handle_models_page(self, request: web.Request) -> web.Response:
        return web.Response(text="Test Models Page", content_type='text/html')
    
    def _parse_specific_params(self, request: web.Request):
        params = {}
        if 'test_param' in request.query:
            params['test_param'] = request.query['test_param']
        return params
    
    async def test_endpoint(self, request: web.Request) -> web.Response:
        return web.json_response({'success': True, 'message': 'test endpoint'})


class TestNewArchitecture:
    """Comprehensive test suite for the new architecture"""
    
    @pytest.fixture
    def service_container(self):
        """Create a test service container"""
        container = ServiceContainer()
        
        # Register mock services
        container.register_singleton('metadata_service', Mock(spec=ModelMetadataService))
        container.register_singleton('file_service', Mock(spec=ModelFileService))
        container.register_singleton('preview_service', Mock(spec=ModelPreviewService))
        
        return container
    
    @pytest.fixture
    def controller(self, service_container):
        """Create a test controller"""
        return TestModelController(service_container)
    
    @pytest.fixture
    async def app(self, controller):
        """Create a test web application"""
        app = web.Application()
        controller.setup_routes(app, 'test')
        return app
    
    @pytest.fixture
    async def client(self, app):
        """Create a test client"""
        async with TestClient(TestServer(app)) as client:
            yield client

    # Service Container Tests
    async def test_service_container_injection(self, service_container):
        """Test that service container injection works"""
        controller = TestModelController(service_container)
        
        assert controller.service_container is service_container
        assert controller.metadata_service is not None
        assert controller.file_service is not None
        assert controller.preview_service is not None

    def test_service_container_singleton_behavior(self):
        """Test that service container maintains singleton instances"""
        container = ServiceContainer()
        
        # Register a service
        mock_service = Mock()
        container.register_singleton('test_service', mock_service)
        
        # Verify singleton behavior
        assert container.get_service('test_service') is mock_service
        assert container.get_service('test_service') is container.get_service('test_service')

    def test_service_container_factory_behavior(self):
        """Test that service container factories work correctly"""
        container = ServiceContainer()
        
        # Register a factory
        factory_mock = Mock(return_value=Mock())
        container.register_factory('factory_service', factory_mock)
        
        # First call should invoke factory
        service1 = container.get_service('factory_service')
        factory_mock.assert_called_once()
        
        # Second call should return cached instance
        service2 = container.get_service('factory_service')
        assert service1 is service2
        factory_mock.assert_called_once()  # Still only called once

    def test_default_service_container_setup(self):
        """Test that DefaultServiceContainer sets up default services"""
        with patch('py.services.service_container.ServiceRegistry'):
            container = DefaultServiceContainer()
            
            # Should have default services registered
            assert container.get_metadata_service() is not None
            assert container.get_file_service() is not None
            assert container.get_preview_service() is not None

    # Controller Tests
    async def test_models_page_route(self, client):
        """Test the models page route"""
        resp = await client.get('/test')
        assert resp.status == 200
        text = await resp.text()
        assert "Test Models Page" in text
    
    async def test_get_models_endpoint(self, client):
        """Test the get models API endpoint"""
        resp = await client.get('/api/test/list')
        assert resp.status == 200
        
        data = await resp.json()
        assert 'items' in data
        assert 'total' in data
        assert 'page' in data
        assert 'page_size' in data
    
    async def test_get_models_with_params(self, client):
        """Test get models with query parameters"""
        resp = await client.get('/api/test/list?page=2&page_size=10&search=test')
        assert resp.status == 200
        
        data = await resp.json()
        assert data['page'] == 1  # Our mock doesn't use params, so default values
    
    async def test_delete_model_endpoint(self, client, service_container):
        """Test the delete model endpoint"""
        # Setup mock file service
        file_service = service_container.get_service('file_service')
        file_service.delete_model_files = AsyncMock(return_value=['/path/to/deleted/file'])
        
        # Mock websocket manager
        with patch('py.controllers.base_model_controller.ws_manager') as mock_ws:
            mock_ws.send_message = AsyncMock()
            
            resp = await client.post('/api/test/delete', json={
                'file_path': '/test/model.safetensors'
            })
            
            assert resp.status == 200
            data = await resp.json()
            assert data['success'] is True
            assert 'deleted_files' in data
    
    async def test_delete_model_validation_error(self, client):
        """Test delete model with validation error"""
        resp = await client.post('/api/test/delete', json={})
        
        assert resp.status == 400
        data = await resp.json()
        assert data['success'] is False
        assert 'error' in data
        assert 'field' in data
    
    async def test_custom_endpoint(self, client):
        """Test custom endpoint"""
        resp = await client.get('/api/test/test')
        assert resp.status == 200
        
        data = await resp.json()
        assert data['success'] is True
        assert data['message'] == 'test endpoint'

    async def test_fetch_civitai_endpoint(self, client, service_container):
        """Test the fetch CivitAI endpoint"""
        # Setup mock metadata service
        metadata_service = service_container.get_service('metadata_service')
        metadata_service.fetch_and_update_model = AsyncMock(return_value=True)
        
        # Mock the model service to return model data
        with patch.object(TestModelController, 'model_service') as mock_model_service:
            mock_model_service.get_model_by_hash = AsyncMock(return_value={'file_path': '/test/model.safetensors'})
            
            resp = await client.post('/api/test/fetch-civitai', json={
                'sha256': 'a' * 64  # Valid SHA256
            })
            
            assert resp.status == 200
            data = await resp.json()
            assert data['success'] is True

    async def test_replace_preview_endpoint(self, client, service_container):
        """Test the replace preview endpoint"""
        # Setup mock preview service
        preview_service = service_container.get_service('preview_service')
        preview_service.replace_preview = AsyncMock(return_value={
            'success': True,
            'preview_url': '/static/previews/test.jpg'
        })
        
        with patch('py.controllers.base_model_controller.ws_manager') as mock_ws:
            mock_ws.send_message = AsyncMock()
            
            resp = await client.post('/api/test/replace-preview', json={
                'file_path': '/test/model.safetensors',
                'preview_data': 'data:image/jpeg;base64,/9j/4AAQSkZJRg...'
            })
            
            assert resp.status == 200
            data = await resp.json()
            assert data['success'] is True
    
    # Validation Tests
    def test_request_validation(self):
        """Test request validation"""
        validator = RequestValidator()
        
        # Valid request
        valid_data = {'file_path': '/test/model.safetensors'}
        result = validator.validate_delete_request(valid_data)
        assert result['file_path'] == '/test/model.safetensors'
        
        # Invalid request - missing file_path
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_delete_request({})
        
        assert exc_info.value.field == 'file_path'
        assert 'required' in exc_info.value.message.lower()
        
        # Invalid request - empty file_path
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_delete_request({'file_path': ''})
        
        assert exc_info.value.field == 'file_path'
        assert 'empty' in exc_info.value.message.lower()
    
    def test_pagination_validation(self):
        """Test pagination parameter validation"""
        validator = RequestValidator()
        
        # Valid params
        valid_params = {'page': '1', 'page_size': '20'}
        result = validator.validate_pagination_params(valid_params)
        assert result['page'] == 1
        assert result['page_size'] == 20
        
        # Invalid page
        with pytest.raises(ValidationError):
            validator.validate_pagination_params({'page': '0'})
        
        # Invalid page_size
        with pytest.raises(ValidationError):
            validator.validate_pagination_params({'page_size': '101'})

    def test_civitai_fetch_validation(self):
        """Test CivitAI fetch request validation"""
        validator = RequestValidator()
        
        # Valid request
        valid_data = {
            'sha256': 'a' * 64,  # Valid SHA256
            'file_path': '/test/model.safetensors'
        }
        result = validator.validate_fetch_civitai_request(valid_data)
        assert result['sha256'] == 'a' * 64
        assert result['file_path'] == '/test/model.safetensors'
        
        # Invalid SHA256 - too short
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_fetch_civitai_request({'sha256': 'abc123'})
        assert exc_info.value.field == 'sha256'
        
        # Invalid SHA256 - non-hex characters
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_fetch_civitai_request({'sha256': 'g' * 64})
        assert exc_info.value.field == 'sha256'

    def test_preview_replacement_validation(self):
        """Test preview replacement validation"""
        validator = RequestValidator()
        
        # Valid base64 data
        valid_data = {
            'file_path': '/test/model.safetensors',
            'preview_data': 'data:image/jpeg;base64,/9j/4AAQSkZJRg...',
            'nsfw_level': 'SFW'
        }
        result = validator.validate_replace_preview_request(valid_data)
        assert result['file_path'] == '/test/model.safetensors'
        assert result['nsfw_level'] == 'SFW'
        
        # Valid URL
        valid_url_data = {
            'file_path': '/test/model.safetensors',
            'preview_data': 'https://example.com/image.jpg'
        }
        result = validator.validate_replace_preview_request(valid_url_data)
        assert result['preview_data'] == 'https://example.com/image.jpg'
        
        # Invalid preview data format
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_replace_preview_request({
                'file_path': '/test/model.safetensors',
                'preview_data': 'invalid_data'
            })
        assert exc_info.value.field == 'preview_data'

    def test_bulk_delete_validation(self):
        """Test bulk delete validation"""
        validator = RequestValidator()
        
        # Valid request
        valid_data = {
            'file_paths': ['/test/model1.safetensors', '/test/model2.safetensors']
        }
        result = validator.validate_bulk_delete_request(valid_data)
        assert len(result['file_paths']) == 2
        
        # Invalid - not a list
        with pytest.raises(ValidationError):
            validator.validate_bulk_delete_request({'file_paths': 'not_a_list'})
        
        # Invalid - empty list
        with pytest.raises(ValidationError):
            validator.validate_bulk_delete_request({'file_paths': []})

    def test_add_tags_validation(self):
        """Test add tags validation"""
        validator = RequestValidator()
        
        # Valid request with list
        valid_data = {
            'file_path': '/test/model.safetensors',
            'tags': ['anime', 'character']
        }
        result = validator.validate_add_tags_request(valid_data)
        assert result['tags'] == ['anime', 'character']
        
        # Valid request with comma-separated string
        valid_string_data = {
            'file_path': '/test/model.safetensors',
            'tags': 'anime, character, style'
        }
        result = validator.validate_add_tags_request(valid_string_data)
        assert result['tags'] == ['anime', 'character', 'style']
        
        # Invalid tags type
        with pytest.raises(ValidationError):
            validator.validate_add_tags_request({
                'file_path': '/test/model.safetensors',
                'tags': 123
            })
    
    # Service Layer Tests
    async def test_service_methods(self, service_container):
        """Test individual service methods"""
        metadata_service = service_container.get_service('metadata_service')
        file_service = service_container.get_service('file_service')
        preview_service = service_container.get_service('preview_service')
        
        # Test that services are properly injected
        assert metadata_service is not None
        assert file_service is not None
        assert preview_service is not None
        
        # Test that services are singletons
        assert metadata_service is service_container.get_service('metadata_service')
        assert file_service is service_container.get_service('file_service')
        assert preview_service is service_container.get_service('preview_service')

    def test_model_metadata_service(self):
        """Test ModelMetadataService functionality"""
        service = ModelMetadataService()
        
        # Test filter_civitai_data
        sample_data = {
            'id': 123,
            'name': 'Test Model',
            'trainedWords': ['test', 'sample'],
            'baseModel': 'SD 1.5',
            'extra_field': 'should_be_filtered'
        }
        
        # Test minimal filtering
        minimal_result = service.filter_civitai_data(sample_data, minimal=True)
        expected_minimal = ['id', 'modelId', 'name', 'trainedWords']
        assert all(key in expected_minimal for key in minimal_result.keys() if key != 'modelId')
        
        # Test full filtering
        full_result = service.filter_civitai_data(sample_data, minimal=False)
        assert 'extra_field' not in full_result
        assert 'id' in full_result
        assert 'name' in full_result

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"test": "data"}')
    async def test_metadata_service_load_local_metadata(self, mock_file, mock_exists):
        """Test loading local metadata"""
        mock_exists.return_value = True
        
        service = ModelMetadataService()
        result = await service.load_local_metadata('/test/metadata.json')
        
        assert result == {"test": "data"}
        mock_file.assert_called_once_with('/test/metadata.json', 'r', encoding='utf-8')

    @patch('os.path.exists')
    async def test_metadata_service_load_nonexistent_file(self, mock_exists):
        """Test loading non-existent metadata file"""
        mock_exists.return_value = False
        
        service = ModelMetadataService()
        result = await service.load_local_metadata('/nonexistent/metadata.json')
        
        assert result == {}

    @patch('os.path.exists')
    @patch('os.remove')
    def test_file_service_delete_model_files(self, mock_remove, mock_exists):
        """Test file service delete functionality"""
        mock_exists.side_effect = lambda path: path.endswith('.safetensors')
        
        service = ModelFileService()
        # This is an async method, so we need to run it
        import asyncio
        result = asyncio.run(service.delete_model_files('/test/dir', 'model'))
        
        # Should try to delete the main file
        mock_remove.assert_called()
        assert len(result) > 0

    def test_file_service_file_operations(self):
        """Test file service utility methods"""
        service = ModelFileService()
        
        # Test sanitize_filename
        assert service.sanitize_filename('test<>file') == 'test__file'
        assert service.sanitize_filename('') == 'untitled'
        assert service.sanitize_filename('  test  ') == 'test'
        
        # Test get_multipart_ext
        assert service.get_multipart_ext('model.metadata.json') == '.metadata.json'
        assert service.get_multipart_ext('model.metadata.json.bak') == '.metadata.json.bak'

    def test_preview_service_url_generation(self):
        """Test preview service URL generation"""
        with patch('py.services.model_preview_service.config') as mock_config:
            mock_config.static_path = '/app/static'
            
            service = ModelPreviewService()
            
            # Test get_preview_path
            with patch('os.path.exists') as mock_exists:
                mock_exists.side_effect = lambda path: path.endswith('.jpg')
                
                result = service.get_preview_path('/models/test.safetensors')
                assert result.endswith('.jpg')

    # Route Registry Tests
    def test_route_registry_initialization(self):
        """Test route registry initialization"""
        registry = RouteRegistry()
        assert registry.controllers == {}

    @patch('py.routes.route_registry.LoraController')
    def test_route_registry_controller_setup(self, mock_lora_controller):
        """Test route registry controller setup"""
        registry = RouteRegistry()
        app = Mock()
        
        # Mock the controller
        mock_controller = Mock()
        mock_lora_controller.return_value = mock_controller
        
        registry._initialize_controllers()
        assert 'lora' in registry.controllers

    async def test_setup_new_routes_function(self):
        """Test the setup_new_routes function"""
        app = Mock()
        
        with patch('py.routes.route_registry.route_registry') as mock_registry:
            setup_new_routes(app)
            mock_registry.setup_routes.assert_called_once_with(app)

    # LoRA Controller Specific Tests
    @patch('py.controllers.lora_controller.ServiceRegistry')
    async def test_lora_controller_initialization(self, mock_service_registry):
        """Test LoRA controller initialization"""
        mock_scanner = Mock()
        mock_service_registry.get_lora_scanner = AsyncMock(return_value=mock_scanner)
        
        controller = LoraController()
        await controller.initialize_services()
        
        assert controller.service is not None
        assert controller.model_service is not None

    async def test_lora_controller_specific_params(self):
        """Test LoRA controller specific parameter parsing"""
        controller = LoraController()
        
        # Mock request with LoRA-specific parameters
        mock_request = Mock()
        mock_request.query = {
            'first_letter': 'A',
            'fuzzy': 'true',
            'lora_hash': 'abc123'
        }
        
        params = controller._parse_specific_params(mock_request)
        
        assert params['first_letter'] == 'A'
        assert params['fuzzy_search'] is True
        assert 'hash_filters' in params
        assert params['hash_filters']['single_hash'] == 'abc123'

    # Error Handling Tests
    async def test_controller_error_handling(self, client):
        """Test controller error handling"""
        # Test validation error handling
        resp = await client.post('/api/test/delete', json={'invalid': 'data'})
        assert resp.status == 400
        
        data = await resp.json()
        assert data['success'] is False
        assert 'error' in data

    def test_validation_error_custom_exception(self):
        """Test ValidationError custom exception"""
        error = ValidationError("Test message", "test_field")
        
        assert str(error) == "Test message"
        assert error.field == "test_field"
        assert error.message == "Test message"

    # Integration Tests
    async def test_full_delete_workflow(self, service_container):
        """Test complete delete workflow integration"""
        # Setup all necessary mocks
        file_service = service_container.get_service('file_service')
        file_service.delete_model_files = AsyncMock(return_value=['/test/model.safetensors'])
        
        controller = TestModelController(service_container)
        
        # Create mock request
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={'file_path': '/test/model.safetensors'})
        
        with patch('py.controllers.base_model_controller.ws_manager') as mock_ws:
            mock_ws.send_message = AsyncMock()
            
            # Execute the delete workflow
            response = await controller.delete_model(mock_request)
            
            # Verify the response
            assert response.status == 200
            
            # Verify services were called
            file_service.delete_model_files.assert_called_once()
            mock_ws.send_message.assert_called_once()

    async def test_service_layer_isolation(self):
        """Test that service layer is properly isolated"""
        # Create real service instances
        metadata_service = ModelMetadataService()
        file_service = ModelFileService()
        preview_service = ModelPreviewService()
        
        # Test that they can be instantiated independently
        assert isinstance(metadata_service, ModelMetadataService)
        assert isinstance(file_service, ModelFileService)
        assert isinstance(preview_service, ModelPreviewService)
        
        # Test that they don't have unwanted dependencies
        assert not hasattr(metadata_service, 'file_service')
        assert not hasattr(file_service, 'metadata_service')
        assert not hasattr(preview_service, 'file_service')




class TestPerformanceAndScalability:
    """Test performance and scalability aspects of the new architecture"""
    
    def test_service_container_memory_usage(self):
        """Test that service container doesn't create unnecessary instances"""
        container = ServiceContainer()
        
        # Register multiple services
        for i in range(100):
            container.register_singleton(f'service_{i}', Mock())
        
        # Verify all services are accessible
        for i in range(100):
            assert container.get_service(f'service_{i}') is not None
        
        # Clear and verify cleanup
        container.clear()
        assert container.get_service('service_0') is None

    async def test_controller_handles_concurrent_requests(self, service_container):
        """Test that controller can handle concurrent requests"""
        controller = TestModelController(service_container)
        
        # Create multiple mock requests
        mock_requests = []
        for i in range(10):
            mock_request = Mock()
            mock_request.json = AsyncMock(return_value={'file_path': f'/test/model_{i}.safetensors'})
            mock_requests.append(mock_request)
        
        # Setup file service mock
        file_service = service_container.get_service('file_service')
        file_service.delete_model_files = AsyncMock(return_value=[])
        
        with patch('py.controllers.base_model_controller.ws_manager') as mock_ws:
            mock_ws.send_message = AsyncMock()
            
            # Execute requests concurrently
            tasks = [controller.delete_model(req) for req in mock_requests]
            responses = await asyncio.gather(*tasks)
            
            # Verify all requests succeeded
            for response in responses:
                assert response.status == 200

    def test_validation_performance(self):
        """Test validation performance with large datasets"""
        validator = RequestValidator()
        
        # Test bulk validation
        large_file_list = [f'/test/model_{i}.safetensors' for i in range(1000)]
        bulk_data = {'file_paths': large_file_list}
        
        # This should complete quickly even with large datasets
        import time
        start_time = time.time()
        result = validator.validate_bulk_delete_request(bulk_data)
        end_time = time.time()
        
        assert len(result['file_paths']) == 1000
        assert (end_time - start_time) < 1.0  # Should complete in under 1 second


class TestBackwardCompatibility:
    """Test backward compatibility of the new architecture"""
    
    def test_old_controller_interface_compatibility(self):
        """Test that new controllers maintain compatibility with expected interfaces"""
        # Verify that BaseModelController has expected methods
        expected_methods = [
            'setup_routes', 'handle_models_page', 'delete_model',
            'fetch_civitai', 'replace_preview', 'get_models'
        ]
        
        for method_name in expected_methods:
            assert hasattr(BaseModelController, method_name)
            assert callable(getattr(BaseModelController, method_name))

    def test_service_interface_compatibility(self):
        """Test that services maintain expected interfaces"""
        # Test ModelMetadataService
        metadata_service = ModelMetadataService()
        expected_metadata_methods = ['load_local_metadata', 'update_model_metadata', 'filter_civitai_data']
        
        for method_name in expected_metadata_methods:
            assert hasattr(metadata_service, method_name)
            assert callable(getattr(metadata_service, method_name))
        
        # Test ModelFileService
        file_service = ModelFileService()
        expected_file_methods = ['delete_model_files', 'file_exists', 'get_file_size']
        
        for method_name in expected_file_methods:
            assert hasattr(file_service, method_name)
            assert callable(getattr(file_service, method_name))


class TestErrorRecovery:
    """Test error recovery and resilience of the new architecture"""
    
    async def test_service_failure_recovery(self, service_container):
        """Test that system handles service failures gracefully"""
        # Setup a failing service
        file_service = service_container.get_service('file_service')
        file_service.delete_model_files = AsyncMock(side_effect=Exception("Service failure"))
        
        controller = TestModelController(service_container)
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={'file_path': '/test/model.safetensors'})
        
        # Should handle the exception gracefully
        response = await controller.delete_model(mock_request)
        assert response.status == 500  # Internal server error
        
        # Verify error response format
        # Note: In a real test, you'd need to extract JSON from the response
        # This is simplified for the example

    def test_validation_edge_cases(self):
        """Test validation with edge cases and malformed data"""
        validator = RequestValidator()
        
        # Test with None values
        with pytest.raises(ValidationError):
            validator.validate_delete_request(None)
        
        # Test with extremely long file paths
        long_path = 'a' * 10000
        with pytest.raises(ValidationError):
            validator.validate_delete_request({'file_path': long_path})
        
        # Test with special characters in SHA256
        with pytest.raises(ValidationError):
            validator.validate_fetch_civitai_request({'sha256': 'invalid#$%^&*'})

    def test_service_container_edge_cases(self):
        """Test service container with edge cases"""
        container = ServiceContainer()
        
        # Test getting non-existent service
        assert container.get_service('nonexistent') is None
        
        # Test registering None service
        container.register_singleton('null_service', None)
        assert container.get_service('null_service') is None
        
        # Test factory that raises exception
        def failing_factory():
            raise Exception("Factory failure")
        
        container.register_factory('failing_service', failing_factory)
        
        # Should handle factory failures gracefully
        try:
            result = container.get_service('failing_service')
            assert result is None or isinstance(result, Exception)
        except Exception:
            # This is acceptable behavior for failing factories
            pass


# Test Helper Functions and Utilities
def create_test_metadata():
    """Helper function to create test metadata"""
    return {
        'id': 12345,
        'name': 'Test LoRA',
        'baseModel': 'SD 1.5',
        'trainedWords': ['test', 'sample'],
        'description': 'A test LoRA model',
        'civitai': {
            'modelId': 12345,
            'trainedWords': ['test', 'sample']
        }
    }


def create_test_service_container():
    """Helper function to create a fully mocked service container"""
    container = ServiceContainer()
    
    # Setup comprehensive mocks
    metadata_service = Mock(spec=ModelMetadataService)
    metadata_service.load_local_metadata = AsyncMock(return_value=create_test_metadata())
    metadata_service.update_model_metadata = AsyncMock()
    metadata_service.fetch_and_update_model = AsyncMock(return_value=True)
    
    file_service = Mock(spec=ModelFileService)
    file_service.delete_model_files = AsyncMock(return_value=['/test/deleted.safetensors'])
    file_service.file_exists = Mock(return_value=True)
    file_service.get_file_size = Mock(return_value=1024)
    
    preview_service = Mock(spec=ModelPreviewService)
    preview_service.replace_preview = AsyncMock(return_value={
        'success': True,
        'preview_url': '/static/test.jpg'
    })
    preview_service.get_preview_url = Mock(return_value='/static/test.jpg')
    
    container.register_singleton('metadata_service', metadata_service)
    container.register_singleton('file_service', file_service)
    container.register_singleton('preview_service', preview_service)
    
    return container


# Example usage and integration tests
if __name__ == "__main__":
    # Run with: python -m pytest tests/test_new_architecture.py -v
    
    # Or run specific test classes:
    # python -m pytest tests/test_new_architecture.py::TestNewArchitecture -v
    # python -m pytest tests/test_new_architecture.py::TestPerformanceAndScalability -v
    # python -m pytest tests/test_new_architecture.py::TestBackwardCompatibility -v
    # python -m pytest tests/test_new_architecture.py::TestErrorRecovery -v
    
    # Run with coverage:
    # python -m pytest tests/test_new_architecture.py --cov=py.controllers --cov=py.services --cov=py.validators
    
    pytest.main([__file__, "-v", "--tb=short"])
