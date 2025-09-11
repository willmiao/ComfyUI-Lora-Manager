# Test Suite for New Architecture

This directory contains comprehensive tests for the new architecture implementation of the ComfyUI LoRA Manager.

## Overview

The test suite is designed to validate the new controller-service-validator architecture and ensure it maintains backward compatibility while providing improved maintainability and testability.

## Test Structure

```
tests/
├── conftest.py                 # Pytest configuration and fixtures
├── test_new_architecture.py    # Integration tests for the overall architecture
├── test_services.py           # Unit tests for service layer components
├── test_validators.py         # Unit tests for validation system
├── run_tests.py              # Test runner script
└── README.md                 # This file
```

## Test Categories

### 1. Integration Tests (`test_new_architecture.py`)
- **TestNewArchitecture**: Main integration tests
- **TestPerformanceAndScalability**: Performance and scalability tests
- **TestBackwardCompatibility**: Backward compatibility validation
- **TestErrorRecovery**: Error handling and resilience tests

### 2. Service Layer Tests (`test_services.py`)
- **TestModelMetadataService**: Metadata service functionality
- **TestModelFileService**: File operations service
- **TestModelPreviewService**: Preview image service
- **TestServiceContainer**: Dependency injection container

### 3. Validation Tests (`test_validators.py`)
- **TestRequestValidator**: Request validation logic
- **TestValidationError**: Custom exception behavior
- **TestValidationEdgeCases**: Edge cases and stress testing

## Quick Start

### Install Dependencies
```bash
python tests/run_tests.py --install-deps
```

### Create Test Configuration
```bash
python tests/run_tests.py --create-config
```

### Run All Tests
```bash
python tests/run_tests.py
```

### Run with Coverage
```bash
python tests/run_tests.py --coverage
```

## Running Tests

### Using the Test Runner

The `run_tests.py` script provides a convenient interface for running tests:

```bash
# Run all tests
python tests/run_tests.py

# Run specific test file
python tests/run_tests.py --file test_services.py

# Run specific test method
python tests/run_tests.py --file test_services.py --test TestModelMetadataService::test_load_local_metadata_success

# Run with coverage reporting
python tests/run_tests.py --coverage

# Run tests in parallel
python tests/run_tests.py --parallel 4

# Run only unit tests
python tests/run_tests.py --type unit

# Verbose output
python tests/run_tests.py -v
```

### Using pytest Directly

You can also run tests directly with pytest:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_services.py -v

# Run with coverage
python -m pytest tests/ --cov=py.controllers --cov=py.services --cov=py.validators

# Run specific test categories
python -m pytest tests/ -m unit
python -m pytest tests/ -m integration
python -m pytest tests/ -m performance
```

## Test Fixtures

The test suite includes several useful fixtures defined in `conftest.py`:

- `mock_config`: Mock configuration object
- `sample_lora_data`: Sample LoRA model data
- `sample_metadata`: Sample metadata structure
- `temp_model_files`: Temporary model files for testing
- `mock_websocket_manager`: Mock WebSocket manager
- `mock_civitai_response`: Mock CivitAI API response

## What's Being Tested

### Architecture Components

1. **Service Container**
   - Dependency injection
   - Singleton behavior
   - Factory pattern
   - Service lifecycle management

2. **Controllers**
   - HTTP request/response handling
   - Route registration
   - Error handling
   - Parameter validation

3. **Services**
   - Business logic isolation
   - File operations
   - Metadata management
   - Preview image handling

4. **Validators**
   - Request validation
   - Data sanitization
   - Error reporting
   - Edge case handling

### Functionality Testing

1. **Model Management**
   - Model deletion
   - Metadata fetching
   - Preview replacement
   - File operations

2. **CivitAI Integration**
   - API communication
   - Data parsing
   - Error handling
   - Rate limiting

3. **WebSocket Communication**
   - Event broadcasting
   - Client notification
   - Connection management

4. **File System Operations**
   - File deletion
   - Directory management
   - Path validation
   - Permission handling

## Test Data

### Sample Data Structures

The tests use realistic sample data that mirrors the actual application data:

```python
sample_lora_data = {
    'file_path': '/models/loras/test_lora.safetensors',
    'name': 'Test LoRA',
    'hash': 'a' * 64,
    'size': 1024 * 1024,
    'civitai': {
        'id': 12345,
        'name': 'Test LoRA',
        'trainedWords': ['test', 'anime'],
        'baseModel': 'SD 1.5'
    }
}
```

### Mock Services

The test suite includes comprehensive mocks for external dependencies:

- File system operations
- HTTP requests to CivitAI
- WebSocket connections
- Database operations

## Coverage Goals

The test suite aims for high coverage across all components:

- **Controllers**: >90% line coverage
- **Services**: >95% line coverage  
- **Validators**: >98% line coverage
- **Overall**: >90% line coverage

## Performance Testing

Performance tests validate:

- Response times under load
- Memory usage with large datasets
- Concurrent request handling
- Resource cleanup

## Error Scenarios

Error testing covers:

- Network failures
- File system errors
- Invalid input data
- Service unavailability
- Permission issues

## Continuous Integration

The test suite is designed to work with CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    python tests/run_tests.py --coverage
    
- name: Upload coverage
  uses: codecov/codecov-action@v1
  with:
    file: ./coverage.xml
```

## Debugging Tests

### Running Individual Tests

```bash
# Run a specific test with debugging
python -m pytest tests/test_services.py::TestModelMetadataService::test_load_local_metadata_success -v -s

# Run with pdb on failure
python -m pytest tests/test_services.py --pdb
```

### Test Output

Tests provide detailed output for debugging:

- Request/response data
- Service call traces
- Error messages with context
- Performance metrics

## Contributing to Tests

### Adding New Tests

1. Follow the existing naming convention
2. Use appropriate fixtures from `conftest.py`
3. Include both positive and negative test cases
4. Add performance tests for new functionality
5. Update this README if adding new test categories

### Test Guidelines

1. **Isolation**: Each test should be independent
2. **Clarity**: Test names should describe what's being tested
3. **Coverage**: Aim for comprehensive coverage of edge cases
4. **Performance**: Tests should run quickly
5. **Reliability**: Tests should not be flaky

### Mock Guidelines

1. Mock external dependencies (file system, network)
2. Use realistic test data
3. Verify mock interactions
4. Keep mocks simple and focused

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure project root is in Python path
2. **Missing Dependencies**: Run `--install-deps` 
3. **Path Issues**: Use absolute paths in test configuration
4. **Async Issues**: Ensure proper async/await usage

### Environment Setup

```bash
# Ensure you're in the project root
cd /path/to/ComfyUI-Lora-Manager

# Install test dependencies
python tests/run_tests.py --install-deps

# Create test configuration
python tests/run_tests.py --create-config

# Run tests
python tests/run_tests.py
```

## Future Enhancements

Planned improvements to the test suite:

1. **Property-based testing** with Hypothesis
2. **Load testing** with realistic data volumes
3. **Integration testing** with real CivitAI API
4. **Cross-platform testing** (Windows, Linux, macOS)
5. **Browser automation** for UI testing
