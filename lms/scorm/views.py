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
from django.core.cache import cache

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
    logger.warning("New handlers not available, using legacy handler: {}".format(e))


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
            
            if last_attempt:
                # CRITICAL FIX: Always resume existing attempt to preserve progress and location
                # This ensures learners can always return to their last saved location
                # even after completing the course
                attempt = last_attempt
                logger.info(f" SCORM Resume: Continuing existing attempt {attempt.attempt_number} for user {request.user.username}")
            else:
                # Create first attempt only if no previous attempt exists
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=1
                )
                logger.info(f" SCORM: Created new attempt {attempt.attempt_number} for user {request.user.username}")
        
        attempt_id = attempt.id
        attempt.is_preview = False  # Mark as real attempt
        
        # CRITICAL FIX: Refresh attempt data from database to get latest bookmark/suspend data
        attempt.refresh_from_db()
    
    # Generate content URL using Django proxy (for iframe compatibility)
    # Include attempt_id in the URL for API access
    # CRITICAL FIX: Properly structure URL with query parameters before hash fragment
    content_url = f'/scorm/content/{topic_id}/{scorm_package.launch_url}?attempt_id={attempt_id}'
    
    # ENHANCED: Add resume parameters BEFORE hash fragment (correct URL structure)
    if attempt.entry == 'resume' or (attempt.lesson_status != 'not_attempted' and attempt.lesson_status != 'not attempted'):
        content_url += '&resume=true'
        if attempt.lesson_location:
            content_url += f'&location={attempt.lesson_location}'
        if attempt.suspend_data:
            content_url += f'&suspend_data={attempt.suspend_data[:100]}'  # First 100 chars
        logger.info(f" SCORM Resume: Added resume parameters to content URL")
    
    # COMPREHENSIVE RESUME FIX: Handle all bookmark formats with fallbacks
    # CRITICAL FIX: Only add hash fragment ONCE at the end to avoid duplicates
    resume_needed = attempt.entry == 'resume' or (attempt.lesson_status != 'not_attempted' and attempt.lesson_status != 'not attempted')
    bookmark_applied = False
    hash_fragment = None
    
    # Case 1: Rise 360 format with lessons/ in lesson_location
    if attempt.lesson_location and 'lessons/' in attempt.lesson_location:
        # Extract lesson ID from lesson_location if it contains the lessons pattern
        lesson_id = attempt.lesson_location.split('lessons/')[-1] if 'lessons/' in attempt.lesson_location else ''
        if lesson_id:
            hash_fragment = f'#/lessons/{lesson_id}'
            logger.info(f" SCORM: Set lesson hash fragment: #/lessons/{lesson_id}")
            bookmark_applied = True
    
    # Case 2: Regular bookmark with or without hash
    elif attempt.lesson_location:
        # Handle lesson locations (avoid double hash)
        if attempt.lesson_location.startswith('#'):
            hash_fragment = attempt.lesson_location  # Already has hash
        else:
            hash_fragment = f'#{attempt.lesson_location}'  # Add hash
        logger.info(f" SCORM: Set location hash fragment: {hash_fragment}")
        bookmark_applied = True
    
    # Case 3: Extract bookmark from suspend_data if no direct bookmark exists
    elif attempt.suspend_data and resume_needed:
        # Try to extract location from suspend_data
        import re
        
        # Common patterns for bookmarks in suspend_data
        bookmark_patterns = [
            r'current_slide[=:]([^&]+)',        # current_slide=slide3
            r'current_location[=:]([^&]+)',      # current_location=slide3
            r'bookmark[=:]([^&]+)',              # bookmark=slide3
            r'\"bookmark\"[=:]\"([^\"]+)\"',     # "bookmark":"slide3"
            r'\"slide\"[=:]\"([^\"]+)\"',        # "slide":"slide3"
            r'\"location\"[=:]\"([^\"]+)\"',     # "location":"slide3"
            r'currentSlide[=:]([^&]+)',          # currentSlide=slide3
            r'slideId[=:]([^&]+)'                # slideId=slide3
        ]
        
        # Try all patterns
        for pattern in bookmark_patterns:
            match = re.search(pattern, attempt.suspend_data)
            if match:
                extracted_location = match.group(1).strip()
                if extracted_location:
                    # Set location in attempt
                    attempt.lesson_location = extracted_location
                    hash_fragment = f'#{extracted_location}'
                    attempt.save()
                    logger.info(f" SCORM Resume: Extracted bookmark '{extracted_location}' from suspend_data")
                    bookmark_applied = True
                    break
        
        # If no pattern matched but we know we need to resume
        if not bookmark_applied:
            # Use a generic slide ID based on progress percentage
            progress = attempt.progress_percentage or 0
            if progress > 75:
                default_slide = "slide_75"  # Near the end
            elif progress > 50:
                default_slide = "slide_50"  # Middle
            elif progress > 25:
                default_slide = "slide_25"  # Quarter way
            else:
                default_slide = "slide_1"   # Beginning
                
            attempt.lesson_location = default_slide
            hash_fragment = f'#{default_slide}'
            attempt.save()
            logger.info(f" SCORM Resume: Created default location '{default_slide}' based on progress {progress}%")
            bookmark_applied = True
            
    # Case 4: Always ensure resume works
    if resume_needed and not bookmark_applied:
        # Final fallback - use slide_1 as a safe default
        attempt.lesson_location = 'slide_1'
        hash_fragment = '#slide_1'
        attempt.save()
        logger.info(f" SCORM Resume: Created failsafe default location 'slide_1'")
    
    # CRITICAL FIX: Add hash fragment ONLY ONCE at the end
    if hash_fragment:
        content_url += hash_fragment
        logger.info(f" SCORM: Final content URL with hash: {content_url}")
    
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
            
            # CRITICAL FIX: Refresh attempt data from database to get latest bookmark/suspend data
            attempt.refresh_from_db()
            
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
            # COMPREHENSIVE FIX: More robust handler selection with caching to prevent race conditions
            # Use cache to ensure consistent handler selection for the same attempt
            cache_key = f'scorm_handler_type_{attempt_id}'
            try:
                handler_type = cache.get(cache_key)
            except Exception as cache_error:
                logger.warning(f"Cache error, using legacy handler: {cache_error}")
                handler_type = 'legacy'
            
            if handler_type == 'specialized':
                # Use specialized handler (cached decision)
                try:
                    handler = get_handler_for_attempt(attempt)
                    logger.info(f" Using cached specialized handler ({handler.get_handler_name()}) for attempt {attempt_id}")
                except Exception as e:
                    logger.error(f" Error with cached specialized handler, falling back to legacy: {e}")
                    handler = ScormAPIHandler(attempt)
                    # Update cache for future requests
                    try:
                        cache.set(cache_key, 'legacy', 3600)  # Cache for 1 hour
                    except Exception as cache_set_error:
                        logger.warning(f"Cache set error: {cache_set_error}")
                    logger.info(f"Using legacy ScormAPIHandler for attempt {attempt_id} (cache updated)")
            elif handler_type == 'legacy':
                # Use legacy handler (cached decision)
                handler = ScormAPIHandler(attempt)
                logger.info(f"Using cached legacy ScormAPIHandler for attempt {attempt_id}")
            else:
                # First time seeing this attempt, make a decision
                if USE_NEW_HANDLERS:
                    try:
                        handler = get_handler_for_attempt(attempt)
                        # Cache the decision for future requests
                        try:
                            cache.set(cache_key, 'specialized', 3600)  # Cache for 1 hour
                        except Exception as cache_set_error:
                            logger.warning(f"Cache set error: {cache_set_error}")
                        logger.info(f" Using specialized handler ({handler.get_handler_name()}) for attempt {attempt_id} (cached)")
                    except Exception as e:
                        logger.error(f" Error with new handler, falling back to legacy: {e}")
                        handler = ScormAPIHandler(attempt)
                        # Cache the decision for future requests
                        try:
                            cache.set(cache_key, 'legacy', 3600)  # Cache for 1 hour
                        except Exception as cache_set_error:
                            logger.warning(f"Cache set error: {cache_set_error}")
                        logger.info(f"Using legacy ScormAPIHandler for attempt {attempt_id} (cached)")
                else:
                    handler = ScormAPIHandler(attempt)
                    # Cache the decision for future requests
                    try:
                        cache.set(cache_key, 'legacy', 3600)  # Cache for 1 hour
                    except Exception as cache_set_error:
                        logger.warning(f"Cache set error: {cache_set_error}")
                    logger.info(f"Using legacy ScormAPIHandler for attempt {attempt_id} (cached)")
        
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
    Serve SCORM content files from S3 with streaming and caching support
    Proxies content to maintain same-origin policy for API access
    Handles multiple SCORM package structures with intelligent fallback
    OPTIMIZED: Added HTTP range support, caching headers, and video streaming
    """
    import hashlib
    from email.utils import formatdate
    from time import time
    
    try:
        # CRITICAL DEBUG: Log the incoming request
        
        topic = get_object_or_404(Topic, id=topic_id)
        
        # Check if topic has SCORM package
        try:
            scorm_package = topic.scorm_package
        except ScormPackage.DoesNotExist:
            return HttpResponse('SCORM package not found', status=404)
        
        # CRITICAL FIX: If path is empty or ends with /, use the launch_url
        if not path or path.endswith('/'):
            path = scorm_package.launch_url
        
        # PERFORMANCE OPTIMIZATION: Enhanced caching strategy
        # 1. Use a hierarchical cache structure
        # 2. Cache both S3 paths and actual content
        # 3. Use longer TTLs for static assets
        
        # Define cache keys and TTLs
        path_cache_key = f"scorm_s3_path:{topic_id}:{path}"
        content_cache_key = f"scorm_content:{topic_id}:{path}"
        path_ttl = 86400  # 24 hours for S3 paths
        content_ttl = 3600  # 1 hour for content (shorter to allow updates)
        
        # Special handling for static assets (longer TTL)
        is_static_asset = path.endswith(('.js', '.css', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.woff', '.woff2'))
        if is_static_asset:
            content_ttl = 604800  # 7 days for static assets
        
        # OPTIMIZATION: Check content cache first (fastest path)
        cached_content = cache.get(content_cache_key)
        if cached_content:
            logger.info(f" CACHE HIT: Serving content from cache for {path}")
            return HttpResponse(
                cached_content['data'],
                content_type=cached_content['content_type'],
                headers=cached_content.get('headers', {})
            )
        
        # Check S3 path cache next
        successful_key = cache.get(path_cache_key)
        
        # Initialize S3 client with better error handling
        import boto3
        from django.conf import settings
        from botocore.config import Config
        
        # Create optimized S3 config with timeouts and retries
        s3_config = Config(
            connect_timeout=3,  # 3 seconds connection timeout
            read_timeout=10,    # 10 seconds read timeout
            retries={'max_attempts': 3}  # Retry failed requests 3 times
        )
        
        try:
            # Initialize S3 client with optimized config
            s3_client = boto3.client(
                's3', 
                region_name=settings.AWS_S3_REGION_NAME,
                config=s3_config
            )
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
            # Fall back to basic client without region
            s3_client = boto3.client('s3', config=s3_config)
            
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        content = None
        
        # Try cached path first with timeout handling
        if successful_key:
            try:
                response = s3_client.get_object(Bucket=bucket_name, Key=successful_key)
                content = response['Body'].read()
                
                # Log cache performance metrics
                logger.info(f" S3 PATH CACHE HIT: Retrieved content using cached path: {successful_key}")
                
            except Exception as e:
                content = None
                successful_key = None
                cache.delete(path_cache_key)
                logger.warning(f" S3 PATH CACHE FAILURE: {str(e)}")
        
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
            
            
            # Try each path until one works
            # Add some additional common path patterns
            if 'story.html' in path:
                # Special handling for Storyline content
                path_attempts.append(f"media/{scorm_package.extracted_path}/story_content/{path.replace('story.html', '')}")
                path_attempts.append(f"{scorm_package.extracted_path}/story_content/{path.replace('story.html', '')}")
                
            for attempt_num, s3_key in enumerate(unique_paths, 1):
                try:
                    # Add timeout handling for S3 requests
                    response = s3_client.get_object(
                        Bucket=bucket_name, 
                        Key=s3_key,
                        ResponseCacheControl=f'max-age={content_ttl}'  # Suggest cache control to CDN
                    )
                    content = response['Body'].read()
                    successful_key = s3_key
                    
                    # Cache successful path with longer TTL
                    cache.set(path_cache_key, successful_key, path_ttl)
                    
                    # Log performance metrics
                    logger.info(f" Found content at path attempt #{attempt_num}: {s3_key}")
                    break
                    
                except s3_client.exceptions.NoSuchKey:
                    # Just skip quietly for NoSuchKey
                    continue
                    
                except Exception as e:
                    # Log other errors but continue trying
                    logger.warning(f"Error trying path {s3_key}: {str(e)}")
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
        
        # Determine content type
        import mimetypes
        content_type, _ = mimetypes.guess_type(path)
        if not content_type:
            content_type = 'application/octet-stream'
        
        # OPTIMIZATION: Check if this is a video/audio file that supports streaming
        is_media = content_type.startswith(('video/', 'audio/'))
        content_length = len(content)
        
        # OPTIMIZATION: Handle HTTP Range requests for video streaming
        range_header = request.META.get('HTTP_RANGE', '')
        if range_header and is_media:
            try:
                # Parse range header (e.g., "bytes=0-1023")
                range_match = range_header.replace('bytes=', '').split('-')
                start = int(range_match[0]) if range_match[0] else 0
                end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else content_length - 1
                
                # Ensure valid range
                if start >= content_length or end >= content_length or start > end:
                    return HttpResponse('Requested Range Not Satisfiable', status=416)
                
                # Slice content for range request
                range_content = content[start:end + 1]
                range_length = len(range_content)
                
                
                # Create partial content response
                response_obj = HttpResponse(range_content, content_type=content_type, status=206)
                response_obj['Content-Range'] = f'bytes {start}-{end}/{content_length}'
                response_obj['Content-Length'] = str(range_length)
                response_obj['Accept-Ranges'] = 'bytes'
                
                # Add caching headers for media
                response_obj['Cache-Control'] = 'public, max-age=86400, immutable'  # 24 hours
                response_obj['Access-Control-Allow-Origin'] = '*'
                response_obj['X-Frame-Options'] = 'SAMEORIGIN'
                
                return response_obj
                
            except (ValueError, IndexError) as e:
                logger.warning(f"Invalid range header: {range_header}, error: {e}")
                # Fall through to serve full content
        
        # Generate ETag for caching (using content hash)
        etag = hashlib.md5(content).hexdigest()
        
        # Check if client has cached version (ETag match)
        if_none_match = request.META.get('HTTP_IF_NONE_MATCH', '')
        if if_none_match == etag:
            response_obj = HttpResponse(status=304)
            response_obj['ETag'] = etag
            return response_obj
        
        # For HTML files, inject SCORM API (but use lighter injection for performance)
        if path.endswith(('.html', '.htm')):
            try:
                # Inject SCORM API for HTML files
                html_content = content.decode('utf-8')
                
                # PERFORMANCE: Check for non-entry point HTML files that don't need API injection
                # These can be cached longer for better performance
                is_entry_point = (
                    path == scorm_package.launch_url or
                    'index.html' in path or 
                    'story.html' in path or
                    'player.html' in path or
                    'loader.html' in path
                )
                
                if not is_entry_point:
                    # For secondary HTML files, cache longer
                    content_ttl = 86400  # Cache for 24 hours
                
               # Inject SCORM API that connects to the real API endpoint
                # Get attempt_id from the URL parameters with null safety
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
                
                # CRITICAL FIX: Add null safety check
                if not attempt_id or attempt_id == 'preview':
                    attempt_id = 'unknown'
                    logger.warning(f"SCORM Content: Using fallback attempt_id: {attempt_id}")
               
                api_endpoint = f'/scorm/api/{attempt_id}/'
                
                # Generate the JavaScript code with the actual attempt_id value
                # CRITICAL FIX: Use f-string to properly interpolate attempt_id
                api_injection = f'''
<script>
// CRITICAL FIX: SCORM API must be available immediately for Rise 360
// Rise 360 checks for API on page load, so we set it up synchronously
(function() {{
    // ENHANCED: Add debugging and monitoring
    window.SCORM_DEBUG = true;
    window.SCORM_API_CALLS = [];
    
    // Prevent multiple API loading with more robust checking
    if (window.API && 
        typeof window.API !== 'undefined' && 
        window.API_1484_11 && 
        typeof window.API_1484_11 !== 'undefined' && 
        window.API._initialized) {{
        console.log('[SCORM] API already loaded and initialized, skipping duplicate injection');
        return;
    }}
    
    // If API exists but not initialized, clean it up first
    if (window.API && typeof window.API !== 'undefined' && 
        window.API_1484_11 && typeof window.API_1484_11 !== 'undefined') {{
        console.log('[SCORM] Cleaning up existing API before re-initialization');
        try {{
            delete window.API;
            delete window.API_1484_11;
        }} catch (e) {{
            console.error('[SCORM] Error cleaning up API:', e);
            // Fallback: set to null if delete fails
            window.API = null;
            window.API_1484_11 = null;
        }}
    }}
    
    // SCORM API that connects to the real API endpoint
    // CRITICAL: Uses modern async/await to avoid synchronous XHR deprecation
    try {{
        // Create API with robust error handling
        window.API = window.API_1484_11 = {{
            _apiEndpoint: '{api_endpoint}',
            _lastError: '0',
            _initialized: false,
            _initPromise: null,
            
            // Add error tracking for debugging
            _errorCount: 0,
            _lastErrorMessage: '',
            _apiReady: true,
    
    _getCookie: function(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    },
    
    _makeAPICall: function(method, parameters) {
        try {
            // CRITICAL FIX: Use synchronous XMLHttpRequest for SCORM compatibility
            // SCORM content expects synchronous API calls
            console.log('[SCORM API] Making API call:', method, parameters);
            
            // Store API call for debugging
            if (window.SCORM_API_CALLS) {
                window.SCORM_API_CALLS.push({
                    method: method,
                    parameters: parameters,
                    timestamp: new Date().toISOString()
                });
            }
            
            const xhr = new XMLHttpRequest();
            xhr.open('POST', this._apiEndpoint, false); // false = synchronous
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', this._getCookie('csrftoken'));
            
            const requestData = JSON.stringify({ method: method, parameters: parameters || [] });
            console.log('[SCORM API] Sending request:', requestData);
            
            // ENHANCED: Add timeout handling
            xhr.timeout = 10000; // 10 second timeout
            
            try {
                xhr.send(requestData);
            } catch (sendError) {
                console.error('[SCORM API]  Failed to send request:', sendError);
                // Store data locally as fallback
                this._storeDataLocally(method, parameters);
                return 'true'; // Return success to prevent SCORM content from breaking
            }
            
            console.log('[SCORM API] Response status:', xhr.status);
            console.log('[SCORM API] Response text:', xhr.responseText);
            
            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                if (data.success) {
                    // ALWAYS log SetValue calls for debugging progress saving
                    if (method === 'SetValue' && parameters && parameters.length >= 2) {
                        console.log('[SCORM API]  SetValue SUCCESS:', parameters[0], '=', parameters[1], '->', data.result);
                    } else if (method === 'Initialize' || method === 'Terminate' || method === 'Commit') {
                        console.log('[SCORM API]  ' + method + ' SUCCESS -> ' + data.result);
                    }
                    return data.result;
                } else {
                    console.error('[SCORM API]  ' + method + ' FAILED:', data.error);
                    this._lastError = data.error_code || '101';
                    return 'false';
                }
            } else {
                console.error('[SCORM API]  HTTP ERROR:', xhr.status, xhr.responseText);
                this._lastError = '101';
                // Store data locally as fallback
                this._storeDataLocally(method, parameters);
                return 'false';
            }
        } catch (e) {
            console.error('[SCORM API]  EXCEPTION:', e);
            this._lastError = '101';
            // Store data locally as fallback
            this._storeDataLocally(method, parameters);
            return 'false';
        }
    },
    
    _storeDataLocally: function(method, parameters) {
        // Store failed API calls in localStorage for later sync
        try {
            const failedCalls = JSON.parse(localStorage.getItem('scorm_failed_calls') || '[]');
            failedCalls.push({
                method: method,
                parameters: parameters,
                timestamp: new Date().toISOString(),
                attempt_id: this._apiEndpoint.match(/\/(\d+)\//)[1]
            });
            localStorage.setItem('scorm_failed_calls', JSON.stringify(failedCalls));
            console.log('[SCORM API] Stored failed call locally for later sync');
        } catch (e) {
            console.error('[SCORM API] Failed to store data locally:', e);
        }
    },
    
    Initialize: function(param) {
        return this._makeAPICall('Initialize', [param]);
    },
            LMSInitialize: function(param) {
        return this._makeAPICall('Initialize', [param]);
    },
    Terminate: function(param) {
        return this._makeAPICall('Terminate', [param]);
    },
    LMSFinish: function(param) {
        return this._makeAPICall('Terminate', [param]);
    },
    GetValue: function(element) {
        return this._makeAPICall('GetValue', [element]);
    },
    LMSGetValue: function(element) {
        return this._makeAPICall('GetValue', [element]);
    },
    SetValue: function(element, value) {
        return this._makeAPICall('SetValue', [element, value]);
    },
    LMSSetValue: function(element, value) {
        return this._makeAPICall('SetValue', [element, value]);
    },
    Commit: function(param) {
        return this._makeAPICall('Commit', [param]);
    },
    LMSCommit: function(param) {
        return this._makeAPICall('Commit', [param]);
    },
    GetLastError: function() {
        return this._lastError;
    },
    LMSGetLastError: function() {
        return this._lastError;
    },
    GetErrorString: function(code) {
        return this._makeAPICall('GetErrorString', [code]);
    },
    LMSGetErrorString: function(code) {
        return this._makeAPICall('GetErrorString', [code]);
    },
    GetDiagnostic: function(code) {
        return this._makeAPICall('GetDiagnostic', [code]);
    },
    LMSGetDiagnostic: function(code) {
        return this._makeAPICall('GetDiagnostic', [code]);
    },
    
    // Additional SCORM functions that some content may require
    CommitData: function() {
        return this._makeAPICall('Commit', []);
    },
    ConcedeControl: function() {
        return 'true';
    },
    CreateResponseIdentifier: function() {
        return 'response_' + Date.now();
    },
    Finish: function() {
        return this._makeAPICall('Terminate', []);
    },
    GetDataChunk: function() {
        return '';
    },
    GetStatus: function() {
        return this._makeAPICall('GetValue', ['cmi.core.lesson_status']);
    },
    MatchingResponse: function() {
        return 'true';
    },
    RecordFillInInteraction: function() {
        return 'true';
    },
    RecordMatchingInteraction: function() {
        return 'true';
    },
    RecordMultipleChoiceInteraction: function() {
        return 'true';
    },
    ResetStatus: function() {
        return 'true';
    },
    SetBookmark: function(bookmark) {
        return this._makeAPICall('SetValue', ['cmi.core.lesson_location', bookmark]);
    },
    SetDataChunk: function(data) {
        return this._makeAPICall('SetValue', ['cmi.suspend_data', data]);
    },
    SetFailed: function() {
        return this._makeAPICall('SetValue', ['cmi.core.lesson_status', 'failed']);
    },
    SetLanguagePreference: function(lang) {
        return 'true';
    },
    SetPassed: function() {
        return this._makeAPICall('SetValue', ['cmi.core.lesson_status', 'passed']);
    },
    SetReachedEnd: function() {
        return this._makeAPICall('SetValue', ['cmi.core.lesson_status', 'completed']);
    },
    SetScore: function(score) {
        return this._makeAPICall('SetValue', ['cmi.core.score.raw', score]);
    },
    WriteToDebug: function(message) {
        console.log('[SCORM Debug]', message);
        return 'true';
    }
};
    
    // CRITICAL: Ensure API is available immediately for Rise 360
    console.log('[SCORM] API initialized with', Object.keys(window.API).length, 'functions');
    console.log('[SCORM] API endpoint:', window.API._apiEndpoint);
    
    // ENHANCED: Add auto-sync for failed calls
    window.API._syncFailedCalls = function() {
        try {
            const failedCalls = JSON.parse(localStorage.getItem('scorm_failed_calls') || '[]');
            if (failedCalls.length > 0) {
                console.log('[SCORM] Found', failedCalls.length, 'failed calls to sync');
                failedCalls.forEach(function(call) {
                    window.API._makeAPICall(call.method, call.parameters);
                });
                localStorage.removeItem('scorm_failed_calls');
            }
        } catch (e) {
            console.error('[SCORM] Error syncing failed calls:', e);
        }
    };
    
    // Sync failed calls after initialization
    setTimeout(function() {
        window.API._syncFailedCalls();
    }, 1000);
    
    } catch (setupError) {{
        // Handle initialization errors gracefully
        console.error('[SCORM] Critical error during API setup:', setupError);
        
        // Create minimal fallback API to prevent crashes
        if (!window.API) {{
            window.API = {
                _apiEndpoint: '/scorm/api/fallback/',
                _lastError: '101',
                _initialized: false,
                _errorState: true,
                
                // Minimal required methods
                Initialize: function() { return 'false'; },
                Terminate: function() { return 'false'; },
                GetValue: function() { return ''; },
                SetValue: function() { return 'false'; },
                Commit: function() { return 'false'; },
                GetLastError: function() { return '101'; },
                GetErrorString: function() { return 'API initialization failed'; },
                GetDiagnostic: function() { return 'API initialization error: ' + setupError.message; }
            };
            
            window.API_1484_11 = window.API;
            console.error('[SCORM] Created emergency fallback API');
        }
    }
}})();

    // ENHANCED: Auto-detect SCORM content initialization
(function() {
    var initAttempts = 0;
    var maxAttempts = 10;
    
    function detectAndInitializeSCORM() {
        initAttempts++;
        
        // Look for common SCORM content patterns
        var scormIndicators = [
            'doInitialize',
            'SCORMInit',
            'loadPage',
            'startCourse',
            'pipwerks',
            'ScormProcessInitialize',
            'doLMSInitialize'
        ];
        
        var foundIndicator = false;
        for (var i = 0; i < scormIndicators.length; i++) {
            if (typeof window[scormIndicators[i]] === 'function') {
                foundIndicator = true;
                console.log('[SCORM] Found SCORM indicator:', scormIndicators[i]);
                break;
            }
        }
        
        // If SCORM content detected but not initialized, try to initialize
        if (foundIndicator && window.API && !window.API._initialized) {
            console.log('[SCORM] Auto-initializing SCORM...');
            try {
                var result = window.API.Initialize('');
                console.log('[SCORM] Auto-initialization result:', result);
            } catch (e) {
                console.error('[SCORM] Auto-initialization error:', e);
            }
        }
        
        // Continue checking
        if (initAttempts < maxAttempts) {
            setTimeout(detectAndInitializeSCORM, 1000);
        }
    }
    
    // Start detection after page load
    if (document.readyState === 'complete') {
        detectAndInitializeSCORM();
    } else {
        window.addEventListener('load', detectAndInitializeSCORM);
    }
})();

// ENHANCED: Auto-resume functionality to skip START screen
(function() {
    function autoResumeSCORM() {
        // Check if this is a resume scenario
        var urlParams = new URLSearchParams(window.location.search);
        var isResume = urlParams.get('resume') === 'true';
        var location = urlParams.get('location');
        var suspendData = urlParams.get('suspend_data');
        
        if (isResume) {
            console.log('[SCORM] Resume mode detected - attempting to skip START screen');
            
            // Look for START button and auto-click it after a delay
            var startButton = document.querySelector('button[class*=\"start\"], button[class*=\"Start\"], button:contains(\"START\"), a[class*=\"start\"], a[class*=\"Start\"]');
            if (!startButton) {
                // Try alternative selectors
                var buttons = document.querySelectorAll('button, a, [role=\"button\"]');
                for (var i = 0; i < buttons.length; i++) {
                    var text = buttons[i].textContent ? buttons[i].textContent.trim() : '';
                    if (text.toLowerCase() === 'start' || text.toLowerCase() === 'begin') {
                        startButton = buttons[i];
                        break;
                    }
                }
            }
            
            if (startButton) {
                console.log('[SCORM] Found START button - auto-clicking in 2 seconds');
                setTimeout(function() {
                    try {
                        startButton.click();
                        console.log('[SCORM]  Auto-clicked START button for resume');
                    } catch (e) {
                        console.error('[SCORM] Error auto-clicking START button:', e);
                    }
                }, 2000);
            } else {
                console.log('[SCORM] No START button found - content may already be resumed');
            }
            
            // Also try to trigger any resume functions
            if (typeof window.resumeCourse === 'function') {
                setTimeout(function() {
                    try {
                        window.resumeCourse();
                        console.log('[SCORM] Called resumeCourse function');
                    } catch (e) {
                        console.error('[SCORM] Error calling resumeCourse:', e);
                    }
                }, 1000);
            }
        }
    }
    
    // Run auto-resume after page load
    if (document.readyState === 'complete') {
        autoResumeSCORM();
    } else {
        window.addEventListener('load', autoResumeSCORM);
    }
})();
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
    
    // CRITICAL FIX: Make API available in ALL possible locations for Storyline
    // Storyline checks multiple locations for the SCORM API
    if (window.API) {
        window.API_1484_11 = window.API;
        console.log('[SCORM] API_1484_11 set for SCORM 2004 compatibility');
    }
    
    // Make API available in parent window (for iframes)
    if (typeof window.parent !== 'undefined' && window.parent !== window) {
        try {
            window.parent.API = window.API;
            window.parent.API_1484_11 = window.API_1484_11;
            console.log('[SCORM] Parent window API set');
        } catch (e) {
            console.log('[SCORM] Cannot set parent API (cross-origin)');
        }
    }
    
    // Make API available in top window (for nested iframes)
    if (typeof window.top !== 'undefined' && window.top !== window) {
        try {
            window.top.API = window.API;
            window.top.API_1484_11 = window.API_1484_11;
            console.log('[SCORM] Top window API set');
        } catch (e) {
            console.log('[SCORM] Cannot set top API (cross-origin)');
        }
    }
    
    // ENHANCED: Create API finder function that SCORM content can use
    window.getAPI = function() {
        return window.API;
    };
    
    window.getAPIHandle = function() {
        if (window.API) return window.API;
        if (window.parent && window.parent.API) return window.parent.API;
        if (window.top && window.top.API) return window.top.API;
        return null;
    };
    
    // ENHANCED: Add Articulate-specific API detection
    window.GetAPI = function() {
        return window.API;
    };
    
    // ENHANCED: Create pipwerks SCORM wrapper compatibility
    window.pipwerks = window.pipwerks || {};
    window.pipwerks.SCORM = {
        version: "1.2",
        handleCompletionStatus: true,
        handleExitMode: true,
        API: {
            handle: window.API,
            find: function() { return window.API; },
            get: function() { return window.API; },
            getHandle: function() { return window.API; }
        },
        connection: {
            isActive: false,
            initialize: function() {
                if (window.API && !this.isActive) {
                    var result = window.API.Initialize('');
                    this.isActive = (result === 'true');
                    return this.isActive;
                }
                return false;
            },
            terminate: function() {
                if (window.API && this.isActive) {
                    var result = window.API.Terminate('');
                    this.isActive = false;
                    return (result === 'true');
                }
                return false;
            }
        },
        data: {
            get: function(param) {
                if (window.API) return window.API.GetValue(param);
                return '';
            },
            set: function(param, value) {
                if (window.API) return window.API.SetValue(param, value);
                return 'false';
            },
            save: function() {
                if (window.API) return window.API.Commit('');
                return 'false';
            }
        },
        debug: {
            getCode: function() {
                if (window.API) return window.API.GetLastError();
                return '0';
            },
            getInfo: function(code) {
                if (window.API) return window.API.GetErrorString(code);
                return '';
            },
            getDiagnosticInfo: function(code) {
                if (window.API) return window.API.GetDiagnostic(code);
                return '';
            }
        }
    };
    
    console.log('[SCORM] Enhanced API detection and compatibility layer installed');
    
    // CRITICAL: Log API availability for debugging
    console.log('[SCORM] API available at:');
    console.log('  - window.API:', typeof window.API !== 'undefined');
    console.log('  - window.API_1484_11:', typeof window.API_1484_11 !== 'undefined');
    try {
        console.log('  - window.parent.API:', typeof window.parent.API !== 'undefined');
    } catch (e) {}
    try {
        console.log('  - window.top.API:', typeof window.top.API !== 'undefined');
    } catch (e) {}
    
    // CRITICAL: Make API functions globally accessible for Storyline
    window.LMSInitialize = window.API.LMSInitialize;
    window.LMSFinish = window.API.LMSFinish;
    window.LMSGetValue = window.API.LMSGetValue;
    window.LMSSetValue = window.API.LMSSetValue;
    window.LMSCommit = window.API.LMSCommit;
    window.LMSGetLastError = window.API.LMSGetLastError;
    window.LMSGetErrorString = window.API.LMSGetErrorString;
    window.LMSGetDiagnostic = window.API.LMSGetDiagnostic;
    console.log('[SCORM] Global LMS functions set for Storyline compatibility');
    
    // CRITICAL FIX: Enhanced exit button functionality for Rise 360
    function enhanceExitButtons() {
        console.log('[SCORM] Enhancing exit buttons in content...');
        
        // Function to handle exit button clicks
        function handleExitClick(event) {
            console.log('[SCORM] Exit button clicked in content');
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            // Try to call SCORM API first
            try {
                if (window.API && window.API.LMSFinish) {
                    console.log('[SCORM] Calling LMSFinish...');
                    var result = window.API.LMSFinish('');
                    console.log('[SCORM] LMSFinish result:', result);
                } else if (window.API && window.API.Terminate) {
                    console.log('[SCORM] Calling Terminate...');
                    var result = window.API.Terminate('');
                    console.log('[SCORM] Terminate result:', result);
                }
            } catch (e) {
                console.error('[SCORM] Error calling SCORM API:', e);
            }
            
            // Send message to parent window to handle exit
            try {
                if (window.parent && window.parent !== window) {
                    window.parent.postMessage({
                        type: 'rise360Exit',
                        source: 'scorm-content'
                    }, window.location.origin);
                    console.log('[SCORM] Sent exit message to parent window');
                } else if (window.top && window.top !== window) {
                    window.top.postMessage({
                        type: 'rise360Exit',
                        source: 'scorm-content'
                    }, window.location.origin);
                    console.log('[SCORM] Sent exit message to top window');
                }
            } catch (e) {
                console.error('[SCORM] Error sending exit message:', e);
            }
            
            return false;
        }
        
        // Look for exit buttons and enhance them
        const exitSelectors = [
            'button[data-acc-text*="Exit" i]',
            'button[data-acc-text*="Save & Exit" i]',
            'button[data-acc-text*="Save and Exit" i]',
            'button[data-acc-text*="Close" i]',
            'button[data-acc-text*="Finish" i]',
            'button[data-acc-text*="Complete" i]',
            'button[data-acc-text*="Done" i]',
            'button[data-acc-text*="End" i]',
            'button[data-acc-text*="Quit" i]',
            'button[data-acc-text*="Stop" i]',
            'button[onclick*="exit" i]',
            'button[onclick*="save" i]',
            'button[onclick*="close" i]',
            'button[onclick*="finish" i]',
            'button[onclick*="complete" i]',
            'button[onclick*="done" i]',
            'button[onclick*="end" i]',
            'button[onclick*="quit" i]',
            'button[onclick*="stop" i]',
            'a[href*="exit" i]',
            'a[href*="close" i]',
            'a[href*="finish" i]',
            'a[href*="complete" i]',
            'a[href*="done" i]',
            'a[href*="end" i]',
            'a[href*="quit" i]',
            'a[href*="stop" i]',
            'button[aria-label*="Exit" i]',
            'button[aria-label*="Save & Exit" i]',
            'button[aria-label*="Save and Exit" i]',
            'button[aria-label*="Close" i]',
            'button[aria-label*="Finish" i]',
            'button[aria-label*="Complete" i]',
            'button[aria-label*="Done" i]',
            'button[aria-label*="End" i]',
            'button[aria-label*="Quit" i]',
            'button[aria-label*="Stop" i]',
            'a[aria-label*="Exit" i]',
            'a[aria-label*="Save & Exit" i]',
            'a[aria-label*="Save and Exit" i]',
            'a[aria-label*="Close" i]',
            'a[aria-label*="Finish" i]',
            'a[aria-label*="Complete" i]',
            'a[aria-label*="Done" i]',
            'a[aria-label*="End" i]',
            'a[aria-label*="Quit" i]',
            'a[aria-label*="Stop" i]',
            '.exit-button',
            '.save-exit-button',
            '.close-button',
            '.finish-button',
            '.complete-button',
            '.done-button',
            '.end-button',
            '.quit-button',
            '.stop-button',
            '#exit-button',
            '#save-exit-button',
            '#close-button',
            '#finish-button',
            '#complete-button',
            '#done-button',
            '#end-button',
            '#quit-button',
            '#stop-button'
        ];
        
        exitSelectors.forEach(selector => {
            try {
                const elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    if (!element.hasAttribute('data-scorm-enhanced')) {
                        element.setAttribute('data-scorm-enhanced', 'true');
                        element.onclick = null; // Remove existing handlers
                        element.addEventListener('click', handleExitClick);
                        console.log('[SCORM] Enhanced exit button:', element);
                    }
                });
            } catch (e) {
                // Silently handle selector errors
            }
        });
        
        // Also look for text-based exit buttons
        const clickableElements = document.querySelectorAll('button, a, [role="button"]');
        clickableElements.forEach(element => {
            const text = element.textContent ? element.textContent.trim().toLowerCase() : '';
            const isExitButton = (
                text === 'exit' || text === 'exit course' || text === 'close' || 
                text === 'save & exit' || text === 'save and exit' || text === 'save exit' ||
                text === 'finish' || text === 'complete' || text === 'done' || 
                text === 'end' || text === 'quit' || text === 'stop' ||
                text === 'finish course' || text === 'complete course' || text === 'end course' ||
                text === 'close course' || text === 'quit course' || text === 'stop course' ||
                (text.includes('save') && text.includes('exit')) ||
                (text.includes('finish') && text.includes('course')) ||
                (text.includes('complete') && text.includes('course')) ||
                (text.includes('end') && text.includes('course')) ||
                (text.includes('close') && text.includes('course')) ||
                (text.includes('quit') && text.includes('course')) ||
                (text.includes('stop') && text.includes('course'))
            );
            
            if (isExitButton && !element.hasAttribute('data-scorm-enhanced')) {
                element.setAttribute('data-scorm-enhanced', 'true');
                element.style.cursor = 'pointer';
                element.onclick = null; // Remove existing handlers
                element.addEventListener('click', handleExitClick);
                console.log('[SCORM] Enhanced text exit button:', element.textContent.trim());
            }
        });
    }
    
    // ARCHITECTURAL IMPROVEMENT: Don't interfere with SCORM content's internal features
    // Instead of enhancing exit buttons which might interfere with SCORM content's functionality,
    // we'll just log that we're respecting the SCORM content's internal features
    console.log('[SCORM] Respecting SCORM content\'s internal exit functionality');
    
    // Only add minimal logging to help with debugging
    if (window.API && window.API.LMSFinish) {
        const originalLMSFinish = window.API.LMSFinish;
        window.API.LMSFinish = function() {
            console.log('[SCORM] LMSFinish called by content');
            return originalLMSFinish.apply(this, arguments);
        };
    }
    
    // CRITICAL FIX: Prevent infinite loops with global flag
    if (window.scormEnhancementActive) {
        console.log('[SCORM] Enhancement already active, skipping duplicate');
        return;
    }
    window.scormEnhancementActive = true;
    
    let enhancementAttempts = 0;
    const maxEnhancementAttempts = 5; // Reduced to 5 attempts
    let enhancementInterval = null;
    
    function limitedEnhanceExitButtons() {
        if (enhancementAttempts >= maxEnhancementAttempts) {
            console.log('[SCORM] Max enhancement attempts reached, stopping');
            if (enhancementInterval) {
                clearInterval(enhancementInterval);
                enhancementInterval = null;
            }
            return;
        }
        enhancementAttempts++;
        enhanceExitButtons();
    }
    
    // Run a limited number of times with increasing intervals to avoid excessive CPU usage
    const enhancementIntervals = [1000, 2000, 3000, 5000, 8000]; // Use Fibonacci-like increasing intervals
    let enhancementIndex = 0;
    
    function scheduleNextEnhancement() {
        if (enhancementIndex >= enhancementIntervals.length) {
            console.log('[SCORM] Exit button enhancement completed after ' + enhancementIndex + ' attempts');
            return; // Stop scheduling when we've used all intervals
        }
        
        const currentInterval = enhancementIntervals[enhancementIndex];
        setTimeout(() => {
            limitedEnhanceExitButtons();
            enhancementIndex++;
            scheduleNextEnhancement(); // Schedule next one with increasing interval
        }, currentInterval);
    }
    
    // Start the enhancement sequence
    scheduleNextEnhancement();
})();

// CRITICAL FIX: Enhanced Exit button functionality
// This ensures Exit buttons inside SCORM content work properly
(function() {
    // Function to redirect back to topic view page after SCORM exit
    function redirectToCourse() {
        console.log('[SCORM] Redirecting back to topic view...');
        
        // Try to get the topic view URL from various sources
        var topicUrl = null;
        
        // Method 1: Extract topic ID from current SCORM URL
        var currentUrl = window.location.href;
        var topicMatch = currentUrl.match(/\/scorm\/content\/(\d+)\//);
        if (topicMatch) {
            var topicId = topicMatch[1];
            topicUrl = '/scorm/view/' + topicId + '/';
            console.log('[SCORM] Found topic ID from URL:', topicId);
        }
        
        // Method 2: Check if we're in an iframe and get parent URL
        if (!topicUrl && window.parent && window.parent !== window) {
            try {
                // Get the referrer URL to determine topic
                var referrer = document.referrer;
                if (referrer) {
                    // Extract topic ID from referrer
                    var topicMatch = referrer.match(/\/scorm\/view\/(\d+)/);
                    if (topicMatch) {
                        topicUrl = '/scorm/view/' + topicMatch[1] + '/';
                        console.log('[SCORM] Found topic ID from referrer:', topicMatch[1]);
                    }
                }
            } catch (e) {
                console.log('[SCORM] Cannot access parent window:', e);
            }
        }
        
        // Method 3: Try to get topic URL from current URL parameters
        if (!topicUrl) {
            // Use a simpler approach to get URL params for better compatibility
            function getParameterByName(name, url) {
                if (!url) url = window.location.search;
                name = name.replace(/[\[\]]/g, '\\$&');
                var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)'),
                    results = regex.exec(url);
                if (!results) return null;
                if (!results[2]) return '';
                return decodeURIComponent(results[2].replace(/\+/g, ' '));
            }
            
            var topicId = getParameterByName('topic_id');
            if (topicId) {
                topicUrl = '/scorm/view/' + topicId + '/';
                console.log('[SCORM] Found topic ID from parameters:', topicId);
            }
        }
        
        // Method 4: Default fallback - go to course list
        if (!topicUrl) {
            topicUrl = '/courses/';
            console.log('[SCORM] Using fallback - course list');
        }
        
        console.log('[SCORM] Redirecting to topic view:', topicUrl);
        
        // Perform the redirect
        if (window.parent && window.parent !== window) {
            // If in iframe, redirect parent window
            window.parent.location.href = topicUrl;
        } else {
            // If not in iframe, redirect current window
            window.location.href = topicUrl;
        }
    }
    
    function enhanceExitButtons() {
        // CRITICAL FIX: Enhanced exit button detection with cross-origin support
        var doc = this.document || document;
        
        // Look for ALL possible Exit button patterns in SCORM content
        var exitSelectors = [
            // Articulate Storyline/Rise buttons
            'button[data-acc-text*="Exit" i]',
            'button[data-acc-text*="Save & Exit" i]',
            'button[data-acc-text*="Save and Exit" i]',
            'button[data-acc-text*="Close" i]',
            'button[data-acc-text*="Finish" i]',
            'button[data-acc-text*="Complete" i]',
            'button[data-acc-text*="Done" i]',
            'button[data-acc-text*="End" i]',
            'button[data-acc-text*="Quit" i]',
            'button[data-acc-text*="Stop" i]',
            '.slide-object[data-acc-text*="Exit" i]',
            '.slide-object[data-acc-text*="Save & Exit" i]',
            '.slide-object[data-acc-text*="Save and Exit" i]',
            '.slide-object[data-acc-text*="Close" i]',
            '.slide-object[data-acc-text*="Finish" i]',
            '.slide-object[data-acc-text*="Complete" i]',
            '.slide-object[data-acc-text*="Done" i]',
            '.slide-object[data-acc-text*="End" i]',
            '.slide-object[data-acc-text*="Quit" i]',
            '.slide-object[data-acc-text*="Stop" i]',
            // Generic button patterns
            'button[onclick*="exit" i]',
            'button[onclick*="save" i]',
            'button[onclick*="close" i]',
            'button[onclick*="finish" i]',
            'button[onclick*="complete" i]',
            'button[onclick*="done" i]',
            'button[onclick*="end" i]',
            'button[onclick*="quit" i]',
            'button[onclick*="stop" i]',
            // Link patterns
            'a[href*="exit" i]',
            'a[href*="close" i]',
            'a[href*="finish" i]',
            'a[href*="complete" i]',
            'a[href*="done" i]',
            'a[href*="end" i]',
            'a[href*="quit" i]',
            'a[href*="stop" i]',
            // Aria labels
            'button[aria-label*="Exit" i]',
            'button[aria-label*="Save & Exit" i]',
            'button[aria-label*="Save and Exit" i]',
            'button[aria-label*="Close" i]',
            'button[aria-label*="Finish" i]',
            'button[aria-label*="Complete" i]',
            'button[aria-label*="Done" i]',
            'button[aria-label*="End" i]',
            'button[aria-label*="Quit" i]',
            'button[aria-label*="Stop" i]',
            'a[aria-label*="Exit" i]',
            'a[aria-label*="Save & Exit" i]',
            'a[aria-label*="Save and Exit" i]',
            'a[aria-label*="Close" i]',
            'a[aria-label*="Finish" i]',
            'a[aria-label*="Complete" i]',
            'a[aria-label*="Done" i]',
            'a[aria-label*="End" i]',
            'a[aria-label*="Quit" i]',
            'a[aria-label*="Stop" i]',
            // CSS classes and IDs
            '.exit-button',
            '.save-exit-button',
            '.close-button',
            '.finish-button',
            '.complete-button',
            '.done-button',
            '.end-button',
            '.quit-button',
            '.stop-button',
            '#exit-button',
            '#save-exit-button',
            '#close-button',
            '#finish-button',
            '#complete-button',
            '#done-button',
            '#end-button',
            '#quit-button',
            '#stop-button'
        ];
        
        for (var s = 0; s < exitSelectors.length; s++) {
            try {
                var selector = exitSelectors[s];
                var elements = doc.querySelectorAll(selector);
                for (var j = 0; j < elements.length; j++) {
                    var element = elements[j];
                    if (!element.hasAttribute('data-scorm-enhanced')) {
                        element.setAttribute('data-scorm-enhanced', 'true');
                        
                        // Add click handler for Exit functionality
                        element.addEventListener('click', function(e) {
                            console.log('[SCORM] Exit button clicked - triggering Save & Exit button');
                            
                            // Prevent default behavior
                            e.preventDefault();
                            e.stopPropagation();
                            
                            // Simple approach: trigger parent page's Save & Exit button
                            try {
                                // Try to find Save & Exit button in parent window
                                if (window.parent && window.parent !== window) {
                                    var parentExitBtn = window.parent.document.getElementById('saveExitBtn');
                                    if (parentExitBtn) {
                                        console.log('[SCORM] Found parent Save & Exit button, triggering click');
                                        parentExitBtn.click();
                                        return false;
                                    }
                                }
                                
                                // If we can't find the button, use regular exit
                                if (window.API && window.API.LMSCommit) {
                                    window.API.LMSCommit('');
                                }
                                redirectToCourse();
                            } catch (ex) {
                                console.log('[SCORM] Error triggering Save & Exit:', ex);
                                redirectToCourse();
                            }
                            
                            return false;
                        });
                        
                        console.log('[SCORM] Enhanced Exit button:', element);
                    }
                }
            } catch (e) {
                // Silently handle unsupported selectors to avoid console spam
            }
        }
        
        // Also look for text-based Exit buttons (only clickable elements)
        var clickableElements = doc.querySelectorAll('button, a, [role="button"]');
        for (var i = 0; i < clickableElements.length; i++) {
            var element = clickableElements[i];
            var text = element.textContent ? element.textContent.trim().toLowerCase() : '';
            // Check for ALL possible exit-related text patterns
            var isExitButton = (
                text === 'exit' || text === 'exit course' || text === 'close' || 
                text === 'save & exit' || text === 'save and exit' || text === 'save exit' ||
                text === 'finish' || text === 'complete' || text === 'done' || 
                text === 'end' || text === 'quit' || text === 'stop' ||
                text === 'finish course' || text === 'complete course' || text === 'end course' ||
                text === 'close course' || text === 'quit course' || text === 'stop course' ||
                (text.indexOf('save') !== -1 && text.indexOf('exit') !== -1) ||
                (text.indexOf('finish') !== -1 && text.indexOf('course') !== -1) ||
                (text.indexOf('complete') !== -1 && text.indexOf('course') !== -1) ||
                (text.indexOf('end') !== -1 && text.indexOf('course') !== -1) ||
                (text.indexOf('close') !== -1 && text.indexOf('course') !== -1) ||
                (text.indexOf('quit') !== -1 && text.indexOf('course') !== -1) ||
                (text.indexOf('stop') !== -1 && text.indexOf('course') !== -1)
            );
            
            if (isExitButton && !element.hasAttribute('data-scorm-enhanced')) {
                element.setAttribute('data-scorm-enhanced', 'true');
                element.style.cursor = 'pointer';
                
                element.addEventListener('click', function(e) {
                    console.log('[SCORM] Text Exit button clicked - triggering Save & Exit button');
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Simple approach: trigger parent page's Save & Exit button
                    try {
                        // Try to find Save & Exit button in parent window
                        if (window.parent && window.parent !== window) {
                            var parentExitBtn = window.parent.document.getElementById('saveExitBtn');
                            if (parentExitBtn) {
                                console.log('[SCORM] Found parent Save & Exit button, triggering click');
                                parentExitBtn.click();
                                return false;
                            }
                        }
                        
                        // If we can't find the button, use regular exit
                        if (window.API && window.API.LMSCommit) {
                            window.API.LMSCommit('');
                        }
                        redirectToCourse();
                    } catch (ex) {
                        console.log('[SCORM] Error triggering Save & Exit:', ex);
                        redirectToCourse();
                    }
                    
                    return false;
                });
            }
        }
    }
    
    // Run immediately and on DOM ready
    enhanceExitButtons();
    document.addEventListener('DOMContentLoaded', enhanceExitButtons);
    
    // CRITICAL FIX: Smart progress tracking with loop prevention
    // This ensures progress is saved without causing infinite loops
    function startSmartProgressTracking() {
        console.log('[SCORM] Starting smart progress tracking...');
        
        let progressCheckInterval;
        let lastKnownLocation = '';
        let lastKnownStatus = '';
        let progressCheckCount = 0;
        let maxChecks = 30; // Maximum 30 checks (1 minute total)
        let isTracking = true;
        
        // Check for progress every 2 seconds, but with smart limits
        progressCheckInterval = setInterval(function() {
            if (!isTracking) {
                clearInterval(progressCheckInterval);
                return;
            }
            
            progressCheckCount++;
            
            // Stop after max checks to prevent infinite loops
            if (progressCheckCount > maxChecks) {
                console.log('[SCORM] Progress tracking stopped after ' + maxChecks + ' checks');
                clearInterval(progressCheckInterval);
                isTracking = false;
                return;
            }
            
            // Only log every 5th check to reduce spam
            if (progressCheckCount % 5 === 0) {
                console.log('[SCORM] Progress check #' + progressCheckCount);
            }
            
            // Try to detect progress from SCORM API only
            let currentLocation = '';
            let currentStatus = '';
            
            // Method 1: Check SCORM API values (most reliable)
            if (window.API && window.API._initialized) {
                try {
                    const location = window.API.GetValue('cmi.core.lesson_location');
                    const status = window.API.GetValue('cmi.core.lesson_status');
                    
                    if (location && location !== '') {
                        currentLocation = location;
                    }
                    
                    if (status && status !== 'not attempted') {
                        currentStatus = status;
                    }
                } catch (e) {
                    // Silently handle errors to avoid console spam
                }
            }
            
            // Only save if we detected NEW progress (avoid loops)
            let shouldSave = false;
            
            if (currentLocation !== '' && currentLocation !== lastKnownLocation) {
                console.log('[SCORM] New location detected:', currentLocation);
                shouldSave = true;
                lastKnownLocation = currentLocation;
            }
            
            if (currentStatus !== '' && currentStatus !== lastKnownStatus) {
                console.log('[SCORM] New status detected:', currentStatus);
                shouldSave = true;
                lastKnownStatus = currentStatus;
            }
            
            // Save progress only if we detected changes
            if (shouldSave && window.API && window.API._initialized) {
                try {
                    if (currentLocation !== '') {
                        window.API.SetValue('cmi.core.lesson_location', currentLocation);
                    }
                    if (currentStatus !== '') {
                        window.API.SetValue('cmi.core.lesson_status', currentStatus);
                    }
                    window.API.Commit('');
                    console.log('[SCORM]  Progress saved successfully');
                    
                    // Stop tracking after successful save to prevent loops
                    clearInterval(progressCheckInterval);
                    isTracking = false;
                    console.log('[SCORM] Progress tracking completed successfully');
                } catch (e) {
                    console.error('[SCORM] Error saving progress:', e);
                }
            }
        }, 2000); // Check every 2 seconds
    }
    
    // REMOVED: Smart progress tracking - causes loops and not needed
    // Storyline will call SCORM API directly when user interacts with content
    
    // CRITICAL FIX: Enhanced exit button detection with better timing
    // Wait for SCORM content to fully load before enhancing exit buttons
    function waitForScormContent() {
        const maxAttempts = 50; // 10 seconds max wait
        let attempts = 0;
        
        function checkForScormContent() {
            attempts++;
            
            // Check if SCORM content is loaded (iframe or direct content)
            const iframe = document.querySelector('iframe[src*="scorm"]');
            const scormContent = document.querySelector('[data-scorm-content]') || 
                               document.querySelector('.scorm-content') ||
                               document.querySelector('body[data-scorm]');
            
            if (iframe || scormContent || attempts >= maxAttempts) {
                console.log('[SCORM] Content detected, enhancing exit buttons...');
                enhanceExitButtons();
                
                // Also enhance buttons in iframe if present
                if (iframe) {
                    try {
                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        if (iframeDoc) {
                            // Wait a bit more for iframe content to load
                            setTimeout(() => {
                                try {
                                    enhanceExitButtons.call({ document: iframeDoc });
                                } catch (e) {
                                    console.log('[SCORM] Cannot enhance iframe buttons (cross-origin):', e.message);
                                }
                            }, 1000);
                        }
                    } catch (e) {
                        console.log('[SCORM] Cannot access iframe content (cross-origin):', e.message);
                    }
                }
            } else {
                setTimeout(checkForScormContent, 200);
            }
        }
        
        checkForScormContent();
    }
    
    // Start the enhanced detection
    waitForScormContent();
    
    // Also run periodically to catch dynamically loaded content
    setInterval(enhanceExitButtons, 2000);
})();

// CRITICAL FIX: Improved SCORM initialization with better error handling
(function() {
    let scormInitialized = false;
    let initRetryCount = 0;
    const maxRetries = 2; // Reduced from 3 to prevent excessive retries
    
    // Global flag to prevent multiple initialization attempts
    if (window.scormInitInProgress) {
        console.log('[SCORM] Initialization already in progress, skipping');
        return;
    }
    window.scormInitInProgress = true;
    
    function autoInitializeSCORM() {
        if (scormInitialized || typeof window.API === 'undefined') {
            return;
        }
        
        if (initRetryCount >= maxRetries) {
            console.log('[SCORM] Max retries reached, stopping auto-initialization');
            window.scormInitInProgress = false; // Reset flag
            return;
        }
        
        try {
            console.log('[SCORM] Auto-initializing SCORM session... (attempt ' + (initRetryCount + 1) + ')');
            
            // CRITICAL FIX: Use synchronous call since SCORM API is synchronous
            try {
                const initResult = window.API.Initialize('');
                if (initResult === 'true') {
                    console.log('[SCORM] Auto-initialization successful');
                    scormInitialized = true;
                    window.scormInitInProgress = false; // Reset flag
                    
                    // Set initial progress tracking with error handling
                    try {
                        window.API.SetValue('cmi.core.lesson_status', 'incomplete');
                        window.API.SetValue('cmi.core.entry', 'ab-initio');
                        window.API.Commit('');
                        console.log('[SCORM] Initial values set successfully');
                    } catch (e) {
                        console.warn('[SCORM] Failed to set initial values:', e);
                    }
                    
                    // Start progress tracking
                    startProgressTracking();
                } else {
                    console.warn('[SCORM] Auto-initialization failed, retrying...');
                    initRetryCount++;
                    setTimeout(autoInitializeSCORM, 1000); // Reduced delay
                }
            } catch (e) {
                console.error('[SCORM] Auto-initialization error:', e);
                initRetryCount++;
                setTimeout(autoInitializeSCORM, 1000); // Reduced delay
            }
        } catch (e) {
            console.error('[SCORM] Auto-initialization error:', e);
            initRetryCount++;
            setTimeout(autoInitializeSCORM, 1000); // Reduced delay
        }
    }
    
    function startProgressTracking() {
        // Track user interactions to update progress
        let interactionCount = 0;
        let lastInteractionTime = 0;
        const INTERACTION_THROTTLE = 2000; // Only track interactions every 2 seconds
        
        async function trackInteraction() {
            const now = Date.now();
            if (now - lastInteractionTime < INTERACTION_THROTTLE) {
                return; // Throttle interactions
            }
            lastInteractionTime = now;
            interactionCount++;
            
            // Only log significant interactions, not every mouse movement
            if (interactionCount % 10 === 0) {
                console.log('[SCORM] Interaction tracked - Storyline manages its own state');
            }
        }
        
        // Track clicks and keypresses (but not mousemove to reduce spam)
        document.addEventListener('click', trackInteraction);
        document.addEventListener('keypress', trackInteraction);
        
        // Periodic progress updates (reduced frequency)
        setInterval(function() {
            if (interactionCount > 0) {
                window.API.Commit('');
            }
        }, 10000); // Increased from 5s to 10s
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

// ENHANCED: Auto-save mechanism
(function() {
    var autoSaveInterval = 30000; // 30 seconds
    var lastActivity = Date.now();
    var autoSaveTimer = null;
    
    function trackActivity() {
        lastActivity = Date.now();
    }
    
    // Track user activity
    document.addEventListener('click', trackActivity);
    document.addEventListener('keypress', trackActivity);
    document.addEventListener('mousemove', trackActivity);
    
    function autoSave() {
        // Only save if there was recent activity
        if (Date.now() - lastActivity < 60000) { // Activity in last minute
            if (window.API && window.API._initialized && typeof window.API.Commit === 'function') {
                console.log('[SCORM] Auto-saving progress...');
                try {
                    var result = window.API.Commit('');
                    console.log('[SCORM] Auto-save result:', result);
                } catch (e) {
                    console.error('[SCORM] Auto-save error:', e);
                }
            }
        }
    }
    
    // Start auto-save timer
    autoSaveTimer = setInterval(autoSave, autoSaveInterval);
    
    // Save on page unload
    window.addEventListener('beforeunload', function(e) {
        if (window.API && window.API._initialized) {
            console.log('[SCORM] Saving on page unload...');
            try {
                window.API.Commit('');
                window.API.Terminate('');
            } catch (error) {
                console.error('[SCORM] Error saving on unload:', error);
            }
        }
    });
    
    // Save on visibility change (tab switch)
    document.addEventListener('visibilitychange', function() {
        if (document.hidden && window.API && window.API._initialized) {
            console.log('[SCORM] Saving on tab switch...');
            try {
                window.API.Commit('');
            } catch (error) {
                console.error('[SCORM] Error saving on tab switch:', error);
            }
        }
    });
})();
</script>
'''
                html_content = html_content.replace('</script>', '</script>' + api_check)
                
                content = html_content.encode('utf-8')
                content_type = 'text/html; charset=utf-8'
                
                logger.info(f" Injected SCORM API into {path} with attempt_id={attempt_id}")
                logger.info(f"   API endpoint: {api_endpoint}")
                logger.info(f"   Content length: {len(html_content)} chars")
                
                # Cache the processed HTML content for faster retrieval next time
                response_headers = {
                    'ETag': etag,
                    'Cache-Control': f'public, max-age={content_ttl}',
                    'Last-Modified': formatdate(time(), usegmt=True),
                    'Access-Control-Allow-Origin': '*',
                    'X-Frame-Options': 'SAMEORIGIN',
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(len(content))
                }
                
                # Store content in cache for faster retrieval
                cache.set(
                    content_cache_key, 
                    {
                        'data': content,
                        'content_type': content_type,
                        'headers': response_headers,
                        'etag': etag
                    },
                    content_ttl
                )
                
                # Log cache storage
                logger.info(f" Stored content in cache (TTL={content_ttl}s): {content_cache_key}")
                
                # Create response with all headers
                response_obj = HttpResponse(content, content_type=content_type)
                for header, value in response_headers.items():
                    response_obj[header] = value
                
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
            # For non-HTML files (CSS, JS, images, videos, etc.), serve with aggressive caching
            try:
                # Define optimal cache TTL by file type
                if is_media:
                    # Videos and audio - cache for 1 week
                    content_ttl = 604800
                    immutable = True
                elif path.endswith(('.js', '.css')):
                    # Scripts and styles - cache for 3 days
                    content_ttl = 259200
                    immutable = True
                elif path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico')):
                    # Images - cache for 1 week
                    content_ttl = 604800
                    immutable = True
                elif path.endswith(('.woff', '.woff2', '.ttf', '.otf', '.eot')):
                    # Fonts - cache for 2 weeks
                    content_ttl = 1209600
                    immutable = True
                else:
                    # Other files - cache for 1 day
                    content_ttl = 86400
                    immutable = False
                
                # Prepare cache headers
                cache_control = f"public, max-age={content_ttl}"
                if immutable:
                    cache_control += ", immutable"
                
                # Prepare headers for CDN compatibility
                response_headers = {
                    'ETag': etag,
                    'Last-Modified': formatdate(time(), usegmt=True),
                    'Access-Control-Allow-Origin': '*',
                    'X-Frame-Options': 'SAMEORIGIN',
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(content_length),
                    'Cache-Control': cache_control
                }
                
                # Store in cache for next time
                cache.set(
                    content_cache_key,
                    {
                        'data': content,
                        'content_type': content_type,
                        'headers': response_headers,
                        'etag': etag
                    },
                    content_ttl
                )
                
                # Log cache storage for performance monitoring
                if is_media or path.endswith(('.js', '.css')):
                    logger.info(f" Cached {content_type} asset ({len(content)} bytes) for {content_ttl/3600:.1f} hours")
                
                # Create response with all headers
                response_obj = HttpResponse(content, content_type=content_type)
                for header, value in response_headers.items():
                    response_obj[header] = value
                
                
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

