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
from django.utils import timezone

from .models import ScormPackage, ScormAttempt
from .api_handler import ScormAPIHandler
from courses.models import Topic

logger = logging.getLogger(__name__)

# OLD SCORM VIEW REMOVED - Now using dedicated_scorm_player only
# This prevents confusion and conflicts between old and new implementations

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
        
        # Log additional context for scormcontent requests
        if 'scormcontent' in path:
            logger.info(f"🎯 SCORM Course Content Request: {path} - User authenticated: {request.user.is_authenticated}")
        
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
        
        # For JavaScript files, serve through Django to maintain CORS and session context
        if path.endswith('.js'):
            try:
                import requests
                response = requests.get(s3_url, timeout=30)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch JavaScript from S3: {response.status_code}")
                    return HttpResponse('JavaScript file not accessible', status=404)
                
                # Serve JavaScript with optimized headers
                http_response = HttpResponse(response.content, content_type='application/javascript; charset=utf-8')
                http_response['Access-Control-Allow-Origin'] = '*'
                http_response['Cache-Control'] = 'public, max-age=3600, immutable'
                http_response['ETag'] = f'"{hash(response.content)}"'
                return http_response
            except Exception as e:
                logger.error(f"Error serving JavaScript file: {e}")
                return HttpResponse('Error loading JavaScript file', status=500)
        
        # For other non-HTML files (images, CSS, etc.), redirect to S3
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
                    
            # CRITICAL FIX: Handle Articulate Rise packages - Fix relative paths in content
            # For indexAPI.html files, fix the relative path references
            if path.endswith('indexAPI.html') and 'scormdriver' in path:
                logger.info(f"🔧 Fixing Articulate Rise indexAPI.html paths")
                
                # Fix the JavaScript path references in indexAPI.html
                if '../scormcontent/index.html' in content:
                    # Replace relative path with absolute Django URL and add attempt_id
                    django_content_url = f'/scorm/content/{topic_id}/scormcontent/index.html'
                    if attempt_id:
                        django_content_url += f'?attempt_id={attempt_id}'
                    content = content.replace('../scormcontent/index.html', django_content_url)
                    logger.info(f"✅ Fixed content path: ../scormcontent/index.html -> {django_content_url}")
                
                if '../scormcontent/' in content:
                    # Replace all other relative scormcontent paths
                    import re
                    def replace_scormcontent_path(match):
                        relative_path = match.group(1)
                        django_path = f'/scorm/content/{topic_id}/scormcontent/{relative_path}'
                        if attempt_id and 'index.html' in relative_path:
                            django_path += f'?attempt_id={attempt_id}'
                        logger.info(f"🔄 Path fix: ../scormcontent/{relative_path} -> {django_path}")
                        return f'"{django_path}"'
                    
                    content = re.sub(r'["\']\.\.\/scormcontent\/([^"\']+)["\']', replace_scormcontent_path, content)
                
                # Optimized debugging for navigation - reduced size and timing
                debug_script = f"""
<script>
// Articulate Rise Navigation Support
var originalLoadContent = window.LoadContent;
if (typeof LoadContent !== 'undefined') {{
    window.LoadContent = function() {{
        return originalLoadContent.apply(this, arguments);
    }};
}}

// Quick iframe navigation fix
setTimeout(function() {{
    var contentFrame = document.getElementById('content-frame');
    if (contentFrame) {{
        setTimeout(function() {{
            if (contentFrame.src.includes('blank.html')) {{
                contentFrame.src = '/scorm/content/{topic_id}/scormcontent/index.html?attempt_id={attempt_id}';
            }}
        }}, 1500);
    }}
}}, 500);
</script>"""
                content = content.replace('</head>', debug_script + '</head>')
                
            # Optimized path resolution script
            path_resolution_script = f"""
<script>
window.SCORM_TOPIC_ID = {topic_id};
</script>"""
                        
            # Check if this is a Storyline package for enhanced support
            is_storyline = (scorm_package.version == 'storyline' or 
                          'storyline' in str(scorm_package.launch_url).lower() or
                          'story.html' in str(scorm_package.launch_url).lower())
            
            # Add CSRF token to the content
            csrf_token = request.META.get('CSRF_COOKIE', '')
            if not csrf_token:
                from django.middleware.csrf import get_token
                csrf_token = get_token(request)
            
            # Optimized API injection for Storyline - reduced size
            if is_storyline:
                scorm_api = """
<script>
// Optimized Storyline SCORM API
window.csrfToken = '{csrf_token}';
window._scormAttemptId = '{attempt_id}';

(function() {{
    var API = {{
        _initialized: false,
        _lastError: '0',
        
        Initialize: function(p) {{ return this.LMSInitialize(p); }},
        LMSInitialize: function(p) {{ this._initialized = true; return 'true'; }},
        Terminate: function(p) {{ return this.LMSFinish(p); }},
        LMSFinish: function(p) {{ this._initialized = false; return 'true'; }},
        GetValue: function(e) {{ return this.LMSGetValue(e); }},
        SetValue: function(e, v) {{ return this.LMSSetValue(e, v); }},
        Commit: function(p) {{ return this.LMSCommit(p); }},
        
        LMSGetValue: function(element) {{
            if (!this._initialized) return '';
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/scorm/api/{attempt_id}/', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', window.csrfToken);
                xhr.send(JSON.stringify({{method: 'LMSGetValue', parameters: [element]}}));
                return xhr.status === 200 ? JSON.parse(xhr.responseText).result || '' : '';
            }} catch (e) {{ return ''; }}
        }},
        
        LMSSetValue: function(element, value) {{
            if (!this._initialized) return 'false';
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/scorm/api/{attempt_id}/', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', window.csrfToken);
                xhr.send(JSON.stringify({{method: 'LMSSetValue', parameters: [element, value]}}));
                if (xhr.status === 200 && (element.indexOf('lesson_status') > -1 || element.indexOf('score') > -1)) {{
                    setTimeout(() => this.LMSCommit(''), 50);
                }}
                return xhr.status === 200 ? JSON.parse(xhr.responseText).result || 'false' : 'false';
            }} catch (e) {{ return 'false'; }}
        }},
        
        LMSCommit: function(p) {{
            if (!this._initialized) return 'false';
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/scorm/api/{attempt_id}/', false);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-CSRFToken', window.csrfToken);
                xhr.send(JSON.stringify({{method: 'LMSCommit', parameters: []}}));
                return xhr.status === 200 ? JSON.parse(xhr.responseText).result || 'false' : 'false';
            }} catch (e) {{ return 'false'; }}
        }},
        
        GetLastError: function() {{ return this._lastError; }},
        LMSGetLastError: function() {{ return this._lastError; }},
        GetErrorString: function(c) {{ return 'No error'; }},
        LMSGetErrorString: function(c) {{ return 'No error'; }},
        GetDiagnostic: function(c) {{ return 'No error'; }},
        LMSGetDiagnostic: function(c) {{ return 'No error'; }}
    }};
    
    // Expose API efficiently
    window.API = window.API_1484_11 = API;
    if (window.parent !== window) window.parent.API = window.parent.API_1484_11 = API;
    if (window.top !== window) window.top.API = window.top.API_1484_11 = API;
    if (document) document.API = document.API_1484_11 = API;
    
    window.getAPI = window.getAPIHandle = window.findAPI = window.scanForAPI = () => API;
    window.scormAPI = window.SCORM_API = API;
}}());
</script>""".format(csrf_token=csrf_token, attempt_id=attempt_id)
            else:
                scorm_api = """
<script>
// Optimized Standard SCORM API
window.csrfToken = '{csrf_token}';

window.API = {{
    _initialized: false,
    _lastError: '0',
    
    Initialize: function(p) {{ this._initialized = true; return 'true'; }},
    Terminate: function(p) {{ this._initialized = false; return 'true'; }},
    
    GetValue: function(element) {{ 
        if (!this._initialized) return '';
        try {{
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/scorm/api/{attempt_id}/', false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', window.csrfToken);
            xhr.send(JSON.stringify({{method: 'GetValue', parameters: [element]}}));
            return xhr.status === 200 ? JSON.parse(xhr.responseText).result || '' : '';
        }} catch (e) {{ return ''; }}
    }},
    
    SetValue: function(element, value) {{ 
        if (!this._initialized) return 'false';
        try {{
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/scorm/api/{attempt_id}/', false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', window.csrfToken);
            xhr.send(JSON.stringify({{method: 'SetValue', parameters: [element, value]}}));
            return xhr.status === 200 ? JSON.parse(xhr.responseText).result || 'false' : 'false';
        }} catch (e) {{ return 'false'; }}
    }},
    
    Commit: function(p) {{ 
        if (!this._initialized) return 'false';
        try {{
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/scorm/api/{attempt_id}/', false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', window.csrfToken);
            xhr.send(JSON.stringify({{method: 'Commit', parameters: []}}));
            return xhr.status === 200 ? JSON.parse(xhr.responseText).result || 'false' : 'false';
        }} catch (e) {{ return 'false'; }}
    }},
    
    GetLastError: function() {{ return this._lastError; }},
    GetErrorString: function(c) {{ return 'No error'; }},
    GetDiagnostic: function(c) {{ return 'No error'; }}
}};

window.API_1484_11 = window.API;
</script>""".format(csrf_token=csrf_token, attempt_id=attempt_id)
            
            # Optimized error suppression for Storyline
            if is_storyline:
                error_suppression = '''
<script>
// Storyline error suppression
window.addEventListener('error', function(e) { e.preventDefault(); return true; });
window.addEventListener('unhandledrejection', function(e) { e.preventDefault(); });

var originalAlert = window.alert, originalConfirm = window.confirm;
window.alert = function(m) {
    if (typeof m === 'string') {
        var msg = m.toLowerCase();
        if (msg.includes('error') || msg.includes('failed') || msg.includes('cannot') || 
            msg.includes('unable') || msg.includes('scorm') || msg.includes('lms')) return;
    }
    return originalAlert.call(this, m);
};
window.confirm = function(m) {
    if (typeof m === 'string') {
        var msg = m.toLowerCase();
        if (msg.includes('error') || msg.includes('failed') || msg.includes('scorm')) return true;
    }
    return originalConfirm.call(this, m);
};
</script>'''
            else:
                error_suppression = '''
<script>
// Standard SCORM error suppression
window.addEventListener('error', function(e) { e.preventDefault(); return true; });
var originalAlert = window.alert;
window.alert = function(m) {
    if (typeof m === 'string' && (m.toLowerCase().includes('error') || m.toLowerCase().includes('an error has occurred'))) return;
    return originalAlert.call(this, m);
};
</script>'''
            
            if '</head>' in content:
                content = content.replace('</head>', path_resolution_script + scorm_api + error_suppression + '</head>')
            else:
                content = path_resolution_script + scorm_api + error_suppression + content
            
            response = HttpResponse(content, content_type='text/html; charset=utf-8')
            response['Access-Control-Allow-Origin'] = '*'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            # Optimized caching - allow brief caching for performance but ensure SCORM data freshness
            response['Cache-Control'] = 'private, max-age=300'  # 5 minutes cache
            response['Vary'] = 'Cookie, Authorization'
            return response
            
        except Exception as e:
            logger.error(f"Error serving content: {e}")
            return HttpResponse('Error loading content', status=500)
            
    except Exception as e:
        logger.error(f"Error in scorm_content: {e}")
        return HttpResponse('Error loading content', status=500)

