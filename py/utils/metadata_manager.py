from datetime import datetime
import os
import json
import logging
from typing import Any, Dict, Optional, Type, Union

from .models import BaseModelMetadata, LoraMetadata
from .file_utils import normalize_path, find_preview_file, calculate_sha256
from .lora_metadata import extract_lora_metadata, extract_checkpoint_metadata

logger = logging.getLogger(__name__)

class MetadataManager:
    """
    Centralized manager for all metadata operations.
    
    This class is responsible for:
    1. Loading metadata safely with fallback mechanisms
    2. Saving metadata with atomic operations
    3. Creating default metadata for models
    4. Handling unknown fields gracefully
    """
    
    @staticmethod
    async def load_metadata(file_path: str, model_class: Type[BaseModelMetadata] = LoraMetadata) -> Optional[BaseModelMetadata]:
        """
        Load metadata safely.
        
        Returns:
            tuple: (metadata, should_skip)
            - metadata: BaseModelMetadata instance or None
            - should_skip: True if corrupted metadata file exists and model should be skipped
        """
        metadata_path = f"{os.path.splitext(file_path)[0]}.metadata.json"
        
        # Check if metadata file exists
        if not os.path.exists(metadata_path):
            return None, False
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Create model instance
            metadata = model_class.from_dict(data)
                
            # Normalize paths
            await MetadataManager._normalize_metadata_paths(metadata, file_path)
            
            return metadata, False
            
        except (json.JSONDecodeError, Exception) as e:
            error_type = "Invalid JSON" if isinstance(e, json.JSONDecodeError) else "Parse error"
            logger.error(f"{error_type} in metadata file: {metadata_path}. Error: {str(e)}. Skipping model to preserve existing data.")
            return None, True  # should_skip = True

    @staticmethod
    async def load_metadata_payload(file_path: str) -> Dict:
        """
        Load metadata and return it as a dictionary, including any unknown fields.
        Falls back to reading the raw JSON file if parsing into a model class fails.
        """

        payload: Dict = {}
        metadata_obj, should_skip = await MetadataManager.load_metadata(file_path)

        if metadata_obj:
            payload = metadata_obj.to_dict()
            unknown_fields = getattr(metadata_obj, "_unknown_fields", None)
            if isinstance(unknown_fields, dict):
                payload.update(unknown_fields)
        else:
            if not should_skip:
                metadata_path = (
                    file_path
                    if file_path.endswith(".metadata.json")
                    else f"{os.path.splitext(file_path)[0]}.metadata.json"
                )
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as handle:
                            raw = json.load(handle)
                        if isinstance(raw, dict):
                            payload = raw
                    except json.JSONDecodeError:
                        logger.warning(
                            "Failed to parse metadata file %s while loading payload",
                            metadata_path,
                        )
                    except Exception as exc:  # pragma: no cover - defensive logging
                        logger.warning("Failed to read metadata file %s: %s", metadata_path, exc)

        if not isinstance(payload, dict):
            payload = {}

        if file_path:
            payload.setdefault("file_path", normalize_path(file_path))

        return payload

    @staticmethod
    async def hydrate_model_data(model_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Replace the provided model data with the authoritative payload from disk.
        Preserves the cached folder entry if present.
        """

        file_path = model_data.get("file_path")
        if not file_path:
            return model_data

        folder = model_data.get("folder")
        payload = await MetadataManager.load_metadata_payload(file_path)
        if folder is not None:
            payload["folder"] = folder

        model_data.clear()
        model_data.update(payload)
        return model_data
    
    @staticmethod
    async def save_metadata(path: str, metadata: Union[BaseModelMetadata, Dict]) -> bool:
        """
        Save metadata with atomic write operations.
        
        Args:
          path: Path to the model file or directly to the metadata file
          metadata: Metadata to save (either BaseModelMetadata object or dict)
          
        Returns:
          bool: Success or failure
        """
        # Determine if the input is a metadata path or a model file path
        if path.endswith('.metadata.json'):
            metadata_path = path
        else:
            # Use existing logic for model file paths
            file_path = path
            metadata_path = f"{os.path.splitext(file_path)[0]}.metadata.json"
        temp_path = f"{metadata_path}.tmp"
        
        try:
            # Convert to dict if needed
            if isinstance(metadata, BaseModelMetadata):
                metadata_dict = metadata.to_dict()
                # Preserve unknown fields if present
                if hasattr(metadata, '_unknown_fields'):
                    metadata_dict.update(metadata._unknown_fields)
            else:
                metadata_dict = metadata.copy()
            
            # Normalize paths
            if 'file_path' in metadata_dict:
                metadata_dict['file_path'] = normalize_path(metadata_dict['file_path'])
            if 'preview_url' in metadata_dict:
                metadata_dict['preview_url'] = normalize_path(metadata_dict['preview_url'])
            
            # Write to temporary file first
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
            
            # Atomic rename operation
            os.replace(temp_path, metadata_path)
            return True
            
        except Exception as e:
            logger.error(f"Error saving metadata to {metadata_path}: {str(e)}")
            # Clean up temporary file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            return False
    
    @staticmethod
    async def create_default_metadata(file_path: str, model_class: Type[BaseModelMetadata] = LoraMetadata) -> Optional[BaseModelMetadata]:
        """
        Create basic metadata structure for a model file.
        This replaces the old get_file_info function with a more appropriately named method.
        
        Args:
            file_path: Path to the model file
            model_class: Class to instantiate
            
        Returns:
            BaseModelMetadata instance or None if file doesn't exist
        """
        # First check if file actually exists and resolve symlinks
        try:
            real_path = os.path.realpath(file_path)
            if not os.path.exists(real_path):
                return None
        except Exception as e:
            logger.error(f"Error checking file existence for {file_path}: {e}")
            return None
            
        try:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            dir_path = os.path.dirname(file_path)
            
            # Find preview image
            preview_url = find_preview_file(base_name, dir_path)
            
            # Calculate file hash
            sha256 = await calculate_sha256(real_path)
            
            # Create instance based on model type
            if model_class.__name__ == "CheckpointMetadata":
                metadata = model_class(
                    file_name=base_name,
                    model_name=base_name,
                    file_path=normalize_path(file_path),
                    size=os.path.getsize(real_path),
                    modified=datetime.now().timestamp(),
                    sha256=sha256,
                    base_model="Unknown",
                    preview_url=normalize_path(preview_url),
                    tags=[],
                    modelDescription="",
                    model_type="checkpoint",
                    from_civitai=True
                )
            elif model_class.__name__ == "EmbeddingMetadata":
                metadata = model_class(
                    file_name=base_name,
                    model_name=base_name,
                    file_path=normalize_path(file_path),
                    size=os.path.getsize(real_path),
                    modified=datetime.now().timestamp(),
                    sha256=sha256,
                    base_model="Unknown",
                    preview_url=normalize_path(preview_url),
                    tags=[],
                    modelDescription="",
                    from_civitai=True
                )
            else:  # Default to LoraMetadata
                metadata = model_class(
                    file_name=base_name,
                    model_name=base_name,
                    file_path=normalize_path(file_path),
                    size=os.path.getsize(real_path),
                    modified=datetime.now().timestamp(),
                    sha256=sha256,
                    base_model="Unknown",
                    preview_url=normalize_path(preview_url),
                    tags=[],
                    modelDescription="",
                    from_civitai=True,
                    usage_tips="{}"
                )
            
            # Try to extract model-specific metadata
            # await MetadataManager._enrich_metadata(metadata, real_path)
            
            # Save the created metadata
            await MetadataManager.save_metadata(file_path, metadata)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error creating default metadata for {file_path}: {e}")
            return None
    
    @staticmethod
    async def _enrich_metadata(metadata: BaseModelMetadata, file_path: str) -> None:
        """
        Enrich metadata with model-specific information
        
        Args:
            metadata: Metadata to enrich
            file_path: Path to the model file
        """
        try:
            if metadata.__class__.__name__ == "LoraMetadata":
                model_info = await extract_lora_metadata(file_path)
                metadata.base_model = model_info['base_model']
            
            # elif metadata.__class__.__name__ == "CheckpointMetadata":
            #     model_info = await extract_checkpoint_metadata(file_path)
            #     metadata.base_model = model_info['base_model']
            #     if 'model_type' in model_info:
            #         metadata.model_type = model_info['model_type']
        except Exception as e:
            logger.error(f"Error enriching metadata: {str(e)}")
    
    @staticmethod
    async def _normalize_metadata_paths(metadata: BaseModelMetadata, file_path: str) -> None:
        """
        Normalize paths in metadata object
        
        Args:
            metadata: Metadata object to update
            file_path: Current file path for the model
        """
        need_update = False
        
        # Check if file_name matches the actual file name
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        if metadata.file_name != base_name:
            metadata.file_name = base_name
            need_update = True
        
        # Check if file path is different from what's in metadata
        if normalize_path(file_path) != metadata.file_path:
            metadata.file_path = normalize_path(file_path)
            need_update = True
        
        # Check if preview exists at the current location
        preview_url = metadata.preview_url
        if preview_url:
            # Get directory parts of both paths
            file_dir = os.path.dirname(file_path)
            preview_dir = os.path.dirname(preview_url)
            
            # Update preview if it doesn't exist OR if model and preview are in different directories
            if not os.path.exists(preview_url) or file_dir != preview_dir:
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                dir_path = os.path.dirname(file_path)
                new_preview_url = find_preview_file(base_name, dir_path)
                if new_preview_url:
                    metadata.preview_url = normalize_path(new_preview_url)
                    need_update = True
        
        # If path attributes were changed, save the metadata back to disk
        if need_update:
            await MetadataManager.save_metadata(file_path, metadata)
