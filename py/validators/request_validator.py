import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field
        self.message = message


class RequestValidator:
    """Request validation class for model operations"""
    
    @staticmethod
    def validate_delete_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate model deletion request
        
        Args:
            data: Request data dictionary
            
        Returns:
            Dict: Validated data
            
        Raises:
            ValidationError: If validation fails
        """
        if not data.get('file_path'):
            raise ValidationError('Model path is required', 'file_path')
        
        file_path = data['file_path'].strip()
        if not file_path:
            raise ValidationError('Model path cannot be empty', 'file_path')
        
        # Validate file path format
        try:
            Path(file_path)
        except ValueError as e:
            raise ValidationError(f'Invalid file path format: {e}', 'file_path')
        
        return {
            'file_path': file_path
        }
    
    @staticmethod
    def validate_fetch_civitai_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate CivitAI fetch request
        
        Args:
            data: Request data dictionary
            
        Returns:
            Dict: Validated data
            
        Raises:
            ValidationError: If validation fails
        """
        if not data.get('sha256'):
            raise ValidationError('SHA256 hash is required', 'sha256')
        
        sha256 = data['sha256'].strip().lower()
        if not sha256:
            raise ValidationError('SHA256 hash cannot be empty', 'sha256')
        
        # Validate SHA256 format (64 hex characters)
        if len(sha256) != 64 or not all(c in '0123456789abcdef' for c in sha256):
            raise ValidationError('Invalid SHA256 hash format', 'sha256')
        
        return {
            'sha256': sha256,
            'file_path': data.get('file_path', '').strip()
        }
    
    @staticmethod
    def validate_replace_preview_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate preview replacement request
        
        Args:
            data: Request data dictionary
            
        Returns:
            Dict: Validated data
            
        Raises:
            ValidationError: If validation fails
        """
        if not data.get('file_path'):
            raise ValidationError('Model file path is required', 'file_path')
        
        if not data.get('preview_data'):
            raise ValidationError('Preview data is required', 'preview_data')
        
        file_path = data['file_path'].strip()
        preview_data = data['preview_data'].strip()
        
        if not file_path:
            raise ValidationError('Model file path cannot be empty', 'file_path')
        
        if not preview_data:
            raise ValidationError('Preview data cannot be empty', 'preview_data')
        
        # Validate preview data format (should be base64 data URL or HTTP URL)
        if not (preview_data.startswith('data:image/') or 
                preview_data.startswith('http://') or 
                preview_data.startswith('https://')):
            raise ValidationError('Invalid preview data format', 'preview_data')
        
        return {
            'file_path': file_path,
            'preview_data': preview_data,
            'nsfw_level': data.get('nsfw_level', '').strip() or None
        }
    
    @staticmethod
    def validate_exclude_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate model exclusion request
        
        Args:
            data: Request data dictionary
            
        Returns:
            Dict: Validated data
            
        Raises:
            ValidationError: If validation fails
        """
        if not data.get('file_path'):
            raise ValidationError('Model file path is required', 'file_path')
        
        file_path = data['file_path'].strip()
        if not file_path:
            raise ValidationError('Model file path cannot be empty', 'file_path')
        
        return {
            'file_path': file_path
        }
    
    @staticmethod
    def validate_bulk_delete_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate bulk deletion request
        
        Args:
            data: Request data dictionary
            
        Returns:
            Dict: Validated data
            
        Raises:
            ValidationError: If validation fails
        """
        if not data.get('file_paths'):
            raise ValidationError('File paths list is required', 'file_paths')
        
        file_paths = data['file_paths']
        if not isinstance(file_paths, list):
            raise ValidationError('File paths must be a list', 'file_paths')
        
        if not file_paths:
            raise ValidationError('File paths list cannot be empty', 'file_paths')
        
        # Validate each file path
        validated_paths = []
        for i, path in enumerate(file_paths):
            if not isinstance(path, str):
                raise ValidationError(f'File path at index {i} must be a string', 'file_paths')
            
            path = path.strip()
            if not path:
                raise ValidationError(f'File path at index {i} cannot be empty', 'file_paths')
            
            validated_paths.append(path)
        
        return {
            'file_paths': validated_paths
        }
    
    @staticmethod
    def validate_rename_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate model rename request
        
        Args:
            data: Request data dictionary
            
        Returns:
            Dict: Validated data
            
        Raises:
            ValidationError: If validation fails
        """
        if not data.get('file_path'):
            raise ValidationError('Model file path is required', 'file_path')
        
        if not data.get('new_name'):
            raise ValidationError('New name is required', 'new_name')
        
        file_path = data['file_path'].strip()
        new_name = data['new_name'].strip()
        
        if not file_path:
            raise ValidationError('Model file path cannot be empty', 'file_path')
        
        if not new_name:
            raise ValidationError('New name cannot be empty', 'new_name')
        
        # Validate filename characters
        invalid_chars = '<>:"/\\|?*'
        if any(char in new_name for char in invalid_chars):
            raise ValidationError(f'New name contains invalid characters: {invalid_chars}', 'new_name')
        
        return {
            'file_path': file_path,
            'new_name': new_name
        }
    
    @staticmethod
    def validate_add_tags_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate add tags request
        
        Args:
            data: Request data dictionary
            
        Returns:
            Dict: Validated data
            
        Raises:
            ValidationError: If validation fails
        """
        if not data.get('file_path'):
            raise ValidationError('Model file path is required', 'file_path')
        
        if not data.get('tags'):
            raise ValidationError('Tags are required', 'tags')
        
        file_path = data['file_path'].strip()
        tags = data['tags']
        
        if not file_path:
            raise ValidationError('Model file path cannot be empty', 'file_path')
        
        # Validate tags format
        if isinstance(tags, str):
            # Convert comma-separated string to list
            tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
        elif isinstance(tags, list):
            # Validate list items
            validated_tags = []
            for i, tag in enumerate(tags):
                if not isinstance(tag, str):
                    raise ValidationError(f'Tag at index {i} must be a string', 'tags')
                
                tag = tag.strip()
                if tag:
                    validated_tags.append(tag)
            tags = validated_tags
        else:
            raise ValidationError('Tags must be a string or list', 'tags')
        
        if not tags:
            raise ValidationError('At least one tag is required', 'tags')
        
        return {
            'file_path': file_path,
            'tags': tags
        }
    
    @staticmethod
    def validate_pagination_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate pagination parameters
        
        Args:
            params: Query parameters dictionary
            
        Returns:
            Dict: Validated parameters
            
        Raises:
            ValidationError: If validation fails
        """
        try:
            page = int(params.get('page', 1))
            page_size = int(params.get('page_size', 20))
        except (ValueError, TypeError):
            raise ValidationError('Page and page_size must be integers')
        
        if page < 1:
            raise ValidationError('Page must be greater than 0')
        
        if page_size < 1 or page_size > 100:
            raise ValidationError('Page size must be between 1 and 100')
        
        return {
            'page': page,
            'page_size': page_size,
            'sort_by': params.get('sort_by', 'name'),
            'folder': params.get('folder'),
            'search': params.get('search', '').strip() or None,
            'fuzzy_search': params.get('fuzzy_search', 'false').lower() == 'true',
            'favorites_only': params.get('favorites_only', 'false').lower() == 'true'
        }
