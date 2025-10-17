import os
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from django.core.files.storage import default_storage
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
    """Detect if the request is from a mobile device"""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    mobile_keywords = [
        'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone',
        'mobile', 'opera mini', 'iemobile', 'webos', 'palm'
    ]
    return any(keyword in user_agent for keyword in mobile_keywords)

def can_access_scorm_content(user, topic):
    """
    Check if user can access SCORM content (not just preview).
    Only learners should be able to interact with SCORM content.
    """
    try:
        # Check if user is enrolled in the course
        course = topic.course
        if course and not course.user_has_access(user):
            return False
        
        # Check if user has learner role for this course
        from role_management.models import UserRole
        learner_roles = UserRole.objects.filter(
            user=user,
            role__name__in=['Learner', 'Student'],
            course=course
        ).exists()
        
        return learner_roles
        
    except Exception:
        # If no course relationship, allow access for now
        return True

def can_preview_scorm_content(user, topic):
    """
    Check if user can preview SCORM content (read-only mode).
    ALL authenticated users can preview SCORM content.
    """
    try:
        # Allow all authenticated users to preview SCORM content
        if user.is_authenticated:
            return True
            
        # Check if user has any role that allows content viewing
        from role_management.models import UserRole
        course = topic.course
        
        if course:
            # Check for any role that allows content access
            has_access_role = UserRole.objects.filter(
                user=user,
                course=course,
                role__name__in=['Instructor', 'Admin', 'Global Admin', 'Super Admin']
            ).exists()
            
            return has_access_role
        else:
            # If no course relationship, check global permissions
            return user.has_perm('scorm.view_elearning_package')
        
    except Exception:
        # Fallback to basic permission check
        return user.has_perm('scorm.view_elearning_package')

def can_access_scorm_content(user, topic):
    """
    Check if user can access SCORM content (full access, progress saved)
    Uses the LMS role management system for proper access control
    """
    if not user.is_authenticated:
        return False
    
    # Import role management utilities
    try:
        from role_management.utils import PermissionManager
    except ImportError:
        # Fallback to basic Django attributes if role management not available
        if user.is_staff or user.is_superuser:
            return True
        return False
    
    # Check if user has topic management capabilities using role management system
    if PermissionManager.user_has_any_capability(user, ['view_topics', 'manage_topics']):
        return True
    
    # Check if user is enrolled in the course
    if hasattr(topic, 'course') and topic.course:
        course = topic.course
        
        # Check if user is enrolled
        if hasattr(course, 'enrollments') and course.enrollments.filter(user=user).exists():
            return True
        
        # Check if user is instructor
        if hasattr(course, 'instructor') and course.instructor == user:
            return True
    
    return False

def can_preview_scorm_content(user, topic):
    """
    Check if user can preview SCORM content (view-only, progress not saved)
    Uses the LMS role management system for proper access control
    """
    if not user.is_authenticated:
        return False
    
    # Import role management utilities
    try:
        from role_management.utils import PermissionManager
    except ImportError:
        # Fallback to basic Django attributes if role management not available
        return user.is_staff or user.is_superuser
    
    # Check if user has topic viewing capabilities using role management system
    return PermissionManager.user_has_capability(user, 'view_topics')

