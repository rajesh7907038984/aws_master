# OPTIMIZED ADMIN DASHBOARD - FIXES BROWSER CRASHES
from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q, Case, When, IntegerField, Prefetch
from courses.models import Course, CourseEnrollment
from users.models import CustomUser
from branches.models import Branch
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.http import JsonResponse
from django.core.cache import cache
import json

class OptimizedSuperAdminDashboardView(UserPassesTestMixin, TemplateView):
    template_name = 'users/dashboards/superadmin_optimized.html'

    def test_func(self):
        return self.request.user.role == 'superadmin'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Use caching to prevent repeated expensive queries
        cache_key = f"dashboard_data_{self.request.user.id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            context.update(cached_data)
            return context
        
        # OPTIMIZED: Use efficient database queries with proper joins
        from core.utils.business_filtering import (
            filter_users_by_business,
            filter_courses_by_business,
            filter_queryset_by_business
        )
        
        # Get business-scoped data efficiently
        accessible_users = filter_users_by_business(self.request.user)
        accessible_courses = filter_courses_by_business(self.request.user)
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.select_related('course', 'user'),  # OPTIMIZED: add select_related
            self.request.user,
            business_field_path='course__branch__business'
        )

        # OPTIMIZED: Single query instead of multiple counts
        enrollment_stats = accessible_enrollments.aggregate(
            total_enrollments=Count('id'),
            completed_enrollments=Count('id', filter=Q(completed=True))
        )
        
        total_enrollments = enrollment_stats['total_enrollments']
        completed_enrollments = enrollment_stats['completed_enrollments']
        
        # Calculate completion rate efficiently
        completion_rate = round(
            (completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0, 
            2
        )
        
        # OPTIMIZED: Limited recent activities to prevent performance issues
        recent_activities = LogEntry.objects.select_related('user').order_by('-action_time')[:5]
        
        # OPTIMIZED: Efficient course data with aggregated enrollments
        courses_with_stats = accessible_courses.annotate(
            total_enrollments=Count('courseenrollment'),
            completed_enrollments=Count(
                Case(
                    When(courseenrollment__completed=True, then=1),
                    output_field=IntegerField()
                )
            )
        ).filter(total_enrollments__gt=0)[:6]
        
        # Calculate progress for courses efficiently
        branch_courses = []
        for course in courses_with_stats:
            progress = round(
                (course.completed_enrollments / course.total_enrollments * 100) 
                if course.total_enrollments > 0 else 0
            )
            course.progress = progress
            branch_courses.append(course)
        
        # OPTIMIZED: Simple activity data without complex date calculations
        now = timezone.now()
        start_date = now - timedelta(days=7)  # Reduced to 7 days for better performance
        
        # Cache the data
        dashboard_data = {
            'total_branches': accessible_users.filter(role='branch_admin').count(),
            'total_users': accessible_users.count(),
            'total_courses': accessible_courses.count(),
            'completion_rate': completion_rate,
            'recent_activities': recent_activities,
            'branch_courses': branch_courses,
            'start_date': start_date.strftime('%d/%m/%Y'),
            'end_date': now.strftime('%d/%m/%Y'),
        }
        
        # Cache for 5 minutes to improve performance
        cache.set(cache_key, dashboard_data, 300)
        
        context.update(dashboard_data)
        return context
