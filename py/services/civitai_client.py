import asyncio
import copy
import logging
import os
from typing import Any, Optional, Dict, Tuple, List, Sequence
from .model_metadata_provider import CivitaiModelMetadataProvider, ModelMetadataProviderManager
from .downloader import get_downloader
from .errors import RateLimitError, ResourceNotFoundError

logger = logging.getLogger(__name__)

class CivitaiClient:
    _instance = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance of CivitaiClient"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                
                # Register this client as a metadata provider
                provider_manager = await ModelMetadataProviderManager.get_instance()
                provider_manager.register_provider('civitai', CivitaiModelMetadataProvider(cls._instance), True)
                
            return cls._instance

    def __init__(self):
        # Check if already initialized for singleton pattern
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.base_url = "https://civitai.com/api/v1"

    async def _make_request(
        self,
        method: str,
        url: str,
        *,
        use_auth: bool = False,
        **kwargs,
    ) -> Tuple[bool, Dict | str]:
        """Wrapper around downloader.make_request that surfaces rate limits."""

        downloader = await get_downloader()
        success, result = await downloader.make_request(
            method,
            url,
            use_auth=use_auth,
            **kwargs,
        )
        if not success and isinstance(result, RateLimitError):
            if result.provider is None:
                result.provider = "civitai_api"
            raise result
        return success, result

    @staticmethod
    def _remove_comfy_metadata(model_version: Optional[Dict]) -> None:
        """Remove Comfy-specific metadata from model version images."""
        if not isinstance(model_version, dict):
            return

        images = model_version.get("images")
        if not isinstance(images, list):
            return

        for image in images:
            if not isinstance(image, dict):
                continue

            meta = image.get("meta")
            if isinstance(meta, dict) and "comfy" in meta:
                meta.pop("comfy", None)
    
    async def download_file(self, url: str, save_dir: str, default_filename: str, progress_callback=None) -> Tuple[bool, str]:
        """Download file with resumable downloads and retry mechanism

        Args:
            url: Download URL
            save_dir: Directory to save the file
            default_filename: Fallback filename if none provided in headers
            progress_callback: Optional async callback function for progress updates (0-100)

        Returns:
            Tuple[bool, str]: (success, save_path or error message)
        """
        downloader = await get_downloader()
        save_path = os.path.join(save_dir, default_filename)
        
        # Use unified downloader with CivitAI authentication
        success, result = await downloader.download_file(
            url=url,
            save_path=save_path,
            progress_callback=progress_callback,
            use_auth=True,  # Enable CivitAI authentication
            allow_resume=True
        )
        
        return success, result

    async def get_model_by_hash(self, model_hash: str) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            success, result = await self._make_request(
                'GET',
                f"{self.base_url}/model-versions/by-hash/{model_hash}",
                use_auth=True
            )
            if success:
                # Get model ID from version data
                model_id = result.get('modelId')
                if model_id:
                    # Fetch additional model metadata
                    success_model, data = await self._make_request(
                        'GET',
                        f"{self.base_url}/models/{model_id}",
                        use_auth=True
                    )
                    if success_model:
                        # Enrich version_info with model data
                        result['model']['description'] = data.get("description")
                        result['model']['tags'] = data.get("tags", [])

                        # Add creator from model data
                        result['creator'] = data.get("creator")

                self._remove_comfy_metadata(result)
                return result, None
            
            # Handle specific error cases
            if "not found" in str(result):
                return None, "Model not found"
            
            # Other error cases
            logger.error(f"Failed to fetch model info for {model_hash[:10]}: {result}")
            return None, str(result)
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"API Error: {str(e)}")
            return None, str(e)

    async def download_preview_image(self, image_url: str, save_path: str):
        try:
            downloader = await get_downloader()
            success, content, headers = await downloader.download_to_memory(
                image_url,
                use_auth=False  # Preview images don't need auth
            )
            if success:
                # Ensure directory exists
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(content)
                return True
            return False
        except Exception as e:
            logger.error(f"Download Error: {str(e)}")
            return False
            
    @staticmethod
    def _extract_error_message(payload: Any) -> str:
        """Return a human-readable error message from an API payload."""

        def _from_value(value: Any) -> str:
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                for key in ("message", "error", "detail", "details"):
                    if key in value:
                        candidate = _from_value(value[key])
                        if candidate:
                            return candidate
            if isinstance(value, list):
                for item in value:
                    candidate = _from_value(item)
                    if candidate:
                        return candidate
            return ""

        return _from_value(payload)

    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        """Get all versions of a model with local availability info"""
        try:
            success, result = await self._make_request(
                'GET',
                f"{self.base_url}/models/{model_id}",
                use_auth=True
            )
            if success:
                # Also return model type along with versions
                return {
                    'modelVersions': result.get('modelVersions', []),
                    'type': result.get('type', ''),
                    'name': result.get('name', '')
                }
            message = self._extract_error_message(result)
            if message and 'not found' in message.lower():
                raise ResourceNotFoundError(f"Resource not found for model {model_id}")
            if message:
                raise RuntimeError(message)
            return None
        except RateLimitError:
            raise
        except ResourceNotFoundError as exc:
            logger.info("Model %s is no longer available on Civitai: %s", model_id, exc)
            raise
        except Exception as e:
            logger.error("Error fetching model versions: %s", e, exc_info=True)
            raise

    async def get_model_versions_bulk(
        self, model_ids: Sequence[int]
    ) -> Optional[Dict[int, Dict]]:
        """Fetch model metadata for multiple ids using the batch API."""

        deduped: Dict[int, None] = {}
        for raw_id in model_ids:
            try:
                normalized = int(raw_id)
            except (TypeError, ValueError):
                continue
            deduped.setdefault(normalized, None)

        normalized_ids = [str(model_id) for model_id in deduped.keys()]
        if not normalized_ids:
            return {}

        try:
            query = ",".join(normalized_ids)
            success, result = await self._make_request(
                'GET',
                f"{self.base_url}/models",
                use_auth=True,
                params={'ids': query},
            )
            if not success:
                return None

            items = result.get('items') if isinstance(result, dict) else None
            if not isinstance(items, list):
                return {}

            payload: Dict[int, Dict] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                model_id = item.get('id')
                try:
                    normalized_id = int(model_id)
                except (TypeError, ValueError):
                    continue
                payload[normalized_id] = {
                    'modelVersions': item.get('modelVersions', []),
                    'type': item.get('type', ''),
                    'name': item.get('name', ''),
                }
            return payload
        except RateLimitError:
            raise
        except Exception as exc:
            logger.error(f"Error fetching model versions in bulk: {exc}")
            return None
            
    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        """Get specific model version with additional metadata."""
        try:
            if model_id is None and version_id is not None:
                return await self._get_version_by_id_only(version_id)

            if model_id is not None:
                return await self._get_version_with_model_id(model_id, version_id)

            logger.error("Either model_id or version_id must be provided")
            return None

        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Error fetching model version: {e}")
            return None

    async def _get_version_by_id_only(self, version_id: int) -> Optional[Dict]:
        version = await self._fetch_version_by_id(version_id)
        if version is None:
            return None

        model_id = version.get('modelId')
        if not model_id:
            logger.error(f"No modelId found in version {version_id}")
            return None

        model_data = await self._fetch_model_data(model_id)
        if model_data:
            self._enrich_version_with_model_data(version, model_data)

        self._remove_comfy_metadata(version)
        return version

    async def _get_version_with_model_id(self, model_id: int, version_id: Optional[int]) -> Optional[Dict]:
        model_data = await self._fetch_model_data(model_id)
        if not model_data:
            return None

        target_version = self._select_target_version(model_data, model_id, version_id)
        if target_version is None:
            return None

        target_version_id = target_version.get('id')
        version = await self._fetch_version_by_id(target_version_id) if target_version_id else None

        if version is None:
            model_hash = self._extract_primary_model_hash(target_version)
            if model_hash:
                version = await self._fetch_version_by_hash(model_hash)
            else:
                logger.warning(
                    f"No primary model hash found for model {model_id} version {target_version_id}"
                )

        if version is None:
            version = self._build_version_from_model_data(target_version, model_id, model_data)

        self._enrich_version_with_model_data(version, model_data)
        self._remove_comfy_metadata(version)
        return version

    async def _fetch_model_data(self, model_id: int) -> Optional[Dict]:
        success, data = await self._make_request(
            'GET',
            f"{self.base_url}/models/{model_id}",
            use_auth=True
        )
        if success:
            return data
        logger.warning(f"Failed to fetch model data for model {model_id}")
        return None

    async def _fetch_version_by_id(self, version_id: Optional[int]) -> Optional[Dict]:
        if version_id is None:
            return None

        success, version = await self._make_request(
            'GET',
            f"{self.base_url}/model-versions/{version_id}",
            use_auth=True
        )
        if success:
            return version

        logger.warning(f"Failed to fetch version by id {version_id}")
        return None

    async def _fetch_version_by_hash(self, model_hash: Optional[str]) -> Optional[Dict]:
        if not model_hash:
            return None

        success, version = await self._make_request(
            'GET',
            f"{self.base_url}/model-versions/by-hash/{model_hash}",
            use_auth=True
        )
        if success:
            return version

        logger.warning(f"Failed to fetch version by hash {model_hash}")
        return None

    def _select_target_version(self, model_data: Dict, model_id: int, version_id: Optional[int]) -> Optional[Dict]:
        model_versions = model_data.get('modelVersions', [])
        if not model_versions:
            logger.warning(f"No model versions found for model {model_id}")
            return None

        if version_id is not None:
            target_version = next(
                (item for item in model_versions if item.get('id') == version_id),
                None
            )
            if target_version is None:
                logger.warning(
                    f"Version {version_id} not found for model {model_id}, defaulting to first version"
                )
                return model_versions[0]
            return target_version

        return model_versions[0]

    def _extract_primary_model_hash(self, version_entry: Dict) -> Optional[str]:
        for file_info in version_entry.get('files', []):
            if file_info.get('type') == 'Model' and file_info.get('primary'):
                hashes = file_info.get('hashes', {})
                model_hash = hashes.get('SHA256')
                if model_hash:
                    return model_hash
        return None

    def _build_version_from_model_data(self, version_entry: Dict, model_id: int, model_data: Dict) -> Dict:
        version = copy.deepcopy(version_entry)
        version.pop('index', None)
        version['modelId'] = model_id
        version['model'] = {
            'name': model_data.get('name'),
            'type': model_data.get('type'),
            'nsfw': model_data.get('nsfw'),
            'poi': model_data.get('poi')
        }
        return version

    def _enrich_version_with_model_data(self, version: Dict, model_data: Dict) -> None:
        model_info = version.get('model')
        if not isinstance(model_info, dict):
            model_info = {}
            version['model'] = model_info

        model_info['description'] = model_data.get("description")
        model_info['tags'] = model_data.get("tags", [])
        version['creator'] = model_data.get("creator")

    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch model version metadata from Civitai
        
        Args:
            version_id: The Civitai model version ID
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: A tuple containing:
                - The model version data or None if not found
                - An error message if there was an error, or None on success
        """
        try:
            url = f"{self.base_url}/model-versions/{version_id}"
            
            logger.debug(f"Resolving DNS for model version info: {url}")
            success, result = await self._make_request(
                'GET',
                url,
                use_auth=True
            )
            
            if success:
                logger.debug(f"Successfully fetched model version info for: {version_id}")
                self._remove_comfy_metadata(result)
                return result, None
            
            # Handle specific error cases
            if "not found" in str(result):
                error_msg = f"Model not found"
                logger.warning(f"Model version not found: {version_id} - {error_msg}")
                return None, error_msg
            
            # Other error cases
            logger.error(f"Failed to fetch model info for {version_id}: {result}")
            return None, str(result)
        except RateLimitError:
            raise
        except Exception as e:
            error_msg = f"Error fetching model version info: {e}"
            logger.error(error_msg)
            return None, error_msg

    async def get_image_info(self, image_id: str) -> Optional[Dict]:
        """Fetch image information from Civitai API

        Args:
            image_id: The Civitai image ID
            
        Returns:
            Optional[Dict]: The image data or None if not found
        """
        try:
            url = f"{self.base_url}/images?imageId={image_id}&nsfw=X"
            
            logger.debug(f"Fetching image info for ID: {image_id}")
            success, result = await self._make_request(
                'GET',
                url,
                use_auth=True
            )
            
            if success:
                if result and "items" in result and len(result["items"]) > 0:
                    logger.debug(f"Successfully fetched image info for ID: {image_id}")
                    return result["items"][0]
                logger.warning(f"No image found with ID: {image_id}")
                return None
            
            logger.error(f"Failed to fetch image info for ID: {image_id}: {result}")
            return None
        except RateLimitError:
            raise
        except Exception as e:
            error_msg = f"Error fetching image info: {e}"
            logger.error(error_msg)
            return None

    async def get_user_models(self, username: str) -> Optional[List[Dict]]:
        """Fetch all models for a specific Civitai user."""
        if not username:
            return None

        try:
            url = f"{self.base_url}/models?username={username}"
            success, result = await self._make_request(
                'GET',
                url,
                use_auth=True
            )

            if not success:
                logger.error("Failed to fetch models for %s: %s", username, result)
                return None

            items = result.get("items") if isinstance(result, dict) else None
            if not isinstance(items, list):
                return []

            for model in items:
                versions = model.get("modelVersions")
                if not isinstance(versions, list):
                    continue
                for version in versions:
                    self._remove_comfy_metadata(version)

            return items
        except RateLimitError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error fetching models for %s: %s", username, exc)
            return None
