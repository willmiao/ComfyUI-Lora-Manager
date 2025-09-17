from abc import ABC, abstractmethod
import json
import aiosqlite
import logging
import aiohttp
from bs4 import BeautifulSoup
from typing import Optional, Dict, Tuple
from .downloader import get_downloader

logger = logging.getLogger(__name__)

class ModelMetadataProvider(ABC):
    """Base abstract class for all model metadata providers"""
    
    @abstractmethod
    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        """Find model by hash value"""
        pass
        
    @abstractmethod
    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        """Get all versions of a model with their details"""
        pass
        
    @abstractmethod
    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        """Get specific model version with additional metadata"""
        pass
        
    @abstractmethod
    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch model version metadata"""
        pass
        
    @abstractmethod
    async def get_model_metadata(self, model_id: str) -> Tuple[Optional[Dict], int]:
        """Fetch model metadata (description, tags, and creator info)"""
        pass

class CivitaiModelMetadataProvider(ModelMetadataProvider):
    """Provider that uses Civitai API for metadata"""
    
    def __init__(self, civitai_client):
        self.client = civitai_client
        
    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        return await self.client.get_model_by_hash(model_hash)
        
    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        return await self.client.get_model_versions(model_id)
        
    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        return await self.client.get_model_version(model_id, version_id)
        
    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        return await self.client.get_model_version_info(version_id)
        
    async def get_model_metadata(self, model_id: str) -> Tuple[Optional[Dict], int]:
        return await self.client.get_model_metadata(model_id)

class CivArchiveModelMetadataProvider(ModelMetadataProvider):
    """Provider that uses CivArchive HTML page parsing for metadata"""
    
    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        """Not supported by CivArchive provider"""
        return None
        
    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        """Not supported by CivArchive provider"""
        return None
        
    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        """Get specific model version by parsing CivArchive HTML page"""
        if model_id is None or version_id is None:
            return None
        
        try:
            # Construct CivArchive URL
            url = f"https://civarchive.com/models/{model_id}?modelVersionId={version_id}"

            downloader = await get_downloader()
            session = await downloader.session
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                html_content = await response.text()
                
            # Parse HTML to extract JSON data
            soup = BeautifulSoup(html_content, 'html.parser')
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
            logger.error(f"Error fetching CivArchive model version {model_id}/{version_id}: {e}")
            return None
        
    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Not supported by CivArchive provider - requires both model_id and version_id"""
        return None, "CivArchive provider requires both model_id and version_id"
        
    async def get_model_metadata(self, model_id: str) -> Tuple[Optional[Dict], int]:
        """Not supported by CivArchive provider"""
        return None, 404

