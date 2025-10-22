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
    def cleanup_deleted_files(cls, dry_run=True):
        """Clean up file records for files that no longer exist on disk"""
        import os
        from django.conf import settings
        
        deleted_count = 0
        usage_records = FileStorageUsage.objects.filter(is_deleted=False)
        
        for record in usage_records:
            # Use S3 permission-safe approach - avoid exists() that triggers HeadObject
            from django.core.files.storage import default_storage
            
            try:
                # Try to open file instead of checking existence
                test_file = default_storage.open(record.file_path)
                test_file.close()
                # File exists and accessible
            except Exception as file_error:
                # File doesn't exist or permission denied
                file_missing = True
                if "403" in str(file_error) or "Forbidden" in str(file_error):
                    logger.warning(f"S3 permission denied for file {record.file_path}: {file_error}")
                    # Don't mark as deleted if it's just a permission issue
                    continue
                elif "NoSuchKey" in str(file_error) or "not found" in str(file_error):
                    if not dry_run:
                        record.mark_as_deleted()
                    deleted_count += 1
                    logger.info(f"{'[DRY RUN] ' if dry_run else ''}File not found, marking as deleted: {record.file_path}")
                else:
                    logger.error(f"Error accessing file {record.file_path}: {file_error}")
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
