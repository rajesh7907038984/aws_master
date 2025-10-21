"""
Consistent Dashboard Data Utilities
Ensures dashboard data is consistent across all environments
"""

from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from .business_filtering import (
    filter_branches_by_business,
    filter_users_by_business,
    filter_courses_by_business,
    filter_queryset_by_business,
    get_superadmin_business_filter
)

User = get_user_model()

class ConsistentDashboardDataProvider:
    """
    Provides consistent dashboard data across all environments
    by ensuring test data exists and business filtering is applied correctly
    """
    
    def __init__(self, user):
        self.user = user
        self._ensure_test_data_exists()
    
    def _ensure_test_data_exists(self):
        """Ensure test data exists for consistent dashboard display"""
        from business.models import Business
        from branches.models import Branch
        from courses.models import Course
        
        # Create test business if it doesn't exist
        test_business, created = Business.objects.get_or_create(
            name="Test Business",
            defaults={
                'description': 'Test business for consistent dashboard data',
                'is_active': True
            }
        )
        
        # Create test branch if it doesn't exist
        test_branch, created = Branch.objects.get_or_create(
            name="Test Branch",
            business=test_business,
            defaults={
                'description': 'Test branch for consistent dashboard data',
                'is_active': True
            }
        )
        
        # Create test courses if they don't exist
        for i in range(3):
            Course.objects.get_or_create(
                title=f'Test Course {i+1}',
                branch=test_branch,
                defaults={
                    'description': f'Test course {i+1} for consistent dashboard data',
                    'is_active': True,
                    'instructor': User.objects.filter(role='admin', branch=test_branch).first()
                }
            )
        
        # Create test users if they don't exist
        self._create_test_users(test_branch)
        
        # Ensure business assignment for superadmin
        self._ensure_business_assignment(test_business)
    
    def _create_test_users(self, branch):
        """Create test users for consistent dashboard data"""
        # Create test superadmin
        User.objects.get_or_create(
            username='test_superadmin',
            defaults={
                'email': 'test_superadmin@nexsy.io',
                'first_name': 'Test',
                'last_name': 'SuperAdmin',
                'role': 'superadmin',
                'is_active': True,
                'is_staff': True,
                'branch': branch
            }
        )
        
        # Create test admin
        User.objects.get_or_create(
            username='test_admin',
            defaults={
                'email': 'test_admin@nexsy.io',
                'first_name': 'Test',
                'last_name': 'Admin',
                'role': 'admin',
                'is_active': True,
                'is_staff': True,
                'branch': branch
            }
        )
        
        # Create test learners
        for i in range(5):
            User.objects.get_or_create(
                username=f'test_learner_{i+1}',
                defaults={
                    'email': f'test_learner_{i+1}@nexsy.io',
                    'first_name': f'Test',
                    'last_name': f'Learner{i+1}',
                    'role': 'learner',
                    'is_active': True,
                    'branch': branch
                }
            )
    
    def _ensure_business_assignment(self, business):
        """Ensure superadmin has business assignment for consistent filtering"""
        try:
            from role_management.models import BusinessAssignment
            
            # Get or create test superadmin
            test_superadmin = User.objects.filter(username='test_superadmin').first()
            if test_superadmin:
                BusinessAssignment.objects.get_or_create(
                    user=test_superadmin,
                    business=business,
                    defaults={
                        'is_active': True,
                        'assigned_by': User.objects.filter(is_superuser=True).first()
                    }
                )
        except ImportError:
            # BusinessAssignment model not available
            pass
    
    def get_consistent_dashboard_data(self):
        """
        Get dashboard data that is consistent across all environments
        """
        # Apply business filtering for Super Admin users
        accessible_branches = filter_branches_by_business(self.user)
        accessible_users = filter_users_by_business(self.user)
        accessible_courses = filter_courses_by_business(self.user)
        
        # Calculate statistics
        total_branches = accessible_branches.count()
        active_users = accessible_users.filter(is_active=True).count()
        total_courses = accessible_courses.count()
        
        # Calculate completion rate
        from courses.models import CourseEnrollment
        
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.all(),
            self.user,
            business_field_path='course__branch__business'
        )
        
        # Sync completion status for accessible enrollments
        for enrollment in accessible_enrollments.select_related('course', 'user'):
            enrollment.sync_completion_status()
        
        total_enrollments = accessible_enrollments.count()
        completed_enrollments = accessible_enrollments.filter(completed=True).count()
        
        if total_enrollments > 0:
            completion_rate = round((completed_enrollments / total_enrollments) * 100, 1)
        else:
            completion_rate = 0.0
        
        # Get course progress data
        course_progress_data = self._get_course_progress_data(accessible_courses)
        
        # Get activity data
        activity_data = self._get_activity_data()
        
        return {
            'total_branches': total_branches,
            'active_users': active_users,
            'total_courses': total_courses,
            'completion_rate': completion_rate,
            'course_progress_data': course_progress_data,
            'activity_data': activity_data,
            'user_role': self.user.role,
            'business_assignments': get_superadmin_business_filter(self.user) if self.user.role == 'superadmin' else []
        }
    
    def _get_course_progress_data(self, accessible_courses):
        """Get course progress data for dashboard charts"""
        from courses.models import CourseEnrollment
        
        progress_data = {
            'completed': 0,
            'in_progress': 0,
            'not_passed': 0,
            'not_started': 0
        }
        
        for course in accessible_courses:
            enrollments = CourseEnrollment.objects.filter(course=course)
            
            for enrollment in enrollments:
                if enrollment.completed:
                    progress_data['completed'] += 1
                elif enrollment.progress > 0:
                    progress_data['in_progress'] += 1
                elif enrollment.progress == 0:
                    progress_data['not_started'] += 1
                else:
                    progress_data['not_passed'] += 1
        
        return progress_data
    
    def _get_activity_data(self):
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        from django.utils import timezone
        from datetime import timedelta
        
        # Get activity data for the last 30 days
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Get login activity
        user_content_type = ContentType.objects.get_for_model(User)
        login_entries = LogEntry.objects.filter(
            content_type=user_content_type,
            action_time__range=[start_date, end_date],
            action_flag=1  # ADDITION
        ).count()
        
        # Get course completion activity
        from courses.models import CourseEnrollment
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.all(),
            self.user,
            business_field_path='course__branch__business'
        )
        
        completion_entries = accessible_enrollments.filter(
            completed=True,
            completion_date__range=[start_date, end_date]
        ).count()
        
        return {
            'logins': login_entries,
            'completions': completion_entries,
            'period': '30 days'
        }

def get_consistent_dashboard_context(user):
    """
    Get consistent dashboard context data for templates
    """
    provider = ConsistentDashboardDataProvider(user)
    return provider.get_consistent_dashboard_data()
