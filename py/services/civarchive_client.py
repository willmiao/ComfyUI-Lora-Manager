import os
import json
import logging
import asyncio
from typing import Optional, Dict, Tuple, List
from .model_metadata_provider import CivArchiveModelMetadataProvider, ModelMetadataProviderManager
from .downloader import get_downloader

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

    async def get_model_by_hash(self, model_hash: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Find model by SHA256 hash value using CivArchive API"""
        if "/" in model_hash:
           metadata = await self.get_model_by_url(model_hash)
           if metadata:
              return metadata, None
           else:
              return None, f"Error fetching url: {model_hash}"
        try:
            # CivArchive only supports SHA256 hashes
            url = f"{self.base_url}/sha256/{model_hash.lower()}"
            
            downloader = await get_downloader()
            session = await downloader.session
            async with session.get(url) as response:
                if response.status != 200:
                    if response.status == 404:
                        return None, "Model not found"
                    return None, f"HTTP {response.status}"
                
                data = await response.json()
            
            # Extract the model and version data from CivArchive structure
            model_data = data.get('model', {})
            version_data = model_data.get('version', {})
            files_data = data.get('files', {})

            if not version_data:
                if files_data:
                   logger.error(f"{data}")
                   # sometimes CivArc returns ONLY file info... but it can then be used to get the rest of the info...
                   # actually as of now (10/25), api broke and ONLY returns 'files' info...
                   for file_data in files_data:
                      logger.error(f"{file_data}")
                      if file_data["source"] == "civitai":
                          api_data = await self.get_model_version(file_data["model_id"], file_data["model_version_id"])
                          logger.error(f"{api_data}")
                          logger.error(f"found CivArchive model by hash {model_hash[:10]}")
                          return api_data, None
                else:
                   logger.error(f"Error fetching version of CivArchive model by hash {model_hash[:10]}")
                   return None, "No version data found"
            
            # Transform to match expected format
            result = version_data.copy()
            
            # Add model information
            result['model'] = {
                'name': model_data.get('name'),
                'type': model_data.get('type'),
                'nsfw': model_data.get('nsfw', False),
                'description': model_data.get('description'),
                'tags': model_data.get('tags', [])
            }
            
            # Add creator information
            result['creator'] = {
                'username': model_data.get('username', model_data.get('creator_username')),
                'image': ''
            }
            
            # Rename trigger to trainedWords for consistency
            if 'trigger' in result:
                result['trainedWords'] = result.pop('trigger')
            
            # Transform stats
            if 'downloadCount' in result and 'ratingCount' in result and 'rating' in result:
                result['stats'] = {
                    'downloadCount': result.pop('downloadCount'),
                    'ratingCount': result.pop('ratingCount'),
                    'rating': result.pop('rating')
                }
            
            # Transform files to match expected format
            if 'files' in result:
                transformed_files = []
                for file_data in result['files']:
                    # Find first available mirror
                    available_mirror = None
                    for mirror in file_data.get('mirrors', []):
                        if mirror.get('deletedAt') is None:
                            available_mirror = mirror
                            break
                    
                    transformed_file = {
                        'id': file_data.get('id'),
                        'sizeKB': file_data.get('sizeKB'),
                        'name': available_mirror.get('filename', file_data.get('name')) if available_mirror else file_data.get('name'),
                        'type': file_data.get('type'),
                        'downloadUrl': available_mirror.get('url') if available_mirror else file_data.get('downloadUrl'),
                        'primary': True,
                        'mirrors': file_data.get('mirrors', [])
                    }
                    
                    # Transform hash format
                    if 'sha256' in file_data:
                        transformed_file['hashes'] = {
                            'SHA256': file_data['sha256'].upper()
                        }
                    
                    transformed_files.append(transformed_file)
                
                result['files'] = transformed_files
            
            # Add source identifier
            result['source'] = 'civarchive'
            
            return result, None
            
        except Exception as e:
            logger.error(f"Error fetching CivArchive model by hash {model_hash[:10]}: {e}")
            return None, str(e)

    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        """Get all versions of a model using CivArchive API"""
        try:
            url = f"{self.base_url}/models/{model_id}"
            
            downloader = await get_downloader()
            session = await downloader.session
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
            
            # Extract versions list
            versions = data.get('versions', [])
            
            # Return in format similar to Civitai
            return {
                'modelVersions': versions,
                'type': data.get('type', ''),
                'name': data.get('name', '')
            }
            
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
            if version_id is not None:
               url = f"{self.base_url}/models/{model_id}?modelVersionId={version_id}"
            else:
               url = f"{self.base_url}/models/{model_id}"
            
            downloader = await get_downloader()
            session = await downloader.session
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
            
            # Get the version data - CivArchive returns the latest/default version in 'version' field
            version_data = data.get('version', {})
            versions = data.get('versions', {})
            
            # If version_id is specified, check if it matches
            if version_id is not None:
                if version_data.get('id') != version_id:
                   # Version mismatch - would need to iterate through versions or make another call
                   # For now, return None as CivArchive API doesn't provide easy version filtering
                   logger.warning(f"Requested version {version_id} doesn't match default version {version_data.get('id')} for model {model_id}")
                   return None
                if version_data.get('modelId') != model_id:
                   # you can pass ANY model id, and a version number, and get the CORRECT model id from this...
                   # so recall the api with the correct info now
                   return await self.get_model_version(version_data.get('modelId'), version_id)
                         
            # Transform to expected format
            result = version_data.copy()
            
            # Restructure stats
            if 'downloadCount' in result and 'ratingCount' in result and 'rating' in result:
                result['stats'] = {
                    'downloadCount': result.pop('downloadCount'),
                    'ratingCount': result.pop('ratingCount'),
                    'rating': result.pop('rating')
                }
            
            # Rename trigger to trainedWords
            if 'trigger' in result:
                result['trainedWords'] = result.pop('trigger')
            
            # Transform files data
            if 'files' in result:
                transformed_files = []
                for file_data in result['files']:
                    # Find first available mirror
                    available_mirror = None
                    for mirror in file_data.get('mirrors', []):
                        if mirror.get('deletedAt') is None:
                            available_mirror = mirror
                            break
                    
                    transformed_file = {
                        'id': file_data.get('id'),
                        'sizeKB': file_data.get('sizeKB'),
                        'name': available_mirror.get('filename', file_data.get('name')) if available_mirror else file_data.get('name'),
                        'type': file_data.get('type'),
                        'downloadUrl': available_mirror.get('url') if available_mirror else file_data.get('downloadUrl'),
                        'primary': True,
                        'mirrors': file_data.get('mirrors', [])
                    }
                    
                    # Transform hash format
                    if 'sha256' in file_data:
                        transformed_file['hashes'] = {
                            'SHA256': file_data['sha256'].upper()
                        }
                    
                    transformed_files.append(transformed_file)
                
                result['files'] = transformed_files
            
            # Add model information
            result['model'] = {
                'name': data.get('name'),
                'type': data.get('type'),
                'nsfw': data.get('is_nsfw', False),
                'description': data.get('description'),
                'tags': data.get('tags', [])
            }
            
            result['creator'] = {
                'username': data.get('username', data.get('creator_username')),
                'image': ''
            }
            
            # Add source identifier
            result['source'] = 'civarchive'
            result['is_deleted'] = data.get('deletedAt') is not None
            
            return result
            
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
        return await self.get_model_version(1, version_id)

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
                        'primary': True,
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
            
        except Exception as e:
            logger.error(f"Error fetching CivArchive model version (scraping) {model_id}/{version_id}: {e}")
            return None
