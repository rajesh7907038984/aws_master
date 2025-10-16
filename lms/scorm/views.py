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

@login_required
def scorm_launch(request, topic_id):
    """Launch a SCORM package"""
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(request.user):
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
        user=request.user,
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
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'launch_url': launch_url,
        'tracking': tracking,
        'user_id': request.user.id,
        'scorm_api_url': f'/scorm/api/{topic_id}/'
    }
    
    return render(request, 'scorm/launch.html', context)

@login_required
def scorm_content(request, topic_id, file_path):
    """Serve SCORM content files"""
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has access to this topic
    if not topic.course.user_has_access(request.user):
        raise Http404("Access denied")
    
    try:
        scorm_package = ELearningPackage.objects.get(topic=topic)
    except ELearningPackage.DoesNotExist:
        raise Http404("E-learning package not found")
    
    if not scorm_package.is_extracted:
        raise Http404("SCORM package not extracted")
    
    # Construct the full file path using the storage system
    if scorm_package.package_file.storage.exists(scorm_package.extracted_path):
        full_path = os.path.join(scorm_package.package_file.storage.path(scorm_package.extracted_path), file_path)
    else:
        raise Http404("SCORM package not found")
    
    if not os.path.exists(full_path):
        raise Http404("File not found")
    
    # Determine content type
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
    
    # Read and serve the file
    try:
        with open(full_path, 'rb') as f:
            content = f.read()
        
        response = HttpResponse(content, content_type=content_type)
        
        # Set appropriate headers for SCORM content
        if file_path.endswith('.html'):
            response['X-Frame-Options'] = 'SAMEORIGIN'
        
        return response
        
    except Exception as e:
        logger.error("Error serving SCORM content: {}".format(str(e)))
        raise Http404("Error serving file")

@csrf_exempt
@require_http_methods(["GET", "POST"])
def scorm_api(request, topic_id):
    """SCORM API endpoint for communication with SCORM packages"""
    if request.method == 'GET':
        return _handle_scorm_get(request, topic_id)
    elif request.method == 'POST':
        return _handle_scorm_post(request, topic_id)

