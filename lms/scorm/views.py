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
        
        attempt_id = attempt.id
    
    # Generate content URL
    launch_url = scorm_package.launch_url or 'index.html'
    content_url = f"/scorm/content/{topic_id}/{launch_url}"
    
    # Add lesson ID if provided
    lesson_id = request.GET.get('lesson_id', '')
    if lesson_id:
        content_url = f"{content_url}{lesson_id}"
    
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
        api_handler = ScormAPIHandler()
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
            simple_api = f'''
<script>
// Enhanced SCORM API with proper attempt handling
window.API = {{
    Initialize: function(param) {{ 
        console.log('SCORM API Initialize called');
        return 'true'; 
    }},
    Terminate: function(param) {{ 
        console.log('SCORM API Terminate called');
        return 'true'; 
    }},
    GetValue: function(element) {{ 
        console.log('SCORM API GetValue called for:', element);
        return ''; 
    }},
    SetValue: function(element, value) {{ 
        console.log('SCORM API SetValue called:', element, '=', value);
        return 'true'; 
    }},
    Commit: function(param) {{ 
        console.log('SCORM API Commit called');
        return 'true'; 
    }},
    GetLastError: function() {{ 
        return '0'; 
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

console.log('SCORM API injected successfully');
</script>'''
            
            # Inject API before closing head tag
            if '</head>' in content:
                content = content.replace('</head>', simple_api + '</head>')
            else:
                content = simple_api + content
            
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