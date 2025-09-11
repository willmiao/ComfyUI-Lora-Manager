# New Architecture Deployment Guide

## Quick Start

### 1. Enable the New Architecture

To start using the new controller-based architecture, modify your main application file:

```python
# In your main application setup (e.g., __init__.py or main route setup)

# OLD: Using the legacy route system
# from py.routes.lora_routes import LoraRoutes
# lora_routes = LoraRoutes()
# lora_routes.setup_routes(app)

# NEW: Using the new controller architecture
from py.routes.route_registry import setup_new_routes
setup_new_routes(app)
```

### 2. Verify the Migration

1. Start your ComfyUI server
2. Navigate to the LoRA management page
3. Check that all existing functionality works
4. Monitor logs for any errors

## Gradual Migration Strategy

### Phase 1: LoRA Controller (✅ COMPLETED)
- [x] Created `BaseModelController` and `LoraController`
- [x] Migrated core LoRA functionality
- [x] Implemented service layer separation
- [x] Added validation layer

### Phase 2: Other Model Types (TODO)
- [ ] Create `CheckpointController`
- [ ] Create `EmbeddingController`
- [ ] Migrate remaining model types

### Phase 3: Legacy Cleanup (TODO)
- [ ] Remove `BaseModelRoutes` class
- [ ] Remove `ModelRouteUtils` class
- [ ] Update all imports and references

## Configuration

### Service Container

The new architecture uses a service container for dependency injection. You can customize it:

```python
from py.services.service_container import ServiceContainer, get_default_container

# Use default container (recommended)
container = get_default_container()

# Or create custom container
custom_container = ServiceContainer()
custom_container.register_singleton('custom_service', MyCustomService())
```

### Environment-Specific Services

For different environments (development, testing, production):

```python
# development.py
from py.services.service_container import DefaultServiceContainer

class DevelopmentServiceContainer(DefaultServiceContainer):
    def _setup_default_services(self):
        super()._setup_default_services()
        # Override with development-specific services
        self.register_singleton('debug_service', DebugService())

# testing.py
class TestServiceContainer(DefaultServiceContainer):
    def _setup_default_services(self):
        super()._setup_default_services()
        # Override with mock services for testing
        self.register_singleton('metadata_service', MockMetadataService())
```

## Monitoring and Troubleshooting

### Logging

The new architecture includes comprehensive logging:

```python
import logging
logging.getLogger('py.controllers').setLevel(logging.DEBUG)
logging.getLogger('py.services').setLevel(logging.DEBUG)
logging.getLogger('py.validators').setLevel(logging.DEBUG)
```

### Health Checks

Add health check endpoints to verify the new architecture:

```python
async def health_check(request):
    """Health check for new architecture"""
    try:
        container = get_default_container()
        
        # Check core services
        metadata_service = container.get_metadata_service()
        file_service = container.get_file_service()
        preview_service = container.get_preview_service()
        
        return web.json_response({
            'status': 'healthy',
            'architecture': 'new',
            'services': {
                'metadata_service': metadata_service is not None,
                'file_service': file_service is not None,
                'preview_service': preview_service is not None
            }
        })
    except Exception as e:
        return web.json_response({
            'status': 'error',
            'error': str(e)
        }, status=500)

# Add to your routes
app.router.add_get('/api/health', health_check)
```

## Performance Considerations

### Service Caching

Services are automatically cached as singletons in the service container. No additional configuration needed.

### Memory Usage

The new architecture uses slightly more memory due to service instances, but provides better memory management through proper separation of concerns.

### Request Processing

Request processing is now faster due to:
- Dedicated validation layer (fail fast)
- Service reuse (no repeated instantiation)
- Cleaner error handling paths

## Rollback Procedure

If you need to rollback to the old architecture:

### 1. Immediate Rollback

```python
# Comment out new routes
# setup_new_routes(app)

# Restore old routes
from py.routes.lora_routes import LoraRoutes
lora_routes = LoraRoutes()
lora_routes.setup_routes(app)
```

### 2. Selective Rollback

You can rollback specific model types:

```python
# Use new architecture for some models
from py.controllers.lora_controller import LoraController
lora_controller = LoraController()
lora_controller.setup_routes(app)

# Use old architecture for others
from py.routes.checkpoint_routes import CheckpointRoutes
checkpoint_routes = CheckpointRoutes()
checkpoint_routes.setup_routes(app)
```

## Testing the New Architecture

### Manual Testing Checklist

- [ ] LoRA list page loads correctly
- [ ] LoRA search and filtering works
- [ ] Model deletion works
- [ ] CivitAI metadata fetching works
- [ ] Preview image replacement works
- [ ] All API endpoints return expected responses
- [ ] Error handling works correctly
- [ ] WebSocket notifications work

### Automated Testing

Run the included test suite:

```bash
# Run all tests
python -m pytest tests/test_new_architecture.py -v

# Run specific test categories
python -m pytest tests/test_new_architecture.py::TestNewArchitecture::test_service_container_injection -v
```

## Support and Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all new files are in the correct locations
2. **Service Not Found**: Check service container registration
3. **Validation Errors**: Review request validation logic
4. **Template Errors**: Verify template paths in controller configuration

### Debug Mode

Enable debug mode for detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Performance Monitoring

Monitor key metrics:
- Request response times
- Memory usage
- Error rates
- Service initialization times

## Future Enhancements

### Planned Features

1. **Async Service Loading**: Improve startup time with lazy loading
2. **Service Health Monitoring**: Real-time service status monitoring
3. **Request Metrics**: Built-in performance metrics collection
4. **Auto-Recovery**: Automatic service restart on failures

### Extension Points

The new architecture provides several extension points:

1. **Custom Services**: Add your own services to the container
2. **Custom Validators**: Extend validation logic
3. **Custom Controllers**: Create controllers for new model types
4. **Middleware**: Add request/response middleware

## Feedback and Contributions

- Report issues with the new architecture
- Suggest improvements
- Contribute new services or controllers
- Help with testing and validation

The new architecture is designed to be more maintainable, testable, and extensible while preserving all existing functionality.
