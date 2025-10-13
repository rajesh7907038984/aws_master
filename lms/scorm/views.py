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
from .api_handler import ScormAPIHandler  # Keep for fallback
from .preview_handler import ScormPreviewHandler
from .s3_direct import scorm_s3
from courses.models import Topic

logger = logging.getLogger(__name__)

# NEW: Import specialized handlers with safe fallback
try:
    from .handlers import get_handler_for_attempt
    USE_NEW_HANDLERS = True
    logger.info("New specialized SCORM handlers loaded successfully")
except ImportError as e:
    USE_NEW_HANDLERS = False
    logger.warning(f"New handlers not available, using legacy handler: {e}")


def _detect_scorm_package_type(scorm_package):
    """
    Detect the type of SCORM package to use the appropriate player template
    Returns: 'rise360', 'storyline', 'captivate', or 'generic'
    """
    try:
        launch_url = scorm_package.launch_url.lower()
        manifest_data = scorm_package.manifest_data or {}
        
        # Check for Rise 360 (most common pattern)
        if 'scormcontent/index.html' in launch_url or 'index.html#/lessons/' in launch_url:
            # Additional Rise 360 checks
            if manifest_data:
                # Rise 360 typically has a specific structure in manifest
                resources = manifest_data.get('resources', [])
                for resource in resources:
                    if isinstance(resource, dict):
                        href = resource.get('href', '').lower()
                        if 'scormcontent' in href and 'lib/' in href:
                            return 'rise360'
            return 'rise360'
        
        # Check for Articulate Storyline
        if 'story.html' in launch_url or 'story_html5.html' in launch_url:
            return 'storyline'
        
        # Check for Adobe Captivate
        if manifest_data:
            title = str(manifest_data.get('title', '')).lower()
            if 'captivate' in title or 'adobe' in title:
                return 'captivate'
        
        if 'captivate' in launch_url or 'multiscreen.html' in launch_url:
            return 'captivate'
        
        # Default to generic SCORM player
        return 'generic'
        
    except Exception as e:
        logger.error(f"Error detecting SCORM package type: {str(e)}")
        return 'generic'


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
    
    # Check if SCORM package has extracted content path
    # Note: For S3 storage, we rely on the extracted_path rather than checking the original zip file
    # The extracted content is what's actually used for playback
    if not scorm_package.extracted_path or not scorm_package.launch_url:
        messages.error(request, "SCORM content configuration is incomplete. Please contact your administrator.")
        logger.error(f"SCORM package missing extracted_path or launch_url for topic {topic_id}, package {scorm_package.id}")
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
        # FIXED: Use transaction and select_for_update to prevent race conditions
        from django.db import transaction
        
        with transaction.atomic():
            # Lock the rows to prevent concurrent creation
            last_attempt = ScormAttempt.objects.select_for_update().filter(
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
    # CRITICAL FIX: Append bookmark hash for Rise 360 resume functionality
    # Rise expects the hash in the URL on initial load to jump to the saved slide
    content_url = f'/scorm/content/{topic_id}/{scorm_package.launch_url}?attempt_id={attempt_id}'
    
    # Check if there's a saved bookmark with a hash (Rise 360 format)
    if attempt.lesson_location and '#' in attempt.lesson_location:
        # Extract just the hash part (e.g., "#/lessons/GgZj1-c4S6yfmISAoYe1dLtFocAO8amH")
        hash_part = '#' + attempt.lesson_location.split('#', 1)[1]
        content_url += hash_part
        logger.info(f"SCORM Resume: Appending bookmark hash to iframe URL: {hash_part[:50]}")
    elif attempt.lesson_location:
        # CRITICAL FIX: Handle lesson locations (avoid double hash)
        if attempt.lesson_location.startswith('#'):
            content_url += attempt.lesson_location  # Already has hash
        else:
            content_url += '#' + attempt.lesson_location  # Add hash
        logger.info(f"SCORM Resume: Appending location to iframe URL: {attempt.lesson_location}")
    elif attempt.suspend_data and attempt.entry == 'resume':
        # CRITICAL FIX: If we have suspend data but no lesson_location, create a default location
        attempt.lesson_location = 'slide_1'  # Default to first slide
        attempt.save()
        content_url += '#slide_1'
        logger.info(f"SCORM Resume: Created default location for resume with suspend data")
    
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
    
    # ARCHITECTURAL IMPROVEMENT: Detect package type and use appropriate player template
    # This simplifies maintenance - each player handles ONE type of SCORM package
    package_type = _detect_scorm_package_type(scorm_package)
    template_map = {
        'rise360': 'scorm/player_rise360.html',
        'storyline': 'scorm/player_storyline.html',
        'captivate': 'scorm/player_captivate.html',
        'generic': 'scorm/player_generic.html',
    }
    
    # Use generic player as fallback for unknown types
    template_name = template_map.get(package_type, 'scorm/player_generic.html')
    logger.info(f"Using {template_name} for package type: {package_type}")
    
    response = render(request, template_name, context)
    
    # Set permissive CSP headers for SCORM content
    # CRITICAL: SCORM content often uses eval() and dynamic code execution
    response['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'unsafe-hashes' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "worker-src 'self' blob: data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "style-src 'self' 'unsafe-inline' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "img-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "font-src 'self' data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "connect-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "media-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "frame-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
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
            # NEW: Use specialized handlers if available, fallback to legacy
            if USE_NEW_HANDLERS:
                try:
                    handler = get_handler_for_attempt(attempt)
                    logger.info(f"✅ Using specialized handler ({handler.get_handler_name()}) for attempt {attempt_id}")
                except Exception as e:
                    logger.error(f"⚠️  Error with new handler, falling back to legacy: {e}")
                    handler = ScormAPIHandler(attempt)
                    logger.info(f"Using legacy ScormAPIHandler for attempt {attempt_id}")
            else:
                handler = ScormAPIHandler(attempt)
                logger.info(f"Using legacy ScormAPIHandler for attempt {attempt_id}")
        
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
    Handles multiple SCORM package structures with intelligent fallback
    FIXED: Added caching to avoid repeated S3 path resolution
    """
    from django.core.cache import cache
    
    try:
        # CRITICAL DEBUG: Log the incoming request
        logger.debug(f"SCORM Content Request - Topic: {topic_id}, Path: '{path}'")
        
        topic = get_object_or_404(Topic, id=topic_id)
        
        # Check if topic has SCORM package
        try:
            scorm_package = topic.scorm_package
        except ScormPackage.DoesNotExist:
            return HttpResponse('SCORM package not found', status=404)
        
        # CRITICAL FIX: If path is empty or ends with /, use the launch_url
        if not path or path.endswith('/'):
            logger.debug(f"Path is empty or directory, using launch_url: {scorm_package.launch_url}")
            path = scorm_package.launch_url
        
        # FIXED: Check cache first for successful S3 path
        cache_key = f"scorm_s3_path:{topic_id}:{path}"
        successful_key = cache.get(cache_key)
        
        # Use boto3 directly to fetch content (authenticated access)
        import boto3
        from django.conf import settings
        
        # Initialize S3 client
        try:
            s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
            s3_client = boto3.client('s3')  # Try without region
            
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        content = None
        
        # Try cached path first
        if successful_key:
            try:
                logger.debug(f"Trying cached S3 path: {successful_key}")
                response = s3_client.get_object(Bucket=bucket_name, Key=successful_key)
                content = response['Body'].read()
                logger.debug(f"✅ Content loaded from cached path")
            except Exception as e:
                logger.debug(f"Cached path failed: {str(e)}, trying alternatives")
                content = None
                successful_key = None
                cache.delete(cache_key)
        
        # If cache miss or failed, try multiple paths
        if content is None:
            # Build path attempts
            path_attempts = []
            
            # Attempt 1: Direct path (for files at root level like story.html)
            path_attempts.append(f"media/{scorm_package.extracted_path}/{path}")
            
            # Attempt 2: Without media/ prefix (for some S3 configurations)
            path_attempts.append(f"{scorm_package.extracted_path}/{path}")
            
            # Attempt 3: If path contains subdirectories, try without the first directory
            if '/' in path:
                path_parts = path.split('/', 1)
                if len(path_parts) > 1:
                    path_attempts.append(f"media/{scorm_package.extracted_path}/{path_parts[1]}")
                    path_attempts.append(f"{scorm_package.extracted_path}/{path_parts[1]}")
            
            # Attempt 4: Try with scormcontent/ prefix (for Rise packages)
            if not path.startswith('scormcontent/'):
                path_attempts.append(f"media/{scorm_package.extracted_path}/scormcontent/{path}")
                path_attempts.append(f"{scorm_package.extracted_path}/scormcontent/{path}")
            
            # Attempt 5: Try with just the filename (for deeply nested structures)
            if '/' in path:
                filename = path.split('/')[-1]
                path_attempts.append(f"media/{scorm_package.extracted_path}/{filename}")
                path_attempts.append(f"{scorm_package.extracted_path}/{filename}")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_paths = []
            for p in path_attempts:
                if p not in seen:
                    seen.add(p)
                    unique_paths.append(p)
            
            logger.debug(f"SCORM Content - Topic: {topic_id}, Requested Path: '{path}'")
            logger.debug(f"Package - Launch URL: '{scorm_package.launch_url}', Extracted Path: '{scorm_package.extracted_path}'")
            logger.debug(f"Will try {len(unique_paths)} path combinations")
            
            # Try each path until one works
            for attempt_num, s3_key in enumerate(unique_paths, 1):
                try:
                    logger.debug(f"Attempt {attempt_num}/{len(unique_paths)}: {s3_key}")
                    response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
                    content = response['Body'].read()
                    successful_key = s3_key
                    logger.debug(f"✅ Successfully fetched content from: {s3_key}")
                    # Cache successful path for 1 hour
                    cache.set(cache_key, successful_key, 3600)
                    break
                except s3_client.exceptions.NoSuchKey:
                    logger.debug(f"Path not found: {s3_key}")
                    continue
                except Exception as e:
                    logger.debug(f"Error trying {s3_key}: {str(e)}")
                    continue
        
        # If no path worked, return detailed error
        if content is None:
            error_msg = f"SCORM content file not found. Tried {len(unique_paths)} paths:\n"
            for p in unique_paths[:5]:  # Show first 5 attempts
                error_msg += f"  - {p}\n"
            if len(unique_paths) > 5:
                error_msg += f"  ... and {len(unique_paths) - 5} more\n"
            error_msg += "\nPlease contact your administrator."
            logger.error(f"Failed to find SCORM content for topic {topic_id}, path: {path}")
            logger.error(f"Tried paths: {unique_paths}")
            return HttpResponse(error_msg, status=404)
        
        logger.info(f"Serving SCORM content from: {successful_key}")
        
        # For HTML files, inject SCORM API
        if path.endswith(('.html', '.htm')):
            try:
                content_type = 'text/html; charset=utf-8'
                
                # Inject SCORM API for HTML files
                if 'text/html' in content_type:
                    html_content = content.decode('utf-8')
                    
                    # Inject SCORM API that connects to the real API endpoint
                    # Get attempt_id from the URL parameters
                    attempt_id = request.GET.get('attempt_id', 'preview')
                    
                    # CRITICAL FIX: If attempt_id is 'preview', try to get the real attempt_id from the referer
                    if attempt_id == 'preview':
                        referer = request.META.get('HTTP_REFERER', '')
                        if 'attempt_id=' in referer:
                            import re
                            match = re.search(r'attempt_id=(\d+)', referer)
                            if match:
                                attempt_id = match.group(1)
                                logger.info(f"SCORM Content: Extracted attempt_id from referer: {attempt_id}")
                    
                    api_endpoint = f'/scorm/api/{attempt_id}/'
                    api_injection = f'''
<script>
// CRITICAL FIX: SCORM API must be available immediately for Rise 360
// Rise 360 checks for API on page load, so we set it up synchronously
(function() {{
    // SCORM API that connects to the real API endpoint
    // CRITICAL: Uses SYNCHRONOUS XHR to support legacy SCORM content that expects immediate return values
    window.API = window.API_1484_11 = {{
        _apiEndpoint: '/scorm/api/{attempt_id}/',
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
            // CRITICAL FIX: Use async/await to avoid synchronous XHR deprecation
            return this._makeAPICallAsync(method, parameters);
        }} catch (e) {{
            console.error('[SCORM API] Error:', e);
            this._lastError = '101';
            return 'false';
        }}
    }},
    
    _makeAPICallAsync: async function(method, parameters) {{
        try {{
            const response = await fetch(this._apiEndpoint, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this._getCookie('csrftoken')
                }},
                body: JSON.stringify({{ method: method, parameters: parameters || [] }})
            }});
            
            if (response.ok) {{
                const data = await response.json();
                if (data.success) {{
                    console.log('[SCORM API] ' + method + ' -> ' + data.result);
                    
                    // Note: Removed auto-initialization that was interfering with Storyline
                    // Storyline manages its own initialization, suspend_data, and bookmarking
                    // Our auto-init was overwriting Storyline's state data
                    
                    return data.result;
                }} else {{
                    console.error('[SCORM API] ' + method + ' failed: ' + data.error);
                    this._lastError = '101';
                    return 'false';
                }}
            }} else {{
                console.error('[SCORM API] HTTP error: ' + response.status);
                this._lastError = '101';
                return 'false';
            }}
        }} catch (e) {{
            console.error('[SCORM API] Async error:', e);
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
    }},
    
    // Additional SCORM functions that some content may require
    CommitData: function() {{ 
        return this._makeAPICall('Commit', []); 
    }},
    ConcedeControl: function() {{ 
        return 'true'; 
    }},
    CreateResponseIdentifier: function() {{ 
        return 'response_' + Date.now(); 
    }},
    Finish: function() {{ 
        return this._makeAPICall('Terminate', []); 
    }},
    GetDataChunk: function() {{ 
        return ''; 
    }},
    GetStatus: function() {{ 
        return this._makeAPICall('GetValue', ['cmi.core.lesson_status']); 
    }},
    MatchingResponse: function() {{ 
        return 'true'; 
    }},
    RecordFillInInteraction: function() {{ 
        return 'true'; 
    }},
    RecordMatchingInteraction: function() {{ 
        return 'true'; 
    }},
    RecordMultipleChoiceInteraction: function() {{ 
        return 'true'; 
    }},
    ResetStatus: function() {{ 
        return 'true'; 
    }},
    SetBookmark: function(bookmark) {{ 
        return this._makeAPICall('SetValue', ['cmi.core.lesson_location', bookmark]); 
    }},
    SetDataChunk: function(data) {{ 
        return this._makeAPICall('SetValue', ['cmi.suspend_data', data]); 
    }},
    SetFailed: function() {{ 
        return this._makeAPICall('SetValue', ['cmi.core.lesson_status', 'failed']); 
    }},
    SetLanguagePreference: function(lang) {{ 
        return 'true'; 
    }},
    SetPassed: function() {{ 
        return this._makeAPICall('SetValue', ['cmi.core.lesson_status', 'passed']); 
    }},
    SetReachedEnd: function() {{ 
        return this._makeAPICall('SetValue', ['cmi.core.lesson_status', 'completed']); 
    }},
    SetScore: function(score) {{ 
        return this._makeAPICall('SetValue', ['cmi.core.score.raw', score]); 
    }},
    WriteToDebug: function(message) {{ 
        console.log('[SCORM Debug]', message);
        return 'true'; 
    }}
}};
    
    // CRITICAL: Ensure API is available immediately for Rise 360
    console.log('[SCORM] API initialized with', Object.keys(window.API).length, 'functions');
    console.log('[SCORM] API endpoint:', window.API._apiEndpoint);
}})();
</script>
'''
                    
                    # Fix relative paths in SCORM content
                    html_content = fix_scorm_relative_paths(html_content, topic_id)
                    
                    # CRITICAL FIX: Inject API at the very beginning of <head> for Rise 360 compatibility
                    # Rise 360 checks for API immediately, so it must be available before any other scripts
                    if '<head>' in html_content:
                        html_content = html_content.replace('<head>', '<head>' + api_injection)
                    elif '</head>' in html_content:
                        html_content = html_content.replace('</head>', api_injection + '</head>')
                    elif '<body' in html_content:
                        import re
                        html_content = re.sub(r'(<body[^>]*>)', r'\1' + api_injection, html_content)
                    else:
                        html_content = api_injection + html_content
                    
                    # Add immediate API availability and Rise 360 compatibility
                    api_check = '''
<script>
// CRITICAL FIX: Ensure API is available immediately for Rise 360
// Rise 360 checks for API immediately on load, so we need to set it up before any other scripts run
(function() {
    // Set up API immediately
    if (typeof window.API === 'undefined') {
        console.error('[SCORM] API not found - this will cause SCORM warnings');
    } else {
        console.log('[SCORM] API successfully loaded with', Object.keys(window.API).length, 'functions');
    }
    
    // Rise 360 specific: Ensure API is available on window object
    if (window.API) {
        window.API_1484_11 = window.API;
        console.log('[SCORM] Rise 360 compatibility: API_1484_11 set');
    }
    
    // Additional Rise 360 compatibility
    if (typeof window.parent !== 'undefined' && window.parent !== window) {
        window.parent.API = window.API;
        window.parent.API_1484_11 = window.API_1484_11;
        console.log('[SCORM] Parent window API set for Rise 360');
    }
})();

// CRITICAL FIX: Enhanced Exit button functionality
// This ensures Exit buttons inside SCORM content work properly
(function() {
    function enhanceExitButtons() {
        // Look for common Exit button patterns (only standard CSS selectors)
        const exitSelectors = [
            'button[data-acc-text*="Exit" i]',
            '.slide-object[data-acc-text*="Exit" i]',
            'button[onclick*="exit" i]',
            'a[href*="exit" i]',
            'button[aria-label*="Exit" i]',
            'a[aria-label*="Exit" i]',
            '.exit-button',
            '#exit-button'
        ];
        
        exitSelectors.forEach(selector => {
            try {
                const elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    if (!element.hasAttribute('data-scorm-enhanced')) {
                        element.setAttribute('data-scorm-enhanced', 'true');
                        
                        // Add click handler for Exit functionality
                        element.addEventListener('click', function(e) {
                            console.log('[SCORM] Exit button clicked inside content');
                            
                            // Prevent default behavior
                            e.preventDefault();
                            e.stopPropagation();
                            
                            // Call SCORM API to save and exit
                            if (window.API && window.API.LMSFinish) {
                                console.log('[SCORM] Calling LMSFinish...');
                                const result = window.API.LMSFinish('');
                                console.log('[SCORM] LMSFinish result:', result);
                            } else if (window.API && window.API.Terminate) {
                                console.log('[SCORM] Calling Terminate...');
                                const result = window.API.Terminate('');
                                console.log('[SCORM] Terminate result:', result);
                            } else {
                                console.warn('[SCORM] No SCORM API available for Exit');
                            }
                            
                            return false;
                        });
                        
                        console.log('[SCORM] Enhanced Exit button:', element);
                    }
                });
            } catch (e) {
                // Silently handle unsupported selectors to avoid console spam
            }
        });
        
        // Also look for text-based Exit buttons (only clickable elements)
        const clickableElements = document.querySelectorAll('button, a, [role="button"]');
        clickableElements.forEach(element => {
            const text = element.textContent ? element.textContent.trim().toLowerCase() : '';
            if ((text === 'exit' || text === 'exit course' || text === 'close') && 
                !element.hasAttribute('data-scorm-enhanced')) {
                element.setAttribute('data-scorm-enhanced', 'true');
                element.style.cursor = 'pointer';
                
                element.addEventListener('click', function(e) {
                    console.log('[SCORM] Text Exit button clicked');
                    e.preventDefault();
                    e.stopPropagation();
                    
                    if (window.API && window.API.LMSFinish) {
                        window.API.LMSFinish('');
                    } else if (window.API && window.API.Terminate) {
                        window.API.Terminate('');
                    }
                    
                    return false;
                });
            }
        });
    }
    
    // Run immediately and on DOM ready
    enhanceExitButtons();
    document.addEventListener('DOMContentLoaded', enhanceExitButtons);
    
    // Also run periodically to catch dynamically loaded content
    setInterval(enhanceExitButtons, 2000);
})();

// CRITICAL FIX: Automatic SCORM initialization
(function() {
    let scormInitialized = false;
    let initRetryCount = 0;
    const maxRetries = 3;
    
    // Global flag to prevent multiple initialization attempts
    if (window.scormInitInProgress) {
        return;
    }
    window.scormInitInProgress = true;
    
    function autoInitializeSCORM() {
        if (scormInitialized || typeof window.API === 'undefined') {
            return;
        }
        
        if (initRetryCount >= maxRetries) {
            console.log('[SCORM] Max retries reached, stopping auto-initialization');
            return;
        }
        
        try {
            console.log('[SCORM] Auto-initializing SCORM session... (attempt ' + (initRetryCount + 1) + ')');
            const initResult = window.API.Initialize('');
            if (initResult === 'true') {
                console.log('[SCORM] Auto-initialization successful');
                scormInitialized = true;
                
                // Set initial progress tracking with error handling
                try {
                    const statusResult = window.API.SetValue('cmi.core.lesson_status', 'incomplete');
                    const entryResult = window.API.SetValue('cmi.core.entry', 'ab-initio');
                    const commitResult = window.API.Commit('');
                    
                    console.log('[SCORM] Initial values set - Status:', statusResult, 'Entry:', entryResult, 'Commit:', commitResult);
                } catch (e) {
                    console.warn('[SCORM] Failed to set initial values:', e);
                }
                
                // Start progress tracking
                startProgressTracking();
            } else {
                console.warn('[SCORM] Auto-initialization failed, retrying...');
                initRetryCount++;
                setTimeout(autoInitializeSCORM, 2000);
            }
        } catch (e) {
            console.error('[SCORM] Auto-initialization error:', e);
            initRetryCount++;
            setTimeout(autoInitializeSCORM, 2000);
        }
    }
    
    function startProgressTracking() {
        // Track user interactions to update progress
        let interactionCount = 0;
        
        async function trackInteraction() {
            // DISABLED: Do not override Storyline's suspend_data
            // Storyline manages its own progress, quiz state, and bookmarking
            // Our interference was destroying Storyline's state data
            console.log('[SCORM] Interaction tracked - Storyline manages its own state');
        }
        
        // Track clicks, keypresses, and other interactions
        document.addEventListener('click', trackInteraction);
        document.addEventListener('keypress', trackInteraction);
        document.addEventListener('mousemove', function() {
            // Only track mousemove once per session
            if (interactionCount === 0) {
                trackInteraction();
            }
        });
        
        // Periodic progress updates
        setInterval(function() {
            if (interactionCount > 0) {
                window.API.Commit('');
            }
        }, 5000);
    }
    
    // Initialize when API is ready
    if (typeof window.API !== 'undefined') {
        autoInitializeSCORM();
    } else {
        // Wait for API to be available
        const checkAPI = setInterval(function() {
            if (typeof window.API !== 'undefined') {
                clearInterval(checkAPI);
                autoInitializeSCORM();
            }
        }, 100);
    }
})();

// Ensure API is available on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    if (typeof window.API !== 'undefined') {
        console.log('[SCORM] API confirmed available on DOM ready');
    } else {
        console.error('[SCORM] API still not available on DOM ready');
    }
});
</script>
'''
                    html_content = html_content.replace('</script>', '</script>' + api_check)
                    
                    content = html_content.encode('utf-8')
                    content_type = 'text/html; charset=utf-8'
                    
                    logger.info(f"✅ Injected SCORM API into {path} with attempt_id={attempt_id}")
                    logger.info(f"   API endpoint: {api_endpoint}")
                    logger.info(f"   Content length: {len(html_content)} chars")
                
                response_obj = HttpResponse(content, content_type=content_type)
                response_obj['Access-Control-Allow-Origin'] = '*'
                response_obj['X-Frame-Options'] = 'SAMEORIGIN'
                
                # CRITICAL: Set very permissive CSP for SCORM content files
                # SCORM content often uses eval(), dynamic code, and inline scripts
                response_obj['Content-Security-Policy'] = (
                    "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: *; "
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'unsafe-hashes' *; "
                    "style-src 'self' 'unsafe-inline' *; "
                    "img-src 'self' data: blob: *; "
                    "font-src 'self' data: *; "
                    "connect-src 'self' *; "
                    "media-src 'self' data: blob: *; "
                    "frame-src 'self' *; "
                    "object-src 'none'"
                )
                
                return response_obj
                
            except Exception as e:
                logger.error(f"Failed to process HTML content: {str(e)}")
                return HttpResponse(f'Failed to load content: {str(e)}', status=502)
        else:
            # For non-HTML files, determine content type and serve
            try:
                import mimetypes
                content_type, _ = mimetypes.guess_type(path)
                if not content_type:
                    content_type = 'application/octet-stream'
                
                response_obj = HttpResponse(content, content_type=content_type)
                response_obj['Access-Control-Allow-Origin'] = '*'
                return response_obj
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