# OLD API TEST VIEW REMOVED - No longer needed with dedicated player

@login_required
def dedicated_scorm_player(request, topic_id):
    """
    Dedicated SCORM Player - Clean, simple, and reliable
    Properly handles all SCORM package types with correct launch URLs
    """
    # Get topic and package
    topic = get_object_or_404(
        Topic.objects.select_related('scorm_package'),
        id=topic_id
    )
    
    if not hasattr(topic, 'scorm_package') or not topic.scorm_package:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    scorm_package = topic.scorm_package
    
    # Get or create attempt
    attempt = None
    attempt_id = None
    
    if request.user.is_authenticated:
        # Get the most recent attempt or create new one
        attempt = ScormAttempt.objects.filter(
            user=request.user,
            scorm_package=scorm_package
        ).order_by('-attempt_number').first()
        
        if not attempt:
            # Create new attempt
            attempt = ScormAttempt.objects.create(
                user=request.user,
                scorm_package=scorm_package,
                attempt_number=1,
                lesson_location='',
                suspend_data='',
                lesson_status='not attempted',
                completion_status='incomplete',
                success_status='unknown',
                total_time='0000:00:00.00',
                session_time='0000:00:00.00',
                entry='ab-initio'
            )
            logger.info(f"Created new SCORM attempt {attempt.id} for user {request.user.username}")
        else:
            # Update existing attempt for resume
            attempt.entry = 'resume'
            attempt.last_accessed = timezone.now()
            attempt.save()
            logger.info(f"Resuming SCORM attempt {attempt.id} for user {request.user.username}")
        
        attempt_id = attempt.id
    
    # CRITICAL FIX: Get the correct launch URL from manifest
    correct_launch_url = _get_correct_launch_url(scorm_package)
    
    # Generate content URLs
    current_url = f"/scorm/content/{topic_id}/{scorm_package.launch_url}"
    if correct_launch_url != scorm_package.launch_url:
        correct_url = f"/scorm/content/{topic_id}/{correct_launch_url}"
    else:
        correct_url = current_url
    
    # Add attempt ID if available
    if attempt_id:
        current_url = f"{current_url}?attempt_id={attempt_id}"
        correct_url = f"{correct_url}?attempt_id={attempt_id}"
    
    # Detect package type
    package_type = _detect_package_type(scorm_package)
    
    logger.info(f"DEDICATED PLAYER: topic={topic_id}, package_type={package_type}, current_launch={scorm_package.launch_url}, correct_launch={correct_launch_url}")
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'attempt_id': attempt_id,
        'launch_url': current_url,
        'correct_launch_url': correct_url,
        'package_type': package_type,
    }
    
    return render(request, 'scorm/dedicated_player.html', context)


