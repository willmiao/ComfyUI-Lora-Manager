import asyncio
import os
import logging
from typing import List, Dict, Optional, Any, Set
from abc import ABC, abstractmethod

from ..utils.utils import calculate_relative_path_for_model, remove_empty_dirs
from ..utils.constants import AUTO_ORGANIZE_BATCH_SIZE
from ..services.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


class ProgressCallback(ABC):
    """Abstract callback interface for progress reporting"""
    
    @abstractmethod
    async def on_progress(self, progress_data: Dict[str, Any]) -> None:
        """Called when progress is updated"""
        pass


class AutoOrganizeResult:
    """Result object for auto-organize operations"""
    
    def __init__(self):
        self.total: int = 0
        self.processed: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.skipped_count: int = 0
        self.operation_type: str = 'unknown'
        self.cleanup_counts: Dict[str, int] = {}
        self.results: List[Dict[str, Any]] = []
        self.results_truncated: bool = False
        self.sample_results: List[Dict[str, Any]] = []
        self.is_flat_structure: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        result = {
            'success': True,
            'message': f'Auto-organize {self.operation_type} completed: {self.success_count} moved, {self.skipped_count} skipped, {self.failure_count} failed out of {self.total} total',
            'summary': {
                'total': self.total,
                'success': self.success_count,
                'skipped': self.skipped_count,
                'failures': self.failure_count,
                'organization_type': 'flat' if self.is_flat_structure else 'structured',
                'cleaned_dirs': self.cleanup_counts,
                'operation_type': self.operation_type
            }
        }
        
        if self.results_truncated:
            result['results_truncated'] = True
            result['sample_results'] = self.sample_results
        else:
            result['results'] = self.results
        
        return result


