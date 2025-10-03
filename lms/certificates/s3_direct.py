"""
Direct S3 Upload Utility for Certificate Templates
Completely bypasses Django file validation to avoid HeadObject permission issues
"""

import boto3
import logging
from django.conf import settings
from django.utils import timezone
from django.db import connection
from botocore.exceptions import ClientError
import mimetypes
import re

logger = logging.getLogger(__name__)

def upload_certificate_image_direct(image_file, template_id):
    """
    Upload certificate image directly to S3, completely bypassing Django file validation
    Returns: (success: bool, file_path: str, error_message: str)
    """
    try:
        # S3 configuration
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME')
        region = getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2')
        media_location = getattr(settings, 'AWS_MEDIA_LOCATION', 'media')
        
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        )
        
        # Generate file path
        timestamp = timezone.now().strftime('%Y/%m/%d')
        original_name = image_file.name
        # Sanitize filename
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', original_name)
        
        # S3 key with media location prefix
        s3_key = f"{media_location}/certificate_templates/{timestamp}/{template_id}_{safe_filename}"
        
        # Django path (without media prefix)
        django_path = f"certificate_templates/{timestamp}/{template_id}_{safe_filename}"
        
        # Read file content
        image_file.seek(0)  # Reset file pointer
        file_content = image_file.read()
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(original_name)
        if not content_type:
            ext = original_name.lower().split('.')[-1]
            content_types = {
                'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                'gif': 'image/gif', 'webp': 'image/webp', 'svg': 'image/svg+xml'
            }
            content_type = content_types.get(ext, 'application/octet-stream')
        
        # Upload directly to S3 - NO HeadObject operations
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_content,
            ContentType=content_type,
            CacheControl='max-age=86400'
        )
        
        logger.info(f"✅ Successfully uploaded certificate image to S3: {s3_key}")
        return True, django_path, None
        
    except ClientError as e:
        error_msg = f"S3 upload failed: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return False, None, error_msg
    except Exception as e:
        error_msg = f"Upload failed: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return False, None, error_msg

def update_template_image_path_direct(template_id, image_path):
    """
    Update template image path directly in database, bypassing Django model validation
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE certificates_certificatetemplate SET image = %s WHERE id = %s",
                [image_path, template_id]
            )
        logger.info(f"✅ Updated template {template_id} image path: {image_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update template {template_id} image path: {str(e)}")
        return False

def construct_image_url_safe(image_path):
    """
    Construct image URL without any S3 HeadObject calls
    """
    if not image_path:
        return None
    
    try:
        media_url = getattr(settings, 'MEDIA_URL', '')
        if media_url and image_path:
            return f"{media_url.rstrip('/')}/{image_path}"
    except Exception as e:
        logger.error(f"Failed to construct image URL: {str(e)}")
    
    return None
