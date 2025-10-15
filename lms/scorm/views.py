"""
Simplified SCORM Views - Clean Implementation
"""
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from .models import ScormPackage, ScormAttempt
from .api_handler import ScormAPIHandler
from courses.models import Topic

logger = logging.getLogger(__name__)

@login_required
def scorm_view(request, topic_id):
    """
    Simplified SCORM content viewer
    """
    # ENHANCED: Comprehensive authentication check for revisit scenarios
    if not request.user.is_authenticated:
        logger.warning(f"Unauthenticated access attempt to SCORM topic {topic_id}")
        messages.error(request, "You must be logged in to access SCORM content.")
        return redirect('users:login')
    
    # ENHANCED: Check for session validity in revisit scenarios
    if not request.user.is_active:
        logger.warning(f"Inactive user {request.user.email} attempted to access SCORM topic {topic_id}")
        messages.error(request, "Your account is not active. Please contact support.")
        return redirect('users:login')
    
    # Get topic and check access
    topic = get_object_or_404(
        Topic.objects.select_related('scorm_package'),
        id=topic_id
    )
    
    # Check user access - Allow all authenticated users to access SCORM content
    # This provides broader access for testing and learning purposes
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to access SCORM content.")
        return redirect('users:login')
    
    # Check if topic has SCORM package
    if not hasattr(topic, 'scorm_package') or not topic.scorm_package:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    scorm_package = topic.scorm_package
    
    # ENHANCED: Smart attempt handling with package type awareness
    attempt = None
    attempt_id = None
    
    # CRITICAL FIX: Detect package type for special handling
    is_scormcontent_type = 'scormcontent/' in scorm_package.launch_url
    is_scormdriver_type = 'scormdriver/' in scorm_package.launch_url
    
    logger.info(f"SCORM Package Type Detection: scormcontent={is_scormcontent_type}, scormdriver={is_scormdriver_type}, launch_url={scorm_package.launch_url}")
    
    if request.user.is_authenticated:
        # Check if user is revisiting (has session data or recent attempt)
        from django.utils import timezone
        from datetime import timedelta
        
        # ENHANCED: Different timeout for different package types
        timeout_minutes = 60 if is_scormcontent_type else 30  # Longer timeout for scormcontent type
        recent_cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
        
        recent_attempt = ScormAttempt.objects.filter(
            user=request.user,
            scorm_package=scorm_package,
            last_accessed__gte=recent_cutoff
        ).order_by('-last_accessed').first()
        
        # Check if user has an incomplete attempt that can be resumed
        incomplete_attempt = ScormAttempt.objects.filter(
            user=request.user,
            scorm_package=scorm_package,
            lesson_status__in=['not attempted', 'incomplete', 'browsed']
        ).order_by('-attempt_number').first()
        
        if recent_attempt and incomplete_attempt and recent_attempt.id == incomplete_attempt.id:
            # Resume existing attempt
            attempt = recent_attempt
            attempt.entry = 'resume'
            attempt.last_accessed = timezone.now()
            attempt.save()
            logger.info(f"SCORM Resume: Resuming attempt {attempt.id} for user {request.user.username}")
        else:
            # Create new attempt
            last_attempt = ScormAttempt.objects.filter(
                user=request.user,
                scorm_package=scorm_package
            ).order_by('-attempt_number').first()
            
            attempt_number = 1
            if last_attempt:
                attempt_number = last_attempt.attempt_number + 1
            
            attempt = ScormAttempt.objects.create(
                user=request.user,
                scorm_package=scorm_package,
                attempt_number=attempt_number,
                lesson_location='',
                suspend_data='',
                lesson_status='not attempted',
                completion_status='incomplete',
                success_status='unknown',
                total_time='0000:00:00.00',
                session_time='0000:00:00.00',
                entry='ab-initio'
            )
            logger.info(f"SCORM New Attempt: Created attempt {attempt.id} (attempt #{attempt_number}) for user {request.user.username}")
        
        attempt_id = attempt.id
    
    # Generate content URL with attempt ID for resume functionality
    # Handle different SCORM package launch URLs (story.html, index.htm, goodbye.html, etc.)
    launch_url = scorm_package.launch_url or 'index.html'
    
    # Ensure the launch URL is properly formatted
    if not launch_url.startswith('/'):
        launch_url = launch_url.lstrip('/')
    
    # Generate the content URL
    content_url = f"/scorm/content/{topic_id}/{launch_url}"
    
    logger.info(f"SCORM Content URL: {content_url} (launch_url: {scorm_package.launch_url})")
    
    # Add attempt ID for resume functionality - FIX: Clean parameter handling
    if attempt_id:
        content_url = f"{content_url}?attempt_id={attempt_id}"
    
    # Add lesson ID if provided - FIX: Check for existing parameters
    lesson_id = request.GET.get('lesson_id', '')
    if lesson_id:
        separator = '&' if '?' in content_url else '?'
        content_url = f"{content_url}{separator}lesson_id={lesson_id}"
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'attempt_id': attempt_id,
        'content_url': content_url,
        'is_scormcontent_type': is_scormcontent_type,
        'is_scormdriver_type': is_scormdriver_type,
        'package_type': 'scormcontent' if is_scormcontent_type else 'scormdriver' if is_scormdriver_type else 'unknown',
    }
    
    return render(request, 'scorm/player.html', context)

