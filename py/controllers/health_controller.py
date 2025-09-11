"""
Health check controller for the new architecture
"""
import logging
from aiohttp import web

from ..services.service_container import get_default_container
from ..utils.performance_monitor import get_performance_monitor

logger = logging.getLogger(__name__)


class HealthController:
    """Health check controller for monitoring new architecture"""
    
    def __init__(self):
        """Initialize health controller"""
        self.container = get_default_container()
    
    def setup_routes(self, app: web.Application):
        """Setup health check routes"""
        app.router.add_get('/api/health', self.health_check)
        app.router.add_get('/api/health/architecture', self.architecture_info)
        app.router.add_get('/api/health/performance', self.performance_metrics)
        app.router.add_get('/api/health/summary', self.health_summary)
    
    async def health_check(self, request: web.Request) -> web.Response:
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
            logger.error(f"Health check failed: {e}", exc_info=True)
            return web.json_response({
                'status': 'error',
                'error': str(e)
            }, status=500)
    
    async def architecture_info(self, request: web.Request) -> web.Response:
        """Get architecture information"""
        try:
            return web.json_response({
                'architecture': 'new',
                'version': '2.0',
                'features': [
                    'controller_based_routing',
                    'service_container_injection',
                    'request_validation',
                    'separation_of_concerns'
                ],
                'migration_status': {
                    'lora_controller': 'completed',
                    'checkpoint_controller': 'completed',
                    'embedding_controller': 'completed'
                }
            })
        except Exception as e:
            logger.error(f"Architecture info failed: {e}", exc_info=True)
            return web.json_response({
                'status': 'error',
                'error': str(e)
            }, status=500)
    
    async def performance_metrics(self, request: web.Request) -> web.Response:
        """Get performance metrics"""
        try:
            monitor = get_performance_monitor()
            metrics = monitor.get_metrics()
            return web.json_response({
                'status': 'success',
                'metrics': metrics
            })
        except Exception as e:
            logger.error(f"Performance metrics failed: {e}", exc_info=True)
            return web.json_response({
                'status': 'error',
                'error': str(e)
            }, status=500)
    
    async def health_summary(self, request: web.Request) -> web.Response:
        """Get health summary with performance data"""
        try:
            monitor = get_performance_monitor()
            health_summary = monitor.get_health_summary()
            container = get_default_container()
            
            return web.json_response({
                'status': 'success',
                'architecture': 'new',
                'health': health_summary,
                'services_status': {
                    'metadata_service': container.get_metadata_service() is not None,
                    'file_service': container.get_file_service() is not None,
                    'preview_service': container.get_preview_service() is not None
                }
            })
        except Exception as e:
            logger.error(f"Health summary failed: {e}", exc_info=True)
            return web.json_response({
                'status': 'error',
                'error': str(e)
            }, status=500)
