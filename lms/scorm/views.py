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

logger = logging.getLogger(__name__)

def scorm_launch(request, topic_id):
    """Launch a SCORM package"""
    # SIMPLIFIED AUTHENTICATION - FIXED
    if not request.user.is_authenticated:
        messages.error(request, "Authentication required to access SCORM content.")
        return redirect('login')
    
    user = request.user
    
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Debug logging for SCORM launch
    logger.info(f"SCORM Launch: User {user.username} (ID: {user.id}) accessing topic {topic_id}")
    logger.info(f"SCORM Launch: User authenticated: {request.user.is_authenticated}")
    logger.info(f"SCORM Launch: Session user ID: {request.session.get('_auth_user_id')}")
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        logger.warning(f"SCORM Launch: User {user.username} does not have access to topic {topic_id}")
        messages.error(request, "You don't have access to this content.")
        return redirect('courses:course_list')
    
    try:
        scorm_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        messages.error(request, "E-learning package not found.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if not scorm_package.is_extracted:
        messages.error(request, "SCORM package is not properly extracted.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get or create tracking record
    tracking, created = ELearningTracking.objects.get_or_create(
        user=user,
        elearning_package=scorm_package
    )
    
    # Update launch timestamps
    if not tracking.first_launch:
        tracking.first_launch = timezone.now()
    tracking.last_launch = timezone.now()
    tracking.save()
    
    # Get the launch file URL
    launch_url = scorm_package.get_content_url()
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
        'scorm_package': scorm_package,
        'launch_url': launch_url,
        'tracking': tracking,
        'user_id': user.id,
        'scorm_api_url': f'/scorm/api/{topic_id}/',
        'scorm_data': scorm_data,
        'scorm_data_json': scorm_data_json
    }
    
    return render(request, 'scorm/launch.html', context)

def scorm_content(request, topic_id, file_path):
    """Serve SCORM content files"""
    # For SCORM content, we need to handle authentication differently
    # since assets are loaded by the iframe content
    if not request.user.is_authenticated:
        # For SCORM assets, we'll allow access if the user has a valid session
        # This is necessary because iframe content can't always send auth headers
        if not request.session.get('_auth_user_id'):
            raise Http404("Authentication required")
        
        # Get user from session
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=request.session.get('_auth_user_id'))
        except User.DoesNotExist:
            raise Http404("Invalid session")
    else:
        user = request.user
    
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(user):
        raise Http404("Access denied")
    
    try:
        scorm_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        raise Http404("E-learning package not found")
    
    if not scorm_package.is_extracted:
        raise Http404("SCORM package not extracted")
    
    # Construct the full file path using the storage system
    if scorm_package.package_file.storage.exists(scorm_package.extracted_path):
        # Try the direct path first
        full_path = os.path.join(scorm_package.package_file.storage.path(scorm_package.extracted_path), file_path)
        
        # If not found, try with scormcontent prefix (common for Articulate)
        if not os.path.exists(full_path):
            scormcontent_path = os.path.join(scorm_package.package_file.storage.path(scorm_package.extracted_path), 'scormcontent', file_path)
            if os.path.exists(scormcontent_path):
                full_path = scormcontent_path
            else:
                # Try other common SCORM content directories
                for content_dir in ['content', 'data', 'story_content']:
                    alt_path = os.path.join(scorm_package.package_file.storage.path(scorm_package.extracted_path), content_dir, file_path)
                    if os.path.exists(alt_path):
                        full_path = alt_path
                        break
    else:
        raise Http404("SCORM package not found")
    
    if not os.path.exists(full_path):
        raise Http404("File not found")
    
    # Determine content type with proper MIME types for Articulate
    content_type = 'text/html'
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
    
    # Read and serve the file
    try:
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
                
                # Inject SCORM API script into HTML content
                scorm_api_script = f'''
<script>
// Enhanced SCORM API Implementation for iframe content
(function() {{
    'use strict';
    
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
            return "true";
        }},
        
        SetDataChunk: function(data) {{
            console.log('SCORM API: SetDataChunk called with:', data);
            this.data['cmi.core.suspend_data'] = data;
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
    
    // Make API available globally with multiple fallbacks
    window.API = SCORM_API;
    window.parent.API = SCORM_API;
    window.top.API = SCORM_API;
    
    // Additional fallbacks for complex iframe structures
    try {{
        if (window.parent && window.parent !== window) {{
            window.parent.API = SCORM_API;
        }}
        if (window.top && window.top !== window) {{
            window.top.API = SCORM_API;
        }}
        if (window.parent.parent) {{
            window.parent.parent.API = SCORM_API;
        }}
        if (window.parent.parent.parent) {{
            window.parent.parent.parent.API = SCORM_API;
        }}
    }} catch (e) {{
        console.log('SCORM API: Could not set API in parent frames (cross-origin)');
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
        SetDataChunk: function(data) {{ return "true"; }},
        GetDataChunk: function() {{ return ""; }},
        SetPassed: function() {{ return "true"; }},
        SetReachedEnd: function() {{ return "true"; }},
        SetScore: function(score) {{ return "true"; }},
        SetBookmark: function(bookmark) {{ return "true"; }},
        SetFailed: function() {{ return "true"; }},
        CommitData: function() {{ return "true"; }},
        ConcedeControl: function() {{ return "true"; }},
        CreateResponseIdentifier: function() {{ return "true"; }},
        Finish: function() {{ return "true"; }},
        GetStatus: function() {{ return "incomplete"; }},
        MatchingResponse: function() {{ return "true"; }},
        RecordFillInInteraction: function() {{ return "true"; }},
        RecordMatchingInteraction: function() {{ return "true"; }},
        RecordMultipleChoiceInteraction: function() {{ return "true"; }},
        ResetStatus: function() {{ return "true"; }},
        SetLanguagePreference: function(lang) {{ return "true"; }},
        WriteToDebug: function(message) {{ return "true"; }},
        LMSInitialize: function(param) {{ return "true"; }},
        LMSGetValue: function(element) {{ return ""; }},
        LMSSetValue: function(element, value) {{ return "true"; }},
        LMSCommit: function(param) {{ return "true"; }},
        LMSFinish: function(param) {{ return "true"; }},
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
            response['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; frame-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self';"
            # Additional headers for Articulate content
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        elif file_path.endswith('.js'):
            # Special handling for JavaScript files
            response['Content-Type'] = 'application/javascript; charset=utf-8'
            # Remove X-Content-Type-Options for JS files to prevent MIME type issues
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            # Don't add X-Content-Type-Options for JS files
            if 'X-Content-Type-Options' in response:
                del response['X-Content-Type-Options']
        elif file_path.endswith('.css'):
            # Special handling for CSS files
            response['Content-Type'] = 'text/css; charset=utf-8'
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        
        return response
        
    except Exception as e:
        logger.error("Error serving SCORM content: {}".format(str(e)))
        raise Http404("Error serving file")

@csrf_exempt
@require_http_methods(["GET", "POST"])
def scorm_api(request, topic_id):
    """SCORM API endpoint for communication with SCORM packages"""
    # SIMPLIFIED AUTHENTICATION - FIXED
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Add user to request for use in handlers
    request.scorm_user = request.user
    
    logger.info(f"SCORM API: Request from user {request.user.username} (ID: {request.user.id})")
    
    if request.method == 'GET':
        return _handle_scorm_get(request, topic_id)
    elif request.method == 'POST':
        return _handle_scorm_post(request, topic_id)

def _handle_scorm_get(request, topic_id):
    """Handle SCORM GET requests (Initialize, GetValue) - Enhanced for SCORM 2004"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = get_object_or_404(ELearningPackage, topic=topic)
        
        # Get tracking record
        tracking, created = ELearningTracking.objects.get_or_create(
            user=request.scorm_user,
            elearning_package=scorm_package
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
            # Return 'resume' if user has bookmarked content, 'ab-initio' for first time
            has_bookmark = bool(tracking.location or tracking.raw_data.get('cmi.core.lesson_location', ''))
            has_suspend_data = bool(tracking.suspend_data or tracking.raw_data.get('cmi.core.suspend_data', ''))
            # Resume if user has bookmark OR suspend data, and this is not their first launch
            should_resume = (has_bookmark or has_suspend_data) and tracking.first_launch is not None
            entry_value = 'resume' if should_resume else 'ab-initio'
            logger.info(f"SCORM: Getting entry for user {request.scorm_user.id}: {entry_value} (has_bookmark: {has_bookmark}, has_suspend_data: {has_suspend_data}, first_launch: {tracking.first_launch})")
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
            # Return suspend data for Articulate
            suspend_data = tracking.suspend_data or tracking.raw_data.get('cmi.core.suspend_data', '')
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
            return JsonResponse({'value': tracking.entry})
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
        scorm_package = get_object_or_404(ELearningPackage, topic=topic)
        
        # Get tracking record
        tracking, created = ELearningTracking.objects.get_or_create(
            user=request.scorm_user,
            elearning_package=scorm_package
        )
        
        # Get the action
        action = request.POST.get('action', '')
        
        if action == 'SetValue':
            element = request.POST.get('element', '')
            value = request.POST.get('value', '')
            
            logger.info(f"SCORM: SetValue request - element: {element}, value: {value} for user {request.scorm_user.id}")
            
            # Enhanced element validation for SCORM 1.2, 2004, and cmi5
            valid_elements = [
                # SCORM 1.2 Core elements
                'cmi.core.lesson_status', 'cmi.core.score.raw', 'cmi.core.score.min', 'cmi.core.score.max',
                'cmi.core.total_time', 'cmi.core.session_time', 'cmi.core.lesson_location', 'cmi.core.exit',
                'cmi.core.entry', 'cmi.core.student_id', 'cmi.core.student_name', 'cmi.core.credit',
                'cmi.core.lesson_mode', 'cmi.core.max_time_allowed', 'cmi.core.mastery_score',
                'cmi.core.suspend_data', 'cmi.core.launch_data', 'cmi.core.comments',
                'cmi.core.comments_from_lms', 'cmi.core.objectives', 'cmi.core.student_data',
                'cmi.core.student_preference', 'cmi.core.interactions', 'cmi.core.navigation',
                
                # SCORM 2004 elements
                'cmi.completion_status', 'cmi.success_status', 'cmi.score.scaled', 'cmi.score.raw',
                'cmi.score.min', 'cmi.score.max', 'cmi.progress_measure', 'cmi.location',
                'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry', 'cmi.exit', 'cmi.credit',
                'cmi.mode', 'cmi.learner_id', 'cmi.learner_name', 'cmi.completion_threshold',
                'cmi.scaled_passing_score', 'cmi.total_time', 'cmi.session_time',
                
                # Learner preferences
                'cmi.learner_preference.audio_level', 'cmi.learner_preference.language',
                'cmi.learner_preference.delivery_speed', 'cmi.learner_preference.audio_captioning',
                
                # Student data
                'cmi.student_data.mastery_score', 'cmi.student_data.max_time_allowed',
                'cmi.student_data.time_limit_action',
                
                # Objectives and interactions
                'cmi.objectives', 'cmi.interactions', 'cmi.comments_from_learner',
                'cmi.comments_from_lms'
            ]
            
            # Allow any element that starts with cmi.core, cmi.interactions, cmi.objectives, or cmi.comments
            if not (element.startswith('cmi.core.') or element.startswith('cmi.interactions.') or 
                   element.startswith('cmi.objectives.') or element.startswith('cmi.comments.') or
                   element.startswith('cmi.learner_preference.') or element.startswith('cmi.student_data.') or
                   element in ['cmi.completion_status', 'cmi.success_status', 'cmi.score.scaled', 'cmi.score.raw',
                              'cmi.score.min', 'cmi.score.max', 'cmi.progress_measure', 'cmi.location',
                              'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry', 'cmi.exit', 'cmi.credit',
                              'cmi.mode', 'cmi.learner_id', 'cmi.learner_name', 'cmi.completion_threshold',
                              'cmi.scaled_passing_score', 'cmi.total_time', 'cmi.session_time']):
                logger.warning(f"SCORM: Invalid element requested: {element}")
                return JsonResponse({'result': 'false', 'error': 'Invalid element'})
            
            # Update tracking based on the element
            if element == 'cmi.core.lesson_status' or element == 'cmi.completion_status':
                # Validate lesson status values
                valid_statuses = ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']
                if value in valid_statuses:
                    tracking.completion_status = value
                    logger.info(f"SCORM: Set completion_status to {value}")
                else:
                    logger.warning(f"SCORM: Invalid completion_status value: {value}")
            elif element == 'cmi.core.score.raw' or element == 'cmi.score.raw':
                try:
                    new_score = float(value) if value else None
                    tracking.score_raw = new_score
                    logger.info(f"SCORM: Set score.raw to {value}")
                    
                    # Validate score after setting
                    if new_score is not None:
                        if not tracking.validate_score():
                            logger.warning(f"SCORM: Score validation failed for user {request.scorm_user.id}: {new_score}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid score.raw value: {value}")
            elif element == 'cmi.core.score.min' or element == 'cmi.score.min':
                try:
                    tracking.score_min = float(value) if value else None
                    logger.info(f"SCORM: Set score.min to {value}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid score.min value: {value}")
            elif element == 'cmi.core.score.max' or element == 'cmi.score.max':
                try:
                    tracking.score_max = float(value) if value else None
                    logger.info(f"SCORM: Set score.max to {value}")
                    
                    # Log score summary after setting max score
                    if tracking.score_raw is not None:
                        summary = tracking.get_score_summary()
                        logger.info(f"SCORM: Score summary for user {request.scorm_user.id}: {summary}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid score.max value: {value}")
            elif element == 'cmi.core.score.scaled' or element == 'cmi.score.scaled':
                try:
                    tracking.score_scaled = float(value) if value else None
                    logger.info(f"SCORM: Set score.scaled to {value}")
                except ValueError:
                    logger.warning(f"SCORM: Invalid score.scaled value: {value}")
            elif element == 'cmi.core.total_time' or element == 'cmi.total_time':
                tracking.total_time = tracking._parse_scorm_time(value)
                logger.info(f"SCORM: Set total_time to {value}")
            elif element == 'cmi.core.session_time' or element == 'cmi.session_time':
                tracking.session_time = tracking._parse_scorm_time(value)
                logger.info(f"SCORM: Set session_time to {value}")
            elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                # Store lesson location for bookmarking
                tracking.location = value
                tracking.raw_data['cmi.core.lesson_location'] = value
                logger.info(f"SCORM: Set lesson_location to {value}")
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
                # Store suspend data (important for Articulate)
                tracking.suspend_data = value
                tracking.raw_data['cmi.core.suspend_data'] = value
                logger.info(f"SCORM: Set suspend_data to {value[:100]}...")  # Log first 100 chars
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
            elif element == 'cmi.progress_measure':
                try:
                    tracking.progress_measure = float(value) if value else None
                    logger.info(f"SCORM: Set progress_measure to {value}")
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
            
            tracking.save()
            
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
    scorm_packages = ELearningPackage.objects.filter(
        topic__in=course_topics
    ).select_related('topic')
    
    # Get tracking data
    tracking_data = ELearningTracking.objects.filter(
        elearning_package__topic__in=course_topics
    ).select_related('user', 'elearning_package__topic')
    
    # Calculate statistics
    total_learners = course.enrolled_users.count()
    scorm_topics = scorm_packages.count()
    
    completion_stats = {}
    score_stats = {}
    
    for package in scorm_packages:
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
        'scorm_packages': scorm_packages,
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