"""
Example of how to use the new restructured architecture
"""
import asyncio
from aiohttp import web

from py.routes.route_registry import setup_new_routes
from py.services.service_container import get_default_container
from py.controllers.lora_controller import LoraController
from py.controllers.base_model_controller import BaseModelController


async def example_using_new_architecture():
    """Example demonstrating the new architecture usage"""
    
    # 1. Setup service container (optional - uses default if not specified)
    container = get_default_container()
    
    # 2. Setup web application with new routes
    app = web.Application()
    setup_new_routes(app)
    
    # 3. Example of using services directly
    metadata_service = container.get_metadata_service()
    file_service = container.get_file_service()
    preview_service = container.get_preview_service()
    
    # Example: Load metadata for a model
    metadata_path = "/path/to/model.metadata.json"
    metadata = await metadata_service.load_local_metadata(metadata_path)
    print(f"Loaded metadata: {metadata}")
    
    # Example: Check if a file exists
    model_path = "/path/to/model.safetensors"
    exists = file_service.file_exists(model_path)
    print(f"Model exists: {exists}")
    
    # Example: Get preview URL
    preview_url = preview_service.get_preview_url(model_path)
    print(f"Preview URL: {preview_url}")
    
    return app


async def example_custom_controller():
    """Example of creating a custom controller"""
    
    class CustomModelController(BaseModelController):
        def __init__(self, service_container=None):
            # Initialize with custom service and model type
            super().__init__(None, 'custom_model', service_container)
        
        async def initialize_services(self):
            """Initialize any custom services"""
            # Custom initialization logic
            pass
        
        def setup_specific_routes(self, app: web.Application, prefix: str):
            """Setup custom routes"""
            app.router.add_get(f'/api/{prefix}/custom-endpoint', self.custom_endpoint)
        
        async def handle_models_page(self, request: web.Request) -> web.Response:
            """Handle the main page"""
            template = self.template_env.get_template('custom_models.html')
            content = template.render(title="Custom Models")
            return web.Response(text=content, content_type='text/html')
        
        def _parse_specific_params(self, request: web.Request):
            """Parse custom parameters"""
            params = {}
            if 'custom_filter' in request.query:
                params['custom_filter'] = request.query['custom_filter']
            return params
        
        async def custom_endpoint(self, request: web.Request) -> web.Response:
            """Custom endpoint implementation"""
            try:
                # Use validation
                data = await request.json()
                # Custom validation logic here
                
                # Use services
                result = await self.file_service.get_file_size(data.get('file_path'))
                
                return web.json_response({
                    'success': True,
                    'file_size': result
                })
            except Exception as e:
                return self._handle_exception('custom_endpoint', e)
    
    # Usage
    container = get_default_container()
    custom_controller = CustomModelController(container)
    
    app = web.Application()
    custom_controller.setup_routes(app, 'custom')
    
    return app


async def example_service_usage():
    """Example of using individual services"""
    
    container = get_default_container()
    
    # Get metadata service
    metadata_service = container.get_metadata_service()
    
    # Example: Update metadata with CivitAI data
    local_metadata = {"name": "test_model"}
    civitai_data = {
        "id": 12345,
        "name": "Test Model",
        "baseModel": "SD 1.5",
        "trainedWords": ["test", "example"]
    }
    
    await metadata_service.update_model_metadata(
        "/path/to/metadata.json",
        local_metadata,
        civitai_data
    )
    
    # Get file service
    file_service = container.get_file_service()
    
    # Example: Delete model files
    deleted_files = await file_service.delete_model_files(
        "/models/loras/",
        "test_model"
    )
    print(f"Deleted files: {deleted_files}")
    
    # Get preview service
    preview_service = container.get_preview_service()
    
    # Example: Replace preview
    result = await preview_service.replace_preview(
        "/models/loras/test_model.safetensors",
        "data:image/jpeg;base64,/9j/4AAQSkZJRg...",  # Base64 image data
        "SFW"
    )
    print(f"Preview replacement result: {result}")


async def example_validation():
    """Example of using the validation system"""
    
    from py.validators.request_validator import RequestValidator, ValidationError
    
    # Example request data
    delete_request = {
        "file_path": "/models/loras/test_model.safetensors"
    }
    
    try:
        # Validate the request
        validated_data = RequestValidator.validate_delete_request(delete_request)
        print(f"Validated data: {validated_data}")
        
        # Use validated data safely
        file_path = validated_data['file_path']
        
    except ValidationError as e:
        print(f"Validation error: {e.message} (field: {e.field})")
    
    # Example with invalid data
    invalid_request = {"file_path": ""}  # Empty path
    
    try:
        RequestValidator.validate_delete_request(invalid_request)
    except ValidationError as e:
        print(f"Expected validation error: {e.message}")


if __name__ == "__main__":
    # Run examples
    asyncio.run(example_using_new_architecture())
    asyncio.run(example_custom_controller())
    asyncio.run(example_service_usage())
    asyncio.run(example_validation())
