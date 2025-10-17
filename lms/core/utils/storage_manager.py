"""
Storage Management Utilities for Branch-wise File Upload Limits
===============================================================

This module provides utilities for managing and enforcing branch-wise file upload limits.
It integrates with the existing file upload system to track usage and enforce limits.
"""

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from ..models import BranchStorageLimit, FileStorageUsage, StorageQuotaWarning
from branches.models import Branch
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class StorageManager:
    """Central manager for branch storage limits and usage tracking"""

    @classmethod
    def check_upload_permission(cls, user, file_size_bytes):
        """
        Check if a user can upload a file of given size.
        Returns: (can_upload: bool, error_message: str)
        """
        if not user or not user.branch:
            return False, "User must belong to a branch to upload files"
        
        # Get or create storage limits for the branch
        storage_limit = BranchStorageLimit.get_or_create_for_branch(user.branch)
        
        # Check if upload is allowed
        can_upload, error_message = storage_limit.can_upload_file(file_size_bytes)
        
        if not can_upload:
            logger.warning(f"Upload rejected for {user.username}: {error_message}")
        
        return can_upload, error_message

    @classmethod
    def register_file_upload(cls, user, file_path, original_filename, file_size_bytes, 
                           content_type=None, source_app=None, source_model=None, 
                           source_object_id=None, upload_session_id=None):
        """
        Register a successful file upload and update storage usage.
        """
        if not user or not user.branch:
            logger.error(f"Cannot register upload: user {user} has no branch")
            return None
        
        # Register the upload
        usage_record = FileStorageUsage.register_upload(
            user=user,
            file_path=file_path,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            content_type=content_type,
            source_app=source_app,
            source_model=source_model,
            source_object_id=source_object_id,
            upload_session_id=upload_session_id
        )
        
        # Check if we need to issue warnings
        cls._check_and_issue_warnings(user.branch, user)
        
        return usage_record

    @classmethod
    def _check_and_issue_warnings(cls, branch, triggered_by_user=None):
        """Check if storage warnings need to be issued for a branch"""
        try:
            storage_limit = BranchStorageLimit.get_or_create_for_branch(branch)
            
            # Skip if unlimited
            if storage_limit.is_unlimited:
                return
            
            current_usage = storage_limit.get_current_usage()
            usage_percentage = storage_limit.get_usage_percentage()
            
            # Check for limit exceeded
            if storage_limit.is_limit_exceeded():
                StorageQuotaWarning.create_warning(
                    branch=branch,
                    warning_type='limit',
                    usage_percentage=usage_percentage,
                    usage_bytes=current_usage,
                    limit_bytes=storage_limit.storage_limit_bytes,
                    triggered_by_user=triggered_by_user
                )
            
            # Check for warning threshold exceeded
            elif storage_limit.is_warning_threshold_exceeded():
                StorageQuotaWarning.create_warning(
                    branch=branch,
                    warning_type='threshold',
                    usage_percentage=usage_percentage,
                    usage_bytes=current_usage,
                    limit_bytes=storage_limit.storage_limit_bytes,
                    triggered_by_user=triggered_by_user
                )
                
        except Exception as e:
            logger.error(f"Error checking storage warnings for branch {branch.name}: {e}")

    @classmethod
    def get_branch_storage_info(cls, branch):
        """Get comprehensive storage information for a branch"""
        storage_limit = BranchStorageLimit.get_or_create_for_branch(branch)
        current_usage = storage_limit.get_current_usage()
        
        info = {
            'branch': branch,
            'storage_limit': storage_limit,
            'current_usage_bytes': current_usage,
            'current_usage_display': storage_limit.get_usage_display(current_usage),
            'limit_display': storage_limit.get_limit_display(),
            'usage_percentage': storage_limit.get_usage_percentage(),
            'remaining_bytes': storage_limit.get_remaining_storage(),
            'remaining_display': storage_limit.get_usage_display(storage_limit.get_remaining_storage()) if not storage_limit.is_unlimited else 'Unlimited',
            'is_limit_exceeded': storage_limit.is_limit_exceeded(),
            'is_warning_threshold_exceeded': storage_limit.is_warning_threshold_exceeded(),
            'is_unlimited': storage_limit.is_unlimited,
        }
        
        return info

    @classmethod
    def get_user_storage_info(cls, user):
        """Get storage information for a specific user's branch"""
        if not user.branch:
            return None
        
        return cls.get_branch_storage_info(user.branch)

    @classmethod
    def mark_file_as_deleted(cls, file_path, user=None):
        """Mark a file as deleted in storage tracking"""
        try:
            usage_records = FileStorageUsage.objects.filter(
                file_path=file_path,
                is_deleted=False
            )
            
            if user:
                usage_records = usage_records.filter(user=user)
            
            for record in usage_records:
                record.mark_as_deleted()
                logger.info(f"Marked file as deleted: {file_path}")
            
            return usage_records.count()
            
        except Exception as e:
            logger.error(f"Error marking file as deleted: {file_path} - {e}")
            return 0

    @classmethod
    def cleanup_s3_orphaned_files(cls, dry_run=True):
        """Clean up orphaned files in S3 that are not tracked in database"""
        from core.utils.s3_cleanup import S3CleanupManager
        
        s3_cleanup = S3CleanupManager()
        
        if not s3_cleanup.is_s3_storage():
            logger.info("S3 storage not configured - skipping orphaned file cleanup")
            return 0
        
        try:
            # Get all tracked file paths
            tracked_paths = set(FileStorageUsage.objects.filter(
                is_deleted=False
            ).values_list('file_path', flat=True))
            
            # Find orphaned files in S3
            orphaned_files = s3_cleanup.find_orphaned_files(tracked_paths)
            
            if not dry_run:
                # Delete orphaned files
                results = s3_cleanup.delete_files(orphaned_files)
                successful_deletions = sum(1 for success in results.values() if success)
                logger.info(f"Cleaned up {successful_deletions} orphaned S3 files")
                return successful_deletions
            else:
                logger.info(f"[DRY RUN] Found {len(orphaned_files)} orphaned S3 files")
                return len(orphaned_files)
                
        except Exception as e:
            logger.error(f"Error during S3 orphaned file cleanup: {e}")
            return 0

    @classmethod
    def get_s3_cleanup_status(cls):
        """Get S3 cleanup status and statistics"""
        from core.utils.s3_cleanup import S3CleanupManager
        
        s3_cleanup = S3CleanupManager()
        
        if not s3_cleanup.is_s3_storage():
            return {
                's3_configured': False,
                'message': 'S3 storage not configured'
            }
        
        try:
            from django.conf import settings
            # Get S3 cleanup statistics
            stats = {
                's3_configured': True,
                'bucket_name': getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'Not configured'),
                'region': getattr(settings, 'AWS_S3_REGION_NAME', 'Not configured'),
                'total_tracked_files': FileStorageUsage.objects.filter(is_deleted=False).count(),
                'total_deleted_files': FileStorageUsage.objects.filter(is_deleted=True).count(),
                'cleanup_available': True
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting S3 cleanup status: {e}")
            return {
                's3_configured': True,
                'error': str(e)
            }

    @classmethod
    def cleanup_deleted_files(cls, dry_run=True):
        """Clean up file records for files that no longer exist in S3"""
        from core.s3_storage import MediaS3Storage
        
        deleted_count = 0
        usage_records = FileStorageUsage.objects.filter(is_deleted=False)
        s3_storage = MediaS3Storage()
        
        for record in usage_records:
            try:
                # Use S3-specific exists check with proper error handling
                if not s3_storage.exists(record.file_path):
                    if not dry_run:
                        record.mark_as_deleted()
                    deleted_count += 1
                    logger.info(f"{'[DRY RUN] ' if dry_run else ''}S3 file not found, marking as deleted: {record.file_path}")
            except Exception as e:
                logger.error(f"Error checking S3 file {record.file_path}: {e}")
                if not dry_run:
                    record.mark_as_deleted()
                deleted_count += 1
        
        return deleted_count

    @classmethod
    def get_top_storage_consuming_branches(cls, limit=10):
        """Get branches with highest storage usage"""
        from django.db.models import Sum
        
        branch_usage = []
        
        for branch in Branch.objects.all():
            usage = FileStorageUsage.objects.filter(
                user__branch=branch,
                is_deleted=False
            ).aggregate(
                total_bytes=Sum('file_size_bytes')
            )['total_bytes'] or 0
            
            if usage > 0:
                branch_usage.append({
                    'branch': branch,
                    'usage_bytes': usage,
                    'usage_display': BranchStorageLimit.get_or_create_for_branch(branch).get_usage_display(usage)
                })
        
        # Sort by usage and return top consumers
        branch_usage.sort(key=lambda x: x['usage_bytes'], reverse=True)
        return branch_usage[:limit]

    @classmethod
    def get_storage_analytics(cls, days=30):
        """Get storage usage analytics for the last N days"""
        from datetime import timedelta
        from django.db.models import Count
        
        start_date = timezone.now() - timedelta(days=days)
        
        analytics = {
            'total_files_uploaded': FileStorageUsage.objects.filter(
                created_at__gte=start_date,
                is_deleted=False
            ).count(),
            'total_bytes_uploaded': FileStorageUsage.objects.filter(
                created_at__gte=start_date,
                is_deleted=False
            ).aggregate(
                total=Sum('file_size_bytes')
            )['total'] or 0,
            'active_branches_count': Branch.objects.filter(
                users__file_storage_usage__created_at__gte=start_date,
                users__file_storage_usage__is_deleted=False
            ).distinct().count(),
            'warnings_issued': StorageQuotaWarning.objects.filter(
                created_at__gte=start_date
            ).count(),
            'limits_exceeded': StorageQuotaWarning.objects.filter(
                created_at__gte=start_date,
                warning_type='limit'
            ).count(),
        }
        
        return analytics

    @classmethod
    def get_s3_storage_analytics(cls, days=30):
        """Get S3-specific storage analytics"""
        from datetime import timedelta
        from django.db.models import Count
        from django.conf import settings
        from core.utils.s3_cleanup import S3CleanupManager
        
        start_date = timezone.now() - timedelta(days=days)
        s3_cleanup = S3CleanupManager()
        
        analytics = {
            's3_configured': s3_cleanup.is_s3_storage(),
            's3_bucket_name': getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'Not configured'),
            's3_region': getattr(settings, 'AWS_S3_REGION_NAME', 'Not configured'),
            's3_media_url': getattr(settings, 'MEDIA_URL', 'Not configured'),
            'total_s3_files': FileStorageUsage.objects.filter(
                created_at__gte=start_date,
                is_deleted=False
            ).count(),
            's3_usage_by_module': cls._get_s3_usage_by_module(days),
            's3_storage_classes': {
                'media': 'MediaS3Storage',
                'static': 'StaticS3Storage', 
                'scorm': 'SCORMS3Storage',
            }
        }
        
        return analytics

    @classmethod
    def _get_s3_usage_by_module(cls, days=30):
        """Get S3 usage breakdown by module"""
        from datetime import timedelta
        from django.db.models import Count, Sum
        
        start_date = timezone.now() - timedelta(days=days)
        
        usage_by_module = FileStorageUsage.objects.filter(
            created_at__gte=start_date,
            is_deleted=False
        ).values('source_app').annotate(
            total_files=Count('id'),
            total_size=Sum('file_size_bytes')
        ).order_by('-total_size')
        
        return list(usage_by_module)

    @staticmethod
    def _format_bytes(bytes_value):
        """Format bytes into human readable format"""
        if bytes_value is None or bytes_value == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        
        return f"{bytes_value:.1f} PB"


