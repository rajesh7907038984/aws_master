"""
SCORM Views - Clean Consolidated Implementation
Handles SCORM content playback with both simple and advanced tracking options
"""
import json
import logging
import os
import uuid
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.files.storage import default_storage
from django.contrib import messages
from django.utils import timezone
from django.conf import settings

from .models import ScormPackage, ScormAttempt
from .api_handler import ScormAPIHandler
from .preview_handler import ScormPreviewHandler
from .s3_direct import scorm_s3
from courses.models import Topic

logger = logging.getLogger(__name__)


@login_required
def scorm_view(request, topic_id):
    """
    Main SCORM content viewer
    Supports both simple and advanced tracking modes
    """
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has permission to access this topic's course
    if not topic.user_has_access(request.user):
        messages.error(request, "You need to be enrolled in this course to access the SCORM content.")
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
    
    # Check for preview mode
    preview_mode = request.GET.get('preview', '').lower() == 'true'
    is_instructor_or_admin = request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']
    
    # Allow preview mode only for instructors/admins
    if preview_mode and not is_instructor_or_admin:
        messages.error(request, "Preview mode is only available for instructors and administrators.")
        preview_mode = False
    
    # Handle attempt creation/retrieval
    attempt = None
    attempt_id = None
    
    if preview_mode:
        # Preview mode: Create temporary attempt object
        attempt_id = f"preview_{uuid.uuid4()}"
        attempt = type('PreviewAttempt', (), {
            'id': attempt_id,
            'user': request.user,
            'scorm_package': scorm_package,
            'attempt_number': 1,
            'lesson_status': 'not_attempted',
            'completion_status': 'incomplete',
            'success_status': 'unknown',
            'score_raw': None,
            'score_max': 100,
            'score_min': 0,
            'score_scaled': None,
            'total_time': '0000:00:00.00',
            'session_time': '0000:00:00.00',
            'lesson_location': '',
            'suspend_data': '',
            'entry': 'ab-initio',
            'exit_mode': '',
            'cmi_data': {},
            'started_at': timezone.now(),
            'last_accessed': timezone.now(),
            'completed_at': None,
            'is_preview': True,
        })()
        
        # Store preview attempt in session for API access
        request.session[f'scorm_preview_{attempt_id}'] = {
            'id': attempt_id,
            'user_id': request.user.id,
            'scorm_package_id': scorm_package.id,
            'is_preview': True,
            'created_at': timezone.now().isoformat(),
        }
        
        logger.info(f"Created preview attempt {attempt_id} for user {request.user.username} on topic {topic_id}")
    else:
        # Normal mode: Get or create actual database attempt for user tracking
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
        attempt_id = attempt.id
        attempt.is_preview = False  # Mark as real attempt
    
    # Generate content URL using S3 direct access
    content_url = scorm_s3.generate_launch_url(scorm_package)
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'attempt_id': attempt_id,
        'content_url': content_url,
        'api_endpoint': f'/scorm/api/{attempt_id}/',
        'preview_mode': preview_mode,
        'is_instructor_or_admin': is_instructor_or_admin,
    }
    
    response = render(request, 'scorm/player.html', context)
    
    # Set permissive CSP headers for SCORM content
    response['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "worker-src 'self' blob: data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "style-src 'self' 'unsafe-inline' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "img-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "font-src 'self' data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "connect-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "media-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "frame-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "object-src 'none'"
    )
    
    response['X-Frame-Options'] = 'SAMEORIGIN'
    response['Access-Control-Allow-Origin'] = '*'
    
    return response


@csrf_exempt
@require_http_methods(["POST"])
def scorm_api(request, attempt_id):
    """
    SCORM API endpoint
    Handles all SCORM API calls from content
    Supports both regular attempts and preview mode
    """
    try:
        # Check if this is a preview attempt first
        session_key = f'scorm_preview_{attempt_id}'
        is_preview = session_key in request.session
        
        if is_preview:
            # Preview mode: Create temporary attempt from session data
            preview_data = request.session[session_key]
            
            # Reconstruct the attempt object for preview
            scorm_package = get_object_or_404(ScormPackage, id=preview_data['scorm_package_id'])
            attempt = type('PreviewAttempt', (), {
                'id': attempt_id,
                'user': request.user,
                'scorm_package': scorm_package,
                'attempt_number': 1,
                'lesson_status': 'not_attempted',
                'completion_status': 'incomplete',
                'success_status': 'unknown',
                'score_raw': None,
                'score_max': 100,
                'score_min': 0,
                'score_scaled': None,
                'total_time': '0000:00:00.00',
                'session_time': '0000:00:00.00',
                'lesson_location': '',
                'suspend_data': '',
                'entry': 'ab-initio',
                'exit_mode': '',
                'cmi_data': {},
                'started_at': timezone.now(),
                'last_accessed': timezone.now(),
                'completed_at': None,
                'is_preview': True,
            })()
            
            # Verify user owns this preview attempt
            if preview_data['user_id'] != request.user.id:
                return JsonResponse({'error': 'Unauthorized'}, status=403)
                
        else:
            # Regular mode: Get database attempt
            attempt = get_object_or_404(ScormAttempt, id=attempt_id)
            
            # Verify user owns this attempt
            if attempt.user != request.user:
                return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Parse request
        data = json.loads(request.body)
        method = data.get('method')
        parameters = data.get('parameters', [])
        
        # Initialize appropriate API handler
        if is_preview:
            handler = ScormPreviewHandler(attempt)
            logger.info(f"Using preview handler for attempt {attempt_id}")
        else:
            handler = ScormAPIHandler(attempt)
            logger.info(f"Using regular handler for attempt {attempt_id}")
        
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


