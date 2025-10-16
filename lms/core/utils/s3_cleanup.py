"""
S3 File Cleanup Utilities for Cascade Deletion
Handles deletion of files from S3 buckets when objects are deleted
"""

import logging
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class S3CleanupManager:
    """
    Manages S3 file cleanup operations for cascade deletion
    """
    
    def __init__(self):
        self.bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        self.media_location = getattr(settings, 'AWS_MEDIA_LOCATION', 'media')
        self.s3_client = None
        self._initialize_s3_client()
    
    def _initialize_s3_client(self):
        """Initialize S3 client if credentials are available"""
        try:
            if self.bucket_name:
                # Try to initialize S3 client with different authentication methods
                access_key_id = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
                secret_access_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
                
                # Check if we have placeholder values and treat them as None
                if access_key_id in ['your_access_key_here', None, ''] or \
                   secret_access_key in ['your_secret_key_here', None, '']:
                    # Try IAM role-based authentication (no explicit credentials)
                    logger.info("Using IAM role-based authentication for S3")
                    from botocore.client import Config
                    self.s3_client = boto3.client(
                        's3',
                        region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'),
                        config=Config(signature_version='s3v4')
                    )
                else:
                    # Use explicit credentials
                    logger.info("Using explicit AWS credentials for S3")
                    from botocore.client import Config
                    self.s3_client = boto3.client(
                        's3',
                        aws_access_key_id=access_key_id,
                        aws_secret_access_key=secret_access_key,
                        region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'),
                        config=Config(signature_version='s3v4')
                    )
                
                # Test the connection
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.info(f"S3 client initialized successfully for bucket: {self.bucket_name}")
            else:
                logger.warning("No S3 bucket configured - S3 cleanup will be skipped")
        except Exception as e:
            logger.warning(f"S3 client initialization failed (S3 cleanup will be disabled): {str(e)}")
            self.s3_client = None
    
    def is_s3_storage(self) -> bool:
        """Check if S3 storage is being used"""
        default_storage_class = getattr(settings, 'DEFAULT_FILE_STORAGE', '')
        return 's3' in default_storage_class.lower() and self.s3_client is not None
    
    def delete_file(self, file_path: str) -> bool:
        """
        Delete a single file from S3
        
        Args:
            file_path: Path to the file in S3
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_s3_storage():
            logger.info(f"S3 storage not configured - skipping file deletion: {file_path}")
            return True
        
        if not file_path:
            return True
        
        try:
            # Remove leading slash if present
            if file_path.startswith('/'):
                file_path = file_path.lstrip('/')
            
            # Add media location prefix if not already present
            if not file_path.startswith(self.media_location):
                file_path = f"{self.media_location}/{file_path}"
            
            # Delete the file
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_path)
            logger.info(f"Successfully deleted S3 file: {file_path}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.info(f"File already deleted or doesn't exist: {file_path}")
                return True
            else:
                logger.error(f"Error deleting S3 file {file_path}: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error deleting S3 file {file_path}: {str(e)}")
            return False
    
    def delete_files(self, file_paths: List[str]) -> Dict[str, bool]:
        """
        Delete multiple files from S3
        
        Args:
            file_paths: List of file paths to delete
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        if not self.is_s3_storage():
            logger.info(f"S3 storage not configured - skipping {len(file_paths)} file deletions")
            return {path: True for path in file_paths}
        
        results = {}
        
        for file_path in file_paths:
            if file_path:
                results[file_path] = self.delete_file(file_path)
            else:
                results[file_path] = True
        
        successful_deletions = sum(1 for success in results.values() if success)
        logger.info(f"Deleted {successful_deletions}/{len(file_paths)} files from S3")
        
        return results
    
    def delete_directory_contents(self, directory_path: str) -> Dict[str, bool]:
        """
        Delete all files in a directory from S3
        
        Args:
            directory_path: Path to the directory in S3
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        if not self.is_s3_storage():
            logger.info(f"S3 storage not configured - skipping directory cleanup: {directory_path}")
            return {}
        
        if not directory_path:
            return {}
        
        try:
            # Remove leading slash if present
            if directory_path.startswith('/'):
                directory_path = directory_path.lstrip('/')
            
            # Add media location prefix if not already present
            if not directory_path.startswith(self.media_location):
                directory_path = f"{self.media_location}/{directory_path}"
            
            # Ensure directory path ends with /
            if not directory_path.endswith('/'):
                directory_path += '/'
            
            # List all objects with the directory prefix
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=directory_path)
            
            files_to_delete = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        files_to_delete.append(obj['Key'])
            
            if not files_to_delete:
                logger.info(f"No files found in S3 directory: {directory_path}")
                return {}
            
            # Delete all files in the directory
            results = {}
            for file_key in files_to_delete:
                try:
                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
                    results[file_key] = True
                    logger.info(f"Successfully deleted S3 file: {file_key}")
                except ClientError as e:
                    logger.error(f"Error deleting S3 file {file_key}: {str(e)}")
                    results[file_key] = False
            
            successful_deletions = sum(1 for success in results.values() if success)
            logger.info(f"Deleted {successful_deletions}/{len(files_to_delete)} files from S3 directory: {directory_path}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error cleaning up S3 directory {directory_path}: {str(e)}")
            return {}
    
    def cleanup_user_files(self, user_id: int) -> Dict[str, bool]:
        """
        Clean up all files associated with a user
        
        Args:
            user_id: ID of the user whose files should be deleted
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        logger.info(f"Starting S3 cleanup for user {user_id}")
        
        # Define user-specific directories to clean up
        user_directories = [
            f"user_files/{user_id}",
            f"profile_images/{user_id}",
            f"assignment_content/submissions/{user_id}",
            f"quiz_uploads/{user_id}",
            f"cv_files/{user_id}",
            f"statement_of_purpose_files/{user_id}",
            f"user_questionnaires/{user_id}",
            f"manual_assessments/{user_id}",
            f"vak_scores/{user_id}"
        ]
        
        all_results = {}
        
        for directory in user_directories:
            results = self.delete_directory_contents(directory)
            all_results.update(results)
        
        logger.info(f"Completed S3 cleanup for user {user_id}")
        return all_results
    
    def cleanup_course_files(self, course_id: int) -> Dict[str, bool]:
        """
        Clean up all files associated with a course
        
        Args:
            course_id: ID of the course whose files should be deleted
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        logger.info(f"Starting S3 cleanup for course {course_id}")
        
        # Define course-specific directories to clean up
        course_directories = [
            f"course_images/{course_id}",
            f"course_videos/{course_id}",
            f"courses/{course_id}",
            f"editor_uploads/courses/{course_id}",
            f"course_content/{course_id}",
            f"course_attachments/{course_id}",
            f"course_media/{course_id}"
        ]
        
        all_results = {}
        
        for directory in course_directories:
            results = self.delete_directory_contents(directory)
            all_results.update(results)
        
        logger.info(f"Completed S3 cleanup for course {course_id}")
        return all_results
    
    def cleanup_topic_files(self, topic_id: int) -> Dict[str, bool]:
        """
        Clean up all files associated with a topic
        
        Args:
            topic_id: ID of the topic whose files should be deleted
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        logger.info(f"Starting S3 cleanup for topic {topic_id}")
        
        all_results = {}
        
        # 1. Clean up topic-specific directories
        topic_directories = [
            f"topic_content/{topic_id}",
            f"topic_attachments/{topic_id}",
            f"topic_media/{topic_id}",
            f"editor_uploads/topics/{topic_id}",
            f"topic_files/{topic_id}"
        ]
        
        for directory in topic_directories:
            results = self.delete_directory_contents(directory)
            all_results.update(results)
        
        # Look for files that might be associated with this topic
        try:
            if self.is_s3_storage():
                search_patterns = [
                    f"topic_content/",  # Topic content
                ]
                
                for pattern in search_patterns:
                    try:
                        paginator = self.s3_client.get_paginator('list_objects_v2')
                        pages = paginator.paginate(
                            Bucket=self.bucket_name, 
                            Prefix=f"{self.media_location}/{pattern}"
                        )
                        
                        for page in pages:
                            if 'Contents' in page:
                                for obj in page['Contents']:
                                    key = obj['Key']
                                    # Check if this file might be related to our topic
                                    # Look for files that might be associated with this topic
                                    if (f"topic_{topic_id}" in key or 
                                        f"/{topic_id}/" in key or 
                                        key.endswith(f"/{topic_id}") or
                                        logger.info(f"Found potential topic-related file: {key}")
                                        result = self.delete_file(key)
                                        all_results[key] = result
                    except Exception as e:
                        logger.warning(f"Error searching for topic files in {pattern}: {e}")
        except Exception as e:
            logger.warning(f"Error in pattern-based topic file cleanup: {e}")
        
        logger.info(f"Completed S3 cleanup for topic {topic_id}")
        return all_results
    
        """
        with additional pattern-based scanning to catch orphaned files
        
        Args:
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        
        all_results = {}
        
        # 1. Delete specific package file if path provided
        if package_file_path:
            result = self.delete_file(package_file_path)
            all_results[package_file_path] = result
            
            # Also try to delete any potential variations of the package file path
            # This catches cases where the file was uploaded with a different name format
            if '/' in package_file_path:
                base_filename = package_file_path.split('/')[-1]
                alt_result = self.delete_file(alt_path)
                all_results[alt_path] = alt_result
                
                alt_result = self.delete_file(alt_path)
                all_results[alt_path] = alt_result
        
            # Primary directories
            
            # Alternate formats that might exist
            
            # Legacy formats
        ]
        
        if topic_id:
                # Primary topic directories
                
                # Alternate formats
                
                # Combined formats
            ])
        
        # 4. Clean up each directory
            results = self.delete_directory_contents(directory)
            all_results.update(results)
        
        # 5. ENHANCED: Try to find any orphaned files with package_id in the key
        try:
            if self.is_s3_storage():
                # Search for any keys containing the package ID
                
                
                for prefix in search_prefixes:
                    try:
                        paginator = self.s3_client.get_paginator('list_objects_v2')
                        pages = paginator.paginate(
                            Bucket=self.bucket_name, 
                            Prefix=f"{self.media_location}/{prefix}"
                        )
                        
                        for page in pages:
                            if 'Contents' in page:
                                for obj in page['Contents']:
                                    key = obj['Key']
                                    # Check if the key contains the package ID as a distinct segment
                                    if f"/{package_id_str}/" in key or f"_{package_id_str}/" in key or key.endswith(f"/{package_id_str}"):
                                        # This is likely an orphaned file related to this package
                                        result = self.delete_file(key)
                                        all_results[key] = result
                    except Exception as e:
                        logger.warning(f"Error searching for orphaned files in {prefix}: {e}")
        except Exception as e:
            logger.warning(f"Error in orphaned file cleanup: {e}")
        
        # 6. Log summary
        successful_deletions = sum(1 for success in all_results.values() if success)
        
        return all_results
    
    def cleanup_assignment_files(self, assignment_id: int) -> Dict[str, bool]:
        """
        Clean up all files associated with an assignment
        
        Args:
            assignment_id: ID of the assignment whose files should be deleted
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        logger.info(f"Starting S3 cleanup for assignment {assignment_id}")
        
        # Define assignment-specific directories to clean up
        assignment_directories = [
            f"assignment_content/assignments/{assignment_id}",
            f"assignment_content/submissions/{assignment_id}",
            f"assignment_attachments/{assignment_id}",
            f"assignment_files/{assignment_id}"
        ]
        
        all_results = {}
        
        for directory in assignment_directories:
            results = self.delete_directory_contents(directory)
            all_results.update(results)
        
        logger.info(f"Completed S3 cleanup for assignment {assignment_id}")
        return all_results
    
    def cleanup_quiz_files(self, quiz_id: int) -> Dict[str, bool]:
        """
        Clean up all files associated with a quiz
        
        Args:
            quiz_id: ID of the quiz whose files should be deleted
            
        Returns:
            Dict mapping file paths to deletion success status
        """
        logger.info(f"Starting S3 cleanup for quiz {quiz_id}")
        
        # Define quiz-specific directories to clean up
        quiz_directories = [
            f"quiz_uploads/{quiz_id}",
            f"quiz_attachments/{quiz_id}",
            f"quiz_media/{quiz_id}",
            f"quiz_files/{quiz_id}"
        ]
        
        all_results = {}
        
        for directory in quiz_directories:
            results = self.delete_directory_contents(directory)
            all_results.update(results)
        
        logger.info(f"Completed S3 cleanup for quiz {quiz_id}")
        return all_results
    
    def cleanup_content_file(self, content_file_path: str) -> bool:
        """
        Clean up a specific content file from S3
        
        Args:
            content_file_path: Path to the content file (as stored in database)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not content_file_path:
            return True
            
        logger.info(f"Cleaning up content file: {content_file_path}")
        
        # The content_file_path from database doesn't include 'media/' prefix
        # but S3 storage automatically adds it, so we need to handle this correctly
        try:
            # Try to delete the file as-is first (in case it's already the full path)
            result1 = self.delete_file(content_file_path)
            
            # Also try with media/ prefix (the actual S3 path)
            if not content_file_path.startswith('media/'):
                media_path = f"media/{content_file_path}"
                result2 = self.delete_file(media_path)
                
                # Return True if either deletion succeeded
                return result1 or result2
            else:
                return result1
                
        except Exception as e:
            logger.error(f"Error cleaning up content file {content_file_path}: {str(e)}")
            return False

# Global instance for easy access
s3_cleanup = S3CleanupManager()

def cleanup_s3_files(file_paths: List[str]) -> Dict[str, bool]:
    """
    Convenience function to delete multiple files from S3
    
    Args:
        file_paths: List of file paths to delete
        
    Returns:
        Dict mapping file paths to deletion success status
    """
    return s3_cleanup.delete_files(file_paths)

def cleanup_s3_directory(directory_path: str) -> Dict[str, bool]:
    """
    Convenience function to delete all files in a directory from S3
    
    Args:
        directory_path: Path to the directory in S3
        
    Returns:
        Dict mapping file paths to deletion success status
    """
    return s3_cleanup.delete_directory_contents(directory_path)

def cleanup_user_s3_files(user_id: int) -> Dict[str, bool]:
    """
    Convenience function to clean up all files associated with a user
    
    Args:
        user_id: ID of the user whose files should be deleted
        
    Returns:
        Dict mapping file paths to deletion success status
    """
    return s3_cleanup.cleanup_user_files(user_id)

def cleanup_course_s3_files(course_id: int) -> Dict[str, bool]:
    """
    Convenience function to clean up all files associated with a course
    
    Args:
        course_id: ID of the course whose files should be deleted
        
    Returns:
        Dict mapping file paths to deletion success status
    """
    return s3_cleanup.cleanup_course_files(course_id)

def cleanup_topic_s3_files(topic_id: int) -> Dict[str, bool]:
    """
    Convenience function to clean up all files associated with a topic
    
    Args:
        topic_id: ID of the topic whose files should be deleted
        
    Returns:
        Dict mapping file paths to deletion success status
    """
    return s3_cleanup.cleanup_topic_files(topic_id)

    """
    
    Args:
        
    Returns:
        Dict mapping file paths to deletion success status
    """

def cleanup_assignment_s3_files(assignment_id: int) -> Dict[str, bool]:
    """
    Convenience function to clean up all files associated with an assignment
    
    Args:
        assignment_id: ID of the assignment whose files should be deleted
        
    Returns:
        Dict mapping file paths to deletion success status
    """
    return s3_cleanup.cleanup_assignment_files(assignment_id)

def cleanup_quiz_s3_files(quiz_id: int) -> Dict[str, bool]:
    """
    Convenience function to clean up all files associated with a quiz
    
    Args:
        quiz_id: ID of the quiz whose files should be deleted
        
    Returns:
        Dict mapping file paths to deletion success status
    """
    return s3_cleanup.cleanup_quiz_files(quiz_id)

def cleanup_content_file_s3(content_file_path: str) -> bool:
    """
    Convenience function to clean up a specific content file from S3
    
    Args:
        content_file_path: Path to the content file (as stored in database)
        
    Returns:
        bool: True if successful, False otherwise
    """
    return s3_cleanup.cleanup_content_file(content_file_path)
