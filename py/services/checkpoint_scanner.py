import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.models import CheckpointMetadata
from ..utils.file_utils import find_preview_file, normalize_path
from ..utils.metadata_manager import MetadataManager
from ..config import config
from .model_scanner import ModelScanner
from .model_hash_index import ModelHashIndex

logger = logging.getLogger(__name__)

class CheckpointScanner(ModelScanner):
    """Service for scanning and managing checkpoint files"""
    
    def __init__(self):
        # Define supported file extensions
        file_extensions = {'.ckpt', '.pt', '.pt2', '.bin', '.pth', '.safetensors', '.pkl', '.sft', '.gguf'}
        super().__init__(
            model_type="checkpoint",
            model_class=CheckpointMetadata,
            file_extensions=file_extensions,
            hash_index=ModelHashIndex()
        )

    async def _create_default_metadata(self, file_path: str) -> Optional[CheckpointMetadata]:
        """Create default metadata for checkpoint without calculating hash (lazy hash).
        
        Checkpoints are typically large (10GB+), so we skip hash calculation during initial
        scanning to improve startup performance. Hash will be calculated on-demand when
        fetching metadata from Civitai.
        """
        try:
            real_path = os.path.realpath(file_path)
            if not os.path.exists(real_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            dir_path = os.path.dirname(file_path)
            
            # Find preview image
            preview_url = find_preview_file(base_name, dir_path)
            
            # Create metadata WITHOUT calculating hash
            metadata = CheckpointMetadata(
                file_name=base_name,
                model_name=base_name,
                file_path=normalize_path(file_path),
                size=os.path.getsize(real_path),
                modified=datetime.now().timestamp(),
                sha256="",  # Empty hash - will be calculated on-demand
                base_model="Unknown",
                preview_url=normalize_path(preview_url),
                tags=[],
                modelDescription="",
                sub_type="checkpoint",
                from_civitai=False,  # Mark as local model since no hash yet
                hash_status="pending"  # Mark hash as pending
            )
            
            # Save the created metadata
            logger.info(f"Creating checkpoint metadata (hash pending) for {file_path}")
            await MetadataManager.save_metadata(file_path, metadata)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error creating default checkpoint metadata for {file_path}: {e}")
            return None

    async def calculate_hash_for_model(self, file_path: str) -> Optional[str]:
        """Calculate hash for a checkpoint on-demand.
        
        Args:
            file_path: Path to the model file
            
        Returns:
            SHA256 hash string, or None if calculation failed
        """
        from ..utils.file_utils import calculate_sha256
        
        try:
            real_path = os.path.realpath(file_path)
            if not os.path.exists(real_path):
                logger.error(f"File not found for hash calculation: {file_path}")
                return None
            
            # Load current metadata
            metadata, _ = await MetadataManager.load_metadata(file_path, self.model_class)
            if metadata is None:
                logger.error(f"No metadata found for {file_path}")
                return None
            
            # Check if hash is already calculated
            if metadata.hash_status == "completed" and metadata.sha256:
                return metadata.sha256
            
            # Update status to calculating
            metadata.hash_status = "calculating"
            await MetadataManager.save_metadata(file_path, metadata)
            
            # Calculate hash
            logger.info(f"Calculating hash for checkpoint: {file_path}")
            sha256 = await calculate_sha256(real_path)
            
            # Update metadata with hash
            metadata.sha256 = sha256
            metadata.hash_status = "completed"
            await MetadataManager.save_metadata(file_path, metadata)
            
            # Update hash index
            self._hash_index.add_entry(sha256.lower(), file_path)
            
            logger.info(f"Hash calculated for checkpoint: {file_path}")
            return sha256
            
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            # Update status to failed
            try:
                metadata, _ = await MetadataManager.load_metadata(file_path, self.model_class)
                if metadata:
                    metadata.hash_status = "failed"
                    await MetadataManager.save_metadata(file_path, metadata)
            except Exception:
                pass
            return None

    async def calculate_all_pending_hashes(self, progress_callback=None) -> Dict[str, int]:
        """Calculate hashes for all checkpoints with pending hash status.
        
        If cache is not initialized, scans filesystem directly for metadata files
        with hash_status != 'completed'.
        
        Args:
            progress_callback: Optional callback(progress, total, current_file)
            
        Returns:
            Dict with 'completed', 'failed', 'total' counts
        """
        # Try to get from cache first
        cache = await self.get_cached_data()
        
        if cache and cache.raw_data:
            # Use cache if available
            pending_models = [
                item for item in cache.raw_data 
                if item.get('hash_status') != 'completed' or not item.get('sha256')
            ]
        else:
            # Cache not initialized, scan filesystem directly
            pending_models = await self._find_pending_models_from_filesystem()
        
        if not pending_models:
            return {'completed': 0, 'failed': 0, 'total': 0}
        
        total = len(pending_models)
        completed = 0
        failed = 0
        
        for i, model_data in enumerate(pending_models):
            file_path = model_data.get('file_path')
            if not file_path:
                continue
            
            try:
                sha256 = await self.calculate_hash_for_model(file_path)
                if sha256:
                    completed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Error calculating hash for {file_path}: {e}")
                failed += 1
            
            if progress_callback:
                try:
                    await progress_callback(i + 1, total, file_path)
                except Exception:
                    pass
        
        return {
            'completed': completed,
            'failed': failed,
            'total': total
        }
    
    async def _find_pending_models_from_filesystem(self) -> List[Dict[str, Any]]:
        """Scan filesystem for checkpoint metadata files with pending hash status."""
        pending_models = []
        
        for root_path in self.get_model_roots():
            if not os.path.exists(root_path):
                continue
            
            for dirpath, _dirnames, filenames in os.walk(root_path):
                for filename in filenames:
                    if not filename.endswith('.metadata.json'):
                        continue
                    
                    metadata_path = os.path.join(dirpath, filename)
                    try:
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Check if hash is pending
                        hash_status = data.get('hash_status', 'completed')
                        sha256 = data.get('sha256', '')
                        
                        if hash_status != 'completed' or not sha256:
                            # Find corresponding model file
                            model_name = filename.replace('.metadata.json', '')
                            model_path = None
                            
                            # Look for model file with matching name
                            for ext in self.file_extensions:
                                potential_path = os.path.join(dirpath, model_name + ext)
                                if os.path.exists(potential_path):
                                    model_path = potential_path
                                    break
                            
                            if model_path:
                                pending_models.append({
                                    'file_path': model_path.replace(os.sep, '/'),
                                    'hash_status': hash_status,
                                    'sha256': sha256,
                                    **{k: v for k, v in data.items() if k not in ['file_path', 'hash_status', 'sha256']}
                                })
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Error reading metadata file {metadata_path}: {e}")
                        continue
        
        return pending_models

    def _resolve_sub_type(self, root_path: Optional[str]) -> Optional[str]:
        """Resolve the sub-type based on the root path."""
        if not root_path:
            return None

        if config.checkpoints_roots and root_path in config.checkpoints_roots:
            return "checkpoint"

        if config.unet_roots and root_path in config.unet_roots:
            return "diffusion_model"

        return None

    def adjust_metadata(self, metadata, file_path, root_path):
        """Adjust metadata during scanning to set sub_type."""
        sub_type = self._resolve_sub_type(root_path)
        if sub_type:
            metadata.sub_type = sub_type
        return metadata

    def adjust_cached_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust entries loaded from the persisted cache to ensure sub_type is set."""
        sub_type = self._resolve_sub_type(
            self._find_root_for_file(entry.get("file_path"))
        )
        if sub_type:
            entry["sub_type"] = sub_type
        return entry

    def get_model_roots(self) -> List[str]:
        """Get checkpoint root directories (including extra paths)"""
        roots: List[str] = []
        roots.extend(config.base_models_roots or [])
        roots.extend(config.extra_checkpoints_roots or [])
        roots.extend(config.extra_unet_roots or [])
        # Remove duplicates while preserving order
        seen: set = set()
        unique_roots: List[str] = []
        for root in roots:
            if root not in seen:
                seen.add(root)
                unique_roots.append(root)
        return unique_roots
