from django import template
from django.template.defaultfilters import stringfilter
from courses.models import TopicProgress, CourseEnrollment, Topic, CourseTopic
import json
from django.utils.safestring import mark_safe
import markdown
from django.utils import timezone
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from quiz.models import Quiz, QuizAttempt
import logging

logger = logging.getLogger(__name__)

register = template.Library()

@register.filter
def add_class(field, class_name):
    """
    Add CSS class to form field widget
    Usage: {{ form.field|add_class:"css-class-name" }}
    """
    if hasattr(field, 'as_widget'):
        return field.as_widget(attrs={'class': class_name})
    return field

@register.filter
def topic_in_section(topics, current_topic):
    """
    Check if a topic is in a section's topics
    Usage: {{ section.topics.all|topic_in_section:current_topic }}
    """
    for topic in topics:
        if topic.id == current_topic.id:
            return True
    return False

@register.filter
def can_manage_course(user, course):
    """Check if user can manage course - Updated to exclude invited instructors from course list edit permissions"""
    # Global Admin and superusers have full access
    if user.is_superuser or user.role == 'globaladmin':
        return True
        
    # Super Admin users (conditional access based on business assignments)
    if user.role == 'superadmin':
        if hasattr(course, 'branch') and course.branch and hasattr(course.branch, 'business'):
            return user.business_assignments.filter(
                business=course.branch.business, 
                is_active=True
            ).exists()
        return False
        
    # Branch Admin users (only within their branch)
    if user.role == 'admin' and course.branch == user.branch:
        return True
        
    # Instructor users (only primary instructors, not invited instructors)
    if user.role == 'instructor' and course.instructor == user:
        return True
        
    # Instructor permissions check
    # Invited instructors should not have manage permissions from course list
    
    return False

@register.filter
def can_manage_topics(user, course):
    """Check if user can manage topics"""
    if user.is_superuser:
        return True
    if user.role == 'admin' and course.branch == user.branch:
        return True
    if user.role == 'instructor':
        # Allow both primary instructor and invited instructors
        if course.instructor == user:
            return True
        # Check for invited instructors with expanded permissions
        invited_instructor = course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__custom_role__name__icontains='instructor',
        ).exists()
        if invited_instructor:
            return True
        # Also check for any instructor with manage permission through course access
        instructor_with_access = course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            course_access__can_modify=True
        ).exists()
        return instructor_with_access
        
    # Check role capability for manage_courses
    if has_manage_courses_capability(user):
        return True
        
    return False

@register.filter
def can_view_course(user, course):
    """Check if user can view course - Aligned with check_course_permission logic"""
    if not user.is_authenticated:
        return False
    
    # Global Admin: FULL access
    if user.role == 'globaladmin' or user.is_superuser:
        return True
    
    # Super Admin: CONDITIONAL access (courses within their business)
    if user.role == 'superadmin':
        if hasattr(course, 'branch') and course.branch:
            return user.business_assignments.filter(
                business=course.branch.business, 
                is_active=True
            ).exists()
        return False
    
    # Branch Admin: CONDITIONAL access (courses within their branch)
    if user.role == 'admin' and course.branch == user.branch:
        return True
    
    # Instructor: CONDITIONAL access (courses they created or assigned to by admin)
    if user.role == 'instructor':
        # 1. Check if user is the assigned instructor
        if course.instructor == user:
            return True
            
        # 2. Check if instructor was assigned to this course by admin through groups
        invited_instructor = course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__custom_role__name__icontains='instructor',
        ).exists()
        
        # 3. Check general instructor access through groups (admin assigned)
        instructor_access = course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True
        ).exists()
        
        if invited_instructor or instructor_access:
            return True
            
        # Instructor can only access courses assigned to them
        return False
    
    # Learner: CONDITIONAL access (courses assigned to them only)
    if user.role == 'learner':
        # For learners, check if course is published (active)
        if not course.is_active:
            return False
            
        # Check enrollment
        if course.enrolled_users.filter(id=user.id).exists():
            return True
            
        # Check group-based access
        group_access = course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__custom_role__can_view=True
        ).exists()
        
        return group_access
        
    return False

@register.filter
def has_group_access(user, course):
    """Check if user has group-based access"""
    if user.role == 'learner':
        return course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__custom_role__can_view=True
        ).exists()
    return course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True
    ).exists()

