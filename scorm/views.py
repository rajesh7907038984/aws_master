import os
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
# Removed unused default_storage import - using SCORMS3Storage instead
from django.utils import timezone
from django.contrib import messages
from django.db import transaction

from .models import ELearningPackage, ELearningTracking, SCORMReport
from courses.models import Topic, Course
from users.models import CustomUser
# SCORM2004Sequencing and SCORM2004ActivityState models removed

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["GET"])
def extraction_progress(request, topic_id):
    """Get extraction progress for a SCORM package"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        if not hasattr(topic, 'elearning_package') or not topic.elearning_package:
            return JsonResponse({'error': 'No e-learning package found'}, status=404)
        
        package = topic.elearning_package
        
        progress_data = {
            'is_extracted': package.is_extracted,
            'extraction_error': package.extraction_error,
            'package_type': package.package_type,
            'title': package.title,
            'status': 'completed' if package.is_extracted else 'extracting' if not package.extraction_error else 'failed'
        }
        
        return JsonResponse(progress_data)
        
    except Exception as e:
        logger.error(f"Error getting extraction progress: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

def is_mobile_device(request):
    """Enhanced mobile device detection with better browser support"""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    
    # Enhanced mobile keywords for better detection
    mobile_keywords = [
        'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone',
        'mobile', 'opera mini', 'iemobile', 'webos', 'palm', 'kindle',
        'silk', 'playbook', 'bb10', 'windows mobile', 'windows ce',
        'pocket', 'palm', 'smartphone', 'tablet', 'touch'
    ]
    
    # Check for mobile-specific patterns
    mobile_patterns = [
        r'mobile.*safari',
        r'android.*chrome',
        r'iphone.*safari',
        r'ipad.*safari',
        r'opera.*mini',
        r'firefox.*mobile'
    ]
    
    import re
    for pattern in mobile_patterns:
        if re.search(pattern, user_agent):
            return True
    
    return any(keyword in user_agent for keyword in mobile_keywords)

def get_browser_info(request):
    """Get detailed browser information for compatibility handling"""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    
    browser_info = {
        'is_mobile': is_mobile_device(request),
        'is_ie': 'msie' in user_agent or 'trident' in user_agent,
        'is_edge': 'edge' in user_agent,
        'is_chrome': 'chrome' in user_agent and 'edge' not in user_agent,
        'is_firefox': 'firefox' in user_agent,
        'is_safari': 'safari' in user_agent and 'chrome' not in user_agent,
        'is_webkit': 'webkit' in user_agent,
        'supports_es6': not ('msie' in user_agent or 'trident' in user_agent),
        'supports_postmessage': True,  # All modern browsers support this
        'supports_touch': 'touch' in user_agent or 'mobile' in user_agent
    }
    
    return browser_info


def can_preview_scorm_content(user, topic):
    """
    Check if user can preview SCORM content (read-only mode).
    ALL authenticated users can preview SCORM content.
    """
    try:
        # Allow all authenticated users to preview SCORM content
        if user and user.is_authenticated:
            return True
        
        # For unauthenticated users, return False (they can't preview)
        if not user or not user.is_authenticated:
            return False
        
        # Check if user has permission to view e-learning packages
        return user.has_perm('scorm.view_elearning_package')
        
    except Exception:
        # Fallback to basic permission check
        return user and user.is_authenticated and user.has_perm('scorm.view_elearning_package')

def can_access_scorm_content(user, topic):
    """
    Check if user can access SCORM content (full access, progress saved)
    Only learners need enrollment - other roles can access without enrollment
    """
    if not user or not user.is_authenticated:
        return False
    
    # Check user role - only learners need enrollment
    user_role = getattr(user, 'role', 'learner')
    
    # CRITICAL FIX: Non-learner roles ALWAYS get full access (not preview mode)
    # This ensures instructors/admins see content properly
    if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        logger.info(f"SCORM Access: {user_role} {user.username} granted FULL access without enrollment")
        return True
    
    # For learners, check enrollment
    if hasattr(topic, 'course') and topic.course:
        course = topic.course
        
        # Check if user is enrolled
        if hasattr(course, 'enrollments') and course.enrollments.filter(user=user).exists():
            return True
        
        # Check if user is the course instructor
        if hasattr(course, 'instructor') and course.instructor == user:
            return True
    
    return False


def clear_scorm_preview_session(request):
    """FIXED: Clear SCORM preview session state to prevent conflicts"""
    if 'scorm_preview_mode' in request.session:
        del request.session['scorm_preview_mode']
    if 'scorm_preview_topic' in request.session:
        del request.session['scorm_preview_topic']
    request.session.save()
    logger.info(f"SCORM Session: Cleared preview state for user {request.user.username if request.user.is_authenticated else 'anonymous'}")


def scorm_launch(request, topic_id):
    """Launch SCORM packages with enhanced support.
    FIXED: Consolidated access control logic for consistent behavior.
    """
    user = request.user if request.user.is_authenticated else None
    logger.info(
        f"E-Learning Launch: User authenticated: {getattr(user, 'username', 'anonymous')}"
    )
    
    topic = get_object_or_404(Topic, id=topic_id)
    
    # FIXED: Single, consolidated access control logic
    if not user or not user.is_authenticated:
        logger.info(f"E-Learning Launch: Unauthenticated user redirected to login for topic {topic_id}")
        messages.error(request, "You must be logged in to access this content.")
        return redirect('login')
    
    user_role = getattr(user, 'role', 'learner')
    logger.info(f"E-Learning Launch: User {user.username} with role '{user_role}' accessing topic {topic_id}")
    
    # FIXED: Single access control decision point
    if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        # Instructors/Admins get view access WITHOUT tracking
        preview_mode = True
        can_track = False
        logger.info(f"E-Learning Launch: {user_role} {user.username} granted view access (no tracking) to topic {topic_id}")
    else:
        # Learners - must be enrolled
        if not can_access_scorm_content(user, topic):
            logger.warning(f"E-Learning Launch: Non-enrolled learner {user.username} denied access to topic {topic_id}")
            messages.error(request, "You must be enrolled in this course to access the content.")
            return redirect('courses:course_list')
        
        # Enrolled learners get full access with tracking
        preview_mode = False
        can_track = True
        logger.info(f"E-Learning Launch: Enrolled learner {user.username} granted full access with tracking to topic {topic_id}")
    
    # FIXED: Clear any stale preview session state for non-preview users
    if not preview_mode:
        clear_scorm_preview_session(request)
    
    if preview_mode:
        username = getattr(user, 'username', 'anonymous')
        logger.info(f"E-Learning Launch: User {username} accessing e-learning content in preview mode for topic {topic_id}")
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        logger.error(f"E-Learning Launch: Package not found for topic {topic_id}")
        messages.error(request, "E-learning package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if not elearning_package.is_extracted:
        # CRITICAL FIX: Auto-extract package if not extracted
        logger.info(f"E-Learning Launch: Auto-extracting package for topic {topic_id}")
        # Extract package with progress tracking
        try:
            if elearning_package.extract_package():
                messages.success(request, "E-learning package extracted successfully.")
            else:
                error_msg = elearning_package.extraction_error or "Unknown extraction error"
                messages.error(request, f"E-learning package extraction failed: {error_msg}")
                return redirect('courses:topic_view', topic_id=topic_id)
        except Exception as e:
            logger.error(f"SCORM extraction error: {str(e)}")
            messages.error(request, f"E-learning package extraction failed: {str(e)}")
            return redirect('courses:topic_view', topic_id=topic_id)
    
    # FIXED: Proper tracking object handling for both preview and real modes
    tracking = None
    if not preview_mode and user and can_track:
        # Create real tracking for enrolled learners
        with transaction.atomic():
            tracking, created = ELearningTracking.objects.select_for_update().get_or_create(
                user=user,
                elearning_package=elearning_package
            )
            
            # Increment attempt count on each launch
            tracking.attempt_count += 1
            
            # Update launch timestamps
            if not tracking.first_launch:
                tracking.first_launch = timezone.now()
            tracking.last_launch = timezone.now()
            tracking.save()
            logger.info(f"E-Learning Launch: Created/updated tracking for user {user.username}")
    else:
        # FIXED: Create proper preview tracking object that doesn't interfere with real data
        class PreviewTracking:
            def __init__(self, user, elearning_package):
                self.user = user
                self.elearning_package = elearning_package
                self.raw_data = {}
                self.completion_status = 'incomplete'
                self.success_status = 'unknown'
                self.score_raw = None
                self.score_min = None
                self.score_max = None
                self.score_scaled = None
                self.total_time = None
                self.session_time = None
                self.location = ''
                self.suspend_data = ''
                self.launch_data = ''
                self.entry = 'ab-initio'
                self.exit_value = ''
                self.attempt_count = 0
                self.first_launch = timezone.now()
                self.last_launch = timezone.now()
                self.progress_measure = None
                self.completion_threshold = None
                self.credit = 'credit'
                self.mode = 'normal'
                self.learner_preference_audio_level = None
                self.learner_preference_language = ''
                self.learner_preference_delivery_speed = None
                self.learner_preference_audio_captioning = None
                self.student_data_mastery_score = None
                self.student_data_max_time_allowed = None
                self.student_data_time_limit_action = ''
                self.objectives = {}
                self.interactions = {}
                self.comments_from_learner = []
                self.comments_from_lms = []
                self.registration_id = None
                self.completion_date = None
                self.created_at = timezone.now()
                self.updated_at = timezone.now()
            
            def save(self):
                # Preview tracking objects don't save to database
                pass
            
            def get_bookmark_data(self):
                return {
                    'lesson_location': '',
                    'suspend_data': '',
                    'entry': 'ab-initio',
                    'exit': '',
                    'launch_data': '',
                    'has_bookmark': False,
                    'has_suspend_data': False,
                    'can_resume': False,
                    'package_type': self.elearning_package.package_type,
                    'progress_indicators': ['Preview Mode: No tracking data']
                }
        
        tracking = PreviewTracking(user, elearning_package)
        logger.info(f"E-Learning Launch: Created preview tracking for user {user.username}")
    
    # Get the launch file URL
    launch_url = elearning_package.get_content_url()
    if not launch_url:
        messages.error(request, "SCORM package launch file not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    
    # Prepare data based on package type
    if elearning_package.package_type in ['SCORM_1_2', 'SCORM_2004']:
        # SCORM data
        scorm_data = {
            'student_name': (user.get_full_name() or user.username) if user else 'Guest',
            'student_id': str(user.id) if user else 'guest',
            'suspend_data': tracking.raw_data.get('cmi.core.suspend_data', ''),
            'total_time': str(tracking.total_time) if tracking.total_time else 'PT0S',
            'lesson_location': tracking.raw_data.get('cmi.core.lesson_location', ''),
            'lesson_status': tracking.completion_status or 'incomplete',
            'launch_data': tracking.raw_data.get('cmi.core.launch_data', ''),
            'score_raw': str(tracking.score_raw) if tracking.score_raw else '',
            'score_min': str(tracking.score_min) if tracking.score_min else '',
            'score_max': str(tracking.score_max) if tracking.score_max else '',
            'entry': tracking.raw_data.get('cmi.core.entry', 'ab-initio'),
            'exit': tracking.raw_data.get('cmi.core.exit', ''),
        }
    else:
        # Default data
        scorm_data = {
            'student_name': (user.get_full_name() or user.username) if user else 'Guest',
            'student_id': str(user.id) if user else 'guest',
        }
    
    # Convert to JSON for safe JavaScript usage
    import json
    scorm_data_json = json.dumps(scorm_data)
    
    # Enhanced browser detection for template selection
    browser_info = get_browser_info(request)
    is_mobile = browser_info['is_mobile']
    
    # Select appropriate template based on device and browser for other formats
    if is_mobile:
        template_name = 'scorm/mobile_launch.html'
    else:
        template_name = 'scorm/launch.html'
    
    context = {
        'topic': topic,
        'elearning_package': elearning_package,
        'launch_url': launch_url,
        'tracking': tracking,
        'user_id': user.id if user else None,
        'scorm_api_url': f"/scorm/api/{topic_id}/",
        'scorm_data': scorm_data,
        'scorm_data_json': scorm_data_json,
        'preview_mode': preview_mode,
        'package_type': elearning_package.package_type,
        'browser_info': browser_info,
        'is_mobile': is_mobile
    }
    
    return render(request, template_name, context)

def scorm_content(request, topic_id, file_path):
    """Serve SCORM content files with enhanced support.
    FIXED: Consistent access control logic matching scorm_launch.
    """
    # FIXED: Use same access control logic as scorm_launch
    user = request.user if request.user.is_authenticated else None
    
    if not user or not user.is_authenticated:
        logger.warning(f"SCORM Content: Unauthenticated user denied access to {file_path}")
        return HttpResponse("Authentication required", status=401)
    
    topic = get_object_or_404(Topic, id=topic_id)
    user_role = getattr(user, 'role', 'learner')
    username = getattr(user, 'username', 'anonymous')
    
    # FIXED: Same access control logic as scorm_launch
    if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        # Instructors/Admins can view content
        logger.info(f"SCORM Content: {user_role} {username} accessing {file_path} for topic {topic_id}")
    else:
        # Learners must be enrolled - same logic as scorm_launch
        if not can_access_scorm_content(user, topic):
            logger.warning(f"SCORM Content: Non-enrolled learner {username} denied access to {file_path}")
            return HttpResponse("Enrollment required", status=403)
        logger.info(f"SCORM Content: Enrolled learner {username} accessing {file_path} for topic {topic_id}")
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        logger.error(f"SCORM Content: Package not found for topic {topic_id}")
        return HttpResponse("E-learning package not found", status=404)
    
    if not elearning_package.is_extracted:
        return HttpResponse("E-learning package not extracted", status=404)
    
    # FIXED: Proper S3 path construction for all package types
    base_path = elearning_package.extracted_path
    
    # Clean up any double prefixing
    if base_path.startswith('elearning/elearning/'):
        base_path = base_path.replace('elearning/elearning/', 'elearning/')
    if base_path.startswith('elearning/packages/'):
        base_path = base_path.replace('elearning/', '')  # Remove elearning prefix as storage adds it
    if base_path.startswith('packages/packages/'):
        base_path = base_path.replace('packages/packages/', 'packages/')
    
    # Ensure consistent path format
    if not base_path.startswith('packages/'):
        base_path = f"packages/{topic_id}"
    
    # Build the file path
    s3_file_path = os.path.join(base_path, file_path).replace('\\', '/')
    
    # Debug S3 path construction
    logger.info(f"SCORM Content: Topic {topic_id}, Extracted Path: {elearning_package.extracted_path}")
    logger.info(f"SCORM Content: File Path: {file_path}")
    logger.info(f"SCORM Content: S3 File Path: {s3_file_path}")
    
    # FIXED: Enhanced error handling for S3 storage with fallback paths
    try:
        from .storage import SCORMS3Storage
        scorm_storage = SCORMS3Storage()
        
        # Try multiple path variations to find the file
        alternative_paths = [
            s3_file_path,
            f"packages/{topic_id}/{file_path}",
            f"elearning/packages/{topic_id}/{file_path}",
            os.path.join(elearning_package.extracted_path, file_path).replace('\\', '/'),
            file_path,
            f"elearning/{file_path}",
            # Additional paths for nested content
            f"{base_path}/scormcontent/{file_path}",
            f"{base_path}/scormdriver/{file_path}",
            f"{base_path}/html5/{file_path}",
            f"{base_path}/story_content/{file_path}",
            f"{base_path}/mobile/{file_path}",
            f"{base_path}/data/{file_path}"
        ]

        # Locale fallback: if path references locales/i18n, try en-US and en variants
        try:
            import re as _re
            locale_fallbacks = []
            if '/locales/' in s3_file_path or '/i18n/' in s3_file_path:
                for loc in ['en-US', 'en']:
                    # Replace segment immediately after /locales/ or /i18n/
                    alt1 = _re.sub(r"(/locales/)([^/]+)(/)", r"\\1" + loc + r"\\3", s3_file_path)
                    alt2 = _re.sub(r"(/i18n/)([^/]+)(/)", r"\\1" + loc + r"\\3", s3_file_path)
                    for alt in [alt1, alt2]:
                        if alt and alt != s3_file_path and alt not in alternative_paths:
                            locale_fallbacks.append(alt)
            # Append locale fallbacks with and without base prefixes
            for p in list(locale_fallbacks):
                for prefix in ["", f"packages/{topic_id}/", "elearning/", f"elearning/packages/{topic_id}/"]:
                    combined = f"{prefix}{p}" if prefix and not p.startswith(prefix) else p
                    if combined not in alternative_paths:
                        alternative_paths.append(combined)
        except Exception as _e:
            # Safe to ignore locale fallback computation errors
            pass
        
        file_content = None
        used_path = None
        
        for path in alternative_paths:
            try:
                if scorm_storage.exists(path):
                    file_content = scorm_storage.open(path, 'rb').read()
                    used_path = path
                    logger.info(f"SCORM Content: Found file at path: {path}")
                    break
            except Exception as e:
                logger.warning(f"SCORM Content: Error checking path {path}: {e}", exc_info=True)
                continue
        
        if file_content is None:
            # Try to get the file URL and redirect to it as last resort
            for path in alternative_paths:
                try:
                    if scorm_storage.exists(path):
                        file_url = scorm_storage.url(path)
                        logger.info(f"SCORM Content: Redirecting to S3 URL: {file_url}")
                        return HttpResponseRedirect(file_url)
                except Exception as url_error:
                    logger.warning(f"SCORM Content: Error generating S3 URL for {path}: {url_error}")
                    continue
            
            logger.error(f"SCORM Content: File not found in any path. Tried: {alternative_paths}")
            return HttpResponse(f"File not found: {file_path}", status=404)
        
        # Determine content type based on file extension
        import mimetypes
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            if file_path.endswith('.html'):
                content_type = 'text/html; charset=utf-8'
            elif file_path.endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
            elif file_path.endswith('.css'):
                content_type = 'text/css; charset=utf-8'
            elif file_path.endswith('.json'):
                content_type = 'application/json; charset=utf-8'
            elif file_path.endswith('.xml'):
                content_type = 'application/xml; charset=utf-8'
            else:
                content_type = 'application/octet-stream'
        
        # CRITICAL FIX: Add CORS headers for all e-learning content
        response = HttpResponse(file_content, content_type=content_type)
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-Requested-With, X-CSRFToken, X-SCORM-User-ID, Authorization'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        
        # CRITICAL FIX: Add permissive CSP for SCORM content (required for eval and data URIs)
        if file_path.endswith('.html'):
            response['Content-Security-Policy'] = (
                "default-src 'self' data: blob: * 'unsafe-inline' 'unsafe-eval'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: *; "
                "style-src 'self' 'unsafe-inline' data: blob: *; "
                "img-src 'self' data: blob: *; "
                "font-src 'self' data: blob: * *.amazonaws.com fonts.gstatic.com fonts.googleapis.com; "
                "connect-src 'self' data: blob: *; "
                "frame-src 'self' data: blob: *; "
                "worker-src 'self' data: blob:; "
                "object-src 'self' data: blob:;"
            )
        # Also add CSP for CSS files that might reference fonts
        elif file_path.endswith('.css'):
            response['Content-Security-Policy'] = (
                "default-src 'self' data: blob: *; "
                "font-src 'self' data: blob: * *.amazonaws.com fonts.gstatic.com fonts.googleapis.com; "
                "style-src 'self' 'unsafe-inline' data: blob: *;"
            )
        
        # ENHANCED: Add specific headers for different package types
        if elearning_package.package_type in ['SCORM_1_2', 'SCORM_2004']:
            response['X-SCORM-Version'] = '1.2' if elearning_package.package_type == 'SCORM_1_2' else '2004'
        
        return response
    except Exception as e:
        logger.error(f"SCORM Content: Error serving file {file_path} (S3 path: {s3_file_path}): {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to serve SCORM content',
            'message': 'Unable to load the learning content. Please try again or contact support.',
            'details': str(e),
            'error_type': 'SCORM_CONTENT_ERROR'
        }, status=500)

@csrf_exempt
def scorm_api(request, topic_id):
    """SCORM API endpoint with enhanced support for e-learning standards"""
    if request.method == 'OPTIONS':
        # Handle preflight requests
        response = HttpResponse()
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-Requested-With, X-CSRFToken, X-SCORM-User-ID, Authorization'
        return response
    
    # ENFORCE ACCESS CONTROL for API
    user = None
    if request.user.is_authenticated:
        user = request.user
    elif request.session.get('_auth_user_id'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.session.get('_auth_user_id'))
            request.user = user
        except User.DoesNotExist:
            pass
    
    # Deny API access to unauthenticated users
    if not user or not user.is_authenticated:
        logger.warning(f"E-Learning API: Unauthenticated user denied API access for topic {topic_id}")
        return JsonResponse({'result': 'false', 'error': 'Authentication required'}, status=401)
    
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        return JsonResponse({'result': 'false', 'error': 'E-learning package not found'}, status=404)
    
    # Check user role to determine if tracking should be saved
    user_role = getattr(user, 'role', 'learner')
    
    # Only create/save tracking for enrolled learners, not instructors/admins
    if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        # Instructors/Admins - no tracking, just return success
        logger.info(f"E-Learning API: {user_role} {user.username} API call (no tracking) for topic {topic_id}")
        # Return dummy success response without saving
        return JsonResponse({'result': 'true', 'message': 'No tracking for instructor/admin role'})
    
    # For learners, check enrollment
    if not can_access_scorm_content(user, topic):
        logger.warning(f"E-Learning API: Non-enrolled learner {user.username} denied API access for topic {topic_id}")
        return JsonResponse({'result': 'false', 'error': 'Enrollment required'}, status=403)
    
    # Get or create tracking record for enrolled learners only
    tracking, created = ELearningTracking.objects.get_or_create(
        user=user,
        elearning_package=elearning_package
    )
    
    if request.method == 'GET':
        # Handle GET requests (LMSGetValue)
        element = request.GET.get('element', '')
        if element:
            value = tracking.raw_data.get(element, '')
            return JsonResponse({'result': 'true', 'value': value})
        else:
            return JsonResponse({'result': 'false', 'error': 'No element specified'})
    
    elif request.method == 'POST':
        # Handle POST requests based on package type
        action = request.POST.get('action', '')
        element = request.POST.get('element', '')
        value = request.POST.get('value', '')
        
        if elearning_package.package_type in ['SCORM_1_2', 'SCORM_2004']:
            # FIXED: Complete SCORM API handling with all data model elements
            if action == 'SetValue' and element:
                # Update tracking data
                tracking.raw_data[element] = value
                
                # Comprehensive SCORM 1.2 element handling
                if element == 'cmi.core.lesson_status':
                    tracking.completion_status = value
                elif element == 'cmi.core.score.raw':
                    try:
                        tracking.score_raw = float(value) if value else None
                    except (ValueError, TypeError):
                        pass
                elif element == 'cmi.core.score.min':
                    try:
                        tracking.score_min = float(value) if value else None
                    except (ValueError, TypeError):
                        pass
                elif element == 'cmi.core.score.max':
                    try:
                        tracking.score_max = float(value) if value else None
                    except (ValueError, TypeError):
                        pass
                elif element == 'cmi.core.total_time':
                    tracking.total_time = tracking._parse_scorm_time(value)
                elif element == 'cmi.core.session_time':
                    tracking.session_time = tracking._parse_scorm_time(value)
                elif element == 'cmi.core.lesson_location':
                    tracking.location = value
                elif element == 'cmi.core.suspend_data':
                    tracking.suspend_data = value
                elif element == 'cmi.core.launch_data':
                    tracking.launch_data = value
                elif element == 'cmi.core.entry':
                    tracking.entry = value
                elif element == 'cmi.core.exit':
                    tracking.exit_value = value
                
                # SCORM 2004 element handling
                elif element == 'cmi.completion_status':
                    tracking.completion_status = value
                elif element == 'cmi.success_status':
                    tracking.success_status = value
                elif element == 'cmi.score.scaled':
                    try:
                        tracking.score_scaled = float(value) if value else None
                    except (ValueError, TypeError):
                        pass
                elif element == 'cmi.progress_measure':
                    try:
                        tracking.progress_measure = float(value) if value else None
                    except (ValueError, TypeError):
                        pass
                elif element == 'cmi.credit':
                    tracking.credit = value
                elif element == 'cmi.mode':
                    tracking.mode = value
                elif element == 'cmi.completion_threshold':
                    try:
                        tracking.completion_threshold = float(value) if value else None
                    except (ValueError, TypeError):
                        pass
                
                # Navigation elements
                elif element == 'adl.nav.request':
                    tracking.raw_data['adl.nav.request'] = value
                elif element == 'adl.nav.request_valid':
                    tracking.raw_data['adl.nav.request_valid'] = value
                
                # Exit assessment elements
                elif element == 'cmi.core.exit_assessment_required':
                    tracking.raw_data['cmi.core.exit_assessment_required'] = value
                elif element == 'cmi.core.exit_assessment_completed':
                    tracking.raw_data['cmi.core.exit_assessment_completed'] = value
                
                
                tracking.save()
                logger.info(f"SCORM API: Set {element} = {value} for user {user.id}")
                return JsonResponse({'result': 'true'})
            
            elif action == 'GetValue' and element:
                # Get value from tracking data
                value = tracking.raw_data.get(element, '')
                return JsonResponse({'result': 'true', 'value': value})
            
            elif action == 'Commit':
                tracking.save()
                logger.info(f"SCORM API: Commit called for user {user.id}")
                return JsonResponse({'result': 'true'})
            
            elif action == 'Terminate':
                tracking.raw_data['cmi.core.exit'] = value
                tracking.save()
                logger.info(f"SCORM API: Terminate called for user {user.id}")
                return JsonResponse({'result': 'true'})
            
            elif action == 'Initialize':
                # Initialize SCORM session
                tracking.raw_data['cmi.core.entry'] = 'ab-initio'
                tracking.save()
                logger.info(f"SCORM API: Initialize called for user {user.id}")
                return JsonResponse({'result': 'true'})
            
            elif action == 'Finish':
                # Finish SCORM session
                tracking.raw_data['cmi.core.exit'] = 'normal'
                tracking.save()
                logger.info(f"SCORM API: Finish called for user {user.id}")
                return JsonResponse({'result': 'true'})
        
        
        
        else:
            return JsonResponse({'result': 'false', 'error': 'Invalid action'})
    
    return JsonResponse({'result': 'false', 'error': 'Invalid request method'})


@csrf_exempt
@require_http_methods(["POST"])
def scorm_log(request):
    """Log SCORM events for debugging"""
    try:
        data = json.loads(request.body)
        logger.info(f"SCORM Log: {data}")
        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"SCORM Log Error: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)})

@login_required
def scorm_result(request, topic_id):
    """Enhanced result view with comprehensive data handling and debugging"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        tracking = ELearningTracking.objects.get(user=user, elearning_package=elearning_package)
    except (ELearningPackage.DoesNotExist, ELearningTracking.DoesNotExist):
        messages.error(request, "No tracking data found for this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    context = {
        'topic': topic,
        'tracking': tracking,
        'elearning_package': elearning_package,
        'user': user,
    }
    
    return render(request, 'scorm/result.html', context)

