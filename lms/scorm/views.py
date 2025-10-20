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
from lrs.scorm2004_sequencing import sequencing_processor
from lrs.models import SCORM2004Sequencing, SCORM2004ActivityState

logger = logging.getLogger(__name__)

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


def scorm_launch(request, topic_id):
    """Launch SCORM, xAPI, cmi5, or Articulate packages with enhanced support.
    Anonymous users are allowed to view in preview mode (no tracking).
    """
    user = request.user if request.user.is_authenticated else None
    logger.info(
        f"E-Learning Launch: User authenticated: {getattr(user, 'username', 'anonymous')}"
    )
    
    topic = get_object_or_404(Topic, id=topic_id)
    
    # ENHANCED: Better access control for different user roles
    # Non-learner roles (instructor, admin, superadmin, globaladmin) get full access
    # Learners need enrollment
    if user:
        user_role = getattr(user, 'role', 'learner')
        logger.info(f"E-Learning Launch: User {user.username} with role '{user_role}' accessing topic {topic_id}")
        
        # Non-learner roles get automatic access
        if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
            logger.info(f"E-Learning Launch: {user_role} {user.username} granted automatic access to topic {topic_id}")
        else:
            # For learners, check enrollment
            try:
                course = topic.course
                if course and not course.user_has_access(user):
                    logger.warning(f"E-Learning Launch: Learner {user.username} not enrolled in course for topic {topic_id}")
                    messages.error(request, "You need to be enrolled in this course to access the content.")
                    return redirect('courses:course_list')
            except AttributeError:
                logger.info(f"E-Learning Launch: Topic {topic_id} has no course relationship, allowing access")
                pass
    
    # CORRECT ACCESS CONTROL:
    # 1. Unauthenticated users: NO ACCESS
    # 2. Non-enrolled learners: NO ACCESS  
    # 3. Instructors/Admins: Full view access WITHOUT tracking
    # 4. Enrolled learners: Full access WITH tracking
    
    if not user or not user.is_authenticated:
        # Unauthenticated users - NO ACCESS
        logger.warning(f"E-Learning Launch: Unauthenticated user denied access to topic {topic_id}")
        messages.error(request, "You must be logged in to access this content.")
        return redirect('users:login')  # Redirect to login page
    
    user_role = getattr(user, 'role', 'learner')
    
    if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        # Instructors/Admins get view access WITHOUT tracking
        preview_mode = True  # View without tracking
        can_access = False   # No tracking/saving progress
        can_preview = True   # Can view content
        logger.info(f"E-Learning Launch: {user_role} {user.username} granted view access (no tracking) to topic {topic_id}")
    else:
        # Learners - must be enrolled
        can_access = can_access_scorm_content(user, topic)
        
        if not can_access:
            # Non-enrolled learners - NO ACCESS
            logger.warning(f"E-Learning Launch: Non-enrolled learner {user.username} denied access to topic {topic_id}")
            messages.error(request, "You must be enrolled in this course to access the content.")
            return redirect('courses:course_list')
        
        # Enrolled learners get full access with tracking
        preview_mode = False
        can_preview = True
        logger.info(f"E-Learning Launch: Enrolled learner {user.username} granted full access with tracking to topic {topic_id}")
    if preview_mode:
        username = getattr(user, 'username', 'anonymous')
        logger.info(f"E-Learning Launch: User {username} accessing e-learning content in preview mode for topic {topic_id}")
        # Different message for instructors/admins vs preview mode
        if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
            messages.info(request, "Instructor/Admin View: Progress tracking is disabled for this role.")
        else:
            messages.info(request, "You are viewing this content in preview mode. Your progress will not be saved.")
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        messages.error(request, "E-learning package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if not elearning_package.is_extracted:
        # CRITICAL FIX: Auto-extract package if not extracted
        logger.info(f"E-Learning Launch: Auto-extracting package for topic {topic_id}")
        if elearning_package.extract_package():
            messages.success(request, "E-learning package extracted successfully.")
        else:
            messages.error(request, "E-learning package extraction failed.")
            return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get or create tracking record (only if not in preview mode and user is authenticated)
    tracking = None
    if not preview_mode and user:  # Only create tracking if user is authenticated
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
    else:
        # Create a dummy tracking object for preview mode
        tracking = ELearningTracking(
            user=user,
            elearning_package=elearning_package,
            completion_status='incomplete',
            success_status='unknown',
            attempt_count=1,
            first_launch=timezone.now(),
            last_launch=timezone.now()
        )
        # Don't save dummy tracking object
    
    # Get the launch file URL
    launch_url = elearning_package.get_content_url()
    if not launch_url:
        messages.error(request, "SCORM package launch file not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Append required CMI5 launch parameters to the AU launch URL
    if elearning_package.package_type == 'CMI5':
        # Import modules at the start
        import urllib.parse
        import json
        import hashlib
        import base64
        import uuid as uuid_lib
        
        try:
            logger.info(f"CMI5 detected for topic {topic_id}, original launch_url: {launch_url}")

            site_url = getattr(settings, 'SITE_URL', None) or getattr(settings, 'BASE_URL', '')

            # Build actor and registration for both authenticated and preview (guest) users
            if user:
                actor = {
                    'objectType': 'Agent',
                    'account': {
                        'homePage': site_url,
                        'name': str(user.id)
                    },
                    'name': user.get_full_name() or user.username
                }
                registration_id = f"{user.id}-{topic_id}-{elearning_package.id}"
            else:
                # Guest/preview actor based on anonymous session
                session_key = getattr(request, 'session', None) and request.session.session_key or 'guest'
                if not session_key and hasattr(request, 'session'):
                    # Ensure a session exists
                    request.session.save()
                    session_key = request.session.session_key or 'guest'
                actor = {
                    'objectType': 'Agent',
                    'account': {
                        'homePage': site_url,
                        'name': f"guest-{session_key}"
                    },
                    'name': 'Guest'
                }
                registration_id = f"guest-{session_key}-{topic_id}-{elearning_package.id}"

            # CRITICAL FIX: Create LMS.LaunchData state BEFORE launching CMI5 content
            # This is required by CMI5 specification
            activity_id = elearning_package.cmi5_au_id or f"{site_url}/activities/{topic_id}"
            
            # Generate auth token for CMI5 content
            auth_token = base64.b64encode(f"Basic:{uuid_lib.uuid4()}".encode()).decode()
            
            # Create LMS.LaunchData content as per CMI5 spec
            lms_launch_data = {
                "contextTemplate": {
                    "contextActivities": {
                        "grouping": [
                            {
                                "objectType": "Activity",
                                "id": f"{site_url}/courses/{topic.course.id if hasattr(topic, 'course') and topic.course else 'unknown'}"
                            }
                        ]
                    },
                    "extensions": {
                        "https://w3id.org/xapi/cmi5/context/extensions/sessionid": str(uuid_lib.uuid4())
                    }
                },
                "launchMode": "Normal",
                "launchMethod": "AnyWindow",
                "moveOn": "Completed",
                "returnURL": f"{site_url}/scorm/result/{topic_id}/",
                "entitlementKey": {
                    "courseStructure": f"{site_url}/courses/{topic.course.id if hasattr(topic, 'course') and topic.course else 'unknown'}",
                    "alternate": ""
                }
            }
            
            # Store LMS.LaunchData in xAPI State API
            from lrs.models import State
            try:
                # CRITICAL FIX: Always generate a deterministic UUID from registration string
                # This ensures the CMI5 content can retrieve LMS.LaunchData using the same registration
                registration_uuid = None
                if registration_id:
                    try:
                        # Try to parse as UUID first
                        registration_uuid = uuid_lib.UUID(registration_id)
                        logger.info(f"CMI5: Using provided UUID registration: {registration_uuid}")
                    except (ValueError, AttributeError):
                        # Generate a deterministic UUID from the string using SHA-256 for better distribution
                        # This ensures consistency: same registration string = same UUID every time
                        import hashlib
                        hash_bytes = hashlib.sha256(str(registration_id).encode()).digest()[:16]
                        registration_uuid = uuid_lib.UUID(bytes=hash_bytes)
                        logger.info(f"CMI5: Generated deterministic UUID {registration_uuid} from registration '{registration_id}'")
                else:
                    # If no registration provided, generate a new UUID
                    registration_uuid = uuid_lib.uuid4()
                    logger.info(f"CMI5: Generated new UUID registration: {registration_uuid}")
                
                # Ensure site_url ends with trailing slash for consistency
                normalized_site_url = site_url.rstrip('/') + '/' if site_url else 'https://staging.nexsy.io/'
                
                # Update actor with normalized URL
                if 'account' in actor and 'homePage' in actor['account']:
                    actor['account']['homePage'] = normalized_site_url
                
                state_etag = hashlib.md5(json.dumps(lms_launch_data, sort_keys=True).encode()).hexdigest()
                
                # Create or update the LMS.LaunchData state
                state, created = State.objects.update_or_create(
                    activity_id=activity_id,
                    agent=actor,
                    state_id="LMS.LaunchData",
                    registration=registration_uuid,
                    defaults={
                        'content': lms_launch_data,
                        'content_type': 'application/json',
                        'etag': state_etag
                    }
                )
                action = "Created" if created else "Updated"
                logger.info(f"CMI5: {action} LMS.LaunchData state for activity {activity_id}, agent {json.dumps(actor)}, registration {registration_uuid}")
            except Exception as state_error:
                logger.error(f"CMI5: Failed to create LMS.LaunchData state: {state_error}", exc_info=True)
                # Continue anyway - some CMI5 content might work without it

            # Compact JSON to avoid spaces that could be turned into '+' by form-style encoders
            compact_actor_json = json.dumps(actor, separators=(',', ':'), ensure_ascii=False)
            cmi5_params = {
                'endpoint': f"{site_url}/lrs/xapi/statements/",
                'fetch': f"{site_url}/lrs/cmi5/fetch/",
                'actor': compact_actor_json,
                'registration': registration_id,
                'activityId': activity_id
            }
            separator = '&' if '?' in launch_url else '?'
            # Use quote_via=quote to encode spaces as %20 (not '+'), preserving JSON correctness
            launch_url = f"{launch_url}{separator}{urllib.parse.urlencode(cmi5_params, quote_via=urllib.parse.quote)}"
            logger.info(f"CMI5 Launch URL with parameters for topic {topic_id}: {launch_url}")
            logger.info(f"CMI5 params: {cmi5_params}")
        except Exception as e:
            logger.error(f"CMI5 parameter injection failed for topic {topic_id}: {e}", exc_info=True)
    
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
    elif elearning_package.package_type == 'XAPI':
        # xAPI data
        scorm_data = {
            'actor': {
                'mbox': f"mailto:{user.email}" if user else '',
                'name': (user.get_full_name() or user.username) if user else 'Guest'
            },
            'endpoint': elearning_package.xapi_endpoint or '',
            'actor_data': elearning_package.xapi_actor or {}
        }
    elif elearning_package.package_type == 'CMI5':
        # cmi5 data
        scorm_data = {
            'au_id': elearning_package.cmi5_au_id or '',
            'launch_url': elearning_package.cmi5_launch_url or '',
            'learner_id': str(user.id) if user else 'guest',
            'learner_name': (user.get_full_name() or user.username) if user else 'Guest'
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
    
    # CRITICAL FIX: CMI5 packages must always use desktop mode for proper launch
    # CMI5 requires specific xAPI communication that doesn't work in mobile mode
    if elearning_package.package_type == 'CMI5':
        template_name = 'scorm/launch.html'
        is_mobile = False  # Force desktop mode for CMI5
        logger.info(f"CMI5 Launch: Forcing desktop mode for topic {topic_id}")
    # Select appropriate template based on device and browser for other formats
    elif is_mobile:
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
    """Serve SCORM, xAPI, cmi5, and Articulate content files with enhanced support"""
    # ENFORCE ACCESS CONTROL for content files
    user = None
    if request.user.is_authenticated:
        user = request.user
    
    # Try to get user from session if not authenticated
    if not user and request.session.get('_auth_user_id'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.session.get('_auth_user_id'))
            request.user = user
        except (User.DoesNotExist, ValueError, TypeError):
            pass
    
    # Deny access to unauthenticated users
    if not user or not user.is_authenticated:
        logger.warning(f"SCORM Content: Unauthenticated user denied access to {file_path}")
        return HttpResponse("Authentication required", status=401)
    
    # Log access attempt
    username = getattr(user, 'username', 'anonymous')
    user_role = getattr(user, 'role', 'learner')
    
    # Get the topic and check access based on role
    topic = get_object_or_404(Topic, id=topic_id)
    
    if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
        # Instructors/Admins can view content
        logger.info(f"SCORM Content: {user_role} {username} accessing {file_path} for topic {topic_id}")
    else:
        # Learners must be enrolled
        if not can_access_scorm_content(user, topic):
            logger.warning(f"SCORM Content: Non-enrolled learner {username} denied access to {file_path}")
            return HttpResponse("Enrollment required", status=403)
        logger.info(f"SCORM Content: Enrolled learner {username} accessing {file_path} for topic {topic_id}")
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
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
        
        # CRITICAL FIX: Add permissive CSP for CMI5/SCORM content (required for eval and data URIs)
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
        elif elearning_package.package_type == 'XAPI':
            response['X-xAPI-Version'] = '1.0.3'
        elif elearning_package.package_type == 'CMI5':
            response['X-cmi5-Version'] = '1.0'
        
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
    """SCORM, xAPI, cmi5 API endpoint with enhanced support for all e-learning standards"""
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
        # Handle GET requests (LMSGetValue, xAPI Get, cmi5 Get)
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
                
                # cmi5 elements
                elif element == 'cmi5.exit':
                    tracking.raw_data['cmi5.exit'] = value
                elif element == 'cmi5.completion_status':
                    tracking.raw_data['cmi5.completion_status'] = value
                elif element == 'cmi5.exit_assessment_completed':
                    tracking.raw_data['cmi5.exit_assessment_completed'] = value
                
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
        
        elif elearning_package.package_type == 'XAPI':
            # xAPI handling
            if action == 'SendStatement':
                # Handle xAPI statement
                statement_data = request.POST.get('statement', '{}')
                try:
                    import json
                    statement = json.loads(statement_data)
                    tracking.raw_data['xapi_statement'] = statement
                    tracking.save()
                    return JsonResponse({'result': 'true'})
                except json.JSONDecodeError:
                    return JsonResponse({'result': 'false', 'error': 'Invalid JSON'})
        
        elif elearning_package.package_type == 'CMI5':
            # cmi5 handling
            if action == 'SetValue' and element:
                tracking.raw_data[element] = value
                tracking.save()
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
            elif elearning_package.package_type == 'XAPI':
                tracking.raw_data['xapi.resume'] = True
                logger.info(f"xAPI Resume: Setting resume mode for user {user.username} on topic {topic_id}")
            elif elearning_package.package_type == 'CMI5':
                tracking.raw_data['cmi5.resume'] = True
                logger.info(f"cmi5 Resume: Setting resume mode for user {user.username} on topic {topic_id}")
            
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

# xAPI Launch and Content
def xapi_launch(request, topic_id):
    """Launch xAPI content"""
    return scorm_launch(request, topic_id)

def xapi_resume(request, topic_id):
    """ENHANCED: Resume xAPI content with proper state handling"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        tracking = ELearningTracking.objects.get(user=user, elearning_package=elearning_package)
        
        # Get xAPI-specific bookmark data
        bookmark_data = tracking.get_bookmark_data()
        
        if bookmark_data['can_resume']:
            # Set xAPI resume mode
            tracking.raw_data['xapi.resume'] = True
            tracking.save()
            logger.info(f"xAPI Resume: Setting resume mode for user {user.username} on topic {topic_id}")
            
            # Show resume message
            if bookmark_data['lesson_location']:
                messages.info(request, f"Resuming xAPI content from: {bookmark_data['lesson_location']}")
            else:
                messages.info(request, "Resuming xAPI content from your last position")
        else:
            messages.info(request, "Starting xAPI content from the beginning")
        
    except (ELearningPackage.DoesNotExist, ELearningTracking.DoesNotExist):
        messages.error(request, "No xAPI tracking data found for this content.")
    
    return redirect('scorm:xapi_launch', topic_id=topic_id)

# cmi5 Launch and Content
def cmi5_launch(request, topic_id):
    """Launch cmi5 content with enhanced logging for external URLs"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        elearning_package = ELearningPackage.objects.get(topic=topic)
        if elearning_package.package_type == 'CMI5' and elearning_package.cmi5_launch_url:
            launch = elearning_package.cmi5_launch_url
            if isinstance(launch, str) and (launch.startswith('http://') or launch.startswith('https://')):
                logger.info(f"CMI5 Launch: External launch URL detected for topic {topic_id}: {launch}")
    except Exception as e:
        logger.warning(f"CMI5 Launch: Unable to pre-check external URL for topic {topic_id}: {e}")
    return scorm_launch(request, topic_id)

def cmi5_resume(request, topic_id):
    """ENHANCED: Resume cmi5 content with proper AU state handling"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        tracking = ELearningTracking.objects.get(user=user, elearning_package=elearning_package)
        
        # Get cmi5-specific bookmark data
        bookmark_data = tracking.get_bookmark_data()
        
        if bookmark_data['can_resume']:
            # Set cmi5 resume mode
            tracking.raw_data['cmi5.resume'] = True
            tracking.save()
            logger.info(f"cmi5 Resume: Setting resume mode for user {user.username} on topic {topic_id}")
            
            # Show resume message
            if bookmark_data['lesson_location']:
                messages.info(request, f"Resuming cmi5 content from: {bookmark_data['lesson_location']}")
            else:
                messages.info(request, "Resuming cmi5 content from your last position")
        else:
            messages.info(request, "Starting cmi5 content from the beginning")
        
    except (ELearningPackage.DoesNotExist, ELearningTracking.DoesNotExist):
        messages.error(request, "No cmi5 tracking data found for this content.")
    
    return redirect('scorm:cmi5_launch', topic_id=topic_id)

# Preview functions for instructors/admins
@login_required
def scorm_preview(request, topic_id):
    """ENHANCED: Preview SCORM content for instructors (bypasses tracking)"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has preview permissions
    user_role = getattr(user, 'role', 'learner')
    if not (user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']):
        messages.error(request, "You don't have permission to preview this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        
        # Set preview mode in session
        request.session['scorm_preview_mode'] = True
        request.session['scorm_preview_topic'] = topic_id
        request.session.save()  # Ensure session is saved
        
        logger.info(f"SCORM Preview: Set preview mode for user {user.username} on topic {topic_id}")
        messages.info(request, "You are now in preview mode. Your progress will not be saved.")
        # Note: Preview mode banner is displayed on the launch page
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "No e-learning package found for this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    return redirect('scorm:launch', topic_id=topic_id)

@login_required
def xapi_preview(request, topic_id):
    """ENHANCED: Preview xAPI content for instructors (bypasses tracking)"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has preview permissions
    user_role = getattr(user, 'role', 'learner')
    if not (user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']):
        messages.error(request, "You don't have permission to preview this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        
        # Set preview mode in session
        request.session['scorm_preview_mode'] = True
        request.session['scorm_preview_topic'] = topic_id
        request.session.save()  # Ensure session is saved
        
        logger.info(f"xAPI Preview: Set preview mode for user {user.username} on topic {topic_id}")
        messages.info(request, "You are now in preview mode. Your progress will not be saved.")
        # Note: Preview mode banner is displayed on the launch page
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "No e-learning package found for this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    return redirect('scorm:xapi_launch', topic_id=topic_id)

@login_required
def cmi5_preview(request, topic_id):
    """ENHANCED: Preview cmi5 content for instructors (bypasses tracking)"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has preview permissions
    user_role = getattr(user, 'role', 'learner')
    if not (user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']):
        messages.error(request, "You don't have permission to preview this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        
        # Set preview mode in session
        request.session['scorm_preview_mode'] = True
        request.session['scorm_preview_topic'] = topic_id
        request.session.save()  # Ensure session is saved
        
        logger.info(f"cmi5 Preview: Set preview mode for user {user.username} on topic {topic_id}")
        messages.info(request, "You are now in preview mode. Your progress will not be saved.")
        # Note: Preview mode banner is displayed on the launch page
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "No e-learning package found for this content.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    return redirect('scorm:cmi5_launch', topic_id=topic_id)

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