class SQLiteModelMetadataProvider(ModelMetadataProvider):
    """Provider that uses SQLite database for metadata"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        """Find model by hash value from SQLite database"""
        async with aiosqlite.connect(self.db_path) as db:
            # Look up in model_files table to get model_id and version_id
            query = """
                SELECT model_id, version_id 
                FROM model_files 
                WHERE sha256 = ? 
                LIMIT 1
            """
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, (model_hash.upper(),))
            file_row = await cursor.fetchone()
            
            if not file_row:
                return None
                
            # Get version details
            model_id = file_row['model_id']
            version_id = file_row['version_id']
            
            # Build response in the same format as Civitai API
            return await self._get_version_with_model_data(db, model_id, version_id)
            
    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        """Get all versions of a model from SQLite database"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # First check if model exists
            model_query = "SELECT * FROM models WHERE id = ?"
            cursor = await db.execute(model_query, (model_id,))
            model_row = await cursor.fetchone()
            
            if not model_row:
                return None
                
            model_data = json.loads(model_row['data'])
            model_type = model_row['type']
            model_name = model_row['name']
            
            # Get all versions for this model
            versions_query = """
                SELECT id, name, base_model, data, position, published_at
                FROM model_versions
                WHERE model_id = ?
                ORDER BY position ASC
            """
            cursor = await db.execute(versions_query, (model_id,))
            version_rows = await cursor.fetchall()
            
            if not version_rows:
                return {'modelVersions': [], 'type': model_type}
                
            # Format versions similar to Civitai API
            model_versions = []
            for row in version_rows:
                version_data = json.loads(row['data'])
                # Add fields from the row to ensure we have the basic fields
                version_entry = {
                    'id': row['id'],
                    'modelId': int(model_id),
                    'name': row['name'],
                    'baseModel': row['base_model'],
                    'model': {
                        'name': model_row['name'],
                        'type': model_type,
                    },
                    'source': 'archive_db'
                }
                # Update with any additional data
                version_entry.update(version_data)
                model_versions.append(version_entry)
                
            return {
                'modelVersions': model_versions,
                'type': model_type,
                'name': model_name
            }
    
    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        """Get specific model version with additional metadata from SQLite database"""
        if not model_id and not version_id:
            return None
            
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Case 1: Only version_id is provided
            if model_id is None and version_id is not None:
                # First get the version info to extract model_id
                version_query = "SELECT model_id FROM model_versions WHERE id = ?"
                cursor = await db.execute(version_query, (version_id,))
                version_row = await cursor.fetchone()
                
                if not version_row:
                    return None
                    
                model_id = version_row['model_id']
            
            # Case 2: model_id is provided but version_id is not
            elif model_id is not None and version_id is None:
                # Find the latest version
                version_query = """
                    SELECT id FROM model_versions 
                    WHERE model_id = ? 
                    ORDER BY position ASC
                    LIMIT 1
                """
                cursor = await db.execute(version_query, (model_id,))
                version_row = await cursor.fetchone()
                
                if not version_row:
                    return None
                    
                version_id = version_row['id']
            
            # Now we have both model_id and version_id, get the full data
            return await self._get_version_with_model_data(db, model_id, version_id)
    
    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch model version metadata from SQLite database"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get version details
            version_query = "SELECT model_id FROM model_versions WHERE id = ?"
            cursor = await db.execute(version_query, (version_id,))
            version_row = await cursor.fetchone()
            
            if not version_row:
                return None, "Model version not found"
                
            model_id = version_row['model_id']
            
            # Build complete version data with model info
            version_data = await self._get_version_with_model_data(db, model_id, version_id)
            return version_data, None
    
    async def get_model_metadata(self, model_id: str) -> Tuple[Optional[Dict], int]:
        """Fetch model metadata from SQLite database"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get model details
            model_query = "SELECT name, type, data, username FROM models WHERE id = ?"
            cursor = await db.execute(model_query, (model_id,))
            model_row = await cursor.fetchone()
            
            if not model_row:
                return None, 404
                
            # Parse data JSON
            try:
                model_data = json.loads(model_row['data'])
                
                # Extract relevant metadata
                metadata = {
                    "description": model_data.get("description", "No model description available"),
                    "tags": model_data.get("tags", []),
                    "creator": {
                        "username": model_row['username'] or model_data.get("creator", {}).get("username"),
                        "image": model_data.get("creator", {}).get("image")
                    }
                }
                
                return metadata, 200
            except json.JSONDecodeError:
                return None, 500
    
    async def _get_version_with_model_data(self, db, model_id, version_id) -> Optional[Dict]:
        """Helper to build version data with model information"""
        # Get version details
        version_query = "SELECT name, base_model, data FROM model_versions WHERE id = ? AND model_id = ?"
        cursor = await db.execute(version_query, (version_id, model_id))
        version_row = await cursor.fetchone()
        
        if not version_row:
            return None
            
        # Get model details
        model_query = "SELECT name, type, data, username FROM models WHERE id = ?"
        cursor = await db.execute(model_query, (model_id,))
        model_row = await cursor.fetchone()
        
        if not model_row:
            return None
            
        # Parse JSON data
        try:
            version_data = json.loads(version_row['data'])
            model_data = json.loads(model_row['data'])
            
            # Build response
            result = {
                "id": int(version_id),
                "modelId": int(model_id),
                "name": version_row['name'],
                "baseModel": version_row['base_model'],
                "model": {
                    "name": model_row['name'],
                    "description": model_data.get("description"),
                    "type": model_row['type'],
                    "tags": model_data.get("tags", [])
                },
                "creator": {
                    "username": model_row['username'] or model_data.get("creator", {}).get("username"),
                    "image": model_data.get("creator", {}).get("image")
                },
                "source": "archive_db"
            }
            
            # Add any additional fields from version data
            result.update(version_data)
            
            return result
        except json.JSONDecodeError:
            return None
        
class FallbackMetadataProvider(ModelMetadataProvider):
    """Try providers in order, return first successful result."""
    def __init__(self, providers: list):
        self.providers = providers

    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        for provider in self.providers:
            try:
                result = await provider.get_model_by_hash(model_hash)
                if result:
                    return result
            except Exception:
                continue
        return None

    async def get_model_versions(self, model_id: str) -> Optional[Dict]:
        for provider in self.providers:
            try:
                result = await provider.get_model_versions(model_id)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Provider failed for get_model_versions: {e}")
                continue
        return None

    async def get_model_version(self, model_id: int = None, version_id: int = None) -> Optional[Dict]:
        for provider in self.providers:
            try:
                result = await provider.get_model_version(model_id, version_id)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Provider failed for get_model_version: {e}")
                continue
        return None

    async def get_model_version_info(self, version_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        for provider in self.providers:
            try:
                result, error = await provider.get_model_version_info(version_id)
                if result:
                    return result, error
            except Exception as e:
                logger.debug(f"Provider failed for get_model_version_info: {e}")
                continue
        return None, "No provider could retrieve the data"

    async def get_model_metadata(self, model_id: str) -> Tuple[Optional[Dict], int]:
        for provider in self.providers:
            try:
                result, status = await provider.get_model_metadata(model_id)
                if result:
                    return result, status
            except Exception as e:
                logger.debug(f"Provider failed for get_model_metadata: {e}")
                continue
        return None, 404

class ModelMetadataProviderManager:
    """Manager for selecting and using model metadata providers"""
    
    _instance = None
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance of ModelMetadataProviderManager"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self.providers = {}
        self.default_provider = None
        
    def register_provider(self, name: str, provider: ModelMetadataProvider, is_default: bool = False):
        """Register a metadata provider"""
        self.providers[name] = provider
        if is_default or self.default_provider is None:
            self.default_provider = name
            
    async def get_model_by_hash(self, model_hash: str, provider_name: str = None) -> Optional[Dict]:
        """Find model by hash using specified or default provider"""
        provider = self._get_provider(provider_name)
        return await provider.get_model_by_hash(model_hash)
        
    async def get_model_versions(self, model_id: str, provider_name: str = None) -> Optional[Dict]:
        """Get model versions using specified or default provider"""
        provider = self._get_provider(provider_name)
        return await provider.get_model_versions(model_id)
        
    async def get_model_version(self, model_id: int = None, version_id: int = None, provider_name: str = None) -> Optional[Dict]:
        """Get specific model version using specified or default provider"""
        provider = self._get_provider(provider_name)
        return await provider.get_model_version(model_id, version_id)
        
    async def get_model_version_info(self, version_id: str, provider_name: str = None) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch model version info using specified or default provider"""
        provider = self._get_provider(provider_name)
        return await provider.get_model_version_info(version_id)
        
    async def get_model_metadata(self, model_id: str, provider_name: str = None) -> Tuple[Optional[Dict], int]:
        """Fetch model metadata using specified or default provider"""
        provider = self._get_provider(provider_name)
        return await provider.get_model_metadata(model_id)
        
    def _get_provider(self, provider_name: str = None) -> ModelMetadataProvider:
        """Get provider by name or default provider"""
        if provider_name and provider_name in self.providers:
            return self.providers[provider_name]
        
        if self.default_provider is None:
            raise ValueError("No default provider set and no valid provider specified")
            
        return self.providers[self.default_provider]
