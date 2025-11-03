from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class CalendarService:
    """
    Comprehensive calendar service that aggregates all user activities
    including assignments, conferences, course deadlines, and topic end dates
    """
    
    def __init__(self, user):
        self.user = user
        self.activities = []
        
        # Log calendar access for Session auditing
        logger.info(f"Calendar service initialized for user {user.username} (role: {user.role}, branch: {user.branch})")
    
    def _validate_user_permission(self, obj, permission_type='view'):
        """Validate that user has permission to access the given object"""
        
        # Global admin has access to everything
        if self.user.is_superuser or self.user.role == 'globaladmin':
            return True
            
        # Super admin has access based on business assignments
        if self.user.role == 'superadmin':
            if hasattr(obj, 'branch') and obj.branch and hasattr(obj.branch, 'business'):
                if hasattr(self.user, 'business_assignments'):
                    return self.user.business_assignments.filter(
                        business=obj.branch.business, 
                        is_active=True
                    ).exists()
            return True
            
        # Branch-based validation for other roles
        if not self.user.branch:
            logger.warning(f"User {self.user.username} has no branch assignment, denying access")
            return False
            
        # Check direct branch relationship
        if hasattr(obj, 'branch'):
            return obj.branch == self.user.branch
            
        # Check indirect branch relationships
        if hasattr(obj, 'course') and hasattr(obj.course, 'branch'):
            return obj.course.branch == self.user.branch
            
        if hasattr(obj, 'user') and hasattr(obj.user, 'branch'):
            return obj.user.branch == self.user.branch
            
        if hasattr(obj, 'created_by') and hasattr(obj.created_by, 'branch'):
            return obj.created_by.branch == self.user.branch
            
        # Default deny for Session
        logger.warning(f"Permission check failed for user {self.user.username} accessing {obj}")
        return False
    
    def _validate_activity_access(self, activity):
        """Final validation of activity access before returning to user"""
        
        # Basic activity structure validation
        if not isinstance(activity, dict) or 'type' not in activity:
            logger.warning(f"Invalid activity structure for user {self.user.username}")
            return False
        
        activity_type = activity.get('type')
        activity_url = activity.get('url', '')
        
        # Role-based activity type validation
        if self.user.role == 'learner':
            # Learners should only see their own activities
            allowed_types = ['assignment', 'quiz', 'conference', 'course_deadline', 'topic_deadline', 'personal_event']
            if activity_type not in allowed_types:
                logger.debug(f"Activity type {activity_type} not allowed for learner {self.user.username}")
                return False
        
        elif self.user.role == 'instructor':
            # Instructors can see grading activities and their courses
            allowed_types = ['assignment', 'quiz', 'conference', 'course_deadline', 'topic_deadline', 'grading', 'personal_event']
            if activity_type not in allowed_types:
                logger.debug(f"Activity type {activity_type} not allowed for instructor {self.user.username}")
                return False
        
        elif self.user.role in ['admin', 'superadmin', 'globaladmin']:
            # Admins can see all activity types
            pass
        
        # URL validation - ensure URLs are internal and safe
        if activity_url and not self._validate_activity_url(activity_url):
            logger.warning(f"Invalid activity URL for user {self.user.username}: {activity_url}")
            return False
        
        return True
    
    def _validate_activity_url(self, url):
        """Validate that activity URLs are safe and internal"""
        
        # Ensure URLs are internal (start with /)
        if not url.startswith('/'):
            return False
        
        # Block any potentially dangerous URLs
        dangerous_patterns = ['..', '/admin/', '/debug/', '/api/admin/', '//']
        for pattern in dangerous_patterns:
            if pattern in url:
                return False
        
        # Validate URL patterns based on user role
        if self.user.role == 'learner':
            # Learners should only access specific URL patterns
            allowed_patterns = ['/assignments/', '/courses/', '/quiz/', '/conferences/', '/calendar/']
            if not any(url.startswith(pattern) for pattern in allowed_patterns):
                return False
        
        return True
    
    def get_user_calendar_data(self, start_date=None, end_date=None):
        """
        Get all calendar activities for a user within a date range
        """
        if not start_date:
            start_date = timezone.now().date()
        if not end_date:
            end_date = start_date + timedelta(days=30)
        
        # Convert to datetime with timezone
        start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
        activities = []
        
        # Get all activity types based on user role
        if self.user.role == 'learner':
            activities.extend(self._get_learner_activities(start_datetime, end_datetime))
        elif self.user.role == 'instructor':
            activities.extend(self._get_instructor_activities(start_datetime, end_datetime))
        elif self.user.role in ['admin', 'superadmin', 'globaladmin']:
            activities.extend(self._get_admin_activities(start_datetime, end_datetime))
        
        # Add personal calendar events for all users
        activities.extend(self._get_personal_calendar_events(start_datetime, end_datetime))
        
        # Final Session validation: double-check all activities before returning
        validated_activities = []
        for activity in activities:
            # Validate activity URLs to prevent unauthorized access
            if self._validate_activity_access(activity):
                validated_activities.append(activity)
            else:
                logger.warning(f"Activity validation failed for user {self.user.username}: {activity.get('title', 'Unknown')}")
        
        # Sort activities by date and time
        validated_activities.sort(key=lambda x: (x['date'], x.get('time', datetime.min.time())))
        
        logger.info(f"Calendar service returned {len(validated_activities)} validated activities for user {self.user.username}")
        return validated_activities
    
    def get_daily_activities(self, date):
        """
        Get all activities for a specific date
        """
        start_datetime = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(date, datetime.max.time()))
        
        return self.get_user_calendar_data(start_datetime.date(), end_datetime.date())
    
    def get_activity_summary_by_date(self, start_date=None, end_date=None):
        """
        Get a summary of activities grouped by date for calendar display
        """
        activities = self.get_user_calendar_data(start_date, end_date)
        
        summary = defaultdict(list)
        for activity in activities:
            date_key = activity['date'].strftime('%Y-%m-%d')
            summary[date_key].append({
                'type': activity['type'],
                'title': activity['title'],
                'priority': activity.get('priority', 'medium'),
                'status': activity.get('status', 'pending'),
                'url': activity.get('url', '#')
            })
        
        return dict(summary)
    
    def _get_learner_activities(self, start_datetime, end_datetime):
        """Get activities specific to learners - only their enrolled courses"""
        activities = []
        
        # Get enrolled courses with branch validation
        from courses.models import CourseEnrollment
        enrolled_courses = CourseEnrollment.objects.filter(
            user=self.user, 
            completed=False,
            course__is_active=True
        ).select_related('course')
        
        # Additional branch validation for Session
        if self.user.branch:
            enrolled_courses = enrolled_courses.filter(course__branch=self.user.branch)
        
        course_ids = [enrollment.course.id for enrollment in enrolled_courses]
        
        # Assignment due dates
        activities.extend(self._get_assignment_activities(start_datetime, end_datetime, course_ids))
        
        # Conference dates
        activities.extend(self._get_conference_activities(start_datetime, end_datetime, course_ids))
        
        # Course end dates
        activities.extend(self._get_course_deadline_activities(start_datetime, end_datetime, course_ids))
        
        # Topic end dates
        activities.extend(self._get_topic_deadline_activities(start_datetime, end_datetime, course_ids))
        
        # Quiz deadlines
        activities.extend(self._get_quiz_activities(start_datetime, end_datetime, course_ids))
        
        return activities
    
    def _get_instructor_activities(self, start_datetime, end_datetime):
        """Get activities specific to instructors - only their assigned courses"""
        activities = []
        
        # Get courses where user is instructor with branch validation
        from courses.models import Course
        instructor_courses = Course.objects.filter(
            Q(instructor=self.user) | 
            Q(accessible_groups__memberships__user=self.user,
              accessible_groups__memberships__is_active=True),
            is_active=True
        ).distinct()
        
        # Additional branch validation for Session
        if self.user.branch:
            instructor_courses = instructor_courses.filter(branch=self.user.branch)
        
        course_ids = [course.id for course in instructor_courses]
        
        # All assignment due dates for instructor's courses
        activities.extend(self._get_assignment_activities(start_datetime, end_datetime, course_ids, instructor_view=True))
        
        # All conferences for instructor's courses
        activities.extend(self._get_conference_activities(start_datetime, end_datetime, course_ids, instructor_view=True))
        
        # Course deadlines
        activities.extend(self._get_course_deadline_activities(start_datetime, end_datetime, course_ids))
        
        # Grading deadlines (assignments that need grading)
        activities.extend(self._get_grading_activities(start_datetime, end_datetime, course_ids))
        
        return activities
    
    def _get_admin_activities(self, start_datetime, end_datetime):
        """Get activities for admin users"""
        activities = []
        
        # Get branch-filtered courses using proper filtering
        from core.branch_filters import get_user_courses
        admin_courses = get_user_courses(self.user)
        course_ids = [course.id for course in admin_courses]
        
        # All activities for courses in their branch
        activities.extend(self._get_assignment_activities(start_datetime, end_datetime, course_ids, admin_view=True))
        activities.extend(self._get_conference_activities(start_datetime, end_datetime, course_ids, admin_view=True))
        activities.extend(self._get_course_deadline_activities(start_datetime, end_datetime, course_ids))
        
        # Branch-specific activities
        activities.extend(self._get_branch_activities(start_datetime, end_datetime))
        
        return activities
    
    def _get_assignment_activities(self, start_datetime, end_datetime, course_ids, instructor_view=False, admin_view=False):
        """Get assignment-related activities"""
        activities = []
        
        try:
            from assignments.models import Assignment, AssignmentSubmission
            
            # Get assignments in the date range
            assignments = Assignment.objects.filter(
                courses__in=course_ids,
                due_date__gte=start_datetime,
                due_date__lte=end_datetime,
                is_active=True
            ).prefetch_related('courses').distinct()
            
            for assignment in assignments:
                # Validate user has permission to see this assignment
                if not self._validate_user_permission(assignment):
                    continue
                    
                activity_type = 'assignment'
                priority = 'high' if assignment.is_overdue else 'medium' if assignment.due_soon else 'low'
                
                if instructor_view or admin_view:
                    # For instructors/admins, show assignment due dates
                    activities.append({
                        'type': activity_type,
                        'title': f"Assignment Due: {assignment.title}",
                        'description': f"Course: {assignment.course.title}",
                        'date': assignment.due_date.date(),
                        'time': assignment.due_date.time(),
                        'priority': priority,
                        'status': 'due',
                        'url': f'/assignments/{assignment.id}/',
                        'course': assignment.course.title,
                        'icon': 'assignment'
                    })
                else:
                    # For learners, check if they've submitted
                    try:
                        submission = AssignmentSubmission.objects.get(
                            assignment=assignment,
                            user=self.user
                        )
                        if submission.status in ['submitted', 'graded']:
                            continue  # Don't show completed assignments
                    except AssignmentSubmission.DoesNotExist:
                        pass  # Assignment not submitted yet
                    
                    activities.append({
                        'type': activity_type,
                        'title': f"Submit: {assignment.title}",
                        'description': f"Course: {assignment.course.title}",
                        'date': assignment.due_date.date(),
                        'time': assignment.due_date.time(),
                        'priority': priority,
                        'status': 'pending',
                        'url': f'/assignments/{assignment.id}/',
                        'course': assignment.course.title,
                        'icon': 'assignment'
                    })
        except Exception as e:
            logger.error(f"Error getting assignment activities: {e}")
        
        return activities
    
    def _get_conference_activities(self, start_datetime, end_datetime, course_ids, instructor_view=False, admin_view=False):
        """Get conference-related activities with permission validation"""
        activities = []
        
        try:
            from conferences.models import Conference
            from django.utils import timezone
            
            # Get conferences in the date range with proper filtering
            conference_filter = Q(course__in=course_ids, date__gte=start_datetime.date(),
                                 date__lte=end_datetime.date(), status='published')
            
            # For general conferences (no specific course), only include if user has branch access
            if self.user.branch:
                general_conference_filter = Q(
                    course__isnull=True,
                    date__gte=start_datetime.date(),
                    date__lte=end_datetime.date(),
                    status='published',
                    created_by__branch=self.user.branch
                )
                conference_filter = conference_filter | general_conference_filter
            
            conferences = Conference.objects.filter(conference_filter).select_related('course')
            
            for conference in conferences:
                # Validate user permission to access this conference
                if not self._validate_user_permission(conference):
                    logger.debug(f"User {self.user.username} denied access to conference {conference.id}")
                    continue
                
                # Combine date and time
                conf_datetime = timezone.make_aware(
                    datetime.combine(conference.date, conference.start_time)
                )
                
                if conf_datetime < start_datetime or conf_datetime > end_datetime:
                    continue
                
                priority = 'high' if conference.date == timezone.now().date() else 'medium'
                
                activities.append({
                    'type': 'conference',
                    'title': f"Conference: {conference.title}",
                    'description': f"Course: {conference.course.title if conference.course else 'General'}",
                    'date': conference.date,
                    'time': conference.start_time,
                    'priority': priority,
                    'status': 'scheduled',
                    'url': f'/conferences/{conference.id}/',
                    'course': conference.course.title if conference.course else 'General',
                    'icon': 'video'
                })
        except Exception as e:
            logger.error(f"Error getting conference activities: {e}")
        
        return activities
    
    def _get_course_deadline_activities(self, start_datetime, end_datetime, course_ids):
        """Get course deadline activities"""
        activities = []
        
        try:
            from courses.models import Course
            
            # Get courses with end dates in the range
            courses = Course.objects.filter(
                id__in=course_ids,
                end_date__gte=start_datetime,
                end_date__lte=end_datetime
            )
            
            for course in courses:
                # Validate user permission to access this course
                if not self._validate_user_permission(course):
                    logger.debug(f"User {self.user.username} denied access to course {course.id}")
                    continue
                
                activities.append({
                    'type': 'course_deadline',
                    'title': f"Course Ends: {course.title}",
                    'description': f"Course access expires",
                    'date': course.end_date.date(),
                    'time': course.end_date.time(),
                    'priority': 'high',
                    'status': 'deadline',
                    'url': f'/courses/{course.id}/',
                    'course': course.title,
                    'icon': 'clock'
                })
        except Exception as e:
            logger.error(f"Error getting course deadline activities: {e}")
        
        return activities
    
    def _get_topic_deadline_activities(self, start_datetime, end_datetime, course_ids):
        """Get topic deadline activities"""
        activities = []
        
        try:
            from courses.models import Topic, TopicProgress
            
            # Get topics with end dates in the range
            topics = Topic.objects.filter(
                courses__id__in=course_ids,
                end_date__gte=start_datetime.date(),
                end_date__lte=end_datetime.date(),
                status='active'
            ).select_related().distinct()
            
            for topic in topics:
                # Validate user permission to access this topic
                if not self._validate_user_permission(topic):
                    logger.debug(f"User {self.user.username} denied access to topic {topic.id}")
                    continue
                
                # Check if user has completed this topic
                if self.user.role == 'learner':
                    try:
                        progress = TopicProgress.objects.filter(
                            user=self.user,
                            topic=topic
                        ).first()
                        if progress and progress.completed:
                            continue  # Don't show completed topics
                    except TopicProgress.DoesNotExist:
                        pass  # Topic not started yet
                
                activities.append({
                    'type': 'topic_deadline',
                    'title': f"Topic Ends: {topic.title}",
                    'description': f"Topic access expires",
                    'date': topic.end_date,
                    'time': datetime.min.time(),
                    'priority': 'medium',
                    'status': 'deadline',
                    'url': f'/courses/topic/{topic.id}/',
                    'course': ', '.join([course.title for course in topic.courses.all()[:2]]),
                    'icon': 'bookmark'
                })
        except Exception as e:
            logger.error(f"Error getting topic deadline activities: {e}")
        
        return activities
    
    def _get_quiz_activities(self, start_datetime, end_datetime, course_ids):
        """Get quiz-related activities"""
        activities = []
        
        try:
            from quiz.models import Quiz, QuizAttempt
            
            # Get quizzes with deadlines in the range
            quizzes = Quiz.objects.filter(
                course__in=course_ids,
                expires_at__gte=start_datetime,
                expires_at__lte=end_datetime,
                is_active=True
            ).select_related('course')
            
            for quiz in quizzes:
                # Validate user permission to access this quiz
                if not self._validate_user_permission(quiz):
                    logger.debug(f"User {self.user.username} denied access to quiz {quiz.id}")
                    continue
                
                # For learners, check if they've completed the quiz
                if self.user.role == 'learner':
                    attempts = QuizAttempt.objects.filter(
                        quiz=quiz,
                        user=self.user,
                        completed=True
                    )
                    if attempts.exists() and quiz.max_attempts and attempts.count() >= quiz.max_attempts:
                        continue  # User has used all attempts
                
                activities.append({
                    'type': 'quiz',
                    'title': f"Quiz: {quiz.title}",
                    'description': f"Course: {quiz.course.title}",
                    'date': quiz.expires_at.date(),
                    'time': quiz.expires_at.time(),
                    'priority': 'medium',
                    'status': 'available',
                    'url': f'/quiz/{quiz.id}/',
                    'course': quiz.course.title,
                    'icon': 'question-circle'
                })
        except Exception as e:
            logger.error(f"Error getting quiz activities: {e}")
        
        return activities
    
    def _get_grading_activities(self, start_datetime, end_datetime, course_ids):
        """Get grading activities for instructors"""
        activities = []
        
        try:
            from assignments.models import Assignment, AssignmentSubmission
            from django.db.models import Count
            
            # Get assignments that have ungraded submissions
            assignments_with_ungraded = Assignment.objects.filter(
                course__in=course_ids,
                is_active=True
            ).annotate(
                ungraded_count=Count('submissions', filter=Q(submissions__status='submitted'))
            ).filter(ungraded_count__gt=0)
            
            for assignment in assignments_with_ungraded:
                # Validate user permission to access this assignment for grading
                if not self._validate_user_permission(assignment):
                    logger.debug(f"User {self.user.username} denied access to grade assignment {assignment.id}")
                    continue
                
                # Only show if the assignment due date is in our range or has passed
                if assignment.due_date and assignment.due_date.date() <= end_datetime.date():
                    activities.append({
                        'type': 'grading',
                        'title': f"Grade: {assignment.title}",
                        'description': f"{assignment.ungraded_count} submission(s) to grade",
                        'date': assignment.due_date.date() if assignment.due_date else timezone.now().date(),
                        'time': assignment.due_date.time() if assignment.due_date else datetime.min.time(),
                        'priority': 'high' if assignment.is_overdue else 'medium',
                        'status': 'needs_grading',
                        'url': f'/assignments/{assignment.id}/submissions/',
                        'course': assignment.course.title,
                        'icon': 'edit'
                    })
        except Exception as e:
            logger.error(f"Error getting grading activities: {e}")
        
        return activities
    
    def _get_branch_activities(self, start_datetime, end_datetime):
        """Get branch-specific activities for admins"""
        activities = []
        
        try:
            # Could add branch-specific deadlines, reports, etc.
            # Future expansion
            pass
        except Exception as e:
            logger.error(f"Error getting branch activities: {e}")
        
        return activities
    
    def _get_personal_calendar_events(self, start_datetime, end_datetime):
        """Get personal calendar events"""
        activities = []
        
        try:
            from calendar_app.models import CalendarEvent
            
            events = CalendarEvent.objects.filter(
                created_by=self.user,
                start_date__gte=start_datetime,
                start_date__lte=end_datetime
            )
            
            for event in events:
                # Personal events are already filtered by created_by=self.user, 
                # but validate for completeness
                if event.created_by != self.user:
                    logger.warning(f"Session issue: Personal event {event.id} not owned by user {self.user.username}")
                    continue
                
                activities.append({
                    'type': 'personal_event',
                    'title': event.title,
                    'description': event.description or '',
                    'date': event.start_date.date(),
                    'time': event.start_date.time(),
                    'priority': 'low',
                    'status': 'scheduled',
                    'url': f'/calendar/events/{event.id}/',
                    'course': 'Personal',
                    'icon': 'calendar'
                })
        except Exception as e:
            logger.error(f"Error getting personal calendar events: {e}")
        
        return activities 