@register.filter
def has_manage_courses_capability(user):
    """Check if user has the manage_courses capability through any of their roles"""
    if user.is_superuser:
        return True
    if user.role in ['superadmin', 'admin']:
        return True
        
    # Check role capabilities
    from role_management.models import RoleCapability, UserRole
    try:
        user_roles = UserRole.objects.filter(user=user)
        if user_roles.exists():
            for user_role in user_roles:
                if RoleCapability.objects.filter(
                    role=user_role.role,
                    capability='manage_courses'
                ).exists():
                    return True
    except Exception:
        pass
    
    return False

@register.filter
def can_edit_course(user, course):
    """Check if user can edit this course - RBAC v0.1 Compliant
    
    Note: This excludes invited instructors from having edit permissions on course list page.
    Only primary instructors, admins, super admins, and global admins can edit courses.
    """
    # Import the secure permission function
    from courses.views import check_course_edit_permission
    
    try:
        result = check_course_edit_permission(user, course)
        logger.info(f"Template can_edit_course check: user {user.id} -> {result}")
        return result
    except Exception as e:
        logger.error(f"Error in can_edit_course template filter: {str(e)}")
        return False

@register.filter
def get_access_type(user, course):
    """Get the type of access the user has with proper role-based logic"""
    if user.is_superuser:
        return 'superadmin'
    if user.role == 'admin' and course.branch == user.branch:
        return 'admin'
    if user.role == 'instructor' and course.instructor == user:
        return 'instructor'
    
    # Check for instructor enrollment (invited instructor)
    if user.role == 'instructor' and course.enrolled_users.filter(id=user.id).exists():
        return 'invited_instructor'
    
    group_access = course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__custom_role__can_view=True
    ).exists()
    if group_access:
        return 'group'
    
    # Check for learner enrollment
    if user.role == 'learner' and course.enrolled_users.filter(id=user.id).exists():
        return 'enrolled_learner'
    
    return 'none'

@register.filter
def get_user_role_display(user):
    """Get user role display name"""
    return user.get_role_display()

@register.filter
def branch_matches(user, branch):
    """Check if user belongs to branch"""
    return user.branch == branch if user.branch else False

@register.filter
def can_modify(user, course):
    """Check if user can modify course content - RBAC v0.1 Compliant"""
    # Import the secure permission function
    from courses.views import check_course_edit_permission
    
    try:
        result = check_course_edit_permission(user, course)
        logger.info(f"Template can_modify check: user {user.id} -> {result}")
        return result
    except Exception as e:
        logger.error(f"Error in can_modify template filter: {str(e)}")
        return False

@register.filter
def can_delete(user, course):
    """Check if user can delete course - includes group-based instructor permissions"""
    # Super Admin, Global Admin, and regular superusers have delete access
    if user.is_superuser or user.role == 'globaladmin':
        return True
        
    # Super Admin users (conditional access based on business assignments)
    if user.role == 'superadmin':
        if hasattr(course, 'branch') and course.branch and hasattr(course.branch, 'business'):
            return user.business_assignments.filter(
                business=course.branch.business, 
                is_active=True
            ).exists()
        return False
        
    # Branch Admin users (only within their branch)
    if user.role == 'admin' and user.branch == course.branch:
        return True
        
    # Primary Instructor users (only for courses they are assigned to)
    if user.role == 'instructor' and course.instructor == user:
        return True
        
    # Group-assigned instructors with content management permissions can delete
    if user.role == 'instructor':
        from groups.models import CourseGroupAccess
        can_delete_group = CourseGroupAccess.objects.filter(
            course=course,
            group__memberships__user=user,
            group__memberships__is_active=True,
            group__memberships__custom_role__can_manage_content=True,
            can_modify=True
        ).exists()
        return can_delete_group
    
    return False

@register.simple_tag
def get_user_groups(user, course):
    """Get all active groups user belongs to for this course"""
    return user.group_memberships.filter(
        group__in=course.accessible_groups.all(),
        is_active=True
    ).select_related('group', 'custom_role')

@register.filter
def group_can_modify(user, course):
    """Check if user has group-based modification rights"""
    if not user.role == 'instructor':
        return False
    return course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__custom_role__can_manage_content=True,
        course_access__can_modify=True
    ).exists()

