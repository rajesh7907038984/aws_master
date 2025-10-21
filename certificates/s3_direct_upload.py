"""
S3 Direct Upload Utility for Certificate Templates
Bypasses Django's file field validation to avoid HeadObject permission issues
"""

import boto3
import logging
from django.conf import settings
from django.utils import timezone
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class S3DirectUploader:
    """Direct S3 uploader that bypasses Django's file field validation"""
    
    def __init__(self):
        self.bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME')
        self.region = getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2')
        self.media_location = getattr(settings, 'AWS_MEDIA_LOCATION', 'media')
        
        # Initialize S3 client with current credentials
        self.s3_client = boto3.client(
            's3',
            region_name=self.region,
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        )
    
    def upload_template_image(self, image_file, template_id):
        """
        Upload image directly to S3 without HeadObject calls
        Returns: (success: bool, file_path: str, error_message: str)
        """
        try:
            # Generate unique file path
            timestamp = timezone.now().strftime('%Y/%m/%d')
            original_name = image_file.name
            safe_filename = self._sanitize_filename(original_name)
            
            # S3 key with media location prefix
            s3_key = f"{self.media_location}/certificate_templates/{timestamp}/{template_id}_{safe_filename}"
            
            # Read file content
            image_file.seek(0)  # Reset file pointer
            file_content = image_file.read()
            
            # Upload directly to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_content,
                ContentType=self._get_content_type(original_name)
            )
            
            # Return the relative path (without media location prefix for Django)
            django_path = f"certificate_templates/{timestamp}/{template_id}_{safe_filename}"
            
            logger.info(f"Successfully uploaded image to S3: {s3_key}")
            return True, django_path, None
            
        except ClientError as e:
            error_msg = f"S3 upload failed: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
    
    def _sanitize_filename(self, filename):
        """Sanitize filename for S3 storage"""
        import re
        # Remove special characters and spaces
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        return safe_name
    
    def _get_content_type(self, filename):
        """Determine content type from filename"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        if content_type:
            return content_type
        
        # Fallback based on extension
        ext = filename.lower().split('.')[-1]
        content_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg', 
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'svg': 'image/svg+xml'
        }
        return content_types.get(ext, 'application/octet-stream')

def upload_certificate_image_safe(image_file, template_id):
    """
    Safe wrapper function to upload certificate template images
    Returns: (success: bool, file_path: str, error_message: str)
    """
    uploader = S3DirectUploader()
    return uploader.upload_template_image(image_file, template_id)