@login_required
@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def scorm_api(request, attempt_id):
    """
    Simplified SCORM API endpoint
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == "OPTIONS":
        response = JsonResponse({'status': 'ok'})
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
        return response
    
    try:
        # Get attempt
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Allow all authenticated users to access SCORM attempts
        # This enables broader testing and learning capabilities
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        # Parse request data
        data = json.loads(request.body)
        method = data.get('method')
        parameters = data.get('parameters', [])
        
        # Handle SCORM API call
        api_handler = ScormAPIHandler(attempt)
        result = api_handler.handle_api_call(attempt, method, parameters)
        
        return JsonResponse({
            'success': True,
            'result': result,
            'error_code': '0'
        })
        
    except Exception as e:
        logger.error(f"SCORM API error: {e}")
        return JsonResponse({
            'success': False,
            'result': 'false',
            'error_code': '101',
            'error': str(e)
        })

@login_required
def scorm_content(request, topic_id, path):
    """
    Enhanced SCORM content serving - Fixed for different package types and revisit scenarios
    """
    try:
        # ENHANCED: Special handling for revisit scenarios with different SCORM package types
        logger.info(f"SCORM Content Request: topic_id={topic_id}, path='{path}', user={request.user.email if request.user.is_authenticated else 'anonymous'}")
        
        # CRITICAL FIX: Handle authentication issues for scormcontent/ type packages
        if not request.user.is_authenticated:
            logger.warning(f"Unauthenticated SCORM content request for topic {topic_id}, path: {path}")
            # For AJAX requests from SCORM content, return 401 instead of redirect
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'scormcontent/' in path:
                return JsonResponse({'error': 'Authentication required', 'redirect': '/users/login/'}, status=401)
            return redirect('users:login')
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = topic.scorm_package
        
        if not scorm_package:
            return HttpResponse('SCORM package not found', status=404)
        
        # Clean up path
        path = path.lstrip('/')
        if '..' in path or path.startswith('/'):
            return HttpResponse('Invalid path', status=400)
        
        logger.info(f"SCORM Content Request: topic_id={topic_id}, path='{path}', scorm_package='{scorm_package.title}'")
        
        # ENHANCED: Handle common SCORM path mapping issues
        # Fix common problematic requests from SCORM content
        if path == 'scormcontent/false':
            # Redirect to the actual content index
            path = 'scormcontent/index.html'
            logger.info(f"SCORM Path Fix: Redirected 'scormcontent/false' to '{path}'")
        elif path.startswith('scormcontent/') and path.endswith('/false'):
            # Handle other false path variations
            base_path = path.replace('/false', '')
            path = f"{base_path}/index.html"
            logger.info(f"SCORM Path Fix: Redirected false path to '{path}'")
        elif path == 'false' or path == 'false/':
            # Direct false request - redirect to main content
            path = 'scormcontent/index.html'
            logger.info(f"SCORM Path Fix: Redirected 'false' to '{path}'")
        
        # Generate S3 URL
        from .s3_direct import scorm_s3
        s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        
        logger.info(f"SCORM S3 URL Generated: {s3_url}")
        
        if not s3_url:
            return HttpResponse('Content not found', status=404)
        
        # For non-HTML files, redirect to S3
        if not path.endswith(('.html', '.htm')):
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(s3_url)
        
        # For HTML files, fetch from S3 and inject SCORM API
        try:
            import requests
            
            # Fetch content from S3
            response = requests.get(s3_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Failed to fetch content from S3: {response.status_code}")
                return HttpResponse('Content not accessible', status=404)
            
            content = response.text
            
            # Enhanced SCORM API injection with proper attempt ID
            attempt_id = request.GET.get('attempt_id', '')
            
            # Get the actual attempt ID from the session or create one
            if not attempt_id and request.user.is_authenticated:
                try:
                    from scorm.models import ScormAttempt
                    attempt = ScormAttempt.objects.filter(
                        user=request.user,
                        scorm_package=scorm_package
                    ).order_by('-attempt_number').first()
                    if attempt:
                        attempt_id = attempt.id
                except Exception as e:
                    logger.warning(f"Could not get attempt ID for user {request.user.username}: {e}")
                    pass
                    
            # Check if this is a Storyline package for enhanced support
            is_storyline = (scorm_package.version == 'storyline' or 
                          'storyline' in str(scorm_package.launch_url).lower() or
                          'story.html' in str(scorm_package.launch_url).lower())
            
            # Add CSRF token to the content
            csrf_token = request.META.get('CSRF_COOKIE', '')
            if not csrf_token:
                from django.middleware.csrf import get_token
                csrf_token = get_token(request)
            
            # Enhanced API injection - different approach for Storyline
            if is_storyline:
                scorm_api = """
