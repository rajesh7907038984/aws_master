from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import View
from django.core.cache import cache
from django.db.models import Count, Q, Avg, Sum, F, Case, When, IntegerField
from django.utils import timezone
from datetime import timedelta, datetime
import json
import logging

from courses.models import Course, CourseEnrollment, TopicProgress
from users.models import CustomUser
from branches.models import Branch
from quiz.models import QuizAttempt, Quiz
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from core.utils.business_filtering import (
    filter_users_by_business,
    filter_courses_by_business,
    filter_queryset_by_business
)

logger = logging.getLogger(__name__)

class PerformanceStatsView(View):
    """View to provide performance statistics data"""
    
    def get(self, request):
        """Get performance statistics for the dashboard"""
        try:
            # Cache key based on user and timeframe
            timeframe = request.GET.get('timeframe', 'month')
            cache_key = f"performance_stats_{request.user.id}_{timeframe}"
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return JsonResponse(cached_data)
            
            # Calculate performance metrics
            performance_data = self.calculate_performance_metrics(request.user, timeframe)
            
            # Cache for 5 minutes
            cache.set(cache_key, performance_data, 300)
            
            return JsonResponse(performance_data)
            
        except Exception as e:
            logger.error(f"Error calculating performance stats: {str(e)}")
            return JsonResponse({
                'error': 'Failed to calculate performance statistics',
                'details': str(e)
            }, status=500)
    
    def calculate_performance_metrics(self, user, timeframe='month'):
        """Calculate comprehensive performance metrics"""
        now = timezone.now()
        
        # Determine date range based on timeframe
        if timeframe == 'day':
            start_date = now - timedelta(days=1)
            time_labels = [f"{i:02d}:00" for i in range(24)]
        elif timeframe == 'week':
            start_date = now - timedelta(days=7)
            time_labels = [(now - timedelta(days=i)).strftime('%a') for i in range(6, -1, -1)]
        elif timeframe == 'year':
            start_date = now - timedelta(days=365)
            time_labels = [(now - timedelta(days=30*i)).strftime('%b') for i in range(12, 0, -1)]
        else:  # month
            start_date = now - timedelta(days=30)
            time_labels = [(now - timedelta(days=i)).strftime('%d') for i in range(29, -1, -1)]
        
        # Get business-filtered data
        accessible_users = filter_users_by_business(user)
        accessible_courses = filter_courses_by_business(user)
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.all(),
            user,
            business_field_path='course__branch__business'
        )
        
        # 1. User Activity Metrics
        user_activity = self.calculate_user_activity(accessible_users, start_date, now, timeframe)
        
        # 2. Course Performance Metrics
        course_performance = self.calculate_course_performance(accessible_courses, accessible_enrollments, start_date, now)
        
        # 3. Learning Progress Metrics
        learning_progress = self.calculate_learning_progress(accessible_enrollments, start_date, now, timeframe)
        
        # 4. Quiz Performance Metrics
        quiz_performance = self.calculate_quiz_performance(accessible_courses, start_date, now, timeframe)
        
        # 5. System Performance Metrics
        system_performance = self.calculate_system_performance(accessible_users, accessible_courses, accessible_enrollments)
        
        # 6. Engagement Metrics
        engagement_metrics = self.calculate_engagement_metrics(accessible_users, accessible_enrollments, start_date, now, timeframe)
        
        return {
            'timeframe': timeframe,
            'time_labels': time_labels,
            'user_activity': user_activity,
            'course_performance': course_performance,
            'learning_progress': learning_progress,
            'quiz_performance': quiz_performance,
            'system_performance': system_performance,
            'engagement_metrics': engagement_metrics,
            'last_updated': now.isoformat()
        }
    
    def calculate_user_activity(self, users, start_date, end_date, timeframe):
        """Calculate user activity metrics"""
        # Active users in timeframe
        active_users = users.filter(
            last_login__gte=start_date,
            last_login__lte=end_date
        ).count()
        
        # New users in timeframe
        new_users = users.filter(
            date_joined__gte=start_date,
            date_joined__lte=end_date
        ).count()
        
        # Total users
        total_users = users.count()
        
        # User activity over time
        activity_data = self.get_activity_over_time(users, start_date, end_date, timeframe)
        
        return {
            'active_users': active_users,
            'new_users': new_users,
            'total_users': total_users,
            'activity_rate': round((active_users / total_users * 100) if total_users > 0 else 0, 2),
            'activity_over_time': activity_data
        }
    
    def calculate_course_performance(self, courses, enrollments, start_date, end_date):
        """Calculate course performance metrics"""
        # Course completion rates
        total_enrollments = enrollments.count()
        completed_enrollments = enrollments.filter(completed=True).count()
        
        # Average completion time
        completed_with_time = enrollments.filter(
            completed=True,
            completion_date__isnull=False,
            enrolled_at__isnull=False
        )
        
        avg_completion_time = 0
        if completed_with_time.exists():
            completion_times = []
            for enrollment in completed_with_time:
                if enrollment.enrolled_at and enrollment.completion_date:
                    time_diff = enrollment.completion_date - enrollment.enrolled_at
                    completion_times.append(time_diff.days)
            
            if completion_times:
                avg_completion_time = sum(completion_times) / len(completion_times)
        
        # Course popularity (enrollments per course)
        course_popularity = courses.annotate(
            enrollment_count=Count('courseenrollment')
        ).order_by('-enrollment_count')[:10]
        
        # Course completion rates by course
        course_completion_rates = []
        for course in courses.annotate(
            total_enrollments=Count('courseenrollment'),
            completed_enrollments=Count(
                Case(
                    When(courseenrollment__completed=True, then=1),
                    output_field=IntegerField()
                )
            )
        ):
            if course.total_enrollments > 0:
                completion_rate = round((course.completed_enrollments / course.total_enrollments) * 100, 2)
                course_completion_rates.append({
                    'course_title': course.title,
                    'completion_rate': completion_rate,
                    'total_enrollments': course.total_enrollments
                })
        
        return {
            'total_courses': courses.count(),
            'total_enrollments': total_enrollments,
            'completed_enrollments': completed_enrollments,
            'overall_completion_rate': round((completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0, 2),
            'avg_completion_time_days': round(avg_completion_time, 1),
            'course_completion_rates': sorted(course_completion_rates, key=lambda x: x['completion_rate'], reverse=True)[:10]
        }
    
    def calculate_learning_progress(self, enrollments, start_date, end_date, timeframe):
        """Calculate learning progress metrics"""
        # Progress distribution
        total_enrollments = enrollments.count()
        completed = enrollments.filter(completed=True).count()
        # Simplified calculation for now - estimate in progress
        in_progress = enrollments.filter(completed=False).count() // 2
        not_started = total_enrollments - completed - in_progress
        
        # Progress over time
        progress_over_time = self.get_progress_over_time(enrollments, start_date, end_date, timeframe)
        
        # Learning velocity (topics completed per day)
        topic_progress = TopicProgress.objects.filter(
            user__in=enrollments.values_list('user', flat=True),
            completed=True,
            completed_at__gte=start_date,
            completed_at__lte=end_date
        )
        
        learning_velocity = 0
        if topic_progress.exists():
            days = (end_date - start_date).days or 1
            learning_velocity = round(topic_progress.count() / days, 2)
        
        return {
            'total_enrollments': total_enrollments,
            'completed': completed,
            'in_progress': in_progress,
            'not_started': not_started,
            'completion_rate': round((completed / total_enrollments * 100) if total_enrollments > 0 else 0, 2),
            'progress_rate': round((in_progress / total_enrollments * 100) if total_enrollments > 0 else 0, 2),
            'learning_velocity': learning_velocity,
            'progress_over_time': progress_over_time
        }
    
    def calculate_quiz_performance(self, courses, start_date, end_date, timeframe):
        """Calculate quiz performance metrics"""
        # Get quiz attempts in timeframe
        quiz_attempts = QuizAttempt.objects.filter(
            quiz__course__in=courses,
            start_time__gte=start_date,
            start_time__lte=end_date
        )
        
        total_attempts = quiz_attempts.count()
        passed_attempts = quiz_attempts.filter(is_completed=True).count()
        
        # Average quiz scores
        avg_score = 0
        if quiz_attempts.exists():
            scores = quiz_attempts.values_list('score', flat=True)
            valid_scores = [s for s in scores if s is not None]
            if valid_scores:
                avg_score = round(sum(valid_scores) / len(valid_scores), 2)
        
        # Quiz performance over time
        quiz_performance_over_time = self.get_quiz_performance_over_time(quiz_attempts, start_date, end_date, timeframe)
        
        # Top performing quizzes - simplified for now
        quiz_stats = Quiz.objects.filter(
            course__in=courses
        )[:10]
        
        top_quizzes = []
        for quiz in quiz_stats:
            top_quizzes.append({
                'quiz_title': quiz.title,
                'avg_score': 0,  # Placeholder
                'pass_rate': 0,  # Placeholder
                'attempt_count': 0  # Placeholder
            })
        
        return {
            'total_attempts': total_attempts,
            'passed_attempts': passed_attempts,
            'pass_rate': round((passed_attempts / total_attempts * 100) if total_attempts > 0 else 0, 2),
            'avg_score': avg_score,
            'performance_over_time': quiz_performance_over_time,
            'top_quizzes': top_quizzes
        }
    
    def calculate_system_performance(self, users, courses, enrollments):
        """Calculate system performance metrics"""
        # Content metrics
        total_courses = courses.count()
        total_users = users.count()
        total_enrollments = enrollments.count()
        
        # Content utilization
        courses_with_enrollments = courses.filter(courseenrollment__isnull=False).distinct().count()
        content_utilization = round((courses_with_enrollments / total_courses * 100) if total_courses > 0 else 0, 2)
        
        # User engagement ratio
        active_users = users.filter(last_login__gte=timezone.now() - timedelta(days=30)).count()
        user_engagement = round((active_users / total_users * 100) if total_users > 0 else 0, 2)
        
        # Average enrollments per course
        avg_enrollments_per_course = round(total_enrollments / total_courses, 2) if total_courses > 0 else 0
        
        return {
            'total_courses': total_courses,
            'total_users': total_users,
            'total_enrollments': total_enrollments,
            'content_utilization': content_utilization,
            'user_engagement': user_engagement,
            'avg_enrollments_per_course': avg_enrollments_per_course
        }
    
    def calculate_engagement_metrics(self, users, enrollments, start_date, end_date, timeframe):
        """Calculate engagement metrics"""
        # Session duration (estimated from login patterns)
        user_ct = ContentType.objects.get_for_model(CustomUser)
        login_entries = LogEntry.objects.filter(
            content_type=user_ct,
            action_time__gte=start_date,
            action_time__lte=end_date
        ).order_by('action_time')
        
        # Daily active users
        daily_active_users = self.get_daily_active_users(users, start_date, end_date, timeframe)
        
        # Course engagement (time spent)
        topic_progress = TopicProgress.objects.filter(
            user__in=enrollments.values_list('user', flat=True),
            completed_at__gte=start_date,
            completed_at__lte=end_date
        )
        
        # Return engagement data
        return {
            'daily_active_users': daily_active_users,
            'total_logins': login_entries.count(),
            'avg_session_duration': 45,  # Placeholder - would need actual session tracking
            'engagement_score': self.calculate_engagement_score(enrollments, topic_progress)
        }
    
    def get_activity_over_time(self, users, start_date, end_date, timeframe):
        """Get user activity data over time"""
        now = timezone.now()
        activity_data = []
        
        if timeframe == 'day':
            # Hourly data
            for hour in range(24):
                hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)
                count = users.filter(
                    last_login__gte=hour_start,
                    last_login__lt=hour_end
                ).count()
                activity_data.append(count)
        else:
            # Daily data
            days = 7 if timeframe == 'week' else 30
            for i in range(days):
                day_start = now - timedelta(days=days-i-1)
                day_end = day_start + timedelta(days=1)
                count = users.filter(
                    last_login__gte=day_start,
                    last_login__lt=day_end
                ).count()
                activity_data.append(count)
        
        return activity_data
    
    def get_progress_over_time(self, enrollments, start_date, end_date, timeframe):
        """Get learning progress data over time"""
        now = timezone.now()
        progress_data = []
        
        if timeframe == 'day':
            # Hourly data
            for hour in range(24):
                hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)
                count = enrollments.filter(
                    completion_date__gte=hour_start,
                    completion_date__lt=hour_end
                ).count()
                progress_data.append(count)
        else:
            # Daily data
            days = 7 if timeframe == 'week' else 30
            for i in range(days):
                day_start = now - timedelta(days=days-i-1)
                day_end = day_start + timedelta(days=1)
                count = enrollments.filter(
                    completion_date__gte=day_start,
                    completion_date__lt=day_end
                ).count()
                progress_data.append(count)
        
        return progress_data
    
    def get_quiz_performance_over_time(self, quiz_attempts, start_date, end_date, timeframe):
        """Get quiz performance data over time"""
        now = timezone.now()
        performance_data = []
        
        if timeframe == 'day':
            # Hourly data
            for hour in range(24):
                hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)
                attempts = quiz_attempts.filter(
                    start_time__gte=hour_start,
                    start_time__lt=hour_end
                )
                avg_score = attempts.aggregate(avg=Avg('score'))['avg'] or 0
                performance_data.append(round(avg_score, 2))
        else:
            # Daily data
            days = 7 if timeframe == 'week' else 30
            for i in range(days):
                day_start = now - timedelta(days=days-i-1)
                day_end = day_start + timedelta(days=1)
                attempts = quiz_attempts.filter(
                    start_time__gte=day_start,
                    start_time__lt=day_end
                )
                avg_score = attempts.aggregate(avg=Avg('score'))['avg'] or 0
                performance_data.append(round(avg_score, 2))
        
        return performance_data
    
    def get_daily_active_users(self, users, start_date, end_date, timeframe):
        """Get daily active users data"""
        now = timezone.now()
        dau_data = []
        
        if timeframe == 'day':
            # Hourly data
            for hour in range(24):
                hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)
                count = users.filter(
                    last_login__gte=hour_start,
                    last_login__lt=hour_end
                ).count()
                dau_data.append(count)
        else:
            # Daily data
            days = 7 if timeframe == 'week' else 30
            for i in range(days):
                day_start = now - timedelta(days=days-i-1)
                day_end = day_start + timedelta(days=1)
                count = users.filter(
                    last_login__gte=day_start,
                    last_login__lt=day_end
                ).count()
                dau_data.append(count)
        
        return dau_data
    
    def calculate_engagement_score(self, enrollments, topic_progress):
        """Calculate overall engagement score (0-100)"""
        if not enrollments.exists():
            return 0
        
        # Factors: completion rate, activity frequency, content interaction
        completion_rate = enrollments.filter(completed=True).count() / enrollments.count()
        activity_score = min(topic_progress.count() / 10, 1)  # Normalize to 0-1
        
        engagement_score = (completion_rate * 0.6 + activity_score * 0.4) * 100
        return round(engagement_score, 2)


