"""
Comprehensive file validation utilities for the LMS
Handles S3 storage, local storage, and error scenarios
"""
import os
import logging
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

class FileValidationError(Exception):
    """Custom exception for file validation errors"""
    pass

def validate_file_exists(file_field, error_message=None):
    """
    Validate that a file field exists in storage
    
    Args:
        file_field: Django FileField instance
        error_message: Custom error message
        
    Returns:
        bool: True if file exists, False otherwise
        
    Raises:
        FileValidationError: If file doesn't exist
    """
    if not file_field:
        error_msg = error_message or "No file attached"
        logger.error(error_msg)
        raise FileValidationError(error_msg)
    
    try:
        # Check if file exists in storage
        if not file_field.storage.exists(file_field.name):
            error_msg = error_message or f"File not found in storage: {file_field.name}"
            logger.error(error_msg)
            raise FileValidationError(error_msg)
        return True
    except Exception as e:
        error_msg = error_message or f"Error checking file existence: {str(e)}"
        logger.error(error_msg)
        raise FileValidationError(error_msg)

def get_safe_file_path(file_field, base_path=None):
    """
    Get a safe file path for file operations, handling S3 and local storage
    
    Args:
        file_field: Django FileField instance
        base_path: Optional base path for local storage
        
    Returns:
        str: Safe file path for operations
    """
    if not file_field:
        raise FileValidationError("No file attached")
    
    # For S3 storage, use local media directory
    if hasattr(file_field.storage, 'location') and file_field.storage.location:
        # This is S3 storage
        local_media_root = getattr(settings, 'MEDIA_ROOT', None)
        if local_media_root:
            return os.path.join(local_media_root, file_field.name)
        else:
            # Fallback to temp directory
            import tempfile
            return os.path.join(tempfile.gettempdir(), file_field.name)
    else:
        # Local storage
        return file_field.path

def validate_storage_consistency(file_field):
    """
    Validate that file storage is consistent (file exists in storage)
    
    Args:
        file_field: Django FileField instance
        
    Returns:
        dict: Validation results
    """
    results = {
        'valid': False,
        'file_exists': False,
        'storage_accessible': False,
        'error': None
    }
    
    if not file_field:
        results['error'] = "No file attached"
        return results
    
    try:
        # Check if storage is accessible
        results['storage_accessible'] = True
        
        # Check if file exists
        results['file_exists'] = file_field.storage.exists(file_field.name)
        
        if results['file_exists']:
            results['valid'] = True
        else:
            results['error'] = f"File not found in storage: {file_field.name}"
            
    except Exception as e:
        results['error'] = f"Storage error: {str(e)}"
        results['storage_accessible'] = False
    
    return results

def safe_file_operation(file_field, operation_func, *args, **kwargs):
    """
    Safely perform file operations with proper error handling
    
    Args:
        file_field: Django FileField instance
        operation_func: Function to execute with file
        *args: Arguments for operation function
        **kwargs: Keyword arguments for operation function
        
    Returns:
        Any: Result of operation function
        
    Raises:
        FileValidationError: If operation fails
    """
    try:
        # Validate file exists first
        validate_file_exists(file_field)
        
        # Get safe file path
        file_path = get_safe_file_path(file_field)
        
        # Execute operation
        return operation_func(file_path, *args, **kwargs)
        
    except Exception as e:
        error_msg = f"File operation failed: {str(e)}"
        logger.error(error_msg)
        raise FileValidationError(error_msg)

def check_storage_health():
    """
    Check overall storage health across the system
    
    Returns:
        dict: Health check results
    """
    health = {
        's3_configured': False,
        'local_media_available': False,
        'storage_accessible': False,
        'issues': []
    }
    
    # Check S3 configuration
    if (hasattr(settings, 'AWS_ACCESS_KEY_ID') and 
        hasattr(settings, 'AWS_SECRET_ACCESS_KEY') and
        hasattr(settings, 'AWS_STORAGE_BUCKET_NAME')):
        health['s3_configured'] = True
    
    # Check local media root
    media_root = getattr(settings, 'MEDIA_ROOT', None)
    if media_root and os.path.exists(media_root):
        health['local_media_available'] = True
    elif not media_root:
        health['issues'].append("MEDIA_ROOT not configured (S3 storage mode)")
    
    # Test storage accessibility
    try:
        test_file = "health_check_test.txt"
        test_content = b"Health check test"
        
        # Try to save a test file
        from django.core.files.base import ContentFile
        saved_name = default_storage.save(test_file, ContentFile(test_content))
        
        # Check if it exists
        if default_storage.exists(saved_name):
            health['storage_accessible'] = True
            # Clean up test file
            default_storage.delete(saved_name)
        else:
            health['issues'].append("Storage write/read test failed")
            
    except Exception as e:
        health['issues'].append(f"Storage accessibility test failed: {str(e)}")
    
    return health

def fix_storage_inconsistencies(model_class, file_field_name):
    """
    Fix storage inconsistencies for a model class
    
    Args:
        model_class: Django model class
        file_field_name: Name of the file field
        
    Returns:
        dict: Fix results
    """
    results = {
        'total_objects': 0,
        'fixed_objects': 0,
        'errors': []
    }
    
    try:
        objects = model_class.objects.all()
        results['total_objects'] = objects.count()
        
        for obj in objects:
            file_field = getattr(obj, file_field_name, None)
            if not file_field:
                continue
                
            # Check storage consistency
            validation = validate_storage_consistency(file_field)
            
            if not validation['valid']:
                # Mark as not processed/extracted if it's a processing field
                if hasattr(obj, 'is_extracted'):
                    obj.is_extracted = False
                if hasattr(obj, 'extraction_error'):
                    obj.extraction_error = validation['error']
                if hasattr(obj, 'extracted_path'):
                    obj.extracted_path = ""
                if hasattr(obj, 'manifest_path'):
                    obj.manifest_path = ""
                if hasattr(obj, 'launch_file'):
                    obj.launch_file = ""
                
                obj.save()
                results['fixed_objects'] += 1
                
    except Exception as e:
        results['errors'].append(f"Error fixing inconsistencies: {str(e)}")
    
    return results
