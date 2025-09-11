import os
import logging
from abc import ABC, abstractmethod
from aiohttp import web
from typing import Dict, Any, Optional

import jinja2

from ..validators.request_validator import RequestValidator, ValidationError
from ..services.service_container import get_default_container
from ..services.websocket_manager import ws_manager
from ..services.settings_manager import settings
from ..services.server_i18n import server_i18n
from ..utils.performance_monitor import monitor_performance
from ..config import config

logger = logging.getLogger(__name__)


class BaseModelController(ABC):
    """Base controller for all model types - handles HTTP requests/responses only"""
    
    def __init__(self, model_service, model_type: str, service_container=None):
        """Initialize the controller
        
        Args:
            model_service: Model service instance (LoraService, CheckpointService, etc.)
            model_type: Type of model (lora, checkpoint, etc.)
            service_container: Optional service container for dependency injection
        """
        self.model_service = model_service
        self.model_type = model_type
        self.template_name = f"{model_type}s.html"
        
        # Get service container
        if service_container is None:
            service_container = get_default_container()
        self.service_container = service_container
        
        # Initialize supporting services from container
        self.metadata_service = service_container.get_metadata_service()
        self.file_service = service_container.get_file_service()
        self.preview_service = service_container.get_preview_service()
        self.validator = RequestValidator()
        
        # Initialize template environment
        self.template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(config.templates_path),
            autoescape=True
        )
    
    def setup_routes(self, app: web.Application, prefix: str):
        """Setup common routes for the model type
        
        Args:
            app: aiohttp application
            prefix: URL prefix (e.g., 'loras', 'checkpoints')
        """
        # Main page route
        app.router.add_get(f'/{prefix}', self.handle_models_page)
        
        # Common model management routes
        app.router.add_get(f'/api/{prefix}/list', self.get_models)
        app.router.add_post(f'/api/{prefix}/delete', self.delete_model)
        app.router.add_post(f'/api/{prefix}/exclude', self.exclude_model)
        app.router.add_post(f'/api/{prefix}/fetch-civitai', self.fetch_civitai)
        app.router.add_post(f'/api/{prefix}/relink-civitai', self.relink_civitai)
        app.router.add_post(f'/api/{prefix}/replace-preview', self.replace_preview)
        app.router.add_post(f'/api/{prefix}/save-metadata', self.save_metadata)
        app.router.add_post(f'/api/{prefix}/add-tags', self.add_tags)
        app.router.add_post(f'/api/{prefix}/rename', self.rename_model)
        app.router.add_post(f'/api/{prefix}/bulk-delete', self.bulk_delete_models)
        app.router.add_post(f'/api/{prefix}/verify-duplicates', self.verify_duplicates)
        app.router.add_post(f'/api/{prefix}/move_model', self.move_model)
        app.router.add_post(f'/api/{prefix}/move_models_bulk', self.move_models_bulk)
        app.router.add_get(f'/api/{prefix}/auto-organize', self.auto_organize_models)
        app.router.add_post(f'/api/{prefix}/auto-organize', self.auto_organize_models)
        app.router.add_get(f'/api/{prefix}/auto-organize-progress', self.get_auto_organize_progress)
        
        # Common query routes
        app.router.add_get(f'/api/{prefix}/top-tags', self.get_top_tags)
        app.router.add_get(f'/api/{prefix}/base-models', self.get_base_models)
        app.router.add_get(f'/api/{prefix}/scan', self.scan_models)
        app.router.add_get(f'/api/{prefix}/roots', self.get_model_roots)
        app.router.add_get(f'/api/{prefix}/folders', self.get_folders)
        app.router.add_get(f'/api/{prefix}/folder-tree', self.get_folder_tree)
        app.router.add_get(f'/api/{prefix}/unified-folder-tree', self.get_unified_folder_tree)
        app.router.add_get(f'/api/{prefix}/find-duplicates', self.find_duplicate_models)
        
        # Model info routes
        app.router.add_get(f'/api/{prefix}/notes', self.get_model_notes)
        app.router.add_get(f'/api/{prefix}/preview-url', self.get_model_preview_url)
        app.router.add_get(f'/api/{prefix}/civitai-url', self.get_model_civitai_url)
        app.router.add_get(f'/api/{prefix}/metadata', self.get_model_metadata)
        app.router.add_get(f'/api/{prefix}/description', self.get_model_description)
        app.router.add_get(f'/api/{prefix}/relative-paths', self.get_relative_paths)
        
        # Download management routes
        app.router.add_post(f'/api/{prefix}/download', self.download_model)
        app.router.add_get(f'/api/{prefix}/download', self.download_model_get)
        app.router.add_get(f'/api/{prefix}/cancel-download', self.cancel_download_get)
        app.router.add_get(f'/api/{prefix}/download-progress', self.get_download_progress)
        app.router.add_get(f'/api/{prefix}/fetch-all-civitai', self.fetch_all_civitai)
        app.router.add_get(f'/api/{prefix}/civitai/versions/{{model_id}}', self.get_civitai_versions)
        
        # Setup model-specific routes
        self.setup_specific_routes(app, prefix)
    
    @abstractmethod
    def setup_specific_routes(self, app: web.Application, prefix: str):
        """Setup model-specific routes - to be implemented by subclasses"""
        pass
    
    @abstractmethod
    async def handle_models_page(self, request: web.Request) -> web.Response:
        """Handle the main models page - to be implemented by subclasses"""
        pass
    
    def _handle_validation_error(self, error: ValidationError) -> web.Response:
        """Handle validation errors consistently
        
        Args:
            error: Validation error to handle
            
        Returns:
            web.Response: Error response
        """
        logger.warning(f"Validation error: {error.message}")
        return web.json_response({
            'success': False,
            'error': error.message,
            'field': error.field
        }, status=400)
    
    def _handle_exception(self, operation: str, error: Exception) -> web.Response:
        """Handle exceptions consistently
        
        Args:
            operation: Name of the operation that failed
            error: Exception that occurred
            
        Returns:
            web.Response: Error response
        """
        logger.error(f"Error in {operation}: {error}", exc_info=True)
        return web.json_response({
            'success': False,
            'error': str(error)
        }, status=500)
    
    # Common route handlers
    @monitor_performance('get_models')
    async def get_models(self, request: web.Request) -> web.Response:
        """Get paginated model data"""
        try:
            # Parse and validate common parameters
            common_params = self._parse_common_params(request)
            validated_params = self.validator.validate_pagination_params(common_params)
            
            # Parse model-specific parameters
            specific_params = self._parse_specific_params(request)
            
            # Merge parameters
            all_params = {**validated_params, **specific_params}
            
            # Get data from service
            result = await self.model_service.get_paginated_data(**all_params)
            
            return web.json_response(result)
            
        except ValidationError as e:
            return self._handle_validation_error(e)
        except Exception as e:
            return self._handle_exception('get_models', e)
    
    def _parse_common_params(self, request: web.Request) -> Dict[str, Any]:
        """Parse common query parameters
        
        Args:
            request: HTTP request object
            
        Returns:
            Dict: Parsed parameters
        """
        params = {}
        
        # Pagination
        params['page'] = request.query.get('page', '1')
        params['page_size'] = request.query.get('page_size', '20')
        
        # Sorting and filtering
        params['sort_by'] = request.query.get('sort_by', 'name')
        params['folder'] = request.query.get('folder')
        params['search'] = request.query.get('search')
        params['fuzzy_search'] = request.query.get('fuzzy_search', 'false')
        params['favorites_only'] = request.query.get('favorites_only', 'false')
        
        # Filter lists
        if 'base_models' in request.query:
            params['base_models'] = request.query['base_models'].split(',')
        if 'tags' in request.query:
            params['tags'] = request.query['tags'].split(',')
        
        return params
    
    def _parse_specific_params(self, request: web.Request) -> Dict[str, Any]:
        """Parse model-specific parameters - to be overridden by subclasses
        
        Args:
            request: HTTP request object
            
        Returns:
            Dict: Parsed model-specific parameters
        """
        return {}
    
    @monitor_performance('delete_model')
    async def delete_model(self, request: web.Request) -> web.Response:
        """Delete a model file"""
        try:
            data = await request.json()
            validated_data = self.validator.validate_delete_request(data)
            
            file_path = validated_data['file_path']
            
            # Get model info before deletion
            model_info = await self.model_service.get_model_info_by_path(file_path)
            if not model_info:
                return web.json_response({
                    'success': False,
                    'error': 'Model not found'
                }, status=404)
            
            # Delete the model files
            target_dir = os.path.dirname(file_path)
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            deleted_files = await self.file_service.delete_model_files(target_dir, file_name)
            
            # Update cache/scanner
            await self.model_service.remove_from_cache(file_path)
            
            # Notify via websocket
            await ws_manager.send_message({
                'type': 'model_deleted',
                'model_type': self.model_type,
                'file_path': file_path,
                'deleted_files': deleted_files
            })
            
            return web.json_response({
                'success': True,
                'message': f'Model deleted successfully',
                'deleted_files': deleted_files
            })
            
        except ValidationError as e:
            return self._handle_validation_error(e)
        except Exception as e:
            return self._handle_exception('delete_model', e)
    
    @monitor_performance('fetch_civitai')
    async def fetch_civitai(self, request: web.Request) -> web.Response:
        """Fetch CivitAI metadata for a model"""
        try:
            data = await request.json()
            validated_data = self.validator.validate_fetch_civitai_request(data)
            
            sha256 = validated_data['sha256']
            file_path = validated_data.get('file_path')
            
            # Get model data from cache
            model_data = await self.model_service.get_model_by_hash(sha256)
            if not model_data:
                return web.json_response({
                    'success': False,
                    'error': 'Model not found in cache'
                }, status=404)
            
            # Use file_path from cache if not provided
            if not file_path:
                file_path = model_data.get('file_path')
            
            if not file_path:
                return web.json_response({
                    'success': False,
                    'error': 'File path not found'
                }, status=400)
            
            # Fetch and update metadata
            success = await self.metadata_service.fetch_and_update_model(
                sha256, file_path, model_data, self.model_service.update_cache_entry
            )
            
            if success:
                return web.json_response({
                    'success': True,
                    'message': 'CivitAI metadata fetched successfully'
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to fetch CivitAI metadata'
                }, status=500)
            
        except ValidationError as e:
            return self._handle_validation_error(e)
        except Exception as e:
            return self._handle_exception('fetch_civitai', e)
    
    async def replace_preview(self, request: web.Request) -> web.Response:
        """Replace model preview image"""
        try:
            data = await request.json()
            validated_data = self.validator.validate_replace_preview_request(data)
            
            result = await self.preview_service.replace_preview(
                validated_data['file_path'],
                validated_data['preview_data'],
                validated_data.get('nsfw_level')
            )
            
            if result['success']:
                # Update cache if needed
                await self.model_service.update_preview_cache(
                    validated_data['file_path'], 
                    result.get('preview_url')
                )
                
                # Notify via websocket
                await ws_manager.send_message({
                    'type': 'preview_updated',
                    'model_type': self.model_type,
                    'file_path': validated_data['file_path'],
                    'preview_url': result.get('preview_url')
                })
            
            return web.json_response(result)
            
        except ValidationError as e:
            return self._handle_validation_error(e)
        except Exception as e:
            return self._handle_exception('replace_preview', e)
    
    async def exclude_model(self, request: web.Request) -> web.Response:
        """Exclude a model from scanning"""
        try:
            data = await request.json()
            validated_data = self.validator.validate_exclude_request(data)
            
            file_path = validated_data['file_path']
            
            # Add to exclusion list
            success = await self.model_service.exclude_model(file_path)
            
            if success:
                return web.json_response({
                    'success': True,
                    'message': 'Model excluded successfully'
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to exclude model'
                }, status=500)
            
        except ValidationError as e:
            return self._handle_validation_error(e)
        except Exception as e:
            return self._handle_exception('exclude_model', e)
    
    # Additional route handlers would follow the same pattern...
    # For brevity, I'll implement a few more key ones
    
    async def get_top_tags(self, request: web.Request) -> web.Response:
        """Get top tags for the model type"""
        try:
            limit = int(request.query.get('limit', 20))
            tags = await self.model_service.get_top_tags(limit)
            
            return web.json_response({
                'success': True,
                'tags': tags
            })
            
        except (ValueError, TypeError):
            return web.json_response({
                'success': False,
                'error': 'Invalid limit parameter'
            }, status=400)
        except Exception as e:
            return self._handle_exception('get_top_tags', e)
    
    async def scan_models(self, request: web.Request) -> web.Response:
        """Trigger model scanning"""
        try:
            force_refresh = request.query.get('force_refresh', 'false').lower() == 'true'
            rebuild_cache = request.query.get('rebuild_cache', 'false').lower() == 'true'
            
            await self.model_service.scan_models(force_refresh, rebuild_cache)
            
            return web.json_response({
                'success': True,
                'message': 'Model scan initiated'
            })
            
        except Exception as e:
            return self._handle_exception('scan_models', e)
    
    # Placeholder implementations for other route handlers
    async def relink_civitai(self, request: web.Request) -> web.Response:
        """Relink CivitAI metadata"""
        try:
            data = await request.json()
            # Delegate to metadata service
            result = await self.metadata_service.relink_civitai_metadata(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('relink_civitai', e)
    
    async def save_metadata(self, request: web.Request) -> web.Response:
        """Save metadata updates"""
        try:
            data = await request.json()
            # Delegate to metadata service
            result = await self.metadata_service.save_metadata(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('save_metadata', e)
    
    async def add_tags(self, request: web.Request) -> web.Response:
        """Add tags to model metadata"""
        try:
            data = await request.json()
            # Delegate to metadata service
            result = await self.metadata_service.add_tags(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('add_tags', e)
    
    async def rename_model(self, request: web.Request) -> web.Response:
        """Rename a model file"""
        try:
            data = await request.json()
            # Delegate to file service
            result = await self.file_service.rename_model(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('rename_model', e)
    
    async def bulk_delete_models(self, request: web.Request) -> web.Response:
        """Bulk delete models"""
        try:
            data = await request.json()
            # Delegate to file service
            result = await self.file_service.bulk_delete_models(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('bulk_delete_models', e)
    
    async def verify_duplicates(self, request: web.Request) -> web.Response:
        """Verify duplicate models"""
        try:
            data = await request.json()
            # Delegate to model service
            result = await self.model_service.verify_duplicates(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('verify_duplicates', e)
    
    async def move_model(self, request: web.Request) -> web.Response:
        """Move a model file"""
        try:
            data = await request.json()
            # Delegate to file service
            result = await self.file_service.move_model(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('move_model', e)
    
    async def move_models_bulk(self, request: web.Request) -> web.Response:
        """Bulk move models"""
        try:
            data = await request.json()
            # Delegate to file service
            result = await self.file_service.move_models_bulk(data)
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('move_models_bulk', e)
    
    async def auto_organize_models(self, request: web.Request) -> web.Response:
        """Auto-organize models"""
        try:
            # Delegate to file service
            result = await self.file_service.auto_organize_models()
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('auto_organize_models', e)
    
    async def get_auto_organize_progress(self, request: web.Request) -> web.Response:
        """Get auto-organize progress"""
        try:
            # Delegate to file service
            result = await self.file_service.get_auto_organize_progress()
            return web.json_response(result)
        except Exception as e:
            return self._handle_exception('get_auto_organize_progress', e)
        
    async def get_base_models(self, request: web.Request) -> web.Response:
        """Get base models"""
        try:
            limit = int(request.query.get('limit', '20'))
            if limit < 1 or limit > 100:
                limit = 20
            
            base_models = await self.model_service.get_base_models(limit)
            
            return web.json_response({
                'success': True,
                'base_models': base_models
            })
        except Exception as e:
            return self._handle_exception('get_base_models', e)
    
    async def get_model_roots(self, request: web.Request) -> web.Response:
        """Get model roots"""
        try:
            roots = self.model_service.get_model_roots()
            return web.json_response({
                "success": True,
                "roots": roots
            })
        except Exception as e:
            return self._handle_exception('get_model_roots', e)
    
    async def get_folders(self, request: web.Request) -> web.Response:
        """Get folders"""
        try:
            cache = await self.model_service.scanner.get_cached_data()
            return web.json_response({
                'folders': cache.folders
            })
        except Exception as e:
            return self._handle_exception('get_folders', e)
    
    async def get_folder_tree(self, request: web.Request) -> web.Response:
        """Get folder tree"""
        try:
            model_root = request.query.get('model_root')
            if not model_root:
                return web.json_response({
                    'success': False,
                    'error': 'model_root parameter is required'
                }, status=400)
            
            folder_tree = await self.model_service.get_folder_tree(model_root)
            return web.json_response({
                'success': True,
                'tree': folder_tree
            })
        except Exception as e:
            return self._handle_exception('get_folder_tree', e)
    
    async def get_unified_folder_tree(self, request: web.Request) -> web.Response:
        """Get unified folder tree"""
        try:
            unified_tree = await self.model_service.get_unified_folder_tree()
            return web.json_response({
                'success': True,
                'tree': unified_tree
            })
        except Exception as e:
            return self._handle_exception('get_unified_folder_tree', e)
    
    async def find_duplicate_models(self, request: web.Request) -> web.Response:
        """Find duplicate models"""
        try:
            # Get duplicate hashes from service
            duplicates = self.model_service.find_duplicate_hashes()
            
            # Format the response
            result = []
            cache = await self.model_service.scanner.get_cached_data()
            
            for sha256, paths in duplicates.items():
                group = {
                    "hash": sha256,
                    "models": []
                }
                # Find matching models for each path
                for path in paths:
                    model = next((m for m in cache.raw_data if m['file_path'] == path), None)
                    if model:
                        group["models"].append(await self.model_service.format_response(model))
                
                # Add the primary model too
                primary_path = self.model_service.get_path_by_hash(sha256)
                if primary_path and primary_path not in paths:
                    primary_model = next((m for m in cache.raw_data if m['file_path'] == primary_path), None)
                    if primary_model:
                        group["models"].insert(0, await self.model_service.format_response(primary_model))
                
                if len(group["models"]) > 1:  # Only include if we found multiple models
                    result.append(group)
                
            return web.json_response({
                "success": True,
                "duplicates": result,
                "count": len(result)
            })
        except Exception as e:
            return self._handle_exception('find_duplicate_models', e)
    
    async def get_model_notes(self, request: web.Request) -> web.Response:
        """Get model notes"""
        try:
            model_name = request.query.get('name')
            if not model_name:
                return web.Response(text=f'{self.model_type.capitalize()} file name is required', status=400)
            
            notes = await self.model_service.get_model_notes(model_name)
            if notes is not None:
                return web.json_response({
                    'success': True,
                    'notes': notes
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': f'{self.model_type.capitalize()} not found in cache'
                }, status=404)
        except Exception as e:
            return self._handle_exception('get_model_notes', e)
    
    async def get_model_preview_url(self, request: web.Request) -> web.Response:
        """Get model preview URL"""
        try:
            model_name = request.query.get('name')
            if not model_name:
                return web.Response(text=f'{self.model_type.capitalize()} file name is required', status=400)
            
            preview_url = await self.model_service.get_model_preview_url(model_name)
            if preview_url:
                return web.json_response({
                    'success': True,
                    'preview_url': preview_url
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': f'No preview URL found for the specified {self.model_type}'
                }, status=404)
        except Exception as e:
            return self._handle_exception('get_model_preview_url', e)
    
    async def get_model_civitai_url(self, request: web.Request) -> web.Response:
        """Get model CivitAI URL"""
        try:
            model_name = request.query.get('name')
            if not model_name:
                return web.Response(text=f'{self.model_type.capitalize()} file name is required', status=400)
            
            result = await self.model_service.get_model_civitai_url(model_name)
            if result['civitai_url']:
                return web.json_response({
                    'success': True,
                    **result
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': f'No Civitai data found for the specified {self.model_type}'
                }, status=404)
        except Exception as e:
            return self._handle_exception('get_model_civitai_url', e)
    
    async def get_model_metadata(self, request: web.Request) -> web.Response:
        """Get model metadata"""
        try:
            file_path = request.query.get('file_path')
            if not file_path:
                return web.Response(text='File path is required', status=400)
            
            metadata = await self.model_service.get_model_metadata(file_path)
            if metadata is not None:
                return web.json_response({
                    'success': True,
                    'metadata': metadata
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': f'{self.model_type.capitalize()} not found or no CivitAI metadata available'
                }, status=404)
        except Exception as e:
            return self._handle_exception('get_model_metadata', e)
    
    async def get_model_description(self, request: web.Request) -> web.Response:
        """Get model description"""
        try:
            file_path = request.query.get('file_path')
            if not file_path:
                return web.Response(text='File path is required', status=400)
            
            description = await self.model_service.get_model_description(file_path)
            if description is not None:
                return web.json_response({
                    'success': True,
                    'description': description
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': f'{self.model_type.capitalize()} not found or no description available'
                }, status=404)
        except Exception as e:
            return self._handle_exception('get_model_description', e)
    
    async def get_relative_paths(self, request: web.Request) -> web.Response:
        """Get relative paths"""
        try:
            search = request.query.get('search', '').strip()
            limit = min(int(request.query.get('limit', '15')), 50)  # Max 50 items
            
            matching_paths = await self.model_service.search_relative_paths(search, limit)
            
            return web.json_response({
                'success': True,
                'relative_paths': matching_paths
            })
        except Exception as e:
            return self._handle_exception('get_relative_paths', e)
    
    async def download_model(self, request: web.Request) -> web.Response:
        """Download model"""
        try:
            # Delegate to ModelRouteUtils for now, can be refactored later
            from ..utils.routes_common import ModelRouteUtils
            return await ModelRouteUtils.handle_download_model(request)
        except Exception as e:
            return self._handle_exception('download_model', e)
    
    async def download_model_get(self, request: web.Request) -> web.Response:
        """Download model (GET)"""
        try:
            import asyncio
            # Extract query parameters
            model_id = request.query.get('model_id')
            if not model_id:
                return web.Response(
                    status=400, 
                    text="Missing required parameter: Please provide 'model_id'"
                )
            
            # Get optional parameters
            model_version_id = request.query.get('model_version_id')
            download_id = request.query.get('download_id')
            use_default_paths = request.query.get('use_default_paths', 'false').lower() == 'true'
            
            # Create a data dictionary that mimics what would be received from a POST request
            data = {
                'model_id': model_id
            }
            
            # Add optional parameters only if they are provided
            if model_version_id:
                data['model_version_id'] = model_version_id
                
            if download_id:
                data['download_id'] = download_id
                
            data['use_default_paths'] = use_default_paths
            
            # Create a mock request object with the data
            future = asyncio.get_event_loop().create_future()
            future.set_result(data)
            
            mock_request = type('MockRequest', (), {
                'json': lambda self=None: future
            })()
            
            # Call the existing download handler
            from ..utils.routes_common import ModelRouteUtils
            return await ModelRouteUtils.handle_download_model(mock_request)
            
        except Exception as e:
            return self._handle_exception('download_model_get', e)
    
    async def cancel_download_get(self, request: web.Request) -> web.Response:
        """Cancel download (GET)"""
        try:
            download_id = request.query.get('download_id')
            if not download_id:
                return web.json_response({
                    'success': False,
                    'error': 'Download ID is required'
                }, status=400)
            
            # Create a mock request with match_info for compatibility
            mock_request = type('MockRequest', (), {
                'match_info': {'download_id': download_id}
            })()
            
            from ..utils.routes_common import ModelRouteUtils
            return await ModelRouteUtils.handle_cancel_download(mock_request)
        except Exception as e:
            return self._handle_exception('cancel_download_get', e)
    
    async def get_download_progress(self, request: web.Request) -> web.Response:
        """Get download progress"""
        try:
            # Get download_id from URL path
            download_id = request.match_info.get('download_id')
            if not download_id:
                return web.json_response({
                    'success': False,
                    'error': 'Download ID is required'
                }, status=400)
            
            progress_data = ws_manager.get_download_progress(download_id)
            
            if progress_data is None:
                return web.json_response({
                    'success': False,
                    'error': 'Download ID not found'
                }, status=404)
            
            return web.json_response({
                'success': True,
                'progress': progress_data.get('progress', 0)
            })
        except Exception as e:
            return self._handle_exception('get_download_progress', e)
    
    async def fetch_all_civitai(self, request: web.Request) -> web.Response:
        """Fetch all CivitAI data"""
        try:
            cache = await self.model_service.scanner.get_cached_data()
            total = len(cache.raw_data)
            processed = 0
            success = 0
            needs_resort = False
            
            # Prepare models to process, only those without CivitAI data or missing tags, description, or creator
            enable_metadata_archive_db = settings.get('enable_metadata_archive_db', False)
            to_process = [
                model for model in cache.raw_data
                if (
                    model.get('sha256')
                    and (
                        not model.get('civitai')
                        or not model['civitai'].get('id')
                        # or not model.get('tags') # Skipping tag cause it could be empty legitimately
                        or not model.get('modelDescription')
                        or not (model.get('civitai') and model['civitai'].get('creator'))
                    )
                    and (
                        (enable_metadata_archive_db)
                        or (not enable_metadata_archive_db and model.get('from_civitai') is True)
                    )
                )
            ]
            total_to_process = len(to_process)
            
            # Send initial progress
            await ws_manager.broadcast({
                'status': 'started',
                'total': total_to_process,
                'processed': 0,
                'success': 0
            })
            
            # Process each model
            for model in to_process:
                try:
                    original_name = model.get('model_name')
                    if await self.metadata_service.fetch_and_update_model(
                        sha256=model['sha256'],
                        file_path=model['file_path'],
                        model_data=model,
                        update_cache_func=self.model_service.scanner.update_single_model_cache
                    ):
                        success += 1
                        if original_name != model.get('model_name'):
                            needs_resort = True
                    
                    processed += 1
                    
                    # Send progress update
                    await ws_manager.broadcast({
                        'status': 'processing',
                        'total': total_to_process,
                        'processed': processed,
                        'success': success,
                        'current_name': model.get('model_name', 'Unknown')
                    })
                    
                except Exception as e:
                    logger.error(f"Error fetching CivitAI data for {model['file_path']}: {e}")
            
            if needs_resort:
                await cache.resort()
            
            # Send completion message
            await ws_manager.broadcast({
                'status': 'completed',
                'total': total_to_process,
                'processed': processed,
                'success': success
            })
                    
            return web.json_response({
                "success": True,
                "message": f"Successfully updated {success} of {processed} processed {self.model_type}s (total: {total})"
            })
            
        except Exception as e:
            # Send error message
            await ws_manager.broadcast({
                'status': 'error',
                'error': str(e)
            })
            return self._handle_exception('fetch_all_civitai', e)
    
    async def get_civitai_versions(self, request: web.Request) -> web.Response:
        """Get CivitAI versions"""
        # This will be implemented by subclasses as they need CivitAI client access
        return web.json_response({
            "error": "Not implemented in base class"
        }, status=501)
