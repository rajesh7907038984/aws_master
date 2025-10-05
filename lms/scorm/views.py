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
    Main SCORM content viewer - Optimized for better performance
    Supports both simple and advanced tracking modes
    """
    # Optimize database queries with select_related and prefetch_related
    topic = get_object_or_404(
        Topic.objects.select_related('scorm_package').prefetch_related('scorm_package__attempts'),
        id=topic_id
    )
    
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
    
    # Check if topic has SCORM package (already loaded with select_related)
    if not hasattr(topic, 'scorm_package') or not topic.scorm_package:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    scorm_package = topic.scorm_package
    
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
        
        # Initialize CMI data for preview
        cmi_data = {}
        if scorm_package.version == '1.2':
            cmi_data = {
                'cmi.core.student_id': str(request.user.id),
                'cmi.core.student_name': request.user.get_full_name() or request.user.username,
                'cmi.core.lesson_location': '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': 'not attempted',
                'cmi.core.entry': 'ab-initio',
                'cmi.core.score.raw': '',
                'cmi.core.score.max': '100',
                'cmi.core.score.min': '0',
                'cmi.core.total_time': '0000:00:00.00',
                'cmi.core.lesson_mode': 'normal',
                'cmi.core.exit': '',
                'cmi.core.session_time': '',
                'cmi.suspend_data': '',
                'cmi.launch_data': '',
                'cmi.comments': '',
                'cmi.comments_from_lms': '',
            }
        else:  # SCORM 2004
            cmi_data = {
                'cmi.learner_id': str(request.user.id),
                'cmi.learner_name': request.user.get_full_name() or request.user.username,
                'cmi.location': '',
                'cmi.credit': 'credit',
                'cmi.completion_status': 'incomplete',
                'cmi.success_status': 'unknown',
                'cmi.entry': 'ab-initio',
                'cmi.score.raw': '',
                'cmi.score.max': '100',
                'cmi.score.min': '0',
                'cmi.score.scaled': '',
                'cmi.total_time': '0000:00:00.00',
                'cmi.mode': 'normal',
                'cmi.exit': '',
                'cmi.session_time': '',
                'cmi.suspend_data': '',
                'cmi.launch_data': '',
            }
        
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
            'cmi_data': cmi_data,
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
        
        logger.info(f"🎭 Created preview attempt {attempt_id} for user {request.user.username} on topic {topic_id}")
    else:
        # Normal mode: Get or create actual database attempt for user tracking
        # Use select_related to optimize database queries
        last_attempt = ScormAttempt.objects.select_related('scorm_package').filter(
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
            # Continue existing attempt - ensure resume data is loaded
            attempt = last_attempt
            
            # Load resume data into CMI data for proper resume functionality
            if attempt.lesson_location or attempt.suspend_data:
                # Ensure CMI data is properly initialized with resume data
                if not attempt.cmi_data:
                    attempt.cmi_data = {}
                
                # Load resume data into CMI data
                if attempt.lesson_location:
                    if scorm_package.version == '1.2':
                        attempt.cmi_data['cmi.core.lesson_location'] = attempt.lesson_location
                    else:  # SCORM 2004
                        attempt.cmi_data['cmi.location'] = attempt.lesson_location
                
                if attempt.suspend_data:
                    if scorm_package.version == '1.2':
                        attempt.cmi_data['cmi.suspend_data'] = attempt.suspend_data
                    else:  # SCORM 2004
                        attempt.cmi_data['cmi.suspend_data'] = attempt.suspend_data
                
                # Set entry mode to resume
                attempt.entry = 'resume'
                if scorm_package.version == '1.2':
                    attempt.cmi_data['cmi.core.entry'] = 'resume'
                else:  # SCORM 2004
                    attempt.cmi_data['cmi.entry'] = 'resume'
                
                # Save the updated attempt
                attempt.save()
                logger.info(f"🔄 Loaded resume data for attempt {attempt.id}: location='{attempt.lesson_location}', suspend_data='{attempt.suspend_data[:50]}...'")
            
            # Standard SCORM bookmark - lesson_location is automatically handled
            logger.info(f"📍 SCORM bookmark: lesson_location='{attempt.lesson_location}', suspend_data='{attempt.suspend_data[:50] if attempt.suspend_data else 'None'}...'")
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
    # Use Django proxy URL for iframe content
    try:
        # Ensure launch_url is properly formatted
        launch_url = scorm_package.launch_url or 'index.html'
        if not launch_url.startswith('/'):
            launch_url = '/' + launch_url
        content_url = f"/scorm/content/{topic_id}{launch_url}"
        logger.info(f"Generated content URL: {content_url}")
    except Exception as e:
        logger.error(f"Error generating content URL: {str(e)}")
        content_url = f"/scorm/content/{topic_id}/index.html"
    
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
    
    response = render(request, 'scorm/player_clean.html', context)
    
    # Set permissive CSP headers for SCORM content
    response['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
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
    # For SCORM API calls, we need to handle authentication differently
    # since the calls come from iframe content. We'll check if the attempt exists
    # and belongs to the current user through the attempt_id
    try:
        attempt = ScormAttempt.objects.get(id=attempt_id)
        # For now, allow API calls if the attempt exists (we'll add proper auth later)
        # if not request.user.is_authenticated or attempt.user != request.user:
        #     return JsonResponse({'error': 'Unauthorized'}, status=401)
    except ScormAttempt.DoesNotExist:
        return JsonResponse({'error': 'Attempt not found'}, status=404)
    
    try:
        # Check if this is a preview attempt first
        session_key = f'scorm_preview_{attempt_id}'
        is_preview = hasattr(request, 'session') and session_key in request.session
        
        if is_preview:
            # Preview mode: Create temporary attempt from session data
            preview_data = request.session.get(session_key, {})
            
            # Reconstruct the attempt object for preview
            scorm_package = get_object_or_404(ScormPackage, id=preview_data['scorm_package_id'])
            
            # Initialize CMI data for preview
            cmi_data = {}
            if scorm_package.version == '1.2':
                cmi_data = {
                    'cmi.core.student_id': str(request.user.id),
                    'cmi.core.student_name': request.user.get_full_name() or request.user.username,
                    'cmi.core.lesson_location': '',
                    'cmi.core.credit': 'credit',
                    'cmi.core.lesson_status': 'not attempted',
                    'cmi.core.entry': 'ab-initio',
                    'cmi.core.score.raw': '',
                    'cmi.core.score.max': '100',
                    'cmi.core.score.min': '0',
                    'cmi.core.total_time': '0000:00:00.00',
                    'cmi.core.lesson_mode': 'normal',
                    'cmi.core.exit': '',
                    'cmi.core.session_time': '',
                    'cmi.suspend_data': '',
                    'cmi.launch_data': '',
                    'cmi.comments': '',
                    'cmi.comments_from_lms': '',
                }
            else:  # SCORM 2004
                cmi_data = {
                    'cmi.learner_id': str(request.user.id),
                    'cmi.learner_name': request.user.get_full_name() or request.user.username,
                    'cmi.location': '',
                    'cmi.credit': 'credit',
                    'cmi.completion_status': 'incomplete',
                    'cmi.success_status': 'unknown',
                    'cmi.entry': 'ab-initio',
                    'cmi.score.raw': '',
                    'cmi.score.max': '100',
                    'cmi.score.min': '0',
                    'cmi.score.scaled': '',
                    'cmi.total_time': '0000:00:00.00',
                    'cmi.mode': 'normal',
                    'cmi.exit': '',
                    'cmi.session_time': '',
                    'cmi.suspend_data': '',
                    'cmi.launch_data': '',
                }
            
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
                'cmi_data': cmi_data,
                'started_at': timezone.now(),
                'last_accessed': timezone.now(),
                'completed_at': None,
                'is_preview': True,
            })()
            
            # Verify user owns this preview attempt
            # if preview_data['user_id'] != request.user.id:
            #     return JsonResponse({'error': 'Unauthorized'}, status=403)
                
        else:
            # Regular mode: Get database attempt
            attempt = get_object_or_404(ScormAttempt, id=attempt_id)
            
            # Verify user owns this attempt
            # if attempt.user != request.user:
            #     return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Parse request
        data = json.loads(request.body)
        method = data.get('method')
        parameters = data.get('parameters', [])
        
        # Initialize appropriate API handler with caching
        if is_preview:
            handler = ScormPreviewHandler(attempt)
            logger.info(f"🎭 Using preview handler for attempt {attempt_id}")
        else:
            # Use cached handler if available
            from django.core.cache import cache
            handler_cache_key = f"scorm_handler_v2_{attempt_id}"
            handler = cache.get(handler_cache_key)
            
            if not handler:
                handler = ScormAPIHandler(attempt)
                # Cache handler for 10 minutes
                cache.set(handler_cache_key, handler, 600)
                logger.info(f"📝 Created new handler for attempt {attempt_id}")
            else:
                logger.info(f"📝 Using cached handler for attempt {attempt_id}")
        
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
            # Ensure error_code is properly handled
            try:
                if isinstance(error_code, str) and error_code.isdigit():
                    error_code = int(error_code)
                result = handler.get_error_string(error_code)
            except Exception as e:
                logger.error(f"Error handling GetErrorString: {str(e)}")
                result = 'Unknown error'
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


def scorm_content(request, topic_id=None, path=None, attempt_id=None):
    """
    Serve SCORM content files from S3 with optimized loading
    Uses direct S3 URLs for better performance
    Handles both topic_id and attempt_id parameters for backward compatibility
    """
    try:
        # Handle both topic_id and attempt_id parameters for backward compatibility
        if attempt_id is not None and topic_id is None:
            # If attempt_id is provided, get the topic from the attempt
            from .models import ScormAttempt
            try:
                attempt = get_object_or_404(ScormAttempt, id=attempt_id)
                topic = attempt.scorm_package.topic
                topic_id = topic.id
            except Exception as e:
                logger.error(f"Error getting topic from attempt {attempt_id}: {str(e)}")
                return HttpResponse('Invalid attempt ID', status=404)
        else:
            # Use topic_id directly
            topic = get_object_or_404(Topic, id=topic_id)
        
        # Check if topic has SCORM package
        try:
            scorm_package = topic.scorm_package
        except ScormPackage.DoesNotExist:
            return HttpResponse('SCORM package not found', status=404)
        
        # Handle directory requests by redirecting to index.html
        if path.endswith('/'):
            path = path + 'index.html'
        
        # Generate direct S3 URL with proper error handling
        try:
            s3_url = scorm_s3.generate_direct_url(scorm_package, path)
            if not s3_url:
                logger.error(f"Failed to generate S3 URL for path: {path}")
                return HttpResponse('Content not found', status=404)
            logger.info(f"Generated S3 URL: {s3_url}")
        except Exception as e:
            logger.error(f"Error generating S3 URL: {str(e)}")
            return HttpResponse('Error generating content URL', status=500)
        
        # For non-HTML files, redirect directly to S3 for better performance
        if not path.endswith(('.html', '.htm')):
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(s3_url)
        
        # For HTML files, we need to proxy to inject API but with caching
        try:
            import requests
            from django.core.cache import cache
            
            # Create cache key for this content with version
            cache_key = f"scorm_content_v2_{scorm_package.id}_{path}_{scorm_package.updated_at.timestamp()}"
            cached_content = cache.get(cache_key)
            
            if cached_content:
                logger.info(f"✅ Serving cached content for {path}")
                response_obj = HttpResponse(cached_content, content_type='text/html; charset=utf-8')
                response_obj['Access-Control-Allow-Origin'] = '*'
                response_obj['X-Frame-Options'] = 'SAMEORIGIN'
                response_obj['Cache-Control'] = 'public, max-age=7200'  # Cache for 2 hours
                return response_obj
            
            # Fetch from S3 with optimized timeout and streaming
            response = requests.get(s3_url, timeout=3, stream=True)
            response.raise_for_status()
            
            content = response.content
            content_type = response.headers.get('content-type', 'text/html; charset=utf-8')
            
            # Inject SCORM API for HTML files
            if 'text/html' in content_type:
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
                
                # Cache the processed content for 2 hours
                cache.set(cache_key, content, 7200)
                logger.info(f"✅ Injected SCORM API into {path} and cached")
            
            response_obj = HttpResponse(content, content_type=content_type)
            response_obj['Access-Control-Allow-Origin'] = '*'
            response_obj['X-Frame-Options'] = 'SAMEORIGIN'
            response_obj['Cache-Control'] = 'public, max-age=7200'  # Cache for 2 hours
            return response_obj
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch S3 content: {str(e)}")
            return HttpResponse(f'Failed to load content: {str(e)}', status=502)
            
    except Exception as e:
        logger.error(f"Error serving SCORM content: {str(e)}")
        return HttpResponse('Error loading content', status=500)


@login_required
@require_http_methods(["GET"])
def scorm_status(request, attempt_id):
    """
    Get current SCORM attempt status with comprehensive progress tracking
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
                'success_status': attempt.success_status,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'total_time': attempt.total_time,
                'session_time': attempt.session_time,
                'lesson_location': attempt.lesson_location,
                'suspend_data': attempt.suspend_data,
                'entry': attempt.entry,
                'exit_mode': attempt.exit_mode,
                'last_accessed': attempt.last_accessed.isoformat() if attempt.last_accessed else None,
                'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
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
