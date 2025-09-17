import logging
import os
import sys
import threading
import asyncio
import subprocess
from server import PromptServer # type: ignore
from aiohttp import web
from ..services.settings_manager import settings
from ..utils.usage_stats import UsageStats
from ..utils.lora_metadata import extract_trained_words
from ..config import config
from ..utils.constants import SUPPORTED_MEDIA_EXTENSIONS, NODE_TYPES, DEFAULT_NODE_COLOR
from ..services.service_registry import ServiceRegistry
from ..services.metadata_service import get_metadata_archive_manager, update_metadata_providers, get_metadata_provider
from ..services.websocket_manager import ws_manager
from ..services.downloader import get_downloader
logger = logging.getLogger(__name__)

standalone_mode = 'nodes' not in sys.modules

# Node registry for tracking active workflow nodes
class NodeRegistry:
    """Thread-safe registry for tracking Lora nodes in active workflows"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._nodes = {}  # node_id -> node_info
        self._registry_updated = threading.Event()
    
    def register_nodes(self, nodes):
        """Register multiple nodes at once, replacing existing registry"""
        with self._lock:
            # Clear existing registry
            self._nodes.clear()
            
            # Register all new nodes
            for node in nodes:
                node_id = node['node_id']
                node_type = node.get('type', '')
                
                # Convert node type name to integer
                type_id = NODE_TYPES.get(node_type, 0)  # 0 for unknown types
                
                # Handle null bgcolor with default color
                bgcolor = node.get('bgcolor')
                if bgcolor is None:
                    bgcolor = DEFAULT_NODE_COLOR
                
                self._nodes[node_id] = {
                    'id': node_id,
                    'bgcolor': bgcolor,
                    'title': node.get('title'),
                    'type': type_id,
                    'type_name': node_type
                }
            
            logger.debug(f"Registered {len(nodes)} nodes in registry")
            
            # Signal that registry has been updated
            self._registry_updated.set()
    
    def get_registry(self):
        """Get current registry information"""
        with self._lock:
            return {
                'nodes': dict(self._nodes),  # Return a copy
                'node_count': len(self._nodes)
            }
    
    def clear_registry(self):
        """Clear the entire registry"""
        with self._lock:
            self._nodes.clear()
            logger.info("Node registry cleared")
    
    def wait_for_update(self, timeout=1.0):
        """Wait for registry update with timeout"""
        self._registry_updated.clear()
        return self._registry_updated.wait(timeout)

# Global registry instance
node_registry = NodeRegistry()

class MiscRoutes:
    """Miscellaneous routes for various utility functions"""
    
    @staticmethod
    def setup_routes(app):
        """Register miscellaneous routes"""
        app.router.add_get('/api/lm/settings', MiscRoutes.get_settings)
        app.router.add_post('/api/lm/settings', MiscRoutes.update_settings)

        app.router.add_get('/api/health-check', lambda request: web.json_response({'status': 'ok'}))

        app.router.add_post('/api/open-file-location', MiscRoutes.open_file_location)

        # Usage stats routes
        app.router.add_post('/api/update-usage-stats', MiscRoutes.update_usage_stats)
        app.router.add_get('/api/get-usage-stats', MiscRoutes.get_usage_stats)
        
        # Lora code update endpoint
        app.router.add_post('/api/update-lora-code', MiscRoutes.update_lora_code)

        # Add new route for getting trained words
        app.router.add_get('/api/trained-words', MiscRoutes.get_trained_words)
        
        # Add new route for getting model example files
        app.router.add_get('/api/model-example-files', MiscRoutes.get_model_example_files)
        
        # Node registry endpoints
        app.router.add_post('/api/register-nodes', MiscRoutes.register_nodes)
        app.router.add_get('/api/get-registry', MiscRoutes.get_registry)
        
        # Add new route for checking if a model exists in the library
        app.router.add_get('/api/check-model-exists', MiscRoutes.check_model_exists)
        
        # Add routes for metadata archive database management
        app.router.add_post('/api/download-metadata-archive', MiscRoutes.download_metadata_archive)
        app.router.add_post('/api/remove-metadata-archive', MiscRoutes.remove_metadata_archive)
        app.router.add_get('/api/metadata-archive-status', MiscRoutes.get_metadata_archive_status)
        
        # Add route for checking model versions in library
        app.router.add_get('/api/model-versions-status', MiscRoutes.get_model_versions_status)

    @staticmethod
    async def get_settings(request):
        """Get application settings that should be synced to frontend"""
        try:
            # Define keys that should be synced from backend to frontend
            sync_keys = [
                'civitai_api_key',
                'default_lora_root', 
                'default_checkpoint_root',
                'default_embedding_root',
                'base_model_path_mappings',
                'download_path_templates',
                'enable_metadata_archive_db',
                'language',
                'proxy_enabled',
                'proxy_type',
                'proxy_host',
                'proxy_port',
                'proxy_username',
                'proxy_password',
                'example_images_path',
                'optimizeExampleImages',
                'autoDownloadExampleImages'
            ]
            
            # Build response with only the keys that should be synced
            response_data = {}
            for key in sync_keys:
                value = settings.get(key)
                if value is not None:
                    response_data[key] = value
            
            return web.json_response({
                'success': True,
                'settings': response_data
            })
            
        except Exception as e:
            logger.error(f"Error getting settings: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def update_settings(request):
        """Update application settings"""
        try:
            data = await request.json()
            proxy_keys = {'proxy_enabled', 'proxy_host', 'proxy_port', 'proxy_username', 'proxy_password', 'proxy_type'}
            proxy_changed = False
            
            # Validate and update settings
            for key, value in data.items():
                if value == settings.get(key):
                    # No change, skip
                    continue
                # Special handling for example_images_path - verify path exists
                if key == 'example_images_path' and value:
                    if not os.path.exists(value):
                        return web.json_response({
                            'success': False,
                            'error': f"Path does not exist: {value}"
                        })
                    
                    # Path changed - server restart required for new path to take effect
                    old_path = settings.get('example_images_path')
                    if old_path != value:
                        logger.info(f"Example images path changed to {value} - server restart required")

                # Handle deletion for proxy credentials
                if value == '__DELETE__' and key in ('proxy_username', 'proxy_password'):
                    settings.delete(key)
                else:
                    # Save to settings
                    settings.set(key, value)
            
                if key == 'enable_metadata_archive_db':
                    await update_metadata_providers()
                
                if key in proxy_keys:
                    proxy_changed = True

            if proxy_changed:
                downloader = await get_downloader()
                await downloader.refresh_session()

            return web.json_response({'success': True})
        except Exception as e:
            logger.error(f"Error updating settings: {e}", exc_info=True)
            return web.Response(status=500, text=str(e))
    
    @staticmethod
    async def update_usage_stats(request):
        """
        Update usage statistics based on a prompt_id
        
        Expects a JSON body with:
        {
            "prompt_id": "string"
        }
        """
        try:
            # Parse the request body
            data = await request.json()
            prompt_id = data.get('prompt_id')
            
            if not prompt_id:
                return web.json_response({
                    'success': False,
                    'error': 'Missing prompt_id'
                }, status=400)
            
            # Call the UsageStats to process this prompt_id synchronously
            usage_stats = UsageStats()
            await usage_stats.process_execution(prompt_id)
            
            return web.json_response({
                'success': True
            })
            
        except Exception as e:
            logger.error(f"Failed to update usage stats: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @staticmethod
    async def get_usage_stats(request):
        """Get current usage statistics"""
        try:
            usage_stats = UsageStats()
            stats = await usage_stats.get_stats()
            
            # Add version information to help clients handle format changes
            stats_response = {
                'success': True,
                'data': stats,
                'format_version': 2  # Indicate this is the new format with history
            }
            
            return web.json_response(stats_response)
            
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @staticmethod
    async def update_lora_code(request):
        """
        Update Lora code in ComfyUI nodes
        
        Expects a JSON body with:
        {
            "node_ids": [123, 456], # Optional - List of node IDs to update (for browser mode)
            "lora_code": "<lora:modelname:1.0>", # The Lora code to send
            "mode": "append" # or "replace" - whether to append or replace existing code
        }
        """
        try:
            # Parse the request body
            data = await request.json()
            node_ids = data.get('node_ids')
            lora_code = data.get('lora_code', '')
            mode = data.get('mode', 'append')
            
            if not lora_code:
                return web.json_response({
                    'success': False,
                    'error': 'Missing lora_code parameter'
                }, status=400)
            
            results = []
            
            # Desktop mode: no specific node_ids provided
            if node_ids is None:
                try:
                    # Send broadcast message with id=-1 to all Lora Loader nodes
                    PromptServer.instance.send_sync("lora_code_update", {
                        "id": -1,
                        "lora_code": lora_code,
                        "mode": mode
                    })
                    results.append({
                        'node_id': 'broadcast',
                        'success': True
                    })
                except Exception as e:
                    logger.error(f"Error broadcasting lora code: {e}")
                    results.append({
                        'node_id': 'broadcast',
                        'success': False,
                        'error': str(e)
                    })
            else:
                # Browser mode: send to specific nodes
                for node_id in node_ids:
                    try:
                        # Send the message to the frontend
                        PromptServer.instance.send_sync("lora_code_update", {
                            "id": node_id,
                            "lora_code": lora_code,
                            "mode": mode
                        })
                        results.append({
                            'node_id': node_id,
                            'success': True
                        })
                    except Exception as e:
                        logger.error(f"Error sending lora code to node {node_id}: {e}")
                        results.append({
                            'node_id': node_id,
                            'success': False,
                            'error': str(e)
                        })
            
            return web.json_response({
                'success': True,
                'results': results
            })
            
        except Exception as e:
            logger.error(f"Failed to update lora code: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def get_trained_words(request):
        """
        Get trained words from a safetensors file, sorted by frequency
        
        Expects a query parameter:
        file_path: Path to the safetensors file
        """
        try:
            # Get file path from query parameters
            file_path = request.query.get('file_path')
            
            if not file_path:
                return web.json_response({
                    'success': False,
                    'error': 'Missing file_path parameter'
                }, status=400)
            
            # Check if file exists and is a safetensors file
            if not os.path.exists(file_path):
                return web.json_response({
                    'success': False,
                    'error': f"File not found: {file_path}"
                }, status=404)
                
            if not file_path.lower().endswith('.safetensors'):
                return web.json_response({
                    'success': False,
                    'error': 'File is not a safetensors file'
                }, status=400)
            
            # Extract trained words and class_tokens
            trained_words, class_tokens = await extract_trained_words(file_path)
            
            # Return result with both trained words and class tokens
            return web.json_response({
                'success': True,
                'trained_words': trained_words,
                'class_tokens': class_tokens
            })
            
        except Exception as e:
            logger.error(f"Failed to get trained words: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def get_model_example_files(request):
        """
        Get list of example image files for a specific model based on file path
        
        Expects:
        - file_path in query parameters
        
        Returns:
        - List of image files with their paths as static URLs
        """
        try:
            # Get the model file path from query parameters
            file_path = request.query.get('file_path')
            
            if not file_path:
                return web.json_response({
                    'success': False,
                    'error': 'Missing file_path parameter'
                }, status=400)
            
            # Extract directory and base filename
            model_dir = os.path.dirname(file_path)
            model_filename = os.path.basename(file_path)
            model_name = os.path.splitext(model_filename)[0]
            
            # Check if the directory exists
            if not os.path.exists(model_dir):
                return web.json_response({
                    'success': False, 
                    'error': 'Model directory not found',
                    'files': []
                }, status=404)
            
            # Look for files matching the pattern modelname.example.<index>.<ext>
            files = []
            pattern = f"{model_name}.example."
            
            for file in os.listdir(model_dir):
                file_lower = file.lower()
                if file_lower.startswith(pattern.lower()):
                    file_full_path = os.path.join(model_dir, file)
                    if os.path.isfile(file_full_path):
                        # Check if the file is a supported media file
                        file_ext = os.path.splitext(file)[1].lower()
                        if (file_ext in SUPPORTED_MEDIA_EXTENSIONS['images'] or 
                            file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']):
                            
                            # Extract the index from the filename
                            try:
                                # Extract the part after '.example.' and before file extension
                                index_part = file[len(pattern):].split('.')[0]
                                # Try to parse it as an integer
                                index = int(index_part)
                            except (ValueError, IndexError):
                                # If we can't parse the index, use infinity to sort at the end
                                index = float('inf')
                            
                            # Convert file path to static URL
                            static_url = config.get_preview_static_url(file_full_path)
                            
                            files.append({
                                'name': file,
                                'path': static_url,
                                'extension': file_ext,
                                'is_video': file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos'],
                                'index': index
                            })
            
            # Sort files by their index for consistent ordering
            files.sort(key=lambda x: x['index'])
            # Remove the index field as it's only used for sorting
            for file in files:
                file.pop('index', None)
            
            return web.json_response({
                'success': True,
                'files': files
            })
            
        except Exception as e:
            logger.error(f"Failed to get model example files: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def register_nodes(request):
        """
        Register multiple Lora nodes at once
        
        Expects a JSON body with:
        {
            "nodes": [
                {
                    "node_id": 123,
                    "bgcolor": "#535",
                    "title": "Lora Loader (LoraManager)"
                },
                ...
            ]
        }
        """
        try:
            data = await request.json()
            
            # Validate required fields
            nodes = data.get('nodes', [])
            
            if not isinstance(nodes, list):
                return web.json_response({
                    'success': False,
                    'error': 'nodes must be a list'
                }, status=400)
            
            # Validate each node
            for i, node in enumerate(nodes):
                if not isinstance(node, dict):
                    return web.json_response({
                        'success': False,
                        'error': f'Node {i} must be an object'
                    }, status=400)
                
                node_id = node.get('node_id')
                if node_id is None:
                    return web.json_response({
                        'success': False,
                        'error': f'Node {i} missing node_id parameter'
                    }, status=400)
                
                # Validate node_id is an integer
                try:
                    node['node_id'] = int(node_id)
                except (ValueError, TypeError):
                    return web.json_response({
                        'success': False,
                        'error': f'Node {i} node_id must be an integer'
                    }, status=400)
            
            # Register all nodes
            node_registry.register_nodes(nodes)
            
            return web.json_response({
                'success': True,
                'message': f'{len(nodes)} nodes registered successfully'
            })
            
        except Exception as e:
            logger.error(f"Failed to register nodes: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @staticmethod
    async def get_registry(request):
        """Get current node registry information by refreshing from frontend"""
        try:
            # Check if running in standalone mode
            if standalone_mode:
                logger.warning("Registry refresh not available in standalone mode")
                return web.json_response({
                    'success': False,
                    'error': 'Standalone Mode Active',
                    'message': 'Cannot interact with ComfyUI in standalone mode.'
                }, status=503)
            
            # Send message to frontend to refresh registry
            try:
                PromptServer.instance.send_sync("lora_registry_refresh", {})
                logger.debug("Sent registry refresh request to frontend")
            except Exception as e:
                logger.error(f"Failed to send registry refresh message: {e}")
                return web.json_response({
                    'success': False,
                    'error': 'Communication Error',
                    'message': f'Failed to communicate with ComfyUI frontend: {str(e)}'
                }, status=500)
            
            # Wait for registry update with timeout
            def wait_for_registry():
                return node_registry.wait_for_update(timeout=1.0)
            
            # Run the wait in a thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            registry_updated = await loop.run_in_executor(None, wait_for_registry)
            
            if not registry_updated:
                logger.warning("Registry refresh timeout after 1 second")
                return web.json_response({
                    'success': False,
                    'error': 'Timeout Error',
                    'message': 'Registry refresh timeout - ComfyUI frontend may not be responsive'
                }, status=408)
            
            # Get updated registry
            registry_info = node_registry.get_registry()
            
            return web.json_response({
                'success': True,
                'data': registry_info
            })
            
        except Exception as e:
            logger.error(f"Failed to get registry: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': 'Internal Error',
                'message': str(e)
            }, status=500)

    @staticmethod
    async def check_model_exists(request):
        """
        Check if a model with specified modelId and optionally modelVersionId exists in the library
        
        Expects query parameters:
        - modelId: int - Civitai model ID (required)
        - modelVersionId: int - Civitai model version ID (optional)
        
        Returns:
        - If modelVersionId is provided: JSON with a boolean 'exists' field
        - If modelVersionId is not provided: JSON with a list of modelVersionIds that exist in the library
        """
        try:
            # Get the modelId and modelVersionId from query parameters
            model_id_str = request.query.get('modelId')
            model_version_id_str = request.query.get('modelVersionId')
            
            # Validate modelId parameter (required)
            if not model_id_str:
                return web.json_response({
                    'success': False,
                    'error': 'Missing required parameter: modelId'
                }, status=400)
                
            try:
                # Convert modelId to integer
                model_id = int(model_id_str)
            except ValueError:
                return web.json_response({
                    'success': False,
                    'error': 'Parameter modelId must be an integer'
                }, status=400)
            
            # Get all scanners
            lora_scanner = await ServiceRegistry.get_lora_scanner()
            checkpoint_scanner = await ServiceRegistry.get_checkpoint_scanner()
            embedding_scanner = await ServiceRegistry.get_embedding_scanner()
            
            # If modelVersionId is provided, check for specific version
            if model_version_id_str:
                try:
                    model_version_id = int(model_version_id_str)
                except ValueError:
                    return web.json_response({
                        'success': False,
                        'error': 'Parameter modelVersionId must be an integer'
                    }, status=400)
                
                # Check lora scanner first
                exists = False
                model_type = None

                if await lora_scanner.check_model_version_exists(model_version_id):
                    exists = True
                    model_type = 'lora'
                elif checkpoint_scanner and await checkpoint_scanner.check_model_version_exists(model_version_id):
                    exists = True
                    model_type = 'checkpoint'
                elif embedding_scanner and await embedding_scanner.check_model_version_exists(model_version_id):
                    exists = True
                    model_type = 'embedding'
                
                return web.json_response({
                    'success': True,
                    'exists': exists,
                    'modelType': model_type if exists else None
                })
            
            # If modelVersionId is not provided, return all version IDs for the model
            else:
                lora_versions = await lora_scanner.get_model_versions_by_id(model_id)
                checkpoint_versions = []
                embedding_versions = []

                # 优先lora，其次checkpoint，最后embedding
                if not lora_versions:
                    checkpoint_versions = await checkpoint_scanner.get_model_versions_by_id(model_id)
                if not lora_versions and not checkpoint_versions:
                    embedding_versions = await embedding_scanner.get_model_versions_by_id(model_id)

                model_type = None
                versions = []

                if lora_versions:
                    model_type = 'lora'
                    versions = lora_versions
                elif checkpoint_versions:
                    model_type = 'checkpoint'
                    versions = checkpoint_versions
                elif embedding_versions:
                    model_type = 'embedding'
                    versions = embedding_versions

                return web.json_response({
                    'success': True,
                    'modelId': model_id,
                    'modelType': model_type,
                    'versions': versions
                })
            
        except Exception as e:
            logger.error(f"Failed to check model existence: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def download_metadata_archive(request):
        """Download and extract the metadata archive database"""
        try:
            archive_manager = await get_metadata_archive_manager()
            
            # Get the download_id from query parameters if provided
            download_id = request.query.get('download_id')
            
            # Progress callback to send updates via WebSocket
            def progress_callback(stage, message):
                data = {
                    'stage': stage,
                    'message': message,
                    'type': 'metadata_archive_download'
                }
                
                if download_id:
                    # Send to specific download WebSocket if download_id is provided
                    asyncio.create_task(ws_manager.broadcast_download_progress(download_id, data))
                else:
                    # Fallback to general broadcast
                    asyncio.create_task(ws_manager.broadcast(data))
            
            # Download and extract in background
            success = await archive_manager.download_and_extract_database(progress_callback)
            
            if success:
                # Update settings to enable metadata archive
                settings.set('enable_metadata_archive_db', True)
                
                # Update metadata providers
                await update_metadata_providers()
                
                return web.json_response({
                    'success': True,
                    'message': 'Metadata archive database downloaded and extracted successfully'
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to download and extract metadata archive database'
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error downloading metadata archive: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @staticmethod
    async def remove_metadata_archive(request):
        """Remove the metadata archive database"""
        try:
            archive_manager = await get_metadata_archive_manager()
            
            success = await archive_manager.remove_database()
            
            if success:
                # Update settings to disable metadata archive
                settings.set('enable_metadata_archive_db', False)
                
                # Update metadata providers
                await update_metadata_providers()
                
                return web.json_response({
                    'success': True,
                    'message': 'Metadata archive database removed successfully'
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to remove metadata archive database'
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error removing metadata archive: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @staticmethod
    async def get_metadata_archive_status(request):
        """Get the status of metadata archive database"""
        try:
            archive_manager = await get_metadata_archive_manager()
            
            is_available = archive_manager.is_database_available()
            is_enabled = settings.get('enable_metadata_archive_db', False)
            
            db_size = 0
            if is_available:
                db_path = archive_manager.get_database_path()
                if db_path and os.path.exists(db_path):
                    db_size = os.path.getsize(db_path)
            
            return web.json_response({
                'success': True,
                'isAvailable': is_available,
                'isEnabled': is_enabled,
                'databaseSize': db_size,
                'databasePath': archive_manager.get_database_path() if is_available else None
            })
            
        except Exception as e:
            logger.error(f"Error getting metadata archive status: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def get_model_versions_status(request):
        """
        Get all versions of a model from metadata provider and check their library status
        
        Expects query parameters:
        - modelId: int - Civitai model ID (required)
        
        Returns:
        - JSON with model type and versions list, each version includes 'inLibrary' flag
        """
        try:
            # Get the modelId from query parameters
            model_id_str = request.query.get('modelId')
            
            # Validate modelId parameter (required)
            if not model_id_str:
                return web.json_response({
                    'success': False,
                    'error': 'Missing required parameter: modelId'
                }, status=400)
                
            try:
                # Convert modelId to integer
                model_id = int(model_id_str)
            except ValueError:
                return web.json_response({
                    'success': False,
                    'error': 'Parameter modelId must be an integer'
                }, status=400)
            
            # Get metadata provider
            metadata_provider = await get_metadata_provider()
            if not metadata_provider:
                return web.json_response({
                    'success': False,
                    'error': 'Metadata provider not available'
                }, status=503)
            
            # Get model versions from metadata provider
            response = await metadata_provider.get_model_versions(model_id)
            if not response or not response.get('modelVersions'):
                return web.json_response({
                    'success': False,
                    'error': 'Model not found'
                }, status=404)
            
            versions = response.get('modelVersions', [])
            model_name = response.get('name', '')
            model_type = response.get('type', '').lower()
            
            # Determine scanner based on model type
            scanner = None
            normalized_type = None
            
            if model_type in ['lora', 'locon', 'dora']:
                scanner = await ServiceRegistry.get_lora_scanner()
                normalized_type = 'lora'
            elif model_type == 'checkpoint':
                scanner = await ServiceRegistry.get_checkpoint_scanner()
                normalized_type = 'checkpoint'
            elif model_type == 'textualinversion':
                scanner = await ServiceRegistry.get_embedding_scanner()
                normalized_type = 'embedding'
            else:
                return web.json_response({
                    'success': False,
                    'error': f'Model type "{model_type}" is not supported'
                }, status=400)
            
            if not scanner:
                return web.json_response({
                    'success': False,
                    'error': f'Scanner for type "{normalized_type}" is not available'
                }, status=503)
            
            # Get local versions from scanner
            local_versions = await scanner.get_model_versions_by_id(model_id)
            local_version_ids = set(version['versionId'] for version in local_versions)
            
            # Add inLibrary flag to each version
            enriched_versions = []
            for version in versions:
                version_id = version.get('id')
                enriched_version = {
                    'id': version_id,
                    'name': version.get('name', ''),
                    'thumbnailUrl': version.get('images')[0]['url'] if version.get('images') else None,
                    'inLibrary': version_id in local_version_ids
                }
                enriched_versions.append(enriched_version)
            
            return web.json_response({
                'success': True,
                'modelId': model_id,
                'modelName': model_name,
                'modelType': model_type,
                'versions': enriched_versions
            })
            
        except Exception as e:
            logger.error(f"Failed to get model versions status: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
        
    @staticmethod
    async def open_file_location(request):
        """
        Open the folder containing the specified file and select the file in the file explorer.

        Expects a JSON request body with:
        {
            "file_path": "absolute/path/to/file"
        }
        """
        try:
            data = await request.json()
            file_path = data.get('file_path')

            if not file_path:
                return web.json_response({
                    'success': False,
                    'error': 'Missing file_path parameter'
                }, status=400)

            file_path = os.path.abspath(file_path)

            if not os.path.isfile(file_path):
                return web.json_response({
                    'success': False,
                    'error': 'File does not exist'
                }, status=404)

            # Open the folder and select the file
            if os.name == 'nt':  # Windows
                # explorer /select,"C:\path\to\file"
                subprocess.Popen(['explorer', '/select,', file_path])
            elif os.name == 'posix':
                if sys.platform == 'darwin':  # macOS
                    subprocess.Popen(['open', '-R', file_path])
                else:  # Linux (selecting file is not standard, just open folder)
                    folder = os.path.dirname(file_path)
                    subprocess.Popen(['xdg-open', folder])

            return web.json_response({
                'success': True,
                'message': f'Opened folder and selected file: {file_path}'
            })

        except Exception as e:
            logger.error(f"Failed to open file location: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
