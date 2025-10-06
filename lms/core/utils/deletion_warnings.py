"""
Utility functions for generating deletion warning messages and handling cascade deletion confirmations.
"""

from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe


def get_deletion_warning_message(obj_type, obj_name, related_data_count):
    """
    Generate a comprehensive warning message for deletion operations.
    
    Args:
        obj_type (str): Type of object being deleted (Topic, Course, User)
        obj_name (str): Name/title of the object being deleted
        related_data_count (dict): Dictionary with counts of related data
    
    Returns:
        str: HTML formatted warning message
    """
    
    if obj_type.lower() == 'topic':
        return _get_topic_deletion_warning(obj_name, related_data_count)
    elif obj_type.lower() == 'course':
        return _get_course_deletion_warning(obj_name, related_data_count)
    elif obj_type.lower() == 'user':
        return _get_user_deletion_warning(obj_name, related_data_count)
    else:
        return _get_generic_deletion_warning(obj_name, related_data_count)


def _get_topic_deletion_warning(topic_name, related_data_count):
    """Generate warning message for topic deletion."""
    
    warning_parts = [
        f"<strong> WARNING: You are about to delete the topic '{topic_name}'</strong>",
        "<br><br>",
        "<strong>This action will permanently delete ALL related data including:</strong>",
        "<ul>"
    ]
    
    if related_data_count.get('progress_records', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['progress_records']}</strong> student progress records</li>")
    
    if related_data_count.get('assignments', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['assignments']}</strong> linked assignments and all their submissions</li>")
    
    if related_data_count.get('quiz_attempts', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['quiz_attempts']}</strong> quiz attempts and answers</li>")
    
    if related_data_count.get('discussion_comments', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['discussion_comments']}</strong> discussion comments and attachments</li>")
    
    if related_data_count.get('gradebook_entries', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['gradebook_entries']}</strong> gradebook entries</li>")
    
    if related_data_count.get('report_templates', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['report_templates']}</strong> report templates</li>")
    
    if related_data_count.get('scorm_content', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['scorm_content']}</strong> SCORM content and files</li>")
    
    if related_data_count.get('uploaded_files', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['uploaded_files']}</strong> uploaded files</li>")
    
    warning_parts.extend([
        "</ul>",
        "<br>",
        "<strong style='color: #dc3545;'> THIS ACTION CANNOT BE UNDONE!</strong>",
        "<br><br>",
        "All student progress, submissions, and related data will be permanently lost.",
        "<br><br>",
        "<strong>Are you absolutely sure you want to proceed?</strong>"
    ])
    
    return mark_safe(''.join(warning_parts))


def _get_course_deletion_warning(course_name, related_data_count):
    """Generate warning message for course deletion."""
    
    warning_parts = [
        f"<strong> WARNING: You are about to delete the course '{course_name}'</strong>",
        "<br><br>",
        "<strong>This action will permanently delete ALL related data including:</strong>",
        "<ul>"
    ]
    
    if related_data_count.get('enrollments', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['enrollments']}</strong> student enrollments</li>")
    
    if related_data_count.get('topics', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['topics']}</strong> topics and all their content</li>")
    
    if related_data_count.get('sections', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['sections']}</strong> course sections</li>")
    
    if related_data_count.get('assignments', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['assignments']}</strong> assignments and all submissions</li>")
    
    if related_data_count.get('gradebook_entries', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['gradebook_entries']}</strong> gradebook entries</li>")
    
    if related_data_count.get('report_templates', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['report_templates']}</strong> report templates</li>")
    
    if related_data_count.get('scorm_content', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['scorm_content']}</strong> SCORM content and files</li>")
    
    if related_data_count.get('uploaded_files', 0) > 0:
        warning_parts.append(f"<li><strong>{related_data_count['uploaded_files']}</strong> course files and media</li>")
    
    warning_parts.extend([
        "</ul>",
        "<br>",
        "<strong style='color: #dc3545;'> THIS ACTION CANNOT BE UNDONE!</strong>",
        "<br><br>",
        "All student progress, enrollments, and course content will be permanently lost.",
        "<br><br>",
        "<strong>Are you absolutely sure you want to proceed?</strong>"
    ])
    
    return mark_safe(''.join(warning_parts))


def _get_user_deletion_warning(user_name, related_data_count):
    """Generate warning message for user deletion."""
    
    # Simple confirmation message without detailed warnings
    warning_parts = [
        f"<strong>Are you sure you want to delete the user '{user_name}'?</strong>",
        "<br><br>",
        "This action cannot be undone."
    ]
    
    return mark_safe(''.join(warning_parts))


