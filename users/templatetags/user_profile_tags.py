from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.contrib.auth import get_user_model


register = template.Library()

@register.filter
def profile_completion_percentage(user):
    """
    Returns the profile completion percentage for a user.
    """
    if not user or user.is_anonymous:
        return 0
    
    # Define fields to check for completion directly on CustomUser
    required_fields = ['first_name', 'last_name', 'email', 'branch']
    completed = 0
    
    for field in required_fields:
        if getattr(user, field, None):
            completed += 1
    
    return int((completed / len(required_fields)) * 100)

@register.filter
def display_name(user):
    """
    Returns the full name of the user if available, otherwise returns the username.
    """
    if not user or user.is_anonymous:
        return "Anonymous User"
    
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    else:
        return user.username

@register.simple_tag
def user_activity_summary(user):
    """
    Returns a summary of the user's activity.
    """
    if not user or user.is_anonymous:
        return mark_safe("<span>No activity data for anonymous users</span>")
    
    try:
        # You would customize this based on your models
        enrolled_courses = getattr(user, 'enrolled_courses', [])
        completed_courses = [course for course in enrolled_courses if getattr(course, 'completed', False)]
        
        return mark_safe(
            f"<div class='user-activity-summary'>"
            f"<p><strong>Enrolled Courses:</strong> {len(enrolled_courses)}</p>"
            f"<p><strong>Completed Courses:</strong> {len(completed_courses)}</p>"
            f"</div>"
        )
    except Exception as e:
        return mark_safe(f"<span>Error retrieving activity data: {escape(str(e))}</span>")

@register.inclusion_tag('users/tags/profile_avatar.html')
def profile_avatar(user, size='md'):
    """
    Renders the user's profile avatar.
    Size can be 'sm', 'md', or 'lg'.
    """
    avatar_url = None
    
    # Since there's no UserProfile model, we'll just return the user data
    # and let the template handle the default avatar
    
    return {
        'user': user,
        'avatar_url': avatar_url,
        'size': size
    }

@register.simple_tag
def last_login_display(user):
    """
    Returns a formatted display of the user's last login time.
    """
    if not user or user.is_anonymous or not user.last_login:
        return "Never"
    
    # Format the last login time
    return user.last_login.strftime("%b %d, %Y at %H:%M")

@register.inclusion_tag('users/tags/user_badges.html')
def display_user_badges(user, limit=3, show_empty=True):
    """
    Displays badges earned by the user.
    
    Args:
        user: The user whose badges to display
        limit: Maximum number of badges to display
        show_empty: Whether to show a placeholder if user has no badges
    """
    badges = []
    total_count = 0
    
    if user and not user.is_anonymous:
        # Gamification system removed
        badges = []
        total_count = 0
    
    return {
        'user': user,
        'badges': badges,
        'show_empty': show_empty,
        'total_count': total_count
    }

@register.inclusion_tag('users/tags/level_progress.html')
def level_progress(user):
    """
    Displays a user's level and progress towards the next level.
    """
    level_data = {
        'current_level': None,
        'next_level': None,
        'progress_percent': 0,
        'total_points': 0
    }
    
    if user and not user.is_anonymous:
        try:
            # Gamification system removed
            user_level_obj = None
            
            if user_level_obj:
                level_data['total_points'] = user_level_obj.total_points
                
                # Get current level
                current_level = user_level_obj.current_level
                if current_level:
                    level_data['current_level'] = current_level
                    
                    # Get next level info
                    next_level = Level.objects.filter(
                        number__gt=current_level.number
                    ).order_by('number').first()
                    
                    if next_level:
                        level_data['next_level'] = next_level
                        
                        # Calculate progress percentage
                        current_level_points = current_level.points_required
                        next_level_points = next_level.points_required
                        points_range = next_level_points - current_level_points
                        
                        if points_range > 0:
                            points_progress = user_level_obj.total_points - current_level_points
                            level_data['progress_percent'] = min(100, max(0, (points_progress / points_range) * 100))
        except Exception:
            pass
    
    return level_data

