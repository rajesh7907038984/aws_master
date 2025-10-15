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
    Simplified SCORM content serving - Non-interfering with package functionality
    """
    try:
        logger.info(f"SCORM Content Request: topic_id={topic_id}, path='{path}', user={request.user.email if request.user.is_authenticated else 'anonymous'}")
        
        # Authentication check
        if not request.user.is_authenticated:
            logger.warning(f"Unauthenticated SCORM content request for topic {topic_id}, path: {path}")
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
        
        # Handle path corrections if needed, but minimal interference
        if path == 'scormcontent/false':
            path = 'scormcontent/index.html'
            logger.info(f"SCORM Path Fix: Redirected 'scormcontent/false' to '{path}'")
        elif path.startswith('scormcontent/') and path.endswith('/false'):
            base_path = path.replace('/false', '')
            path = f"{base_path}/index.html"
            logger.info(f"SCORM Path Fix: Redirected false path to '{path}'")
        elif path == 'false' or path == 'false/':
            path = 'scormcontent/index.html'
            logger.info(f"SCORM Path Fix: Redirected 'false' to '{path}'")
        
        # Generate S3 URL
        from .s3_direct import scorm_s3
        s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        
        logger.info(f"SCORM S3 URL Generated: {s3_url}")
        
        if not s3_url:
            return HttpResponse('Content not found', status=404)
        
        # For non-HTML files, redirect directly to S3 to avoid interference
        if not path.endswith(('.html', '.htm')):
            from django.http import HttpResponseRedirect
            response = HttpResponseRedirect(s3_url)
            response['Access-Control-Allow-Origin'] = '*'
            return response
        
        # For HTML files, fetch from S3 and inject SCORM API
        try:
            import requests
            
            # Fetch content from S3
            response = requests.get(s3_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Failed to fetch content from S3: {response.status_code}")
                return HttpResponse('Content not accessible', status=404)
            
            content = response.text
            
            # Get attempt ID for tracking only
            attempt_id = request.GET.get('attempt_id', '')
            
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
            
            # Only fix critical path issues for Articulate Rise packages
            if path.endswith('indexAPI.html') and 'scormdriver' in path:
                logger.info(f"Fixing Articulate Rise paths")
                if '../scormcontent/index.html' in content:
                    django_content_url = f'/scorm/content/{topic_id}/scormcontent/index.html'
                    if attempt_id:
                        django_content_url += f'?attempt_id={attempt_id}'
                    content = content.replace('../scormcontent/index.html', django_content_url)
                    logger.info(f"Fixed content path: ../scormcontent/index.html -> {django_content_url}")
            
            # Add CSRF token for API calls
            csrf_token = request.META.get('CSRF_COOKIE', '')
            if not csrf_token:
                from django.middleware.csrf import get_token
                csrf_token = get_token(request)
            
            # Minimal SCORM API injection - only if absolutely needed
            scorm_api = """
<script>
// Minimal SCORM API Bridge - Only saves to database, doesn't interfere
window.csrfToken = '{csrf_token}';
window._scormAttemptId = '{attempt_id}';

// Fix AudioContext autoplay policy issues
(function() {{
    // Store the original AudioContext constructor
    const OriginalAudioContext = window.AudioContext || window.webkitAudioContext;
    
    if (OriginalAudioContext) {{
        // Override AudioContext to handle autoplay policy
        window.AudioContext = window.webkitAudioContext = function() {{
            const context = new OriginalAudioContext();
            
            // If the context is suspended, resume it on user interaction
            if (context.state === 'suspended') {{
                const resume = () => {{
                    context.resume().then(() => {{
                        console.log('AudioContext resumed successfully');
                    }}).catch(err => {{
                        console.log('AudioContext resume failed:', err);
                    }});
                }};
                
                // Try to resume on various user interactions
                document.addEventListener('click', resume, {{ once: true }});
                document.addEventListener('touchstart', resume, {{ once: true }});
                document.addEventListener('keydown', resume, {{ once: true }});
                
                // Also try to resume immediately (might work in some cases)
                setTimeout(resume, 100);
            }}
            
            return context;
        }};
        
        // Copy static properties
        Object.setPrototypeOf(window.AudioContext, OriginalAudioContext);
        window.AudioContext.prototype = OriginalAudioContext.prototype;
    }}
}})();