def _get_generic_deletion_warning(obj_name, related_data_count):
    """Generate generic warning message for deletion."""
    
    warning_parts = [
        f"<strong> WARNING: You are about to delete '{obj_name}'</strong>",
        "<br><br>",
        "<strong>This action will permanently delete ALL related data.</strong>",
        "<br><br>",
        "<strong style='color: #dc3545;'> THIS ACTION CANNOT BE UNDONE!</strong>",
        "<br><br>",
        "All related data will be permanently lost.",
        "<br><br>",
        "<strong>Are you absolutely sure you want to proceed?</strong>"
    ]
    
    return mark_safe(''.join(warning_parts))


def get_related_data_counts(obj):
    """
    Get counts of related data for an object to include in warning messages.
    
    Args:
        obj: The object being deleted (Topic, Course, or User)
    
    Returns:
        dict: Dictionary with counts of related data
    """
    counts = {}
    
    try:
        if hasattr(obj, 'title'):  # Topic or Course
            if hasattr(obj, 'content_type'):  # Topic
                counts['progress_records'] = obj.user_progress.count()
                counts['assignments'] = obj.topicassignment_set.count()
                counts['quiz_attempts'] = 0
                if hasattr(obj, 'quiz') and obj.quiz:
                    counts['quiz_attempts'] = obj.quiz.quizattempt_set.count()
                counts['discussion_comments'] = 0
                if hasattr(obj, 'topic_discussion') and obj.topic_discussion:
                    counts['discussion_comments'] = obj.topic_discussion.comments.count()
                counts['gradebook_entries'] = 0
                try:
                    from gradebook.models import Grade
                    counts['gradebook_entries'] = Grade.objects.filter(topic=obj).count()
                except:
                    pass
                counts['report_templates'] = 0
                counts['scorm_content'] = 0
                counts['uploaded_files'] = 1 if obj.content_file else 0
                
            else:  # Course
                counts['enrollments'] = obj.courseenrollment_set.count()
                counts['topics'] = obj.topics.count()
                counts['sections'] = obj.sections.count()
                counts['assignments'] = obj.course_assignments.count()
                counts['gradebook_entries'] = 0
                try:
                    from gradebook.models import Grade
                    counts['gradebook_entries'] = Grade.objects.filter(course=obj).count()
                except:
                    pass
                counts['report_templates'] = 0
                counts['scorm_content'] = 0
                counts['uploaded_files'] = 0
                if obj.course_image:
                    counts['uploaded_files'] += 1
                if obj.course_video:
                    counts['uploaded_files'] += 1
                    
        elif hasattr(obj, 'username'):  # User
            counts['enrollments'] = obj.courseenrollment_set.count()
            counts['progress_records'] = obj.topic_progress.count()
            counts['submissions'] = obj.assignment_submissions.count()
            counts['quiz_attempts'] = obj.quizattempt_set.count()
            counts['group_memberships'] = obj.groupmembership_set.count()
            counts['gradebook_entries'] = 0
            try:
                from gradebook.models import Grade
                counts['gradebook_entries'] = Grade.objects.filter(student=obj).count()
            except:
                pass
            counts['user_files'] = 0
            if obj.profile_image:
                counts['user_files'] += 1
            if obj.cv_file:
                counts['user_files'] += 1
            if obj.statement_of_purpose_file:
                counts['user_files'] += 1
            counts['discussion_comments'] = obj.comment_set.count()
            counts['assigned_students'] = 0
            if obj.role == 'instructor':
                counts['assigned_students'] = obj.assigned_students.count()
                
    except Exception as e:
        # If there's an error getting counts, return empty dict
        pass
    
    return counts


def add_deletion_warning_message(request, obj_type, obj_name, related_data_count):
    """
    Add a deletion warning message to the request.
    
    Args:
        request: Django request object
        obj_type (str): Type of object being deleted
        obj_name (str): Name of the object being deleted
        related_data_count (dict): Counts of related data
    """
    warning_message = get_deletion_warning_message(obj_type, obj_name, related_data_count)
    messages.warning(request, warning_message)


def create_deletion_confirmation_response(obj_type, obj_name, related_data_count):
    """
    Create a JSON response for deletion confirmation with warning message.
    
    Args:
        obj_type (str): Type of object being deleted
        obj_name (str): Name of the object being deleted
        related_data_count (dict): Counts of related data
    
    Returns:
        JsonResponse: JSON response with warning message
    """
    warning_message = get_deletion_warning_message(obj_type, obj_name, related_data_count)
    
    return JsonResponse({
        'success': False,
        'requires_confirmation': True,
        'warning_message': warning_message,
        'object_type': obj_type,
        'object_name': obj_name,
        'related_data_count': related_data_count
    })
