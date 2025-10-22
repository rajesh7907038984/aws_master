"""
Storage Management Views for Account Settings
Handles AJAX requests for branch storage limits management
"""

import json
import logging
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.utils import timezone
from django.core.files.storage import default_storage
from django.conf import settings

from core.models import BranchStorageLimit, FileStorageUsage
from core.utils.storage_manager import StorageManager
from branches.models import Branch

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def manage_branch_storage(request, branch_id):
    """
    Manage storage limits for a specific branch
    GET: Returns current storage info and limit settings
    POST: Updates storage limit settings
    """
    try:
        # Check if user is a global admin
        if request.user.role != 'globaladmin':
            return JsonResponse({
                'success': False,
                'error': 'Insufficient permissions. Global admin access required.'
            }, status=403)

        # Get the branch
        branch = get_object_or_404(Branch, id=branch_id)
        
        if request.method == 'GET':
            # Return current storage information
            storage_info = StorageManager.get_branch_storage_info(branch)
            
            # Get additional stats
            file_count = FileStorageUsage.objects.filter(
                user__branch=branch,
                is_deleted=False
            ).count()
            
            recent_uploads = FileStorageUsage.objects.filter(
                user__branch=branch,
                is_deleted=False
            ).select_related('user').order_by('-created_at')[:10]
            
            # Serialize recent uploads
            recent_uploads_data = []
            for upload in recent_uploads:
                recent_uploads_data.append({
                    'id': upload.id,
                    'filename': upload.original_filename,
                    'user': upload.user.get_full_name() or upload.user.username,
                    'size': upload.get_file_size_display(),
                    'size_bytes': upload.file_size_bytes,
                    'uploaded_at': upload.created_at.isoformat(),
                    'content_type': upload.content_type,
                    'source_app': upload.source_app,
                })
            
            # Get storage limit object for additional data
            storage_limit = storage_info['storage_limit']
            
            return JsonResponse({
                'success': True,
                'data': {
                    'branch_id': branch.id,
                    'branch_name': branch.name,
                    'storage_limit': storage_limit.storage_limit_bytes,
                    'storage_limit_display': storage_limit.get_limit_display(),
                    'warning_threshold_percent': storage_limit.warning_threshold_percent,
                    'current_usage_bytes': storage_info['current_usage_bytes'],
                    'current_usage_display': storage_info['current_usage_display'],
                    'limit_display': storage_info['limit_display'],
                    'usage_percentage': round(storage_info['usage_percentage'], 1),
                    'remaining_bytes': storage_info['remaining_bytes'],
                    'remaining_display': storage_info['remaining_display'],
                    'is_unlimited': storage_info['is_unlimited'],
                    'is_limit_exceeded': storage_info['is_limit_exceeded'],
                    'is_warning_threshold_exceeded': storage_info['is_warning_threshold_exceeded'],
                    'file_count': file_count,
                    'recent_uploads': recent_uploads_data,
                }
            })
        
        elif request.method == 'POST':
            # Update storage limit settings
            data = request.POST
            
            # Get or create storage limit record
            storage_limit, created = BranchStorageLimit.objects.get_or_create(
                branch=branch,
                defaults={
                    'storage_limit_bytes': 1073741824,  # 1GB default
                    'is_unlimited': False,
                    'warning_threshold_percent': 80,
                }
            )
            
            # Update settings
            if 'is_unlimited' in data:
                storage_limit.is_unlimited = data.get('is_unlimited') == 'on'
            
            if 'storage_limit' in data and not storage_limit.is_unlimited:
                try:
                    # Convert GB to bytes
                    storage_limit_gb = float(data['storage_limit'])
                    storage_limit_bytes = int(storage_limit_gb * 1024 * 1024 * 1024)
                    if storage_limit_bytes > 0:
                        storage_limit.storage_limit_bytes = storage_limit_bytes
                    else:
                        return JsonResponse({
                            'success': False,
                            'error': 'Storage limit must be greater than 0'
                        }, status=400)
                except (ValueError, TypeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid storage limit value'
                    }, status=400)
            
            if 'warning_threshold' in data:
                try:
                    threshold = int(data['warning_threshold'])
                    if 0 <= threshold <= 100:
                        storage_limit.warning_threshold_percent = threshold
                    else:
                        return JsonResponse({
                            'success': False,
                            'error': 'Warning threshold must be between 0 and 100'
                        }, status=400)
                except (ValueError, TypeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid warning threshold value'
                    }, status=400)
            
            storage_limit.save()
            
            logger.info(f"Storage limit updated for branch {branch.name} by user {request.user.username}")
            
            # Return updated storage information
            updated_info = StorageManager.get_branch_storage_info(branch)
            updated_storage_limit = updated_info['storage_limit']
            
            return JsonResponse({
                'success': True,
                'message': f'Storage settings updated for {branch.name}',
                'data': {
                    'branch_id': branch.id,
                    'storage_limit': updated_storage_limit.storage_limit_bytes,
                    'storage_limit_display': updated_storage_limit.get_limit_display(),
                    'warning_threshold_percent': updated_storage_limit.warning_threshold_percent,
                    'current_usage_bytes': updated_info['current_usage_bytes'],
                    'current_usage_display': updated_info['current_usage_display'],
                    'limit_display': updated_info['limit_display'],
                    'usage_percentage': round(updated_info['usage_percentage'], 1),
                    'remaining_bytes': updated_info['remaining_bytes'],
                    'remaining_display': updated_info['remaining_display'],
                    'is_unlimited': updated_info['is_unlimited'],
                }
            })
            
    except Exception as e:
        logger.error(f"Error in manage_branch_storage: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def storage_analytics(request):
    """
    Returns storage analytics data for dashboard
    """
    try:
        # Check if user is a global admin
        if request.user.role != 'globaladmin':
            return JsonResponse({
                'success': False,
                'error': 'Insufficient permissions'
            }, status=403)

        # Get overall storage statistics
        total_files = FileStorageUsage.objects.filter(is_deleted=False).count()
        total_size = FileStorageUsage.objects.filter(is_deleted=False).aggregate(
            total=Sum('file_size_bytes')
        )['total'] or 0
        
        # Get storage by branch
        branches = Branch.objects.all()
        branch_data = []
        
        for branch in branches:
            storage_info = StorageManager.get_branch_storage_info(branch)
            branch_data.append({
                'branch_id': branch.id,
                'branch_name': branch.name,
                'usage_bytes': storage_info['current_usage_bytes'],
                'usage_display': storage_info['current_usage_display'],
                'limit_bytes': storage_info['storage_limit'].storage_limit_bytes if storage_info['storage_limit'] else None,
                'is_unlimited': storage_info['is_unlimited'],
                'usage_percentage': round(storage_info['usage_percentage'], 1),
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'total_files': total_files,
                'total_size_bytes': total_size,
                'total_size_display': StorageManager._format_bytes(total_size),
                'branches': branch_data,
            }
        })
        
    except Exception as e:
        logger.error(f"Error in storage_analytics: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_storage_info(request):
    """
    Get storage information for the current user's branch
    """
    try:
        if not hasattr(request.user, 'branch') or not request.user.branch:
            return JsonResponse({
                'success': False,
                'error': 'User is not associated with any branch'
            }, status=400)

        branch = request.user.branch
        storage_info = StorageManager.get_branch_storage_info(branch)
        
        return JsonResponse({
            'success': True,
            'data': {
                'branch_name': branch.name,
                'current_usage_bytes': storage_info['current_usage_bytes'],
                'current_usage_display': storage_info['current_usage_display'],
                'limit_display': storage_info['limit_display'],
                'usage_percentage': round(storage_info['usage_percentage'], 1),
                'remaining_bytes': storage_info['remaining_bytes'],
                'remaining_display': storage_info['remaining_display'],
                'is_unlimited': storage_info['is_unlimited'],
                'is_limit_exceeded': storage_info['is_limit_exceeded'],
                'is_warning_threshold_exceeded': storage_info['is_warning_threshold_exceeded'],
            }
        })
        
    except Exception as e:
        logger.error(f"Error in get_storage_info: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def check_upload_permission(request):
    """
    Check if user can upload a file of specified size
    """
    try:
        data = json.loads(request.body)
        file_size = int(data.get('file_size', 0))
        
        if file_size <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Invalid file size'
            }, status=400)

        # Check upload permission
        can_upload, message = StorageManager.check_upload_permission(request.user, file_size)
        
        return JsonResponse({
            'success': True,
            'data': {
                'can_upload': can_upload,
                'message': message,
                'file_size': file_size,
                'file_size_display': StorageManager._format_bytes(file_size),
            }
        })
        
    except Exception as e:
        logger.error(f"Error in check_upload_permission: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def branch_storage_report(request, branch_id=None):
    """
    Generate a detailed storage report for a branch
    """
    try:
        # Determine which branch to report on
        if branch_id:
            # Global admin viewing specific branch
            if request.user.role != 'globaladmin':
                return JsonResponse({
                    'success': False,
                    'error': 'Insufficient permissions'
                }, status=403)
            branch = get_object_or_404(Branch, id=branch_id)
        else:
            # User viewing their own branch
            if not hasattr(request.user, 'branch') or not request.user.branch:
                return JsonResponse({
                    'success': False,
                    'error': 'User is not associated with any branch'
                }, status=400)
            branch = request.user.branch

        # Get storage information
        storage_info = StorageManager.get_branch_storage_info(branch)
        
        # Get file usage by app
        usage_by_app = FileStorageUsage.objects.filter(
            user__branch=branch,
            is_deleted=False
        ).values('source_app').annotate(
            total_files=Count('id'),
            total_size=Sum('file_size_bytes')
        ).order_by('-total_size')
        
        # Get top uploaders
        top_uploaders = FileStorageUsage.objects.filter(
            user__branch=branch,
            is_deleted=False
        ).values(
            'user__username', 'user__first_name', 'user__last_name'
        ).annotate(
            total_files=Count('id'),
            total_size=Sum('file_size_bytes')
        ).order_by('-total_size')[:10]
        
        # Format the data
        usage_by_app_data = []
        for item in usage_by_app:
            usage_by_app_data.append({
                'source_app': item['source_app'],
                'file_count': item['total_files'],
                'total_size_bytes': item['total_size'] or 0,
                'total_size_display': StorageManager._format_bytes(item['total_size'] or 0),
            })
        
        top_uploaders_data = []
        for item in top_uploaders:
            name = f"{item['user__first_name']} {item['user__last_name']}".strip()
            if not name:
                name = item['user__username']
            
            top_uploaders_data.append({
                'username': item['user__username'],
                'name': name,
                'file_count': item['total_files'],
                'total_size_bytes': item['total_size'] or 0,
                'total_size_display': StorageManager._format_bytes(item['total_size'] or 0),
            })

        return JsonResponse({
            'success': True,
            'data': {
                'branch': {
                    'id': branch.id,
                    'name': branch.name,
                },
                'storage_info': {
                    'current_usage_bytes': storage_info['current_usage_bytes'],
                    'current_usage_display': storage_info['current_usage_display'],
                    'limit_display': storage_info['limit_display'],
                    'usage_percentage': round(storage_info['usage_percentage'], 1),
                    'remaining_bytes': storage_info['remaining_bytes'],
                    'remaining_display': storage_info['remaining_display'],
                    'is_unlimited': storage_info['is_unlimited'],
                },
                'usage_by_app': usage_by_app_data,
                'top_uploaders': top_uploaders_data,
                'generated_at': timezone.now().isoformat(),
            }
        })
        
    except Exception as e:
        logger.error(f"Error in branch_storage_report: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)