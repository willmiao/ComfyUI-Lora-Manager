import logging
from aiohttp import web
from typing import Dict, Any

from .base_model_controller import BaseModelController
from ..services.lora_service import LoraService
from ..services.service_registry import ServiceRegistry
from ..services.metadata_service import get_default_metadata_provider
from ..services.server_i18n import server_i18n

logger = logging.getLogger(__name__)


class LoraController(BaseModelController):
    """LoRA-specific controller"""
    
    def __init__(self, service_container=None):
        """Initialize LoRA controller"""
        # Service will be initialized later via setup_routes
        self.service = None
        super().__init__(None, 'lora', service_container)
    
    async def initialize_services(self):
        """Initialize services from ServiceRegistry"""
        lora_scanner = await ServiceRegistry.get_lora_scanner()
        self.service = LoraService(lora_scanner)
        
        # Update the model_service reference in parent
        self.model_service = self.service
    
    def setup_routes(self, app: web.Application):
        """Setup LoRA routes"""
        # Schedule service initialization on app startup
        app.on_startup.append(lambda _: self.initialize_services())
        
        # Setup common routes with 'loras' prefix
        super().setup_routes(app, 'loras')
    
    def setup_specific_routes(self, app: web.Application, prefix: str):
        """Setup LoRA-specific routes"""
        # LoRA-specific query routes
        app.router.add_get(f'/api/{prefix}/letter-counts', self.get_letter_counts)
        app.router.add_get(f'/api/{prefix}/get-trigger-words', self.get_lora_trigger_words)
        app.router.add_get(f'/api/{prefix}/usage-tips-by-path', self.get_lora_usage_tips_by_path)
        
        # CivitAI integration with LoRA-specific validation
        app.router.add_get(f'/api/{prefix}/civitai/versions/{{model_id}}', self.get_civitai_versions_lora)
        app.router.add_get(f'/api/{prefix}/civitai/model/version/{{modelVersionId}}', self.get_civitai_model_by_version)
        app.router.add_get(f'/api/{prefix}/civitai/model/hash/{{hash}}', self.get_civitai_model_by_hash)
        
        # ComfyUI integration
        app.router.add_post(f'/api/{prefix}/get_trigger_words', self.get_trigger_words)
    
    async def handle_models_page(self, request: web.Request) -> web.Response:
        """Handle the LoRAs page"""
        try:
            template = self.template_env.get_template(self.template_name)
            content = template.render(
                title=server_i18n.get('loras.title', 'LoRAs'),
                model_type='lora'
            )
            return web.Response(text=content, content_type='text/html')
        except Exception as e:
            logger.error(f"Error rendering LoRAs page: {e}", exc_info=True)
            return web.Response(text="Error loading page", status=500)
    
    def _parse_specific_params(self, request: web.Request) -> Dict[str, Any]:
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
    
    # LoRA-specific route handlers
    async def get_letter_counts(self, request: web.Request) -> web.Response:
        """Get count of LoRAs for each letter of the alphabet"""
        try:
            letter_counts = await self.model_service.get_letter_counts()
            return web.json_response({
                'success': True,
                'letter_counts': letter_counts
            })
        except Exception as e:
            return self._handle_exception('get_letter_counts', e)
    
    async def get_lora_trigger_words(self, request: web.Request) -> web.Response:
        """Get trigger words for a specific LoRA file"""
        try:
            lora_name = request.query.get('name')
            if not lora_name:
                return web.json_response({
                    'success': False,
                    'error': 'LoRA name is required'
                }, status=400)
            
            trigger_words = await self.model_service.get_lora_trigger_words(lora_name)
            return web.json_response({
                'success': True,
                'trigger_words': trigger_words
            })
            
        except Exception as e:
            return self._handle_exception('get_lora_trigger_words', e)
    
    async def get_lora_usage_tips_by_path(self, request: web.Request) -> web.Response:
        """Get usage tips for a LoRA by its relative path"""
        try:
            relative_path = request.query.get('relative_path')
            if not relative_path:
                return web.json_response({
                    'success': False,
                    'error': 'Relative path is required'
                }, status=400)
            
            usage_tips = await self.model_service.get_lora_usage_tips_by_path(relative_path)
            return web.json_response({
                'success': True,
                'usage_tips': usage_tips
            })
            
        except Exception as e:
            return self._handle_exception('get_lora_usage_tips_by_path', e)
    
    # CivitAI integration methods
    async def get_civitai_versions_lora(self, request: web.Request) -> web.Response:
        """Get available versions for a Civitai LoRA model with local availability info"""
        try:
            model_id = request.match_info['model_id']
            metadata_provider = await get_default_metadata_provider()
            response = await metadata_provider.get_model_versions(model_id)
            if not response or not response.get('modelVersions'):
                return web.Response(status=404, text="Model not found")
            
            versions = response.get('modelVersions', [])
            model_type = response.get('type', '')
            
            # Check model type - should be LORA
            if model_type.lower() != 'lora':
                return web.json_response({
                    'error': f"Model type mismatch. Expected LORA, got {model_type}"
                }, status=400)
            
            # Check local availability for each version
            for version in versions:
                # Find the primary model file (type="Model" and primary=true) in the files list
                model_file = next((file for file in version.get('files', []) 
                                  if file.get('type') == 'Model' and file.get('primary') == True), None)
                
                # If no primary file found, try to find any model file
                if not model_file:
                    model_file = next((file for file in version.get('files', []) 
                                      if file.get('type') == 'Model'), None)
                
                if model_file:
                    sha256 = model_file.get('hashes', {}).get('SHA256')
                    if sha256:
                        # Set existsLocally and localPath at the version level
                        version['existsLocally'] = self.model_service.has_hash(sha256)
                        if version['existsLocally']:
                            version['localPath'] = self.model_service.get_path_by_hash(sha256)
                        
                        # Also set the model file size at the version level for easier access
                        version['modelSizeKB'] = model_file.get('sizeKB')
                else:
                    # No model file found in this version
                    version['existsLocally'] = False
                    
            return web.json_response(versions)
        except Exception as e:
            return self._handle_exception('get_civitai_versions_lora', e)
    
    async def get_civitai_model_by_version(self, request: web.Request) -> web.Response:
        """Get CivitAI model details by model version ID"""
        try:
            model_version_id = request.match_info['modelVersionId']
            metadata_provider = await get_default_metadata_provider()
            
            response = await metadata_provider.get_model_by_version_id(model_version_id)
            if not response:
                return web.Response(status=404, text="Model version not found")
            
            return web.json_response(response)
        except Exception as e:
            return self._handle_exception('get_civitai_model_by_version', e)
    
    async def get_civitai_model_by_hash(self, request: web.Request) -> web.Response:
        """Get CivitAI model details by hash"""
        try:
            hash_value = request.match_info['hash']
            metadata_provider = await get_default_metadata_provider()
            
            response = await metadata_provider.get_model_by_hash(hash_value)
            if not response:
                return web.Response(status=404, text="Model not found")
            
            return web.json_response(response)
        except Exception as e:
            return self._handle_exception('get_civitai_model_by_hash', e)
    
    async def get_trigger_words(self, request: web.Request) -> web.Response:
        """Get trigger words for specified LoRA models"""
        try:
            data = await request.json()
            lora_names = data.get('lora_names', [])
            
            if not isinstance(lora_names, list):
                return web.json_response({
                    'success': False,
                    'error': 'lora_names must be a list'
                }, status=400)
            
            result = {}
            for lora_name in lora_names:
                trigger_words = await self.model_service.get_lora_trigger_words(lora_name)
                result[lora_name] = trigger_words
            
            return web.json_response({
                'success': True,
                'trigger_words': result
            })

        except Exception as e:
            return self._handle_exception('get_trigger_words', e)