@register.filter
def get_progress(course, user):
    """
    Gets progress data for a specific user and course
    Usage: {{ course|get_progress:user }}
    """
    progress = {
        'status': 'not_started',
        'progress': 0,
        'percentage': 0,
        'score': None,
        'last_accessed': None,
        'completed_topics': 0,
        'total_topics': course.topics.count()
    }
    
    # Get enrollment progress
    enrollment = CourseEnrollment.objects.filter(user=user, course=course).first()
    if enrollment:
        # Get topic progress
        topic_progress = TopicProgress.objects.filter(
            user=user,
            topic__coursetopic__course=course
        )
        completed_topics = topic_progress.filter(completed=True).count()
        total_topics = course.topics.count()
        
        if completed_topics > 0:
            progress['completed_topics'] = completed_topics
            calculated_progress = round((completed_topics / total_topics) * 100)
            progress['progress'] = calculated_progress
            progress['percentage'] = calculated_progress
            
            if completed_topics == total_topics:
                progress['status'] = 'completed'
                # Get final score if available
                final_score = topic_progress.filter(
                    topic__content_type='Quiz',
                    completed=True
                ).order_by('-completed_at').first()
                
                if final_score and 'score' in final_score.progress_data:
                    progress['score'] = round(final_score.progress_data['score'])
            else:
                progress['status'] = 'in_progress'
                
            # Get last accessed time
            last_progress = topic_progress.order_by('-last_accessed').first()
            if last_progress:
                progress['last_accessed'] = last_progress.last_accessed
                
    return progress

@register.filter
def get_user_progress(topic, user):
    """Get progress for a specific user on a topic"""
    try:
        return topic.user_progress.filter(user=user).first()
    except:
        return None

@register.filter
@stringfilter
def endswith(value, arg):
    """Check if a string ends with the specified argument"""
    return value.lower().endswith(arg.lower())

@register.filter
def get_topic_progress(topic, user):
    """Get topic progress for a user"""
    if not user or not user.is_authenticated:
        return None
        
    progress = TopicProgress.objects.filter(topic=topic, user=user).first()
    
    # Initialize progress if it doesn't exist
    if not progress:
        try:
            progress = TopicProgress.objects.create(topic=topic, user=user, completed=False)
            progress.init_progress_data()
        except Exception as e:
            logger.error(f"Error creating topic progress: {str(e)}")
            return None
    
    # For SCORM topics, check if completion status is out of sync
    if topic.content_type == 'SCORM' and progress:
        # Check if progress_data indicates completion but completed field is False
        if (not progress.completed and 
            isinstance(progress.progress_data, dict) and 
            progress.progress_data.get('completion_status') in ['completed', 'passed']):
            
            # Sync the completion status (restored for real-time sync)
            progress.completed = True
            progress.completion_method = 'scorm'
            if not progress.completed_at:
                progress.completed_at = timezone.now()
            progress.save()
            logger.info(f"Auto-fixed SCORM completion status for topic {topic.id}, user {user.username}")
            
        # Enhanced SCORM sync with latest attempt
        from scorm.models import ScormAttempt
        latest_attempt = ScormAttempt.objects.filter(
            user=user,
            scorm_package__topic=topic
        ).order_by('-id').first()
        
        if latest_attempt:
            # Sync completion status from latest attempt
            if latest_attempt.lesson_status in ['completed', 'passed']:
                if not progress.completed:
                    progress.completed = True
                    progress.completion_method = 'scorm'
                    progress.last_score = latest_attempt.score_raw
                    if not progress.completed_at:
                        progress.completed_at = timezone.now()
                    progress.save()
                    logger.info(f"🔄 TEMPLATE SYNC: Fixed SCORM completion for topic {topic.id}, user {user.username}")
            
            # Update progress_data with latest SCORM data
            if not isinstance(progress.progress_data, dict):
                progress.progress_data = {}
            
            progress.progress_data.update({
                'scorm_attempt_id': latest_attempt.id,
                'lesson_status': latest_attempt.lesson_status,
                'completion_status': latest_attempt.completion_status,
                'success_status': latest_attempt.success_status,
                'score_raw': float(latest_attempt.score_raw) if latest_attempt.score_raw else None,
                'last_updated': timezone.now().isoformat(),
                'scorm_sync': True,
            })
            
            # Update scores
            if latest_attempt.score_raw is not None:
                progress.last_score = latest_attempt.score_raw
                if progress.best_score is None or latest_attempt.score_raw > progress.best_score:
                    progress.best_score = latest_attempt.score_raw
            
            progress.save()
        elif not progress.completed:
            try:
                from scorm.models import ScormAttempt, ScormPackage
                # Check if this topic has a SCORM package
                try:
                    scorm_package = ScormPackage.objects.get(topic=topic)
                    # Get the user's latest attempt
                    latest_attempt = ScormAttempt.objects.filter(
                        user=user,
                        scorm_package=scorm_package
                    ).order_by('-attempt_number').first()
                    
                    if latest_attempt:
                        # Check completion based on SCORM version
                        is_completed = False
                        if scorm_package.version == '1.2':
                            is_completed = latest_attempt.lesson_status in ['completed', 'passed']
                        else:  # SCORM 2004
                            is_completed = latest_attempt.completion_status == 'completed'
                        
                        if is_completed:
                            progress.completed = True
                            progress.completion_method = 'scorm'
                            if not progress.completed_at:
                                progress.completed_at = timezone.now()
                            progress.save()
                            logger.info(f"Auto-synced SCORM completion from native attempt for topic {topic.id}, user {user.username}")
                except ScormPackage.DoesNotExist:
                    pass  # Topic doesn't have a SCORM package
            except Exception as e:
                logger.error(f"Error checking SCORM attempt for topic {topic.id}, user {user.username}: {str(e)}")
    
    # For quiz topics, check if there's a passing attempt
    elif topic.content_type == 'Quiz' and progress:
        # Get the quiz associated with this topic
        quiz = Quiz.objects.filter(topics=topic).first()
        if quiz:
            # Check if there's a passing attempt
            passing_attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                user=user,
                end_time__isnull=False,
                score__gte=quiz.passing_score
            ).exists()
            
            # Update progress status based on quiz attempts
            if passing_attempt:
                progress.completed = True
            else:
                progress.completed = False
                
            # Save the updated progress
            progress.save()
    
    return progress

