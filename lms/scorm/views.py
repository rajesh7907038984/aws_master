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


def fix_scorm_relative_paths(html_content, topic_id):
    """
    Fix relative paths in SCORM content to use Django proxy URLs
    """
    base_content_url = f"/scorm/content/{topic_id}"
    
    # First, clean up any existing double paths
    double_path_patterns = [
        f"{base_content_url}//{base_content_url}/",
        f"{base_content_url}//{base_content_url}",
    ]
    
    for pattern in double_path_patterns:
        if pattern in html_content:
            html_content = html_content.replace(pattern, f"{base_content_url}/")
            logger.info(f"Cleaned double path: {pattern} -> {base_content_url}/")
    
    # Fix common SCORM relative paths - check each occurrence to avoid duplicate replacements
    path_fixes = [
        ('../scormcontent/', f'{base_content_url}/scormcontent/'),
        ('../scormdriver/', f'{base_content_url}/scormdriver/'),
    ]
    
    for old_path, new_path in path_fixes:
        # Only replace if the pattern exists and isn't already part of a fixed path
        # Use a more careful approach: don't replace if it's already in the context of base_content_url
        if old_path in html_content:
            # Check if this would create double paths
            if new_path not in html_content:
                html_content = html_content.replace(old_path, new_path)
                logger.info(f"Fixed relative path: {old_path} -> {new_path}")
    
    # Fix direct paths only if they don't already have the base URL prefix
    # This is more careful - we need to avoid replacing paths that are already fixed
    direct_path_fixes = [
        ('scormcontent/', f'{base_content_url}/scormcontent/'),
        ('scormdriver/', f'{base_content_url}/scormdriver/'),
    ]
    
    for old_path, new_path in direct_path_fixes:
        # Only replace standalone occurrences, not ones already prefixed with base_content_url
        # Use negative lookbehind concept: don't replace if preceded by base_content_url
        count_before = html_content.count(old_path)
        if count_before > 0:
            # Replace only occurrences that aren't already prefixed correctly
            import re
            # Match the path only if it's not already part of the fixed path
            pattern = re.compile(r'(?<!' + re.escape(base_content_url + '/') + r')' + re.escape(old_path))
            matches = pattern.findall(html_content)
            if matches:
                html_content = pattern.sub(new_path, html_content)
                logger.info(f"Fixed {len(matches)} direct path occurrences: {old_path} -> {new_path}")
    
    return html_content


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
    
    # Check if SCORM package file exists in storage
    from django.core.files.storage import default_storage
    if not scorm_package.package_file or not default_storage.exists(scorm_package.package_file.name):
        messages.error(request, "SCORM content files are missing. Please contact your administrator to re-upload the SCORM package.")
        logger.error(f"SCORM package file missing for topic {topic_id}, package {scorm_package.id}: {scorm_package.package_file}")
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
    
    # Generate content URL using Django proxy (for iframe compatibility)
    # Include attempt_id in the URL for API access
    content_url = f'/scorm/content/{topic_id}/{scorm_package.launch_url}?attempt_id={attempt_id}'
    
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
        
        # Use boto3 directly to fetch content (authenticated access)
        # Django storage prepends 'media/' automatically, but we need the full S3 path
        import boto3
        from django.conf import settings
        
        # Build the S3 key for the file (with media/ prefix for direct S3 access)
        s3_key = f"media/{scorm_package.extracted_path}/{path}"
        
        # Initialize S3 client
        s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        # For HTML files, we need to proxy to inject API
        if path.endswith(('.html', '.htm')):
            try:
                # Use boto3 to get the file content directly from S3
                try:
                    response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
                    content = response['Body'].read()
                    content_type = 'text/html; charset=utf-8'
                except Exception as e:
                    logger.error(f"Failed to get S3 object {s3_key}: {str(e)}")
                    return HttpResponse('SCORM content files are missing. Please contact your administrator to re-upload the SCORM package.', status=404)
                
                # Inject SCORM API for HTML files
                if 'text/html' in content_type:
                    html_content = content.decode('utf-8')
                    
                    # Inject SCORM API that connects to the real API endpoint
                    # Get attempt_id from the URL parameters
                    attempt_id = request.GET.get('attempt_id', 'preview')
                    api_endpoint = f'/scorm/api/{attempt_id}/'
                    api_injection = f'''
<script>
// SCORM API that connects to the real API endpoint
// CRITICAL: Uses SYNCHRONOUS XHR to support legacy SCORM content that expects immediate return values
window.API = window.API_1484_11 = {{
    _apiEndpoint: '{api_endpoint}',
    _lastError: '0',
    
    _getCookie: function(name) {{
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {{
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {{
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {{
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }}
            }}
        }}
        return cookieValue;
    }},
    
    _makeAPICall: function(method, parameters) {{
        try {{
            const xhr = new XMLHttpRequest();
            xhr.open('POST', this._apiEndpoint, false); // SYNCHRONOUS request
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', this._getCookie('csrftoken'));
            xhr.send(JSON.stringify({{ method: method, parameters: parameters || [] }}));
            
            if (xhr.status === 200) {{
                const data = JSON.parse(xhr.responseText);
                if (data.success) {{
                    console.log('[SCORM API] ' + method + ' -> ' + data.result);
                    return data.result;
                }} else {{
                    console.error('[SCORM API] ' + method + ' failed: ' + data.error);
                    this._lastError = '101';
                    return 'false';
                }}
            }} else {{
                console.error('[SCORM API] HTTP error: ' + xhr.status);
                this._lastError = '101';
                return 'false';
            }}
        }} catch (e) {{
            console.error('[SCORM API] Error:', e);
            this._lastError = '101';
            return 'false';
        }}
    }},
    
    Initialize: function(param) {{ 
        return this._makeAPICall('Initialize', [param]); 
    }},
    LMSInitialize: function(param) {{ 
        return this._makeAPICall('Initialize', [param]); 
    }},
    Terminate: function(param) {{ 
        return this._makeAPICall('Terminate', [param]); 
    }},
    LMSFinish: function(param) {{ 
        return this._makeAPICall('Terminate', [param]); 
    }},
    GetValue: function(element) {{ 
        return this._makeAPICall('GetValue', [element]); 
    }},
    LMSGetValue: function(element) {{ 
        return this._makeAPICall('GetValue', [element]); 
    }},
    SetValue: function(element, value) {{ 
        return this._makeAPICall('SetValue', [element, value]); 
    }},
    LMSSetValue: function(element, value) {{ 
        return this._makeAPICall('SetValue', [element, value]); 
    }},
    Commit: function(param) {{ 
        return this._makeAPICall('Commit', [param]); 
    }},
    LMSCommit: function(param) {{ 
        return this._makeAPICall('Commit', [param]); 
    }},
    GetLastError: function() {{ 
        return this._lastError; 
    }},
    LMSGetLastError: function() {{ 
        return this._lastError; 
    }},
    GetErrorString: function(code) {{ 
        return this._makeAPICall('GetErrorString', [code]); 
    }},
    LMSGetErrorString: function(code) {{ 
        return this._makeAPICall('GetErrorString', [code]); 
    }},
    GetDiagnostic: function(code) {{ 
        return this._makeAPICall('GetDiagnostic', [code]); 
    }},
    LMSGetDiagnostic: function(code) {{ 
        return this._makeAPICall('GetDiagnostic', [code]); 
    }}
}};
</script>
'''
                    
                    # Fix relative paths in SCORM content
                    html_content = fix_scorm_relative_paths(html_content, topic_id)
                    
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
                    
                    logger.info(f" Injected SCORM API into {path}")
                
                response_obj = HttpResponse(content, content_type=content_type)
                response_obj['Access-Control-Allow-Origin'] = '*'
                response_obj['X-Frame-Options'] = 'SAMEORIGIN'
                return response_obj
                
            except Exception as e:
                logger.error(f"Failed to fetch content: {str(e)}")
                return HttpResponse(f'Failed to load content: {str(e)}', status=502)
        else:
            # For non-HTML files, serve through boto3
            try:
                # Use boto3 to get the file content directly from S3
                try:
                    response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
                    content = response['Body'].read()
                    
                    # Determine content type based on file extension
                    import mimetypes
                    content_type, _ = mimetypes.guess_type(path)
                    if not content_type:
                        content_type = 'application/octet-stream'
                    
                    response_obj = HttpResponse(content, content_type=content_type)
                    response_obj['Access-Control-Allow-Origin'] = '*'
                    return response_obj
                except Exception as e:
                    logger.error(f"Failed to get S3 object {s3_key}: {str(e)}")
                    return HttpResponse('SCORM content files are missing. Please contact your administrator to re-upload the SCORM package.', status=404)
            except Exception as e:
                logger.error(f"Failed to serve content: {str(e)}")
                return HttpResponse(f'Failed to load content: {str(e)}', status=502)
            
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