@method_decorator(login_required, name='dispatch')
class PerformanceChartDataView(View):
    """View to provide chart data for specific performance metrics"""
    
    def get(self, request):
        """Get chart data for specific metric"""
        chart_type = request.GET.get('chart_type')
        timeframe = request.GET.get('timeframe', 'month')
        
        try:
            if chart_type == 'user_activity':
                data = self.get_user_activity_chart_data(request.user, timeframe)
            elif chart_type == 'course_performance':
                data = self.get_course_performance_chart_data(request.user, timeframe)
            elif chart_type == 'learning_progress':
                data = self.get_learning_progress_chart_data(request.user, timeframe)
            elif chart_type == 'quiz_performance':
                data = self.get_quiz_performance_chart_data(request.user, timeframe)
            elif chart_type == 'engagement':
                data = self.get_engagement_chart_data(request.user, timeframe)
            else:
                return JsonResponse({'error': 'Invalid chart type'}, status=400)
            
            return JsonResponse(data)
            
        except Exception as e:
            logger.error(f"Error getting chart data: {str(e)}")
            return JsonResponse({'error': 'Failed to get chart data'}, status=500)
    
    def get_user_activity_chart_data(self, user, timeframe):
        """Get user activity chart data"""
        # Implementation for user activity chart
        return {'labels': [], 'datasets': []}
    
    def get_course_performance_chart_data(self, user, timeframe):
        """Get course performance chart data"""
        # Implementation for course performance chart
        return {'labels': [], 'datasets': []}
    
    def get_learning_progress_chart_data(self, user, timeframe):
        """Get learning progress chart data"""
        # Implementation for learning progress chart
        return {'labels': [], 'datasets': []}
    
    def get_quiz_performance_chart_data(self, user, timeframe):
        """Get quiz performance chart data"""
        # Implementation for quiz performance chart
        return {'labels': [], 'datasets': []}
    
    def get_engagement_chart_data(self, user, timeframe):
        """Get engagement chart data"""
        # Implementation for engagement chart
        return {'labels': [], 'datasets': []}