class ModelFileService:
    """Service for handling model file operations and organization"""
    
    def __init__(self, scanner, model_type: str):
        """Initialize the service
        
        Args:
            scanner: Model scanner instance
            model_type: Type of model (e.g., 'lora', 'checkpoint')
        """
        self.scanner = scanner
        self.model_type = model_type
    
    def get_model_roots(self) -> List[str]:
        """Get model root directories"""
        return self.scanner.get_model_roots()
    
    async def auto_organize_models(
        self, 
        file_paths: Optional[List[str]] = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> AutoOrganizeResult:
        """Auto-organize models based on current settings
        
        Args:
            file_paths: Optional list of specific file paths to organize. 
                       If None, organizes all models.
            progress_callback: Optional callback for progress updates
            
        Returns:
            AutoOrganizeResult object with operation results
        """
        result = AutoOrganizeResult()
        source_directories: Set[str] = set()
        
        try:
            # Get all models from cache
            cache = await self.scanner.get_cached_data()
            all_models = cache.raw_data
            
            # Filter models if specific file paths are provided
            if file_paths:
                all_models = [model for model in all_models if model.get('file_path') in file_paths]
                result.operation_type = 'bulk'
            else:
                result.operation_type = 'all'
            
            # Get model roots for this scanner
            model_roots = self.get_model_roots()
            if not model_roots:
                raise ValueError('No model roots configured')
            
            # Check if flat structure is configured for this model type
            settings_manager = get_settings_manager()
            path_template = settings_manager.get_download_path_template(self.model_type)
            result.is_flat_structure = not path_template
            
            # Initialize tracking
            result.total = len(all_models)
            
            # Send initial progress
            if progress_callback:
                await progress_callback.on_progress({
                    'type': 'auto_organize_progress',
                    'status': 'started',
                    'total': result.total,
                    'processed': 0,
                    'success': 0,
                    'failures': 0,
                    'skipped': 0,
                    'operation_type': result.operation_type
                })
            
            # Process models in batches
            await self._process_models_in_batches(
                all_models, 
                model_roots, 
                result, 
                progress_callback,
                source_directories  # Pass the set to track source directories
            )
            
            # Send cleanup progress
            if progress_callback:
                await progress_callback.on_progress({
                    'type': 'auto_organize_progress',
                    'status': 'cleaning',
                    'total': result.total,
                    'processed': result.processed,
                    'success': result.success_count,
                    'failures': result.failure_count,
                    'skipped': result.skipped_count,
                    'message': 'Cleaning up empty directories...',
                    'operation_type': result.operation_type
                })
            
            # Clean up empty directories - only in affected directories for bulk operations
            cleanup_paths = list(source_directories) if result.operation_type == 'bulk' else model_roots
            result.cleanup_counts = await self._cleanup_empty_directories(cleanup_paths)
            
            # Send completion message
            if progress_callback:
                await progress_callback.on_progress({
                    'type': 'auto_organize_progress',
                    'status': 'completed',
                    'total': result.total,
                    'processed': result.processed,
                    'success': result.success_count,
                    'failures': result.failure_count,
                    'skipped': result.skipped_count,
                    'cleanup': result.cleanup_counts,
                    'operation_type': result.operation_type
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in auto_organize_models: {e}", exc_info=True)
            
            # Send error message
            if progress_callback:
                await progress_callback.on_progress({
                    'type': 'auto_organize_progress',
                    'status': 'error',
                    'error': str(e),
                    'operation_type': result.operation_type
                })
            
            raise e
    
    async def _process_models_in_batches(
        self, 
        all_models: List[Dict[str, Any]], 
        model_roots: List[str], 
        result: AutoOrganizeResult,
        progress_callback: Optional[ProgressCallback],
        source_directories: Optional[Set[str]] = None
    ) -> None:
        """Process models in batches to avoid overwhelming the system"""
        
        for i in range(0, result.total, AUTO_ORGANIZE_BATCH_SIZE):
            batch = all_models[i:i + AUTO_ORGANIZE_BATCH_SIZE]
            
            for model in batch:
                await self._process_single_model(model, model_roots, result, source_directories)
                result.processed += 1
            
            # Send progress update after each batch
            if progress_callback:
                await progress_callback.on_progress({
                    'type': 'auto_organize_progress',
                    'status': 'processing',
                    'total': result.total,
                    'processed': result.processed,
                    'success': result.success_count,
                    'failures': result.failure_count,
                    'skipped': result.skipped_count,
                    'operation_type': result.operation_type
                })
            
            # Small delay between batches
            await asyncio.sleep(0.1)
    
    async def _process_single_model(
        self, 
        model: Dict[str, Any], 
        model_roots: List[str], 
        result: AutoOrganizeResult,
        source_directories: Optional[Set[str]] = None
    ) -> None:
        """Process a single model for organization"""
        try:
            file_path = model.get('file_path')
            model_name = model.get('model_name', 'Unknown')
            
            if not file_path:
                self._add_result(result, model_name, False, "No file path found")
                result.failure_count += 1
                return
            
            # Find which model root this file belongs to
            current_root = self._find_model_root(file_path, model_roots)
            if not current_root:
                self._add_result(result, model_name, False, 
                               "Model file not found in any configured root directory")
                result.failure_count += 1
                return
            
            # Determine target directory
            target_dir = await self._calculate_target_directory(
                model, current_root, result.is_flat_structure
            )
            
            if target_dir is None:
                self._add_result(result, model_name, False, 
                               "Skipped - insufficient metadata for organization")
                result.skipped_count += 1
                return
            
            current_dir = os.path.dirname(file_path)
            
            # Skip if already in correct location
            if current_dir.replace(os.sep, '/') == target_dir.replace(os.sep, '/'):
                result.skipped_count += 1
                return
            
            # Check for conflicts
            file_name = os.path.basename(file_path)
            target_file_path = os.path.join(target_dir, file_name)
            
            if os.path.exists(target_file_path):
                self._add_result(result, model_name, False, 
                               f"Target file already exists: {target_file_path}")
                result.failure_count += 1
                return
            
            # Store the source directory for potential cleanup
            if source_directories is not None:
                source_directories.add(current_dir)
            
            # Perform the move
            success = await self.scanner.move_model(file_path, target_dir)
            
            if success:
                result.success_count += 1
            else:
                self._add_result(result, model_name, False, "Failed to move model")
                result.failure_count += 1
            
        except Exception as e:
            logger.error(f"Error processing model {model.get('model_name', 'Unknown')}: {e}", exc_info=True)
            self._add_result(result, model.get('model_name', 'Unknown'), False, f"Error: {str(e)}")
            result.failure_count += 1
    
    def _find_model_root(self, file_path: str, model_roots: List[str]) -> Optional[str]:
        """Find which model root the file belongs to"""
        for root in model_roots:
            # Normalize paths for comparison
            normalized_root = os.path.normpath(root).replace(os.sep, '/')
            normalized_file = os.path.normpath(file_path).replace(os.sep, '/')
            
            if normalized_file.startswith(normalized_root):
                return root
        return None
    
    async def _calculate_target_directory(
        self, 
        model: Dict[str, Any], 
        current_root: str, 
        is_flat_structure: bool
    ) -> Optional[str]:
        """Calculate the target directory for a model"""
        if is_flat_structure:
            file_path = model.get('file_path')
            current_dir = os.path.dirname(file_path)
            
            # Check if already in root directory
            if os.path.normpath(current_dir) == os.path.normpath(current_root):
                return None  # Signal to skip
            
            return current_root
        else:
            # Calculate new relative path based on settings
            new_relative_path = calculate_relative_path_for_model(model, self.model_type)
            
            if not new_relative_path:
                return None  # Signal to skip
            
            return os.path.join(current_root, new_relative_path).replace(os.sep, '/')
    
    def _add_result(
        self, 
        result: AutoOrganizeResult, 
        model_name: str, 
        success: bool, 
        message: str
    ) -> None:
        """Add a result entry if under the limit"""
        if len(result.results) < 100:  # Limit detailed results
            result.results.append({
                "model": model_name,
                "success": success,
                "message": message
            })
        elif len(result.results) == 100:
            # Mark as truncated and save sample
            result.results_truncated = True
            result.sample_results = result.results[:50]
    
    async def _cleanup_empty_directories(self, paths: List[str]) -> Dict[str, int]:
        """Clean up empty directories after organizing
        
        Args:
            paths: List of paths to check for empty directories
            
        Returns:
            Dictionary with counts of removed directories by root path
        """
        cleanup_counts = {}
        for path in paths:
            removed = remove_empty_dirs(path)
            cleanup_counts[path] = removed
        return cleanup_counts


class ModelMoveService:
    """Service for handling individual model moves"""
    
    def __init__(self, scanner):
        """Initialize the service
        
        Args:
            scanner: Model scanner instance
        """
        self.scanner = scanner
    
    async def move_model(self, file_path: str, target_path: str) -> Dict[str, Any]:
        """Move a single model file
        
        Args:
            file_path: Source file path
            target_path: Target directory path
            
        Returns:
            Dictionary with move result
        """
        try:
            source_dir = os.path.dirname(file_path)
            if os.path.normpath(source_dir) == os.path.normpath(target_path):
                logger.info(f"Source and target directories are the same: {source_dir}")
                return {
                    'success': True, 
                    'message': 'Source and target directories are the same',
                    'original_file_path': file_path,
                    'new_file_path': file_path
                }

            new_file_path = await self.scanner.move_model(file_path, target_path)
            if new_file_path:
                return {
                    'success': True, 
                    'original_file_path': file_path,
                    'new_file_path': new_file_path
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to move model',
                    'original_file_path': file_path,
                    'new_file_path': None
                }
        except Exception as e:
            logger.error(f"Error moving model: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'original_file_path': file_path,
                'new_file_path': None
            }
    
    async def move_models_bulk(self, file_paths: List[str], target_path: str) -> Dict[str, Any]:
        """Move multiple model files
        
        Args:
            file_paths: List of source file paths
            target_path: Target directory path
            
        Returns:
            Dictionary with bulk move results
        """
        try:
            results = []
            
            for file_path in file_paths:
                result = await self.move_model(file_path, target_path)
                results.append({
                    "original_file_path": file_path,
                    "new_file_path": result.get('new_file_path'),
                    "success": result['success'],
                    "message": result.get('message', result.get('error', 'Unknown'))
                })
            
            success_count = sum(1 for r in results if r["success"])
            failure_count = len(results) - success_count
            
            return {
                'success': True,
                'message': f'Moved {success_count} of {len(file_paths)} models',
                'results': results,
                'success_count': success_count,
                'failure_count': failure_count
            }
        except Exception as e:
            logger.error(f"Error moving models in bulk: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'results': [],
                'success_count': 0,
                'failure_count': len(file_paths)
            }