<script>
// Enhanced Storyline SCORM API Support
window.csrfToken = '{csrf_token}';
window._scormAttemptId = '{attempt_id}';
window._isStoryline = true;

// Storyline-specific API setup
(function() {{
    console.log('Initializing enhanced Storyline SCORM API support');
    
    // Create robust API for Storyline
    var StorylineAPI = {{
        _attemptId: '{attempt_id}',
        _initialized: false,
        _lastError: '0',
        
        // Storyline expects both SCORM 1.2 and 2004 methods
        Initialize: function(param) {{
            return this.LMSInitialize(param);
        }},
        
        LMSInitialize: function(param) {{
            console.log('Storyline SCORM Initialize called');
            try {{
                this._initialized = true;
                return 'true';
            }} catch (e) {{
                console.error('Storyline Initialize error:', e);
                this._lastError = '101';
                return 'false';
            }}
        }},
        
        Terminate: function(param) {{
            return this.LMSFinish(param);
        }},
        
        LMSFinish: function(param) {{
            console.log('Storyline SCORM Terminate called');
            this._initialized = false;
            return 'true'; 
        }},
        
        GetValue: function(element) {{
            return this.LMSGetValue(element);
        }},
        
        LMSGetValue: function(element) {{
            console.log('Storyline GetValue:', element);
            if (!this._initialized) {{
                this._lastError = '301';
                return '';
            }}
            
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/scorm/api/{attempt_id}/', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', window.csrfToken || '');
                
                xhr.send(JSON.stringify({{
                    method: 'LMSGetValue',
                    parameters: [element]
                }}));
                
                if (xhr.status === 200) {{
                    var result = JSON.parse(xhr.responseText);
                    console.log('Storyline GetValue result:', element, '=', result.result);
                    return result.result || '';
                }} else {{
                    console.error('Storyline GetValue error:', xhr.status);
                    this._lastError = '101';
                    return '';
                }}
            }} catch (e) {{
                console.error('Storyline GetValue exception:', e);
                this._lastError = '101';
                return '';
            }}
        }},
        
        SetValue: function(element, value) {{
            return this.LMSSetValue(element, value);
        }},
        
        LMSSetValue: function(element, value) {{
            console.log('Storyline SetValue:', element, '=', value);
            if (!this._initialized) {{
                this._lastError = '301';
                return 'false';
            }}
            
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/scorm/api/{attempt_id}/', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', window.csrfToken || '');
                
                xhr.send(JSON.stringify({{
                    method: 'LMSSetValue',
                    parameters: [element, value]
                }}));
                
                if (xhr.status === 200) {{
                    var result = JSON.parse(xhr.responseText);
                    console.log('Storyline SetValue success:', element, '=', value);
                    
                    // Auto-commit critical Storyline data
                    if (element.indexOf('lesson_status') > -1 || element.indexOf('score') > -1) {{
                        setTimeout(function() {{
                            this.LMSCommit('');
                        }}.bind(this), 100);
                    }}
                    
                    return result.result || 'false';
                }} else {{
                    console.error('Storyline SetValue error:', xhr.status);
                    this._lastError = '101';
                    return 'false';
                }}
            }} catch (e) {{
                console.error('Storyline SetValue exception:', e);
                this._lastError = '101';
                return 'false';
            }}
        }},
        
        Commit: function(param) {{
            return this.LMSCommit(param);
        }},
        
        LMSCommit: function(param) {{
            console.log('Storyline Commit called');
            if (!this._initialized) {{
                this._lastError = '301';
                return 'false';
            }}
            
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/scorm/api/{attempt_id}/', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', window.csrfToken || '');
                
                xhr.send(JSON.stringify({{
                    method: 'LMSCommit',
                    parameters: []
                }}));
                
                if (xhr.status === 200) {{
                    var result = JSON.parse(xhr.responseText);
                    console.log('Storyline Commit success');
                    return result.result || 'false';
                }} else {{
                    console.error('Storyline Commit error:', xhr.status);
                    this._lastError = '101';
                    return 'false';
                }}
            }} catch (e) {{
                console.error('Storyline Commit exception:', e);
                this._lastError = '101';
                return 'false';
            }}
        }},
        
        GetLastError: function() {{
            return this._lastError;
        }},
        
        LMSGetLastError: function() {{
            return this._lastError;
        }},
        
        GetErrorString: function(code) {{
            return 'No error';
        }},
        
        LMSGetErrorString: function(code) {{
            return 'No error';
        }},
        
        GetDiagnostic: function(code) {{
            return 'No error';
        }},
        
        LMSGetDiagnostic: function(code) {{
            return 'No error';
        }}
    }};
    
    // Expose API in ALL contexts that Storyline might check
    window.API = StorylineAPI;
    window.API_1484_11 = StorylineAPI;
    
    // Parent window exposure (critical for iframes)
    if (window.parent && window.parent !== window) {{
        window.parent.API = StorylineAPI;
        window.parent.API_1484_11 = StorylineAPI;
        console.log('Storyline API exposed to parent window');
    }}
    
    if (window.top && window.top !== window) {{
        window.top.API = StorylineAPI;
        window.top.API_1484_11 = StorylineAPI;
        console.log('Storyline API exposed to top window');
    }}
    
    // Document exposure
    if (document) {{
        document.API = StorylineAPI;
        document.API_1484_11 = StorylineAPI;
    }}
    
    // Create API finder functions
    window.getAPI = function() {{ return StorylineAPI; }};
    window.getAPIHandle = function() {{ return StorylineAPI; }};
    window.findAPI = function() {{ return StorylineAPI; }};
    window.scanForAPI = function() {{ return StorylineAPI; }};
    
    // Storyline-specific properties
    window.scormAPI = StorylineAPI;
    window.SCORM_API = StorylineAPI;
    
    console.log('Enhanced Storyline SCORM API initialized successfully');
    
    // Periodic re-exposure for dynamic content
    var exposureCount = 0;
    var refresher = setInterval(function() {{
        if (++exposureCount > 10) {{
            clearInterval(refresher);
            return;
        }}
        
        if (!window.parent.API) window.parent.API = StorylineAPI;
        if (!window.top.API) window.top.API = StorylineAPI;
    }}, 500);
    
}}})();
</script>""".format(csrf_token=csrf_token, attempt_id=attempt_id)
            else:
                scorm_api = """
