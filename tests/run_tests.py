#!/usr/bin/env python3
"""
Test runner script for the new architecture tests
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_command(cmd, description):
    """Run a command and print the result"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.stdout:
        print("STDOUT:")
        print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    print(f"Exit code: {result.returncode}")
    return result.returncode == 0


def main():
    """Main test runner function"""
    parser = argparse.ArgumentParser(description='Run tests for the new architecture')
    parser.add_argument('--type', choices=['all', 'unit', 'integration', 'performance'], 
                       default='all', help='Type of tests to run')
    parser.add_argument('--coverage', action='store_true', 
                       help='Run tests with coverage reporting')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose output')
    parser.add_argument('--file', help='Run specific test file')
    parser.add_argument('--test', help='Run specific test (e.g., TestClass::test_method)')
    parser.add_argument('--parallel', '-n', type=int, 
                       help='Run tests in parallel with N workers')
    
    args = parser.parse_args()
    
    # Change to project directory
    os.chdir(project_root)
    
    # Base pytest command
    cmd = ['python', '-m', 'pytest']
    
    # Add verbosity
    if args.verbose:
        cmd.append('-v')
    else:
        cmd.append('-q')
    
    # Add parallel execution
    if args.parallel:
        cmd.extend(['-n', str(args.parallel)])
    
    # Add coverage
    if args.coverage:
        cmd.extend([
            '--cov=py.controllers',
            '--cov=py.services', 
            '--cov=py.validators',
            '--cov=py.routes',
            '--cov-report=html',
            '--cov-report=term-missing'
        ])
    
    success = True
    
    if args.file:
        # Run specific file
        test_file = f"tests/{args.file}" if not args.file.startswith('tests/') else args.file
        cmd.append(test_file)
        
        if args.test:
            cmd[-1] += f"::{args.test}"
        
        success = run_command(cmd, f"Running {test_file}")
    
    elif args.test:
        # Run specific test
        cmd.append(f"tests/{args.test}")
        success = run_command(cmd, f"Running specific test: {args.test}")
    
    elif args.type == 'all':
        # Run all tests
        test_files = [
            'tests/test_new_architecture.py',
            'tests/test_services.py', 
            'tests/test_validators.py'
        ]
        
        for test_file in test_files:
            if os.path.exists(test_file):
                current_cmd = cmd + [test_file]
                if not run_command(current_cmd, f"Running {test_file}"):
                    success = False
    
    elif args.type == 'unit':
        # Run unit tests
        cmd.extend(['-m', 'unit', 'tests/'])
        success = run_command(cmd, "Running unit tests")
    
    elif args.type == 'integration':
        # Run integration tests
        cmd.extend(['-m', 'integration', 'tests/'])
        success = run_command(cmd, "Running integration tests")
    
    elif args.type == 'performance':
        # Run performance tests
        cmd.extend(['-m', 'performance', 'tests/'])
        success = run_command(cmd, "Running performance tests")
    
    # Print summary
    print(f"\n{'='*60}")
    if success:
        print("✅ All tests completed successfully!")
    else:
        print("❌ Some tests failed!")
    print('='*60)
    
    # Generate coverage report if requested
    if args.coverage and success:
        print("\n📊 Coverage report generated:")
        print(f"   - HTML: {project_root}/htmlcov/index.html")
        print(f"   - Terminal output above")
    
    return 0 if success else 1


def install_dependencies():
    """Install test dependencies"""
    dependencies = [
        'pytest',
        'pytest-asyncio',
        'pytest-cov',
        'pytest-xdist',  # for parallel execution
        'aiohttp',
        'aioresponses'   # for mocking aiohttp requests
    ]
    
    print("Installing test dependencies...")
    for dep in dependencies:
        cmd = [sys.executable, '-m', 'pip', 'install', dep]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {dep}")
        else:
            print(f"❌ {dep}: {result.stderr}")


def create_test_config():
    """Create pytest.ini configuration file"""
    config_content = """[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --strict-markers
    --tb=short
    --disable-warnings
markers =
    unit: Unit tests
    integration: Integration tests
    performance: Performance tests
    slow: Slow running tests
asyncio_mode = auto
"""
    
    config_path = project_root / "pytest.ini"
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    print(f"✅ Created pytest configuration: {config_path}")


def show_help():
    """Show usage examples"""
    examples = """
Examples:
    # Run all tests
    python run_tests.py
    
    # Run with coverage
    python run_tests.py --coverage
    
    # Run specific test file
    python run_tests.py --file test_services.py
    
    # Run specific test method
    python run_tests.py --file test_services.py --test TestModelMetadataService::test_load_local_metadata_success
    
    # Run only unit tests
    python run_tests.py --type unit
    
    # Run tests in parallel
    python run_tests.py --parallel 4
    
    # Verbose output
    python run_tests.py -v
    
    # Install dependencies
    python run_tests.py --install-deps
    
    # Create test configuration
    python run_tests.py --create-config
"""
    print(examples)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if '--install-deps' in sys.argv:
            install_dependencies()
        elif '--create-config' in sys.argv:
            create_test_config()
        elif '--help-examples' in sys.argv:
            show_help()
        else:
            sys.exit(main())
    else:
        sys.exit(main())
