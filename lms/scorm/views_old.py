"""
SCORM Views
Handles SCORM content playback and API endpoint
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

from .models import ScormPackage, ScormAttempt
from .api_handler import ScormAPIHandler
from .preview_handler import ScormPreviewHandler
from courses.models import Topic

logger = logging.getLogger(__name__)


def _modernize_javascript_content(content):
    """
    Modernize deprecated JavaScript patterns in SCORM content
    
    Replaces deprecated unload event listeners with modern equivalents:
    - window.onunload -> window.onbeforeunload + window.onpagehide
    - addEventListener("unload", ...) -> addEventListener("beforeunload", ...) + addEventListener("pagehide", ...)
    - attachEvent("onunload", ...) -> attachEvent("onbeforeunload", ...) + attachEvent("onpagehide", ...)
    """
    try:
        import re
        
        # Track if we made any changes
        original_content = content
        
        # Pattern 1: Replace window.onunload assignments
        # window.onunload = function() { ... } -> window.onbeforeunload = function() { ... }; window.onpagehide = function() { ... }
        unload_assignment_pattern = r'(window\.onunload\s*=\s*)(function[^}]*\}[^;]*;?)'
        matches = re.finditer(unload_assignment_pattern, content, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            old_assignment = match.group(0)
            func_part = match.group(2)
            
            # Remove any trailing semicolon from func_part to prevent double semicolons
            if func_part.rstrip().endswith(';'):
                func_part = func_part.rstrip()[:-1]
            
            # Create modern replacement
            new_assignment = "window.onbeforeunload = {};\nwindow.onpagehide = {};".format(func_part, func_part)
            
            content = content.replace(old_assignment, new_assignment)
        
        # Pattern 2: Replace addEventListener("unload", ...)
        # addEventListener("unload", handler) -> addEventListener("beforeunload", handler); addEventListener("pagehide", handler)
        unload_listener_pattern = r'(\w+\.)?addEventListener\s*\(\s*["\']unload["\']\s*,\s*([^)]+)\)'
        matches = re.finditer(unload_listener_pattern, content, re.IGNORECASE)
        
        for match in matches:
            old_listener = match.group(0)
            target = match.group(1) or 'window.'
            handler = match.group(2)
            
            # Remove any trailing semicolon from handler to prevent double semicolons
            if handler.rstrip().endswith(';'):
                handler = handler.rstrip()[:-1]
            
            # Create modern replacement
            new_listener = "{}addEventListener(\"beforeunload\", {});\n{}addEventListener(\"pagehide\", {})".format(target, handler, target, handler)
            
            content = content.replace(old_listener, new_listener)
        
        # Pattern 3: Replace attachEvent("onunload", ...) for IE compatibility
        unload_attach_pattern = r'(\w+\.)?attachEvent\s*\(\s*["\']onunload["\']\s*,\s*([^)]+)\)'
        matches = re.finditer(unload_attach_pattern, content, re.IGNORECASE)
        
        for match in matches:
            old_attach = match.group(0)
            target = match.group(1) or 'window.'
            handler = match.group(2)
            
            # Remove any trailing semicolon from handler to prevent double semicolons
            if handler.rstrip().endswith(';'):
                handler = handler.rstrip()[:-1]
            
            # Create modern replacement
            new_attach = "{}attachEvent(\"onbeforeunload\", {});\n{}attachEvent(\"onpagehide\", {})".format(target, handler, target, handler)
            
            content = content.replace(old_attach, new_attach)
        
        # Pattern 4: Handle string-based event assignments like obj.onunload = "functionName()"
        string_unload_pattern = r'(\.onunload\s*=\s*["\'][^"\']+["\'])'
        matches = re.finditer(string_unload_pattern, content, re.IGNORECASE)
        
        for match in matches:
            old_assignment = match.group(0)
            # Extract the string part
            string_part = old_assignment.split('=')[1].strip()
            obj_part = old_assignment.split('=')[0].strip()
            
            # Remove any trailing semicolon to prevent double semicolons
            if string_part.rstrip().endswith(';'):
                string_part = string_part.rstrip()[:-1]
            
            # Create modern replacement
            new_assignment = "{} = {};\n{} = {}".format(
                obj_part.replace('onunload', 'onbeforeunload'), string_part,
                obj_part.replace('onunload', 'onpagehide'), string_part
            )
            
            content = content.replace(old_assignment, new_assignment)
        
        # Pattern 5: Handle inline HTML event attributes like <body onunload="handler()">
        # This is the most common source of deprecated unload warnings in SCORM content
        
        # Simple approach: If onbeforeunload exists, remove onunload (it's redundant and deprecated)
        if 'onbeforeunload' in content.lower():
            # Remove onunload attributes when onbeforeunload is already present
            content = re.sub(r'\s+onunload\s*=\s*["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
        else:
            # If no onbeforeunload exists, replace onunload with both onbeforeunload and onpagehide
            unload_attr_pattern = r'(\s+onunload\s*=\s*["\'])([^"\']*?)(["\'])'
            
            def replace_unload_attr(match):
                prefix = match.group(1)
                handler = match.group(2)
                suffix = match.group(3)
                
                # Replace with modern equivalents
                return ' onbeforeunload="{}" onpagehide="{}"'.format(handler, handler)
            
            content = re.sub(unload_attr_pattern, replace_unload_attr, content, flags=re.IGNORECASE)
        
        # Log if we made changes
        if content != original_content:
            logger.info("Modernized deprecated unload event listeners in SCORM content")
            
        return content
        
    except Exception as e:
        logger.warning("Error modernizing JavaScript content: {}".format(e))
        return content


@login_required
def scorm_player(request, topic_id):
    """
    SCORM content player view
    Displays SCORM content in an iframe with API wrapper
    Supports preview mode for instructors/admins
    """
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check for preview mode
    preview_mode = request.GET.get('preview', '').lower() == 'true'
    is_instructor_or_admin = request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']
    
    # Allow preview mode only for instructors/admins
    if preview_mode and not is_instructor_or_admin:
        messages.error(request, "Preview mode is only available for instructors and administrators.")
        preview_mode = False
    
    # Check if user has permission to access this topic's course
    if not topic.user_has_access(request.user):
        messages.error(request, "You need to be enrolled in this course to access the SCORM content.")
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
    
    # Handle preview mode vs normal tracking
    if preview_mode:
        # Preview mode: Create a temporary attempt object and store in session
        from uuid import uuid4
        preview_id = str(uuid4())
        
        # Create temporary attempt object
        attempt = type('PreviewAttempt', (), {
            'id': preview_id,
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
        request.session['scorm_preview_{}'.format(preview_id)] = {
            'id': preview_id,
            'user_id': request.user.id,
            'scorm_package_id': scorm_package.id,
            'is_preview': True,
            'created_at': timezone.now().isoformat(),
        }
        
        logger.info("Created preview attempt {} for user {} on topic {}".format(preview_id, request.user.username, topic_id))
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
        attempt.is_preview = False  # Mark as real attempt
    
    # Build launch URL through proxy to maintain same-origin policy for SCORM API access
    # Use the scorm_content proxy view to serve content from the same domain
    # This allows the SCORM content to access the API object in the parent window
    launch_url = "/scorm/content/{}/{}".format(attempt.id, scorm_package.launch_url)
    logger.info("Generated proxied launch URL for SCORM package {}, attempt {}".format(scorm_package.id, attempt.id))
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'launch_url': launch_url,
        'api_endpoint': '/scorm/api/{}/'.format(attempt.id),
        'preview_mode': preview_mode,
        'is_instructor_or_admin': is_instructor_or_admin,
    }
    
    # Render the response
    response = render(request, 'scorm/player.html', context)
    
    # REMOVE RESTRICTIVE SECURITY HEADERS FOR SCORM PLAYER
    # This is necessary for SCORM content to work with all types of packages
    
    # AGGRESSIVELY REMOVE ALL CSP HEADERS FOR SCORM (SCORM needs eval and inline scripts)
    csp_headers = ['Content-Security-Policy', 'Content-Security-Policy-Report-Only', 'X-Content-Security-Policy']
    for header in csp_headers:
        if header in response:
            del response[header]
            logger.info(f"Removed {header} for SCORM player: topic {topic_id}")
    
    # SIMPLE CSP FOR MAXIMUM CROSS-BROWSER COMPATIBILITY
    response['Content-Security-Policy'] = (
        "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "script-src * 'unsafe-inline' 'unsafe-eval'; "
        "style-src * 'unsafe-inline'; "
        "img-src * data: blob:; "
        "font-src * data:; "
        "connect-src *; "
        "media-src * data: blob:; "
        "frame-src *"
    )
    logger.info(f"Set permissive CSP with unsafe-eval for SCORM player: topic {topic_id}")
    
    # Allow iframe embedding from same origin (needed for nested SCORM content)
    response['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Disable XSS protection (SCORM content may use patterns that trigger false positives)
    response['X-XSS-Protection'] = '0'
    
    # Allow CORS for SCORM resources
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    
    # Remove content type sniffing restrictions (SCORM content may have unusual mime types)
    if 'X-Content-Type-Options' in response:
        del response['X-Content-Type-Options']
    
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
        session_key = 'scorm_preview_{}'.format(attempt_id)
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
            logger.info("Using preview handler for attempt {}".format(attempt_id))
        else:
            handler = ScormAPIHandler(attempt)
            logger.info("Using regular handler for attempt {}".format(attempt_id))
        
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
                'error': 'Unknown method: {}'.format(method)
            })
        
        return JsonResponse({
            'success': True,
            'result': result,
            'error_code': handler.last_error
        })
        
    except Exception as e:
        logger.error("SCORM API error: {}".format(str(e)))
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def scorm_content(request, attempt_id, path):
    """
    Serve SCORM content files from S3
    Proxies content to maintain same-origin policy for API access
    
    Note: This endpoint doesn't use @login_required because iframe requests
    may not properly pass session cookies. Instead, we use the attempt_id
    as a temporary access token and verify ownership through the database.
    """
    try:
        # Try to get a regular attempt first
        attempt = None
        is_preview = False
        
        try:
            attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        except:
            # If not found, check if this is a preview mode attempt (stored in session)
            session_key = 'scorm_preview_{}'.format(attempt_id)
            if session_key in request.session:
                # Create temporary attempt object from session data
                preview_data = request.session[session_key]
                
                # Get the actual ScormPackage from database
                from scorm.models import ScormPackage
                scorm_package = get_object_or_404(ScormPackage, id=preview_data['scorm_package_id'])
                
                # Create temporary attempt object
                attempt = type('PreviewAttempt', (), {
                    'id': attempt_id,
                    'scorm_package': scorm_package,
                    'user_id': preview_data['user_id'],
                    'is_preview': True,
                })()
                is_preview = True
            else:
                return HttpResponse('Attempt not found', status=404)
        
        # For authenticated users, verify ownership or admin privileges
        if request.user.is_authenticated:
            user_id = attempt.user.id if hasattr(attempt, 'user') else attempt.user_id
            if user_id != request.user.id and not request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
                return HttpResponse('Unauthorized: You do not own this SCORM attempt', status=403)
        else:
            # For unauthenticated requests, allow access but log for security monitoring
            # The attempt_id serves as a temporary access token
            logger.warning("Unauthenticated SCORM content access for attempt {} from IP {}".format(attempt_id, request.META.get('REMOTE_ADDR')))
            
            # Optional: Add rate limiting or additional security checks here
            # For now, we allow access since attempt_id is a UUID providing reasonable security
        
        # Build file path - note that MediaS3Storage automatically adds 'media/' prefix
        # So the stored path in extracted_path is 'scorm_content/{id}' 
        # and the full S3 path becomes 'media/scorm_content/{id}/filename'
        file_path = "{}/{}".format(attempt.scorm_package.extracted_path, path)
        logger.info("[SCORM Content] Attempting to serve file: {}".format(file_path))
        logger.info("[SCORM Content] Request from: {} (Attempt ID: {})".format(request.user.username, attempt_id))
        
        # Try to read file from S3 first, then fallback to local storage
        file_content = None
        file_source = "unknown"
        
        try:
            # First try direct S3 access using boto3 (more reliable than Django storage)
            import boto3
            from django.conf import settings
            
            s3_client = boto3.client('s3', region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'))
            bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'lms-staging-nexsy-io')
            
            # The file is stored with 'media/' prefix in S3
            s3_key = "media/{}".format(file_path) if not file_path.startswith('media/') else file_path
            
            logger.info("[SCORM Content] Attempting direct S3 access: bucket={}, key={}".format(bucket_name, s3_key))
            
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            file_content = response['Body'].read()
            file_source = "S3 (direct access)"
            logger.info("[SCORM Content] Successfully read {} bytes from S3 direct access: {}".format(len(file_content), s3_key))
            
        except Exception as s3_direct_error:
            s3_key_for_log = "media/{}".format(file_path) if not file_path.startswith('media/') else file_path
            logger.warning("[SCORM Content] S3 direct access failed for '{}': {}".format(s3_key_for_log, str(s3_direct_error)))
            
            # Fallback: Try Django storage with the file path as-is
            try:
                # MediaS3Storage will automatically prepend 'media/' to the path
                with default_storage.open(file_path, 'rb') as f:
                    file_content = f.read()
                file_source = "S3 (Django storage)"
                logger.info("[SCORM Content] Successfully read {} bytes from Django S3 storage: {}".format(len(file_content), file_path))
                
            except Exception as s3_error:
                logger.warning("[SCORM Content] Django S3 storage read failed for path '{}': {}".format(file_path, str(s3_error)))
                
                # Fallback: Try with explicit media/ prefix in case the storage path changed
                try:
                    # For legacy files that might have been stored with explicit media/ prefix
                    media_file_path = "media/{}".format(file_path) if not file_path.startswith('media/') else file_path
                    logger.info("[SCORM Content] Trying Django S3 storage with media prefix: {}".format(media_file_path))
                    with default_storage.open(media_file_path, 'rb') as f:
                        file_content = f.read()
                    file_source = "S3 (Django storage with media prefix)"
                    logger.info("[SCORM Content] Successfully read {} bytes from Django S3 storage with media prefix: {}".format(len(file_content), media_file_path))
                except Exception as s3_media_error:
                    logger.warning("[SCORM Content] Django S3 storage read with media prefix failed: {}".format(str(s3_media_error)))
                    
                    # Final fallback to local file system
                    try:
                        import os  # Ensure os is available in this scope
                        # Try both with and without media_local prefix
                        local_paths = []
                        
                        if file_path.startswith('media_local/'):
                            local_paths.append(os.path.join('/home/ec2-user/lms', file_path))
                        else:
                            local_paths.extend([
                                os.path.join('/home/ec2-user/lms', file_path),
                                os.path.join('/home/ec2-user/lms', 'media_local', file_path),
                                os.path.join('/home/ec2-user/lms', "media/{}".format(file_path))
                            ])
                        
                        for local_file_path in local_paths:
                            logger.info("[SCORM Content] Trying local file: {}".format(local_file_path))
                            if os.path.exists(local_file_path):
                                with open(local_file_path, 'rb') as f:
                                    file_content = f.read()
                                file_source = "Local"
                                logger.info("[SCORM Content] Successfully read {} bytes from local file: {}".format(len(file_content), local_file_path))
                                break
                        
                        if file_content is None:
                            logger.error("[SCORM Content] Local file not found in any of these paths: {}".format(local_paths))
                            
                    except Exception as local_error:
                        logger.error("[SCORM Content] Local file read failed: {}".format(str(local_error)))
        
        # If we still don't have content, return error
        if file_content is None:
            logger.error("[SCORM Content] File not found in S3 or local storage: {}".format(file_path))
            logger.error("[SCORM Content] Package extracted path: {}".format(attempt.scorm_package.extracted_path))
            logger.error("[SCORM Content] Requested path: {}".format(path))
            
            # Return a detailed HTML error message for HTML files with debug info
            if path.endswith('.html') or path.endswith('.htm'):
                error_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>SCORM Content Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .error {{ background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                    .debug {{ background: #e2e3e5; color: #383d41; padding: 10px; border-radius: 3px; margin: 10px 0; font-family: monospace; font-size: 12px; }}
                    .attempts {{ background: #d1ecf1; color: #0c5460; padding: 10px; border-radius: 3px; margin: 10px 0; }}
                </style>
            </head>
            <body>
                <h1>🚫 SCORM Content Error</h1>
                <div class="error">
                    <h3>File Not Found</h3>
                    <p>The requested SCORM content file could not be located: <code>{0}</code></p>
                </div>
                
                <div class="debug">
                    <h4>Debug Information:</h4>
                    <p><strong>Package ID:</strong> {1}</p>
                    <p><strong>Package Title:</strong> {2}</p>
                    <p><strong>Extracted Path:</strong> {3}</p>
                    <p><strong>Launch URL:</strong> {4}</p>
                    <p><strong>Full File Path:</strong> {5}</p>
                    <p><strong>Attempt ID:</strong> {6}</p>
                    <p><strong>User:</strong> {7}</p>
                </div>
                
                <div class="attempts">
                    <h4>Troubleshooting Steps:</h4>
                    <ol>
                        <li>Verify the SCORM package was properly uploaded and extracted</li>
                        <li>Check if the launch URL in the manifest is correct</li>
                        <li>Ensure S3 permissions are configured correctly</li>
                        <li>Contact your system administrator with the debug information above</li>
                    </ol>
                </div>
                
                <p><a href="/scorm/player/{8}/" style="color: #007bff;">← Return to SCORM Player</a></p>
            </body>
            </html>
            """.format(
                    path,
                    attempt.scorm_package.id,
                    attempt.scorm_package.title,
                    attempt.scorm_package.extracted_path,
                    attempt.scorm_package.launch_url,
                    file_path,
                    attempt_id,
                    request.user.username,
                    attempt.scorm_package.topic.id
                )
                return HttpResponse(error_html, content_type='text/html', status=404)
            
            # For non-HTML files, return JSON error with debug info
            import json
            error_data = {
                'error': 'File not found',
                'path': path,
                'file_path': file_path,
                'package_id': attempt.scorm_package.id,
                'extracted_path': attempt.scorm_package.extracted_path,
                'launch_url': attempt.scorm_package.launch_url,
                'debug': True
            }
            return HttpResponse(json.dumps(error_data, indent=2), content_type='application/json', status=404)
        
        # Determine content type
        content_type = 'application/octet-stream'
        is_html = path.endswith('.html') or path.endswith('.htm')
        
        if is_html:
            content_type = 'text/html; charset=utf-8'
        elif path.endswith('.js'):
            content_type = 'text/javascript; charset=utf-8'
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
        
        # Simple JavaScript modernization for cross-browser compatibility
        is_js = path.endswith('.js')
        if is_js:
            try:
                js_content = file_content.decode('utf-8')
                js_content = _modernize_javascript_content(js_content)
                file_content = js_content.encode('utf-8')
            except Exception as e:
                logger.warning("Could not modernize JavaScript file {}: {}".format(path, e))
        
        # For HTML files, inject base tag and fix DOCTYPE to ensure compatibility
        # This is crucial for SCORM content that uses relative paths for resources
        if is_html:
            try:
                html_content = file_content.decode('utf-8')
                
                # Fix DOCTYPE to prevent Quirks Mode
                # Check if DOCTYPE is missing or incorrect
                if not html_content.strip().lower().startswith('<!doctype html'):
                    # Remove any existing DOCTYPE declarations
                    import re
                    html_content = re.sub(r'<!DOCTYPE[^>]*>', '', html_content, flags=re.IGNORECASE)
                    # Add proper HTML5 DOCTYPE at the beginning
                    if not html_content.strip().startswith('<html'):
                        html_content = '<!DOCTYPE html>\n' + html_content
                    else:
                        html_content = '<!DOCTYPE html>\n' + html_content
                    logger.info("Fixed DOCTYPE to prevent Quirks Mode")
                
                # Get the directory of the current file
                import os
                file_dir = os.path.dirname(path)
                
                # Use absolute HTTPS URL to prevent mixed content issues
                # Get the scheme and host from the request
                scheme = 'https' if request.is_secure() or request.META.get('HTTP_X_FORWARDED_PROTO') == 'https' else 'http'
                host = request.get_host()
                # Always include the directory path in the base URL
                base_url = "{}://{}/scorm/content/{}/{}/".format(scheme, host, attempt_id, file_dir) if file_dir else "{}://{}/scorm/content/{}/".format(scheme, host, attempt_id)
                
                # Modernize deprecated JavaScript - fix unload event listeners
                html_content = _modernize_javascript_content(html_content)
                
                # Inject stub API and base tag for native SCORM
                stub_api_script = '''
<script>
// Enhanced SCORM API Stub - Based on pipwerks approach
// Makes SCORM content work standalone without player wrapper
(function() {
    console.log('[SCORM] Starting API initialization...');
    
    // Data store for SCORM values
    var scormData = {
        'cmi.core.student_id': 'guest_user',
        'cmi.core.student_name': 'Guest, User',
        'cmi.core.lesson_status': 'incomplete',
        'cmi.core.lesson_location': '',
        'cmi.core.credit': 'credit',
        'cmi.core.entry': 'ab-initio',
        'cmi.core.score.raw': '',
        'cmi.core.score.min': '0',
        'cmi.core.score.max': '100',
        'cmi.core.total_time': '0000:00:00',
        'cmi.core.lesson_mode': 'normal',
        'cmi.core.exit': '',
        'cmi.core.session_time': '',
        'cmi.suspend_data': '',
        'cmi.launch_data': '',
        'cmi.comments': '',
        'cmi.comments_from_lms': '',
        // SCORM 2004 equivalents
        'cmi.learner_id': 'guest_user',
        'cmi.learner_name': 'Guest, User',
        'cmi.completion_status': 'incomplete',
        'cmi.success_status': 'unknown',
        'cmi.location': '',
        'cmi.score.scaled': '',
        'cmi.score.raw': '',
        'cmi.score.min': '0',
        'cmi.score.max': '100',
        'cmi.total_time': 'PT0H0M0S',
        'cmi.mode': 'normal',
        'cmi.exit': '',
        'cmi.session_time': '',
        'cmi.entry': 'ab-initio'
    };
    
    var initialized = false;
    var terminated = false;
    
    // SCORM 1.2 API
    var API = {
        LMSInitialize: function(param) {
            console.log('[SCORM 1.2] Initialize called');
            if (!initialized && !terminated) {
                initialized = true;
                return 'true';
            }
            return 'false';
        },
        
        LMSFinish: function(param) {
            console.log('[SCORM 1.2] Finish called');
            if (initialized && !terminated) {
                terminated = true;
                return 'true';
            }
            return 'false';
        },
        
        LMSGetValue: function(element) {
            console.log('[SCORM 1.2] GetValue: ' + element);
            if (!initialized || terminated) return '';
            
            if (scormData.hasOwnProperty(element)) {
                return scormData[element];
            }
            
            // Handle special cases
            if (element === 'cmi.core._children') {
                return 'student_id,student_name,lesson_location,credit,lesson_status,entry,score,total_time,lesson_mode,exit,session_time';
            }
            if (element === 'cmi.core.score._children') {
                return 'raw,min,max';
            }
            
            return '';
        },
        
        LMSSetValue: function(element, value) {
            console.log('[SCORM 1.2] SetValue: ' + element + ' = ' + value);
            if (!initialized || terminated) return 'false';
            
            // Store the value
            scormData[element] = value;
            
            // Auto-handle status changes
            if (element === 'cmi.core.score.raw') {
                var score = parseInt(value, 10);
                var max = parseInt(scormData['cmi.core.score.max'], 10) || 100;
                if (score >= (max * 0.8)) {  // 80% passing
                    scormData['cmi.core.lesson_status'] = 'passed';
                } else if (scormData['cmi.core.lesson_status'] === 'not attempted') {
                    scormData['cmi.core.lesson_status'] = 'incomplete';
                }
            }
            
            return 'true';
        },
        
        LMSCommit: function(param) {
            console.log('[SCORM 1.2] Commit called');
            if (!initialized || terminated) return 'false';
            // In standalone mode, just log the data
            console.log('[SCORM 1.2] Current data:', scormData);
            return 'true';
        },
        
        LMSGetLastError: function() {
            return '0';
        },
        
        LMSGetErrorString: function(errorCode) {
            return 'No error';
        },
        
        LMSGetDiagnostic: function(errorCode) {
            return 'No diagnostic information available';
        }
    };
    
    // SCORM 2004 API
    var API_1484_11 = {
        Initialize: function(param) {
            console.log('[SCORM 2004] Initialize called');
            if (!initialized && !terminated) {
                initialized = true;
                return 'true';
            }
            return 'false';
        },
        
        Terminate: function(param) {
            console.log('[SCORM 2004] Terminate called');
            if (initialized && !terminated) {
                terminated = true;
                return 'true';
            }
            return 'false';
        },
        
        GetValue: function(element) {
            console.log('[SCORM 2004] GetValue: ' + element);
            if (!initialized || terminated) return '';
            
            if (scormData.hasOwnProperty(element)) {
                return scormData[element];
            }
            
            // Handle special cases
            if (element === 'cmi._children') {
                return 'comments_from_learner,comments_from_lms,completion_status,credit,entry,exit,interactions,launch_data,learner_id,learner_name,learner_preference,location,max_time_allowed,mode,objectives,progress_measure,scaled_passing_score,score,session_time,success_status,suspend_data,time_limit_action,total_time';
            }
            if (element === 'cmi.score._children') {
                return 'scaled,raw,min,max';
            }
            
            return '';
        },
        
        SetValue: function(element, value) {
            console.log('[SCORM 2004] SetValue: ' + element + ' = ' + value);
            if (!initialized || terminated) return 'false';
            
            // Store the value
            scormData[element] = value;
            
            // Auto-handle status changes
            if (element === 'cmi.score.raw' || element === 'cmi.score.scaled') {
                var score = parseFloat(value);
                if (element === 'cmi.score.scaled' && score >= 0.8) {
                    scormData['cmi.success_status'] = 'passed';
                    scormData['cmi.completion_status'] = 'completed';
                } else if (element === 'cmi.score.raw') {
                    var max = parseFloat(scormData['cmi.score.max']) || 100;
                    if (score >= (max * 0.8)) {
                        scormData['cmi.success_status'] = 'passed';
                        scormData['cmi.completion_status'] = 'completed';
                    }
                }
            }
            
            if (element === 'cmi.completion_status' && value === 'completed') {
                console.log('[SCORM 2004] Course marked as completed');
            }
            
            return 'true';
        },
        
        Commit: function(param) {
            console.log('[SCORM 2004] Commit called');
            if (!initialized || terminated) return 'false';
            // In standalone mode, just log the data
            console.log('[SCORM 2004] Current data:', scormData);
            return 'true';
        },
        
        GetLastError: function() {
            return '0';
        },
        
        GetErrorString: function(errorCode) {
            return 'No error';
        },
        
        GetDiagnostic: function(errorCode) {
            return 'No diagnostic information available';
        }
    };
    
    // Try to find existing API first (pipwerks approach)
    function findAPI(win) {
        var attempts = 0;
        var limit = 500;
        
        while ((!win.API && !win.API_1484_11) && (win.parent) && (win.parent != win) && (attempts <= limit)) {
            attempts++;
            win = win.parent;
        }
        
        return win.API || win.API_1484_11;
    }
    
    // Check for existing API
    var existingAPI = findAPI(window);
    
    if (!existingAPI) {
        // No API found, use our stub
        console.log('[SCORM] No parent API found, using standalone stub');
        window.API = API;
        window.API_1484_11 = API_1484_11;
        
        // Also set on parent if accessible (for deeply nested content)
        try {
            if (window.parent && window.parent !== window) {
                window.parent.API = API;
                window.parent.API_1484_11 = API_1484_11;
            }
        } catch (e) {
            // Cross-origin, ignore
        }
        
        // Auto-initialize after a short delay (some content expects this)
        setTimeout(function() {
            if (!initialized) {
                console.log('[SCORM] Auto-initializing API...');
                API.LMSInitialize('');
                API_1484_11.Initialize('');
            }
        }, 100);
        
    } else {
        console.log('[SCORM] Parent API found, using existing');
    }
    
    console.log('[SCORM] API setup complete');
})();
</script>'''
                
                # Add cross-browser compatibility meta tags and error handling
                browser_compat_tags = '''
<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta charset="utf-8">
<script>
// Simple JavaScript error handler for SCORM content
window.addEventListener('error', function(e) {
    console.log('[SCORM] Handled JavaScript error:', e.message);
    return true; // Prevent error from stopping execution
});
</script>'''
                
                # Inject compatibility tags and API stub
                if '<head>' in html_content.lower():
                    # Inject both compatibility tags and API stub after <head>
                    html_content = html_content.replace('<head>', '<head>' + browser_compat_tags + '\n' + stub_api_script, 1)
                    html_content = html_content.replace('<HEAD>', '<HEAD>' + browser_compat_tags + '\n' + stub_api_script, 1)
                elif '<html' in html_content.lower():
                    # If no head tag, create one with compatibility tags and API stub
                    injection = '\n<head>\n' + browser_compat_tags + '\n' + stub_api_script + '\n</head>\n'
                    html_content = re.sub(r'(<html[^>]*>)', r'\1' + injection, html_content, flags=re.IGNORECASE)
                else:
                    # As last resort, inject at the beginning
                    html_content = browser_compat_tags + '\n' + stub_api_script + '\n' + html_content
                
                file_content = html_content.encode('utf-8')
                logger.info("Injected SCORM API stub for standalone content access")
            
            except Exception as e:
                logger.warning("Could not process HTML content: {}".format(e))
        
        response = HttpResponse(file_content, content_type=content_type)
        
        # Allow iframe embedding and cross-origin requests (for fonts, etc)
        response['Access-Control-Allow-Origin'] = '*'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        
        # SCORM-specific headers to allow dynamic script evaluation
        # This is necessary because SCORM content often uses eval(), new Function(), etc.
        if is_html:
            # Remove restrictive security headers for SCORM content while maintaining minimal security
            
            # AGGRESSIVELY REMOVE ALL CSP HEADERS FOR SCORM CONTENT
            csp_headers = ['Content-Security-Policy', 'Content-Security-Policy-Report-Only', 'X-Content-Security-Policy']
            for header in csp_headers:
                if header in response:
                    del response[header]
                    logger.info(f"Removed {header} for SCORM content: {path}")
            
            # SIMPLE CSP FOR MAXIMUM CROSS-BROWSER COMPATIBILITY
            response['Content-Security-Policy'] = (
                "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                "script-src * 'unsafe-inline' 'unsafe-eval'; "
                "style-src * 'unsafe-inline'; "
                "img-src * data: blob:; "
                "font-src * data:; "
                "connect-src *; "
                "media-src * data: blob:; "
                "frame-src *"
            )
            logger.info(f"Set permissive CSP with unsafe-eval for SCORM content: {path}")
            
            # Allow iframe embedding from same origin (needed for SCORM player)
            response['X-Frame-Options'] = 'SAMEORIGIN'
            
            # Remove content type options to allow flexible content loading
            if 'X-Content-Type-Options' in response:
                del response['X-Content-Type-Options']
            
            # Disable XSS protection (SCORM content may use patterns that trigger false positives)
            response['X-XSS-Protection'] = '0'
            
            # Allow CORS for SCORM content resources
            response['Access-Control-Allow-Origin'] = '*'
        
        # Prevent caching of SCORM content to ensure fresh data
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response
        
    except Exception as e:
        logger.error("Error serving SCORM content: {}".format(str(e)))
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
        logger.error("Error getting SCORM status: {}".format(str(e)))
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def scorm_debug(request, attempt_id):
    """
    SCORM diagnostic endpoint for troubleshooting
    Returns detailed information about SCORM package and file locations
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt or is instructor/admin
        if attempt.user != request.user and not request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Check S3 configuration
        from django.conf import settings
        s3_configured = hasattr(settings, 'AWS_STORAGE_BUCKET_NAME') and settings.AWS_STORAGE_BUCKET_NAME
        
        # Test file access
        test_file_path = "{}/{}".format(attempt.scorm_package.extracted_path, attempt.scorm_package.launch_url)
        s3_test_result = "Not tested"
        local_test_result = "Not tested"
        
        # Test S3 access
        if s3_configured:
            try:
                from django.core.files.storage import default_storage
                s3_test_result = "Accessible" if default_storage.exists(test_file_path) else "File not found"
            except Exception as e:
                s3_test_result = "Error: {}".format(str(e))
        
        # Test local access
        try:
            import os
            local_file_path = os.path.join('/home/ec2-user/lms', test_file_path)
            local_test_result = "Accessible" if os.path.exists(local_file_path) else "File not found"
        except Exception as e:
            local_test_result = "Error: {}".format(str(e))
        
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
            'storage_info': {
                's3_configured': s3_configured,
                'bucket_name': getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None),
                'media_location': getattr(settings, 'AWS_MEDIA_LOCATION', None),
                'default_file_storage': getattr(settings, 'DEFAULT_FILE_STORAGE', None),
            },
            'file_tests': {
                'test_file_path': test_file_path,
                's3_test': s3_test_result,
                'local_test': local_test_result,
            },
            'urls': {
                's3_direct_url': "https://{}.s3.{}.amazonaws.com/media/{}".format(getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'bucket'), getattr(settings, 'AWS_S3_REGION_NAME', 'region'), test_file_path) if s3_configured else None,
                'proxy_url': "/scorm/content/{}/{}".format(attempt_id, attempt.scorm_package.launch_url),
                'player_url': "/scorm/player/{}/".format(attempt.scorm_package.topic.id),
            },
            'manifest_data': attempt.scorm_package.manifest_data,
            'system_info': {
                'environment': getattr(settings, 'ENVIRONMENT', 'unknown'),
                'debug': getattr(settings, 'DEBUG', False),
                'media_url': getattr(settings, 'MEDIA_URL', None),
                'media_root': getattr(settings, 'MEDIA_ROOT', None),
            }
        }
        
        return JsonResponse({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        logger.error("Error in SCORM debug endpoint: {}".format(str(e)))
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@xframe_options_exempt
def scorm_player_direct(request, topic_id):
    """
    Simplified SCORM player using direct S3 URLs
    Eliminates Django proxy layer for better performance and fewer bugs
    """
    # Check authentication
    if not request.user.is_authenticated:
        request.session['login_redirect'] = request.get_full_path()
        messages.info(request, "Please log in to access this content.")
        return redirect('login')
    
    # Get the topic
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
    
    # Import direct S3 access utility
    from .s3_direct import scorm_s3
    
    logger.info("Direct S3 SCORM Player - User: {}, Topic: {}, Package: {}".format(request.user.username, topic_id, scorm_package.id))
    
    # Handle preview mode for instructors/admins
    preview_mode = request.GET.get('preview', '').lower() == 'true'
    is_instructor_or_admin = request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']
    
    if preview_mode and not is_instructor_or_admin:
        messages.error(request, "Preview mode is only available for instructors and administrators.")
        preview_mode = False
    
    if preview_mode:
        # Preview mode - no tracking
        attempt_id = "preview_{}".format(uuid.uuid4())
        attempt = None
        logger.info("Preview mode activated for user {}".format(request.user.username))
    else:
        # Regular mode - get or create attempt for tracking
        last_attempt = ScormAttempt.objects.filter(
            user=request.user,
            scorm_package=scorm_package
        ).order_by('-attempt_number').first()
        
        if last_attempt and last_attempt.lesson_status not in ['completed', 'passed']:
            # Continue existing incomplete attempt
            attempt = last_attempt
            logger.info("Continuing existing attempt {}".format(attempt.id))
        else:
            # Create new attempt
            attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1
            attempt = ScormAttempt.objects.create(
                user=request.user,
                scorm_package=scorm_package,
                attempt_number=attempt_number
            )
            logger.info("Created new attempt {}".format(attempt.id))
            
        attempt_id = attempt.id
    
    # Generate direct S3 URLs - bypass Django proxy entirely
    from django.conf import settings
    bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'lms-staging-nexsy-io')
    region = getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2')
    
    base_s3_url = "https://{}.s3.{}.amazonaws.com/media/{}".format(bucket_name, region, scorm_package.extracted_path)
    direct_s3_url = "{}/{}".format(base_s3_url, scorm_package.launch_url)
    
    logger.info("🎯 Direct S3 URL generated: {}".format(direct_s3_url))
    
    # Skip S3 verification for faster loading - let browser handle any 404s
    # This saves ~100-200ms per request by avoiding S3 API call
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt_id': attempt_id,
        'attempt': attempt,
        'api_endpoint': '/scorm/api/{}/'.format(attempt_id),
        'direct_s3_url': direct_s3_url,
        'base_s3_url': base_s3_url,
        'preview_mode': preview_mode,
        'use_direct_s3': True,
    }
    
    response = render(request, 'scorm/player_simple.html', context)
    
    # Set permissive CSP headers for SCORM player to allow S3 content loading
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
    
    # Explicitly allow SCORM player to be embedded in iframes from same origin
    response['X-Frame-Options'] = 'SAMEORIGIN'
    
    return response


def scorm_content_proxy(request, attempt_id, path):
    """
    Lightweight proxy that fetches SCORM content from S3 and injects API
    Solves cross-origin issues while maintaining S3 performance
    """
    try:
        # Get attempt (similar to scorm_player_direct validation)
        if str(attempt_id).startswith('preview_'):
            # Handle preview mode
            scorm_package = None
            # For preview, we need to get package info from session or database
            # For now, get the first package as fallback
            scorm_package = ScormPackage.objects.first()
        else:
            try:
                attempt = get_object_or_404(ScormAttempt, id=attempt_id)
                scorm_package = attempt.scorm_package
            except:
                return HttpResponse('Attempt not found', status=404)
        
        if not scorm_package:
            return HttpResponse('SCORM package not found', status=404)
        
        # Import S3 utility
        from .s3_direct import scorm_s3
        
        # Get content from S3
        s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        
        try:
            import requests
            response = requests.get(s3_url, timeout=10)
            response.raise_for_status()
            
            content = response.content
            content_type = response.headers.get('content-type', 'application/octet-stream')
            
            # Only inject API for HTML files
            if path.endswith('.html') and 'text/html' in content_type:
                # Decode content for HTML manipulation
                try:
                    html_content = content.decode('utf-8')
                except:
                    html_content = content.decode('latin1', errors='ignore')
                
                # Inject SCORM API into HTML head
                api_injection = '''
<script>
// Injected SCORM API for Direct S3 Content
console.log('🎯 SCORM API injected into content');
window.API = window.API_1484_11 = {
    Initialize: function(param) { 
        console.log('API: Initialize'); 
        return "true"; 
    },
    LMSInitialize: function(param) { 
        console.log('API: LMSInitialize'); 
        return "true"; 
    },
    Terminate: function(param) { 
        console.log('API: Terminate'); 
        return "true"; 
    },
    LMSFinish: function(param) { 
        console.log('API: LMSFinish'); 
        return "true"; 
    },
    GetValue: function(element) {
        console.log('API: GetValue(' + element + ')');
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
    LMSGetValue: function(element) { 
        return this.GetValue(element); 
    },
    SetValue: function(element, value) { 
        console.log('API: SetValue(' + element + ', ' + value + ')'); 
        return "true"; 
    },
    LMSSetValue: function(element, value) { 
        return this.SetValue(element, value); 
    },
    Commit: function(param) { 
        console.log('API: Commit'); 
        return "true"; 
    },
    LMSCommit: function(param) { 
        console.log('API: LMSCommit'); 
        return "true"; 
    },
    GetLastError: function() { 
        return "0"; 
    },
    LMSGetLastError: function() { 
        return "0"; 
    },
    GetErrorString: function(code) { 
        return "No error"; 
    },
    LMSGetErrorString: function(code) { 
        return "No error"; 
    },
    GetDiagnostic: function(code) { 
        return "No error"; 
    },
    LMSGetDiagnostic: function(code) { 
        return "No error"; 
    }
};
console.log('✅ SCORM API ready for content');
</script>
'''
                
                # Inject before </head> or at beginning of <body>
                if '</head>' in html_content:
                    html_content = html_content.replace('</head>', api_injection + '</head>')
                elif '<body' in html_content:
                    # Find the end of <body> tag
                    import re
                    html_content = re.sub(r'(<body[^>]*>)', r'\1' + api_injection, html_content)
                else:
                    # Fallback: add at beginning
                    html_content = api_injection + html_content
                
                # Convert back to bytes
                content = html_content.encode('utf-8')
                content_type = 'text/html; charset=utf-8'
                
                logger.info("✅ Injected SCORM API into {}".format(path))
            
            # Create HTTP response
            response_obj = HttpResponse(content, content_type=content_type)
            
            # Add appropriate headers
            if path.endswith(('.js', '.css', '.png', '.jpg', '.gif', '.svg')):
                response_obj['Cache-Control'] = 'public, max-age=3600'
            
            return response_obj
            
        except requests.RequestException as e:
            logger.error("Failed to fetch S3 content: {}".format(str(e)))
            return HttpResponse('Failed to load content: {}'.format(str(e)), status=502)
            
    except Exception as e:
        logger.error("Error in content proxy: {}".format(str(e)))
        return HttpResponse('Proxy error: {}'.format(str(e)), status=500)

