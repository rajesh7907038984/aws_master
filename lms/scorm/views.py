"""
SCORM Views
Handles SCORM content playback and API endpoint
"""
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.contrib import messages
from django.utils import timezone

from .models import ScormPackage, ScormAttempt
from .api_handler import ScormAPIHandler
from courses.models import Topic

logger = logging.getLogger(__name__)


@login_required
def scorm_player(request, topic_id):
    """
    SCORM content player view
    Displays SCORM content in an iframe with API wrapper
    """
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has permission to access this topic's course (enrollment check)
    if not topic.user_has_access(request.user):
        messages.error(request, "You don't have permission to access this content. Please enroll in the course first.")
        # Try to get the course to redirect appropriately
        try:
            from courses.models import CourseTopic
            course_topic = CourseTopic.objects.filter(topic=topic).first()
            if course_topic:
                return redirect('courses:course_view', course_id=course_topic.course.id)
        except Exception:
            pass
        return redirect('courses:course_list')
    
    # Check if topic has SCORM package
    try:
        scorm_package = topic.scorm_package
    except ScormPackage.DoesNotExist:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get or create attempt
    last_attempt = ScormAttempt.objects.filter(
        user=request.user,
        scorm_package=scorm_package
    ).order_by('-attempt_number').first()
    
    if last_attempt and last_attempt.lesson_status in ['completed', 'passed']:
        # Create new attempt if last one was completed
        attempt_number = last_attempt.attempt_number + 1
        attempt = ScormAttempt.objects.create(
            user=request.user,
            scorm_package=scorm_package,
            attempt_number=attempt_number
        )
    elif last_attempt:
        # Continue existing attempt
        attempt = last_attempt
    else:
        # Create first attempt
        attempt = ScormAttempt.objects.create(
            user=request.user,
            scorm_package=scorm_package,
            attempt_number=1
        )
    
    # Build launch URL through proxy to maintain same-origin policy for SCORM API access
    # Use the scorm_content proxy view to serve content from the same domain
    # This allows the SCORM content to access the API object in the parent window
    launch_url = f"/scorm/content/{attempt.id}/{scorm_package.launch_url}"
    logger.info(f"Generated proxied launch URL for SCORM package {scorm_package.id}, attempt {attempt.id}")
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'launch_url': launch_url,
        'api_endpoint': f'/scorm/api/{attempt.id}/',
    }
    
    return render(request, 'scorm/player.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def scorm_api(request, attempt_id):
    """
    SCORM API endpoint
    Handles all SCORM API calls from content
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt
        if attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Parse request
        data = json.loads(request.body)
        method = data.get('method')
        parameters = data.get('parameters', [])
        
        # Initialize API handler
        handler = ScormAPIHandler(attempt)
        
        # Route to appropriate API method
        if method == 'Initialize' or method == 'LMSInitialize':
            result = handler.initialize()
        elif method == 'Terminate' or method == 'LMSFinish':
            result = handler.terminate()
        elif method == 'GetValue' or method == 'LMSGetValue':
            element = parameters[0] if parameters else ''
            result = handler.get_value(element)
        elif method == 'SetValue' or method == 'LMSSetValue':
            element = parameters[0] if len(parameters) > 0 else ''
            value = parameters[1] if len(parameters) > 1 else ''
            result = handler.set_value(element, value)
        elif method == 'Commit' or method == 'LMSCommit':
            result = handler.commit()
        elif method == 'GetLastError' or method == 'LMSGetLastError':
            result = handler.get_last_error()
        elif method == 'GetErrorString' or method == 'LMSGetErrorString':
            error_code = parameters[0] if parameters else '0'
            result = handler.get_error_string(error_code)
        elif method == 'GetDiagnostic' or method == 'LMSGetDiagnostic':
            error_code = parameters[0] if parameters else '0'
            result = handler.get_diagnostic(error_code)
        else:
            return JsonResponse({
                'success': False,
                'error': f'Unknown method: {method}'
            })
        
        return JsonResponse({
            'success': True,
            'result': result,
            'error_code': handler.last_error
        })
        
    except Exception as e:
        logger.error(f"SCORM API error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def scorm_content(request, attempt_id, path):
    """
    Serve SCORM content files from S3
    Proxies content to maintain same-origin policy for API access
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt or is instructor/admin
        if attempt.user != request.user and not request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
            return HttpResponse('Unauthorized', status=403)
        
        # Build file path
        file_path = f"{attempt.scorm_package.extracted_path}/{path}"
        logger.info(f"Attempting to serve SCORM file: {file_path}")
        
        # Read file from S3 using storage backend's connection
        try:
            # Use the storage backend's S3 client to leverage existing configuration
            # Build full S3 key (with media prefix from storage location)
            s3_key = f"{default_storage.location}/{file_path}"
            
            # Get the S3 resource/client from storage backend
            # This avoids permission issues with HeadObject by using get_object directly
            s3_object = default_storage.bucket.Object(s3_key)
            
            # Get object directly (this only requires GetObject permission, not HeadObject)
            file_content = s3_object.get()['Body'].read()
            logger.info(f"Successfully read {len(file_content)} bytes from {s3_key}")
            
        except default_storage.bucket.meta.client.exceptions.NoSuchKey:
            logger.error(f"File not found in S3: {s3_key}")
            return HttpResponse('File not found', status=404)
        except Exception as open_error:
            logger.error(f"Error reading SCORM file from S3: {str(open_error)}")
            import traceback
            logger.error(traceback.format_exc())
            return HttpResponse(f'Error loading file: {str(open_error)}', status=500)
        
        # Determine content type
        content_type = 'application/octet-stream'
        if path.endswith('.html') or path.endswith('.htm'):
            content_type = 'text/html; charset=utf-8'
        elif path.endswith('.js'):
            content_type = 'application/javascript; charset=utf-8'
        elif path.endswith('.css'):
            content_type = 'text/css; charset=utf-8'
        elif path.endswith('.json'):
            content_type = 'application/json'
        elif path.endswith('.xml'):
            content_type = 'application/xml'
        elif path.endswith('.png'):
            content_type = 'image/png'
        elif path.endswith('.jpg') or path.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif path.endswith('.gif'):
            content_type = 'image/gif'
        elif path.endswith('.svg'):
            content_type = 'image/svg+xml'
        elif path.endswith('.mp4'):
            content_type = 'video/mp4'
        elif path.endswith('.mp3'):
            content_type = 'audio/mpeg'
        elif path.endswith('.woff') or path.endswith('.woff2'):
            content_type = 'font/woff'
        
        response = HttpResponse(file_content, content_type=content_type)
        
        # Allow iframe embedding and cross-origin requests (for fonts, etc)
        response['Access-Control-Allow-Origin'] = request.get_host()
        response['X-Frame-Options'] = 'SAMEORIGIN'
        
        return response
        
    except Exception as e:
        logger.error(f"Error serving SCORM content: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return HttpResponse('Error loading content', status=500)


@login_required
@require_http_methods(["GET"])
def scorm_status(request, attempt_id):
    """
    Get current SCORM attempt status
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt
        if attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        return JsonResponse({
            'success': True,
            'status': {
                'lesson_status': attempt.lesson_status,
                'completion_status': attempt.completion_status,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'total_time': attempt.total_time,
                'last_accessed': attempt.last_accessed.isoformat() if attempt.last_accessed else None,
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting SCORM status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

