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
    CourseTopic = None

logger = logging.getLogger(__name__)

def topic_view(request, topic_id):
    """View for displaying a topic and its content"""
    try:
        # Get the topic with better error handling
        try:
            topic = Topic.objects.get(id=topic_id)
        except Topic.DoesNotExist:
            logger.error(f"Topic with id {topic_id} does not exist")
            messages.error(request, f"Topic with ID {topic_id} not found")
            return redirect('courses:course_list')
        except ValueError:
            logger.error(f"Invalid topic_id format: {topic_id}")
            messages.error(request, "Invalid topic ID format")
            return redirect('courses:course_list')
        
        # For Document types, show the PDF in the template instead of redirecting
        # This allows for better error handling and fallback options
        if topic.content_type == 'Document' and topic.content_file:
            logger.info(f"DEBUG: Showing PDF for topic {topic_id} - {topic.title}")
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
        logger.info(f"DEBUG: Showing topic {topic_id} - {topic.title}")
        
        # Simple progress tracking for authenticated users only
        topic_progress = None
        is_completed = False
        
        if request.user.is_authenticated:
            try:
                # Only create progress records for learners
                # Instructors, admins, etc. should be able to view topics without tracking progress
                if hasattr(request.user, 'role') and request.user.role == 'learner':
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
                else:
                    # For non-learners (instructors, admins), just check if progress exists but don't create
                    topic_progress = TopicProgress.objects.filter(
                        user=request.user,
                        topic=topic
                    ).first()
                    is_completed = topic_progress.completed if topic_progress else False
            except Exception as e:
                logger.error(f"Error creating/getting TopicProgress: {str(e)}")
                topic_progress = None
                is_completed = False
        
        # Update viewing history for authenticated users
        if request.user.is_authenticated:
            request.session['has_viewed_content'] = True
        
        # Build proper course content navigation context
        from courses.models import Section
        
        # Import CourseTopic dynamically
        try:
            from courses.models import CourseTopic
        except ImportError:
            CourseTopic = None
        
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
                {'label': 'Courses', 'url': '/courses/', 'icon': 'fa-book'},
                {'label': course.title, 'url': f'/courses/{course.id}/details/', 'icon': 'fa-graduation-cap'},
                {'label': topic.title}
            ],
            'topics_without_section': topics_without_section,
            'all_progress': all_progress,
            'total_topics_count': total_topics_count,
            'completed_topics_count': completed_topics_count,
            'can_access_interactive_content': can_access_interactive_content,
            'access_warning': access_warning
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
