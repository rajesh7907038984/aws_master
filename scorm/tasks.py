"""
Celery tasks for SCORM package processing
"""
import os
import zipfile
import tempfile
import logging
from pathlib import Path
try:
    from celery import shared_task
except ImportError:
    try:
        from celery.decorators import task as shared_task
    except ImportError:
        # Fallback - use a dummy decorator if Celery not available
        def shared_task(*args, **kwargs):
            def decorator(func):
                return func
            return decorator
from django.conf import settings
from django.core.files.storage import default_storage
import boto3
from botocore.client import Config

from .models import ScormPackage
from .utils import validate_zip_file, parse_imsmanifest

logger = logging.getLogger(__name__)


@shared_task(bind=True, soft_time_limit=300, time_limit=600, max_retries=3)
def extract_scorm_package(self, package_id, zip_file_path=None):
    """
    Celery task to extract and process SCORM package
    
    Args:
        package_id: ID of ScormPackage instance
        zip_file_path: Optional path to ZIP file (if not provided, uses package_zip field)
    """
    package = None
    temp_dir = None
    
    try:
        # Get package instance
        try:
            package = ScormPackage.objects.get(id=package_id)
        except ScormPackage.DoesNotExist:
            logger.error(f"ScormPackage {package_id} not found")
            return {'success': False, 'error': 'Package not found'}
        
        # Update status to processing
        package.processing_status = 'processing'
        package.processing_error = None
        package.save(update_fields=['processing_status', 'processing_error'])
        
        # Get ZIP file path or download from S3
        if not zip_file_path and package.package_zip:
            # Check if file has local path (development) or S3 URL (production)
            if hasattr(package.package_zip, 'path') and os.path.exists(package.package_zip.path):
                zip_file_path = package.package_zip.path
            else:
                # Download from S3 to temporary file
                from django.core.files.storage import default_storage
                import tempfile
                
                # Get S3 key from storage
                s3_key = package.package_zip.name
                
                # Download to temporary file
                temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
                temp_zip_path = temp_zip.name
                
                # Download from S3
                with default_storage.open(s3_key, 'rb') as s3_file:
                    temp_zip.write(s3_file.read())
                    temp_zip.close()
                
                zip_file_path = temp_zip_path
        
        if not zip_file_path:
            raise ValueError("No ZIP file provided")
        
        # Validate ZIP file
        is_valid, error_msg = validate_zip_file(zip_file_path, max_size_mb=600, max_files=10000)
        if not is_valid:
            package.processing_status = 'failed'
            package.processing_error = error_msg
            package.save(update_fields=['processing_status', 'processing_error'])
            # Clean up temp file if it was downloaded
            if zip_file_path != package.package_zip.path and os.path.exists(zip_file_path):
                os.unlink(zip_file_path)
            return {'success': False, 'error': error_msg}
        
        # Parse manifest
        try:
            manifest_data = parse_imsmanifest(zip_file_path)
            
            # Extract version
            scorm_version = manifest_data.get('version', '1.2')
            if scorm_version not in ['1.2', '2004']:
                scorm_version = '1.2'  # Default fallback
            
            # Extract title from manifest
            title = None
            if manifest_data.get('metadata', {}).get('title'):
                title = manifest_data['metadata']['title']
            elif manifest_data.get('organizations'):
                org = manifest_data['organizations'][0]
                title = org.get('title', '')
            
            # Update package with manifest data
            package.manifest_data = manifest_data
            package.version = scorm_version
            if title:
                package.title = title[:255]  # Truncate to max length
            package.save(update_fields=['manifest_data', 'version', 'title'])
            
        except Exception as e:
            logger.error(f"Error parsing manifest for package {package_id}: {e}")
            package.processing_status = 'failed'
            package.processing_error = f"Manifest parsing error: {str(e)}"
            package.save(update_fields=['processing_status', 'processing_error'])
            return {'success': False, 'error': f"Manifest parsing failed: {str(e)}"}
        
        # Extract ZIP to temporary directory
        temp_dir = tempfile.mkdtemp(prefix='scorm_extract_')
        
        try:
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                # Extract all files
                zip_ref.extractall(temp_dir)
            
            # Upload extracted files to S3
            s3_path = upload_to_s3(temp_dir, package_id)
            
            # Update package with extracted path
            package.extracted_path = s3_path
            package.processing_status = 'ready'
            package.processing_error = None
            package.save(update_fields=['extracted_path', 'processing_status', 'processing_error'])
            
            logger.info(f"Successfully extracted SCORM package {package_id} to {s3_path}")
            
            return {
                'success': True,
                'package_id': package_id,
                'extracted_path': s3_path,
                'version': scorm_version
            }
            
        except Exception as e:
            logger.error(f"Error extracting ZIP for package {package_id}: {e}")
            package.processing_status = 'failed'
            package.processing_error = f"Extraction error: {str(e)}"
            package.save(update_fields=['processing_status', 'processing_error'])
            return {'success': False, 'error': f"Extraction failed: {str(e)}"}
        
    except Exception as e:
        logger.error(f"Unexpected error processing package {package_id}: {e}", exc_info=True)
        if package:
            package.processing_status = 'failed'
            package.processing_error = f"Unexpected error: {str(e)}"
            package.save(update_fields=['processing_status', 'processing_error'])
        return {'success': False, 'error': f"Unexpected error: {str(e)}"}
    
    finally:
        # Cleanup temp directory and temp ZIP file
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Error cleaning up temp directory {temp_dir}: {e}")
        
        # Cleanup temp ZIP file if it was downloaded from S3
        if 'zip_file_path' in locals() and zip_file_path:
            try:
                # Check if this was a temporary download (not original path)
                if package and package.package_zip:
                    original_path = None
                    if hasattr(package.package_zip, 'path'):
                        original_path = package.package_zip.path
                    
                    # If zip_file_path is not the original path, it's a temp file
                    if original_path and zip_file_path != original_path:
                        if os.path.exists(zip_file_path):
                            os.unlink(zip_file_path)
                            logger.debug(f"Cleaned up temp ZIP file: {zip_file_path}")
                    elif not original_path and zip_file_path:
                        # S3 storage - always a temp file
                        if os.path.exists(zip_file_path):
                            os.unlink(zip_file_path)
                            logger.debug(f"Cleaned up temp ZIP file: {zip_file_path}")
            except Exception as e:
                logger.warning(f"Error cleaning up temp ZIP file: {e}")