@register.filter
def subtract(value, arg):
    """Subtract the arg from the value"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def uncompleted_count(topics, user):
    """Count uncompleted topics for a user"""
    count = 0
    for topic in topics:
        progress = topic.get_user_progress(user)
        if not progress or not progress.completed:
            count += 1
    return count

@register.filter
def get_scorm_status(topic, user):
    """Get SCORM completion status for a topic"""
    if topic.content_type == 'SCORM':
        tracking = TopicProgress.objects.filter(
            topic=topic,
            user=user
        ).first()
        if tracking:
            return {
                'status': tracking.completed,
                'progress': tracking.progress_data.get('completion_percent', 0) if tracking.progress_data else 0,
                'score': tracking.last_score
            }
    return None

@register.filter
def get_item(dictionary, key):
    """Custom template filter to access dictionary elements by key"""
    if not dictionary:
        return None
        
    return dictionary.get(str(key))

@register.filter
def map(items, attribute):
    """
    Extract specified attribute from each item in a list
    Usage: {{ items|map:"attribute" }}
    """
    if not items:
        return []
    result = []
    for item in items:
        try:
            if isinstance(item, dict):
                result.append(item.get(attribute))
            else:
                result.append(getattr(item, attribute))
        except (AttributeError, KeyError, TypeError):
            result.append(None)
    return result

@register.filter
@stringfilter
def split(value, delimiter=','):
    """Split a string into a list using the specified delimiter"""
    if not value:
        return []
    return [x.strip() for x in value.split(delimiter)]

@register.filter
@stringfilter
def parse_json(value):
    """Parse a JSON string into a Python object"""
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {'html': '', 'delta': ''}

@register.filter
def strip(value):
    """Strip whitespace from string"""
    if value is None:
        return ''
    return str(value).strip()

@register.filter
def lower(value):
    """Convert string to lowercase"""
    if value is None:
        return ''
    return str(value).lower()

@register.filter
def endswith(value, suffix):
    """Check if string ends with suffix"""
    if value is None:
        return False
    return str(value).endswith(suffix)

@register.filter
def get_user_attempts(quiz, user):
    """Get quiz attempts for a specific user"""
    try:
        return quiz.attempts.filter(user=user).order_by('-started_at')[:5]  # Get last 5 attempts
    except:
        return None

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divided_by(value, arg):
    """Divide the value by the argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def user_course_progress(course, user):
    """
    Calculate the percentage of course completion for a user
    Usage: {{ course|user_course_progress:request.user }}
    """
    total_topics = course.topics.count()
    if total_topics == 0:
        return 0
    
    completed_topics = TopicProgress.objects.filter(
        user=user,
        topic__coursetopic__course=course,
        completed=True
    ).count()
    
    progress = int((completed_topics / total_topics) * 100)
    return progress

