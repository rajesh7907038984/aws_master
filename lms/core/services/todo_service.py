"""
Centralized Todo Service for Role-Based and User-Specific Todo Generation
"""
from django.utils import timezone
from django.db.models import Q, Count, Prefetch
from datetime import timedelta, datetime
import logging

logger = logging.getLogger(__name__)

# Import models at module level to prevent scoping issues
try:
    from courses.models import CourseEnrollment
except ImportError:
    # Handle case where models aren't ready yet
    CourseEnrollment = None

class TodoService:
    """Service class for generating role-based and user-specific todo items"""
    
    def __init__(self, user):
        self.user = user
        self.now = timezone.now()
        self.today = self.now.date()
        self.tomorrow = self.today + timedelta(days=1)
        self.next_week = self.today + timedelta(days=7)
        self.next_month = self.today + timedelta(days=30)
        
    def get_todos(self, limit=10, offset=0):
        """Main method to get todos based on user role"""
        try:
            if self.user.role == 'learner':
                return self._get_learner_todos(limit, offset)
            elif self.user.role == 'instructor':
                return self._get_instructor_todos(limit, offset)
            elif self.user.role in ['admin', 'superadmin']:
                return self._get_admin_todos(limit, offset)
            elif self.user.role == 'globaladmin':
                return self._get_global_admin_todos(limit, offset)
            else:
                return []
        except Exception as e:
            logger.error(f"Error generating todos for user {self.user.id}: {str(e)}")
            return []
    
    def _get_learner_todos(self, limit=10, offset=0):
        """Generate todos for learners"""
        from assignments.models import Assignment
        from conferences.models import Conference
        
        # Use module-level import, fallback to local import if needed
        if CourseEnrollment is None:
            from courses.models import CourseEnrollment as LocalCourseEnrollment
        else:
            LocalCourseEnrollment = CourseEnrollment
        
        todos = []
        
        # Get enrolled courses
        enrolled_courses = LocalCourseEnrollment.objects.filter(
            user=self.user
        ).select_related('course')
        enrolled_course_ids = list(enrolled_courses.values_list('course_id', flat=True))
        
        if not enrolled_course_ids:
            return []
        
        # 1. HIGH PRIORITY: Overdue assignments
        overdue_assignments = Assignment.objects.filter(
            Q(course__in=enrolled_course_ids) |
            Q(courses__in=enrolled_course_ids),
            due_date__lt=self.now,
            is_active=True
        ).exclude(
            submissions__user=self.user,
            submissions__status__in=['submitted', 'graded']
        ).distinct().select_related('course')[:5]
        
        for assignment in overdue_assignments:
            days_overdue = (self.now.date() - assignment.due_date.date()).days
            todos.append({
                'id': f'assignment_overdue_{assignment.id}',
                'title': f'OVERDUE: {assignment.title}',
                'description': f'{assignment.course.title if assignment.course else "General"} - {days_overdue} days overdue',
                'due_date': f'{days_overdue} days overdue',
                'sort_date': assignment.due_date - timedelta(days=1000),  # Highest priority
                'type': 'assignment',
                'priority': 'critical',
                'icon': 'exclamation-triangle',
                'url': f'/assignments/{assignment.id}/',
                'metadata': {
                    'assignment_id': assignment.id,
                    'course_id': assignment.course.id if assignment.course else None,
                    'points': getattr(assignment, 'points', None),
                    'days_overdue': days_overdue
                }
            })
        
        # 2. HIGH PRIORITY: Due today/tomorrow assignments
        urgent_assignments = Assignment.objects.filter(
            Q(course__in=enrolled_course_ids) |
            Q(courses__in=enrolled_course_ids),
            due_date__gte=self.now,
            due_date__date__lte=self.tomorrow,
            is_active=True
        ).exclude(
            submissions__user=self.user,
            submissions__status__in=['submitted', 'graded']
        ).distinct().select_related('course').order_by('due_date')[:10]
        
        for assignment in urgent_assignments:
            due_text = self._format_due_date(assignment.due_date)
            priority = 'high' if assignment.due_date.date() <= self.tomorrow else 'medium'
            
            todos.append({
                'id': f'assignment_urgent_{assignment.id}',
                'title': assignment.title,
                'description': f'{assignment.course.title if assignment.course else "General"}',
                'due_date': due_text,
                'sort_date': assignment.due_date,
                'type': 'assignment',
                'priority': priority,
                'icon': 'file-alt',
                'url': f'/assignments/{assignment.id}/',
                'metadata': {
                    'assignment_id': assignment.id,
                    'course_id': assignment.course.id if assignment.course else None,
                    'points': getattr(assignment, 'points', None)
                }
            })
        
        # 3. MEDIUM PRIORITY: Upcoming assignments (within week)
        upcoming_assignments = Assignment.objects.filter(
            Q(course__in=enrolled_course_ids) |
            Q(courses__in=enrolled_course_ids),
            due_date__gt=self.tomorrow,
            due_date__date__lte=self.next_week,
            is_active=True
        ).exclude(
            submissions__user=self.user,
            submissions__status__in=['submitted', 'graded']
        ).distinct().select_related('course').order_by('due_date')[:10]
        
        for assignment in upcoming_assignments:
            due_text = self._format_due_date(assignment.due_date)
            todos.append({
                'id': f'assignment_upcoming_{assignment.id}',
                'title': assignment.title,
                'description': f'{assignment.course.title if assignment.course else "General"}',
                'due_date': due_text,
                'sort_date': assignment.due_date,
                'type': 'assignment',
                'priority': 'medium',
                'icon': 'file-alt',
                'url': f'/assignments/{assignment.id}/',
                'metadata': {
                    'assignment_id': assignment.id,
                    'course_id': assignment.course.id if assignment.course else None,
                    'points': getattr(assignment, 'points', None)
                }
            })
        
        # 4. MEDIUM PRIORITY: Conferences today/tomorrow
        upcoming_conferences = Conference.objects.filter(
            course__in=enrolled_course_ids,
            date__gte=self.today,
            date__lte=self.next_week,
            status='published'
        ).select_related('course').order_by('date')[:5]
        
        for conference in upcoming_conferences:
            due_text = self._format_due_date(conference.date)
            priority = 'high' if conference.date.date() <= self.tomorrow else 'medium'
            
            todos.append({
                'id': f'conference_{conference.id}',
                'title': f'Join: {conference.title}',
                'description': f'{conference.course.title} - {conference.date.strftime("%I:%M %p")}',
                'due_date': due_text,
                'sort_date': conference.date,
                'type': 'conference',
                'priority': priority,
                'icon': 'video',
                'url': f'/conferences/{conference.id}/',
                'metadata': {
                    'conference_id': conference.id,
                    'course_id': conference.course.id,
                    'meeting_time': conference.date.strftime("%I:%M %p")
                }
            })
        
        # 5. LOW PRIORITY: In-progress courses
        in_progress_enrollments = enrolled_courses.filter(
            completed=False,
            last_accessed__isnull=False
        ).order_by('-last_accessed')[:5]
        
        for enrollment in in_progress_enrollments:
            progress = enrollment.progress_percentage
            todos.append({
                'id': f'course_continue_{enrollment.course.id}',
                'title': f'Continue: {enrollment.course.title}',
                'description': f'{progress}% complete - Last accessed {enrollment.last_accessed.strftime("%b %d")}',
                'due_date': 'In Progress',
                'sort_date': self.now + timedelta(days=1),
                'type': 'course',
                'priority': 'low',
                'icon': 'book-open',
                'url': f'/courses/{enrollment.course.id}/view/',
                'metadata': {
                    'course_id': enrollment.course.id,
                    'progress': progress,
                    'enrollment_id': enrollment.id
                }
            })
        
        # 6. LOW PRIORITY: Not started courses
        not_started_enrollments = enrolled_courses.filter(
            completed=False,
            last_accessed__isnull=True
        )[:3]
        
        for enrollment in not_started_enrollments:
            course_desc = (enrollment.course.short_description or 
                          enrollment.course.description or 
                          enrollment.course.title)[:60] + "..."
            
            todos.append({
                'id': f'course_start_{enrollment.course.id}',
                'title': f'Start: {enrollment.course.title}',
                'description': course_desc,
                'due_date': 'Not Started',
                'sort_date': self.now + timedelta(days=2),
                'type': 'course',
                'priority': 'low',
                'icon': 'play-circle',
                'url': f'/courses/{enrollment.course.id}/view/',
                'metadata': {
                    'course_id': enrollment.course.id,
                    'enrollment_id': enrollment.id,
                    'progress': 0
                }
            })
        
        # Sort todos by priority and date
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['sort_date']))
        
        # Apply pagination
        return todos[offset:offset + limit]
    
    def _get_instructor_todos(self, limit=10, offset=0):
        """Generate todos for instructors"""
        from courses.models import Course
        from assignments.models import AssignmentSubmission
        from users.models import CustomUser
        
        todos = []
        
        # Get instructor's courses
        if self.user.role == 'instructor' and self.user.branch:
            accessible_courses = Course.objects.filter(
                Q(instructor=self.user) | 
                Q(accessible_groups__memberships__user=self.user,
                  accessible_groups__memberships__is_active=True),
                branch=self.user.branch,
                is_active=True
            ).distinct()
        else:
            return []
        
        accessible_course_ids = list(accessible_courses.values_list('id', flat=True))
        
        # 1. HIGH PRIORITY: Submissions pending grading
        pending_submissions = AssignmentSubmission.objects.filter(
            assignment__course__in=accessible_course_ids,
            status='submitted'
        ).select_related('assignment', 'assignment__course', 'user').order_by('submitted_at')[:15]
        
        for submission in pending_submissions:
            days_since = (self.now.date() - submission.submitted_at.date()).days
            if days_since == 0:
                due_text, priority = "Submitted today", 'high'
            elif days_since == 1:
                due_text, priority = "Submitted yesterday", 'high'
            elif days_since <= 3:
                due_text, priority = f"Submitted {days_since} days ago", 'high'
            else:
                due_text, priority = f"Submitted {days_since} days ago", 'medium'
            
            todos.append({
                'id': f'submission_grade_{submission.id}',
                'title': f'Grade: {submission.assignment.title}',
                'description': f'{submission.user.get_full_name()} - {submission.assignment.course.title}',
                'due_date': due_text,
                'sort_date': submission.submitted_at,
                'type': 'grading',
                'priority': priority,
                'icon': 'check-circle',
                'url': f'/assignments/{submission.assignment.id}/submissions/',
                'metadata': {
                    'submission_id': submission.id,
                    'student_id': submission.user.id,
                    'assignment_id': submission.assignment.id,
                    'days_pending': days_since
                }
            })
        
        # 2. MEDIUM PRIORITY: Upcoming conferences to host
        from conferences.models import Conference
        upcoming_conferences = Conference.objects.filter(
            course__in=accessible_course_ids,
            date__gte=self.now,
            date__lte=self.next_week,
            status='published'
        ).select_related('course').order_by('date')[:5]
        
        for conference in upcoming_conferences:
            due_text = self._format_due_date(conference.date)
            priority = 'high' if conference.date.date() <= self.tomorrow else 'medium'
            
            todos.append({
                'id': f'conference_host_{conference.id}',
                'title': f'Host: {conference.title}',
                'description': f'{conference.course.title} - {conference.date.strftime("%I:%M %p")}',
                'due_date': due_text,
                'sort_date': conference.date,
                'type': 'conference',
                'priority': priority,
                'icon': 'video',
                'url': f'/conferences/{conference.id}/edit/',
                'metadata': {
                    'conference_id': conference.id,
                    'course_id': conference.course.id,
                    'meeting_time': conference.date.strftime("%I:%M %p")
                }
            })
        
        # 3. LOW PRIORITY: Course management tasks
        for course in accessible_courses[:5]:
            # Get enrollment count - ONLY count learner role users, exclude instructors/admins
            enrollment_count = course.courseenrollment_set.filter(user__role='learner').count()
            
            todos.append({
                'id': f'course_manage_{course.id}',
                'title': f'Manage: {course.title}',
                'description': f'{enrollment_count} students enrolled',
                'due_date': 'Ongoing',
                'sort_date': self.now + timedelta(days=5),
                'type': 'course_management',
                'priority': 'low',
                'icon': 'chalkboard-teacher',
                'url': f'/courses/{course.id}/edit/',
                'metadata': {
                    'course_id': course.id,
                    'enrollment_count': enrollment_count
                }
            })
        
        # Sort todos by priority and date
        priority_order = {'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['sort_date']))
        
        return todos[offset:offset + limit]
    
    def _get_admin_todos(self, limit=10, offset=0):
        """Generate todos for admins/superadmins"""
        from users.models import CustomUser
        from assignments.models import AssignmentSubmission
        from courses.models import Course
        
        todos = []
        
        # Determine admin scope
        if self.user.role == 'admin':
            scope_filter = {'branch': self.user.branch} if self.user.branch else {}
        else:  # superadmin
            from core.utils.business_filtering import get_superadmin_business_filter
            business_scope = get_superadmin_business_filter(self.user)
            if business_scope:
                scope_filter = {'branch__business__in': business_scope}
            else:
                scope_filter = {}
        
        # 1. HIGH PRIORITY: New user registrations
        pending_users = CustomUser.objects.filter(
            is_active=False,
            date_joined__gte=self.now - timedelta(days=30),
            **scope_filter
        ).order_by('-date_joined')[:10]
        
        for user in pending_users:
            days_since = (self.now.date() - user.date_joined.date()).days
            if days_since == 0:
                due_text, priority = "Registered today", 'high'
            elif days_since <= 3:
                due_text, priority = f"Registered {days_since} days ago", 'high'
            else:
                due_text, priority = f"Registered {days_since} days ago", 'medium'
            
            todos.append({
                'id': f'user_approval_{user.id}',
                'title': f'Approve: {user.get_full_name()}',
                'description': f'{user.email} - {user.role.title() if user.role else "User"}',
                'due_date': due_text,
                'sort_date': user.date_joined,
                'type': 'user_management',
                'priority': priority,
                'icon': 'user-check',
                'url': f'/users/{user.id}/edit/',
                'metadata': {
                    'user_id': user.id,
                    'user_role': user.role,
                    'days_pending': days_since
                }
            })
        
        # 2. MEDIUM PRIORITY: Course management
        if scope_filter:
            recent_courses = Course.objects.filter(
                created_at__gte=self.now - timedelta(days=7),
                **scope_filter
            ).order_by('-created_at')[:5]
        else:
            recent_courses = Course.objects.filter(
                created_at__gte=self.now - timedelta(days=7)
            ).order_by('-created_at')[:5]
        
        for course in recent_courses:
            days_since = (self.now.date() - course.created_at.date()).days
            # Get enrollment count - ONLY count learner role users, exclude instructors/admins  
            enrollment_count = course.courseenrollment_set.filter(user__role='learner').count()
            
            todos.append({
                'id': f'course_review_{course.id}',
                'title': f'Review: {course.title}',
                'description': f'Created {days_since} days ago - {enrollment_count} enrollments',
                'due_date': f'Created {days_since} days ago',
                'sort_date': course.created_at,
                'type': 'course_review',
                'priority': 'medium',
                'icon': 'eye',
                'url': f'/courses/{course.id}/view/',
                'metadata': {
                    'course_id': course.id,
                    'enrollment_count': enrollment_count,
                    'days_since_created': days_since
                }
            })
        
        # 3. LOW PRIORITY: System maintenance
        todos.append({
            'id': 'system_maintenance',
            'title': 'System Health Check',
            'description': 'Review system performance and maintenance tasks',
            'due_date': 'Weekly',
            'sort_date': self.now + timedelta(days=7),
            'type': 'maintenance',
            'priority': 'low',
            'icon': 'cogs',
            'url': '/users/admin/',
            'metadata': {}
        })
        
        # Sort and return
        priority_order = {'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['sort_date']))
        
        return todos[offset:offset + limit]
    
    def _get_global_admin_todos(self, limit=10, offset=0):
        """Generate todos for global admins"""
        from users.models import CustomUser
        from courses.models import Course
        from business.models import Business
        
        todos = []
        
        # 1. System-wide monitoring tasks
        todos.append({
            'id': 'global_system_overview',
            'title': 'Global System Overview',
            'description': 'Monitor platform-wide performance and usage',
            'due_date': 'Daily',
            'sort_date': self.now,
            'type': 'monitoring',
            'priority': 'high',
            'icon': 'globe',
            'url': '/dashboard/globaladmin/',
            'metadata': {}
        })
        
        # 2. New business registrations
        recent_businesses = Business.objects.filter(
            created_at__gte=self.now - timedelta(days=7)
        ).order_by('-created_at')[:5]
        
        for business in recent_businesses:
            days_since = (self.now.date() - business.created_at.date()).days
            todos.append({
                'id': f'business_review_{business.id}',
                'title': f'Review: {business.name}',
                'description': f'New business registered {days_since} days ago',
                'due_date': f'{days_since} days ago',
                'sort_date': business.created_at,
                'type': 'business_review',
                'priority': 'high' if days_since <= 2 else 'medium',
                'icon': 'building',
                'url': f'/business/{business.id}/',
                'metadata': {
                    'business_id': business.id,
                    'days_since_created': days_since
                }
            })
        
        # Sort and return
        priority_order = {'high': 1, 'medium': 2, 'low': 3}
        todos.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['sort_date']))
        
        return todos[offset:offset + limit]
    
    def _format_due_date(self, due_date):
        """Format due date for display"""
        if isinstance(due_date, str):
            return due_date
            
        due_date_only = due_date.date() if hasattr(due_date, 'date') else due_date
        
        if due_date_only == self.today:
            return "Today"
        elif due_date_only == self.tomorrow:
            return "Tomorrow"
        elif due_date_only <= self.next_week:
            return due_date.strftime('%a %b %d')
        else:
            return due_date.strftime('%b %d')
    
    def get_todo_counts_by_type(self):
        """Get todo counts grouped by type"""
        todos = self.get_todos(limit=100)  # Get more for accurate counts
        
        counts = {}
        for todo in todos:
            todo_type = todo['type']
            priority = todo['priority']
            
            if todo_type not in counts:
                counts[todo_type] = {'total': 0, 'high': 0, 'medium': 0, 'low': 0, 'critical': 0}
            
            counts[todo_type]['total'] += 1
            counts[todo_type][priority] += 1
        
        return counts
    
    def get_todos_by_type(self, todo_type, limit=10, offset=0):
        """Get todos filtered by type"""
        all_todos = self.get_todos(limit=100)  # Get more for filtering
        filtered_todos = [todo for todo in all_todos if todo['type'] == todo_type]
        return filtered_todos[offset:offset + limit]
