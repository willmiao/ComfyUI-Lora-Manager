#!/usr/bin/env python3
"""
Simple verification script for the new architecture (no external dependencies)
"""
import sys
from pathlib import Path

def verify_new_architecture_files():
    """Verify that all new architecture files exist"""
    print("🔄 Verifying new architecture files...")
    
    # Define required files
    required_files = [
        # Controllers
        'py/controllers/base_model_controller.py',
        'py/controllers/lora_controller.py',
        'py/controllers/checkpoint_controller.py',
        'py/controllers/embedding_controller.py',
        'py/controllers/health_controller.py',
        
        # Services
        'py/services/service_container.py',
        'py/services/lora_service.py',
        'py/services/checkpoint_service.py',
        
        # Routes
        'py/routes/route_registry.py',
        
        # Utils
        'py/utils/performance_monitor.py',
        'py/config/architecture_config.py',
        
        # Validators
        'py/validators/request_validator.py'
    ]
    
    project_root = Path(__file__).parent
    missing_files = []
    
    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} - MISSING")
            missing_files.append(file_path)
    
    return len(missing_files) == 0, missing_files

def verify_main_integration():
    """Verify that main integration is updated"""
    print("\n🔧 Checking main integration...")
    
    project_root = Path(__file__).parent
    lora_manager_path = project_root / 'py' / 'lora_manager.py'
    
    if not lora_manager_path.exists():
        print("  ❌ lora_manager.py not found")
        return False
    
    with open(lora_manager_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if new routes are enabled
    if 'setup_new_routes(app)' in content:
        print("  ✅ New route system enabled")
        new_routes_enabled = True
    else:
        print("  ⚠️  New route system not enabled")
        new_routes_enabled = False
    
    # Check if old routes are commented out
    if '# ModelServiceFactory.setup_all_routes(app)' in content:
        print("  ✅ Old route system commented out")
        old_routes_disabled = True
    else:
        print("  ⚠️  Old route system not commented out")
        old_routes_disabled = False
    
    return new_routes_enabled and old_routes_disabled

def check_architecture_features():
    """Check if architecture features are properly defined"""
    print("\n🏗️  Checking architecture features...")
    
    project_root = Path(__file__).parent
    
    # Check BaseModelController
    base_controller_path = project_root / 'py' / 'controllers' / 'base_model_controller.py'
    if base_controller_path.exists():
        with open(base_controller_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        features = [
            ('Abstract base class', 'class BaseModelController(ABC):'),
            ('Route setup method', 'def setup_routes(self, app: web.Application, prefix: str):'),
            ('Error handling', 'def _handle_validation_error(self, error: ValidationError)'),
            ('Performance monitoring', '@monitor_performance'),
            ('Service injection', 'service_container')
        ]
        
        for feature_name, search_text in features:
            if search_text in content:
                print(f"  ✅ {feature_name}")
            else:
                print(f"  ❌ {feature_name} - MISSING")
    
    # Check RouteRegistry
    route_registry_path = project_root / 'py' / 'routes' / 'route_registry.py'
    if route_registry_path.exists():
        with open(route_registry_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'def setup_new_routes(app: web.Application):' in content:
            print("  ✅ Route registry setup function")
        else:
            print("  ❌ Route registry setup function - MISSING")

def main():
    """Main verification function"""
    print("ComfyUI LoRA Manager - New Architecture File Verification")
    print("=" * 55)
    
    # Check files
    files_ok, missing_files = verify_new_architecture_files()
    
    # Check integration
    integration_ok = verify_main_integration()
    
    # Check features
    check_architecture_features()
    
    print("\n" + "=" * 55)
    
    if files_ok and integration_ok:
        print("✅ New architecture verification completed successfully!")
        print("\n📋 Architecture Status:")
        print("  • All required files are present")
        print("  • Main integration is properly configured")
        print("  • New route system is enabled")
        print("  • Old route system is disabled")
        
        print("\n🌐 Available Endpoints (when ComfyUI starts):")
        print("  • /loras - LoRA management page")
        print("  • /checkpoints - Checkpoint management page") 
        print("  • /embeddings - Embedding management page")
        print("  • /api/health - Health check")
        print("  • /api/health/architecture - Architecture info")
        print("  • /api/health/performance - Performance metrics")
        
        print("\n🔄 Rollback Instructions:")
        print("  1. Edit py/lora_manager.py")
        print("  2. Comment out: setup_new_routes(app)")
        print("  3. Uncomment: ModelServiceFactory.setup_all_routes(app)")
        
        print("\n🚀 Ready to start ComfyUI with the new architecture!")
        
    else:
        print("❌ Verification found issues:")
        if missing_files:
            print(f"  • Missing files: {', '.join(missing_files)}")
        if not integration_ok:
            print("  • Main integration not properly configured")
        
        print("\n🔧 Please check the implementation and try again.")

if __name__ == "__main__":
    main()