def _get_correct_launch_url(scorm_package):
    """
    Extract the correct launch URL from SCORM manifest
    FIXED: Properly handles XML namespaces and finds SCO resource
    """
    try:
        import xml.etree.ElementTree as ET
        
        manifest_xml = scorm_package.manifest_data.get('raw_manifest', '')
        if not manifest_xml:
            return scorm_package.launch_url
        
        root = ET.fromstring(manifest_xml)
        
        # CRITICAL FIX: Handle XML namespaces properly
        # Register namespaces
        namespaces = {
            'imscp': 'http://www.imsproject.org/xsd/imscp_rootv1p1p2',
            'adlcp': 'http://www.adlnet.org/xsd/adlcp_rootv1p2'
        }
        
        # Look for resource with adlcp:scormtype="sco" using proper namespace
        resources = root.findall('.//imscp:resource', namespaces)
        if not resources:
            # Fallback: try without namespace
            resources = root.findall('.//resource')
        
        for resource in resources:
            # Check for scormtype attribute with namespace
            scormtype = resource.get('{http://www.adlnet.org/xsd/adlcp_rootv1p2}scormtype', '')
            if not scormtype:
                # Fallback: check without namespace
                scormtype = resource.get('scormtype', '')
            
            if scormtype == 'sco':
                href = resource.get('href', '')
                if href:
                    logger.info(f"✅ Found correct SCO launch URL: {href}")
                    return href
        
        # ENHANCED: Look for scormdriver specifically for Articulate Rise packages
        for resource in resources:
            href = resource.get('href', '')
            if href and 'scormdriver' in href and href.endswith('.html'):
                logger.info(f"✅ Found scormdriver launch URL: {href}")
                return href
        
        # Fallback to first HTML resource
        for resource in resources:
            href = resource.get('href', '')
            if href and href.endswith('.html'):
                logger.info(f"⚠️ Using first HTML resource: {href}")
                return href
                
    except Exception as e:
        logger.error(f"Error parsing manifest for launch URL: {e}")
        logger.info(f"Falling back to stored launch URL: {scorm_package.launch_url}")
    
    return scorm_package.launch_url


def _detect_package_type(scorm_package):
    """
    Detect SCORM package type from structure and manifest
    """
    launch_url = scorm_package.launch_url
    version = scorm_package.version
    
    if 'scormdriver' in launch_url:
        return 'articulate_rise_with_driver'
    elif 'scormcontent' in launch_url:
        return 'articulate_rise_content_only'
    elif 'story.html' in launch_url:
        return 'articulate_storyline'
    elif version == '2004':
        return 'scorm_2004'
    elif version == '1.2':
        return 'scorm_12'
    else:
        return 'unknown'


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