@csrf_exempt
@require_http_methods(['POST'])
def scorm_emergency_save(request):
    '''
    Emergency save endpoint for SCORM data
    Used when browser is closing or user navigates away
    '''
    try:
        data = json.loads(request.body)
        attempt_id = data.get('attempt_id')
        
        if not attempt_id:
            return JsonResponse({'error': 'No attempt_id provided'}, status=400)
        
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt
        if request.user.is_authenticated and attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Force score sync
        from .score_sync_service import ScormScoreSyncService
        sync_result = ScormScoreSyncService.sync_score(attempt, force=True)
        
        logger.info(f'Emergency save for attempt {attempt_id}: sync_result={sync_result}')
        
        return JsonResponse({
            'success': True,
            'synced': sync_result,
            'message': 'Emergency save completed'
        })
        
    except Exception as e:
        logger.error(f'Emergency save error: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(['GET'])
def scorm_tracking_report(request, attempt_id):
    '''
    Comprehensive SCORM tracking report with all detailed data
    '''
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt or is instructor/admin
        if (attempt.user != request.user and 
            not (hasattr(request.user, 'role') and request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'])):
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Calculate time spent in different formats
        time_spent_hours = attempt.time_spent_seconds / 3600 if attempt.time_spent_seconds else 0
        time_spent_minutes = attempt.time_spent_seconds / 60 if attempt.time_spent_seconds else 0
        
        # Calculate session duration
        session_duration = None
        if attempt.session_start_time and attempt.session_end_time:
            session_duration = (attempt.session_end_time - attempt.session_start_time).total_seconds()
        elif attempt.session_start_time:
            session_duration = (timezone.now() - attempt.session_start_time).total_seconds()
        
        # Generate comprehensive report
        report = {
            'user_info': {
                'username': attempt.user.username,
                'full_name': attempt.user.get_full_name(),
                'email': attempt.user.email,
            },
            'course_info': {
                'topic_id': attempt.scorm_package.topic.id,
                'topic_title': attempt.scorm_package.topic.title,
                'scorm_package': attempt.scorm_package.title,
                'scorm_version': attempt.scorm_package.version,
            },
            'attempt_summary': {
                'attempt_id': attempt.id,
                'attempt_number': attempt.attempt_number,
                'lesson_status': attempt.lesson_status,
                'completion_status': attempt.completion_status,
                'success_status': attempt.success_status,
                'entry_mode': attempt.entry,
                'exit_mode': attempt.exit_mode,
            },
            'scoring_data': {
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'score_min': float(attempt.score_min) if attempt.score_min else 0,
                'score_max': float(attempt.score_max) if attempt.score_max else 100,
                'score_scaled': float(attempt.score_scaled) if attempt.score_scaled else None,
                'percentage_score': attempt.get_percentage_score(),
                'is_passed': attempt.is_passed(),
            },
            'time_tracking': {
                'total_time_scorm': attempt.total_time,
                'session_time_scorm': attempt.session_time,
                'time_spent_seconds': attempt.time_spent_seconds,
                'time_spent_hours': round(time_spent_hours, 2),
                'time_spent_minutes': round(time_spent_minutes, 2),
                'session_start_time': attempt.session_start_time.isoformat() if attempt.session_start_time else None,
                'session_end_time': attempt.session_end_time.isoformat() if attempt.session_end_time else None,
                'session_duration_seconds': session_duration,
                'started_at': attempt.started_at.isoformat(),
                'last_accessed': attempt.last_accessed.isoformat(),
                'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
            },
            'progress_tracking': {
                'lesson_location': attempt.lesson_location,
                'last_visited_slide': attempt.last_visited_slide,
                'progress_percentage': float(attempt.progress_percentage) if attempt.progress_percentage else 0,
                'completed_slides': attempt.completed_slides,
                'total_slides': attempt.total_slides,
                'suspend_data': attempt.suspend_data,
            },
            'navigation_history': attempt.navigation_history if attempt.navigation_history else [],
            'detailed_tracking': attempt.detailed_tracking if attempt.detailed_tracking else {},
            'session_data': attempt.session_data if attempt.session_data else {},
            'cmi_data': attempt.cmi_data if attempt.cmi_data else {},
        }
        
        return JsonResponse({
            'success': True,
            'tracking_report': report
        })
        
    except Exception as e:
        logger.error(f'Error generating SCORM tracking report: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