@register.filter
def next_incomplete_topic(course, user):
    """Return the next topic that needs to be completed"""
    if not user.is_authenticated:
        return None
        
    topics = Topic.objects.filter(coursetopic__course=course).order_by('order', 'coursetopic__order', 'created_at')
    
    for topic in topics:
        # Get progress for this topic
        progress, created = TopicProgress.objects.get_or_create(
            topic=topic,
            user=user,
            defaults={'completed': False}
        )
        
        # If not completed, this is our next topic
        if not progress.completed:
            return topic
            
    # All topics completed
    return None

@register.filter
def is_completed(topic, user):
    """Check if a topic is completed by the user"""
    if not user.is_authenticated:
        return False
        
    try:
        progress = TopicProgress.objects.get(topic=topic, user=user)
        
        # For SCORM content, also check progress_data for completion status
        if topic.content_type == 'SCORM':
            # Check main completed field first
            if progress.completed:
                return True
                
            # If not completed, check if progress_data indicates completion
            if (isinstance(progress.progress_data, dict) and 
                progress.progress_data.get('completion_status') in ['completed', 'passed']):
                # Auto-fix the completion status (restored for real-time sync)
                progress.completed = True
                progress.completion_method = 'scorm'
                if not progress.completed_at:
                    progress.completed_at = timezone.now()
                progress.save()
                logger.info(f"Auto-fixed SCORM completion in is_completed filter for topic {topic.id}, user {user.username}")
                return True
        
        return progress.completed
    except TopicProgress.DoesNotExist:
        return False

@register.filter
def has_completed_topic(user, topic):
    """Check if a user has completed the topic (reverse parameter order of is_completed)"""
    if not user.is_authenticated:
        return False
        
    try:
        progress = TopicProgress.objects.get(topic=topic, user=user)
        return progress.completed
    except TopicProgress.DoesNotExist:
        return False

@register.filter
def is_complete_for_user(topic, user):
    """Check if a topic is completed for a user"""
    if not user or not user.is_authenticated:
        return False
    return TopicProgress.objects.filter(
        user=user,
        topic=topic,
        completed=True
    ).exists()

@register.filter
def last_part(value):
    """
    Extract the last part of a file path (the filename).
    Works with both string paths and Django FileField objects.
    """
    if value is None:
        return ''
    
    # Handle Django FileField objects
    if hasattr(value, 'name'):
        value = value.name
    
    # Convert to string if needed
    value = str(value)
    
    # Use os.path.basename to extract filename
    import os
    return os.path.basename(value)

@register.filter
def format_course_title(title):
    """
    Format course title for display:
    - Ensures title is a string
    - Removes unnecessary whitespace
    - Ensures proper capitalization
    - Handles any special characters
    """
    if not title:
        return "Untitled Course"
        
    # Ensure title is a string
    title = str(title).strip()
    
    # Remove any excessive whitespace
    title = ' '.join(title.split())
    
    # If title is all uppercase or lowercase, convert to title case
    if title.isupper() or title.islower():
        title = title.title()
        
    return title

@register.filter
def can_delete_topic(user, topic):
    """Check if user can delete a topic - uses proper permission checks"""
    # Get the course for this topic
    course_topic = CourseTopic.objects.filter(topic=topic).first()
    if not course_topic:
        return False
        
    course = course_topic.course
    
    # Use the topic edit permission check which includes all proper group access logic
    from courses.views import check_topic_edit_permission
    return check_topic_edit_permission(user, topic, course, check_for='delete')

@register.filter
def scorm_cloud_content_exists(topic_id):
    """Check if SCORM content exists for topic (native SCORM implementation)"""
    try:
        from scorm.models import ScormPackage
        from courses.models import Topic
        topic = Topic.objects.get(id=topic_id)
        return hasattr(topic, 'scorm_package')
    except:
        return False

@register.filter
def contains_id(queryset, id_to_check):
    """
    Check if a queryset of items contains an item with the specified ID
    Usage: {{ section.topics.all|contains_id:topic.id }}
    """
    return any(item.id == id_to_check for item in queryset)