@login_required
def scorm_retake(request, topic_id):
    """Reset SCORM tracking data for retake"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        tracking = ELearningTracking.objects.get(user=user, elearning_package=elearning_package)
        
        # Reset tracking data
        tracking.raw_data = {}
        tracking.completion_status = 'not attempted'
        tracking.success_status = 'unknown'
        tracking.score_raw = None
        tracking.score_min = None
        tracking.score_max = None
        tracking.total_time = None
        tracking.attempt_count = 0
        tracking.save()
        
        messages.success(request, "Content reset successfully. You can now retake this content.")
        
    except (ELearningPackage.DoesNotExist, ELearningTracking.DoesNotExist):
        messages.error(request, "No tracking data found for this content.")
    
    return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def scorm_resume(request, topic_id):
    """ENHANCED: Resume SCORM content from bookmark location with package type detection"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        tracking = ELearningTracking.objects.get(user=user, elearning_package=elearning_package)
        
        # Get bookmark data based on package type
        bookmark_data = tracking.get_bookmark_data()
        
        if bookmark_data['can_resume']:
            # Set resume mode based on package type
            if elearning_package.package_type in ['SCORM_1_2', 'SCORM_2004']:
                tracking.raw_data['cmi.core.entry'] = 'resume'
                logger.info(f"SCORM Resume: Setting resume mode for user {user.username} on topic {topic_id}")
            
            tracking.save()
            
            # Show appropriate resume message
            if bookmark_data['lesson_location']:
                messages.info(request, f"Resuming from: {bookmark_data['lesson_location']}")
            else:
                messages.info(request, "Resuming from your last position")
        else:
            messages.info(request, "Starting from the beginning")
        
    except (ELearningPackage.DoesNotExist, ELearningTracking.DoesNotExist):
        messages.error(request, "No tracking data found for this content.")
    
    return redirect('scorm:launch', topic_id=topic_id)




