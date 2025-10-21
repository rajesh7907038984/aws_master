from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, FileResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.utils import timezone
from django.conf import settings
import boto3
import os
from datetime import datetime, timedelta

from .models import MediaFile, StorageStatistics
from conferences.models import ConferenceFile
from reports.models import ReportAttachment
from branch_portal.models import SocialMediaIcon


@staff_member_required
def media_dashboard(request):
    """Main media library dashboard"""
    
    # Get filter parameters
    storage_type = request.GET.get('storage', 'all')
    file_type = request.GET.get('type', 'all')
    search = request.GET.get('search', '')
    
    # Build queryset
    files = MediaFile.objects.filter(is_active=True)
    
    if storage_type != 'all':
        files = files.filter(storage_type=storage_type)
    
    if file_type != 'all':
        files = files.filter(file_type=file_type)
    
    if search:
        files = files.filter(
            Q(filename__icontains=search) |
            Q(original_filename__icontains=search) |
            Q(description__icontains=search) |
            Q(tags__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(files, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get statistics
    stats = get_storage_statistics()
    
    # Get recent uploads
    recent_uploads = MediaFile.objects.filter(is_active=True).order_by('-uploaded_at')[:10]
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'recent_uploads': recent_uploads,
        'storage_type': storage_type,
        'file_type': file_type,
        'search': search,
        'storage_types': MediaFile.STORAGE_TYPES,
        'file_types': MediaFile.FILE_TYPES,
    }
    
    return render(request, 'media_library/dashboard.html', context)


@staff_member_required
def storage_statistics(request):
    """Detailed storage statistics page"""
    
    # Get current statistics
    stats = get_storage_statistics()
    
    # Get file type breakdown
    file_type_stats = MediaFile.objects.filter(is_active=True).values('file_type').annotate(
        count=Count('id'),
        total_size=Sum('file_size')
    ).order_by('-total_size')
    
    # Get storage type breakdown
    storage_stats = MediaFile.objects.filter(is_active=True).values('storage_type').annotate(
        count=Count('id'),
        total_size=Sum('file_size')
    ).order_by('-total_size')
    
    # Get recent activity
    recent_activity = MediaFile.objects.filter(is_active=True).order_by('-uploaded_at')[:20]
    
    # Get top uploaders
    top_uploaders = MediaFile.objects.filter(is_active=True).values(
        'uploaded_by__username', 'uploaded_by__first_name', 'uploaded_by__last_name'
    ).annotate(
        file_count=Count('id'),
        total_size=Sum('file_size')
    ).order_by('-file_count')[:10]
    
    context = {
        'stats': stats,
        'file_type_stats': file_type_stats,
        'storage_stats': storage_stats,
        'recent_activity': recent_activity,
        'top_uploaders': top_uploaders,
    }
    
    return render(request, 'media_library/statistics.html', context)


@staff_member_required
def file_browser(request):
    """File browser with folder-like structure"""
    
    # Get filter parameters
    storage_type = request.GET.get('storage', 'all')
    file_type = request.GET.get('type', 'all')
    path = request.GET.get('path', '')
    
    # Build queryset
    files = MediaFile.objects.filter(is_active=True)
    
    if storage_type != 'all':
        files = files.filter(storage_type=storage_type)
    
    if file_type != 'all':
        files = files.filter(file_type=file_type)
    
    if path:
        files = files.filter(file_path__startswith=path)
    
    # Group files by directory
    directories = {}
    for file in files:
        dir_path = os.path.dirname(file.file_path) if file.file_path else '/'
        if dir_path not in directories:
            directories[dir_path] = []
        directories[dir_path].append(file)
    
    context = {
        'directories': directories,
        'current_path': path,
        'storage_type': storage_type,
        'file_type': file_type,
        'storage_types': MediaFile.STORAGE_TYPES,
        'file_types': MediaFile.FILE_TYPES,
    }
    
    return render(request, 'media_library/browser.html', context)


@staff_member_required
def file_detail(request, file_id):
    """Detailed view of a specific file"""
    
    file_obj = get_object_or_404(MediaFile, id=file_id, is_active=True)
    
    # Update access count and last accessed
    file_obj.access_count += 1
    file_obj.last_accessed = timezone.now()
    file_obj.save(update_fields=['access_count', 'last_accessed'])
    
    # Get related files (same directory or similar)
    related_files = MediaFile.objects.filter(
        is_active=True,
        file_path__startswith=os.path.dirname(file_obj.file_path)
    ).exclude(id=file_id)[:5]
    
    context = {
        'file_obj': file_obj,
        'related_files': related_files,
    }
    
    return render(request, 'media_library/file_detail.html', context)


def get_storage_statistics():
    """Get current storage statistics"""
    
    # Get S3 statistics
    s3_stats, created = StorageStatistics.objects.get_or_create(
        storage_type='s3',
        defaults={'total_files': 0, 'total_size_bytes': 0}
    )
    
    # S3 storage only - no local statistics needed
    
    # Update statistics from actual data
    update_storage_statistics()
    
    return {
        's3': StorageStatistics.objects.get(storage_type='s3'),
    }


def update_storage_statistics():
    """Update storage statistics from actual data"""
    
    # Update S3 statistics
    s3_files = MediaFile.objects.filter(storage_type='s3', is_active=True)
    s3_stats, created = StorageStatistics.objects.get_or_create(storage_type='s3')
    
    s3_stats.total_files = s3_files.count()
    s3_stats.total_size_bytes = s3_files.aggregate(Sum('file_size'))['file_size__sum'] or 0
    
    # Update file type counts for S3
    s3_stats.image_count = s3_files.filter(file_type='image').count()
    s3_stats.video_count = s3_files.filter(file_type='video').count()
    s3_stats.audio_count = s3_files.filter(file_type='audio').count()
    s3_stats.document_count = s3_files.filter(file_type='document').count()
    s3_stats.archive_count = s3_files.filter(file_type='archive').count()
    s3_stats.other_count = s3_files.filter(file_type='other').count()
    
    s3_stats.last_updated = timezone.now()
    s3_stats.save()
    
    # S3 storage only - no local statistics to update


@staff_member_required
def sync_media_files(request):
    """Sync media files from existing models to MediaFile model"""
    
    if request.method == 'POST':
        try:
            # Sync Conference Files
            conference_files = ConferenceFile.objects.all()
            for cf in conference_files:
                MediaFile.objects.get_or_create(
                    file_path=cf.file_url if cf.file_url else '',
                    defaults={
                        'filename': cf.filename,
                        'original_filename': cf.original_filename,
                        'file_url': cf.file_url,
                        'file_size': cf.file_size or 0,
                        'file_type': get_file_type_from_mime(cf.mime_type),
                        'mime_type': cf.mime_type,
                        'storage_type': 's3' if cf.file_url else 'local',
                        'uploaded_by': cf.shared_by,
                        'uploaded_at': cf.shared_at or cf.created_at,
                        'source_app': 'conferences',
                        'source_model': 'ConferenceFile',
                        'source_id': cf.id,
                        'description': "Conference file: {{cf.conference.title}}",
                    }
                )
            
            # Sync Report Attachments
            report_attachments = ReportAttachment.objects.all()
            for ra in report_attachments:
                MediaFile.objects.get_or_create(
                    file_path=ra.file.name if ra.file else '',
                    defaults={
                        'filename': ra.filename,
                        'original_filename': ra.filename,
                        'file_size': ra.file.size if ra.file else 0,
                        'file_type': get_file_type_from_mime(ra.file_type),
                        'mime_type': ra.file_type,
                        'storage_type': 'local',
                        'uploaded_by': ra.report.created_by,
                        'uploaded_at': ra.uploaded_at,
                        'source_app': 'reports',
                        'source_model': 'ReportAttachment',
                        'source_id': ra.id,
                        'description': "Report attachment: {{ra.report.title}}",
                    }
                )
            
            # Update statistics
            update_storage_statistics()
            
            return JsonResponse({'success': True, 'message': 'Media files synced successfully'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': "Error syncing files: {{str(e)}}"})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@staff_member_required
def serve_s3_file(request, file_id):
    """Serve S3 media files"""
    
    file_obj = get_object_or_404(MediaFile, id=file_id, storage_type='s3', is_active=True)
    
    # S3 storage - use default storage
    from django.core.files.storage import default_storage
    try:
        # Get the file URL from S3
        file_url = default_storage.url(file_obj.file_path)
        
        # Update access count
        file_obj.access_count += 1
        file_obj.last_accessed = timezone.now()
        file_obj.save(update_fields=['access_count', 'last_accessed'])
        
        # Redirect to S3 URL
        return redirect(file_url)
    except Exception:
        raise Http404("File not found in S3")


@staff_member_required
def bulk_delete_files(request):
    """Bulk delete selected media files"""
    
    if request.method == 'POST':
        try:
            file_ids = request.POST.getlist('file_ids')
            
            if not file_ids:
                return JsonResponse({'success': False, 'message': 'No files selected'})
            
            # Convert string IDs to integers
            try:
                file_ids = [int(id) for id in file_ids]
            except ValueError:
                return JsonResponse({'success': False, 'message': 'Invalid file IDs'})
            
            # Get files to delete
            files_to_delete = MediaFile.objects.filter(id__in=file_ids, is_active=True)
            deleted_count = files_to_delete.count()
            
            if deleted_count == 0:
                return JsonResponse({'success': False, 'message': 'No valid files found to delete'})
            
            # Soft delete by setting is_active to False
            files_to_delete.update(is_active=False)
            
            # Update statistics
            update_storage_statistics()
            
            return JsonResponse({
                'success': True, 
                'message': "Successfully deleted {{deleted_count}} file(s)"
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': "Error deleting files: {{str(e)}}"})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


def get_file_type_from_mime(mime_type):
    """Determine file type from MIME type"""
    if not mime_type:
        return 'other'
    
    mime_type = mime_type.lower()
    
    if mime_type.startswith('image/'):
        return 'image'
    elif mime_type.startswith('video/'):
        return 'video'
    elif mime_type.startswith('audio/'):
        return 'audio'
    elif mime_type in ['application/pd", "application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        return 'document'
    elif mime_type in ['application/zip', 'application/x-rar-compressed', 'application/x-tar']:
        return 'archive'
    else:
        return 'other'