<script>
// Standard SCORM API Support
window.csrfToken = '{csrf_token}';

// Enhanced error handling for SCORM API
window.API = {{
    _attemptId: '{attempt_id}',
    _initialized: false,
    _lastError: '0',
    
    Initialize: function(param) {{ 
        console.log('SCORM API Initialize called for attempt {attempt_id}');
        try {{
            this._initialized = true;
            return 'true';
        }} catch (e) {{
            console.error('SCORM Initialize error:', e);
            this._lastError = '101';
            return 'false';
        }}
    }},
    
    Terminate: function(param) {{ 
        console.log('SCORM API Terminate called');
        this._initialized = false;
        return 'true'; 
    }},
    
    GetValue: function(element) {{ 
        console.log('SCORM API GetValue called for:', element);
        if (!this._initialized) {{
            this._lastError = '301';
            return '';
        }}
        
        try {{
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/scorm/api/{attempt_id}/', false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', window.csrfToken || '');
            
            var response = xhr.send(JSON.stringify({{
                method: 'GetValue',
                parameters: [element]
            }}));
            
            if (xhr.status === 200) {{
                var result = JSON.parse(xhr.responseText);
                console.log('SCORM GetValue result:', result);
                return result.result || '';
            }} else {{
                console.error('SCORM GetValue error:', xhr.status, xhr.responseText);
                this._lastError = '101';
                return '';
            }}
        }} catch (e) {{
            console.error('SCORM GetValue exception:', e);
            this._lastError = '101';
            return '';
        }}
    }},
    
    SetValue: function(element, value) {{ 
        console.log('SCORM API SetValue called:', element, '=', value);
        if (!this._initialized) {{
            this._lastError = '301';
            return 'false';
        }}
        
        // Make API call to backend
        try {{
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/scorm/api/{attempt_id}/', false); // Synchronous for SCORM compatibility
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', window.csrfToken || '');
            
            var response = xhr.send(JSON.stringify({{
                method: 'SetValue',
                parameters: [element, value]
            }}));
            
            if (xhr.status === 200) {{
                var result = JSON.parse(xhr.responseText);
                console.log('SCORM SetValue result:', result);
                return result.result || 'false';
            }} else {{
                console.error('SCORM SetValue error:', xhr.status);
                this._lastError = '101';
                return 'false';
            }}
        }} catch (e) {{
            console.error('SCORM SetValue exception:', e);
            this._lastError = '101';
            return 'false';
        }}
    }},
    
    Commit: function(param) {{ 
        console.log('SCORM API Commit called');
        if (!this._initialized) {{
            this._lastError = '301';
            return 'false';
        }}
        
        // Make API call to backend
        try {{
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/scorm/api/{attempt_id}/', false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', window.csrfToken || '');
            
            var response = xhr.send(JSON.stringify({{
                method: 'Commit',
                parameters: []
            }}));
            
            if (xhr.status === 200) {{
                var result = JSON.parse(xhr.responseText);
                console.log('SCORM Commit result:', result);
                return result.result || 'false';
            }} else {{
                console.error('SCORM Commit error:', xhr.status);
                this._lastError = '101';
                return 'false';
            }}
        }} catch (e) {{
            console.error('SCORM Commit exception:', e);
            this._lastError = '101';
            return 'false';
        }}
    }},
    
    GetLastError: function() {{ 
        return this._lastError; 
    }},
    
    GetErrorString: function(code) {{ 
        return 'No error'; 
    }},
    
    GetDiagnostic: function(code) {{ 
        return 'No error'; 
    }}
}};