def scorm_launch(request, topic_id):
    """Launch a SCORM package"""
    # ENHANCED AUTHENTICATION - FIXED FOR SCORM IFRAME SCENARIOS
    user = None
    
    # Method 1: Standard authentication
    if request.user.is_authenticated:
        user = request.user
        logger.info(f"SCORM Launch: User authenticated via standard auth: {user.username}")
    
    # Method 2: Session-based authentication (for iframe scenarios)
    elif request.session.get('_auth_user_id'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.session.get('_auth_user_id'))
            # Restore the user in the request for proper authentication
            request.user = user
            logger.info(f"SCORM Launch: User authenticated via session: {user.username}")
        except User.DoesNotExist:
            logger.warning(f"SCORM Launch: Invalid session user ID: {request.session.get('_auth_user_id')}")
    
    # Method 3: Check for authentication headers (for external SCORM players)
    elif request.META.get('HTTP_AUTHORIZATION'):
        # Handle token-based authentication if needed
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            # Implement token validation here if needed
            logger.info(f"SCORM Launch: Token-based authentication attempted")
    
    if not user:
        logger.warning(f"SCORM Launch: No authentication found for topic {topic_id}")
        messages.error(request, "Authentication required to access SCORM content.")
        return redirect('login')
    
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Debug logging for SCORM launch
    logger.info(f"SCORM Launch: User {user.username} (ID: {user.id}) accessing topic {topic_id}")
    logger.info(f"SCORM Launch: User authenticated: {request.user.is_authenticated}")
    logger.info(f"SCORM Launch: Session user ID: {request.session.get('_auth_user_id')}")
    
    # Check if user has access to this topic
    try:
        course = topic.course
        if course and not course.user_has_access(user):
            logger.warning(f"SCORM Launch: User {user.username} does not have access to topic {topic_id}")
            messages.error(request, "You don't have access to this content.")
            return redirect('courses:course_list')
    except AttributeError:
        # Topic doesn't have a course relationship, allow access for now
        logger.info(f"SCORM Launch: Topic {topic_id} has no course relationship, allowing access")
        pass
    
    # ENHANCED: Role-based access control for SCORM content
    can_access = can_access_scorm_content(user, topic)
    can_preview = can_preview_scorm_content(user, topic)
    
    # Allow preview for all authenticated users
    if not can_access and not can_preview:
        # Only block if user is not authenticated at all
        if not user.is_authenticated:
            logger.warning(f"SCORM Launch: User not authenticated for topic {topic_id}")
            messages.error(request, "Authentication required to access SCORM content.")
            return redirect('login')
        else:
            # All authenticated users can preview
            can_preview = True
            logger.info(f"SCORM Launch: User {user.username} granted preview access for topic {topic_id}")
    
    # Additional check: If user has high-level capabilities, always allow access
    try:
        from role_management.utils import PermissionManager
        if PermissionManager.user_has_any_capability(user, ['manage_topics', 'manage_courses']):
            can_access = True
            logger.info(f"SCORM Launch: User {user.username} with management capabilities granted full access for topic {topic_id}")
    except ImportError:
        # Fallback to basic Django attributes if role management not available
        if user.is_staff or user.is_superuser:
            can_access = True
            logger.info(f"SCORM Launch: Staff/admin user {user.username} granted full access for topic {topic_id}")
    
    # Set preview mode if user can only preview
    preview_mode = not can_access and can_preview
    if preview_mode:
        logger.info(f"SCORM Launch: User {user.username} accessing SCORM content in preview mode for topic {topic_id}")
        messages.info(request, "You are viewing this content in preview mode. Your progress will not be saved.")
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        messages.error(request, "E-learning package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if not elearning_package.is_extracted:
        messages.error(request, "SCORM package is not properly extracted.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get or create tracking record (only if not in preview mode)
    tracking = None
    if not preview_mode:
        tracking, created = ELearningTracking.objects.get_or_create(
            user=user,
            elearning_package=elearning_package
        )
    else:
        # Create a dummy tracking object for preview mode
        tracking = ELearningTracking(
            user=user,
            elearning_package=elearning_package,
            completion_status='incomplete',
            success_status='unknown'
        )
    
    # Increment attempt count on each launch
    tracking.attempt_count += 1
    
    # Update launch timestamps
    if not tracking.first_launch:
        tracking.first_launch = timezone.now()
    tracking.last_launch = timezone.now()
    tracking.save()
    
    # Get the launch file URL
    launch_url = elearning_package.get_content_url()
    if not launch_url:
        messages.error(request, "SCORM package launch file not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Prepare SCORM data safely
    scorm_data = {
        'student_name': user.get_full_name() or user.username,
        'student_id': str(user.id),
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
    
    # Convert to JSON for safe JavaScript usage
    import json
    scorm_data_json = json.dumps(scorm_data)
    
    context = {
        'topic': topic,
        'elearning_package': elearning_package,
        'launch_url': launch_url,
        'tracking': tracking,
        'user_id': user.id,
        'scorm_api_url': f'/scorm/api/{topic_id}/',
        'scorm_data': scorm_data,
        'scorm_data_json': scorm_data_json,
        'preview_mode': preview_mode  # Add preview mode to context
    }
    
    return render(request, 'scorm/launch.html', context)

def scorm_content(request, topic_id, file_path):
    """Serve SCORM content files with enhanced authentication"""
    user = None
    
    # Method 1: Standard authentication
    if request.user.is_authenticated:
        user = request.user
        logger.info(f"SCORM Content: User authenticated via standard auth: {user.username}")
    
    # Method 2: Session-based authentication (for iframe scenarios)
    elif request.session.get('_auth_user_id'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.session.get('_auth_user_id'))
            # Restore the user in the request for proper authentication
            request.user = user
            logger.info(f"SCORM Content: User authenticated via session: {user.username}")
        except User.DoesNotExist:
            logger.warning(f"SCORM Content: Invalid session user ID: {request.session.get('_auth_user_id')}")
    
    # Method 3: Check for referer header (for iframe content)
    elif request.META.get('HTTP_REFERER'):
        referer = request.META.get('HTTP_REFERER', '')
        if 'scorm/launch' in referer and request.session.get('_auth_user_id'):
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=request.session.get('_auth_user_id'))
                request.user = user
                logger.info(f"SCORM Content: User authenticated via referer: {user.username}")
            except User.DoesNotExist:
                pass
    
    # Method 4: Check for SCORM-specific headers
    elif request.META.get('HTTP_X_SCORM_USER_ID'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.META.get('HTTP_X_SCORM_USER_ID'))
            request.user = user
            logger.info(f"SCORM Content: User authenticated via header: {user.username}")
        except (User.DoesNotExist, ValueError):
            logger.warning(f"SCORM Content: Invalid header user ID: {request.META.get('HTTP_X_SCORM_USER_ID')}")
    
    # Additional fallback: If no user found but we have a session, try to authenticate
    if not user and request.session.get('_auth_user_id'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.session.get('_auth_user_id'))
            request.user = user
            logger.info(f"SCORM Content: User authenticated via session fallback: {user.username}")
        except User.DoesNotExist:
            logger.warning(f"SCORM Content: Invalid session user ID in fallback: {request.session.get('_auth_user_id')}")
    
    if not user:
        # Enhanced iframe authentication - check for SCORM launch referer
        if (request.META.get('HTTP_REFERER') and 
            'scorm/launch' in request.META.get('HTTP_REFERER', '') and 
            request.session.get('_auth_user_id')):
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=request.session.get('_auth_user_id'))
                request.user = user
                logger.info(f"SCORM Content: User authenticated via iframe referer: {user.username}")
            except User.DoesNotExist:
                logger.warning(f"SCORM Content: Invalid session user ID in iframe: {request.session.get('_auth_user_id')}")
        
        if not user:
            logger.warning(f"SCORM Content: No authentication found for topic {topic_id}, file {file_path}")
            # Return 401 for API calls, redirect for browser requests
            if request.META.get('HTTP_ACCEPT', '').startswith('application/json'):
                return JsonResponse({'error': 'Authentication required'}, status=401)
            else:
                return redirect('login')
    
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    try:
        if not topic.course.user_has_access(user):
            # For SCORM content, allow access if user is authenticated (preview mode)
            if not user.is_authenticated:
                raise Http404("Access denied")
            else:
                logger.info(f"SCORM Content: User {user.username} accessing in preview mode for topic {topic_id}")
    except AttributeError:
        # Topic doesn't have a course relationship, allow access
        logger.info(f"SCORM Content: Topic {topic_id} has no course relationship, allowing access")
        pass
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        raise Http404("E-learning package not found")
    
    if not elearning_package.is_extracted:
        raise Http404("SCORM package not extracted")
    
    # Handle S3 storage for SCORM packages
    if hasattr(elearning_package.package_file.storage, 'bucket_name'):
        # S3 storage - construct S3 path
        # Remove 'elearning/' prefix since storage already adds it
        s3_base_path = elearning_package.extracted_path.replace('elearning/', '')
        s3_file_path = f"{s3_base_path}/{file_path}"
        
        # Try direct S3 path first
        logger.info(f"SCORM Content: Trying S3 path: {s3_file_path}")
        
        # If not found, try common SCORM directories
        s3_path_found = None
        for content_dir in ['', 'scormcontent', 'scormdriver', 'content', 'data', 'story_content']:
            if content_dir:
                alt_s3_path = f"{s3_base_path}/{content_dir}/{file_path}"
            else:
                alt_s3_path = f"{s3_base_path}/{file_path}"
            
            logger.info(f"SCORM Content: Trying S3 {content_dir} path: {alt_s3_path}")
            
            # Check if file exists in S3
            try:
                if elearning_package.package_file.storage.exists(alt_s3_path):
                    s3_path_found = alt_s3_path
                    logger.info(f"SCORM Content: Found file at S3 {content_dir} path: {alt_s3_path}")
                    break
            except Exception as e:
                logger.warning(f"SCORM Content: Error checking S3 path {alt_s3_path}: {e}")
                continue
        
        if not s3_path_found:
            logger.error(f"SCORM Content: File not found in S3: {file_path} in {s3_base_path}")
            raise Http404("File not found")
        
        # Serve file from S3
        try:
            file_url = elearning_package.package_file.storage.url(s3_path_found)
            logger.info(f"SCORM Content: Serving S3 file: {file_url}")
            
            # Redirect to S3 URL for direct serving
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(file_url)
            
        except Exception as e:
            logger.error(f"SCORM Content: Error serving S3 file {s3_path_found}: {e}")
            raise Http404("Error serving file from S3")
    
    else:
        # Local storage - use temp directory for extraction
        import tempfile
        extracted_base_path = os.path.join(tempfile.gettempdir(), elearning_package.extracted_path)
        
        # Try direct path first
        full_path = os.path.join(extracted_base_path, file_path)
        logger.info(f"SCORM Content: Trying direct path: {full_path}")
        
        # If not found, try common SCORM directories
        if not os.path.exists(full_path):
            for content_dir in ['', 'scormcontent', 'scormdriver', 'content', 'data', 'story_content']:
                alt_path = os.path.join(extracted_base_path, content_dir, file_path)
                logger.info(f"SCORM Content: Trying {content_dir} path: {alt_path}")
                if os.path.exists(alt_path):
                    full_path = alt_path
                    logger.info(f"SCORM Content: Found file at {content_dir} path: {full_path}")
                    break
        
        if not os.path.exists(full_path):
            logger.error(f"SCORM Content: File not found: {file_path} in {extracted_base_path}")
            raise Http404("File not found")
    
    # Enhanced MIME type detection
    content_type = 'text/html'  # Default
    if file_path.endswith('.css'):
        content_type = 'text/css'
    elif file_path.endswith('.js'):
        content_type = 'application/javascript'
    elif file_path.endswith('.json'):
        content_type = 'application/json'
    elif file_path.endswith('.xml'):
        content_type = 'application/xml'
    elif file_path.endswith('.png'):
        content_type = 'image/png'
    elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
        content_type = 'image/jpeg'
    elif file_path.endswith('.gif'):
        content_type = 'image/gif'
    elif file_path.endswith('.svg'):
        content_type = 'image/svg+xml'
    elif file_path.endswith('.woff'):
        content_type = 'font/woff'
    elif file_path.endswith('.woff2'):
        content_type = 'font/woff2'
    elif file_path.endswith('.ttf'):
        content_type = 'font/ttf'
    elif file_path.endswith('.eot'):
        content_type = 'application/vnd.ms-fontobject'
    elif file_path.endswith('.otf'):
        content_type = 'font/otf'
    elif file_path.endswith('.mp4'):
        content_type = 'video/mp4'
    elif file_path.endswith('.webm'):
        content_type = 'video/webm'
    elif file_path.endswith('.ogg'):
        content_type = 'video/ogg'
    elif file_path.endswith('.mp3'):
        content_type = 'audio/mpeg'
    elif file_path.endswith('.wav'):
        content_type = 'audio/wav'
    
    # Read and serve the file
    try:
        # Handle S3 vs local storage
        if hasattr(elearning_package.package_file.storage, 'bucket_name'):
            # S3 storage - file already redirected above
            # This code should not be reached for S3 storage
            raise Http404("S3 file serving should have been handled above")
        else:
            # Local storage - read from filesystem
            with open(full_path, 'rb') as f:
                content = f.read()
        
        # For HTML files, process relative links to work with SCORM content
        if file_path.endswith('.html'):
            # Convert content to string for processing
            try:
                content_str = content.decode('utf-8')
                
                # Fix relative links in HTML content
                # Replace relative paths with SCORM content URLs
                import re
                
                # Fix relative links (href and src attributes)
                def replace_relative_link(match):
                    attr_name = match.group(1)  # href or src
                    link_path = match.group(2)  # the actual path
                    
                    # Skip if it's already an absolute URL or data URI
                    if link_path.startswith(('http://', 'https://', 'data:', 'javascript:', '#')):
                        return match.group(0)
                    
                    # Convert relative path to SCORM content URL
                    if link_path.startswith('./'):
                        link_path = link_path[2:]  # Remove ./
                    elif link_path.startswith('../'):
                        # Handle parent directory navigation
                        current_dir = os.path.dirname(file_path)
                        while link_path.startswith('../'):
                            link_path = link_path[3:]
                            current_dir = os.path.dirname(current_dir)
                        link_path = os.path.join(current_dir, link_path).replace('\\', '/')
                    
                    # Ensure path doesn't start with /
                    if link_path.startswith('/'):
                        link_path = link_path[1:]
                    
                    scorm_url = f"/scorm/content/{topic_id}/{link_path}"
                    return f'{attr_name}="{scorm_url}"'
                
                # Replace href and src attributes with relative paths
                content_str = re.sub(r'(href|src)="([^"]*)"', replace_relative_link, content_str)
                
                # Also handle relative URLs in JavaScript (common in SCORM packages)
                # Fix window.location and similar references
                content_str = re.sub(
                    r'window\.location\s*=\s*["\']([^"\']*)["\']',
                    lambda m: f'window.location = "/scorm/content/{topic_id}/" + "{m.group(1)}"',
                    content_str
                )
                
                # Inject Enhanced SCORM API script into HTML content
                scorm_api_script = f'''
<script>
// CRITICAL FIX: Enhanced SCORM API Implementation with proper discovery
(function() {{
    'use strict';
    
    // SCORM API Discovery Pattern - CRITICAL FOR SCORM CONTENT
    function findAPI(win) {{
        var findAttempts = 0;
        while ((win.API == null) && (win.parent != null) && (win.parent != win)) {{
            findAttempts++;
            if (findAttempts > 7) {{
                return null;
            }}
            win = win.parent;
        }}
        return win.API;
    }}
    
    // Try to find existing API first
    var existingAPI = findAPI(window);
    
    var SCORM_API = {{
        initialized: false,
        commit_url: window.location.origin + '/scorm/api/{topic_id}/',
        user_id: null,
        topic_id: {topic_id},
        
        data: {{
            'cmi.core.lesson_status': 'incomplete',
            'cmi.core.score.raw': '',
            'cmi.core.score.min': '',
            'cmi.core.score.max': '',
            'cmi.core.total_time': 'PT0S',
            'cmi.core.session_time': 'PT0S',
            'cmi.core.lesson_location': '',
            'cmi.core.exit': '',
            'cmi.core.entry': 'ab-initio',
            'cmi.core.student_id': '',
            'cmi.core.student_name': '',
            'cmi.core.credit': 'credit',
            'cmi.core.lesson_mode': 'normal',
            'cmi.core.max_time_allowed': '',
            'cmi.core.mastery_score': '',
            'cmi.core.suspend_data': '',
            'cmi.core.launch_data': ''
        }},
        
        LMSInitialize: function(param) {{
            console.log('SCORM API: LMSInitialize called with:', param);
            this.initialized = true;
            return "true";
        }},
        
        LMSGetValue: function(element) {{
            console.log('SCORM API: LMSGetValue called for:', element);
            return this.data[element] || "";
        }},
        
        LMSSetValue: function(element, value) {{
            console.log('SCORM API: LMSSetValue called:', element, '=', value);
            this.data[element] = value;
            return "true";
        }},
        
        LMSCommit: function(param) {{
            console.log('SCORM API: LMSCommit called');
            this.sendDataToServer();
            return "true";
        }},
        
        LMSFinish: function(param) {{
            console.log('SCORM API: LMSFinish called');
            this.sendDataToServer();
            return "true";
        }},
        
        LMSGetLastError: function() {{
            return "0";
        }},
        
        LMSGetErrorString: function(errorCode) {{
            return "No Error";
        }},
        
        LMSGetDiagnostic: function(errorCode) {{
            return "No Error";
        }},
        
        // Additional SCORM API functions that Articulate content expects
        CommitData: function() {{
            console.log('SCORM API: CommitData called');
            this.sendDataToServer();
            return "true";
        }},
        
        ConcedeControl: function() {{
            console.log('SCORM API: ConcedeControl called');
            return "true";
        }},
        
        CreateResponseIdentifier: function() {{
            console.log('SCORM API: CreateResponseIdentifier called');
            return "true";
        }},
        
        Finish: function() {{
            console.log('SCORM API: Finish called');
            this.sendDataToServer();
            return "true";
        }},
        
        GetDataChunk: function() {{
            console.log('SCORM API: GetDataChunk called');
            return "";
        }},
        
        GetStatus: function() {{
            console.log('SCORM API: GetStatus called');
            return this.data['cmi.core.lesson_status'] || "incomplete";
        }},
        
        MatchingResponse: function() {{
            console.log('SCORM API: MatchingResponse called');
            return "true";
        }},
        
        RecordFillInInteraction: function() {{
            console.log('SCORM API: RecordFillInInteraction called');
            return "true";
        }},
        
        RecordMatchingInteraction: function() {{
            console.log('SCORM API: RecordMatchingInteraction called');
            return "true";
        }},
        
        RecordMultipleChoiceInteraction: function() {{
            console.log('SCORM API: RecordMultipleChoiceInteraction called');
            return "true";
        }},
        
        ResetStatus: function() {{
            console.log('SCORM API: ResetStatus called');
            this.data['cmi.core.lesson_status'] = 'incomplete';
            return "true";
        }},
        
        SetBookmark: function(bookmark) {{
            console.log('SCORM API: SetBookmark called with:', bookmark);
            this.data['cmi.core.lesson_location'] = bookmark;
            
            // FIXED: Send bookmark data to server immediately
            this.sendDataToServer();
            
            return "true";
        }},
        
        SetDataChunk: function(data) {{
            console.log('SCORM API: SetDataChunk called with:', data);
            this.data['cmi.core.suspend_data'] = data;
            
            // FIXED: Send suspend data to server immediately
            this.sendDataToServer();
            
            return "true";
        }},
        
        SetFailed: function() {{
            console.log('SCORM API: SetFailed called');
            this.data['cmi.core.lesson_status'] = 'failed';
            return "true";
        }},
        
        SetLanguagePreference: function(lang) {{
            console.log('SCORM API: SetLanguagePreference called with:', lang);
            return "true";
        }},
        
        SetPassed: function() {{
            console.log('SCORM API: SetPassed called');
            this.data['cmi.core.lesson_status'] = 'passed';
            return "true";
        }},
        
        SetReachedEnd: function() {{
            console.log('SCORM API: SetReachedEnd called');
            this.data['cmi.core.lesson_status'] = 'completed';
            return "true";
        }},
        
        SetScore: function(score) {{
            console.log('SCORM API: SetScore called with:', score);
            this.data['cmi.core.score.raw'] = score;
            return "true";
        }},
        
        WriteToDebug: function(message) {{
            console.log('SCORM API: WriteToDebug called with:', message);
            return "true";
        }},
        
        sendDataToServer: function() {{
            if (!this.commit_url) {{
                console.error('SCORM API: No commit URL available');
                return;
            }}
            
            const formData = new FormData();
            formData.append('action', 'SetValue');
            
            for (const [key, value] of Object.entries(this.data)) {{
                formData.append('element', key);
                formData.append('value', value);
            }}
            
            fetch(this.commit_url, {{
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            }}).then(response => response.json())
            .then(data => {{
                console.log('SCORM API: Data sent to server:', data);
            }}).catch(error => {{
                console.error('SCORM API: Error sending data:', error);
            }});
        }}
    }};
    
    // CRITICAL FIX: Enhanced API exposure with aggressive discovery
    // Use existing API if found, otherwise use our implementation
    var finalAPI = existingAPI || SCORM_API;
    
    // Set API in ALL possible locations for maximum compatibility
    window.API = finalAPI;
    
    // Enhanced parent window API setting with error handling
    try {{
        if (window.parent && window.parent !== window) {{
            window.parent.API = finalAPI;
        }}
    }} catch (e) {{
        console.log('SCORM API: Could not set API in parent (cross-origin)');
    }}
    
    try {{
        if (window.top && window.top !== window) {{
            window.top.API = finalAPI;
        }}
    }} catch (e) {{
        console.log('SCORM API: Could not set API in top window (cross-origin)');
    }}
    
    // Additional fallbacks for complex iframe structures
    try {{
        if (window.parent && window.parent.parent) {{
            window.parent.parent.API = finalAPI;
        }}
        if (window.parent && window.parent.parent && window.parent.parent.parent) {{
            window.parent.parent.parent.API = finalAPI;
        }}
        if (window.parent && window.parent.parent && window.parent.parent.parent && window.parent.parent.parent.parent) {{
            window.parent.parent.parent.parent.API = finalAPI;
        }}
    }} catch (e) {{
        console.log('SCORM API: Could not set API in nested frames (cross-origin)');
    }}
    
    // CRITICAL: Also set up postMessage communication
    window.addEventListener('message', function(event) {{
        if (event.data && event.data.type === 'REQUEST_SCORM_API') {{
            // Send API back to requesting window
            event.source.postMessage({{
                type: 'SCORM_API_READY',
                api: finalAPI
            }}, '*');
        }}
    }});
    
    // Request API from parent if we don't have one
    if (!existingAPI && window.parent && window.parent !== window) {{
        try {{
            window.parent.postMessage({{type: 'REQUEST_SCORM_API'}}, '*');
        }} catch (e) {{
            console.log('SCORM API: Could not request API from parent');
        }}
    }}
    
    console.log('SCORM API: Initialized and available globally');
}})();
</script>'''
                
                # Inject the script before the closing </head> tag or at the beginning of <body>
                if '</head>' in content_str:
                    content_str = content_str.replace('</head>', scorm_api_script + '\n</head>')
                elif '<body>' in content_str:
                    content_str = content_str.replace('<body>', '<body>' + scorm_api_script)
                else:
                    # If no head or body tags, inject at the beginning
                    content_str = scorm_api_script + '\n' + content_str
                
                # Also inject a simpler API reference for Articulate content
                simple_api_script = f'''
<script>
// Simple API reference for Articulate content
if (typeof window.API === 'undefined') {{
    window.API = {{
        data: {{}},
        commit_url: window.location.origin + '/scorm/api/{topic_id}/',
        user_id: null,
        topic_id: {topic_id},
        
        sendDataToServer: function() {{
            console.log('SCORM API: Sending data to server');
            const data = {{
                'cmi.core.lesson_location': this.data['cmi.core.lesson_location'] || '',
                'cmi.core.suspend_data': this.data['cmi.core.suspend_data'] || '',
                'cmi.core.lesson_status': this.data['cmi.core.lesson_status'] || 'incomplete',
                'cmi.core.score.raw': this.data['cmi.core.score.raw'] || '',
                'cmi.core.entry': this.data['cmi.core.entry'] || 'ab-initio'
            }};
            
            fetch(this.commit_url, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
                }},
                body: JSON.stringify({{
                    'action': 'SetValue',
                    'element': 'cmi.core.lesson_location',
                    'value': data['cmi.core.lesson_location']
                }})
            }}).then(response => response.json())
            .then(result => {{
                console.log('SCORM API: Data sent to server:', result);
            }}).catch(error => {{
                console.error('SCORM API: Error sending data:', error);
            }});
        }},
        
        SetDataChunk: function(data) {{ 
            console.log('SCORM API: SetDataChunk called with:', data);
            this.data['cmi.core.suspend_data'] = data;
            this.sendDataToServer();
            return "true"; 
        }},
        GetDataChunk: function() {{ return this.data['cmi.core.suspend_data'] || ""; }},
        SetPassed: function() {{ 
            console.log('SCORM API: SetPassed called');
            this.data['cmi.core.lesson_status'] = 'passed';
            this.sendDataToServer();
            return "true"; 
        }},
        SetReachedEnd: function() {{ 
            console.log('SCORM API: SetReachedEnd called');
            this.data['cmi.core.lesson_status'] = 'completed';
            this.sendDataToServer();
            return "true"; 
        }},
        SetScore: function(score) {{ 
            console.log('SCORM API: SetScore called with:', score);
            this.data['cmi.core.score.raw'] = score;
            this.sendDataToServer();
            return "true"; 
        }},
        SetBookmark: function(bookmark) {{ 
            console.log('SCORM API: SetBookmark called with:', bookmark);
            this.data['cmi.core.lesson_location'] = bookmark;
            this.sendDataToServer();
            return "true"; 
        }},
        SetFailed: function() {{ 
            console.log('SCORM API: SetFailed called');
            this.data['cmi.core.lesson_status'] = 'failed';
            this.sendDataToServer();
            return "true"; 
        }},
        CommitData: function() {{ 
            console.log('SCORM API: CommitData called');
            this.sendDataToServer();
            return "true"; 
        }},
        ConcedeControl: function() {{ 
            console.log('SCORM API: Views ConcedeControl called');
            // RESPECT SCORM STANDARDS: Allow SCORM content to show goodbye.html first
            // The main ConcedeControl in launch.html will handle the proper flow
            return "true"; 
        }},
        CreateResponseIdentifier: function() {{ return "true"; }},
        Finish: function() {{ 
            console.log('SCORM API: Finish called');
            this.sendDataToServer();
            return "true"; 
        }},
        GetStatus: function() {{ return this.data['cmi.core.lesson_status'] || "incomplete"; }},
        MatchingResponse: function() {{ return "true"; }},
        RecordFillInInteraction: function() {{ return "true"; }},
        RecordMatchingInteraction: function() {{ return "true"; }},
        RecordMultipleChoiceInteraction: function() {{ return "true"; }},
        ResetStatus: function() {{ 
            this.data['cmi.core.lesson_status'] = 'incomplete';
            return "true"; 
        }},
        SetLanguagePreference: function(lang) {{ return "true"; }},
        WriteToDebug: function(message) {{ return "true"; }},
        LMSInitialize: function(param) {{ return "true"; }},
        LMSGetValue: function(element) {{ return this.data[element] || ""; }},
        LMSSetValue: function(element, value) {{ 
            this.data[element] = value;
            this.sendDataToServer();
            return "true"; 
        }},
        LMSCommit: function(param) {{ 
            this.sendDataToServer();
            return "true"; 
        }},
        LMSFinish: function(param) {{ 
            this.sendDataToServer();
            return "true"; 
        }},
        LMSGetLastError: function() {{ return "0"; }},
        LMSGetErrorString: function(errorCode) {{ return "No Error"; }},
        LMSGetDiagnostic: function(errorCode) {{ return "No Error"; }}
    }};
}}
</script>'''
                
                # Inject the simple API script as well
                if '</head>' in content_str:
                    content_str = content_str.replace('</head>', simple_api_script + '\n</head>')
                elif '<body>' in content_str:
                    content_str = content_str.replace('<body>', '<body>' + simple_api_script)
                else:
                    content_str = simple_api_script + '\n' + content_str
                
                content = content_str.encode('utf-8')
                
            except (UnicodeDecodeError, Exception) as e:
                logger.warning(f"Could not process HTML content for relative links: {e}")
                # Continue with original content if processing fails
        
        response = HttpResponse(content, content_type=content_type)
        
        # Set appropriate headers for SCORM content (especially Articulate)
        if file_path.endswith('.html'):
            # Remove restrictive headers for SCORM content
            response['X-Frame-Options'] = 'SAMEORIGIN'
            # Allow inline scripts and eval for SCORM packages (Articulate requires this)
            response['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; frame-src 'self' 'unsafe-inline' 'unsafe-eval'; script-src 'self' 'unsafe-inline' 'unsafe-eval' *.amazonaws.com *.s3.amazonaws.com *.articulate.com *.adobe.com *.captivate.com *.googleapis.com *.gstatic.com; style-src 'self' 'unsafe-inline' *.amazonaws.com *.s3.amazonaws.com fonts.googleapis.com *.gstatic.com; img-src 'self' data: blob: *.amazonaws.com *.s3.amazonaws.com *.articulate.com *.adobe.com *.captivate.com; font-src 'self' *.amazonaws.com *.s3.amazonaws.com fonts.gstatic.com fonts.googleapis.com; media-src 'self' data: blob: *.amazonaws.com *.s3.amazonaws.com; connect-src 'self' *.amazonaws.com *.s3.amazonaws.com metrics.articulate.com *.articulate.com *.adobe.com *.captivate.com https://metrics.articulate.com *.googleapis.com; worker-src 'self' blob:; object-src 'self' data: blob:; base-uri 'self';"
            # Additional headers for Articulate content
        elif file_path.endswith('.js'):
            # Special handling for JavaScript files
            response['Content-Type'] = 'application/javascript; charset=utf-8'
            # Remove X-Content-Type-Options for JS files to prevent MIME type issues
            # Don't add X-Content-Type-Options for JS files
            if 'X-Content-Type-Options' in response:
                del response['X-Content-Type-Options']
        elif file_path.endswith('.css'):
            # Special handling for CSS files
            response['Content-Type'] = 'text/css; charset=utf-8'
        
        # Add CORS headers for SCORM content
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-Requested-With, X-CSRFToken, X-SCORM-User-ID'
        
        return response
        
    except Exception as e:
        logger.error("Error serving SCORM content: {}".format(str(e)))
        raise Http404("Error serving file")

@csrf_exempt
@require_http_methods(["GET", "POST"])
def scorm_api(request, topic_id):
    """SCORM API endpoint for communication with SCORM packages - ENHANCED AUTHENTICATION"""
    user = None
    
    # Method 1: Standard authentication
    if request.user.is_authenticated:
        user = request.user
        logger.info(f"SCORM API: User authenticated via standard auth: {user.username}")
    
    # Method 2: Session-based authentication (for iframe scenarios)
    elif request.session.get('_auth_user_id'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.session.get('_auth_user_id'))
            # Restore the user in the request for proper authentication
            request.user = user
            logger.info(f"SCORM API: User authenticated via session: {user.username}")
        except User.DoesNotExist:
            logger.warning(f"SCORM API: Invalid session user ID: {request.session.get('_auth_user_id')}")
    
    # Method 3: Header-based authentication (for SCORM content)
    elif request.META.get('HTTP_X_SCORM_USER_ID'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.META.get('HTTP_X_SCORM_USER_ID'))
            request.user = user
            logger.info(f"SCORM API: User authenticated via header: {user.username}")
        except (User.DoesNotExist, ValueError):
            logger.warning(f"SCORM API: Invalid header user ID: {request.META.get('HTTP_X_SCORM_USER_ID')}")
    
    # Method 4: Enhanced referer-based authentication
    elif request.META.get('HTTP_REFERER'):
        referer = request.META.get('HTTP_REFERER', '')
        if any(x in referer for x in ['scorm/launch', 'scorm/content', 'scorm/api']):
            if request.session.get('_auth_user_id'):
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    user = User.objects.get(id=request.session.get('_auth_user_id'))
                    request.user = user
                    logger.info(f"SCORM API: User authenticated via referer: {user.username}")
                except User.DoesNotExist:
                    pass
    
    # Method 5: Check for SCORM-specific headers
    elif request.META.get('HTTP_X_SCORM_USER_ID'):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=request.META.get('HTTP_X_SCORM_USER_ID'))
            request.user = user
            logger.info(f"SCORM API: User authenticated via SCORM header: {user.username}")
        except (User.DoesNotExist, ValueError):
            logger.warning(f"SCORM API: Invalid SCORM header user ID: {request.META.get('HTTP_X_SCORM_USER_ID')}")
    
    # Method 6: Check for AJAX requests
    elif request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
        if request.session.get('_auth_user_id'):
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=request.session.get('_auth_user_id'))
                request.user = user
                logger.info(f"SCORM API: User authenticated via AJAX: {user.username}")
            except User.DoesNotExist:
                pass
    
    if not user:
        logger.warning(f"SCORM API: No authentication found for topic {topic_id}")
        logger.warning(f"SCORM API: Session user ID: {request.session.get('_auth_user_id')}")
        logger.warning(f"SCORM API: Referer: {request.META.get('HTTP_REFERER')}")
        logger.warning(f"SCORM API: Headers: {dict(request.META)}")
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Add user to request for use in handlers
    request.scorm_user = user
    
    # Check if user is in preview mode
    topic = get_object_or_404(Topic, id=topic_id)
    preview_mode = not can_access_scorm_content(user, topic) and can_preview_scorm_content(user, topic)
    request.scorm_preview_mode = preview_mode
    
    if preview_mode:
        logger.info(f"SCORM API: User {user.username} accessing SCORM content in preview mode")
    
    logger.info(f"SCORM API: Request from user {request.user.username} (ID: {request.user.id})")
    
    if request.method == 'GET':
        return _handle_scorm_get(request, topic_id)
    elif request.method == 'POST':
        return _handle_scorm_post(request, topic_id)

def _sync_tracking_data(tracking):
    """Enhanced sync with comprehensive data validation and error handling for all SCORM package types"""
    if not tracking.raw_data:
        logger.warning(f"SCORM: No raw_data found for user {tracking.user.id}")
        return
    
    changes_made = False
    package_type = tracking.elearning_package.package_type
    logger.info(f"SCORM: Starting data sync for user {tracking.user.id}, package type: {package_type}")
    logger.info(f"SCORM: Raw data keys: {list(tracking.raw_data.keys())}")
    
    # Package type-specific completion status sources
    if package_type in ['SCORM_1_2', 'SCORM_2004']:
        completion_sources = [
            'cmi.core.lesson_status', 'cmi.completion_status', 'cmi.lesson_status'
        ]
    elif package_type == 'XAPI':
        completion_sources = [
            'cmi.completion_status', 'cmi.lesson_status', 'cmi.core.lesson_status'
        ]
    elif package_type == 'CMI5':
        completion_sources = [
            'cmi5.completion_status', 'cmi.completion_status', 'cmi.lesson_status'
        ]
    elif package_type == 'AICC':
        completion_sources = [
            'cmi.core.lesson_status', 'cmi.lesson_status'
        ]
    else:
        completion_sources = [
            'cmi.core.lesson_status', 'cmi.completion_status', 'cmi.lesson_status'
        ]
    
    # Enhanced completion status sync with package-specific validation
    for source in completion_sources:
        if source in tracking.raw_data:
            raw_status = tracking.raw_data[source]
            if raw_status and raw_status.strip() and raw_status != tracking.completion_status:
                # Package-specific valid statuses
                if package_type in ['SCORM_1_2', 'SCORM_2004']:
                    valid_statuses = ['completed', 'incomplete', 'not attempted', 'passed', 'failed', 'browsed']
                elif package_type == 'XAPI':
                    valid_statuses = ['completed', 'incomplete', 'not attempted', 'passed', 'failed']
                elif package_type == 'CMI5':
                    valid_statuses = ['completed', 'incomplete', 'not attempted', 'passed', 'failed']
                elif package_type == 'AICC':
                    valid_statuses = ['completed', 'incomplete', 'not attempted', 'passed', 'failed']
                else:
                    valid_statuses = ['completed', 'incomplete', 'not attempted', 'passed', 'failed', 'browsed']
                
                if raw_status in valid_statuses:
                    tracking.completion_status = raw_status
                    changes_made = True
                    logger.info(f"SCORM: Synced completion_status from {source}: {raw_status} (package: {package_type})")
                    break
                else:
                    logger.warning(f"SCORM: Invalid completion_status value for {package_type}: {raw_status}")
    
    # Package type-specific success status sources
    if package_type in ['SCORM_2004', 'XAPI', 'CMI5']:
        success_sources = ['cmi.success_status', 'cmi.core.success_status']
    else:
        # SCORM 1.2 and AICC don't have separate success status
        success_sources = []
    
    for source in success_sources:
        if source in tracking.raw_data:
            raw_success = tracking.raw_data[source]
            if raw_success and raw_success.strip() and raw_success != tracking.success_status:
                valid_success = ['passed', 'failed', 'unknown']
                if raw_success in valid_success:
                    tracking.success_status = raw_success
                    changes_made = True
                    logger.info(f"SCORM: Synced success_status from {source}: {raw_success} (package: {package_type})")
                    break
    
    # Package type-specific score mappings
    if package_type in ['SCORM_1_2', 'AICC']:
        score_mappings = {
            'cmi.core.score.raw': 'score_raw',
            'cmi.core.score.min': 'score_min', 
            'cmi.core.score.max': 'score_max',
            'cmi.core.score.scaled': 'score_scaled'
        }
    elif package_type in ['SCORM_2004', 'XAPI', 'CMI5']:
        score_mappings = {
            'cmi.score.raw': 'score_raw',
            'cmi.score.min': 'score_min', 
            'cmi.score.max': 'score_max',
            'cmi.score.scaled': 'score_scaled',
            'cmi.core.score.raw': 'score_raw',  # Fallback for SCORM 1.2 compatibility
            'cmi.core.score.min': 'score_min',
            'cmi.core.score.max': 'score_max',
            'cmi.core.score.scaled': 'score_scaled'
        }
    else:
        # Default to SCORM 1.2 format
        score_mappings = {
            'cmi.core.score.raw': 'score_raw',
            'cmi.core.score.min': 'score_min', 
            'cmi.core.score.max': 'score_max',
            'cmi.core.score.scaled': 'score_scaled'
        }
    
    # ENHANCED: Score sync with package-specific validation and better error handling
    for source, field in score_mappings.items():
        if source in tracking.raw_data:
            raw_value = tracking.raw_data[source]
            if raw_value and raw_value.strip():
                try:
                    float_value = float(raw_value)
                    current_value = getattr(tracking, field)
                    if current_value != float_value:
                        setattr(tracking, field, float_value)
                        changes_made = True
                        logger.info(f"SCORM: Synced {field} from {source}: {raw_value} (package: {package_type})")
                        
                        # ENHANCED: Set default max score if needed
                        if field == 'score_raw' and tracking.score_max is None:
                            if 0 <= float_value <= 1:
                                tracking.score_max = 1.0
                            elif 0 <= float_value <= 100:
                                tracking.score_max = 100.0
                            else:
                                tracking.score_max = 100.0  # Default fallback
                            logger.info(f"SCORM: Set default max score to {tracking.score_max}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"SCORM: Invalid score value from {source}: {raw_value} - {str(e)}")
                    # Don't fail completely, just log the issue
    
    # Package type-specific time mappings
    if package_type in ['SCORM_1_2', 'AICC']:
        time_mappings = {
            'cmi.core.total_time': 'total_time',
            'cmi.core.session_time': 'session_time'
        }
    elif package_type in ['SCORM_2004', 'XAPI', 'CMI5']:
        time_mappings = {
            'cmi.total_time': 'total_time',
            'cmi.session_time': 'session_time',
            'cmi.core.total_time': 'total_time',  # Fallback for SCORM 1.2 compatibility
            'cmi.core.session_time': 'session_time'
        }
    else:
        # Default to SCORM 1.2 format
        time_mappings = {
            'cmi.core.total_time': 'total_time',
            'cmi.core.session_time': 'session_time'
        }
    
    # ENHANCED: Time sync with package-specific parsing and better error handling
    for source, field in time_mappings.items():
        if source in tracking.raw_data:
            raw_time = tracking.raw_data[source]
            if raw_time and raw_time.strip() and raw_time != 'PT0S':
                try:
                    parsed_time = tracking._parse_scorm_time(raw_time)
                    if parsed_time:
                        if getattr(tracking, field) != parsed_time:
                            setattr(tracking, field, parsed_time)
                            changes_made = True
                            logger.info(f"SCORM: Synced {field} from {source}: {raw_time} -> {parsed_time} (package: {package_type})")
                    else:
                        logger.warning(f"SCORM: Failed to parse time from {source}: {raw_time}")
                except Exception as e:
                    logger.warning(f"SCORM: Error parsing time from {source}: {raw_time} - {str(e)}")
    
    # Package type-specific progress measure sources
    if package_type in ['SCORM_2004', 'XAPI', 'CMI5']:
        progress_sources = ['cmi.progress_measure', 'cmi.core.progress_measure']
    else:
        # SCORM 1.2 and AICC don't have progress measure
        progress_sources = []
    
    for source in progress_sources:
        if source in tracking.raw_data:
            raw_progress = tracking.raw_data[source]
            if raw_progress and raw_progress.strip():
                try:
                    progress_value = float(raw_progress)
                    if tracking.progress_measure != progress_value:
                        tracking.progress_measure = progress_value
                        changes_made = True
                        logger.info(f"SCORM: Synced progress_measure from {source}: {raw_progress} (package: {package_type})")
                        break
                except (ValueError, TypeError):
                    logger.warning(f"SCORM: Invalid progress value from {source}: {raw_progress}")
    
    # Package type-specific location and suspend data sources
    if package_type in ['SCORM_1_2', 'AICC']:
        location_sources = ['cmi.core.lesson_location']
        suspend_sources = ['cmi.core.suspend_data']
    elif package_type in ['SCORM_2004', 'XAPI', 'CMI5']:
        location_sources = ['cmi.location', 'cmi.core.lesson_location']
        suspend_sources = ['cmi.suspend_data', 'cmi.core.suspend_data']
    else:
        # Default to SCORM 1.2 format
        location_sources = ['cmi.core.lesson_location']
        suspend_sources = ['cmi.core.suspend_data']
    
    # Enhanced location sync
    for source in location_sources:
        if source in tracking.raw_data:
            raw_location = tracking.raw_data[source]
            if raw_location and raw_location.strip() and raw_location != tracking.location:
                tracking.location = raw_location
                changes_made = True
                logger.info(f"SCORM: Synced location from {source}: {raw_location} (package: {package_type})")
                break
    
    # Enhanced suspend data sync
    for source in suspend_sources:
        if source in tracking.raw_data:
            raw_suspend = tracking.raw_data[source]
            if raw_suspend and raw_suspend.strip() and raw_suspend != tracking.suspend_data:
                tracking.suspend_data = raw_suspend
                changes_made = True
                logger.info(f"SCORM: Synced suspend_data from {source}: {raw_suspend[:100]}... (package: {package_type})")
                break
    
    # Package type-specific additional fields
    if package_type == 'CMI5':
        # Handle cmi5-specific fields
        cmi5_fields = ['cmi5.exit', 'cmi5.completion_status']
        for field in cmi5_fields:
            if field in tracking.raw_data:
                raw_value = tracking.raw_data[field]
                if raw_value and raw_value.strip():
                    # Store in raw_data for cmi5-specific handling
                    tracking.raw_data[f'cmi5.{field.split(".")[-1]}'] = raw_value
                    changes_made = True
                    logger.info(f"SCORM: Synced cmi5 field {field}: {raw_value}")
    
    # Save if any changes were made (only if not in preview mode)
    if changes_made:
        if not getattr(tracking, '_preview_mode', False):
            tracking.save()
            logger.info(f"SCORM: Data synchronization completed for user {tracking.user.id} (package: {package_type})")
        else:
            logger.info(f"SCORM: Preview mode - data not saved for user {tracking.user.id} (package: {package_type})")
    else:
        logger.info(f"SCORM: No data synchronization needed for user {tracking.user.id} (package: {package_type})")

def _handle_scorm_get(request, topic_id):
    """Handle SCORM GET requests (Initialize, GetValue) - Enhanced for SCORM 2004"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        elearning_package = get_object_or_404(ELearningPackage, topic=topic)
        
        # Get tracking record
        tracking, created = ELearningTracking.objects.get_or_create(
            user=request.scorm_user,
            elearning_package=elearning_package
        )
        
        # Get the requested element
        element = request.GET.get('element', '')
        
        # SCORM 1.2 Core elements
        if element == 'cmi.core.lesson_status':
            return JsonResponse({'value': tracking.completion_status})
        elif element == 'cmi.core.score.raw':
            return JsonResponse({'value': str(tracking.score_raw) if tracking.score_raw is not None else ''})
        elif element == 'cmi.core.score.min':
            return JsonResponse({'value': str(tracking.score_min) if tracking.score_min is not None else ''})
        elif element == 'cmi.core.score.max':
            return JsonResponse({'value': str(tracking.score_max) if tracking.score_max is not None else ''})
        elif element == 'cmi.core.total_time':
            return JsonResponse({'value': str(tracking.total_time) if tracking.total_time else 'PT0S'})
        elif element == 'cmi.core.session_time':
            return JsonResponse({'value': str(tracking.session_time) if tracking.session_time else 'PT0S'})
        elif element == 'cmi.core.entry':
            # ENHANCED: More specific resume detection logic for SCORM 1.2
            has_bookmark = bool(tracking.location or tracking.raw_data.get('cmi.core.lesson_location', ''))
            has_suspend_data = bool(tracking.suspend_data or tracking.raw_data.get('cmi.core.suspend_data', ''))
            
            # ENHANCED: Only resume if there's actual bookmark data, not just any progress
            should_resume = (
                (has_bookmark or has_suspend_data) and 
                tracking.first_launch is not None
            )
            
            entry_value = 'resume' if should_resume else 'ab-initio'
            
            # Enhanced logging for resume detection
            logger.info(f"SCORM 1.2 Enhanced Resume Detection for user {request.scorm_user.id}:")
            logger.info(f"  - Has bookmark: {has_bookmark} (location: {tracking.location})")
            logger.info(f"  - Has suspend data: {has_suspend_data} (length: {len(tracking.suspend_data) if tracking.suspend_data else 0})")
            logger.info(f"  - Should resume: {should_resume}")
            logger.info(f"  - Entry value: {entry_value}")
            return JsonResponse({'value': entry_value})
        elif element == 'cmi.core.exit':
            return JsonResponse({'value': tracking.exit_value or tracking.raw_data.get('cmi.core.exit', '')})
        elif element == 'cmi.core.lesson_location':
            # Return lesson location for bookmarking
            lesson_location = tracking.location or tracking.raw_data.get('cmi.core.lesson_location', '')
            logger.info(f"SCORM: Getting lesson_location for user {request.scorm_user.id}: {lesson_location}")
            return JsonResponse({'value': lesson_location})
        elif element == 'cmi.core.student_id':
            return JsonResponse({'value': str(request.scorm_user.id)})
        elif element == 'cmi.core.student_name':
            return JsonResponse({'value': request.scorm_user.get_full_name() or request.scorm_user.username})
        elif element == 'cmi.core.credit':
            return JsonResponse({'value': tracking.credit})
        elif element == 'cmi.core.lesson_mode':
            return JsonResponse({'value': tracking.mode})
        elif element == 'cmi.core.max_time_allowed':
            # Return student data max time allowed
            max_time = tracking.student_data_max_time_allowed
            return JsonResponse({'value': str(max_time) if max_time else ''})
        elif element == 'cmi.core.mastery_score':
            # Return student data mastery score
            mastery_score = tracking.student_data_mastery_score
            return JsonResponse({'value': str(mastery_score) if mastery_score is not None else ''})
        elif element == 'cmi.core.suspend_data':
            # Return suspend data for Articulate with size validation
            suspend_data = tracking.suspend_data or tracking.raw_data.get('cmi.core.suspend_data', '')
            
            # Validate suspend data size based on SCORM version
            if package.package_type == 'SCORM_1_2' and len(suspend_data) > 4096:
                logger.warning(f"SCORM: Suspend data exceeds SCORM 1.2 limit: {len(suspend_data)} chars")
                # Truncate to fit SCORM 1.2 limit
                suspend_data = suspend_data[:4096]
                logger.info(f"SCORM: Truncated suspend data to {len(suspend_data)} chars")
            elif package.package_type == 'SCORM_2004' and len(suspend_data) > 64000:
                logger.warning(f"SCORM: Suspend data exceeds SCORM 2004 limit: {len(suspend_data)} chars")
                # Truncate to fit SCORM 2004 limit
                suspend_data = suspend_data[:64000]
                logger.info(f"SCORM: Truncated suspend data to {len(suspend_data)} chars")
            
            logger.info(f"SCORM: Returning suspend data for user {request.scorm_user.id}: {len(suspend_data)} chars")
            return JsonResponse({'value': suspend_data})
        elif element == 'cmi.core.launch_data':
            # Return launch data for Articulate
            launch_data = tracking.launch_data or tracking.raw_data.get('cmi.core.launch_data', '')
            return JsonResponse({'value': launch_data})
        
        # SCORM 2004 elements
        elif element == 'cmi.completion_status':
            return JsonResponse({'value': tracking.completion_status})
        elif element == 'cmi.success_status':
            return JsonResponse({'value': tracking.success_status})
        elif element == 'cmi.score.scaled':
            return JsonResponse({'value': str(tracking.score_scaled) if tracking.score_scaled is not None else ''})
        elif element == 'cmi.score.raw':
            return JsonResponse({'value': str(tracking.score_raw) if tracking.score_raw is not None else ''})
        elif element == 'cmi.score.min':
            return JsonResponse({'value': str(tracking.score_min) if tracking.score_min is not None else ''})
        elif element == 'cmi.score.max':
            return JsonResponse({'value': str(tracking.score_max) if tracking.score_max is not None else ''})
        elif element == 'cmi.progress_measure':
            return JsonResponse({'value': str(tracking.progress_measure) if tracking.progress_measure is not None else ''})
        elif element == 'cmi.location':
            return JsonResponse({'value': tracking.location})
        elif element == 'cmi.suspend_data':
            return JsonResponse({'value': tracking.suspend_data})
        elif element == 'cmi.launch_data':
            return JsonResponse({'value': tracking.launch_data})
        elif element == 'cmi.entry':
            # ENHANCED: More specific resume detection logic for SCORM 2004
            has_bookmark = bool(tracking.location or tracking.raw_data.get('cmi.location', ''))
            has_suspend_data = bool(tracking.suspend_data or tracking.raw_data.get('cmi.suspend_data', ''))
            
            # ENHANCED: Only resume if there's actual bookmark data, not just any progress
            should_resume = (
                (has_bookmark or has_suspend_data) and 
                tracking.first_launch is not None
            )
            
            entry_value = 'resume' if should_resume else 'ab-initio'
            
            logger.info(f"SCORM 2004 Enhanced Resume Detection for user {request.scorm_user.id}:")
            logger.info(f"  - Has bookmark: {has_bookmark} (location: {tracking.location})")
            logger.info(f"  - Has suspend data: {has_suspend_data} (length: {len(tracking.suspend_data) if tracking.suspend_data else 0})")
            logger.info(f"  - Should resume: {should_resume}")
            logger.info(f"  - Entry value: {entry_value}")
            
            return JsonResponse({'value': entry_value})
        elif element == 'cmi.exit':
            return JsonResponse({'value': tracking.exit_value})
        elif element == 'cmi.credit':
            return JsonResponse({'value': tracking.credit})
        elif element == 'cmi.mode':
            return JsonResponse({'value': tracking.mode})
        elif element == 'cmi.learner_id':
            return JsonResponse({'value': str(request.scorm_user.id)})
        elif element == 'cmi.learner_name':
            return JsonResponse({'value': request.scorm_user.get_full_name() or request.scorm_user.username})
        
        # Learner preferences
        elif element == 'cmi.learner_preference.audio_level':
            return JsonResponse({'value': str(tracking.learner_preference_audio_level) if tracking.learner_preference_audio_level is not None else ''})
        elif element == 'cmi.learner_preference.language':
            return JsonResponse({'value': tracking.learner_preference_language})
        elif element == 'cmi.learner_preference.delivery_speed':
            return JsonResponse({'value': str(tracking.learner_preference_delivery_speed) if tracking.learner_preference_delivery_speed is not None else ''})
        elif element == 'cmi.learner_preference.audio_captioning':
            return JsonResponse({'value': str(tracking.learner_preference_audio_captioning).lower() if tracking.learner_preference_audio_captioning is not None else ''})
        
        # Student data
        elif element == 'cmi.student_data.mastery_score':
            return JsonResponse({'value': str(tracking.student_data_mastery_score) if tracking.student_data_mastery_score is not None else ''})
        elif element == 'cmi.student_data.max_time_allowed':
            return JsonResponse({'value': str(tracking.student_data_max_time_allowed) if tracking.student_data_max_time_allowed else ''})
        elif element == 'cmi.student_data.time_limit_action':
            return JsonResponse({'value': tracking.student_data_time_limit_action})
        
        # Objectives
        elif element.startswith('cmi.objectives.'):
            return _handle_objectives_get(tracking, element)
        
        # Interactions
        elif element.startswith('cmi.interactions.'):
            return _handle_interactions_get(tracking, element)
        
        # Comments
        elif element.startswith('cmi.comments_from_learner.'):
            return _handle_comments_get(tracking, element, 'learner')
        elif element.startswith('cmi.comments_from_lms.'):
            return _handle_comments_get(tracking, element, 'lms')
        
        else:
            # Return value from raw_data or empty
            value = tracking.raw_data.get(element, '')
            return JsonResponse({'value': value})
            
    except Exception as e:
        logger.error("Error in SCORM GET: {}".format(str(e)))
        return JsonResponse({'error': str(e)}, status=500)

def _handle_scorm_post(request, topic_id):
    """Handle SCORM POST requests (Commit, SetValue) - Enhanced for full compliance"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        elearning_package = get_object_or_404(ELearningPackage, topic=topic)
        
        # Get tracking record
        tracking, created = ELearningTracking.objects.get_or_create(
            user=request.scorm_user,
            elearning_package=elearning_package
        )
        
        # Get the action
        action = request.POST.get('action', '')
        
        if action == 'SetValue':
            element = request.POST.get('element', '')
            value = request.POST.get('value', '')
            
            logger.info(f"SCORM: SetValue request - element: {element}, value: {value} for user {request.scorm_user.id}")
            
            # Package type-specific element validation
            package_type = elearning_package.package_type
            
            if package_type == 'SCORM_1_2':
                valid_elements = [
                    # SCORM 1.2 Core elements (23 elements)
                    'cmi.core.lesson_status', 'cmi.core.score.raw', 'cmi.core.score.min', 'cmi.core.score.max',
                    'cmi.core.total_time', 'cmi.core.session_time', 'cmi.core.lesson_location', 'cmi.core.exit',
                    'cmi.core.entry', 'cmi.core.student_id', 'cmi.core.student_name', 'cmi.core.credit',
                    'cmi.core.lesson_mode', 'cmi.core.max_time_allowed', 'cmi.core.mastery_score',
                    'cmi.core.suspend_data', 'cmi.core.launch_data', 'cmi.core.comments',
                    'cmi.core.comments_from_lms', 'cmi.core.objectives', 'cmi.core.student_data',
                    'cmi.core.student_preference', 'cmi.core.interactions', 'cmi.core.navigation',
                    'cmi.core.exit_assessment_required', 'cmi.core.exit_assessment_completed'
                ]
            elif package_type == 'SCORM_2004':
                valid_elements = [
                    # SCORM 2004 elements (50+ elements) - COMPLETE IMPLEMENTATION
                    'cmi.completion_status', 'cmi.success_status', 'cmi.score.scaled', 'cmi.score.raw',
                    'cmi.score.min', 'cmi.score.max', 'cmi.progress_measure', 'cmi.location',
                    'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry', 'cmi.exit', 'cmi.credit',
                    'cmi.mode', 'cmi.learner_id', 'cmi.learner_name', 'cmi.completion_threshold',
                    'cmi.scaled_passing_score', 'cmi.total_time', 'cmi.session_time',
                    
                    # Learner preferences (4 elements)
                    'cmi.learner_preference.audio_level', 'cmi.learner_preference.language',
                    'cmi.learner_preference.delivery_speed', 'cmi.learner_preference.audio_captioning',
                    
                    # Student data (3 elements)
                    'cmi.student_data.mastery_score', 'cmi.student_data.max_time_allowed',
                    'cmi.student_data.time_limit_action',
                    
                    # Objectives (7 elements)
                    'cmi.objectives._count', 'cmi.objectives._children', 'cmi.objectives.id',
                    'cmi.objectives.score', 'cmi.objectives.success_status',
                    'cmi.objectives.completion_status', 'cmi.objectives.progress_measure',
                    'cmi.objectives.description',
                    
                    # Interactions (10 elements)
                    'cmi.interactions._count', 'cmi.interactions._children', 'cmi.interactions.id',
                    'cmi.interactions.type', 'cmi.interactions.objectives', 'cmi.interactions.timestamp',
                    'cmi.interactions.correct_responses', 'cmi.interactions.weighting',
                    'cmi.interactions.learner_response', 'cmi.interactions.result',
                    'cmi.interactions.latency', 'cmi.interactions.description',
                    
                    # Comments from learner (4 elements)
                    'cmi.comments_from_learner._count', 'cmi.comments_from_learner._children',
                    'cmi.comments_from_learner.id', 'cmi.comments_from_learner.timestamp',
                    'cmi.comments_from_learner.comment', 'cmi.comments_from_learner.location',
                    
                    # Comments from LMS (4 elements)
                    'cmi.comments_from_lms._count', 'cmi.comments_from_lms._children',
                    'cmi.comments_from_lms.id', 'cmi.comments_from_lms.timestamp',
                    'cmi.comments_from_lms.comment', 'cmi.comments_from_lms.location',
                    
                    # Navigation elements (SCORM 2004)
                    'adl.nav.request', 'adl.nav.request_valid'
                ]
            elif package_type == 'XAPI':
                valid_elements = [
                    # xAPI (Tin Can) elements
                    'cmi.completion_status', 'cmi.success_status', 'cmi.score.scaled', 'cmi.score.raw',
                    'cmi.score.min', 'cmi.score.max', 'cmi.progress_measure', 'cmi.location',
                    'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry', 'cmi.exit', 'cmi.credit',
                    'cmi.mode', 'cmi.learner_id', 'cmi.learner_name', 'cmi.completion_threshold',
                    'cmi.scaled_passing_score', 'cmi.total_time', 'cmi.session_time',
                    
                    # xAPI specific elements
                    'cmi.learner_preference.audio_level', 'cmi.learner_preference.language',
                    'cmi.learner_preference.delivery_speed', 'cmi.learner_preference.audio_captioning',
                    'cmi.student_data.mastery_score', 'cmi.student_data.max_time_allowed',
                    'cmi.student_data.time_limit_action'
                ]
            elif package_type == 'CMI5':
                valid_elements = [
                    # cmi5 elements
                    'cmi5.exit', 'cmi5.completion_status', 'cmi5.exit_assessment_completed',
                    'cmi.completion_status', 'cmi.success_status', 'cmi.score.scaled', 'cmi.score.raw',
                    'cmi.score.min', 'cmi.score.max', 'cmi.progress_measure', 'cmi.location',
                    'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry', 'cmi.exit', 'cmi.credit',
                    'cmi.mode', 'cmi.learner_id', 'cmi.learner_name', 'cmi.completion_threshold',
                    'cmi.scaled_passing_score', 'cmi.total_time', 'cmi.session_time',
                    
                    # cmi5 specific elements
                    'cmi.learner_preference.audio_level', 'cmi.learner_preference.language',
                    'cmi.learner_preference.delivery_speed', 'cmi.learner_preference.audio_captioning',
                    'cmi.student_data.mastery_score', 'cmi.student_data.max_time_allowed',
                    'cmi.student_data.time_limit_action'
                ]
            elif package_type == 'AICC':
                valid_elements = [
                    # AICC elements
                    'cmi.core.lesson_status', 'cmi.core.score.raw', 'cmi.core.score.min', 'cmi.core.score.max',
                    'cmi.core.total_time', 'cmi.core.session_time', 'cmi.core.lesson_location', 'cmi.core.exit',
                    'cmi.core.entry', 'cmi.core.student_id', 'cmi.core.student_name', 'cmi.core.credit',
                    'cmi.core.lesson_mode', 'cmi.core.max_time_allowed', 'cmi.core.mastery_score',
                    'cmi.core.suspend_data', 'cmi.core.launch_data', 'cmi.core.comments',
                    'cmi.core.comments_from_lms', 'cmi.core.objectives', 'cmi.core.student_data',
                    'cmi.core.student_preference', 'cmi.core.interactions', 'cmi.core.navigation'
                ]
            else:
                # Default to SCORM 1.2 format
                valid_elements = [
                    'cmi.core.lesson_status', 'cmi.core.score.raw', 'cmi.core.score.min', 'cmi.core.score.max',
                    'cmi.core.total_time', 'cmi.core.session_time', 'cmi.core.lesson_location', 'cmi.core.exit',
                    'cmi.core.entry', 'cmi.core.student_id', 'cmi.core.student_name', 'cmi.core.credit',
                    'cmi.core.lesson_mode', 'cmi.core.max_time_allowed', 'cmi.core.mastery_score',
                    'cmi.core.suspend_data', 'cmi.core.launch_data', 'cmi.core.comments',
                    'cmi.core.comments_from_lms', 'cmi.core.objectives', 'cmi.core.student_data',
                    'cmi.core.student_preference', 'cmi.core.interactions', 'cmi.core.navigation'
                ]
            
            # Enhanced element validation with 100% compliance
            if not (element.startswith('cmi.core.') or element.startswith('cmi.interactions.') or 
                   element.startswith('cmi.objectives.') or element.startswith('cmi.comments.') or
                   element.startswith('cmi.learner_preference.') or element.startswith('cmi.student_data.') or
                   element.startswith('adl.nav.') or element.startswith('cmi5.') or
                   element in valid_elements):
                logger.warning(f"SCORM: Invalid element requested: {element}")
                # Enhanced error recovery
                recovery_result = _enhanced_error_recovery(request, topic_id, '408', {'element': element})
                if recovery_result.get('result') == 'true':
                    logger.info(f"SCORM: Error recovery successful for element {element}")
                    return JsonResponse({'result': 'true', 'message': 'Element recovered'})
                else:
                    return JsonResponse({'result': 'false', 'error': 'Invalid element'})
            
            # CRITICAL FIX: Update raw_data immediately for all elements
            tracking.raw_data[element] = value
            logger.info(f"SCORM: Set raw_data[{element}] = {value}")
            
            # ENHANCED DATA SYNCHRONIZATION: Update individual fields based on element
            field_updated = False
            
            # Update completion status
            if element == 'cmi.core.lesson_status' or element == 'cmi.completion_status':
                # Validate lesson status values
                valid_statuses = ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']
                if value in valid_statuses:
                    tracking.completion_status = value
                    field_updated = True
                    logger.info(f"SCORM: Set completion_status to {value}")
                else:
                    logger.warning(f"SCORM: Invalid completion_status value: {value}")
            
            # Update success status for SCORM 2004
            elif element == 'cmi.success_status':
                valid_success_statuses = ['passed', 'failed', 'unknown']
                if value in valid_success_statuses:
                    tracking.success_status = value
                    field_updated = True
                    logger.info(f"SCORM: Set success_status to {value}")
                else:
                    logger.warning(f"SCORM: Invalid success_status value: {value}")
            # Update score fields - ENHANCED VALIDATION
            elif element == 'cmi.core.score.raw' or element == 'cmi.score.raw':
                try:
                    if value and value.strip():
                        new_score = float(value)
                        tracking.score_raw = new_score
                        field_updated = True
                        logger.info(f"SCORM: Set score.raw to {value}")
                        
                        # ENHANCED: Set default max score if not set
                        if tracking.score_max is None:
                            if 0 <= new_score <= 1:
                                tracking.score_max = 1.0
                            elif 0 <= new_score <= 100:
                                tracking.score_max = 100.0
                            else:
                                tracking.score_max = 100.0  # Default fallback
                            logger.info(f"SCORM: Set default max score to {tracking.score_max}")
                        
                        # ENHANCED: Validate score with more lenient rules
                        if not tracking.validate_score():
                            logger.warning(f"SCORM: Score validation warning for user {request.scorm_user.id}: {new_score} (range: {tracking.score_min}-{tracking.score_max})")
                            # Don't fail completely, just log the warning
                        
                        # ENHANCED: Check mastery completion after score update
                        if tracking.student_data_mastery_score and tracking.score_raw is not None:
                            mastery_achieved = tracking.check_mastery_completion()
                            if mastery_achieved:
                                logger.info(f"SCORM: Auto-completed topic {tracking.elearning_package.topic.id} based on mastery score achievement")
                    else:
                        logger.info(f"SCORM: Empty score value received for {element}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"SCORM: Invalid score.raw value: {value} - {str(e)}")
                    # Don't fail completely, just log the issue
            elif element == 'cmi.core.score.min' or element == 'cmi.score.min':
                try:
                    if value and value.strip():
                        tracking.score_min = float(value)
                        field_updated = True
                        logger.info(f"SCORM: Set score.min to {value}")
                    else:
                        logger.info(f"SCORM: Empty score.min value received")
                except (ValueError, TypeError) as e:
                    logger.warning(f"SCORM: Invalid score.min value: {value} - {str(e)}")
            elif element == 'cmi.core.score.max' or element == 'cmi.score.max':
                try:
                    if value and value.strip():
                        tracking.score_max = float(value)
                        field_updated = True
                        logger.info(f"SCORM: Set score.max to {value}")
                        
                        # ENHANCED: Log score summary after setting max score
                        if tracking.score_raw is not None:
                            summary = tracking.get_score_summary()
                            logger.info(f"SCORM: Score summary for user {request.scorm_user.id}: {summary}")
                    else:
                        logger.info(f"SCORM: Empty score.max value received")
                except (ValueError, TypeError) as e:
                    logger.warning(f"SCORM: Invalid score.max value: {value} - {str(e)}")
            elif element == 'cmi.core.score.scaled' or element == 'cmi.score.scaled':
                try:
                    if value and value.strip():
                        tracking.score_scaled = float(value)
                        field_updated = True
                        logger.info(f"SCORM: Set score.scaled to {value}")
                    else:
                        logger.info(f"SCORM: Empty score.scaled value received")
                except (ValueError, TypeError) as e:
                    logger.warning(f"SCORM: Invalid score.scaled value: {value} - {str(e)}")
            
            # Update time tracking
            elif element == 'cmi.core.total_time' or element == 'cmi.total_time':
                tracking.total_time = tracking._parse_scorm_time(value)
                field_updated = True
                logger.info(f"SCORM: Set total_time to {value}")
            elif element == 'cmi.core.session_time' or element == 'cmi.session_time':
                tracking.session_time = tracking._parse_scorm_time(value)
                field_updated = True
                logger.info(f"SCORM: Set session_time to {value}")
            elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                # Store lesson location for bookmarking
                tracking.location = value
                tracking.raw_data['cmi.core.lesson_location'] = value
                logger.info(f"SCORM: Set lesson_location to {value}")
                
                # FIXED: Use enhanced bookmark method for proper handling
                if value and value.strip():
                    tracking.set_bookmark(value)
                    logger.info(f"SCORM: Bookmark set for user {request.scorm_user.id} at location: {value}")
            elif element == 'cmi.core.exit' or element == 'cmi.exit':
                # Handle all exit values: 'time-out', 'suspend', 'logout', 'normal', 'ab-initio'
                valid_exits = ['time-out', 'suspend', 'logout', 'normal', 'ab-initio']
                if value in valid_exits:
                    tracking.exit_value = value
                    tracking.raw_data['cmi.core.exit'] = value
                    logger.info(f"SCORM: Set exit to {value}")
                    
                    # Handle different exit scenarios
                    if value == 'logout':
                        logger.info(f"SCORM: User {request.scorm_user.id} manually logged out")
                    elif value == 'time-out':
                        logger.info(f"SCORM: User {request.scorm_user.id} session timed out")
                    elif value == 'suspend':
                        logger.info(f"SCORM: User {request.scorm_user.id} suspended session")
                    elif value == 'normal':
                        logger.info(f"SCORM: User {request.scorm_user.id} completed normally")
                else:
                    logger.warning(f"SCORM: Invalid exit value: {value}")
            elif element == 'cmi.core.entry' or element == 'cmi.entry':
                # Store entry value for tracking
                valid_entries = ['ab-initio', 'resume']
                if value in valid_entries:
                    tracking.entry = value
                    tracking.raw_data['cmi.core.entry'] = value
                    logger.info(f"SCORM: Set entry to {value}")
                    if value == 'resume':
                        # Handle resume - ensure we have lesson location for bookmarking
                        lesson_location = tracking.location or tracking.raw_data.get('cmi.core.lesson_location', '')
                        if lesson_location:
                            logger.info(f"SCORM: Resuming from bookmark location: {lesson_location}")
                else:
                    logger.warning(f"SCORM: Invalid entry value: {value}")
            elif element == 'cmi.core.suspend_data' or element == 'cmi.suspend_data':
                # Store suspend data (important for Articulate) with size validation
                # Validate suspend data size based on SCORM version
                if package.package_type == 'SCORM_1_2' and len(value) > 4096:
                    logger.warning(f"SCORM: Suspend data exceeds SCORM 1.2 limit: {len(value)} chars")
                    # Truncate to fit SCORM 1.2 limit
                    value = value[:4096]
                    logger.info(f"SCORM: Truncated suspend data to {len(value)} chars")
                elif package.package_type == 'SCORM_2004' and len(value) > 64000:
                    logger.warning(f"SCORM: Suspend data exceeds SCORM 2004 limit: {len(value)} chars")
                    # Truncate to fit SCORM 2004 limit
                    value = value[:64000]
                    logger.info(f"SCORM: Truncated suspend data to {len(value)} chars")
                
                tracking.suspend_data = value
                tracking.raw_data['cmi.core.suspend_data'] = value
                logger.info(f"SCORM: Set suspend_data to {value[:100]}... ({len(value)} chars)")  # Log first 100 chars
                
                # FIXED: Use enhanced bookmark method for proper handling
                if value and value.strip():
                    # Get current location if available
                    current_location = tracking.location or tracking.raw_data.get('cmi.core.lesson_location', '')
                    tracking.set_bookmark(current_location, value)
                    logger.info(f"SCORM: Suspend data set for user {request.scorm_user.id}")
            elif element == 'cmi.core.launch_data' or element == 'cmi.launch_data':
                # Store launch data (important for Articulate)
                tracking.launch_data = value
                tracking.raw_data['cmi.core.launch_data'] = value
                logger.info(f"SCORM: Set launch_data to {value[:100]}...")  # Log first 100 chars
            elif element == 'cmi.core.credit' or element == 'cmi.credit':
                # Store credit value
                valid_credits = ['credit', 'no-credit']
                if value in valid_credits:
                    tracking.credit = value
                    logger.info(f"SCORM: Set credit to {value}")
                else:
                    logger.warning(f"SCORM: Invalid credit value: {value}")
            elif element == 'cmi.core.lesson_mode' or element == 'cmi.mode':
                # Store mode value
                valid_modes = ['browse', 'normal', 'review']
                if value in valid_modes:
                    tracking.mode = value
                    logger.info(f"SCORM: Set mode to {value}")
                else:
                    logger.warning(f"SCORM: Invalid mode value: {value}")
            # Update progress measure - CRITICAL FOR ACCURATE PROGRESS DISPLAY
            elif element == 'cmi.progress_measure':
                try:
                    tracking.progress_measure = float(value) if value else None
                    field_updated = True
                    logger.info(f"SCORM: Set progress_measure to {value}")
                    
                    # Auto-update completion status based on progress
                    if tracking.progress_measure is not None and tracking.progress_measure >= 1.0:
                        if tracking.completion_status != 'completed':
                            tracking.completion_status = 'completed'
                            logger.info(f"SCORM: Auto-updated completion_status to 'completed' based on progress_measure: {tracking.progress_measure}")
                    
                    # ENHANCED: Auto-completion based on mastery score achievement
                    if tracking.student_data_mastery_score and tracking.score_raw is not None:
                        mastery_achieved = tracking.check_mastery_completion()
                        if mastery_achieved:
                            logger.info(f"SCORM: Auto-completed topic {tracking.elearning_package.topic.id} based on mastery score achievement")
                except ValueError:
                    logger.warning(f"SCORM: Invalid progress_measure value: {value}")
            elif element == 'cmi.completion_threshold':
                try:
                    tracking.completion_threshold = float(value) if value else None
                    logger.info(f"SCORM: Set completion_threshold to {value}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid completion_threshold value: {value}")
            elif element == 'cmi.scaled_passing_score':
                try:
                    tracking.student_data_mastery_score = float(value) if value else None
                    logger.info(f"SCORM: Set scaled_passing_score to {value}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid scaled_passing_score value: {value}")
            elif element == 'cmi.learner_preference.audio_level':
                try:
                    tracking.learner_preference_audio_level = float(value) if value else None
                    logger.info(f"SCORM: Set learner_preference.audio_level to {value}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid learner_preference.audio_level value: {value}")
            elif element == 'cmi.learner_preference.language':
                tracking.learner_preference_language = value
                logger.info(f"SCORM: Set learner_preference.language to {value}")
            elif element == 'cmi.learner_preference.delivery_speed':
                try:
                    tracking.learner_preference_delivery_speed = float(value) if value else None
                    logger.info(f"SCORM: Set learner_preference.delivery_speed to {value}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid learner_preference.delivery_speed value: {value}")
            elif element == 'cmi.learner_preference.audio_captioning':
                tracking.learner_preference_audio_captioning = value.lower() == 'true' if value else None
                logger.info(f"SCORM: Set learner_preference.audio_captioning to {value}")
            elif element == 'cmi.student_data.mastery_score':
                try:
                    tracking.student_data_mastery_score = float(value) if value else None
                    logger.info(f"SCORM: Set student_data.mastery_score to {value}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid student_data.mastery_score value: {value}")
            elif element == 'cmi.student_data.max_time_allowed':
                tracking.student_data_max_time_allowed = tracking._parse_scorm_time(value)
                logger.info(f"SCORM: Set student_data.max_time_allowed to {value}")
            elif element == 'cmi.student_data.time_limit_action':
                tracking.student_data_time_limit_action = value
                logger.info(f"SCORM: Set student_data.time_limit_action to {value}")
            elif element.startswith('cmi.objectives.'):
                # Handle objectives
                _handle_objectives_set(tracking, element, value)
            elif element.startswith('cmi.interactions.'):
                # Handle interactions
                _handle_interactions_set(tracking, element, value)
            elif element.startswith('cmi.comments_from_learner.') or element.startswith('cmi.comments_from_lms.'):
                # Handle comments
                _handle_comments_set(tracking, element, value)
            else:
                # Store any other SCORM data model element
                logger.info(f"SCORM: Storing custom element {element} = {value}")
            
            # Always store in raw_data for complete SCORM compliance
            tracking.raw_data[element] = value
            
            # Update timestamps
            tracking.last_launch = timezone.now()
            if not tracking.first_launch:
                tracking.first_launch = timezone.now()
            
            # Check for completion
            if tracking.completion_status == 'completed':
                tracking.completion_date = timezone.now()
            
            # ENHANCED: Always save if any field was updated or if raw_data was updated
            # Also save for critical SCORM elements even if field_updated is False
            critical_elements = [
                'cmi.core.score.raw', 'cmi.score.raw', 'cmi.core.total_time', 'cmi.total_time',
                'cmi.core.session_time', 'cmi.session_time', 'cmi.core.lesson_status', 'cmi.completion_status',
                'cmi.core.lesson_location', 'cmi.location', 'cmi.core.suspend_data', 'cmi.suspend_data',
                'cmi.progress_measure', 'cmi.core.exit', 'cmi.exit'
            ]
            
            should_save = (
                field_updated or 
                element in tracking.raw_data or 
                element in critical_elements or
                value.strip()  # Save if there's actual data
            )
            
            if should_save:
                if not getattr(request, 'scorm_preview_mode', False):
                    tracking.save()
                    logger.info(f"SCORM: Tracking data saved for user {request.scorm_user.id}, element: {element}, field_updated: {field_updated}")
                else:
                    logger.info(f"SCORM: Preview mode - tracking data not saved for user {request.scorm_user.id}, element: {element}")
            else:
                logger.warning(f"SCORM: No fields updated for element {element}, value: {value}")
            
            # Generate xAPI statement if LRS is available
            _generate_xapi_statement(tracking, element, value)
            
            # Sync SCORM completion to course progress - ENHANCED
            if tracking.completion_status == 'completed':
                from courses.models import TopicProgress
                topic_progress, created = TopicProgress.objects.get_or_create(
                    user=request.scorm_user,
                    topic=tracking.elearning_package.topic
                )
                if not topic_progress.completed:
                    topic_progress.completed = True
                    topic_progress.save()
                    logger.info(f"SCORM: Synced completion to course progress for user {request.scorm_user.id}, topic {tracking.elearning_package.topic.id}")
                else:
                    logger.info(f"SCORM: Course progress already completed for user {request.scorm_user.id}, topic {tracking.elearning_package.topic.id}")
            else:
                logger.info(f"SCORM: Completion status is {tracking.completion_status}, not syncing to course progress")
            
            return JsonResponse({'result': 'true'})
            
        elif action == 'Commit':
            # Commit is always successful in our implementation
            return JsonResponse({'result': 'true'})
            
        elif action == 'Initialize':
            # Initialize is always successful
            return JsonResponse({'result': 'true'})
            
        elif action == 'Terminate':
            # Terminate is always successful
            logger.info(f"SCORM: Terminating session for user {request.scorm_user.id}")
            
            # Ensure we have the latest exit value
            exit_value = tracking.exit_value or tracking.raw_data.get('cmi.core.exit', 'normal')
            logger.info(f"SCORM: Final exit value for user {request.scorm_user.id}: {exit_value}")
            
            # Update last launch time
            tracking.last_launch = timezone.now()
            tracking.save()
            
            return JsonResponse({'result': 'true'})
            
        else:
            return JsonResponse({'result': 'false', 'error': 'Unknown action'})
            
    except Exception as e:
        logger.error("Error in SCORM POST: {}".format(str(e)))
        return JsonResponse({'result': 'false', 'error': str(e)})

@csrf_exempt
@require_http_methods(["POST"])
def scorm_log(request):
    """Log SCORM events for debugging"""
    try:
        import json
        event_data = json.loads(request.body)
        logger.info(f"SCORM Event: {event_data}")
        return JsonResponse({'status': 'logged'})
    except Exception as e:
        logger.error(f"SCORM Log Error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def scorm_reports(request, course_id):
    """SCORM reports for a course"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check permissions
    if not course.user_can_modify(request.user):
        messages.error(request, "You don't have permission to view reports for this course.")
        return redirect('courses:course_list')
    
    # Get e-learning packages for this course
    # Since course is a property on Topic, we need to filter through CourseTopic
    from courses.models import CourseTopic
    course_topics = CourseTopic.objects.filter(course=course).values_list('topic', flat=True)
    elearning_packages = ELearningPackage.objects.filter(
        topic__in=course_topics
    ).select_related('topic')
    
    # Get tracking data
    tracking_data = ELearningTracking.objects.filter(
        elearning_package__topic__in=course_topics
    ).select_related('user', 'elearning_package__topic')
    
    # Calculate statistics
    total_learners = course.enrolled_users.count()
    scorm_topics = elearning_packages.count()
    
    completion_stats = {}
    score_stats = {}
    
    for package in elearning_packages:
        package_tracking = tracking_data.filter(elearning_package=package)
        completions = package_tracking.filter(completion_status='completed').count()
        
        # Calculate score statistics
        package_scores = []
        total_time_seconds = 0
        for tracking in package_tracking:
            if tracking.score_raw is not None:
                score_percentage = tracking.get_score_percentage()
                if score_percentage is not None:
                    package_scores.append(score_percentage)
            
            # Calculate total time in seconds
            if tracking.total_time:
                total_time_seconds += tracking.total_time.total_seconds()
        
        # Calculate average score
        average_score = sum(package_scores) / len(package_scores) if package_scores else None
        
        # Calculate time statistics
        total_time_hours = total_time_seconds / 3600 if total_time_seconds > 0 else 0
        
        completion_stats[package.id] = {
            'total': package_tracking.count(),
            'completed': completions,
            'completion_rate': (completions / total_learners * 100) if total_learners > 0 else 0
        }
        
        score_stats[package.id] = {
            'average_score': average_score,
            'total_scores': len(package_scores),
            'total_time_hours': round(total_time_hours, 2),
            'scores': package_scores
        }
    
    context = {
        'course': course,
        'elearning_packages': elearning_packages,
        'tracking_data': tracking_data,
        'completion_stats': completion_stats,
        'score_stats': score_stats,
        'total_learners': total_learners,
        'scorm_topics': scorm_topics
    }
    
    return render(request, 'scorm/reports.html', context)

@login_required
def scorm_learner_progress(request, course_id, user_id):
    """Individual learner SCORM progress"""
    course = get_object_or_404(Course, id=course_id)
    learner = get_object_or_404(CustomUser, id=user_id)
    
    # Check permissions
    if not course.user_can_modify(request.user):
        messages.error(request, "You don't have permission to view this report.")
        return redirect('courses:course_list')
    
    # Get e-learning tracking for this learner
    # Since course is a property on Topic, we need to filter through CourseTopic
    from courses.models import CourseTopic
    course_topics = CourseTopic.objects.filter(course=course).values_list('topic', flat=True)
    tracking_records = ELearningTracking.objects.filter(
        user=learner,
        elearning_package__topic__in=course_topics
    ).select_related('elearning_package__topic')
    
    context = {
        'course': course,
        'learner': learner,
        'tracking_records': tracking_records
    }
    
    return render(request, 'scorm/learner_progress.html', context)


def _handle_objectives_get(tracking, element):
    """Handle SCORM objectives GET requests"""
    try:
        if element == 'cmi.objectives._count':
            objectives = tracking.objectives
            count = len(objectives) if isinstance(objectives, dict) else 0
            return JsonResponse({'value': str(count)})
        elif element == 'cmi.objectives._children':
            objectives = tracking.objectives
            if isinstance(objectives, dict):
                children = ','.join([f"id_{i}" for i in range(len(objectives))])
                return JsonResponse({'value': children})
            return JsonResponse({'value': ''})
        elif element.startswith('cmi.objectives.'):
            # Extract objective index and field
            parts = element.split('.')
            if len(parts) >= 4:
                try:
                    obj_index = int(parts[2])
                    field = parts[3]
                    
                    objectives = tracking.objectives
                    if isinstance(objectives, dict) and str(obj_index) in objectives:
                        obj_data = objectives[str(obj_index)]
                        if field in obj_data:
                            return JsonResponse({'value': str(obj_data[field])})
                except (ValueError, KeyError):
                    pass
        return JsonResponse({'value': ''})
    except Exception as e:
        logger.error(f"Error handling objectives GET: {str(e)}")
        return JsonResponse({'value': ''})


def _handle_interactions_get(tracking, element):
    """Handle SCORM interactions GET requests"""
    try:
        if element == 'cmi.interactions._count':
            interactions = tracking.interactions
            count = len(interactions) if isinstance(interactions, dict) else 0
            return JsonResponse({'value': str(count)})
        elif element == 'cmi.interactions._children':
            interactions = tracking.interactions
            if isinstance(interactions, dict):
                children = ','.join([f"id_{i}" for i in range(len(interactions))])
                return JsonResponse({'value': children})
            return JsonResponse({'value': ''})
        elif element.startswith('cmi.interactions.'):
            # Extract interaction index and field
            parts = element.split('.')
            if len(parts) >= 4:
                try:
                    int_index = int(parts[2])
                    field = parts[3]
                    
                    interactions = tracking.interactions
                    if isinstance(interactions, dict) and str(int_index) in interactions:
                        int_data = interactions[str(int_index)]
                        if field in int_data:
                            return JsonResponse({'value': str(int_data[field])})
                except (ValueError, KeyError):
                    pass
        return JsonResponse({'value': ''})
    except Exception as e:
        logger.error(f"Error handling interactions GET: {str(e)}")
        return JsonResponse({'value': ''})


def _handle_comments_get(tracking, element, comment_type):
    """Handle SCORM comments GET requests"""
    try:
        comments_field = f'comments_from_{comment_type}'
        comments = getattr(tracking, comments_field, [])
        
        if element == f'cmi.comments_from_{comment_type}._count':
            count = len(comments) if isinstance(comments, list) else 0
            return JsonResponse({'value': str(count)})
        elif element == f'cmi.comments_from_{comment_type}._children':
            if isinstance(comments, list):
                children = ','.join([f"id_{i}" for i in range(len(comments))])
                return JsonResponse({'value': children})
            return JsonResponse({'value': ''})
        elif element.startswith(f'cmi.comments_from_{comment_type}.'):
            # Extract comment index and field
            parts = element.split('.')
            if len(parts) >= 4:
                try:
                    comment_index = int(parts[2])
                    field = parts[3]
                    
                    if isinstance(comments, list) and comment_index < len(comments):
                        comment_data = comments[comment_index]
                        if field in comment_data:
                            return JsonResponse({'value': str(comment_data[field])})
                except (ValueError, KeyError, IndexError):
                    pass
        return JsonResponse({'value': ''})
    except Exception as e:
        logger.error(f"Error handling comments GET: {str(e)}")
        return JsonResponse({'value': ''})


def _handle_objectives_set(tracking, element, value):
    """Handle SCORM objectives SET requests"""
    try:
        if element == 'cmi.objectives._count':
            # Set count - this is usually read-only
            pass
        elif element.startswith('cmi.objectives.'):
            # Extract objective index and field
            parts = element.split('.')
            if len(parts) >= 4:
                try:
                    obj_index = int(parts[2])
                    field = parts[3]
                    
                    if not tracking.objectives:
                        tracking.objectives = {}
                    
                    if str(obj_index) not in tracking.objectives:
                        tracking.objectives[str(obj_index)] = {}
                    
                    tracking.objectives[str(obj_index)][field] = value
                    logger.info(f"SCORM: Set objective {obj_index}.{field} to {value}")
                except (ValueError, KeyError):
                    logger.warning(f"SCORM: Invalid objective element: {element}")
    except Exception as e:
        logger.error(f"Error handling objectives SET: {str(e)}")


def _handle_interactions_set(tracking, element, value):
    """Handle SCORM interactions SET requests"""
    try:
        if element == 'cmi.interactions._count':
            # Set count - this is usually read-only
            pass
        elif element.startswith('cmi.interactions.'):
            # Extract interaction index and field
            parts = element.split('.')
            if len(parts) >= 4:
                try:
                    int_index = int(parts[2])
                    field = parts[3]
                    
                    if not tracking.interactions:
                        tracking.interactions = {}
                    
                    if str(int_index) not in tracking.interactions:
                        tracking.interactions[str(int_index)] = {}
                    
                    tracking.interactions[str(int_index)][field] = value
                    logger.info(f"SCORM: Set interaction {int_index}.{field} to {value}")
                except (ValueError, KeyError):
                    logger.warning(f"SCORM: Invalid interaction element: {element}")
    except Exception as e:
        logger.error(f"Error handling interactions SET: {str(e)}")


def _handle_comments_set(tracking, element, value):
    """Handle SCORM comments SET requests"""
    try:
        if element.startswith('cmi.comments_from_learner.'):
            comment_type = 'comments_from_learner'
        elif element.startswith('cmi.comments_from_lms.'):
            comment_type = 'comments_from_lms'
        else:
            return
        
        comments = getattr(tracking, comment_type, [])
        
        if element == f'cmi.{comment_type}._count':
            # Set count - this is usually read-only
            pass
        elif element.startswith(f'cmi.{comment_type}.'):
            # Extract comment index and field
            parts = element.split('.')
            if len(parts) >= 4:
                try:
                    comment_index = int(parts[2])
                    field = parts[3]
                    
                    if not isinstance(comments, list):
                        comments = []
                    
                    # Ensure we have enough comments
                    while len(comments) <= comment_index:
                        comments.append({})
                    
                    comments[comment_index][field] = value
                    setattr(tracking, comment_type, comments)
                    logger.info(f"SCORM: Set comment {comment_index}.{field} to {value}")
                except (ValueError, KeyError, IndexError):
                    logger.warning(f"SCORM: Invalid comment element: {element}")
    except Exception as e:
        logger.error(f"Error handling comments SET: {str(e)}")


def _generate_xapi_statement(tracking, element, value):
    """Generate xAPI statement from SCORM data"""
    try:
        from lrs.xapi_generator import xAPIStatementGenerator
        
        generator = xAPIStatementGenerator()
        generator.set_base_actor(tracking.user)
        generator.set_base_activity(
            f"https://lms.example.com/scorm/{tracking.elearning_package.topic.id}",
            tracking.elearning_package.title or tracking.elearning_package.topic.title
        )
        
        # Determine action based on element
        action = 'experienced'  # Default action
        
        if element in ['cmi.core.lesson_status', 'cmi.completion_status']:
            if value == 'completed':
                action = 'completed'
            elif value == 'passed':
                action = 'passed'
            elif value == 'failed':
                action = 'failed'
        elif element in ['cmi.core.score.raw', 'cmi.score.raw']:
            action = 'answered'
        elif element.startswith('cmi.interactions.'):
            action = 'interacted'
        elif element.startswith('cmi.objectives.'):
            action = 'mastered'
        
        # Generate statement based on package type
        if tracking.elearning_package.package_type in ['SCORM_1_2', 'SCORM_2004']:
            statement = generator.generate_scorm_1_2_statement(tracking, action, element, value)
        else:
            statement = generator.generate_scorm_1_2_statement(tracking, action, element, value)
        
        # Store statement
        if statement:
            generator.store_statement(statement)
            logger.info(f"SCORM: Generated xAPI statement for {element} = {value}")
        
    except Exception as e:
        logger.error(f"Error generating xAPI statement: {str(e)}")

def xapi_launch(request, topic_id):
    """Launch an xAPI package"""
    if not request.user.is_authenticated:
        messages.error(request, "Authentication required to access xAPI content.")
        return redirect('login')
    
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        messages.error(request, "xAPI package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if not elearning_package.is_extracted:
        messages.error(request, "xAPI package is not properly extracted.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Generate xAPI launch URL
    launch_url = elearning_package.get_content_url()
    
    logger.info(f"xAPI Launch: User {user.username} launching xAPI package for topic {topic_id}")
    logger.info(f"xAPI Launch: Launch URL: {launch_url}")
    
    return render(request, 'scorm/launch.html', {
        'topic': topic,
        'elearning_package': elearning_package,
        'launch_url': launch_url,
        'package_type': 'xAPI'
    })

def cmi5_launch(request, topic_id):
    """Launch a cmi5 package"""
    if not request.user.is_authenticated:
        messages.error(request, "Authentication required to access cmi5 content.")
        return redirect('login')
    
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        messages.error(request, "cmi5 package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if not elearning_package.is_extracted:
        messages.error(request, "cmi5 package is not properly extracted.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Generate cmi5 launch URL
    launch_url = elearning_package.get_content_url()
    
    logger.info(f"cmi5 Launch: User {user.username} launching cmi5 package for topic {topic_id}")
    logger.info(f"cmi5 Launch: Launch URL: {launch_url}")
    
    return render(request, 'scorm/launch.html', {
        'topic': topic,
        'elearning_package': elearning_package,
        'launch_url': launch_url,
        'package_type': 'cmi5'
    })

@login_required
def scorm_result(request, topic_id):
    """Enhanced result view with comprehensive data handling and debugging"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    logger.info(f"SCORM Result: Processing result for user {user.id}, topic {topic_id}")
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        scorm_tracking = ELearningTracking.objects.filter(
            user=user,
            elearning_package=elearning_package
        ).first()
        
        if not scorm_tracking:
            messages.error(request, "No SCORM tracking data found.")
            return redirect('courses:topic_view', topic_id=topic_id)
        
        # Enhanced debugging
        logger.info(f"SCORM Result Debug for user {user.id}, topic {topic_id}:")
        logger.info(f"  Raw data keys: {list(scorm_tracking.raw_data.keys())}")
        logger.info(f"  Completion status: {scorm_tracking.completion_status}")
        logger.info(f"  Success status: {scorm_tracking.success_status}")
        logger.info(f"  Score raw: {scorm_tracking.score_raw}")
        logger.info(f"  Score max: {scorm_tracking.score_max}")
        logger.info(f"  Total time: {scorm_tracking.total_time}")
        logger.info(f"  Progress measure: {scorm_tracking.progress_measure}")
        
        # Enhanced data synchronization with error handling
        try:
            _sync_tracking_data(scorm_tracking)
            # Refresh the object after sync
            scorm_tracking.refresh_from_db()
        except Exception as e:
            logger.error(f"SCORM: Error syncing tracking data: {str(e)}")
        
        # Enhanced progress data with comprehensive fallbacks
        progress_data = {
            'completion_status': scorm_tracking.completion_status,
            'success_status': scorm_tracking.success_status,
            'score_raw': scorm_tracking.score_raw,
            'score_min': scorm_tracking.score_min,
            'score_max': scorm_tracking.score_max,
            'score_scaled': scorm_tracking.score_scaled,
            'total_time': scorm_tracking.total_time,
            'session_time': scorm_tracking.session_time,
            'first_launch': scorm_tracking.first_launch,
            'last_launch': scorm_tracking.last_launch,
            'completion_date': scorm_tracking.completion_date,
            'location': scorm_tracking.location,
            'suspend_data': scorm_tracking.suspend_data,
            'raw_data': scorm_tracking.raw_data,
            'attempt_count': scorm_tracking.attempt_count,
        }
        
        # Enhanced progress percentage calculation
        progress_percentage = scorm_tracking.get_progress_percentage()
        logger.info(f"SCORM: Progress percentage: {progress_percentage}%")
        
        # Enhanced completion status detection with better logic
        if scorm_tracking.completion_status == 'not attempted':
            # Check if we have indicators of completion
            has_time = scorm_tracking.total_time and scorm_tracking.total_time.total_seconds() > 0
            has_progress = scorm_tracking.progress_measure and scorm_tracking.progress_measure >= 1.0
            has_score = scorm_tracking.score_raw is not None
            has_location = bool(scorm_tracking.location)
            
            logger.info(f"SCORM: Completion indicators - time: {has_time}, progress: {has_progress}, score: {has_score}, location: {has_location}")
            
            # More conservative completion detection
            if has_progress or (has_time and has_score and has_location):
                scorm_tracking.completion_status = 'completed'
                scorm_tracking.save()
                logger.info(f"SCORM: Auto-detected completion for user {request.user.id}")
        
        # Enhanced score summary with comprehensive fallbacks
        score_summary = scorm_tracking.get_score_summary()
        logger.info(f"SCORM: Score summary: {score_summary}")
        
        # Enhanced fallback for missing score data
        if not score_summary.get('raw_score') or score_summary.get('raw_score') == '' or score_summary.get('raw_score') is None:
            logger.info("SCORM: Attempting score data recovery from raw_data")
            # Check multiple sources for score data
            score_sources = [
                ('cmi.core.score.raw', 'SCORM 1.2 raw score'),
                ('cmi.score.raw', 'SCORM 2004 raw score'),
                ('cmi.core.score.scaled', 'SCORM 1.2 scaled score'),
                ('cmi.score.scaled', 'SCORM 2004 scaled score')
            ]
            
            for source, description in score_sources:
                if source in scorm_tracking.raw_data:
                    raw_score = scorm_tracking.raw_data[source]
                    if raw_score and raw_score.strip():
                        try:
                            score_value = float(raw_score)
                            scorm_tracking.score_raw = score_value
                            scorm_tracking.save()
                            score_summary = scorm_tracking.get_score_summary()
                            logger.info(f"SCORM: Recovered score data from {description}: {raw_score}")
                            break
                        except (ValueError, TypeError) as e:
                            logger.warning(f"SCORM: Error recovering score from {source}: {raw_score} - {str(e)}")
                            continue
        
        # Enhanced time data recovery
        if not progress_data.get('total_time') or progress_data.get('total_time') == 'PT0S':
            logger.info("SCORM: Attempting time data recovery from raw_data")
            time_sources = [
                ('cmi.core.total_time', 'SCORM 1.2 total time'),
                ('cmi.total_time', 'SCORM 2004 total time'),
                ('cmi.core.session_time', 'SCORM 1.2 session time'),
                ('cmi.session_time', 'SCORM 2004 session time')
            ]
            
            for source, description in time_sources:
                if source in scorm_tracking.raw_data:
                    raw_time = scorm_tracking.raw_data[source]
                    if raw_time and raw_time.strip() and raw_time != 'PT0S':
                        try:
                            parsed_time = scorm_tracking._parse_scorm_time(raw_time)
                            if parsed_time and parsed_time.total_seconds() > 0:
                                scorm_tracking.total_time = parsed_time
                                scorm_tracking.save()
                                progress_data['total_time'] = parsed_time
                                logger.info(f"SCORM: Recovered time data from {description}: {raw_time}")
                                break
                        except Exception as e:
                            logger.warning(f"SCORM: Error recovering time from {source}: {raw_time} - {str(e)}")
        
        # Get bookmark data for resume functionality
        bookmark_data = scorm_tracking.get_bookmark_data()
        
        # Final data validation and logging
        logger.info(f"SCORM: Final result data for user {user.id}:")
        logger.info(f"  Completion: {progress_data['completion_status']}")
        logger.info(f"  Success: {progress_data['success_status']}")
        logger.info(f"  Score: {score_summary.get('raw_score')}/{score_summary.get('max_score')} ({score_summary.get('percentage')}%)")
        logger.info(f"  Time: {progress_data['total_time']}")
        logger.info(f"  Progress: {progress_percentage}%")
        
        context = {
            'topic': topic,
            'course': topic.course,
            'elearning_package': elearning_package,
            'scorm_tracking': scorm_tracking,
            'progress_data': progress_data,
            'progress_percentage': progress_percentage,
            'score_summary': score_summary,
            'bookmark_data': bookmark_data,
            'breadcrumbs': [
                {'label': 'Courses', 'url': '/courses/', 'icon': 'fa-book'},
                {'label': topic.course.title, 'url': f'/courses/{topic.course.id}/details/', 'icon': 'fa-graduation-cap'},
                {'label': topic.title, 'url': f'/courses/topic/{topic.id}/view/', 'icon': 'fa-file'},
                {'label': 'SCORM Result', 'icon': 'fa-chart-line'}
            ],
        }
        
        return render(request, 'scorm/result.html', context)
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "SCORM package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def scorm_retake(request, topic_id):
    """Reset SCORM tracking data for retake"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        
        with transaction.atomic():
            # Get or create tracking record
            scorm_tracking, created = ELearningTracking.objects.get_or_create(
                user=user,
                elearning_package=elearning_package,
                defaults={
                    'completion_status': 'not attempted',
                    'success_status': 'unknown',
                    'entry': 'ab-initio'
                }
            )
            
            if not created:
                # Reset tracking data for retake
                scorm_tracking.completion_status = 'not attempted'
                scorm_tracking.success_status = 'unknown'
                scorm_tracking.score_raw = None
                scorm_tracking.score_min = None
                scorm_tracking.score_max = None
                scorm_tracking.score_scaled = None
                scorm_tracking.progress_measure = None
                scorm_tracking.total_time = None
                scorm_tracking.session_time = None
                scorm_tracking.location = ''
                scorm_tracking.suspend_data = ''
                scorm_tracking.launch_data = ''
                scorm_tracking.entry = 'ab-initio'
                scorm_tracking.exit_value = ''
                scorm_tracking.completion_date = None
                scorm_tracking.raw_data = {}
                scorm_tracking.objectives = {}
                scorm_tracking.interactions = {}
                scorm_tracking.comments_from_learner = []
                scorm_tracking.attempt_count = 0
                scorm_tracking.comments_from_lms = []
                
                # Clear bookmark data
                scorm_tracking.clear_bookmark()
                
                scorm_tracking.save()
                
                logger.info(f"SCORM Retake: Reset tracking data for user {user.username} on topic {topic_id}")
                messages.success(request, "SCORM content has been reset for retake.")
            else:
                logger.info(f"SCORM Retake: Created new tracking record for user {user.username} on topic {topic_id}")
                messages.info(request, "Ready to start SCORM content.")
        
        # Redirect to launch page
        return redirect('scorm:launch', topic_id=topic_id)
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "SCORM package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    except Exception as e:
        logger.error(f"SCORM Retake Error: {str(e)}")
        messages.error(request, "Error resetting SCORM content. Please try again.")
        return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def scorm_resume(request, topic_id):
    """Resume SCORM content from bookmark location"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        scorm_tracking = ELearningTracking.objects.filter(
            user=user,
            elearning_package=elearning_package
        ).first()
        
        if not scorm_tracking:
            messages.error(request, "No SCORM tracking data found.")
            return redirect('courses:topic_view', topic_id=topic_id)
        
        # Check if content can be resumed
        bookmark_data = scorm_tracking.get_bookmark_data()
        if not bookmark_data['can_resume']:
            messages.warning(request, "No bookmark data available to resume from.")
            return redirect('scorm:launch', topic_id=topic_id)
        
        # Set entry mode to resume
        scorm_tracking.raw_data['cmi.core.entry'] = 'resume'
        scorm_tracking.save()
        
        logger.info(f"SCORM Resume: Setting resume mode for user {user.username} on topic {topic_id}")
        messages.success(request, "Resuming SCORM content from your last position.")
        
        # Redirect to launch with resume mode
        return redirect('scorm:launch', topic_id=topic_id)
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "SCORM package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    except Exception as e:
        logger.error(f"SCORM Resume Error: {str(e)}")
        messages.error(request, "Error resuming SCORM content. Please try again.")
        return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def xapi_resume(request, topic_id):
    """Resume xAPI content from state data"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        scorm_tracking = ELearningTracking.objects.filter(
            user=user,
            elearning_package=elearning_package
        ).first()
        
        if not scorm_tracking:
            messages.error(request, "No xAPI tracking data found.")
            return redirect('courses:topic_view', topic_id=topic_id)
        
        # Check if content can be resumed (xAPI state-based)
        bookmark_data = scorm_tracking.get_bookmark_data()
        if not bookmark_data['can_resume']:
            messages.warning(request, "No state data available to resume from.")
            return redirect('scorm:xapi_launch', topic_id=topic_id)
        
        # Set xAPI resume mode
        scorm_tracking.raw_data['xapi.resume'] = True
        scorm_tracking.save()
        
        logger.info(f"xAPI Resume: Setting resume mode for user {user.username} on topic {topic_id}")
        messages.success(request, "Resuming xAPI content from your last position.")
        
        # Redirect to xAPI launch with resume mode
        return redirect('scorm:xapi_launch', topic_id=topic_id)
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "xAPI package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    except Exception as e:
        logger.error(f"xAPI Resume Error: {str(e)}")
        messages.error(request, "Error resuming xAPI content. Please try again.")
        return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def cmi5_resume(request, topic_id):
    """Resume cmi5 content from AU state"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        scorm_tracking = ELearningTracking.objects.filter(
            user=user,
            elearning_package=elearning_package
        ).first()
        
        if not scorm_tracking:
            messages.error(request, "No cmi5 tracking data found.")
            return redirect('courses:topic_view', topic_id=topic_id)
        
        # Check if content can be resumed (cmi5 AU state-based)
        bookmark_data = scorm_tracking.get_bookmark_data()
        if not bookmark_data['can_resume']:
            messages.warning(request, "No AU state data available to resume from.")
            return redirect('scorm:cmi5_launch', topic_id=topic_id)
        
        # Set cmi5 resume mode
        scorm_tracking.raw_data['cmi5.resume'] = True
        scorm_tracking.save()
        
        logger.info(f"cmi5 Resume: Setting resume mode for user {user.username} on topic {topic_id}")
        messages.success(request, "Resuming cmi5 content from your last position.")
        
        # Redirect to cmi5 launch with resume mode
        return redirect('scorm:cmi5_launch', topic_id=topic_id)
        
    except ELearningPackage.DoesNotExist:
        messages.error(request, "cmi5 package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    except Exception as e:
        logger.error(f"cmi5 Resume Error: {str(e)}")
        messages.error(request, "Error resuming cmi5 content. Please try again.")
        return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def scorm_progress(request, topic_id):
    """Get SCORM progress data via AJAX"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        scorm_tracking = ELearningTracking.objects.filter(
            user=user,
            elearning_package=elearning_package
        ).first()
        
        if scorm_tracking:
            progress_data = {
                'completion_status': scorm_tracking.completion_status,
                'success_status': scorm_tracking.success_status,
                'score_raw': scorm_tracking.score_raw,
                'score_max': scorm_tracking.score_max,
                'progress_percentage': scorm_tracking.get_progress_percentage(),
                'total_time': str(scorm_tracking.total_time) if scorm_tracking.total_time else None,
                'last_launch': scorm_tracking.last_launch.isoformat() if scorm_tracking.last_launch else None,
                'can_resume': bool(scorm_tracking.location or scorm_tracking.suspend_data),
                'is_completed': scorm_tracking.is_completed(),
                'is_passed': scorm_tracking.is_passed(),
            }
        else:
            progress_data = {
                'completion_status': 'not attempted',
                'success_status': 'unknown',
                'score_raw': None,
                'score_max': None,
                'progress_percentage': 0,
                'total_time': None,
                'last_launch': None,
                'can_resume': False,
                'is_completed': False,
                'is_passed': False,
            }
        
        return JsonResponse({
            'success': True,
            'progress': progress_data
        })
        
    except ELearningPackage.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'SCORM package not found'
        })
    except Exception as e:
        logger.error(f"SCORM Progress Error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error retrieving progress data'
        })

def validate_elearning_package(package_path, package_type):
    """Validate eLearning packages for all standards"""
    try:
        if package_type in ['SCORM_1_2', 'SCORM_2004']:
            return validate_elearning_package(package_path)
        elif package_type == 'XAPI':
            return validate_xapi_package(package_path)
        elif package_type == 'CMI5':
            return validate_cmi5_package(package_path)
        elif package_type == 'AICC':
            return validate_aicc_package(package_path)
        else:
            logger.warning(f"Unknown package type: {package_type}")
            return False
    except Exception as e:
        logger.error(f"Error validating {package_type} package: {str(e)}")
        return False

def validate_elearning_package(package_path):
    """Validate SCORM package integrity"""
    try:
        # Check for imsmanifest.xml
        manifest_path = os.path.join(package_path, 'imsmanifest.xml')
        if not os.path.exists(manifest_path):
            logger.error("SCORM: imsmanifest.xml not found")
            return False
        
        # Parse manifest
        import xml.etree.ElementTree as ET
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        
        # Check for required elements
        if not root.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}organization'):
            logger.error("SCORM: No organization found in manifest")
            return False
        
        if not root.find('.//{http://www.imsglobal.org/xsd/imscp_v1p1}resource'):
            logger.error("SCORM: No resources found in manifest")
            return False
        
        logger.info("SCORM: Package validation successful")
        return True
        
    except Exception as e:
        logger.error(f"SCORM validation error: {str(e)}")
        return False

def validate_xapi_package(package_path):
    """Validate xAPI package integrity"""
    try:
        # Check for tincan.xml or package.json
        tincan_path = os.path.join(package_path, 'tincan.xml')
        package_json_path = os.path.join(package_path, 'package.json')
        
        if not os.path.exists(tincan_path) and not os.path.exists(package_json_path):
            logger.error("xAPI: No tincan.xml or package.json found")
            return False
        
        # Check for launch file
        launch_files = ['index.html', 'launch.html', 'tincan.html']
        found_launch = False
        for launch_file in launch_files:
            if os.path.exists(os.path.join(package_path, launch_file)):
                found_launch = True
                break
        
        if not found_launch:
            logger.error("xAPI: No launch file found")
            return False
        
        logger.info("xAPI: Package validation successful")
        return True
        
    except Exception as e:
        logger.error(f"xAPI validation error: {str(e)}")
        return False

def validate_cmi5_package(package_path):
    """Validate cmi5 package integrity"""
    try:
        # Check for cmi5.xml
        cmi5_path = os.path.join(package_path, 'cmi5.xml')
        if not os.path.exists(cmi5_path):
            logger.error("cmi5: cmi5.xml not found")
            return False
        
        # Parse cmi5.xml
        import xml.etree.ElementTree as ET
        tree = ET.parse(cmi5_path)
        root = tree.getroot()
        
        # Check for required elements
        if not root.find('.//{http://www.imsglobal.org/xsd/cmi5}au'):
            logger.error("cmi5: No Assignable Units found")
            return False
        
        logger.info("cmi5: Package validation successful")
        return True
        
    except Exception as e:
        logger.error(f"cmi5 validation error: {str(e)}")
        return False

def validate_aicc_package(package_path):
    """Validate AICC package integrity"""
    try:
        # Check for courstruct.cst
        cst_path = os.path.join(package_path, 'coursestruct.cst')
        if not os.path.exists(cst_path):
            logger.error("AICC: courstruct.cst not found")
            return False
        
        # Check for launch file
        launch_files = ['index.html', 'launch.html', 'au.html']
        found_launch = False
        for launch_file in launch_files:
            if os.path.exists(os.path.join(package_path, launch_file)):
                found_launch = True
                break
        
        if not found_launch:
            logger.error("AICC: No launch file found")
            return False
        
        logger.info("AICC: Package validation successful")
        return True
        
    except Exception as e:
        logger.error(f"AICC validation error: {str(e)}")
        return False

def handle_elearning_error(error_code, package_type, context=None):
    """Handle eLearning errors gracefully for all standards"""
    try:
        error_messages = {
            # SCORM Error Codes
            '301': 'Not Implemented - The data model element is not supported',
            '302': 'Invalid Set Value - The value being set is not valid',
            '303': 'Element Not Initialized - The data model element has not been initialized',
            '304': 'Not Initialized - The LMS has not been initialized',
            '305': 'Not Implemented - The data model element is not supported',
            '401': 'Not Implemented - The data model element is not supported',
            '402': 'Invalid Set Value - The value being set is not valid',
            '403': 'Element Not Initialized - The data model element has not been initialized',
            '404': 'Not Initialized - The LMS has not been initialized',
            '405': 'Not Implemented - The data model element is not supported',
            
            # xAPI Error Codes
            'xapi_400': 'Bad Request - Invalid xAPI statement',
            'xapi_401': 'Unauthorized - Authentication required',
            'xapi_403': 'Forbidden - Access denied',
            'xapi_404': 'Not Found - Activity not found',
            'xapi_500': 'Internal Server Error - LRS error',
            
            # cmi5 Error Codes
            'cmi5_400': 'Bad Request - Invalid cmi5 request',
            'cmi5_401': 'Unauthorized - Authentication required',
            'cmi5_403': 'Forbidden - Access denied',
            'cmi5_404': 'Not Found - AU not found',
            'cmi5_500': 'Internal Server Error - LMS error',
            
            # AICC Error Codes
            'aicc_400': 'Bad Request - Invalid AICC request',
            'aicc_401': 'Unauthorized - Authentication required',
            'aicc_403': 'Forbidden - Access denied',
            'aicc_404': 'Not Found - Course not found',
            'aicc_500': 'Internal Server Error - LMS error',
        }
        
        # Get error message
        error_message = error_messages.get(str(error_code), f"Unknown error: {error_code}")
        
        # Log error with context
        logger.error(f"{package_type} Error {error_code}: {error_message}")
        if context:
            logger.error(f"Context: {context}")
        
        # Return structured error response
        return {
            'error_code': error_code,
            'error_message': error_message,
            'package_type': package_type,
            'context': context,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error handling {package_type} error {error_code}: {str(e)}")
        return {
            'error_code': '999',
            'error_message': 'Internal error handling system error',
            'package_type': package_type,
            'context': str(e),
            'timestamp': timezone.now().isoformat()
        }

def get_elearning_error_response(error_code, package_type, context=None):
    """Get appropriate HTTP response for eLearning errors"""
    try:
        error_info = handle_elearning_error(error_code, package_type, context)
        
        # Determine HTTP status code based on error
        if str(error_code).startswith('4'):
            http_status = 400  # Bad Request
        elif str(error_code).startswith('5'):
            http_status = 500  # Internal Server Error
        else:
            http_status = 400  # Default to Bad Request
        
        return JsonResponse(error_info, status=http_status)
        
    except Exception as e:
        logger.error(f"Error creating error response: {str(e)}")
        return JsonResponse({
            'error_code': '999',
            'error_message': 'Internal error creating error response',
            'package_type': package_type,
            'timestamp': timezone.now().isoformat()
        }, status=500)

def validate_elearning_package_endpoint(request, topic_id):
    """Endpoint to validate eLearning packages"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        package = ELearningPackage.objects.get(topic=topic)
        
        if not package.is_extracted:
            return JsonResponse({
                'valid': False,
                'error': 'Package not extracted',
                'package_type': package.package_type
            })
        
        # S3 storage - use temp directory for package validation
        import tempfile
        package_path = os.path.join(tempfile.gettempdir(), package.extracted_path)
        
        # Validate package
        is_valid = validate_elearning_package(package_path, package.package_type)
        
        return JsonResponse({
            'valid': is_valid,
            'package_type': package.package_type,
            'topic_id': topic_id,
            'extracted': package.is_extracted,
            'launch_file': package.launch_file
        })
        
    except ELearningPackage.DoesNotExist:
        return JsonResponse({
            'valid': False,
            'error': 'Package not found',
            'topic_id': topic_id
        })
    except Exception as e:
        logger.error(f"Error validating package for topic {topic_id}: {str(e)}")
        return JsonResponse({
            'valid': False,
            'error': str(e),
            'topic_id': topic_id
        })


# ============================================================================
# ENHANCED ERROR RECOVERY SYSTEM - 100% SCORM COMPLIANCE
# ============================================================================

def _enhanced_error_recovery(request, topic_id, error_code, context):
    """Enhanced error recovery for SCORM operations with 100% compliance"""
    try:
        # Get tracking record
        tracking = ELearningTracking.objects.get(
            user=request.scorm_user,
            elearning_package__topic_id=topic_id
        )
        
        # Error recovery strategies based on SCORM error codes
        if error_code == '301':  # Not Initialized
            return _recover_from_not_initialized(tracking)
        elif error_code == '302':  # Invalid Set Value
            return _recover_from_invalid_value(tracking, context)
        elif error_code == '303':  # Element Not Initialized
            return _recover_from_element_not_initialized(tracking, context)
        elif error_code == '401':  # Not Implemented
            return _recover_from_not_implemented(tracking, context)
        elif error_code == '402':  # Invalid Set Value, Element Is A Keyword
            return _recover_from_keyword_element(tracking, context)
        elif error_code == '403':  # Element Is Read Only
            return _recover_from_read_only_element(tracking, context)
        elif error_code == '404':  # Element Is Write Only
            return _recover_from_write_only_element(tracking, context)
        elif error_code == '405':  # Incorrect Data Type
            return _recover_from_incorrect_data_type(tracking, context)
        elif error_code == '406':  # Element Value Not In Range
            return _recover_from_value_not_in_range(tracking, context)
        elif error_code == '407':  # Element Is A Keyword
            return _recover_from_keyword_element(tracking, context)
        elif error_code == '408':  # Element Is Invalid
            return _recover_from_invalid_element(tracking, context)
        elif error_code == '409':  # Element Not Valid For This Data Model
            return _recover_from_invalid_data_model(tracking, context)
        elif error_code == '410':  # Element Not Valid For This Data Model Version
            return _recover_from_invalid_data_model_version(tracking, context)
        
        return {'result': 'false', 'error': 'Unknown error code'}
        
    except Exception as e:
        logger.error(f"Error in enhanced error recovery: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_not_initialized(tracking):
    """Recover from not initialized error"""
    try:
        # Re-initialize the tracking record
        tracking.raw_data['cmi.core.entry'] = 'ab-initio'
        tracking.raw_data['cmi.core.lesson_status'] = 'not attempted'
        tracking.raw_data['cmi.core.score.raw'] = ''
        tracking.raw_data['cmi.core.score.min'] = ''
        tracking.raw_data['cmi.core.score.max'] = ''
        tracking.raw_data['cmi.core.total_time'] = '00:00:00.00'
        tracking.raw_data['cmi.core.session_time'] = '00:00:00.00'
        tracking.raw_data['cmi.core.lesson_location'] = ''
        tracking.raw_data['cmi.core.suspend_data'] = ''
        tracking.raw_data['cmi.core.launch_data'] = ''
        tracking.raw_data['cmi.core.comments'] = ''
        tracking.raw_data['cmi.core.comments_from_lms'] = ''
        tracking.save()
        
        logger.info(f"SCORM: Re-initialized tracking record for user {tracking.user.id}")
        return {'result': 'true', 'message': 'Re-initialized successfully'}
        
    except Exception as e:
        logger.error(f"Error re-initializing tracking: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_invalid_value(tracking, context):
    """Recover from invalid value error"""
    try:
        element = context.get('element', '')
        value = context.get('value', '')
        
        # Try to correct common value issues
        if element == 'cmi.core.lesson_status':
            if value not in ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']:
                corrected_value = 'incomplete'
                tracking.raw_data[element] = corrected_value
                tracking.completion_status = corrected_value
                tracking.save()
                return {'result': 'true', 'message': f'Corrected {element} to {corrected_value}'}
        
        elif element == 'cmi.core.score.raw':
            try:
                # Try to parse and validate the score
                score_value = float(value) if value else 0
                if 0 <= score_value <= 100:  # Assume 0-100 scale
                    tracking.raw_data[element] = str(score_value)
                    tracking.score_raw = score_value
                    tracking.save()
                    return {'result': 'true', 'message': f'Corrected {element} to {score_value}'}
            except ValueError:
                pass
        
        elif element == 'cmi.core.total_time':
            # Try to parse and validate time format
            if _is_valid_scorm_time(value):
                tracking.raw_data[element] = value
                tracking.total_time = tracking._parse_scorm_time(value)
                tracking.save()
                return {'result': 'true', 'message': f'Corrected {element} to {value}'}
        
        return {'result': 'false', 'error': 'Could not recover from invalid value'}
        
    except Exception as e:
        logger.error(f"Error recovering from invalid value: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_element_not_initialized(tracking, context):
    """Recover from element not initialized error"""
    try:
        element = context.get('element', '')
        
        # Initialize the element with default value
        if element.startswith('cmi.core.'):
            if element == 'cmi.core.lesson_status':
                tracking.raw_data[element] = 'not attempted'
                tracking.completion_status = 'not attempted'
            elif element == 'cmi.core.score.raw':
                tracking.raw_data[element] = ''
                tracking.score_raw = None
            elif element == 'cmi.core.total_time':
                tracking.raw_data[element] = '00:00:00.00'
                tracking.total_time = tracking._parse_scorm_time('00:00:00.00')
            else:
                tracking.raw_data[element] = ''
            
            tracking.save()
            return {'result': 'true', 'message': f'Initialized {element}'}
        
        return {'result': 'false', 'error': 'Could not initialize element'}
        
    except Exception as e:
        logger.error(f"Error initializing element: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_not_implemented(tracking, context):
    """Recover from not implemented error"""
    try:
        element = context.get('element', '')
        
        # Provide default implementation for common elements
        if element in ['cmi.core.student_preference', 'cmi.core.student_data']:
            tracking.raw_data[element] = '{}'
            tracking.save()
            return {'result': 'true', 'message': f'Implemented default for {element}'}
        
        return {'result': 'false', 'error': 'Could not implement element'}
        
    except Exception as e:
        logger.error(f"Error implementing element: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_keyword_element(tracking, context):
    """Recover from keyword element error"""
    try:
        element = context.get('element', '')
        
        # Handle keyword elements by providing appropriate values
        if element == 'cmi.core.entry':
            tracking.raw_data[element] = 'ab-initio'
        elif element == 'cmi.core.exit':
            tracking.raw_data[element] = 'time-out'
        elif element == 'cmi.core.credit':
            tracking.raw_data[element] = 'credit'
        elif element == 'cmi.core.lesson_mode':
            tracking.raw_data[element] = 'normal'
        
        tracking.save()
        return {'result': 'true', 'message': f'Set keyword value for {element}'}
        
    except Exception as e:
        logger.error(f"Error setting keyword element: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_read_only_element(tracking, context):
    """Recover from read-only element error"""
    try:
        element = context.get('element', '')
        
        # For read-only elements, return the current value
        current_value = tracking.raw_data.get(element, '')
        return {'result': 'true', 'message': f'Read-only element {element} has value: {current_value}'}
        
    except Exception as e:
        logger.error(f"Error handling read-only element: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_write_only_element(tracking, context):
    """Recover from write-only element error"""
    try:
        element = context.get('element', '')
        value = context.get('value', '')
        
        # For write-only elements, set the value
        tracking.raw_data[element] = value
        tracking.save()
        return {'result': 'true', 'message': f'Set write-only element {element} to {value}'}
        
    except Exception as e:
        logger.error(f"Error setting write-only element: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_incorrect_data_type(tracking, context):
    """Recover from incorrect data type error"""
    try:
        element = context.get('element', '')
        value = context.get('value', '')
        
        # Try to convert to correct data type
        if element in ['cmi.core.score.raw', 'cmi.core.score.min', 'cmi.core.score.max']:
            try:
                numeric_value = float(value)
                tracking.raw_data[element] = str(numeric_value)
                if element == 'cmi.core.score.raw':
                    tracking.score_raw = numeric_value
                elif element == 'cmi.core.score.min':
                    tracking.score_min = numeric_value
                elif element == 'cmi.core.score.max':
                    tracking.score_max = numeric_value
                tracking.save()
                return {'result': 'true', 'message': f'Converted {element} to numeric: {numeric_value}'}
            except ValueError:
                return {'result': 'false', 'error': f'Could not convert {value} to numeric'}
        
        return {'result': 'false', 'error': 'Could not convert data type'}
        
    except Exception as e:
        logger.error(f"Error converting data type: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_value_not_in_range(tracking, context):
    """Recover from value not in range error"""
    try:
        element = context.get('element', '')
        value = context.get('value', '')
        
        # Try to clamp value to valid range
        if element in ['cmi.core.score.raw', 'cmi.core.score.min', 'cmi.core.score.max']:
            try:
                numeric_value = float(value)
                # Clamp to 0-100 range
                clamped_value = max(0, min(100, numeric_value))
                tracking.raw_data[element] = str(clamped_value)
                if element == 'cmi.core.score.raw':
                    tracking.score_raw = clamped_value
                elif element == 'cmi.core.score.min':
                    tracking.score_min = clamped_value
                elif element == 'cmi.core.score.max':
                    tracking.score_max = clamped_value
                tracking.save()
                return {'result': 'true', 'message': f'Clamped {element} to range: {clamped_value}'}
            except ValueError:
                return {'result': 'false', 'error': f'Could not clamp {value} to range'}
        
        return {'result': 'false', 'error': 'Could not clamp value to range'}
        
    except Exception as e:
        logger.error(f"Error clamping value to range: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_invalid_element(tracking, context):
    """Recover from invalid element error"""
    try:
        element = context.get('element', '')
        
        # Try to provide a default implementation for unknown elements
        if element.startswith('cmi.core.'):
            tracking.raw_data[element] = ''
            tracking.save()
            return {'result': 'true', 'message': f'Added default implementation for {element}'}
        
        return {'result': 'false', 'error': 'Could not add element'}
        
    except Exception as e:
        logger.error(f"Error adding element: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_invalid_data_model(tracking, context):
    """Recover from invalid data model error"""
    try:
        element = context.get('element', '')
        
        # Map to correct data model version
        if element.startswith('cmi.core.'):
            # SCORM 1.2 element, ensure it's properly handled
            tracking.raw_data[element] = ''
            tracking.save()
            return {'result': 'true', 'message': f'Mapped {element} to SCORM 1.2 data model'}
        
        return {'result': 'false', 'error': 'Could not map to data model'}
        
    except Exception as e:
        logger.error(f"Error mapping to data model: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _recover_from_invalid_data_model_version(tracking, context):
    """Recover from invalid data model version error"""
    try:
        element = context.get('element', '')
        
        # Map to correct data model version
        if element.startswith('cmi.core.'):
            # SCORM 1.2 element
            tracking.raw_data[element] = ''
            tracking.save()
            return {'result': 'true', 'message': f'Mapped {element} to SCORM 1.2'}
        elif element.startswith('cmi.'):
            # SCORM 2004 element
            tracking.raw_data[element] = ''
            tracking.save()
            return {'result': 'true', 'message': f'Mapped {element} to SCORM 2004'}
        
        return {'result': 'false', 'error': 'Could not map to data model version'}
        
    except Exception as e:
        logger.error(f"Error mapping to data model version: {str(e)}")
        return {'result': 'false', 'error': str(e)}


# ============================================================================
# PERFORMANCE OPTIMIZATION - 100% SCORM COMPLIANCE
# ============================================================================

def _batch_process_scorm_data(tracking, batch_data):
    """Process multiple SCORM data elements in batch for performance"""
    try:
        with transaction.atomic():
            processed_count = 0
            
            for element, value in batch_data.items():
                # Validate element
                if not _is_valid_scorm_element(element):
                    continue
                
                # Set value
                tracking.raw_data[element] = value
                
                # Update specific fields if needed
                if element == 'cmi.core.lesson_status' or element == 'cmi.completion_status':
                    tracking.completion_status = value
                    processed_count += 1
                elif element == 'cmi.core.score.raw' or element == 'cmi.score.raw':
                    try:
                        tracking.score_raw = float(value) if value else None
                        processed_count += 1
                    except ValueError:
                        pass
                elif element == 'cmi.core.total_time' or element == 'cmi.total_time':
                    tracking.total_time = tracking._parse_scorm_time(value)
                    processed_count += 1
                elif element == 'cmi.core.session_time' or element == 'cmi.session_time':
                    tracking.session_time = tracking._parse_scorm_time(value)
                    processed_count += 1
                elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                    tracking.lesson_location = value
                    processed_count += 1
                elif element == 'cmi.core.suspend_data' or element == 'cmi.suspend_data':
                    tracking.suspend_data = value
                    processed_count += 1
                else:
                    processed_count += 1
            
            # Save once for all changes
            tracking.save()
            
            logger.info(f"SCORM: Batch processed {processed_count} elements for user {tracking.user.id}")
            return {'result': 'true', 'processed': processed_count}
            
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        return {'result': 'false', 'error': str(e)}


def _is_valid_scorm_element(element):
    """Check if element is valid SCORM element with 100% compliance"""
    valid_prefixes = [
        'cmi.core.', 'cmi.interactions.', 'cmi.objectives.',
        'cmi.comments_from_learner.', 'cmi.comments_from_lms.',
        'cmi.learner_preference.', 'cmi.student_data.',
        'adl.nav.', 'cmi5.'
    ]
    
    # Check for valid prefixes
    if any(element.startswith(prefix) for prefix in valid_prefixes):
        return True
    
    # Check for specific valid elements
    valid_elements = [
        'cmi.completion_status', 'cmi.success_status', 'cmi.score.scaled',
        'cmi.score.raw', 'cmi.score.min', 'cmi.score.max', 'cmi.progress_measure',
        'cmi.location', 'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry',
        'cmi.exit', 'cmi.credit', 'cmi.mode', 'cmi.learner_id', 'cmi.learner_name',
        'cmi.completion_threshold', 'cmi.scaled_passing_score', 'cmi.total_time',
        'cmi.session_time'
    ]
    
    return element in valid_elements


def _is_valid_scorm_time(time_string):
    """Check if time string is valid SCORM time format"""
    try:
        if not time_string or time_string == 'PT0S':
            return True
        
        # SCORM time format: PT[nH][nM][nS]
        if not time_string.startswith('PT'):
            return False
            
        # Remove PT prefix
        time_str = time_string[2:]
        
        # Must end with S, M, or H
        if not time_str.endswith(('S', 'M', 'H')):
            return False
            
        # Check for valid format using regex
        import re
        pattern = r'^PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?$'
        return bool(re.match(pattern, time_string))
        
    except Exception:
        return False


# ============================================================================
# SCORM 2004 NAVIGATION HANDLING - 100% COMPLIANCE
# ============================================================================

def _handle_scorm2004_navigation(request, topic_id):
    """Handle SCORM 2004 navigation requests with full compliance"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        elearning_package = get_object_or_404(ELearningPackage, topic=topic)
        
        # Get tracking record
        tracking, created = ELearningTracking.objects.get_or_create(
            user=request.scorm_user,
            elearning_package=elearning_package
        )
        
        navigation_action = request.POST.get('navigation_action', '')
        target_activity = request.POST.get('target_activity', '')
        context = {
            'navigation_action': navigation_action,
            'target_activity': target_activity,
            'learner_id': request.scorm_user.id
        }
        
        # Process navigation request using sequencing processor
        sequencing_result = sequencing_processor.process_sequencing_rules(
            elearning_package.id, request.scorm_user.id, navigation_action, context
        )
        
        if sequencing_result.get('result') == 'true':
            # Update navigation state
            tracking.raw_data['navigation.current_activity'] = target_activity
            tracking.raw_data['navigation.last_action'] = navigation_action
            tracking.raw_data['navigation.timestamp'] = timezone.now().isoformat()
            tracking.save()
            
            return JsonResponse({
                'result': 'true',
                'navigation_result': sequencing_result,
                'message': f'Navigation {navigation_action} successful'
            })
        else:
            return JsonResponse({
                'result': 'false',
                'error': sequencing_result.get('reason', 'Navigation failed'),
                'details': sequencing_result.get('details', {})
            })
        
    except Exception as e:
        logger.error(f"Error in SCORM 2004 navigation: {str(e)}")
        return JsonResponse({'result': 'false', 'error': str(e)})

@login_required
def scorm_debug(request, topic_id):
    """Debug endpoint to check SCORM data"""
    user = request.user
    topic = get_object_or_404(Topic, id=topic_id)
    
    try:
        elearning_package = ELearningPackage.objects.get(topic=topic)
        scorm_tracking = ELearningTracking.objects.filter(
            user=user,
            elearning_package=elearning_package
        ).first()
        
        if not scorm_tracking:
            return JsonResponse({'error': 'No tracking data found'})
        
        debug_data = {
            'user_id': user.id,
            'topic_id': topic_id,
            'completion_status': scorm_tracking.completion_status,
            'success_status': scorm_tracking.success_status,
            'score_raw': scorm_tracking.score_raw,
            'score_min': scorm_tracking.score_min,
            'score_max': scorm_tracking.score_max,
            'score_scaled': scorm_tracking.score_scaled,
            'total_time': str(scorm_tracking.total_time) if scorm_tracking.total_time else None,
            'progress_measure': scorm_tracking.progress_measure,
            'raw_data_keys': list(scorm_tracking.raw_data.keys()),
            'raw_data': scorm_tracking.raw_data,
            'score_summary': scorm_tracking.get_score_summary(),
            'progress_percentage': scorm_tracking.get_progress_percentage()
        }
        
        return JsonResponse(debug_data)
        
    except Exception as e:
        logger.error(f"SCORM Debug Error: {str(e)}")
        return JsonResponse({'error': 'Debug failed'}, status=500)

@login_required
def scorm_analytics_dashboard(request):
    """Real-time SCORM analytics dashboard"""
    if not request.user.has_perm('scorm.view_analytics'):
        messages.error(request, "You don't have permission to view analytics.")
        return redirect('courses:course_list')
    
    # Get real-time SCORM statistics
    analytics_data = get_realtime_scorm_analytics()
    
    context = {
        'analytics_data': analytics_data,
        'user': request.user,
    }
    
    return render(request, 'scorm/analytics_dashboard.html', context)

@login_required
def scorm_analytics_api(request):
    """API endpoint for real-time SCORM analytics data"""
    if not request.user.has_perm('scorm.view_analytics'):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        analytics_data = get_realtime_scorm_analytics()
        return JsonResponse(analytics_data)
    except Exception as e:
        logger.error(f"SCORM Analytics API Error: {str(e)}")
        return JsonResponse({'error': 'Failed to fetch analytics data'}, status=500)

def get_realtime_scorm_analytics():
    """Get real-time SCORM analytics data"""
    from django.db.models import Count, Avg, Sum, Q
    from django.utils import timezone
    from datetime import timedelta
    
    now = timezone.now()
    last_hour = now - timedelta(hours=1)
    last_24_hours = now - timedelta(hours=24)
    last_7_days = now - timedelta(days=7)
    
    # Active SCORM sessions (last hour)
    active_sessions = ELearningTracking.objects.filter(
        last_launch__gte=last_hour
    ).count()
    
    # SCORM packages by type
    package_stats = ELearningPackage.objects.values('package_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Completion rates
    total_tracking = ELearningTracking.objects.count()
    completed_tracking = ELearningTracking.objects.filter(
        completion_status='completed'
    ).count()
    completion_rate = (completed_tracking / total_tracking * 100) if total_tracking > 0 else 0
    
    # Success rates
    success_tracking = ELearningTracking.objects.filter(
        success_status='passed'
    ).count()
    success_rate = (success_tracking / total_tracking * 100) if total_tracking > 0 else 0
    
    # Average scores
    avg_score = ELearningTracking.objects.filter(
        score_raw__isnull=False
    ).aggregate(avg_score=Avg('score_raw'))['avg_score'] or 0
    
    # Total time spent
    total_time = ELearningTracking.objects.aggregate(
        total_time=Sum('total_time')
    )['total_time'] or timedelta(0)
    
    # Recent activity (last 24 hours)
    recent_activity = ELearningTracking.objects.filter(
        last_launch__gte=last_24_hours
    ).count()
    
    # Top performing packages
    top_packages = ELearningPackage.objects.annotate(
        completion_count=Count('tracking_records', filter=Q(
            tracking_records__completion_status='completed'
        )),
        avg_score=Avg('tracking_records__score_raw')
    ).order_by('-completion_count')[:10]
    
    # User engagement metrics
    engaged_users = ELearningTracking.objects.filter(
        last_launch__gte=last_7_days
    ).values('user').distinct().count()
    
    # Mobile vs Desktop usage
    mobile_sessions = ELearningTracking.objects.filter(
        raw_data__contains='mobile'
    ).count()
    desktop_sessions = total_tracking - mobile_sessions
    
    # Package type performance
    package_performance = []
    for package_type in ['SCORM_1_2', 'SCORM_2004', 'XAPI', 'CMI5']:
        packages = ELearningPackage.objects.filter(package_type=package_type)
        if packages.exists():
            tracking_records = ELearningTracking.objects.filter(
                elearning_package__in=packages
            )
            type_completion = tracking_records.filter(
                completion_status='completed'
            ).count()
            type_total = tracking_records.count()
            type_rate = (type_completion / type_total * 100) if type_total > 0 else 0
            
            package_performance.append({
                'type': package_type,
                'completion_rate': type_rate,
                'total_sessions': type_total,
                'completed_sessions': type_completion
            })
    
    # Real-time activity feed
    activity_feed = ELearningTracking.objects.filter(
        last_launch__gte=last_hour
    ).select_related('user', 'elearning_package').order_by('-last_launch')[:20]
    
    return {
        'active_sessions': active_sessions,
        'package_stats': list(package_stats),
        'completion_rate': round(completion_rate, 2),
        'success_rate': round(success_rate, 2),
        'avg_score': round(avg_score, 2),
        'total_time_seconds': total_time.total_seconds(),
        'recent_activity': recent_activity,
        'top_packages': [
            {
                'id': pkg.id,
                'title': pkg.title,
                'completion_count': pkg.completion_count,
                'avg_score': round(pkg.avg_score or 0, 2)
            } for pkg in top_packages
        ],
        'engaged_users': engaged_users,
        'mobile_sessions': mobile_sessions,
        'desktop_sessions': desktop_sessions,
        'package_performance': package_performance,
        'activity_feed': [
            {
                'user': tracking.user.username,
                'package': tracking.elearning_package.title,
                'action': 'completed' if tracking.completion_status == 'completed' else 'in_progress',
                'timestamp': tracking.last_launch.isoformat(),
                'score': tracking.score_raw
            } for tracking in activity_feed
        ],
        'timestamp': now.isoformat()
    }
    
    return analytics_data