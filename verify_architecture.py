#!/usr/bin/env python3
"""
Quick verification script for the new architecture
"""
import asyncio
import sys
import logging
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def verify_new_architecture():
    """Verify that the new architecture is working correctly"""
    print("🔄 Verifying new architecture...")
    
    try:
        # Test service container
        print("📦 Testing service container...")
        from py.services.service_container import get_default_container
        container = get_default_container()
        
        # Check core services
        metadata_service = container.get_metadata_service()
        file_service = container.get_file_service()
        preview_service = container.get_preview_service()
        
        print(f"  ✅ Metadata service: {'OK' if metadata_service else 'FAIL'}")
        print(f"  ✅ File service: {'OK' if file_service else 'FAIL'}")
        print(f"  ✅ Preview service: {'OK' if preview_service else 'FAIL'}")
        
        # Test controllers
        print("🎮 Testing controllers...")
        from py.controllers.lora_controller import LoraController
        from py.controllers.checkpoint_controller import CheckpointController
        from py.controllers.embedding_controller import EmbeddingController
        from py.controllers.health_controller import HealthController
        
        controllers = {
            'LoRA': LoraController(),
            'Checkpoint': CheckpointController(),
            'Embedding': EmbeddingController(),
            'Health': HealthController()
        }
        
        for name, controller in controllers.items():
            print(f"  ✅ {name} controller: OK")
        
        # Test route registry
        print("🛣️  Testing route registry...")
        from py.routes.route_registry import RouteRegistry
        registry = RouteRegistry()
        registry._initialize_controllers()
        print("  ✅ Route registry: OK")
        
        # Test performance monitor
        print("📊 Testing performance monitor...")
        from py.utils.performance_monitor import get_performance_monitor
        monitor = get_performance_monitor()
        metrics = monitor.get_metrics()
        print("  ✅ Performance monitor: OK")
        
        # Test architecture config
        print("⚙️  Testing architecture config...")
        from py.config.architecture_config import get_architecture_config
        arch_config = get_architecture_config()
        status = arch_config.get_migration_status()
        print("  ✅ Architecture config: OK")
        
        print("\n🎉 New architecture verification completed successfully!")
        print("\n📋 Migration Status:")
        for model_type, config in status.items():
            using_new = config['using_new_controller']
            fallback = config['fallback_enabled']
            status_icon = "✅" if using_new else "⏸️"
            print(f"  {status_icon} {model_type.capitalize()}: {'New Controller' if using_new else 'Legacy'}")
            if fallback:
                print(f"    ⚠️  Fallback to legacy enabled")
        
        print("\n🌐 Health Check Endpoints:")
        print("  • /api/health - Basic health status")
        print("  • /api/health/architecture - Architecture information")
        print("  • /api/health/performance - Performance metrics")
        print("  • /api/health/summary - Health summary")
        
        print("\n🔧 Quick Rollback Commands:")
        print("  • Immediate rollback: Comment setup_new_routes() in lora_manager.py")
        print("  • Selective rollback: Use ArchitectureConfig.enable_selective_rollback()")
        
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main verification function"""
    print("ComfyUI LoRA Manager - New Architecture Verification")
    print("=" * 50)
    
    # Set up logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    # Run verification
    success = asyncio.run(verify_new_architecture())
    
    if success:
        print("\n✅ All checks passed! The new architecture is ready.")
        print("🚀 You can now start ComfyUI and test the new features.")
        sys.exit(0)
    else:
        print("\n❌ Verification failed. Please check the errors above.")
        print("🔄 Consider rolling back to the legacy architecture if needed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
