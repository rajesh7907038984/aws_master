"""
Enhanced SCORM Upload View with Improved Temporary File Management
This demonstrates how to use the enhanced temp file manager.
"""

import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from scorm_cloud.models import SCORMPackage, SCORMCloudContent
from scorm_cloud.utils.api import get_scorm_client, SCORMCloudError
from scorm_cloud.utils.temp_file_manager import temp_file_manager

logger = logging.getLogger(__name__)

@login_required
@require_POST
@csrf_protect
def enhanced_topic_scorm_upload(request):
    """
    Enhanced SCORM upload with robust temporary file management.
    
    Benefits:
    - Automatic cleanup with context manager
    - Orphaned file detection
    - Thread-safe operations
    - Better error handling
    - No S3 dependency
    """
    logger.info("=== Enhanced SCORM Topic Upload ===")
    logger.info(f"User: {request.user.username}")

    try:
        # Get the uploaded file
        file = request.FILES.get('scorm_file')
        if not file:
            return JsonResponse({
                'status': 'error',
                'message': 'No SCORM file provided',
                'field': 'scorm_file'
            }, status=400)

        # Get other required data
        topic_title = request.POST.get('topic_title', '').strip()
        topic_id = request.POST.get('topic_id')
        
        if not topic_title:
            return JsonResponse({
                'status': 'error',
                'message': 'Topic title is required',
                'field': 'topic_title'
            }, status=400)

        # Validate file
        if not file.name.lower().endswith('.zip'):
            return JsonResponse({
                'status': 'error',
                'message': 'Only ZIP files are allowed for SCORM packages.',
                'field': 'scorm_file'
            }, status=400)
            
        # Validate file size - maximum 1GB
        max_size = 1024 * 1024 * 1024  # 1GB
        if file.size > max_size:
            return JsonResponse({
                'status': 'error',
                'message': f'File size exceeds limit. Maximum size is 1GB, got {file.size/(1024*1024):.2f}MB',
                'field': 'scorm_file'
            }, status=400)

        logger.info(f"Processing SCORM upload for topic: {topic_title} (ID: {topic_id})")
        logger.info(f"File size: {file.size/(1024*1024):.2f}MB")

        # Check for duplicate package by title
        existing_package = SCORMPackage.objects.filter(title=topic_title).first()
        if existing_package:
            logger.info(f"Package with title '{topic_title}' already exists, using existing package")
            return JsonResponse({
                'status': 'success',
                'message': 'Using existing SCORM package',
                'package_id': str(existing_package.id),
                'cloud_id': existing_package.cloud_id,
                'launch_url': existing_package.launch_url,
                'package_title': existing_package.title,
                'topic_title': topic_title,
                'existing': True
            })

        # Generate unique SCORM Cloud course ID
        import uuid
        if topic_id:
            unique_id = uuid.uuid4().hex[:8]
            scorm_course_id = f"LMS_Topic_{topic_id}_{unique_id}"
        else:
            scorm_course_id = f"LMS_{uuid.uuid4().hex[:12]}"
        
        logger.info(f"Generated SCORM Course ID: {scorm_course_id}")

        # Use enhanced temporary file manager
        with temp_file_manager.create_temp_file(file, prefix="scorm_topic_") as temp_path:
            logger.info(f"Using temporary file: {temp_path}")
            
            # Upload to SCORM Cloud using branch-specific settings
            logger.info("Uploading to SCORM Cloud...")
            scorm_client = get_scorm_client(
                user=request.user, 
                branch=request.user.branch if hasattr(request.user, 'branch') else None
            )
            
            cloud_response = scorm_client.upload_package(
                temp_path,
                course_id=scorm_course_id,
                title=topic_title
            )
            
            if not cloud_response:
                raise SCORMCloudError("Failed to upload to SCORM Cloud - no response received")
                
            logger.info("SCORM Cloud upload successful")
            logger.debug(f"Cloud response: {cloud_response}")

            # Create package record
            package = SCORMPackage.objects.create(
                cloud_id=cloud_response.get('id', scorm_course_id),
                title=topic_title,
                description=f"SCORM content for topic {topic_id}" if topic_id else "Direct SCORM upload",
                version='1.2',
                launch_url=cloud_response.get('launch_url', ''),
                entry_url=cloud_response.get('entry_url', ''),
                use_frameset=True,
                launch_mode='window'
            )
            logger.info(f"Created SCORMPackage record with ID: {package.id}")

            # If we have a topic_id, create the SCORM content linking
            if topic_id:
                scorm_content, created = SCORMCloudContent.objects.update_or_create(
                    content_id=str(topic_id),
                    content_type='topic',
                    defaults={
                        'package': package,
                        'title': topic_title,
                        'description': f"SCORM content for topic {topic_id}",
                        'registration_prefix': f'LMS_{topic_id}_',
                        'passing_score': 80,
                        'requires_passing_score': True
                    }
                )
                logger.info(f"{'Created' if created else 'Updated'} SCORM content record for topic {topic_id}")

            # Temporary file is automatically cleaned up by context manager
            return JsonResponse({
                'status': 'success',
                'message': 'SCORM package uploaded successfully',
                'package_id': str(package.id),
                'cloud_id': package.cloud_id,
                'launch_url': package.launch_url,
                'package_title': package.title,
                'topic_title': topic_title,
                'temp_file_stats': temp_file_manager.get_stats()
            })

    except SCORMCloudError as e:
        logger.error(f"SCORM Cloud error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'SCORM Cloud upload failed: {str(e)}'
        }, status=500)
    except Exception as e:
        logger.error(f"Unexpected error in SCORM upload: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'An unexpected error occurred during upload'
        }, status=500)


@login_required
def scorm_temp_file_stats(request):
    """API endpoint to get temporary file statistics"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    stats = temp_file_manager.get_stats()
    return JsonResponse({
        'status': 'success',
        'stats': stats
    })


@login_required
@require_POST
def cleanup_orphaned_scorm_files(request):
    """Manual cleanup endpoint for orphaned SCORM temp files"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        temp_file_manager.cleanup_orphaned_files()
        stats = temp_file_manager.get_stats()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Orphaned files cleaned up successfully',
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error during manual cleanup: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Cleanup failed: {str(e)}'
        }, status=500)