def scorm_content(request, topic_id, path):
    """
    Serve SCORM content files from S3
    Proxies content to maintain same-origin policy for API access
    """
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        
        # Check if topic has SCORM package
        try:
            scorm_package = topic.scorm_package
        except ScormPackage.DoesNotExist:
            return HttpResponse('SCORM package not found', status=404)
        
        # Generate direct S3 URL
        s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        
        # For HTML files, we need to proxy to inject API
        if path.endswith(('.html', '.htm')):
            try:
                import requests
                response = requests.get(s3_url, timeout=10)
                response.raise_for_status()
                
                content = response.content
                content_type = response.headers.get('content-type', 'text/html; charset=utf-8')
                
                # Inject SCORM API for HTML files
                if 'text/html' in content_type:
                    try:
                        html_content = content.decode('utf-8')
                        
                        # Inject SCORM API stub
                        api_injection = '''
<script>
// SCORM API Stub for Content
window.API = window.API_1484_11 = {
    Initialize: function(param) { return "true"; },
    LMSInitialize: function(param) { return "true"; },
    Terminate: function(param) { return "true"; },
    LMSFinish: function(param) { return "true"; },
    GetValue: function(element) {
        switch(element) {
            case 'cmi.core.lesson_status':
            case 'cmi.completion_status':
                return 'incomplete';
            case 'cmi.core.student_id':
            case 'cmi.learner_id':
                return 'student';
            case 'cmi.core.student_name':
            case 'cmi.learner_name':
                return 'Student';
            case 'cmi.core.score.max':
            case 'cmi.score.max':
                return '100';
            case 'cmi.core.score.min':
            case 'cmi.score.min':
                return '0';
            case 'cmi.mode':
                return 'normal';
            default:
                return '';
        }
    },
    LMSGetValue: function(element) { return this.GetValue(element); },
    SetValue: function(element, value) { return "true"; },
    LMSSetValue: function(element, value) { return this.SetValue(element, value); },
    Commit: function(param) { return "true"; },
    LMSCommit: function(param) { return "true"; },
    GetLastError: function() { return "0"; },
    LMSGetLastError: function() { return "0"; },
    GetErrorString: function(code) { return "No error"; },
    LMSGetErrorString: function(code) { return "No error"; },
    GetDiagnostic: function(code) { return "No error"; },
    LMSGetDiagnostic: function(code) { return "No error"; }
};
</script>
'''
                        
                        # Inject before </head> or at beginning of <body>
                        if '</head>' in html_content:
                            html_content = html_content.replace('</head>', api_injection + '</head>')
                        elif '<body' in html_content:
                            import re
                            html_content = re.sub(r'(<body[^>]*>)', r'\1' + api_injection, html_content)
                        else:
                            html_content = api_injection + html_content
                        
                        content = html_content.encode('utf-8')
                        content_type = 'text/html; charset=utf-8'
                        
                        logger.info(f"✅ Injected SCORM API into {path}")
                    
                response_obj = HttpResponse(content, content_type=content_type)
                response_obj['Access-Control-Allow-Origin'] = '*'
                response_obj['X-Frame-Options'] = 'SAMEORIGIN'
                return response_obj
                
            except requests.RequestException as e:
                logger.error(f"Failed to fetch S3 content: {str(e)}")
                return HttpResponse(f'Failed to load content: {str(e)}', status=502)
        else:
            # For non-HTML files, redirect to S3
            return redirect(s3_url)
            
    except Exception as e:
        logger.error(f"Error serving SCORM content: {str(e)}")
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


@login_required
@require_http_methods(["GET"])
def scorm_debug(request, attempt_id):
    """
    SCORM diagnostic endpoint for troubleshooting
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt or is instructor/admin
        if attempt.user != request.user and not request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        debug_info = {
            'attempt_info': {
                'id': attempt.id,
                'user': attempt.user.username,
                'package_id': attempt.scorm_package.id,
                'package_title': attempt.scorm_package.title,
                'version': attempt.scorm_package.version,
                'extracted_path': attempt.scorm_package.extracted_path,
                'launch_url': attempt.scorm_package.launch_url,
                'created_at': attempt.started_at.isoformat(),
                'last_accessed': attempt.last_accessed.isoformat(),
            },
            'urls': {
                'content_url': scorm_s3.generate_launch_url(attempt.scorm_package),
                'api_endpoint': f'/scorm/api/{attempt_id}/',
            },
            'manifest_data': attempt.scorm_package.manifest_data,
        }
        
        return JsonResponse({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        logger.error(f"Error in SCORM debug endpoint: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