// Also expose as API_1484_11 for SCORM 2004 compatibility
window.API_1484_11 = window.API;

console.log('SCORM API injected successfully with attempt ID: {attempt_id}');
</script>""".format(csrf_token=csrf_token, attempt_id=attempt_id)
            
            # Enhanced error suppression - more aggressive for Storyline
            if is_storyline:
                error_suppression = '''
<script>
// Enhanced Storyline error suppression
window.addEventListener('error', function(e) {
    console.log('Suppressed Storyline error:', e.message, e.filename, e.lineno);
    e.preventDefault();
    return true;
});

// Suppress unhandled promise rejections
window.addEventListener('unhandledrejection', function(e) {
    console.log('Suppressed Storyline promise rejection:', e.reason);
    e.preventDefault();
});

// Override alert and confirm for Storyline
var originalAlert = window.alert;
var originalConfirm = window.confirm;

window.alert = function(message) {
    if (typeof message === 'string') {
        var msg = message.toLowerCase();
        if (msg.includes('error') || msg.includes('failed') || msg.includes('cannot') || 
            msg.includes('unable') || msg.includes('scorm') || msg.includes('lms')) {
            console.log('Suppressed Storyline alert:', message);
            return;
        }
    }
    return originalAlert.call(this, message);
};

window.confirm = function(message) {
    if (typeof message === 'string') {
        var msg = message.toLowerCase();
        if (msg.includes('error') || msg.includes('failed') || msg.includes('scorm')) {
            console.log('Auto-confirmed Storyline dialog:', message);
            return true;
        }
    }
    return originalConfirm.call(this, message);
};

console.log('Enhanced Storyline error suppression active');
</script>'''
            else:
                error_suppression = '''
<script>
// Standard SCORM error suppression
window.addEventListener('error', function(e) {
    console.log('Suppressed SCORM error:', e.message);
    e.preventDefault();
    return true;
});

var originalAlert = window.alert;
window.alert = function(message) {
    if (typeof message === 'string' && 
        (message.toLowerCase().includes('error') || 
         message.toLowerCase().includes('an error has occurred'))) {
        console.log('Suppressed error alert:', message);
        return;
    }
    return originalAlert.call(this, message);
};
</script>'''
            
            if '</head>' in content:
                content = content.replace('</head>', scorm_api + error_suppression + '</head>')
            else:
                content = scorm_api + error_suppression + content
            
            response = HttpResponse(content, content_type='text/html; charset=utf-8')
            response['Access-Control-Allow-Origin'] = '*'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
            
        except Exception as e:
            logger.error(f"Error serving content: {e}")
            return HttpResponse('Error loading content', status=500)
            
    except Exception as e:
        logger.error(f"Error in scorm_content: {e}")
        return HttpResponse('Error loading content', status=500)

@login_required
def scorm_api_test(request):
    """
    Diagnostic tool for testing SCORM API calls
    """
    return render(request, 'scorm/api_test.html')

@login_required
def scorm_debug(request, attempt_id):
    """
    Debug SCORM attempt data
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Allow all authenticated users to access debug information
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        debug_data = {
            'attempt_id': attempt.id,
            'user': attempt.user.username,
            'scorm_package': attempt.scorm_package.title,
            'version': attempt.scorm_package.version,
            'lesson_status': attempt.lesson_status,
            'completion_status': attempt.completion_status,
            'score_raw': attempt.score_raw,
            'lesson_location': attempt.lesson_location,
            'suspend_data': attempt.suspend_data[:100] if attempt.suspend_data else None,
            'cmi_data_keys': list(attempt.cmi_data.keys()) if attempt.cmi_data else [],
            'entry': attempt.entry,
            'exit_mode': attempt.exit_mode,
            'last_accessed': attempt.last_accessed.isoformat() if attempt.last_accessed else None,
        }
        
        return JsonResponse(debug_data)
        
    except Exception as e:
        logger.error(f"SCORM debug error: {e}")
        return JsonResponse({'error': str(e)}, status=500)