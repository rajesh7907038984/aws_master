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
    # Basic authentication check
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to access SCORM content.")
        return redirect('users:login')
    
    # Get topic and check access
    topic = get_object_or_404(
        Topic.objects.select_related('scorm_package'),
        id=topic_id
    )
    
    # Check user access
    if not topic.user_has_access(request.user):
        messages.error(request, "You need to be enrolled in this course to access the SCORM content.")
        return redirect('courses:course_list')
    
    # Check if topic has SCORM package
    if not hasattr(topic, 'scorm_package') or not topic.scorm_package:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    scorm_package = topic.scorm_package
    
    # Simple attempt handling
    attempt = None
    attempt_id = None
    
    # Get or create attempt
    if request.user.is_authenticated:
        attempt = ScormAttempt.objects.filter(
            user=request.user,
            scorm_package=scorm_package
        ).order_by('-attempt_number').first()
        
        if not attempt:
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
                session_time='0000:00:00.00'
            )
        else:
            # CRITICAL FIX: Check if this should be a resume attempt
            if (attempt.lesson_location and 
                attempt.progress_percentage > 0 and 
                attempt.lesson_status in ['incomplete', 'browsed']):
                attempt.entry = 'resume'
                attempt.save()
                logger.info(f"SCORM Resume: Setting entry mode to 'resume' for attempt {attempt.id}")
        
        attempt_id = attempt.id
    
    # Generate content URL with attempt ID for resume functionality
    launch_url = scorm_package.launch_url or 'index.html'
    content_url = f"/scorm/content/{topic_id}/{launch_url}"
    
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
        
        # Verify user owns this attempt
        if attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
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
    Simplified SCORM content serving - Fixed to properly handle S3 content
    """
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = topic.scorm_package
        
        if not scorm_package:
            return HttpResponse('SCORM package not found', status=404)
        
        # Clean up path
        path = path.lstrip('/')
        if '..' in path or path.startswith('/'):
            return HttpResponse('Invalid path', status=400)
        
        # Generate S3 URL
        from .s3_direct import scorm_s3
        s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        
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
            
            # Add CSRF token to the content
            csrf_token = request.META.get('CSRF_COOKIE', '')
            if not csrf_token:
                from django.middleware.csrf import get_token
                csrf_token = get_token(request)
            
            scorm_api = f'''
<script>
// Add CSRF token for API calls
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
</script>'''
            
            # Inject API before closing head tag
            if '</head>' in content:
                content = content.replace('</head>', scorm_api + '</head>')
            else:
                content = scorm_api + content
            
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
        
        if attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
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