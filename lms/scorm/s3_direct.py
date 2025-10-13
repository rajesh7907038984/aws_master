"""
Direct S3 URL Generator for SCORM Content
Simple utility to generate direct S3 URLs without Django proxy
"""

import boto3
from django.conf import settings
from core.env_loader import get_env
import logging

logger = logging.getLogger(__name__)

class ScormS3DirectAccess:
    """
    Simple class to generate direct S3 URLs for SCORM content
    Eliminates the need for Django proxy layer
    """
    
    def __init__(self):
        self.bucket_name = get_env('AWS_STORAGE_BUCKET_NAME', 'lms-staging-nexsy-io')
        self.region = get_env('AWS_S3_REGION_NAME', 'eu-west-2')
        self.media_location = get_env('AWS_MEDIA_LOCATION', 'media')
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=get_env('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=get_env('AWS_SECRET_ACCESS_KEY'),
            region_name=self.region
        )
    
    def generate_direct_url(self, scorm_package, file_path=''):
        """
        Generate full S3 URL for content access
        
        Args:
            scorm_package: ScormPackage instance
            file_path: Optional file path within the package
            
        Returns:
            Full HTTPS URL to S3 content
        """
        try:
            # Build S3 key path - handle double media/ prefix issue
            extracted_path = scorm_package.extracted_path
            if extracted_path.startswith('media/'):
                # Remove the 'media/' prefix since media_location will add it
                extracted_path = extracted_path[6:]  # Remove 'media/' prefix
            
            base_path = f"{self.media_location}/{extracted_path}"
            if file_path:
                s3_key = f"{base_path}/{file_path}"
            else:
                s3_key = f"{base_path}/{scorm_package.launch_url}"
            
            # Generate full HTTPS URL
            full_url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            
            logger.info(f"Generated S3 URL: {full_url}")
            return full_url
            
        except Exception as e:
            logger.error(f"Error generating S3 URL: {str(e)}")
            return None
    
    def generate_launch_url(self, scorm_package):
        """
        Generate direct S3 URL for SCORM launch file (index.html, etc.)
        
        Args:
            scorm_package: ScormPackage instance
            
        Returns:
            Direct HTTPS URL to launch file
        """
        return self.generate_direct_url(scorm_package)
    
    def get_s3_key(self, scorm_package, file_path=''):
        """
        Get S3 key for authenticated access (for boto3 operations)
        
        Args:
            scorm_package: ScormPackage instance
            file_path: Optional file path within the package
            
        Returns:
            S3 key for boto3 operations
        """
        try:
            # Handle double media/ prefix issue
            extracted_path = scorm_package.extracted_path
            if extracted_path.startswith('media/'):
                # Remove the 'media/' prefix since media_location will add it
                extracted_path = extracted_path[6:]  # Remove 'media/' prefix
            
            base_path = f"{self.media_location}/{extracted_path}"
            if file_path:
                s3_key = f"{base_path}/{file_path}"
            else:
                s3_key = f"{base_path}/{scorm_package.launch_url}"
            
            return s3_key
            
        except Exception as e:
            logger.error(f"Error generating S3 key: {str(e)}")
            return None
    
    def get_base_url(self, scorm_package):
        """
        Get base URL for SCORM package content
        Used for resolving relative paths in SCORM content
        
        Args:
            scorm_package: ScormPackage instance
            
        Returns:
            Base URL for the SCORM package
        """
        # Handle double media/ prefix issue
        extracted_path = scorm_package.extracted_path
        if extracted_path.startswith('media/'):
            # Remove the 'media/' prefix since media_location will add it
            extracted_path = extracted_path[6:]  # Remove 'media/' prefix
        
        base_path = f"{self.media_location}/{extracted_path}"
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{base_path}/"
    
    def verify_file_exists(self, scorm_package, file_path=''):
        """
        Verify that a file exists in S3
        
        Args:
            scorm_package: ScormPackage instance
            file_path: Optional file path within the package
            
        Returns:
            Boolean indicating if file exists
        """
        try:
            s3_key = self.get_s3_key(scorm_package, file_path)
            if not s3_key:
                return False
                
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
            
        except Exception as e:
            logger.warning(f"File not found in S3: {s3_key} - {str(e)}")
            return False
    
    def list_package_files(self, scorm_package):
        """
        List all files in a SCORM package
        
        Args:
            scorm_package: ScormPackage instance
            
        Returns:
            List of file paths in the package
        """
        try:
            # Handle double media/ prefix issue
            extracted_path = scorm_package.extracted_path
            if extracted_path.startswith('media/'):
                # Remove the 'media/' prefix since media_location will add it
                extracted_path = extracted_path[6:]  # Remove 'media/' prefix
            
            base_path = f"{self.media_location}/{extracted_path}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=base_path
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    # Remove the base path to get relative file path
                    relative_path = obj['Key'].replace(base_path, '')
                    if relative_path:  # Skip empty paths (directories)
                        files.append(relative_path)
            
            logger.info(f"Found {len(files)} files in SCORM package {scorm_package.id}")
            return files
            
        except Exception as e:
            logger.error(f"Error listing SCORM package files: {str(e)}")
            return []

# Singleton instance for easy access
scorm_s3 = ScormS3DirectAccess()
