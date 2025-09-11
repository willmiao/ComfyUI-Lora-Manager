#!/usr/bin/env python3
"""
Simple standalone test to verify the new architecture components work
"""
import sys
import os
from pathlib import Path
from unittest.mock import Mock

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Mock ComfyUI dependencies before importing our modules
folder_paths = Mock()
folder_paths.get_directory = Mock(return_value="/fake/path")
folder_paths.get_folder_names = Mock(return_value=["loras", "checkpoints"])
sys.modules['folder_paths'] = folder_paths

nodes = Mock()
sys.modules['nodes'] = nodes

def test_validation_system():
    """Test the request validation system"""
    print("Testing validation system...")
    
    try:
        from py.validators.request_validator import RequestValidator, ValidationError
        
        validator = RequestValidator()
        
        # Test valid request
        valid_data = {'file_path': '/models/test.safetensors'}
        result = validator.validate_delete_request(valid_data)
        assert result['file_path'] == '/models/test.safetensors'
        print("✅ Valid request validation passed")
        
        # Test invalid request
        try:
            validator.validate_delete_request({})
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert e.field == 'file_path'
            print("✅ Invalid request validation passed")
        
        # Test pagination validation
        params = {'page': '1', 'page_size': '20'}
        result = validator.validate_pagination_params(params)
        assert result['page'] == 1
        assert result['page_size'] == 20
        print("✅ Pagination validation passed")
        
    except Exception as e:
        print(f"❌ Validation system test failed: {e}")
        return False
    
    return True


def test_service_container():
    """Test the service container system"""
    print("\nTesting service container...")
    
    try:
        from py.services.service_container import ServiceContainer
        
        container = ServiceContainer()
        
        # Test singleton registration
        test_service = object()
        container.register_singleton('test_service', test_service)
        
        retrieved = container.get_service('test_service')
        assert retrieved is test_service
        print("✅ Singleton registration passed")
        
        # Test factory registration
        def factory():
            return "factory_result"
        
        container.register_factory('factory_service', factory)
        result = container.get_service('factory_service')
        assert result == "factory_result"
        
        # Should return cached result
        result2 = container.get_service('factory_service')
        assert result2 is result
        print("✅ Factory registration passed")
        
        # Test non-existent service
        result = container.get_service('nonexistent')
        assert result is None
        print("✅ Non-existent service handling passed")
        
    except Exception as e:
        print(f"❌ Service container test failed: {e}")
        return False
    
    return True


def test_service_layer():
    """Test individual service components"""
    print("\nTesting service layer...")
    
    try:
        from py.services.model_metadata_service import ModelMetadataService
        from py.services.model_file_service import ModelFileService
        from py.services.model_preview_service import ModelPreviewService
        
        # Test metadata service
        metadata_service = ModelMetadataService()
        
        # Test filter function
        test_data = {
            'id': 123,
            'name': 'Test',
            'extra_field': 'should_be_removed'
        }
        filtered = metadata_service.filter_civitai_data(test_data, minimal=True)
        assert 'extra_field' not in filtered
        print("✅ Metadata service instantiation passed")
        
        # Test file service
        file_service = ModelFileService()
        
        # Test filename sanitization
        sanitized = file_service.sanitize_filename('test<>file')
        assert '<' not in sanitized and '>' not in sanitized
        print("✅ File service instantiation passed")
        
        # Test preview service
        preview_service = ModelPreviewService()
        
        # Test path checking (without actual files)
        result = preview_service.get_preview_path('/nonexistent/model.safetensors')
        assert result is None  # Should return None for non-existent files
        print("✅ Preview service instantiation passed")
        
    except Exception as e:
        print(f"❌ Service layer test failed: {e}")
        return False
    
    return True


def test_controller_structure():
    """Test controller base structure"""
    print("\nTesting controller structure...")
    
    try:
        from py.controllers.base_model_controller import BaseModelController
        from py.services.service_container import DefaultServiceContainer
        
        # Create a mock service
        class MockModelService:
            def __init__(self):
                self.model_type = 'test'
        
        # Create a test controller
        class TestController(BaseModelController):
            def setup_specific_routes(self, app, prefix):
                pass
            
            async def handle_models_page(self, request):
                pass
            
            def _parse_specific_params(self, request):
                return {}
        
        container = DefaultServiceContainer()
        controller = TestController(MockModelService(), 'test', container)
        
        assert controller.model_type == 'test'
        assert controller.service_container is container
        print("✅ Controller structure passed")
        
    except Exception as e:
        print(f"❌ Controller structure test failed: {e}")
        return False
    
    return True


def test_route_registry():
    """Test route registry system"""
    print("\nTesting route registry...")
    
    try:
        from py.routes.route_registry import RouteRegistry
        
        registry = RouteRegistry()
        assert registry.controllers == {}
        print("✅ Route registry instantiation passed")
        
    except Exception as e:
        print(f"❌ Route registry test failed: {e}")
        return False
    
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("New Architecture Component Tests")
    print("=" * 60)
    
    tests = [
        test_validation_system,
        test_service_container,
        test_service_layer,
        test_controller_structure,
        test_route_registry
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The new architecture is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
