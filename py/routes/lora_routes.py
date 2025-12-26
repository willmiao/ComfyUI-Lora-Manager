import asyncio
import logging
from aiohttp import web
from typing import Dict
from server import PromptServer  # type: ignore

from .base_model_routes import BaseModelRoutes
from .model_route_registrar import ModelRouteRegistrar
from ..services.lora_service import LoraService
from ..services.service_registry import ServiceRegistry
from ..utils.utils import get_lora_info

logger = logging.getLogger(__name__)

class LoraRoutes(BaseModelRoutes):
    """LoRA-specific route controller"""
    
    def __init__(self):
        """Initialize LoRA routes with LoRA service"""
        super().__init__()
        self.template_name = "loras.html"
    
    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        lora_scanner = await ServiceRegistry.get_lora_scanner()
        update_service = await ServiceRegistry.get_model_update_service()
        self.service = LoraService(lora_scanner, update_service=update_service)
        self.set_model_update_service(update_service)

        # Attach service dependencies
        self.attach_service(self.service)
    
    def setup_routes(self, app: web.Application):
        """Setup LoRA routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())

        # Setup common routes with 'loras' prefix (includes page route)
        super().setup_routes(app, 'loras')

    def setup_specific_routes(self, registrar: ModelRouteRegistrar, prefix: str):
        """Setup LoRA-specific routes"""
        # LoRA-specific query routes
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/letter-counts', prefix, self.get_letter_counts)
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/get-trigger-words', prefix, self.get_lora_trigger_words)
        registrar.add_prefixed_route('GET', '/api/lm/{prefix}/usage-tips-by-path', prefix, self.get_lora_usage_tips_by_path)

        # ComfyUI integration
        registrar.add_prefixed_route('POST', '/api/lm/{prefix}/get_trigger_words', prefix, self.get_trigger_words)
        registrar.add_prefixed_route('POST', '/api/lm/{prefix}/cycler_preview', prefix, self.get_cycler_preview)
    
    def _parse_specific_params(self, request: web.Request) -> Dict:
        """Parse LoRA-specific parameters"""
        params = {}
        
        # LoRA-specific parameters
        if 'first_letter' in request.query:
            params['first_letter'] = request.query.get('first_letter')
        
        # Handle fuzzy search parameter name variation
        if request.query.get('fuzzy') == 'true':
            params['fuzzy_search'] = True
        
        # Handle additional filter parameters for LoRAs
        if 'lora_hash' in request.query:
            if not params.get('hash_filters'):
                params['hash_filters'] = {}
            params['hash_filters']['single_hash'] = request.query['lora_hash'].lower()
        elif 'lora_hashes' in request.query:
            if not params.get('hash_filters'):
                params['hash_filters'] = {}
            params['hash_filters']['multiple_hashes'] = [h.lower() for h in request.query['lora_hashes'].split(',')]
        
        return params
    
    def _validate_civitai_model_type(self, model_type: str) -> bool:
        """Validate CivitAI model type for LoRA"""
        from ..utils.constants import VALID_LORA_TYPES
        return model_type.lower() in VALID_LORA_TYPES
    
    def _get_expected_model_types(self) -> str:
        """Get expected model types string for error messages"""
        return "LORA, LoCon, or DORA"
    
    # LoRA-specific route handlers
    async def get_letter_counts(self, request: web.Request) -> web.Response:
        """Get count of LoRAs for each letter of the alphabet"""
        try:
            letter_counts = await self.service.get_letter_counts()
            return web.json_response({
                'success': True,
                'letter_counts': letter_counts
            })
        except Exception as e:
            logger.error(f"Error getting letter counts: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def get_lora_notes(self, request: web.Request) -> web.Response:
        """Get notes for a specific LoRA file"""
        try:
            lora_name = request.query.get('name')
            if not lora_name:
                return web.Response(text='Lora file name is required', status=400)
            
            notes = await self.service.get_lora_notes(lora_name)
            if notes is not None:
                return web.json_response({
                    'success': True,
                    'notes': notes
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'LoRA not found in cache'
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error getting lora notes: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def get_lora_trigger_words(self, request: web.Request) -> web.Response:
        """Get trigger words for a specific LoRA file"""
        try:
            lora_name = request.query.get('name')
            if not lora_name:
                return web.Response(text='Lora file name is required', status=400)
            
            trigger_words = await self.service.get_lora_trigger_words(lora_name)
            return web.json_response({
                'success': True,
                'trigger_words': trigger_words
            })
            
        except Exception as e:
            logger.error(f"Error getting lora trigger words: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def get_lora_usage_tips_by_path(self, request: web.Request) -> web.Response:
        """Get usage tips for a LoRA by its relative path"""
        try:
            relative_path = request.query.get('relative_path')
            if not relative_path:
                return web.Response(text='Relative path is required', status=400)
            
            usage_tips = await self.service.get_lora_usage_tips_by_relative_path(relative_path)
            return web.json_response({
                'success': True,
                'usage_tips': usage_tips or ''
            })
            
        except Exception as e:
            logger.error(f"Error getting lora usage tips by path: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def get_lora_preview_url(self, request: web.Request) -> web.Response:
        """Get the static preview URL for a LoRA file"""
        try:
            lora_name = request.query.get('name')
            if not lora_name:
                return web.Response(text='Lora file name is required', status=400)
            
            preview_url = await self.service.get_lora_preview_url(lora_name)
            if preview_url:
                return web.json_response({
                    'success': True,
                    'preview_url': preview_url
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'No preview URL found for the specified lora'
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error getting lora preview URL: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def get_lora_civitai_url(self, request: web.Request) -> web.Response:
        """Get the Civitai URL for a LoRA file"""
        try:
            lora_name = request.query.get('name')
            if not lora_name:
                return web.Response(text='Lora file name is required', status=400)
            
            result = await self.service.get_lora_civitai_url(lora_name)
            if result['civitai_url']:
                return web.json_response({
                    'success': True,
                    **result
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'No Civitai data found for the specified lora'
                }, status=404)
                
        except Exception as e:
            logger.error(f"Error getting lora Civitai URL: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def get_trigger_words(self, request: web.Request) -> web.Response:
        """Get trigger words for specified LoRA models"""
        try:
            json_data = await request.json()
            lora_names = json_data.get("lora_names", [])
            node_ids = json_data.get("node_ids", [])
            
            all_trigger_words = []
            for lora_name in lora_names:
                _, trigger_words = get_lora_info(lora_name)
                all_trigger_words.extend(trigger_words)
            
            # Format the trigger words
            trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""
            
            # Send update to all connected trigger word toggle nodes
            for entry in node_ids:
                node_identifier = entry
                graph_identifier = None
                if isinstance(entry, dict):
                    node_identifier = entry.get("node_id")
                    graph_identifier = entry.get("graph_id")

                try:
                    parsed_node_id = int(node_identifier)
                except (TypeError, ValueError):
                    parsed_node_id = node_identifier

                payload = {
                    "id": parsed_node_id,
                    "message": trigger_words_text
                }

                if graph_identifier is not None:
                    payload["graph_id"] = str(graph_identifier)

                PromptServer.instance.send_sync("trigger_word_update", payload)
            
            return web.json_response({"success": True})

        except Exception as e:
            logger.error(f"Error getting trigger words: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def get_cycler_preview(self, request: web.Request) -> web.Response:
        """Get preview of which LoRA would be selected by LoraCycler with current settings.

        This endpoint enables real-time trigger word updates before workflow execution.
        """
        try:
            import os
            import random
            from ..nodes.lora_cycler import _execution_counters
            from ..config import config

            json_data = await request.json()

            # Parse parameters
            folder_filter = json_data.get("folder_filter", "").strip()
            base_model_filter = json_data.get("base_model_filter", "").strip()
            tag_filter = json_data.get("tag_filter", "").strip()
            name_filter = json_data.get("name_filter", "").strip()
            selection_mode = json_data.get("selection_mode", "fixed")
            index = json_data.get("index", 0)
            seed = json_data.get("seed", 0)
            unique_id = json_data.get("unique_id", "default")
            node_ids = json_data.get("node_ids", [])
            first_trigger_word_only = json_data.get("first_trigger_word_only", False)

            # Get LoRA cache data
            scanner = await ServiceRegistry.get_lora_scanner()
            cache = await scanner.get_cached_data()
            raw_data = cache.raw_data

            # Apply filters
            filtered_loras = []
            folder_filter_lower = folder_filter.lower() if folder_filter else ""
            base_model_filter_lower = base_model_filter.lower() if base_model_filter else ""
            tag_filter_lower = tag_filter.lower() if tag_filter else ""
            name_filter_lower = name_filter.lower() if name_filter else ""

            for item in raw_data:
                # Skip excluded items
                if item.get('exclude', False):
                    continue

                # Folder filter
                if folder_filter_lower:
                    item_folder = (item.get('folder') or '').lower()
                    if folder_filter_lower not in item_folder:
                        continue

                # Base model filter
                if base_model_filter_lower:
                    item_base = (item.get('base_model') or '').lower()
                    if base_model_filter_lower not in item_base:
                        continue

                # Tag filter
                if tag_filter_lower:
                    item_tags = [t.lower() for t in (item.get('tags') or [])]
                    if not any(tag_filter_lower in tag for tag in item_tags):
                        continue

                # Name filter
                if name_filter_lower:
                    item_name = (item.get('file_name') or '').lower()
                    model_name = (item.get('model_name') or '').lower()
                    if name_filter_lower not in item_name and name_filter_lower not in model_name:
                        continue

                # Get trigger words
                civitai = item.get('civitai', {})
                trigger_words = civitai.get('trainedWords', []) if civitai else []

                filtered_loras.append({
                    'file_name': item.get('file_name', ''),
                    'model_name': item.get('model_name', ''),
                    'trigger_words': trigger_words,
                })

            # Sort for consistent ordering
            filtered_loras.sort(key=lambda x: x.get('file_name', '').lower())

            total_count = len(filtered_loras)

            if total_count == 0:
                # Send empty trigger words to connected nodes
                for entry in node_ids:
                    node_identifier = entry
                    graph_identifier = None
                    if isinstance(entry, dict):
                        node_identifier = entry.get("node_id")
                        graph_identifier = entry.get("graph_id")

                    try:
                        parsed_node_id = int(node_identifier)
                    except (TypeError, ValueError):
                        parsed_node_id = node_identifier

                    payload = {"id": parsed_node_id, "message": ""}
                    if graph_identifier is not None:
                        payload["graph_id"] = str(graph_identifier)

                    PromptServer.instance.send_sync("trigger_word_update", payload)

                return web.json_response({
                    "success": True,
                    "total_count": 0,
                    "selected_index": -1,
                    "selected_lora": "",
                    "trigger_words": ""
                })

            # Determine selection index based on mode
            node_key = str(unique_id) if unique_id else "default"

            if selection_mode == "fixed":
                selected_index = index % total_count
            elif selection_mode == "random":
                if seed == 0:
                    selected_index = random.randint(0, total_count - 1)
                else:
                    rng = random.Random(seed)
                    selected_index = rng.randint(0, total_count - 1)
            elif selection_mode == "increment":
                current_counter = _execution_counters.get(node_key, index)
                selected_index = current_counter % total_count
            elif selection_mode == "decrement":
                current_counter = _execution_counters.get(node_key, index)
                if current_counter <= 0:
                    current_counter = total_count - 1
                else:
                    current_counter -= 1
                selected_index = current_counter % total_count
            else:
                selected_index = 0

            # Get selected LoRA info
            selected_lora = filtered_loras[selected_index]
            lora_name = selected_lora.get('file_name', '') or selected_lora.get('model_name', '')
            trigger_words = selected_lora.get('trigger_words', [])

            # Apply first_trigger_word_only filter if enabled
            if first_trigger_word_only and trigger_words:
                trigger_words = [trigger_words[0]]

            trigger_words_text = ",, ".join(trigger_words) if trigger_words else ""

            # Send trigger words to connected nodes
            for entry in node_ids:
                node_identifier = entry
                graph_identifier = None
                if isinstance(entry, dict):
                    node_identifier = entry.get("node_id")
                    graph_identifier = entry.get("graph_id")

                try:
                    parsed_node_id = int(node_identifier)
                except (TypeError, ValueError):
                    parsed_node_id = node_identifier

                payload = {"id": parsed_node_id, "message": trigger_words_text}
                if graph_identifier is not None:
                    payload["graph_id"] = str(graph_identifier)

                PromptServer.instance.send_sync("trigger_word_update", payload)

            return web.json_response({
                "success": True,
                "total_count": total_count,
                "selected_index": selected_index,
                "selected_lora": lora_name,
                "trigger_words": trigger_words_text
            })

        except Exception as e:
            logger.error(f"Error in cycler preview: {e}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)