@register.filter
def in_list(value, list_str):
    """Check if value is in a comma-separated list of strings"""
    if value is None:
        return False
    items = [item.strip() for item in list_str.split(',')]
    return str(value) in items

@register.filter
def get_course_certificate(user, course):
    """Get the certificate issued to the user for a specific course"""
    try:
        from certificates.models import IssuedCertificate
        return IssuedCertificate.objects.filter(
            recipient=user,
            course_name=course.title
        ).order_by('-issue_date').first()
    except (ImportError, Exception):
        return None

@register.filter
def contains_text(value, arg):
    """
    Check if value contains arg (text-based)
    """
    try:
        return arg in value
    except (TypeError, ValueError):
        return False

@register.filter
def add(value, arg):
    """Add two values together"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return value
        
@register.filter
def is_enrolled(course, user):
    """Check if a user is enrolled in a course"""
    try:
        return CourseEnrollment.objects.filter(course=course, user=user).exists()
    except Exception as e:
        logger.error(f"Error checking enrollment: {str(e)}")
        return False
        
@register.filter
def get_enrollment(course, user):
    """Get the enrollment object for a user in a course"""
    try:
        return CourseEnrollment.objects.filter(course=course, user=user).first()
    except Exception as e:
        logger.error(f"Error retrieving enrollment: {str(e)}")
        return None

@register.filter
def filter_topics_with_documents(topics):
    """
    Filter topics that have document files attached (PDF or Word documents)
    
    Usage: {% with pdf_docs=course.topics.all|filter_topics_with_documents %}
    """
    result = []
    for topic in topics:
        if topic.content_type == 'Document' and hasattr(topic, 'content_file') and topic.content_file:
            filename = topic.content_file.name.lower()
            if filename.endswith('.pdf') or filename.endswith('.doc') or filename.endswith('.docx'):
                result.append(topic)
    return result

@register.filter
def filename(path):
    """
    Return just the filename from a path
    
    Usage: {{ topic.document_file.name|filename }}
    """
    import os
    return os.path.basename(path)

@register.filter
def file_extension(path):
    """
    Return just the file extension from a path
    
    Usage: {{ topic.document_file.name|file_extension }}
    """
    import os
    _, ext = os.path.splitext(path)
    return ext.lstrip('.')

@register.filter
def contains(queryset, user):
    """Check if a user is in a queryset - handles None values"""
    if queryset is None or user is None:
        return False
    try:
        return queryset.filter(id=user.id).exists()
    except (AttributeError, TypeError):
        return False

@register.filter
def has_scorm_resume(topic, user):
    """
    Check if a user has started a SCORM course but hasn't completed it
    This is used to show "Resume" button instead of "Start" button
    
    Usage: {{ topic|has_scorm_resume:user }}
    """
    if not user or not user.is_authenticated:
        return False
    
    if topic.content_type != 'SCORM':
        return False
    
    try:
        from scorm.models import ScormAttempt, ScormPackage
        scorm_package = ScormPackage.objects.get(topic=topic)
        
        # Check if user has any attempt (started the course)
        has_attempt = ScormAttempt.objects.filter(
            user=user,
            scorm_package=scorm_package
        ).exists()
        
        if has_attempt:
            # Check if the attempt is incomplete (not completed/passed)
            latest_attempt = ScormAttempt.objects.filter(
                user=user,
                scorm_package=scorm_package
            ).order_by('-attempt_number').first()
            
            if latest_attempt and latest_attempt.lesson_status in ['incomplete', 'not_attempted']:
                # ENHANCED: Only show resume if there's actual progress or legitimate resume scenario
                # This prevents showing "Resume" for attempts that never actually started
                has_progress = (
                    latest_attempt.lesson_location or 
                    latest_attempt.suspend_data or 
                    latest_attempt.lesson_status == 'incomplete' or
                    latest_attempt.entry == 'resume'
                )
                
                if has_progress:
                    return True
                else:
                    # No actual progress - this is likely a failed start, show "Start" instead
                    logger.info(f"SCORM Resume Check: No progress found for user {user.username}, topic {topic.id}")
                    return False
        
        return False
    except Exception as e:
        logger.warning(f"Error checking SCORM resume for topic {topic.id}: {str(e)}")
        return False