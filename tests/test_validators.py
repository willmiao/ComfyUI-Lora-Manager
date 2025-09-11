"""
Unit tests for the request validation system
"""
import pytest
from unittest.mock import Mock

from py.validators.request_validator import RequestValidator, ValidationError


class TestRequestValidator:
    """Unit tests for RequestValidator"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.validator = RequestValidator()
    
    # Delete Request Validation Tests
    def test_validate_delete_request_valid(self):
        """Test valid delete request validation"""
        valid_data = {
            'file_path': '/models/loras/test_model.safetensors'
        }
        
        result = self.validator.validate_delete_request(valid_data)
        
        assert result['file_path'] == '/models/loras/test_model.safetensors'
    
    def test_validate_delete_request_missing_file_path(self):
        """Test delete request validation with missing file_path"""
        invalid_data = {}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_path'
        assert 'required' in exc_info.value.message.lower()
    
    def test_validate_delete_request_empty_file_path(self):
        """Test delete request validation with empty file_path"""
        invalid_data = {'file_path': ''}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_path'
        assert 'empty' in exc_info.value.message.lower()
    
    def test_validate_delete_request_whitespace_only_file_path(self):
        """Test delete request validation with whitespace-only file_path"""
        invalid_data = {'file_path': '   '}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_path'
        assert 'empty' in exc_info.value.message.lower()
    
    # CivitAI Fetch Request Validation Tests
    def test_validate_fetch_civitai_request_valid(self):
        """Test valid CivitAI fetch request validation"""
        valid_data = {
            'sha256': 'a' * 64,  # Valid SHA256
            'file_path': '/models/loras/test_model.safetensors'
        }
        
        result = self.validator.validate_fetch_civitai_request(valid_data)
        
        assert result['sha256'] == 'a' * 64
        assert result['file_path'] == '/models/loras/test_model.safetensors'
    
    def test_validate_fetch_civitai_request_no_file_path(self):
        """Test CivitAI fetch request validation without file_path (optional)"""
        valid_data = {
            'sha256': 'b' * 64
        }
        
        result = self.validator.validate_fetch_civitai_request(valid_data)
        
        assert result['sha256'] == 'b' * 64
        assert result['file_path'] == ''
    
    def test_validate_fetch_civitai_request_missing_sha256(self):
        """Test CivitAI fetch request validation with missing SHA256"""
        invalid_data = {'file_path': '/test/model.safetensors'}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_fetch_civitai_request(invalid_data)
        
        assert exc_info.value.field == 'sha256'
        assert 'required' in exc_info.value.message.lower()
    
    def test_validate_fetch_civitai_request_empty_sha256(self):
        """Test CivitAI fetch request validation with empty SHA256"""
        invalid_data = {'sha256': ''}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_fetch_civitai_request(invalid_data)
        
        assert exc_info.value.field == 'sha256'
        assert 'empty' in exc_info.value.message.lower()
    
    def test_validate_fetch_civitai_request_invalid_sha256_length(self):
        """Test CivitAI fetch request validation with invalid SHA256 length"""
        invalid_data = {'sha256': 'abc123'}  # Too short
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_fetch_civitai_request(invalid_data)
        
        assert exc_info.value.field == 'sha256'
        assert 'format' in exc_info.value.message.lower()
    
    def test_validate_fetch_civitai_request_invalid_sha256_characters(self):
        """Test CivitAI fetch request validation with invalid SHA256 characters"""
        invalid_data = {'sha256': 'g' * 64}  # Contains 'g' which is not hex
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_fetch_civitai_request(invalid_data)
        
        assert exc_info.value.field == 'sha256'
        assert 'format' in exc_info.value.message.lower()
    
    def test_validate_fetch_civitai_request_sha256_case_normalization(self):
        """Test that SHA256 is normalized to lowercase"""
        valid_data = {'sha256': 'A' * 64}  # Uppercase
        
        result = self.validator.validate_fetch_civitai_request(valid_data)
        
        assert result['sha256'] == 'a' * 64  # Should be lowercase
    
    # Preview Replacement Validation Tests
    def test_validate_replace_preview_request_valid_base64(self):
        """Test valid preview replacement with base64 data"""
        valid_data = {
            'file_path': '/models/test.safetensors',
            'preview_data': 'data:image/jpeg;base64,/9j/4AAQSkZJRg...',
            'nsfw_level': 'SFW'
        }
        
        result = self.validator.validate_replace_preview_request(valid_data)
        
        assert result['file_path'] == '/models/test.safetensors'
        assert result['preview_data'] == 'data:image/jpeg;base64,/9j/4AAQSkZJRg...'
        assert result['nsfw_level'] == 'SFW'
    
    def test_validate_replace_preview_request_valid_url(self):
        """Test valid preview replacement with URL"""
        valid_data = {
            'file_path': '/models/test.safetensors',
            'preview_data': 'https://example.com/image.jpg'
        }
        
        result = self.validator.validate_replace_preview_request(valid_data)
        
        assert result['file_path'] == '/models/test.safetensors'
        assert result['preview_data'] == 'https://example.com/image.jpg'
        assert result['nsfw_level'] is None
    
    def test_validate_replace_preview_request_empty_nsfw_level(self):
        """Test preview replacement with empty nsfw_level becomes None"""
        valid_data = {
            'file_path': '/models/test.safetensors',
            'preview_data': 'data:image/jpeg;base64,/9j/4AAQSkZJRg...',
            'nsfw_level': ''
        }
        
        result = self.validator.validate_replace_preview_request(valid_data)
        
        assert result['nsfw_level'] is None
    
    def test_validate_replace_preview_request_missing_file_path(self):
        """Test preview replacement validation with missing file_path"""
        invalid_data = {
            'preview_data': 'data:image/jpeg;base64,/9j/4AAQSkZJRg...'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_replace_preview_request(invalid_data)
        
        assert exc_info.value.field == 'file_path'
        assert 'required' in exc_info.value.message.lower()
    
    def test_validate_replace_preview_request_missing_preview_data(self):
        """Test preview replacement validation with missing preview_data"""
        invalid_data = {
            'file_path': '/models/test.safetensors'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_replace_preview_request(invalid_data)
        
        assert exc_info.value.field == 'preview_data'
        assert 'required' in exc_info.value.message.lower()
    
    def test_validate_replace_preview_request_invalid_preview_format(self):
        """Test preview replacement validation with invalid preview data format"""
        invalid_data = {
            'file_path': '/models/test.safetensors',
            'preview_data': 'invalid_format_data'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_replace_preview_request(invalid_data)
        
        assert exc_info.value.field == 'preview_data'
        assert 'format' in exc_info.value.message.lower()
    
    # Bulk Delete Validation Tests
    def test_validate_bulk_delete_request_valid(self):
        """Test valid bulk delete request validation"""
        valid_data = {
            'file_paths': [
                '/models/loras/model1.safetensors',
                '/models/loras/model2.safetensors',
                '/models/loras/model3.safetensors'
            ]
        }
        
        result = self.validator.validate_bulk_delete_request(valid_data)
        
        assert len(result['file_paths']) == 3
        assert all(path.endswith('.safetensors') for path in result['file_paths'])
    
    def test_validate_bulk_delete_request_missing_file_paths(self):
        """Test bulk delete validation with missing file_paths"""
        invalid_data = {}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_bulk_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_paths'
        assert 'required' in exc_info.value.message.lower()
    
    def test_validate_bulk_delete_request_not_list(self):
        """Test bulk delete validation with non-list file_paths"""
        invalid_data = {'file_paths': 'not_a_list'}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_bulk_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_paths'
        assert 'list' in exc_info.value.message.lower()
    
    def test_validate_bulk_delete_request_empty_list(self):
        """Test bulk delete validation with empty file_paths list"""
        invalid_data = {'file_paths': []}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_bulk_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_paths'
        assert 'empty' in exc_info.value.message.lower()
    
    def test_validate_bulk_delete_request_non_string_path(self):
        """Test bulk delete validation with non-string path in list"""
        invalid_data = {
            'file_paths': ['/valid/path.safetensors', 123, '/another/valid/path.safetensors']
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_bulk_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_paths'
        assert 'string' in exc_info.value.message.lower()
        assert 'index 1' in exc_info.value.message
    
    def test_validate_bulk_delete_request_empty_string_path(self):
        """Test bulk delete validation with empty string in list"""
        invalid_data = {
            'file_paths': ['/valid/path.safetensors', '', '/another/valid/path.safetensors']
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_bulk_delete_request(invalid_data)
        
        assert exc_info.value.field == 'file_paths'
        assert 'empty' in exc_info.value.message.lower()
        assert 'index 1' in exc_info.value.message
    
    # Add Tags Validation Tests
    def test_validate_add_tags_request_valid_list(self):
        """Test valid add tags request with list"""
        valid_data = {
            'file_path': '/models/test.safetensors',
            'tags': ['anime', 'character', 'style']
        }
        
        result = self.validator.validate_add_tags_request(valid_data)
        
        assert result['file_path'] == '/models/test.safetensors'
        assert result['tags'] == ['anime', 'character', 'style']
    
    def test_validate_add_tags_request_valid_string(self):
        """Test valid add tags request with comma-separated string"""
        valid_data = {
            'file_path': '/models/test.safetensors',
            'tags': 'anime, character, style'
        }
        
        result = self.validator.validate_add_tags_request(valid_data)
        
        assert result['file_path'] == '/models/test.safetensors'
        assert result['tags'] == ['anime', 'character', 'style']
    
    def test_validate_add_tags_request_string_with_empty_tags(self):
        """Test add tags with string containing empty tags"""
        valid_data = {
            'file_path': '/models/test.safetensors',
            'tags': 'anime, , character, ,style'  # Contains empty strings
        }
        
        result = self.validator.validate_add_tags_request(valid_data)
        
        # Empty tags should be filtered out
        assert result['tags'] == ['anime', 'character', 'style']
    
    def test_validate_add_tags_request_list_with_non_string(self):
        """Test add tags validation with non-string in list"""
        invalid_data = {
            'file_path': '/models/test.safetensors',
            'tags': ['anime', 123, 'character']
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_add_tags_request(invalid_data)
        
        assert exc_info.value.field == 'tags'
        assert 'string' in exc_info.value.message.lower()
        assert 'index 1' in exc_info.value.message
    
    def test_validate_add_tags_request_invalid_type(self):
        """Test add tags validation with invalid tags type"""
        invalid_data = {
            'file_path': '/models/test.safetensors',
            'tags': 123
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_add_tags_request(invalid_data)
        
        assert exc_info.value.field == 'tags'
        assert 'string or list' in exc_info.value.message.lower()
    
    def test_validate_add_tags_request_no_valid_tags(self):
        """Test add tags validation when no valid tags remain"""
        invalid_data = {
            'file_path': '/models/test.safetensors',
            'tags': ['', '   ', '']  # All empty/whitespace
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_add_tags_request(invalid_data)
        
        assert exc_info.value.field == 'tags'
        assert 'at least one tag' in exc_info.value.message.lower()
    
    # Pagination Validation Tests
    def test_validate_pagination_params_valid(self):
        """Test valid pagination parameters"""
        valid_params = {
            'page': '2',
            'page_size': '50',
            'sort_by': 'name',
            'search': 'test query',
            'fuzzy_search': 'true',
            'favorites_only': 'false'
        }
        
        result = self.validator.validate_pagination_params(valid_params)
        
        assert result['page'] == 2
        assert result['page_size'] == 50
        assert result['sort_by'] == 'name'
        assert result['search'] == 'test query'
        assert result['fuzzy_search'] is True
        assert result['favorites_only'] is False
    
    def test_validate_pagination_params_defaults(self):
        """Test pagination parameters with defaults"""
        minimal_params = {}
        
        result = self.validator.validate_pagination_params(minimal_params)
        
        assert result['page'] == 1
        assert result['page_size'] == 20
        assert result['sort_by'] == 'name'
        assert result['search'] is None
        assert result['fuzzy_search'] is False
        assert result['favorites_only'] is False
    
    def test_validate_pagination_params_empty_search(self):
        """Test pagination with empty search becomes None"""
        params = {'search': '   '}
        
        result = self.validator.validate_pagination_params(params)
        
        assert result['search'] is None
    
    def test_validate_pagination_params_invalid_page(self):
        """Test pagination validation with invalid page"""
        invalid_params = {'page': '0'}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_pagination_params(invalid_params)
        
        assert 'page must be greater than 0' in exc_info.value.message.lower()
    
    def test_validate_pagination_params_invalid_page_size(self):
        """Test pagination validation with invalid page_size"""
        invalid_params = {'page_size': '101'}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_pagination_params(invalid_params)
        
        assert 'page size must be between 1 and 100' in exc_info.value.message.lower()
    
    def test_validate_pagination_params_non_integer(self):
        """Test pagination validation with non-integer values"""
        invalid_params = {'page': 'not_a_number'}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_pagination_params(invalid_params)
        
        assert 'must be integers' in exc_info.value.message.lower()
    
    # Rename Request Validation Tests
    def test_validate_rename_request_valid(self):
        """Test valid rename request validation"""
        valid_data = {
            'file_path': '/models/old_name.safetensors',
            'new_name': 'new_model_name'
        }
        
        result = self.validator.validate_rename_request(valid_data)
        
        assert result['file_path'] == '/models/old_name.safetensors'
        assert result['new_name'] == 'new_model_name'
    
    def test_validate_rename_request_missing_new_name(self):
        """Test rename validation with missing new_name"""
        invalid_data = {'file_path': '/models/test.safetensors'}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_rename_request(invalid_data)
        
        assert exc_info.value.field == 'new_name'
        assert 'required' in exc_info.value.message.lower()
    
    def test_validate_rename_request_invalid_characters(self):
        """Test rename validation with invalid characters in new_name"""
        invalid_data = {
            'file_path': '/models/test.safetensors',
            'new_name': 'invalid<>name'
        }
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_rename_request(invalid_data)
        
        assert exc_info.value.field == 'new_name'
        assert 'invalid characters' in exc_info.value.message.lower()
    
    # Exclude Request Validation Tests
    def test_validate_exclude_request_valid(self):
        """Test valid exclude request validation"""
        valid_data = {'file_path': '/models/exclude_me.safetensors'}
        
        result = self.validator.validate_exclude_request(valid_data)
        
        assert result['file_path'] == '/models/exclude_me.safetensors'
    
    def test_validate_exclude_request_missing_file_path(self):
        """Test exclude validation with missing file_path"""
        invalid_data = {}
        
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate_exclude_request(invalid_data)
        
        assert exc_info.value.field == 'file_path'
        assert 'required' in exc_info.value.message.lower()


class TestValidationError:
    """Unit tests for ValidationError exception"""
    
    def test_validation_error_with_field(self):
        """Test ValidationError with field parameter"""
        error = ValidationError("Test message", "test_field")
        
        assert str(error) == "Test message"
        assert error.message == "Test message"
        assert error.field == "test_field"
    
    def test_validation_error_without_field(self):
        """Test ValidationError without field parameter"""
        error = ValidationError("Test message")
        
        assert str(error) == "Test message"
        assert error.message == "Test message"
        assert error.field is None
    
    def test_validation_error_inheritance(self):
        """Test that ValidationError properly inherits from Exception"""
        error = ValidationError("Test message", "test_field")
        
        assert isinstance(error, Exception)
        
        # Should be raisable and catchable
        with pytest.raises(ValidationError) as exc_info:
            raise error
        
        assert exc_info.value is error


# Edge Case and Stress Tests
class TestValidationEdgeCases:
    """Test edge cases and stress scenarios for validation"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.validator = RequestValidator()
    
    def test_extremely_long_file_path(self):
        """Test validation with extremely long file path"""
        long_path = 'a' * 10000  # Very long path
        data = {'file_path': long_path}
        
        # Should not raise an exception for long paths
        # (filesystem will handle path length limits)
        result = self.validator.validate_delete_request(data)
        assert result['file_path'] == long_path
    
    def test_unicode_file_path(self):
        """Test validation with unicode characters in file path"""
        unicode_path = '/models/测试模型_アニメ_🎨.safetensors'
        data = {'file_path': unicode_path}
        
        result = self.validator.validate_delete_request(data)
        assert result['file_path'] == unicode_path
    
    def test_massive_tag_list(self):
        """Test validation with very large tag list"""
        massive_tags = [f'tag_{i}' for i in range(1000)]
        data = {
            'file_path': '/models/test.safetensors',
            'tags': massive_tags
        }
        
        result = self.validator.validate_add_tags_request(data)
        assert len(result['tags']) == 1000
    
    def test_massive_file_paths_list(self):
        """Test validation with very large file paths list"""
        massive_paths = [f'/models/model_{i}.safetensors' for i in range(1000)]
        data = {'file_paths': massive_paths}
        
        result = self.validator.validate_bulk_delete_request(data)
        assert len(result['file_paths']) == 1000
    
    def test_mixed_case_sha256(self):
        """Test SHA256 validation with mixed case"""
        mixed_case_sha256 = 'aBcDeF' + '0' * 58
        data = {'sha256': mixed_case_sha256}
        
        result = self.validator.validate_fetch_civitai_request(data)
        assert result['sha256'] == mixed_case_sha256.lower()
    
    def test_null_bytes_in_strings(self):
        """Test validation with null bytes in strings"""
        path_with_null = '/models/test\x00model.safetensors'
        data = {'file_path': path_with_null}
        
        # Should not raise an exception - filesystem will handle this
        result = self.validator.validate_delete_request(data)
        assert '\x00' in result['file_path']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
