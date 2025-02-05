import os
import json
import logging
from aiohttp import web
from typing import Dict, List
from ..services.civitai_client import CivitaiClient
from ..config import config
from ..services.lora_scanner import LoraScanner
from operator import itemgetter
from ..services.websocket_manager import ws_manager
from services.metadata.providers import MetadataProviderManager

logger = logging.getLogger(__name__)

class ApiRoutes:
    """API route handlers for LoRA management"""

    def __init__(self):
        self.scanner = LoraScanner()

    @classmethod
    def setup_routes(cls, app: web.Application):
        """Register API routes"""
        routes = cls()
        app.router.add_post('/api/delete_model', routes.delete_model)
        app.router.add_post('/api/fetch-civitai', routes.fetch_civitai)
        app.router.add_post('/api/replace_preview', routes.replace_preview)
        app.router.add_get('/api/loras', routes.get_loras)
        app.router.add_post('/api/fetch-all-civitai', routes.fetch_all_civitai)
        app.router.add_get('/ws/fetch-progress', ws_manager.handle_connection)
        app.router.add_post('/api/fetch_metadata', routes.fetch_metadata)

    async def delete_model(self, request: web.Request) -> web.Response:
        """Handle model deletion request"""
        try:
            data = await request.json()
            file_path = data.get('file_path')
            if not file_path:
                return web.Response(text='Model path is required', status=400)

            target_dir = os.path.dirname(file_path)
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            
            deleted_files = await self._delete_model_files(target_dir, file_name)
            
            return web.json_response({
                'success': True,
                'deleted_files': deleted_files
            })
            
        except Exception as e:
            logger.error(f"Error deleting model: {e}", exc_info=True)
            return web.Response(text=str(e), status=500)

    async def fetch_civitai(self, request: web.Request) -> web.Response:
        """Handle CivitAI metadata fetch request"""
        client = CivitaiClient()
        try:
            data = await request.json()
            metadata_path = os.path.splitext(data['file_path'])[0] + '.metadata.json'
            
            # Check if model is from CivitAI
            local_metadata = await self._load_local_metadata(metadata_path)
            if not local_metadata.get('from_civitai', True):
                return web.json_response({"success": True, "notice": "Not from CivitAI"})

            # Fetch and update metadata
            civitai_metadata = await client.get_model_by_hash(data["sha256"])
            if not civitai_metadata:
                return await self._handle_not_found_on_civitai(metadata_path, local_metadata)

            await self._update_model_metadata(metadata_path, local_metadata, civitai_metadata, client)
            
            return web.json_response({"success": True})

        except Exception as e:
            logger.error(f"Error fetching from CivitAI: {e}", exc_info=True)
            return web.json_response({"success": False, "error": str(e)}, status=500)
        finally:
            await client.close()

    async def replace_preview(self, request: web.Request) -> web.Response:
        """Handle preview image replacement request"""
        try:
            reader = await request.multipart()
            preview_data, content_type = await self._read_preview_file(reader)
            model_path = await self._read_model_path(reader)
            
            preview_path = await self._save_preview_file(model_path, preview_data, content_type)
            await self._update_preview_metadata(model_path, preview_path)
            
            # Update preview URL in scanner cache
            await self.scanner.update_preview_in_cache(model_path, preview_path)
            
            return web.json_response({
                "success": True,
                "preview_url": config.get_preview_static_url(preview_path)
            })
            
        except Exception as e:
            logger.error(f"Error replacing preview: {e}", exc_info=True)
            return web.Response(text=str(e), status=500)

    async def get_loras(self, request: web.Request) -> web.Response:
        """Handle paginated LoRA data request"""
        try:
            # Parse query parameters
            page = int(request.query.get('page', '1'))
            page_size = int(request.query.get('page_size', '20'))
            sort_by = request.query.get('sort_by', 'name')
            folder = request.query.get('folder')
            search = request.query.get('search', '').lower()
            
            # Validate parameters
            if page < 1 or page_size < 1 or page_size > 100:
                return web.json_response({
                    'error': 'Invalid pagination parameters'
                }, status=400)
            
            if sort_by not in ['date', 'name']:
                return web.json_response({
                    'error': 'Invalid sort parameter'
                }, status=400)
            
            # Get paginated data with search
            result = await self.scanner.get_paginated_data(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                folder=folder,
                search=search
            )
            
            # Format the response data
            formatted_items = [
                self._format_lora_response(item) 
                for item in result['items']
            ]
            
            return web.json_response({
                'items': formatted_items,
                'total': result['total'],
                'page': result['page'],
                'page_size': result['page_size'],
                'total_pages': result['total_pages']
            })
            
        except Exception as e:
            logger.error(f"Error in get_loras: {str(e)}", exc_info=True)
            return web.json_response({
                'error': 'Internal server error'
            }, status=500)

    def _format_lora_response(self, lora: Dict) -> Dict:
        """Format LoRA data for API response"""
        return {
            "model_name": lora["model_name"],
            "file_name": lora["file_name"],
            "preview_url": config.get_preview_static_url(lora["preview_url"]),
            "base_model": lora["base_model"],
            "folder": lora["folder"],
            "sha256": lora["sha256"],
            "file_path": lora["file_path"].replace(os.sep, "/"),
            "modified": lora["modified"],
            "from_civitai": lora.get("from_civitai", True),
            "civitai": self._filter_civitai_data(lora.get("civitai", {}))
        }

    def _filter_civitai_data(self, data: Dict) -> Dict:
        """Filter relevant fields from CivitAI data"""
        if not data:
            return {}
            
        fields = [
            "id", "modelId", "name", "createdAt", "updatedAt", 
            "publishedAt", "trainedWords", "baseModel", "description",
            "model", "images"
        ]
        return {k: data[k] for k in fields if k in data}

    # Private helper methods
    async def _delete_model_files(self, target_dir: str, file_name: str) -> List[str]:
        """Delete model and associated files"""
        patterns = [
            f"{file_name}.safetensors",  # Required
            f"{file_name}.metadata.json",
            f"{file_name}.preview.png",
            f"{file_name}.preview.jpg",
            f"{file_name}.preview.jpeg",
            f"{file_name}.preview.webp",
            f"{file_name}.preview.mp4",
            f"{file_name}.png",
            f"{file_name}.jpg",
            f"{file_name}.jpeg",
            f"{file_name}.webp",
            f"{file_name}.mp4"
        ]
        
        deleted = []
        main_file = patterns[0]
        main_path = os.path.join(target_dir, main_file)
        
        if not os.path.exists(main_path):
            raise web.HTTPNotFound(text=f"Model file not found: {main_file}")
            
        # Delete main file first
        os.remove(main_path)
        deleted.append(main_file)
        
        # Delete optional files
        for pattern in patterns[1:]:
            path = os.path.join(target_dir, pattern)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    deleted.append(pattern)
                except Exception as e:
                    logger.warning(f"Failed to delete {pattern}: {e}")
                    
        return deleted

    async def _read_preview_file(self, reader) -> tuple[bytes, str]:
        """Read preview file and content type from multipart request"""
        field = await reader.next()
        if field.name != 'preview_file':
            raise ValueError("Expected 'preview_file' field")
        content_type = field.headers.get('Content-Type', 'image/png')
        return await field.read(), content_type

    async def _read_model_path(self, reader) -> str:
        """Read model path from multipart request"""
        field = await reader.next()
        if field.name != 'model_path':
            raise ValueError("Expected 'model_path' field")
        return (await field.read()).decode()

    async def _save_preview_file(self, model_path: str, preview_data: bytes, content_type: str) -> str:
        """Save preview file and return its path"""
        # Determine file extension based on content type
        if content_type.startswith('video/'):
            extension = '.preview.mp4'
        else:
            extension = '.preview.png'
        
        base_name = os.path.splitext(os.path.basename(model_path))[0]
        folder = os.path.dirname(model_path)
        preview_path = os.path.join(folder, base_name + extension).replace(os.sep, '/')
        
        with open(preview_path, 'wb') as f:
            f.write(preview_data)
            
        return preview_path

    async def _update_preview_metadata(self, model_path: str, preview_path: str):
        """Update preview path in metadata"""
        metadata_path = os.path.splitext(model_path)[0] + '.metadata.json'
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Update preview_url directly in the metadata dict
                metadata['preview_url'] = preview_path
                
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error updating metadata: {e}")

    async def _load_local_metadata(self, metadata_path: str) -> Dict:
        """Load local metadata file"""
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading metadata from {metadata_path}: {e}")
        return {}

    async def _handle_not_found_on_civitai(self, metadata_path: str, local_metadata: Dict) -> web.Response:
        """Handle case when model is not found on CivitAI"""
        local_metadata['from_civitai'] = False
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(local_metadata, f, indent=2, ensure_ascii=False)
        return web.json_response(
            {"success": False, "error": "Not found on CivitAI"}, 
            status=404
        )

    async def _update_model_metadata(self, metadata_path: str, local_metadata: Dict, 
                                   civitai_metadata: Dict, client: CivitaiClient) -> None:
        """Update local metadata with CivitAI data"""
        local_metadata['civitai'] = civitai_metadata
        
        # Update model name if available
        if 'model' in civitai_metadata:
            local_metadata['model_name'] = civitai_metadata['model'].get('name', 
                                                                       local_metadata.get('model_name'))
        
        # Update base model
        local_metadata['base_model'] = civitai_metadata.get('baseModel')
        
        # Update preview if needed
        if not local_metadata.get('preview_url') or not os.path.exists(local_metadata['preview_url']):
            first_preview = next((img for img in civitai_metadata.get('images', [])), None)
            if first_preview:
                preview_ext = '.mp4' if first_preview['type'] == 'video' else os.path.splitext(first_preview['url'])[-1]
                base_name = os.path.splitext(os.path.splitext(os.path.basename(metadata_path))[0])[0]
                preview_filename = base_name + '.preview' + preview_ext
                preview_path = os.path.join(os.path.dirname(metadata_path), preview_filename)
                
                if await client.download_preview_image(first_preview['url'], preview_path):
                    local_metadata['preview_url'] = preview_path.replace(os.sep, '/')

        # Save updated metadata
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(local_metadata, f, indent=2, ensure_ascii=False)

    async def fetch_all_civitai(self, request: web.Request) -> web.Response:
        """Fetch CivitAI metadata for all loras in the background"""
        try:
            cache = await self.scanner.get_cached_data()
            total = len(cache.raw_data)
            processed = 0
            success = 0
            needs_resort = False
            
            # 准备要处理的 loras
            to_process = [
                lora for lora in cache.raw_data 
                if lora.get('sha256') and not lora.get('civitai') and lora.get('from_civitai')
            ]
            total_to_process = len(to_process)
            
            # 发送初始进度
            await ws_manager.broadcast({
                'status': 'started',
                'total': total_to_process,
                'processed': 0,
                'success': 0
            })
            
            for lora in to_process:
                try:
                    original_name = lora.get('model_name')
                    if await self._fetch_and_update_single_lora(
                        sha256=lora['sha256'],
                        file_path=lora['file_path'],
                        lora=lora
                    ):
                        success += 1
                        if original_name != lora.get('model_name'):
                            needs_resort = True
                    
                    processed += 1
                    
                    # 每处理一个就发送进度更新
                    await ws_manager.broadcast({
                        'status': 'processing',
                        'total': total_to_process,
                        'processed': processed,
                        'success': success,
                        'current_name': lora.get('model_name', 'Unknown')
                    })
                    
                except Exception as e:
                    logger.error(f"Error fetching CivitAI data for {lora['file_path']}: {e}")
            
            if needs_resort:
                await cache.resort(name_only=True)
            
            # 发送完成消息
            await ws_manager.broadcast({
                'status': 'completed',
                'total': total_to_process,
                'processed': processed,
                'success': success
            })
                    
            return web.json_response({
                "success": True,
                "message": f"Successfully updated {success} of {processed} processed loras (total: {total})"
            })
            
        except Exception as e:
            # 发送错误消息
            await ws_manager.broadcast({
                'status': 'error',
                'error': str(e)
            })
            logger.error(f"Error in fetch_all_civitai: {e}")
            return web.Response(text=str(e), status=500)

    async def _fetch_and_update_single_lora(self, sha256: str, file_path: str, lora: dict) -> bool:
        """Fetch and update metadata for a single lora without sorting
        
        Args:
            sha256: SHA256 hash of the lora file
            file_path: Path to the lora file
            lora: The lora object in cache to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        client = CivitaiClient()
        try:
            metadata_path = os.path.splitext(file_path)[0] + '.metadata.json'
            
            # Check if model is from CivitAI
            local_metadata = await self._load_local_metadata(metadata_path)

            # Fetch metadata
            civitai_metadata = await client.get_model_by_hash(sha256)
            if not civitai_metadata:
                # Mark as not from CivitAI if not found
                local_metadata['from_civitai'] = False
                lora['from_civitai'] = False
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(local_metadata, f, indent=2, ensure_ascii=False)
                return False

            # Update metadata
            await self._update_model_metadata(
                metadata_path, 
                local_metadata, 
                civitai_metadata, 
                client
            )
            
            # Update cache object directly
            lora.update({
                'model_name': local_metadata.get('model_name'),
                'preview_url': local_metadata.get('preview_url'),
                'from_civitai': True,
                'civitai': civitai_metadata
            })
                
            return True

        except Exception as e:
            logger.error(f"Error fetching CivitAI data: {e}")
            return False
        finally:
            await client.close()

    async def fetch_metadata(self, request: web.Request) -> web.Response:
        """Handle metadata fetch request"""
        try:
            data = await request.json()
            provider_name = data.get("provider", "civitai")
            
            provider = await MetadataProviderManager.get_provider(provider_name)
            metadata = await provider.get_model_by_hash(data["sha256"])
            
            if not metadata:
                return await self._handle_not_found(data["file_path"])
                
            formatted_data = provider.format_metadata(metadata)
            await self._update_model_metadata(data["file_path"], formatted_data)
            
            return web.json_response({"success": True})
            
        except Exception as e:
            logger.error(f"Error fetching metadata: {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500
            )