def upload_to_s3(local_dir, package_id):
    """
    Upload extracted SCORM package directory to S3
    
    Args:
        local_dir: Local directory containing extracted files
        package_id: SCORM package ID
    
    Returns:
        S3 path prefix for uploaded files
    """
    try:
        # Get S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'),
            config=Config(signature_version='s3v4')
        )
        
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        # S3 path structure: scorm-packages/{package_id}/extracted/
        s3_prefix = f"scorm-packages/{package_id}/extracted/"
        
        # Walk through local directory and upload files
        for root, dirs, files in os.walk(local_dir):
            for file_name in files:
                local_path = os.path.join(root, file_name)
                
                # Get relative path for S3 key
                rel_path = os.path.relpath(local_path, local_dir)
                # Normalize path separators for S3
                s3_key = s3_prefix + rel_path.replace('\\', '/')
                
                # Determine content type
                content_type = 'application/octet-stream'
                if file_name.endswith('.html'):
                    content_type = 'text/html'
                elif file_name.endswith('.js'):
                    content_type = 'application/javascript'
                elif file_name.endswith('.css'):
                    content_type = 'text/css'
                elif file_name.endswith('.json'):
                    content_type = 'application/json'
                elif file_name.endswith('.xml'):
                    content_type = 'application/xml'
                elif file_name.endswith('.png'):
                    content_type = 'image/png'
                elif file_name.endswith('.jpg') or file_name.endswith('.jpeg'):
                    content_type = 'image/jpeg'
                elif file_name.endswith('.gif'):
                    content_type = 'image/gif'
                elif file_name.endswith('.svg'):
                    content_type = 'image/svg+xml'
                
                # Upload file to S3
                with open(local_path, 'rb') as f:
                    s3_client.upload_fileobj(
                        f,
                        bucket_name,
                        s3_key,
                        ExtraArgs={
                            'ContentType': content_type,
                            'CacheControl': 'max-age=86400'
                        }
                    )
        
        logger.info(f"Uploaded SCORM package files to S3: {s3_prefix}")
        return s3_prefix
        
    except Exception as e:
        logger.error(f"Error uploading to S3: {e}", exc_info=True)
        raise