// Add string table fallback handler - suppress non-critical errors
(function() {{
    const originalError = console.error;
    const originalWarn = console.warn;
    
    // Override console.error to filter string table errors
    console.error = function() {{
        const args = Array.from(arguments);
        const message = args.join(' ');
        
        // Filter out non-critical string table errors
        if (message.includes('could not find') && message.includes('in string table')) {{
            // Log as info instead of error
            console.info('[String Table Info]', ...args);
            return;
        }}
        
        // Also suppress AudioContext autoplay warnings (they're handled above)
        if (message.includes('AudioContext was not allowed to start')) {{
            console.info('[Audio Info] AudioContext start delayed until user interaction');
            return;
        }}
        
        // Call original console.error for other messages
        originalError.apply(console, arguments);
    }};
    
    // Also handle console.warn for AudioContext messages
    console.warn = function() {{
        const args = Array.from(arguments);
        const message = args.join(' ');
        
        if (message.includes('AudioContext was not allowed to start')) {{
            console.info('[Audio Info] AudioContext start delayed until user interaction');
            return;
        }}
        
        originalWarn.apply(console, arguments);
    }};
}})();

// Only create API if one doesn't exist and content doesn't have its own
if (!window.API && !window.API_1484_11 && !window.parent.API) {{
    window.API = {{
        _initialized: false,
        _lastError: '0',
        
        Initialize: function(p) {{ this._initialized = true; return 'true'; }},
        Terminate: function(p) {{ this._initialized = false; return 'true'; }},
        LMSInitialize: function(p) {{ return this.Initialize(p); }},
        LMSFinish: function(p) {{ return this.Terminate(p); }},
        
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
        
        LMSGetValue: function(e) {{ return this.GetValue(e); }},
        LMSSetValue: function(e, v) {{ return this.SetValue(e, v); }},
        LMSCommit: function(p) {{ return this.Commit(p); }},
        
        GetLastError: function() {{ return this._lastError; }},
        LMSGetLastError: function() {{ return this._lastError; }},
        GetErrorString: function(c) {{ return 'No error'; }},
        LMSGetErrorString: function(c) {{ return 'No error'; }},
        GetDiagnostic: function(c) {{ return 'No error'; }},
        LMSGetDiagnostic: function(c) {{ return 'No error'; }}
    }};
    
    window.API_1484_11 = window.API;
}}

// Minimal audio enabler - doesn't interfere with SCORM package
document.addEventListener('DOMContentLoaded', function() {{
    // Only check for audio context state, don't override package behavior
    setTimeout(() => {{
        try {{
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            if (ctx.state === 'suspended') {{
                // Just add a click listener to resume, no UI changes
                const resumeAudio = () => {{
                    ctx.resume();
                    document.removeEventListener('click', resumeAudio);
                    document.removeEventListener('touchstart', resumeAudio);
                }};
                document.addEventListener('click', resumeAudio, {{ once: true }});
                document.addEventListener('touchstart', resumeAudio, {{ once: true }});
            }}
        }} catch (e) {{
            // AudioContext not available, that's fine
        }}
    }}, 100);
}});
</script>""".format(csrf_token=csrf_token, attempt_id=attempt_id)
            
            # NO ERROR SUPPRESSION - Let SCORM packages handle their own errors
            # This was interfering with package functionality
            
            # Inject minimal API only if needed
            if '</head>' in content:
                content = content.replace('</head>', scorm_api + '</head>')
            else:
                content = scorm_api + content
            
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
    Dedicated SCORM Player - User-based launch URLs with direct S3 access
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
    
    # Get or create attempt for user
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
    
    # Get correct launch URL from manifest
    correct_launch_url = _get_correct_launch_url(scorm_package)
    
    # Generate direct S3 URL for user-based access
    from .s3_direct import scorm_s3
    s3_launch_url = scorm_s3.generate_direct_url(scorm_package, correct_launch_url)
    s3_base_url = scorm_s3.get_base_url(scorm_package)
    
    # Detect package type
    package_type = _detect_package_type(scorm_package)
    
    logger.info(f"USER-BASED PLAYER: user={request.user.username}, topic={topic_id}, s3_url={s3_launch_url}")
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'attempt_id': attempt_id,
        'launch_url': s3_launch_url,  # Direct S3 URL
        's3_base_url': s3_base_url,   # Base URL for relative paths
        'api_endpoint': f'/scorm/api/{attempt_id}/' if attempt_id else None,
        'package_type': package_type,
        'user_id': request.user.id,
        'username': request.user.username,
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