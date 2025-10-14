import os
import json
import logging
import asyncio
from copy import deepcopy
from typing import Optional, Dict, Tuple, List
from .model_metadata_provider import CivArchiveModelMetadataProvider, ModelMetadataProviderManager
from .downloader import get_downloader
from .errors import RateLimitError

try:
    from bs4 import BeautifulSoup
except ImportError as exc:
    BeautifulSoup = None  # type: ignore[assignment]
    _BS4_IMPORT_ERROR = exc
else:
    _BS4_IMPORT_ERROR = None

def _require_beautifulsoup():
    if BeautifulSoup is None:
        raise RuntimeError(
            "BeautifulSoup (bs4) is required for CivArchive client. "
            "Install it with 'pip install beautifulsoup4'."
        ) from _BS4_IMPORT_ERROR
    return BeautifulSoup

logger = logging.getLogger(__name__)

class CivArchiveClient:
    _instance = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance of CivArchiveClient"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                
                # Register this client as a metadata provider
                provider_manager = await ModelMetadataProviderManager.get_instance()
                provider_manager.register_provider('civarchive', CivArchiveModelMetadataProvider(cls._instance), False)
                
            return cls._instance

    def __init__(self):
        # Check if already initialized for singleton pattern
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.base_url = "https://civarchive.com/api"

    async def _request_json(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Call CivArchive API and return JSON payload"""
        success, payload = await self._make_request(path, params=params)
        if not success:
            error = payload if isinstance(payload, str) else "Request failed"
            return None, error
        if not isinstance(payload, dict):
            return None, "Invalid response structure"
        return payload, None

    async def _make_request(
        self,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, Dict | str]:
        """Wrapper around downloader.make_request that surfaces rate limits."""

        downloader = await get_downloader()
        kwargs: Dict[str, Dict[str, str]] = {}
        if params:
            safe_params = {str(key): str(value) for key, value in params.items() if value is not None}
            if safe_params:
                kwargs["params"] = safe_params

        success, payload = await downloader.make_request(
            "GET",
            f"{self.base_url}{path}",
            use_auth=False,
            **kwargs,
        )
        if not success and isinstance(payload, RateLimitError):
            if payload.provider is None:
                payload.provider = "civarchive_api"
            raise payload
        return success, payload

    @staticmethod
    def _normalize_payload(payload: Dict) -> Dict:
        """Unwrap CivArchive responses that wrap content under a data key"""
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    @staticmethod
    def _split_context(payload: Dict) -> Tuple[Dict, Dict, List[Dict]]:
        """Separate version payload from surrounding model context"""
        data = CivArchiveClient._normalize_payload(payload)
        context: Dict = {}
        fallback_files: List[Dict] = []
        version: Dict = {}

        for key, value in data.items():
            if key in {"version", "model"}:
                continue
            context[key] = value

        if isinstance(data.get("version"), dict):
            version = data["version"]

        model_block = data.get("model")
        if isinstance(model_block, dict):
            for key, value in model_block.items():
                if key == "version":
                    if not version and isinstance(value, dict):
                        version = value
                    continue
                context.setdefault(key, value)
            fallback_files = fallback_files or model_block.get("files") or []

        fallback_files = fallback_files or data.get("files") or []
        return context, version, fallback_files

    @staticmethod
    def _ensure_list(value) -> List:
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]

    @staticmethod
    def _build_model_info(context: Dict) -> Dict:
        tags = context.get("tags")
        if not isinstance(tags, list):
            tags = list(tags) if isinstance(tags, (set, tuple)) else ([] if tags is None else [tags])
        return {
            "name": context.get("name"),
            "type": context.get("type"),
            "nsfw": bool(context.get("is_nsfw", context.get("nsfw", False))),
            "description": context.get("description"),
            "tags": tags,
        }

    @staticmethod
    def _build_creator_info(context: Dict) -> Dict:
        username = context.get("creator_username") or context.get("username") or ""
        image = context.get("creator_image") or context.get("creator_avatar") or ""
        creator: Dict[str, Optional[str]] = {
            "username": username,
            "image": image,
        }
        if context.get("creator_name"):
            creator["name"] = context["creator_name"]
        if context.get("creator_url"):
            creator["url"] = context["creator_url"]
        return creator

    @staticmethod
    def _transform_file_entry(file_data: Dict) -> Dict:
        mirrors = file_data.get("mirrors") or []
        if not isinstance(mirrors, list):
            mirrors = [mirrors]
        available_mirror = next(
            (mirror for mirror in mirrors if isinstance(mirror, dict) and mirror.get("deletedAt") is None),
            None
        )
        download_url = file_data.get("downloadUrl")
        if not download_url and available_mirror:
            download_url = available_mirror.get("url")
        name = file_data.get("name")
        if not name and available_mirror:
            name = available_mirror.get("filename")

        transformed: Dict = {
            "id": file_data.get("id"),
            "sizeKB": file_data.get("sizeKB"),
            "name": name,
            "type": file_data.get("type"),
            "downloadUrl": download_url,
            "primary": True,
            # TODO: for some reason is_primary is false in CivArchive response, need to figure this out, 
            # "primary": bool(file_data.get("is_primary", file_data.get("primary", False))),
            "mirrors": mirrors,
        }

        sha256 = file_data.get("sha256")
        if sha256:
            transformed["hashes"] = {"SHA256": str(sha256).upper()}
        elif isinstance(file_data.get("hashes"), dict):
            transformed["hashes"] = file_data["hashes"]

        if "metadata" in file_data:
            transformed["metadata"] = file_data["metadata"]

        if file_data.get("modelVersionId") is not None:
            transformed["modelVersionId"] = file_data.get("modelVersionId")
        elif file_data.get("model_version_id") is not None:
            transformed["modelVersionId"] = file_data.get("model_version_id")

        if file_data.get("modelId") is not None:
            transformed["modelId"] = file_data.get("modelId")
        elif file_data.get("model_id") is not None:
            transformed["modelId"] = file_data.get("model_id")

        return transformed

    def _transform_files(
        self,
        files: Optional[List[Dict]],
        fallback_files: Optional[List[Dict]] = None
    ) -> List[Dict]:
        candidates: List[Dict] = []
        if isinstance(files, list) and files:
            candidates = files
        elif isinstance(fallback_files, list):
            candidates = fallback_files

        transformed_files: List[Dict] = []
        for file_data in candidates:
            if isinstance(file_data, dict):
                transformed_files.append(self._transform_file_entry(file_data))
        return transformed_files

    def _transform_version(
        self,
        context: Dict,
        version: Dict,
        fallback_files: Optional[List[Dict]] = None
    ) -> Optional[Dict]:
        if not version:
            return None

        version_copy = deepcopy(version)
        version_copy.pop("model", None)
        version_copy.pop("creator", None)

        if "trigger" in version_copy:
            triggers = version_copy.pop("trigger")
            if isinstance(triggers, list):
                version_copy["trainedWords"] = triggers
            elif triggers is None:
                version_copy["trainedWords"] = []
            else:
                version_copy["trainedWords"] = [triggers]

        if "trainedWords" in version_copy and isinstance(version_copy["trainedWords"], str):
            version_copy["trainedWords"] = [version_copy["trainedWords"]]

        if "nsfw_level" in version_copy:
            version_copy["nsfwLevel"] = version_copy.pop("nsfw_level")
        elif "nsfwLevel" not in version_copy and context.get("nsfw_level") is not None:
            version_copy["nsfwLevel"] = context.get("nsfw_level")

        stats_keys = ["downloadCount", "ratingCount", "rating"]
        stats = {key: version_copy.pop(key) for key in stats_keys if key in version_copy}
        if stats:
            version_copy["stats"] = stats

        version_copy["files"] = self._transform_files(version_copy.get("files"), fallback_files)
        version_copy["images"] = self._ensure_list(version_copy.get("images"))

        version_copy["model"] = self._build_model_info(context)
        version_copy["creator"] = self._build_creator_info(context)

        version_copy["source"] = "civarchive"
        version_copy["is_deleted"] = bool(context.get("deletedAt")) or bool(version.get("deletedAt"))

        return version_copy

    async def _resolve_version_from_files(self, payload: Dict) -> Optional[Dict]:
        """Fallback to fetch version data when only file metadata is available"""
        data = self._normalize_payload(payload)
        files = data.get("files") or payload.get("files") or []
        if not isinstance(files, list):
            files = [files]
        for file_data in files:
            if not isinstance(file_data, dict):
                continue
            model_id = file_data.get("model_id") or file_data.get("modelId")
            version_id = file_data.get("model_version_id") or file_data.get("modelVersionId")
            if model_id is None or version_id is None:
                continue
            resolved = await self.get_model_version(model_id, version_id)
            if resolved:
                return resolved
        return None

    async def get_model_by_hash(self, model_hash: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Find model by SHA256 hash value using CivArchive API"""
        try:
            payload, error = await self._request_json(f"/sha256/{model_hash.lower()}")
            if error:
                if "not found" in error.lower():
                    return None, "Model not found"
                return None, error

            context, version_data, fallback_files = self._split_context(payload)
            transformed = self._transform_version(context, version_data, fallback_files)
            if transformed:
                return transformed, None

            resolved = await self._resolve_version_from_files(payload)
            if resolved:
                return resolved, None

            logger.error("Error fetching version of CivArchive model by hash %s", model_hash[:10])
            return None, "No version data found"

        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Error fetching CivArchive model by hash {model_hash[:10]}: {e}")
            return None, str(e)

    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        """Get all versions of a model using CivArchive API"""
        try:
            payload, error = await self._request_json(f"/models/{model_id}")
            if error or payload is None:
                if error and "not found" in error.lower():
                    return None
                logger.error(f"Error fetching CivArchive model versions for {model_id}: {error}")
                return None

            data = self._normalize_payload(payload)
            context, version_data, fallback_files = self._split_context(payload)

            versions_meta = data.get("versions") or []
            transformed_versions: List[Dict] = []
            for meta in versions_meta:
                if not isinstance(meta, dict):
                    continue
                version_id = meta.get("id")
                if version_id is None:
                    continue
                target_model_id = meta.get("modelId") or model_id
                version = await self.get_model_version(target_model_id, version_id)
                if version:
                    transformed_versions.append(version)

            # Ensure the primary version is included even if versions list was empty
            primary_version = self._transform_version(context, version_data, fallback_files)
            if primary_version:
                transformed_versions.insert(0, primary_version)

            ordered_versions: List[Dict] = []
            seen_ids = set()
            for version in transformed_versions:
                version_id = version.get("id")
                if version_id in seen_ids:
                    continue
                seen_ids.add(version_id)
                ordered_versions.append(version)

            return {
                "modelVersions": ordered_versions,
                "type": context.get("type", ""),
                "name": context.get("name", ""),
            }

        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Error fetching CivArchive model versions for {model_id}: {e}")
            return None

    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        """Get specific model version using CivArchive API
        
        Args:
            model_id: The model ID (required)
            version_id: Optional specific version ID to filter to
            
        Returns:
            Optional[Dict]: The model version data or None if not found
        """
        if model_id is None:
            return None

        try:
            params = {"modelVersionId": version_id} if version_id is not None else None
            payload, error = await self._request_json(f"/models/{model_id}", params=params)
            if error or payload is None:
                if error and "not found" in error.lower():
                    return None
                logger.error(f"Error fetching CivArchive model version via API {model_id}/{version_id}: {error}")
                return None

            context, version_data, fallback_files = self._split_context(payload)

            if not version_data:
                return await self._resolve_version_from_files(payload)

            if version_id is not None:
                raw_id = version_data.get("id")
                if raw_id != version_id:
                    logger.warning(
                        "Requested version %s doesn't match default version %s for model %s",
                        version_id,
                        raw_id,
                        model_id,
                    )
                    return None
                actual_model_id = version_data.get("modelId")
                context_model_id = context.get("id")
                # CivArchive can respond with data for a different model id while already
                # returning the fully resolved model context. Only follow the redirect when
                # the context itself still points to the original (wrong) model.
                if (
                    actual_model_id is not None
                    and str(actual_model_id) != str(model_id)
                    and (context_model_id is None or str(context_model_id) != str(actual_model_id))
                ):
                    return await self.get_model_version(actual_model_id, version_id)

            return self._transform_version(context, version_data, fallback_files)

        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Error fetching CivArchive model version via API {model_id}/{version_id}: {e}")
            return None

    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """ Fetch model version metadata using a known bogus model lookup        
        CivArchive lacks a direct version lookup API, this uses a workaround (which we handle in the main model request now)
        
        Args:
            version_id: The model version ID
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (version_data, error_message)
        """
        version = await self.get_model_version(1, version_id)
        if version is None:
            return None, "Model not found"
        return version, None

    async def get_model_by_url(self, url) -> Optional[Dict]:
        """Get specific model version by parsing CivArchive HTML page (legacy method)
        
        This is the original HTML scraping implementation, kept for reference and new sites added not in api.
        The primary get_model_version() now uses the API instead.
        """

        try:
            # Construct CivArchive URL
            url = f"https://civarchive.com/{url}"
            downloader = await get_downloader()
            session = await downloader.session
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                html_content = await response.text()
                
            # Parse HTML to extract JSON data
            soup_parser = _require_beautifulsoup()
            soup = soup_parser(html_content, 'html.parser')
            script_tag = soup.find('script', {'id': '__NEXT_DATA__', 'type': 'application/json'})
            
            if not script_tag:
                return None
                
            # Parse JSON content
            json_data = json.loads(script_tag.string)
            model_data = json_data.get('props', {}).get('pageProps', {}).get('model')
            
            if not model_data or 'version' not in model_data:
                return None
            
            # Extract version data as base
            version = model_data['version'].copy()
            
            # Restructure stats
            if 'downloadCount' in version and 'ratingCount' in version and 'rating' in version:
                version['stats'] = {
                    'downloadCount': version.pop('downloadCount'),
                    'ratingCount': version.pop('ratingCount'),
                    'rating': version.pop('rating')
                }
            
            # Rename trigger to trainedWords
            if 'trigger' in version:
                version['trainedWords'] = version.pop('trigger')
            
            # Transform files data to expected format
            if 'files' in version:
                transformed_files = []
                for file_data in version['files']:
                    # Find first available mirror (deletedAt is null)
                    available_mirror = None
                    for mirror in file_data.get('mirrors', []):
                        if mirror.get('deletedAt') is None:
                            available_mirror = mirror
                            break
                    
                    # Create transformed file entry
                    transformed_file = {
                        'id': file_data.get('id'),
                        'sizeKB': file_data.get('sizeKB'),
                        'name': available_mirror.get('filename', file_data.get('name')) if available_mirror else file_data.get('name'),
                        'type': file_data.get('type'),
                        'downloadUrl': available_mirror.get('url') if available_mirror else None,
                        'primary': file_data.get('is_primary', False),
                        'mirrors': file_data.get('mirrors', [])
                    }
                    
                    # Transform hash format
                    if 'sha256' in file_data:
                        transformed_file['hashes'] = {
                            'SHA256': file_data['sha256'].upper()
                        }
                    
                    transformed_files.append(transformed_file)
                
                version['files'] = transformed_files
            
            # Add model information
            version['model'] = {
                'name': model_data.get('name'),
                'type': model_data.get('type'),
                'nsfw': model_data.get('is_nsfw', False),
                'description': model_data.get('description'),
                'tags': model_data.get('tags', [])
            }

            version['creator'] = {
                'username': model_data.get('username'),
                'image': ''
            }
            
            # Add source identifier
            version['source'] = 'civarchive'
            version['is_deleted'] = json_data.get('query', {}).get('is_deleted', False)
            
            return version
            
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Error fetching CivArchive model version (scraping) {url}: {e}")
            return None