# Preview functions for instructors/admins
@login_required
def scorm_preview(request, topic_id):
    """ENHANCED: Preview SCORM content for instructors (bypasses tracking).
    FIXED: Proper session state management.
    """
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has preview permissions
    user_role = getattr(user, 'role', 'learner')
    if not (user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']):
        messages.error(request, "You don't have permission to preview this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        
        # FIXED: Use centralized session cleanup function
        clear_scorm_preview_session(request)
        
        # FIXED: Set new preview state with proper cleanup
        request.session['scorm_preview_mode'] = True
        request.session['scorm_preview_topic'] = topic_id
        request.session.save()
        
        logger.info(f"SCORM Preview: Set preview mode for user {user.username} on topic {topic_id}")
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "No e-learning package found for this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    return redirect('scorm:launch', topic_id=topic_id)


@login_required

# Additional SCORM functions
@login_required
def scorm_progress(request, topic_id):
    """Get SCORM progress data"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        tracking = ELearningTracking.objects.get(user=user, elearning_package=elearning_package)
        
        progress_data = {
            'completion_status': tracking.completion_status,
            'success_status': tracking.success_status,
            'score_raw': tracking.score_raw,
            'score_min': tracking.score_min,
            'score_max': tracking.score_max,
            'total_time': str(tracking.total_time) if tracking.total_time else None,
            'attempt_count': tracking.attempt_count,
            'last_launch': tracking.last_launch.isoformat() if tracking.last_launch else None,
        }
        
        return JsonResponse(progress_data)
        
    except (ELearningPackage.DoesNotExist, ELearningTracking.DoesNotExist):
        return JsonResponse({'error': 'No tracking data found'}, status=404)

@login_required
def scorm_debug(request, topic_id):
    """Debug SCORM data"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        tracking = ELearningTracking.objects.get(user=user, elearning_package=elearning_package)
        
        debug_data = {
            'package_type': elearning_package.package_type,
            'is_extracted': elearning_package.is_extracted,
            'launch_file': elearning_package.launch_file,
            'raw_data': tracking.raw_data,
            'completion_status': tracking.completion_status,
            'success_status': tracking.success_status,
            'score_raw': tracking.score_raw,
            'total_time': str(tracking.total_time) if tracking.total_time else None,
        }
        
        return JsonResponse(debug_data)
        
    except (ELearningPackage.DoesNotExist, ELearningTracking.DoesNotExist):
        return JsonResponse({'error': 'No tracking data found'}, status=404)

def validate_elearning_package_endpoint(request, topic_id):
    """Validate e-learning package"""
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        validation_result = {
            'valid': elearning_package.is_extracted,
            'package_type': elearning_package.package_type,
            'launch_file': elearning_package.launch_file,
        }
        return JsonResponse(validation_result)
    except ELearningPackage.DoesNotExist:
        return JsonResponse({'valid': False, 'error': 'Package not found'}, status=404)

@login_required
def scorm_reports(request, course_id):
    """SCORM reports for course"""
    course = get_object_or_404(Course, id=course_id)
    context = {'course': course}
    return render(request, 'scorm/reports.html', context)

@login_required
def scorm_learner_progress(request, course_id, user_id):
    """SCORM learner progress"""
    course = get_object_or_404(Course, id=course_id)
    user = get_object_or_404(CustomUser, id=user_id)
    context = {'course': course, 'learner': user}
    return render(request, 'scorm/learner_progress.html', context)

@login_required
def scorm_analytics_dashboard(request):
    """SCORM analytics dashboard"""
    return render(request, 'scorm/analytics_dashboard.html')

@login_required
def scorm_analytics_api(request):
    """SCORM analytics API"""
    # Basic analytics data
    analytics_data = {
        'total_packages': ELearningPackage.objects.count(),
        'total_tracking': ELearningTracking.objects.count(),
        'completed_tracking': ELearningTracking.objects.filter(completion_status='completed').count(),
    }
    return JsonResponse(analytics_data)