@register.filter
def user_course_count(user):
    """Returns the number of courses a user is enrolled in - Role-aware"""
    if not user or user.is_anonymous:
        return 0
    try:
        from django.apps import apps
        CourseEnrollment = apps.get_model('courses', 'CourseEnrollment')
        
        # For learners, count their enrollments
        if user.role == 'learner':
            return CourseEnrollment.objects.filter(user=user).count()
        # For instructors, count instructor-related courses (assigned or invited)
        elif user.role == 'instructor':
            from courses.models import Course
            # Count courses where they're primary instructor or enrolled as instructor
            primary_courses = Course.objects.filter(instructor=user).count()
            enrolled_as_instructor = CourseEnrollment.objects.filter(
                user=user, user__role='instructor'
            ).exclude(course__instructor=user).count()
            return primary_courses + enrolled_as_instructor
        else:
            # For other roles, return total enrollments
            return CourseEnrollment.objects.filter(user=user).count()
    except Exception:
        return 0

@register.filter
def user_completion_rate(user):
    """Returns the user's course completion rate as a percentage - Role-aware"""
    if not user or user.is_anonymous:
        return 0
    try:
        from django.apps import apps
        CourseEnrollment = apps.get_model('courses', 'CourseEnrollment')
        
        # Sync completion status before calculating rate
        CourseEnrollment.sync_user_completions(user)
        
        # For learners, calculate completion rate for learner enrollments only
        if user.role == 'learner':
            total = CourseEnrollment.objects.filter(user=user, user__role='learner').count()
            if total == 0:
                return 0
            completed = CourseEnrollment.objects.filter(user=user, user__role='learner', completed=True).count()
            return int((completed / total) * 100)
        # For instructors, completion rate doesn't make as much sense, so return 100% if they have courses
        elif user.role == 'instructor':
            from courses.models import Course
            total_courses = Course.objects.filter(instructor=user).count()
            enrolled_courses = CourseEnrollment.objects.filter(
                user=user, user__role='instructor'
            ).count()
            return 100 if (total_courses + enrolled_courses) > 0 else 0
        else:
            # For other roles, use original logic
            total = CourseEnrollment.objects.filter(user=user).count()
            if total == 0:
                return 0
            completed = CourseEnrollment.objects.filter(user=user, completed=True).count()
            return int((completed / total) * 100)
    except Exception:
        return 0

@register.filter
def user_total_points(user):
    """Returns the user's total points"""
    if not user or user.is_anonymous:
        return 0
    # Gamification system removed
    return 0

@register.filter
def user_badge_count(user):
    """Returns the number of badges earned by the user"""
    if not user or user.is_anonymous:
        return 0
    # Gamification system removed
    return 0

@register.filter
def is_quiz_available_for_user(quiz, user):
    """
    Check if a quiz is available for a specific user.
    """
    if not quiz or not user:
        return False
    
    try:
        return quiz.is_available_for_user(user)
    except Exception:
        return False

@register.inclusion_tag('users/tags/user_stats.html')
def user_stats(user):
    """
    Displays key statistics about a user.
    """
    stats = {
        'user': user,
        'completed_courses': 0,
        'assignments_submitted': 0,
        'avg_grade': None,
        'badges_earned': 0,
        'total_points': 0
    }
    
    if user and not user.is_anonymous:
        # Get course completion stats
        try:
            # Use apps.get_model to avoid import errors
            from django.apps import apps
            CourseEnrollment = apps.get_model('courses', 'CourseEnrollment')
            
            stats['completed_courses'] = CourseEnrollment.objects.filter(
                user=user, 
                completed=True
            ).count()
        except Exception:
            pass
            
        # Get assignment stats
        try:
            AssignmentSubmission = apps.get_model('assignments', 'AssignmentSubmission')
            stats['assignments_submitted'] = AssignmentSubmission.objects.filter(
                user=user
            ).count()
            
            # Calculate average grade if there are submissions with grades
            graded_submissions = AssignmentSubmission.objects.filter(
                user=user,
                grade__isnull=False
            )
            
            if graded_submissions.exists():
                from django.db.models import Avg
                stats['avg_grade'] = graded_submissions.aggregate(
                    avg=Avg('grade')
                )['avg']
        except Exception:
            pass
            
        # Gamification system removed
        stats['badges_earned'] = 0
        stats['total_points'] = 0
    
    return stats 