def _handle_scorm_get(request, topic_id):
    """Handle SCORM GET requests (Initialize, GetValue)"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = get_object_or_404(ELearningPackage, topic=topic)
        
        # Get tracking record
        tracking, created = ELearningTracking.objects.get_or_create(
            user=request.user,
            elearning_package=scorm_package
        )
        
        # Get the requested element
        element = request.GET.get('element', '')
        
        if element == 'cmi.core.lesson_status':
            return JsonResponse({'value': tracking.completion_status})
        elif element == 'cmi.core.score.raw':
            return JsonResponse({'value': tracking.score_raw or ''})
        elif element == 'cmi.core.score.min':
            return JsonResponse({'value': tracking.score_min or ''})
        elif element == 'cmi.core.score.max':
            return JsonResponse({'value': tracking.score_max or ''})
        elif element == 'cmi.core.total_time':
            return JsonResponse({'value': str(tracking.total_time) if tracking.total_time else 'PT0S'})
        elif element == 'cmi.core.session_time':
            return JsonResponse({'value': str(tracking.session_time) if tracking.session_time else 'PT0S'})
        elif element == 'cmi.core.entry':
            # Return 'resume' if user has bookmarked content, 'ab-initio' for first time
            has_bookmark = bool(tracking.raw_data.get('cmi.core.lesson_location', ''))
            entry_value = 'resume' if (tracking.first_launch and has_bookmark) else 'ab-initio'
            logger.info(f"SCORM: Getting entry for user {request.user.id}: {entry_value} (has_bookmark: {has_bookmark})")
            return JsonResponse({'value': entry_value})
        elif element == 'cmi.core.exit':
            return JsonResponse({'value': tracking.raw_data.get('cmi.core.exit', '')})
        elif element == 'cmi.core.lesson_location':
            # Return lesson location for bookmarking
            lesson_location = tracking.raw_data.get('cmi.core.lesson_location', '')
            logger.info(f"SCORM: Getting lesson_location for user {request.user.id}: {lesson_location}")
            return JsonResponse({'value': lesson_location})
        elif element == 'cmi.core.student_id':
            return JsonResponse({'value': str(request.user.id)})
        elif element == 'cmi.core.student_name':
            return JsonResponse({'value': request.user.get_full_name() or request.user.username})
        else:
            # Return value from raw_data or empty
            value = tracking.raw_data.get(element, '')
            return JsonResponse({'value': value})
            
    except Exception as e:
        logger.error("Error in SCORM GET: {}".format(str(e)))
        return JsonResponse({'error': str(e)}, status=500)

def _handle_scorm_post(request, topic_id):
    """Handle SCORM POST requests (Commit, SetValue)"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = get_object_or_404(ELearningPackage, topic=topic)
        
        # Get tracking record
        tracking, created = ELearningTracking.objects.get_or_create(
            user=request.user,
            elearning_package=scorm_package
        )
        
        # Get the action
        action = request.POST.get('action', '')
        
        if action == 'SetValue':
            element = request.POST.get('element', '')
            value = request.POST.get('value', '')
            
            # Update tracking based on the element
            if element == 'cmi.core.lesson_status':
                tracking.completion_status = value
            elif element == 'cmi.core.score.raw':
                tracking.score_raw = float(value) if value else None
            elif element == 'cmi.core.score.min':
                tracking.score_min = float(value) if value else None
            elif element == 'cmi.core.score.max':
                tracking.score_max = float(value) if value else None
            elif element == 'cmi.core.total_time':
                tracking.total_time = tracking._parse_scorm_time(value)
            elif element == 'cmi.core.session_time':
                tracking.session_time = tracking._parse_scorm_time(value)
            elif element == 'cmi.core.lesson_location':
                # Store lesson location for bookmarking
                tracking.raw_data['cmi.core.lesson_location'] = value
                logger.info(f"SCORM: Setting lesson_location for user {request.user.id}: {value}")
            elif element == 'cmi.core.exit':
                # Handle all exit values: 'time-out', 'suspend', 'logout', 'normal', 'ab-initio'
                # Store the exit value for proper SCORM compliance
                tracking.raw_data['cmi.core.exit'] = value
                logger.info(f"SCORM: Setting exit value for user {request.user.id}: {value}")
                
                # Handle different exit scenarios
                if value == 'logout':
                    logger.info(f"SCORM: User {request.user.id} manually logged out")
                elif value == 'time-out':
                    logger.info(f"SCORM: User {request.user.id} session timed out")
                elif value == 'suspend':
                    logger.info(f"SCORM: User {request.user.id} suspended session")
                elif value == 'normal':
                    logger.info(f"SCORM: User {request.user.id} completed normally")
            elif element == 'cmi.core.entry':
                # Store entry value for tracking
                tracking.raw_data['cmi.core.entry'] = value
                logger.info(f"SCORM: Setting entry for user {request.user.id}: {value}")
                if value == 'resume':
                    # Handle resume - ensure we have lesson location for bookmarking
                    lesson_location = tracking.raw_data.get('cmi.core.lesson_location', '')
                    if lesson_location:
                        logger.info(f"SCORM: Resuming from bookmark location: {lesson_location}")
            
            # Store in raw_data
            tracking.raw_data[element] = value
            
            # Update timestamps
            tracking.last_launch = timezone.now()
            if not tracking.first_launch:
                tracking.first_launch = timezone.now()
            
            # Check for completion
            if tracking.completion_status == 'completed':
                tracking.completion_date = timezone.now()
            
            tracking.save()
            
            return JsonResponse({'result': 'true'})
            
        elif action == 'Commit':
            # Commit is always successful in our implementation
            return JsonResponse({'result': 'true'})
            
        elif action == 'Initialize':
            # Initialize is always successful
            return JsonResponse({'result': 'true'})
            
        elif action == 'Terminate':
            # Terminate is always successful
            logger.info(f"SCORM: Terminating session for user {request.user.id}")
            
            # Ensure we have the latest exit value
            exit_value = tracking.raw_data.get('cmi.core.exit', 'normal')
            logger.info(f"SCORM: Final exit value for user {request.user.id}: {exit_value}")
            
            # Update last launch time
            tracking.last_launch = timezone.now()
            tracking.save()
            
            return JsonResponse({'result': 'true'})
            
        else:
            return JsonResponse({'result': 'false', 'error': 'Unknown action'})
            
    except Exception as e:
        logger.error("Error in SCORM POST: {}".format(str(e)))
        return JsonResponse({'result': 'false', 'error': str(e)})

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
    for package in scorm_packages:
        completions = tracking_data.filter(
            elearning_package=package,
            completion_status='completed'
        ).count()
        
        completion_stats[package.id] = {
            'total': tracking_data.filter(elearning_package=package).count(),
            'completed': completions,
            'completion_rate': (completions / total_learners * 100) if total_learners > 0 else 0
        }
    
    context = {
        'course': course,
        'scorm_packages': scorm_packages,
        'tracking_data': tracking_data,
        'completion_stats': completion_stats,
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