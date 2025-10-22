import os
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from .models import Topic, Course, Section
from .views import get_topic_course

# Import TopicProgress and CourseTopic dynamically
try:
    from .models import TopicProgress
except ImportError:
    TopicProgress = None

try:
    from .models import CourseTopic
except ImportError:
    CourseTopic = Course.topics.through if hasattr(Course, "topics") else None

logger = logging.getLogger(__name__)

def topic_view(request, topic_id):
    """View for displaying a topic and its content"""
    try:
        # Get the topic with better error handling
        try:
            topic = Topic.objects.get(id=topic_id)
        except Topic.DoesNotExist:
            logger.error("Topic with id {{topic_id}} does not exist")
            messages.error(request, "Topic with ID {{topic_id}} not found")
            return redirect('courses:course_list')
        except ValueError:
            logger.error("Invalid topic_id format: {{topic_id}}")
            messages.error(request, "Invalid topic ID format")
            return redirect('courses:course_list')
        
        # For Document types, show the PDF in the template instead of redirecting
        # This allows for better error handling and fallback options
        if topic.content_type == 'Document' and topic.content_file:
            logger.info("DEBUG: Showing PDF for topic {{topic_id}} - {{topic.title}}")
            # Don't redirect, let the template handle the PDF display
        
        # Get the course the topic belongs to
        course = get_topic_course(topic)
        if not course:
            messages.error(request, 'Topic is not associated with any course')
            return redirect('courses:course_list')
        
        # Check if user has permission to access this topic's course (enrollment check)
        # Only enforce for authenticated users; anonymous users handled by course visibility
        if request.user.is_authenticated:
            if not topic.user_has_access(request.user):
                messages.error(request, "You don't have permission to access this content. Please enroll in the course first.")
                return redirect('courses:course_view', course_id=course.id)
        
        # Simple access - just show the topic content
        logger.info("DEBUG: Showing topic {{topic_id}} - {{topic.title}}")
        
        # Simple progress tracking for authenticated users only
        topic_progress = None
        is_completed = False
        
        if request.user.is_authenticated:
            try:
                # Use get_or_create to automatically create progress record when learner views topic
                topic_progress, created = TopicProgress.objects.get_or_create(
                    user=request.user,
                    topic=topic,
                    defaults={
                        'completed': False,
                        'completion_method': 'auto'
                    }
                )
                is_completed = topic_progress.completed
                
                # Log creation for debugging
                if created:
                    logger.info(f"Created TopicProgress for user {request.user.username} on topic {topic.id} - {topic.title}")
            except Exception as e:
                logger.error(f"Error creating/getting TopicProgress: {str(e)}")
                topic_progress = None
                is_completed = False
        
        # Update viewing history for authenticated users
        if request.user.is_authenticated:
            request.session['has_viewed_content'] = True
        
        # Check for SCORM tracking data if this is a SCORM topic
        scorm_tracking = None
        can_resume_scorm = False
        scorm_action_text = "Launch Content"
        
        if topic.content_type == 'SCORM' and hasattr(topic, 'elearning_package') and topic.elearning_package:
            if request.user.is_authenticated:
                try:
                    from scorm.models import ELearningTracking
                    scorm_tracking = ELearningTracking.objects.filter(
                        user=request.user,
                        elearning_package=topic.elearning_package
                    ).first()
                    
                    if scorm_tracking:
                        # Check if user has any progress indicators
                        has_bookmark = bool(scorm_tracking.location or scorm_tracking.raw_data.get('cmi.core.lesson_location', ''))
                        has_suspend_data = bool(scorm_tracking.suspend_data or scorm_tracking.raw_data.get('cmi.core.suspend_data', ''))
                        has_progress = scorm_tracking.completion_status not in ['not attempted', 'unknown']
                        has_time = scorm_tracking.total_time and scorm_tracking.total_time.total_seconds() > 0
                        has_score = scorm_tracking.score_raw is not None and scorm_tracking.score_raw > 0
                        
                        # Determine if user can resume
                        can_resume_scorm = (has_bookmark or has_suspend_data or has_progress or has_time or has_score)
                        scorm_action_text = "Resume Content" if can_resume_scorm else "Launch Content"
                        
                        logger.info(f"SCORM Resume Check for user {request.user.username} on topic {topic.id}:")
                        logger.info(f"  - Has bookmark: {has_bookmark}")
                        logger.info(f"  - Has suspend data: {has_suspend_data}")
                        logger.info(f"  - Has progress: {has_progress}")
                        logger.info(f"  - Has time: {has_time}")
                        logger.info(f"  - Has score: {has_score}")
                        logger.info(f"  - Can resume: {can_resume_scorm}")
                        logger.info(f"  - Action text: {scorm_action_text}")
                        
                except Exception as e:
                    logger.error(f"Error checking SCORM tracking: {str(e)}")
        
        # removed functionality removed
        
        # Build proper course content navigation context
        from courses.models import Section
        
        # Import CourseTopic dynamically
        try:
            from courses.models import CourseTopic
        except ImportError:
            from courses.models import Course
            CourseTopic = Course.topics.through if hasattr(Course, "topics") else None
        
        # Get all topics for this course that the user can access
        if request.user.is_authenticated and request.user.role == 'learner':
            # For learners, exclude draft topics and restricted topics
            all_course_topics = Topic.objects.filter(
                coursetopic__course=course
            ).exclude(
                status='draft'
            ).exclude(
                restrict_to_learners=True,
                restricted_learners=request.user
            ).order_by('order', 'coursetopic__order', 'created_at')
        else:
            # For other users, show all topics
            all_course_topics = Topic.objects.filter(
                coursetopic__course=course
            ).order_by('order', 'coursetopic__order', 'created_at')
        
        # Build section_topics structure
        sections = Section.objects.filter(course=course).order_by('order')
        section_topics = []
        
        for section in sections:
            # Get topics in this section
            section_topic_query = all_course_topics.filter(section=section)
            
            if section_topic_query.exists():
                section_topics.append({
                    'section': section,
                    'topics': section_topic_query
                })
        
        # Get topics not in any section
        topics_without_section = all_course_topics.filter(section__isnull=True)
        
        # Build progress data for authenticated learners
        all_progress = {}
        completed_topics_count = 0
        total_topics_count = all_course_topics.count()
        
        if request.user.is_authenticated and request.user.role == 'learner':
            # Get all progress for this user and course
            progress_data = TopicProgress.objects.filter(
                user=request.user,
                topic__in=all_course_topics,
                completed=True
            )
            
            # Build progress dictionary for template lookup
            for progress in progress_data:
                all_progress[progress.topic.id] = progress
            
            completed_topics_count = progress_data.count()
        
        # Find previous and next topics for navigation
        # Build a section-aware ordered list: section topics first (by section order), then standalone topics
        all_topics_list = []
        
        # Add topics from each section in order
        for section in sections:
            section_topics_list = all_course_topics.filter(section=section).order_by('order', 'coursetopic__order', 'created_at')
            all_topics_list.extend(list(section_topics_list))
        
        # Add standalone topics (without section) at the end
        standalone_topics_list = all_course_topics.filter(section__isnull=True).order_by('order', 'coursetopic__order', 'created_at')
        all_topics_list.extend(list(standalone_topics_list))
        
        previous_topic = None
        next_topic = None
        
        try:
            current_index = all_topics_list.index(topic)
            if current_index > 0:
                previous_topic = all_topics_list[current_index - 1]
            if current_index < len(all_topics_list) - 1:
                next_topic = all_topics_list[current_index + 1]
        except ValueError:
            # Topic not found in list, leave as None
            pass
        
        # Set access permissions
        can_access_interactive_content = True
        access_warning = None
        
        if not request.user.is_authenticated:
            can_access_interactive_content = False
            access_warning = "Please log in to access interactive content."
        elif request.user.role not in ['learner', 'instructor', 'admin', 'superadmin', 'globaladmin']:
            can_access_interactive_content = False
            access_warning = "Your account type does not have access to interactive content."
        
        context = {
            'topic': topic,
            'course': course,
            'topic_progress': topic_progress,
            'is_completed': is_completed,
            'section_topics': section_topics,
            'previous_topic': previous_topic,
            'next_topic': next_topic,
            'first_topic': all_topics_list[0] if all_topics_list else None,
            'breadcrumbs': [
                {'label': 'Courses', 'url': reverse('courses:course_list'), 'icon': 'fa-book'},
                {'label': course.title, 'url': reverse('courses:course_details', kwargs={'course_id': course.id}), 'icon': 'fa-graduation-cap'},
                {'label': topic.title}
            ],
            'topics_without_section': topics_without_section,
            'all_progress': all_progress,
            'total_topics_count': total_topics_count,
            'completed_topics_count': completed_topics_count,
            'can_access_interactive_content': can_access_interactive_content,
            'access_warning': access_warning,
            'scorm_tracking': scorm_tracking,
            'can_resume_scorm': can_resume_scorm,
            'scorm_action_text': scorm_action_text,
        }
        
        
        return render(request, 'courses/topic_view.html', context)
    
    except Exception as e:
        logger.error(f"Error viewing topic: {str(e)}")
        messages.error(request, f"Error loading topic: {str(e)}")
        return redirect('courses:course_list')

@login_required
def topic_content(request, topic_id):
    """View for displaying just the content of a topic (for embedding)"""
    # Redirect to topic_view since this is a simplified version
    return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def topic_url_embed(request, topic_id):
    """View for embedding external URL content from a topic"""
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        
        # Check if the topic has a URL to embed
        if not topic.web_url:
            messages.error(request, 'This topic does not have a URL to embed')
            return redirect('courses:topic_view', topic_id=topic_id)
        
        # Check course permission
        course = get_topic_course(topic)
        if not course or not check_course_permission(request.user, course):
            messages.error(request, 'You do not have permission to view this content')
            return redirect('courses:course_list')
        
        context = {
            'topic': topic,
            'course': course,
            'embed_url': topic.web_url
        }
        
        # Simple template that just shows the embedded URL
        return render(request, 'courses/topic_embed.html', context)
    
    except Exception as e:
        logger.error(f"Error embedding topic URL: {str(e)}")
        messages.error(request, f"Error loading embedded content: {str(e)}")
        return redirect('courses:course_list')
