"""
Celery tasks for SCORM package processing
"""
import os
import zipfile
import tempfile as temp_module
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
from .utils import validate_zip_file, parse_imsmanifest, validate_manifest_structure

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    soft_time_limit=900,    # 15 minutes (increased from 5)
    time_limit=1800,        # 30 minutes (increased from 10)
    max_retries=3,
    default_retry_delay=60  # 1 minute between retries
)
def extract_scorm_package(self, package_id, zip_file_path=None):
    """
    Celery task to extract and process SCORM package
    
    Args:
        self: Celery task instance (when called via Celery) or None (when called directly)
        package_id: ID of ScormPackage instance
        zip_file_path: Optional path to ZIP file (if not provided, uses package_zip field)
    
    Note: When called directly (not via Celery), pass self=None
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
            # Try to get local path (only works with local storage)
            try:
                if hasattr(package.package_zip, 'path'):
                    try:
                        zip_file_path = package.package_zip.path
                    except (ValueError, NotImplementedError):
                        # No file associated yet or S3 backend
                        zip_file_path = None
                    if zip_file_path and not os.path.exists(zip_file_path):
                        zip_file_path = None
            except (NotImplementedError, AttributeError):
                # S3 storage or other storage backends that don't support .path
                zip_file_path = None
            
            # If no local path, download from S3
            if not zip_file_path:
                # Download from S3 to temporary file
                from django.core.files.storage import default_storage
                
                # Get S3 key from storage
                s3_key = package.package_zip.name
                
                logger.info(f"Downloading SCORM package from S3: {s3_key}")
                
                # Download to temporary file
                temp_zip = temp_module.NamedTemporaryFile(delete=False, suffix='.zip')
                temp_zip_path = temp_zip.name
                
                try:
                    # Download from S3
                    with default_storage.open(s3_key, 'rb') as s3_file:
                        temp_zip.write(s3_file.read())
                        temp_zip.close()
                    
                    zip_file_path = temp_zip_path
                    logger.info(f"Downloaded SCORM package to temporary file: {temp_zip_path}")
                except Exception as e:
                    logger.error(f"Error downloading SCORM package from S3: {e}")
                    temp_zip.close()
                    if os.path.exists(temp_zip_path):
                        os.unlink(temp_zip_path)
                    raise
        
        if not zip_file_path:
            raise ValueError("No ZIP file provided")
        
        # Validate ZIP file
        is_valid, error_msg = validate_zip_file(zip_file_path, max_size_mb=600, max_files=10000)
        if not is_valid:
            package.processing_status = 'failed'
            package.processing_error = error_msg
            package.save(update_fields=['processing_status', 'processing_error'])
            # Clean up temp file if it was downloaded (avoid S3 .path access)
            try:
                original_path = package.package_zip.path if hasattr(package.package_zip, 'path') else None
                if original_path and zip_file_path != original_path and os.path.exists(zip_file_path):
                    os.unlink(zip_file_path)
            except (NotImplementedError, AttributeError):
                # S3 storage - zip_file_path is always temp file, safe to delete
                if os.path.exists(zip_file_path):
                    os.unlink(zip_file_path)
            return {'success': False, 'error': error_msg}
        
        # Validate manifest structure
        is_valid, error_msg = validate_manifest_structure(zip_file_path)
        if not is_valid:
            package.processing_status = 'failed'
            package.processing_error = f"Invalid manifest: {error_msg}"
            package.save(update_fields=['processing_status', 'processing_error'])
            # Clean up temp file if it was downloaded (avoid S3 .path access)
            try:
                original_path = package.package_zip.path if hasattr(package.package_zip, 'path') else None
                if original_path and zip_file_path != original_path and os.path.exists(zip_file_path):
                    os.unlink(zip_file_path)
            except (NotImplementedError, AttributeError):
                # S3 storage - zip_file_path is always temp file, safe to delete
                if os.path.exists(zip_file_path):
                    os.unlink(zip_file_path)
            return {'success': False, 'error': f"Invalid manifest: {error_msg}"}
        
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
            
            # Extract resources data
            resources = manifest_data.get('resources', [])
            
            # Extract primary resource (first SCO resource found)
            primary_resource = None
            primary_resource_identifier = None
            primary_resource_type = None
            primary_resource_scorm_type = None
            primary_resource_href = None
            
            # Find first SCO resource (primary resource)
            for resource in resources:
                resource_id = resource.get('identifier', '')
                resource_type_raw = resource.get('type', '')
                resource_type = resource_type_raw.lower() if resource_type_raw else ''
                scorm_type_raw = resource.get('scormType', '')
                scorm_type = scorm_type_raw.lower() if scorm_type_raw else ''
                href = resource.get('href', '')
                
                # Check if this is a SCO resource (check both scormType attribute and type field)
                is_sco = (
                    scorm_type == 'sco' or 
                    'sco' in scorm_type or
                    (resource_type and 'sco' in resource_type)
                )
                
                if is_sco:
                    primary_resource = resource
                    primary_resource_identifier = resource_id
                    base = resource.get('base', '')
                    
                    # Normalize resource type to match choices
                    if 'webcontent' in resource_type or resource_type == '':
                        primary_resource_type = 'webcontent'
                    else:
                        primary_resource_type = 'webcontent'  # Default to webcontent for now
                    
                    # Normalize scorm type
                    if scorm_type == 'sco':
                        primary_resource_scorm_type = 'sco'
                    elif scorm_type == 'asset':
                        primary_resource_scorm_type = 'asset'
                    elif 'sco' in scorm_type:
                        primary_resource_scorm_type = 'sco'
                    elif resource_type and 'sco' in resource_type:
                        primary_resource_scorm_type = 'sco'
                    else:
                        primary_resource_scorm_type = 'sco'  # Default to sco
                    
                    # Normalize href with base path (same logic as get_entry_point uses)
                    if href:
                        # Use the same normalization logic as in models.py
                        from urllib.parse import urlparse
                        parsed = urlparse(href)
                        if parsed.scheme or parsed.netloc:
                            # It's a full URL, extract just the path
                            href_path = parsed.path.lstrip('/')
                            primary_resource_href = href_path.replace('\\', '/') if href_path else href
                        else:
                            # Combine base and href if base is provided
                            href_clean = href.lstrip('/').lstrip('\\')
                            if base and isinstance(base, str):
                                base_clean = base.strip('/').strip('\\')
                                if base_clean:
                                    primary_resource_href = f"{base_clean}/{href_clean}".replace('\\', '/')
                                else:
                                    primary_resource_href = href_clean.replace('\\', '/')
                            else:
                                primary_resource_href = href_clean.replace('\\', '/')
                        
                        # Remove double slashes and normalize
                        parts = [p for p in primary_resource_href.split('/') if p]
                        primary_resource_href = '/'.join(parts)
                    else:
                        primary_resource_href = href
                    break
            
            # If no SCO found, use first resource with href as fallback
            if not primary_resource:
                for resource in resources:
                    href = resource.get('href', '')
                    base = resource.get('base', '')
                    if href:
                        primary_resource = resource
                        primary_resource_identifier = resource.get('identifier', '')
                        primary_resource_type = 'webcontent'  # Default
                        primary_resource_scorm_type = 'sco'  # Default to sco
                        
                        # Normalize href with base path (same as above)
                        from urllib.parse import urlparse
                        parsed = urlparse(href)
                        if parsed.scheme or parsed.netloc:
                            href_path = parsed.path.lstrip('/')
                            primary_resource_href = href_path.replace('\\', '/') if href_path else href
                        else:
                            href_clean = href.lstrip('/').lstrip('\\')
                            if base and isinstance(base, str):
                                base_clean = base.strip('/').strip('\\')
                                if base_clean:
                                    primary_resource_href = f"{base_clean}/{href_clean}".replace('\\', '/')
                                else:
                                    primary_resource_href = href_clean.replace('\\', '/')
                            else:
                                primary_resource_href = href_clean.replace('\\', '/')
                        
                        # Remove double slashes and normalize
                        parts = [p for p in primary_resource_href.split('/') if p]
                        primary_resource_href = '/'.join(parts)
                        break
            
            # Update package with manifest data and resource data
            package.manifest_data = manifest_data
            package.version = scorm_version
            if title:
                package.title = title[:255]  # Truncate to max length
            package.resources = resources
            
            # Set primary resource fields
            if primary_resource_identifier:
                package.primary_resource_identifier = primary_resource_identifier[:128]  # Truncate to max length
            if primary_resource_type:
                package.primary_resource_type = primary_resource_type[:32]  # Truncate to max length
            if primary_resource_scorm_type:
                package.primary_resource_scorm_type = primary_resource_scorm_type[:16]  # Truncate to max length
            if primary_resource_href:
                package.primary_resource_href = primary_resource_href[:2048]  # Truncate to max length
            
            # ✅ VALIDATION: Ensure primary resource fields are populated
            # This is CRITICAL for the entry point to work
            if not package.primary_resource_href:
                logger.warning(f"SCORM package {package_id}: No primary_resource_href found, attempting fallback...")
                # Try to get from cached entry point or manifest
                cached_entry = manifest_data.get('entry_point')
                if cached_entry:
                    package.primary_resource_href = cached_entry[:2048]
                    logger.info(f"SCORM package {package_id}: Using cached entry point as primary_resource_href: {cached_entry}")
                else:
                    # Use fallback entry point
                    fallback = package._get_fallback_entry_point()
                    package.primary_resource_href = fallback[:2048]
                    logger.warning(f"SCORM package {package_id}: Using fallback entry point as primary_resource_href: {fallback}")
            
            # Set defaults if still missing
            if not package.primary_resource_identifier:
                package.primary_resource_identifier = 'default_resource'
            if not package.primary_resource_type:
                package.primary_resource_type = 'webcontent'
            if not package.primary_resource_scorm_type:
                package.primary_resource_scorm_type = 'sco'
            
            package.save(update_fields=[
                'manifest_data', 'version', 'title', 'resources',
                'primary_resource_identifier', 'primary_resource_type',
                'primary_resource_scorm_type', 'primary_resource_href'
            ])
            
            # Log saved values for verification
            logger.info(f"SCORM package {package_id}: Saved primary resource fields:")
            logger.info(f"  - identifier: {package.primary_resource_identifier}")
            logger.info(f"  - type: {package.primary_resource_type}")
            logger.info(f"  - scorm_type: {package.primary_resource_scorm_type}")
            logger.info(f"  - href: {package.primary_resource_href}")

            # Compute and persist normalized entry point for faster/consistent lookup
            # This happens early (after manifest parsing) so we can validate it later
            try:
                entry_point = package.get_entry_point()
                if entry_point:
                    # Store a cached copy inside manifest_data so templates can rely on it
                    md = package.manifest_data or {}
                    # Always update entry_point in manifest_data for consistency
                    md['entry_point'] = entry_point
                    package.manifest_data = md
                    # Update launch URL
                    package.update_launch_url()
                    # Auto-detect authoring tool
                    if not package.authoring_tool or package.authoring_tool == 'unknown':
                        package.authoring_tool = package.detect_authoring_tool()
                    package.save(update_fields=['manifest_data', 'launch_url', 'authoring_tool'])
                    logger.info(f"📌 Cached SCORM entry point during manifest parsing for package {package_id}: {entry_point}")
            except Exception as entry_err:
                logger.warning(f"Could not cache SCORM entry point for package {package_id} during manifest parsing: {entry_err}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Error parsing manifest for package {package_id}: {e}")
            package.processing_status = 'failed'
            package.processing_error = f"Manifest parsing error: {str(e)}"
            package.save(update_fields=['processing_status', 'processing_error'])
            return {'success': False, 'error': f"Manifest parsing failed: {str(e)}"}
        
        # Extract ZIP to temporary directory
        temp_dir = temp_module.mkdtemp(prefix='scorm_extract_')
        
        try:
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                # Extract all files
                zip_ref.extractall(temp_dir)
            
            # Upload extracted files to S3
            s3_path = upload_to_s3(temp_dir, package_id)
            
            # ✅ FINAL VALIDATION: Ensure all critical fields are populated before marking as 'ready'
            package.refresh_from_db()  # Ensure we have latest data
            
            validation_errors = []
            if not package.primary_resource_href:
                validation_errors.append("primary_resource_href is missing")
            if not package.primary_resource_identifier:
                validation_errors.append("primary_resource_identifier is missing")
            if not package.resources:
                validation_errors.append("resources array is empty")
            if not package.manifest_data:
                validation_errors.append("manifest_data is missing")
            
            if validation_errors:
                error_msg = f"Validation failed: {', '.join(validation_errors)}"
                logger.error(f"SCORM package {package_id}: {error_msg}")
                package.processing_status = 'failed'
                package.processing_error = error_msg
                package.save(update_fields=['processing_status', 'processing_error'])
                return {'success': False, 'error': error_msg}
            
            # Update package with extracted path
            package.extracted_path = s3_path
            package.processing_status = 'ready'
            package.processing_error = None
            package.save(update_fields=['extracted_path', 'processing_status', 'processing_error'])
            
            logger.info(f"✅ SCORM package {package_id} marked as READY with all required fields populated")
            
            # Re-compute and verify entry point now that files are in S3
            # This ensures entry_point is saved even if it wasn't computed earlier
            try:
                # Refresh from DB to ensure we have latest manifest_data
                package.refresh_from_db()
                
                entry_point = package.get_entry_point()
                if entry_point:
                    # Ensure entry point is cached in manifest_data
                    md = package.manifest_data or {}
                    if md.get('entry_point') != entry_point:
                        md['entry_point'] = entry_point
                        package.manifest_data = md
                    
                    # Update launch URL
                    package.update_launch_url()
                    # Auto-detect authoring tool if not already set
                    if not package.authoring_tool or package.authoring_tool == 'unknown':
                        package.authoring_tool = package.detect_authoring_tool()
                    package.save(update_fields=['manifest_data', 'launch_url', 'authoring_tool'])
                    logger.info(f"Cached SCORM entry point after extraction for package {package_id}: {entry_point}")
                    
                    # Verify entry point exists in S3
                    exists, error = package.verify_entry_point_exists()
                    if exists:
                        logger.info(f"Verified SCORM entry point exists in S3 for package {package_id}: {entry_point}")
                    else:
                        logger.warning(f"SCORM entry point not found in S3 for package {package_id}: {entry_point} - {error}")
                else:
                    logger.warning(f"Could not determine entry point for package {package_id}")
            except Exception as verify_err:
                logger.warning(f"Could not verify entry point for package {package_id} after extraction: {verify_err}")
            
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
                        try:
                            original_path = package.package_zip.path
                        except (NotImplementedError, AttributeError):
                            # S3 backend doesn't support .path
                            original_path = None
                    
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
                file_ext = file_name.lower()
                
                # Mapping of extensions to content types
                content_type_map = {
                    '.html': 'text/html',
                    '.htm': 'text/html',
                    '.js': 'application/javascript',
                    '.css': 'text/css',
                    '.json': 'application/json',
                    '.xml': 'application/xml',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.svg': 'image/svg+xml',
                    '.webp': 'image/webp',
                    '.ico': 'image/x-icon',
                    '.woff': 'font/woff',
                    '.woff2': 'font/woff2',
                    '.ttf': 'font/ttf',
                    '.eot': 'application/vnd.ms-fontobject',
                    '.otf': 'font/otf',
                    '.mp4': 'video/mp4',
                    '.webm': 'video/webm',
                    '.mp3': 'audio/mpeg',
                    '.wav': 'audio/wav',
                    '.ogg': 'audio/ogg',
                }
                
                for ext, ctype in content_type_map.items():
                    if file_ext.endswith(ext):
                        content_type = ctype
                        break
                
                # Upload file to S3 with retry logic
                max_retries = 3
                retry_count = 0
                upload_success = False
                
                while retry_count < max_retries and not upload_success:
                    try:
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
                        upload_success = True
                    except Exception as upload_error:
                        retry_count += 1
                        if retry_count >= max_retries:
                            logger.error(f"Failed to upload {s3_key} after {max_retries} attempts: {upload_error}")
                            raise
                        logger.warning(f"Upload attempt {retry_count} failed for {s3_key}, retrying...")
                        import time
                        time.sleep(2 ** retry_count)  # Exponential backoff
        
        logger.info(f"Uploaded SCORM package files to S3: {s3_prefix}")
        return s3_prefix
        
    except Exception as e:
        logger.error(f"Error uploading to S3: {e}", exc_info=True)
        raise

