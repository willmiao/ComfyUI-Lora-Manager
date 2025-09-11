"""
Performance monitoring for the new architecture
"""
import time
import logging
from typing import Dict, Optional
from functools import wraps
from aiohttp import web

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor performance metrics for the new architecture"""
    
    def __init__(self):
        """Initialize performance monitor"""
        self.metrics = {}
        self.request_times = []
        self.error_counts = {}
        self.service_init_times = {}
    
    def record_request_time(self, endpoint: str, duration: float):
        """Record request processing time
        
        Args:
            endpoint: The endpoint that was called
            duration: Time taken in seconds
        """
        if endpoint not in self.metrics:
            self.metrics[endpoint] = {
                'total_requests': 0,
                'total_time': 0.0,
                'avg_time': 0.0,
                'min_time': float('inf'),
                'max_time': 0.0
            }
        
        metrics = self.metrics[endpoint]
        metrics['total_requests'] += 1
        metrics['total_time'] += duration
        metrics['avg_time'] = metrics['total_time'] / metrics['total_requests']
        metrics['min_time'] = min(metrics['min_time'], duration)
        metrics['max_time'] = max(metrics['max_time'], duration)
        
        # Keep last 100 request times for analysis
        self.request_times.append({
            'endpoint': endpoint,
            'duration': duration,
            'timestamp': time.time()
        })
        if len(self.request_times) > 100:
            self.request_times.pop(0)
    
    def record_error(self, endpoint: str, error_type: str):
        """Record an error occurrence
        
        Args:
            endpoint: The endpoint where error occurred
            error_type: Type of error
        """
        key = f"{endpoint}:{error_type}"
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
    
    def record_service_init_time(self, service_name: str, duration: float):
        """Record service initialization time
        
        Args:
            service_name: Name of the service
            duration: Initialization time in seconds
        """
        self.service_init_times[service_name] = duration
    
    def get_metrics(self) -> Dict:
        """Get all collected metrics
        
        Returns:
            Dict: All performance metrics
        """
        return {
            'request_metrics': self.metrics,
            'error_counts': self.error_counts,
            'service_init_times': self.service_init_times,
            'recent_requests': self.request_times[-10:] if self.request_times else []
        }
    
    def get_health_summary(self) -> Dict:
        """Get health summary based on metrics
        
        Returns:
            Dict: Health summary
        """
        total_requests = sum(m['total_requests'] for m in self.metrics.values())
        total_errors = sum(self.error_counts.values())
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        avg_response_time = 0
        if self.request_times:
            recent_times = [r['duration'] for r in self.request_times[-20:]]
            avg_response_time = sum(recent_times) / len(recent_times)
        
        return {
            'total_requests': total_requests,
            'total_errors': total_errors,
            'error_rate_percent': error_rate,
            'avg_response_time_ms': avg_response_time * 1000,
            'health_status': 'healthy' if error_rate < 5 else 'degraded' if error_rate < 15 else 'unhealthy'
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


def monitor_performance(endpoint_name: Optional[str] = None):
    """Decorator to monitor performance of request handlers
    
    Args:
        endpoint_name: Optional custom endpoint name, defaults to function name
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            name = endpoint_name or func.__name__
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                performance_monitor.record_request_time(name, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                performance_monitor.record_request_time(name, duration)
                performance_monitor.record_error(name, type(e).__name__)
                raise
        
        return wrapper
    return decorator


def monitor_service_init(service_name: str):
    """Decorator to monitor service initialization time
    
    Args:
        service_name: Name of the service being initialized
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            performance_monitor.record_service_init_time(service_name, duration)
            logger.info(f"Service {service_name} initialized in {duration:.3f}s")
            return result
        return wrapper
    return decorator


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance
    
    Returns:
        PerformanceMonitor: The global monitor
    """
    return performance_monitor