class StorageQuotaDecorator:
    """Decorator to check storage quota before file upload operations"""
    
    def __init__(self, source_app=None):
        self.source_app = source_app
    
    def __call__(self, func):
        def wrapper(request, *args, **kwargs):
            # Only apply to POST requests with files
            if request.method != 'POST' or not request.FILES:
                return func(request, *args, **kwargs)
            
            # Check user and branch
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                from django.http import JsonResponse
                return JsonResponse({
                    'success': False,
                    'error': 'Authentication required'
                }, status=401)
            
            # Calculate total upload size
            total_size = sum(file.size for file in request.FILES.values())
            
            # Check storage permission
            can_upload, error_message = StorageManager.check_upload_permission(
                request.user, total_size
            )
            
            if not can_upload:
                from django.http import JsonResponse
                return JsonResponse({
                    'success': False,
                    'error': error_message,
                    'storage_limit_exceeded': True
                }, status=403)
            
            # Proceed with the original function
            response = func(request, *args, **kwargs)
            
            # If upload was successful, register the files
            if hasattr(response, 'status_code') and response.status_code == 200:
                for field_name, file in request.FILES.items():
                    StorageManager.register_file_upload(
                        user=request.user,
                        file_path=file.name,  # This might need to be the actual saved path
                        original_filename=file.name,
                        file_size_bytes=file.size,
                        content_type=file.content_type,
                        source_app=self.source_app,
                    )
            
            return response
        
        return wrapper


# Convenience function for checking storage before upload
def check_storage_before_upload(user, file_size_bytes):
    """
    Convenience function to check storage before upload.
    Returns: (can_upload: bool, error_message: str, storage_info: dict)
    """
    can_upload, error_message = StorageManager.check_upload_permission(user, file_size_bytes)
    storage_info = StorageManager.get_user_storage_info(user) if user.branch else None
    
    return can_upload, error_message, storage_info
