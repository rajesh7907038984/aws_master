import os
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q
from django.db import OperationalError, DatabaseError, InterfaceError

from .models import Topic, Course, Section
from .views import get_topic_course
from core.utils.db_retry import retry_db_operation, safe_db_query

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

@retry_db_operation(max_attempts=3, delay=1.0)
def topic_view(request, topic_id):
    """View for displaying a topic and its content"""
    try:
        # Get the topic with better error handling and retry logic
        try:
            topic = safe_db_query(
                lambda: Topic.objects.get(id=topic_id),
                max_attempts=3,
                delay=1.0
            )
        except Topic.DoesNotExist:
            logger.error(f"Topic with id {topic_id} does not exist")
            messages.error(request, f"Topic with ID {topic_id} not found")
            return redirect('courses:course_list')
        except ValueError:
            logger.error(f"Invalid topic_id format: {topic_id}")
            messages.error(request, "Invalid topic ID format")
            return redirect('courses:course_list')
        except (OperationalError, DatabaseError, InterfaceError) as e:
            # Check if it's a connection error
            error_str = str(e).lower()
            if any(indicator in error_str for indicator in ['ssl', 'connection', 'eof', 'timeout']):
                logger.error(f"Database connection error loading topic {topic_id}: {e}")
                messages.error(request, "Unable to connect to the database. Please try again in a moment.")
                return redirect('courses:course_list')
            raise
        
        # For Document types, show the PDF in the template instead of redirecting
        # This allows for better error handling and fallback options
        if topic.content_type == 'Document' and topic.content_file:
            logger.info(f"DEBUG: Showing PDF for topic {topic_id} - {topic.title}")
            # Don't redirect, let the template handle the PDF display
        
        # Get the course the topic belongs to with retry logic
        try:
            course = safe_db_query(
                lambda: get_topic_course(topic),
                max_attempts=3,
                delay=1.0
            )
        except (OperationalError, DatabaseError, InterfaceError) as e:
            error_str = str(e).lower()
            if any(indicator in error_str for indicator in ['ssl', 'connection', 'eof', 'timeout']):
                logger.error(f"Database connection error getting course for topic {topic_id}: {e}")
                messages.error(request, "Unable to connect to the database. Please try again in a moment.")
                return redirect('courses:course_list')
            raise
        
        if not course:
            messages.error(request, 'Topic is not associated with any course')
            return redirect('courses:course_list')
        
        # Check if user has permission to access this topic's course (enrollment check)
        # Only enforce for authenticated users; anonymous users handled by course visibility
        if request.user.is_authenticated:
            if not topic.user_has_access(request.user):
                messages.error(request, "You don't have permission to access this content. Please enroll in the course first.")
                return redirect('courses:course_view', course_id=course.id)
            
            # Check sequential progression for learners only
            # Only check if sequential progression is enabled
            if hasattr(request.user, 'role') and request.user.role == 'learner':
                # Skip sequential progression check if it's disabled
                if course.enforce_sequence or course.sequential_progression:
                    if not course.can_access_topic(request.user, topic):
                        # If manual=True, redirect to next available topic instead of course details
                        manual_navigation = request.GET.get('manual', '').lower() == 'true'
                        if manual_navigation:
                            # Find the next available topic the learner can access using the same ordering
                            next_available_topic = None
                            try:
                                # Build the same ordered list used for display (will be built later in the function)
                                # But we need sections here, so get them now
                                from courses.models import Section
                                sections = Section.objects.filter(course=course).order_by('order')
                                
                                # Get all topics for this course that the user can access
                                if request.user.is_authenticated and request.user.role == 'learner':
                                    all_course_topics = Topic.objects.filter(
                                        coursetopic__course=course
                                    ).exclude(
                                        status='draft'
                                    ).exclude(
                                        restrict_to_learners=True,
                                        restricted_learners=request.user
                                    ).order_by('order', 'coursetopic__order', 'created_at')
                                else:
                                    all_course_topics = Topic.objects.filter(
                                        coursetopic__course=course
                                    ).order_by('order', 'coursetopic__order', 'created_at')
                                
                                # Build the same ordered list used for display
                                all_topics_ordered = []
                                
                                # Add topics from each section in order
                                for section in sections:
                                    section_topics_list = all_course_topics.filter(section=section).order_by('order', 'coursetopic__order', 'created_at')
                                    all_topics_ordered.extend(list(section_topics_list))
                                
                                # Add standalone topics (without section) at the end
                                standalone_topics_list = all_course_topics.filter(section__isnull=True).order_by('order', 'coursetopic__order', 'created_at')
                                all_topics_ordered.extend(list(standalone_topics_list))
                                
                                # Find the first topic the learner can access
                                for topic_item in all_topics_ordered:
                                    if course.can_access_topic(request.user, topic_item):
                                        next_available_topic = topic_item
                                        break
                            except Exception as e:
                                logger.error(f"Error finding next available topic: {str(e)}")
                            
                            if next_available_topic:
                                messages.warning(request, f"You must complete previous topics before accessing '{topic.title}'. Redirecting to the next available topic.")
                                return redirect('courses:topic_view', topic_id=next_available_topic.id)
                            else:
                                # Fallback: no accessible topic found, go to course details
                                messages.warning(request, "You must complete previous topics before accessing this one. Please complete the topics in order.")
                                return redirect('courses:course_details', course_id=course.id)
                        else:
                            # Not manual navigation, redirect to course details
                            messages.warning(request, "You must complete previous topics before accessing this one. Please complete the topics in order.")
                            return redirect('courses:course_details', course_id=course.id)
        
        # Simple access - just show the topic content
        logger.info(f"DEBUG: Showing topic {topic_id} - {topic.title}")
        
        # Simple progress tracking for authenticated users only
        topic_progress = None
        is_completed = False
        scorm_enrollment = None
        scorm_is_passed = False
        
        if request.user.is_authenticated:
            try:
                # Only create progress records for learners
                # Instructors, admins, etc. should be able to view topics without tracking progress
                if hasattr(request.user, 'role') and request.user.role == 'learner':
                    # Use get_or_create with course context to ensure consistency with sidebar
                    topic_progress, created = TopicProgress.objects.get_or_create(
                        user=request.user,
                        topic=topic,
                        course=course,  # Add course filter to match sidebar logic
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
                    # Prefer progress with course context to match sidebar logic
                    topic_progress = TopicProgress.objects.filter(
                        user=request.user,
                        topic=topic
                    ).order_by(
                        '-course__id'  # Prefer progress with course context
                    ).first()
                    is_completed = topic_progress.completed if topic_progress else False
                
                # Check SCORM enrollment status if this is a SCORM topic
                # Do this AFTER getting topic_progress so we can sync bookmark data
                if topic.content_type == 'SCORM' and topic.scorm:
                    try:
                        from scorm.models import ScormEnrollment, ScormAttempt
                        scorm_enrollment = ScormEnrollment.objects.filter(
                            user=request.user,
                            topic=topic
                        ).first()
                        if scorm_enrollment:
                            # Check if passed or completed
                            scorm_is_passed = scorm_enrollment.enrollment_status in ['passed', 'completed']
                            
                            # Check for incomplete attempt with resume data
                            # This helps show "Resume" button even if TopicProgress.bookmark isn't synced
                            incomplete_attempt = scorm_enrollment.get_current_attempt()
                            if incomplete_attempt and not scorm_is_passed and topic_progress:
                                # If there's an incomplete attempt with resume data, ensure bookmark is synced
                                if incomplete_attempt.lesson_location or incomplete_attempt.suspend_data:
                                    bookmark_updated = False
                                    if not topic_progress.bookmark:
                                        topic_progress.bookmark = {}
                                    
                                    # Sync lesson_location if it exists in attempt but not in bookmark
                                    if incomplete_attempt.lesson_location and (
                                        not topic_progress.bookmark.get('lesson_location') or 
                                        topic_progress.bookmark.get('lesson_location') != incomplete_attempt.lesson_location
                                    ):
                                        topic_progress.bookmark['lesson_location'] = incomplete_attempt.lesson_location
                                        bookmark_updated = True
                                    
                                    # Sync suspend_data if it exists in attempt but not in bookmark
                                    if incomplete_attempt.suspend_data and (
                                        not topic_progress.bookmark.get('suspend_data') or 
                                        topic_progress.bookmark.get('suspend_data') != incomplete_attempt.suspend_data
                                    ):
                                        topic_progress.bookmark['suspend_data'] = incomplete_attempt.suspend_data
                                        bookmark_updated = True
                                    
                                    if bookmark_updated:
                                        topic_progress.save(update_fields=['bookmark'])
                                        logger.info(
                                            f"Synced bookmark data from ScormAttempt to TopicProgress: "
                                            f"user={request.user.username}, topic_id={topic.id}"
                                        )
                    except ImportError:
                        logger.warning("ScormEnrollment model not found")
                    except Exception as e:
                        logger.error(f"Error checking SCORM enrollment: {str(e)}")
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
            # Include both progress with course context and without (for backward compatibility)
            progress_data = TopicProgress.objects.filter(
                user=request.user,
                topic__in=all_course_topics
            ).filter(
                Q(course=course) | Q(course__isnull=True)
            ).filter(
                completed=True
            )
            
            # Build progress dictionary for template lookup
            for progress in progress_data:
                all_progress[progress.topic.id] = progress
            
            # Also check for completed quiz attempts (especially for initial assessments)
            # that might not have TopicProgress marked as completed yet
            completed_quiz_topics = set()
            try:
                from quiz.models import QuizAttempt
                quiz_topics = all_course_topics.filter(content_type='Quiz', quiz__isnull=False)
                for topic in quiz_topics:
                    if topic.id not in all_progress:
                        # Check if there's a completed quiz attempt
                        completed_attempt = QuizAttempt.objects.filter(
                            quiz=topic.quiz,
                            user=request.user,
                            is_completed=True
                        ).exists()
                        if completed_attempt:
                            completed_quiz_topics.add(topic.id)
                            # Try to get progress for consistency
                            topic_progress = TopicProgress.objects.filter(
                                user=request.user,
                                topic=topic,
                                course=course
                            ).first()
                            if topic_progress:
                                all_progress[topic.id] = topic_progress
            except ImportError:
                pass
            except Exception as e:
                logger.error(f"Error checking quiz attempts for progress: {str(e)}")
            
            # Count completed topics: from progress data + completed quiz attempts
            completed_topics_count = len(all_progress) + len(completed_quiz_topics - set(all_progress.keys()))
        
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
        
        # Check if quiz is an initial assessment and if user has completed it
        has_completed_initial_assessment = False
        can_retake_initial_assessment = False
        remaining_attempts = 0
        if topic.content_type == 'Quiz' and topic.quiz and request.user.is_authenticated:
            try:
                from quiz.models import QuizAttempt
                if topic.quiz.is_initial_assessment:
                    # Check if user has a completed attempt for this initial assessment
                    completed_attempt = QuizAttempt.objects.filter(
                        quiz=topic.quiz,
                        user=request.user,
                        is_completed=True
                    ).order_by('-end_time').first()
                    has_completed_initial_assessment = completed_attempt is not None
                    
                    # Check if user can retake the initial assessment (if attempts are available)
                    if has_completed_initial_assessment:
                        remaining_attempts = topic.quiz.get_remaining_attempts(request.user)
                        can_retake_initial_assessment = (
                            topic.quiz.is_available_for_user(request.user) and
                            (remaining_attempts > 0 or remaining_attempts == -1) and
                            topic.quiz.can_start_new_attempt(request.user)
                        )
            except ImportError:
                logger.warning("QuizAttempt model not found")
            except Exception as e:
                logger.error(f"Error checking initial assessment completion: {str(e)}")
        
        # Get incomplete SCORM attempt for resume button check
        scorm_incomplete_attempt = None
        has_scorm_resume_data = False
        if topic.content_type == 'SCORM' and topic.scorm and not scorm_is_passed:
            try:
                from scorm.models import ScormAttempt
                # First try to get attempt through enrollment if it exists
                if scorm_enrollment:
                    scorm_incomplete_attempt = scorm_enrollment.get_current_attempt()
                else:
                    # If no enrollment, check for incomplete attempts directly
                    scorm_incomplete_attempt = ScormAttempt.objects.filter(
                        user=request.user,
                        topic=topic,
                        completed=False
                    ).order_by('-started_at').first()
                
                if scorm_incomplete_attempt:
                    has_scorm_resume_data = bool(
                        scorm_incomplete_attempt.lesson_location or 
                        scorm_incomplete_attempt.suspend_data
                    )
                    logger.info(
                        f"Found incomplete SCORM attempt for resume check: "
                        f"user={request.user.username}, topic_id={topic.id}, "
                        f"has_location={bool(scorm_incomplete_attempt.lesson_location)}, "
                        f"has_suspend={bool(scorm_incomplete_attempt.suspend_data)}, "
                        f"has_resume_data={has_scorm_resume_data}"
                    )
            except Exception as e:
                logger.error(f"Error getting incomplete SCORM attempt: {str(e)}")
        
        # Also check TopicProgress bookmark as fallback
        has_bookmark_resume_data = False
        if topic_progress and topic_progress.bookmark:
            bookmark = topic_progress.bookmark
            has_bookmark_resume_data = bool(
                bookmark.get('lesson_location') or 
                bookmark.get('suspend_data')
            )
            logger.info(
                f"Checked TopicProgress bookmark for resume: "
                f"user={request.user.username}, topic_id={topic.id}, "
                f"has_bookmark_resume_data={has_bookmark_resume_data}"
            )
        
        # Combined resume check - ensure it's always set
        can_resume_scorm = has_scorm_resume_data or has_bookmark_resume_data
        
        # Log the resume check for debugging
        if topic.content_type == 'SCORM' and topic.scorm:
            logger.info(
                f"SCORM Resume Check: user={request.user.username}, topic_id={topic.id}, "
                f"can_resume_scorm={can_resume_scorm}, "
                f"has_scorm_resume_data={has_scorm_resume_data}, "
                f"has_bookmark_resume_data={has_bookmark_resume_data}, "
                f"scorm_is_passed={scorm_is_passed}, "
                f"scorm_enrollment={scorm_enrollment.id if scorm_enrollment else None}, "
                f"incomplete_attempt={scorm_incomplete_attempt.id if scorm_incomplete_attempt else None}"
            )
        
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
            'access_warning': access_warning,
            'has_completed_initial_assessment': has_completed_initial_assessment,
            'can_retake_initial_assessment': can_retake_initial_assessment,
            'remaining_attempts': remaining_attempts,
            'scorm_enrollment': scorm_enrollment,
            'scorm_is_passed': scorm_is_passed,
            'scorm_incomplete_attempt': scorm_incomplete_attempt,
            'can_resume_scorm': can_resume_scorm  # Always include this, defaults to False if not SCORM
        }
        
        
        return render(request, 'courses/topic_view.html', context)
    
    except (OperationalError, DatabaseError, InterfaceError) as e:
        # Handle database connection errors with user-friendly message
        error_str = str(e).lower()
        if any(indicator in error_str for indicator in ['ssl', 'connection', 'eof', 'timeout', 'syscall']):
            logger.error(f"Database connection error viewing topic {topic_id}: {e}", exc_info=True)
            messages.error(request, "Unable to connect to the database. Please try again in a moment.")
        else:
            logger.error(f"Database error viewing topic {topic_id}: {e}", exc_info=True)
            messages.error(request, "A database error occurred. Please try again later.")
        return redirect('courses:course_list')
    except Exception as e:
        logger.error(f"Error viewing topic {topic_id}: {str(e)}", exc_info=True)
        # Don't expose internal error details to users
        messages.error(request, "An error occurred while loading the topic. Please try again later.")
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
