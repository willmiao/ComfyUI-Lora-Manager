# Code Restructure Migration Guide

## Overview

This document describes the code restructure implementation based on the suggestions in `restructure.md`. The restructure follows industry best practices for clean architecture and separation of concerns.

## New Architecture

### Layer Separation

```
Request → Controller → Service → Repository → Data Source
             ↑            ↑           ↑
    HTTP handling    Business logic   Data access
```

### Directory Structure

```
py/
├── controllers/              # HTTP request/response handling
│   ├── base_model_controller.py    # Base controller with common functionality
│   └── lora_controller.py          # LoRA-specific controller
├── services/                 # Business logic services
│   ├── model_metadata_service.py   # Metadata operations
│   ├── model_file_service.py       # File operations
│   ├── model_preview_service.py    # Preview image operations
│   └── service_container.py        # Dependency injection container
├── validators/               # Request validation
│   └── request_validator.py        # Validation logic
└── routes/                   # Route registration
    └── route_registry.py           # New route registration system
```

## Changes Made

### 1. Service Layer Refactoring

**Before**: Monolithic `ModelRouteUtils` class with static methods
```python
# Old approach
result = await ModelRouteUtils.handle_delete_model(request, scanner)
```

**After**: Dedicated service classes with clear responsibilities
```python
# New approach
metadata_service = ModelMetadataService()
file_service = ModelFileService()
preview_service = ModelPreviewService()

# Each service handles its specific domain
await metadata_service.load_local_metadata(path)
await file_service.delete_model_files(dir, name)
await preview_service.replace_preview(path, data)
```

### 2. Controller Layer

**Before**: `BaseModelRoutes` mixed business logic with HTTP handling
```python
# Old approach - business logic in route handler
async def delete_model(self, request):
    data = await request.json()
    # Validation, file deletion, cache updates all mixed together
```

**After**: Clean separation with dedicated controllers
```python
# New approach - controller only handles HTTP concerns
async def delete_model(self, request):
    try:
        data = await request.json()
        validated_data = self.validator.validate_delete_request(data)
        
        # Delegate to service layer
        result = await self.file_service.delete_model_files(...)
        return web.json_response(result)
    except ValidationError as e:
        return self._handle_validation_error(e)
```

### 3. Validation Layer

**Before**: Validation scattered throughout route handlers
```python
# Old approach - validation mixed with business logic
if not data.get('file_path'):
    return web.Response(text='Model path is required', status=400)
```

**After**: Centralized validation with clear error handling
```python
# New approach - dedicated validator
class RequestValidator:
    @staticmethod
    def validate_delete_request(data: Dict[str, Any]) -> Dict[str, Any]:
        if not data.get('file_path'):
            raise ValidationError('Model path is required', 'file_path')
        return validated_data
```

### 4. Dependency Injection

**Before**: Manual service instantiation throughout the code
```python
# Old approach - tight coupling
scanner = LoraScanner()
metadata_service = MetadataService()
```

**After**: Service container with dependency injection
```python
# New approach - loose coupling
container = get_default_container()
scanner = await container.get_lora_scanner()
metadata_service = container.get_metadata_service()
```

## Migration Path

### For Existing Code

1. **Immediate**: Use `route_registry.py` to register the new LoRA controller
   ```python
   from py.routes.route_registry import setup_new_routes
   setup_new_routes(app)
   ```

2. **Gradual**: Migrate other model types (Checkpoints, Embeddings) to use the new controller pattern

3. **Eventually**: Remove old `BaseModelRoutes` and `ModelRouteUtils` once all routes are migrated

### For New Features

1. Use the new controller base class: `BaseModelController`
2. Create dedicated service classes in the `services/` directory
3. Add validation logic to `RequestValidator`
4. Register services in the `ServiceContainer`

## Benefits

### 1. Improved Testability
- Services can be easily mocked and tested in isolation
- Clear separation of concerns makes unit testing straightforward

### 2. Better Maintainability
- Each class has a single responsibility
- Changes to business logic don't affect HTTP handling
- Easier to locate and modify specific functionality

### 3. Enhanced Flexibility
- Services can be easily swapped or extended
- Dependency injection allows for different implementations
- Better support for configuration and environment-specific behavior

### 4. Reduced Code Duplication
- Common functionality is centralized in base classes
- Shared services eliminate repeated code
- Consistent error handling across all endpoints

## Usage Examples

### Creating a New Controller

```python
class MyModelController(BaseModelController):
    def __init__(self, service_container=None):
        super().__init__(my_service, 'my_model', service_container)
    
    def setup_specific_routes(self, app, prefix):
        app.router.add_get(f'/api/{prefix}/custom', self.custom_endpoint)
    
    async def handle_models_page(self, request):
        # Implement page rendering
        pass
    
    def _parse_specific_params(self, request):
        # Parse model-specific parameters
        return {}
```

### Using Services

```python
# Get services from container
container = get_default_container()
metadata_service = container.get_metadata_service()
file_service = container.get_file_service()

# Use services
metadata = await metadata_service.load_local_metadata(path)
deleted_files = await file_service.delete_model_files(dir, name)
```

### Validation

```python
# Validate request data
try:
    validated_data = RequestValidator.validate_delete_request(data)
    # Use validated_data safely
except ValidationError as e:
    return web.json_response({
        'error': e.message,
        'field': e.field
    }, status=400)
```

## Next Steps

1. **Complete LoRA migration**: Ensure all LoRA endpoints work with the new controller
2. **Create Checkpoint and Embedding controllers**: Apply the same pattern
3. **Remove legacy code**: Once migration is complete, remove old classes
4. **Add tests**: Create comprehensive tests for the new architecture
5. **Documentation**: Update API documentation to reflect the new structure

## Rollback Plan

If issues arise during migration:

1. **Switch back to old routes**: Comment out `setup_new_routes()` and use the original route setup
2. **Gradual rollback**: Move specific endpoints back to the old system as needed
3. **Preserve data**: The new architecture doesn't change data structures, so rollback is safe

The new architecture is designed to coexist with the old system during the transition period.
