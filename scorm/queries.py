"""
SCORM Query Manager
Collection of queries for retrieving SCORM data
"""
from django.db import models
from django.db.models import Q, Count, Avg, Sum, Max, Min
from django.contrib.auth import get_user_model
from .models import ScormPackage, ScormAttempt

User = get_user_model()


class ScormQueryManager:
    """
    Manager for SCORM-related database queries
    """
    
    @staticmethod
    def get_user_performance_summary(user_id):
        """
        Get performance summary for a user across all SCORM courses
        
        Args:
            user_id (int): User ID
            
        Returns:
            dict: Performance summary
        """
        attempts = ScormAttempt.objects.filter(user_id=user_id)
        
        summary = {
            'total_attempts': attempts.count(),
            'completed_attempts': attempts.filter(lesson_status='completed').count(),
            'passed_attempts': attempts.filter(lesson_status='passed').count(),
            'failed_attempts': attempts.filter(lesson_status='failed').count(),
            'average_score': 0,
            'best_score': 0,
            'total_time_spent': 0,
            'courses_completed': 0
        }
        
        if summary['total_attempts'] > 0:
            # Calculate average score
            scores = attempts.exclude(score_raw__isnull=True).values_list('score_raw', flat=True)
            if scores:
                summary['average_score'] = sum(scores) / len(scores)
                summary['best_score'] = max(scores)
            
            # Calculate total time spent
            time_values = attempts.exclude(time_spent_seconds__isnull=True).values_list('time_spent_seconds', flat=True)
            if time_values:
                summary['total_time_spent'] = sum(time_values)
            
            # Count completed courses
            summary['courses_completed'] = attempts.filter(
                lesson_status__in=['completed', 'passed']
            ).values('scorm_package_id').distinct().count()
        
        return summary
    
    @staticmethod
    def get_course_performance_analytics(scorm_package_id):
        """
        Get performance analytics for a specific SCORM course
        
        Args:
            scorm_package_id (int): SCORM package ID
            
        Returns:
            dict: Course analytics
        """
        attempts = ScormAttempt.objects.filter(scorm_package_id=scorm_package_id)
        
        analytics = {
            'total_attempts': attempts.count(),
            'unique_users': attempts.values('user_id').distinct().count(),
            'completion_rate': 0,
            'pass_rate': 0,
            'average_score': 0,
            'average_time': 0,
            'score_distribution': {},
            'time_distribution': {}
        }
        
        if analytics['total_attempts'] > 0:
            # Calculate completion and pass rates
            completed = attempts.filter(lesson_status='completed').count()
            passed = attempts.filter(lesson_status='passed').count()
            
            analytics['completion_rate'] = (completed / analytics['total_attempts']) * 100
            analytics['pass_rate'] = (passed / analytics['total_attempts']) * 100
            
            # Calculate average score
            scores = attempts.exclude(score_raw__isnull=True).values_list('score_raw', flat=True)
            if scores:
                analytics['average_score'] = sum(scores) / len(scores)
            
            # Calculate average time
            times = attempts.exclude(time_spent_seconds__isnull=True).values_list('time_spent_seconds', flat=True)
            if times:
                analytics['average_time'] = sum(times) / len(times)
        
        return analytics
    
    @staticmethod
    def get_learner_progress_tracking(user_id, scorm_package_id):
        """
        Get detailed progress tracking for a learner on a specific course
        
        Args:
            user_id (int): User ID
            scorm_package_id (int): SCORM package ID
            
        Returns:
            dict: Progress tracking data
        """
        attempts = ScormAttempt.objects.filter(
            user_id=user_id,
            scorm_package_id=scorm_package_id
        ).order_by('attempt_number')
        
        if not attempts.exists():
            return None
        
        progress = {
            'user_id': user_id,
            'scorm_package_id': scorm_package_id,
            'total_attempts': attempts.count(),
            'current_attempt': attempts.last(),
            'attempt_history': [],
            'progress_summary': {}
        }
        
        # Build attempt history
        for attempt in attempts:
            attempt_data = {
                'attempt_number': attempt.attempt_number,
                'lesson_status': attempt.lesson_status,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'score_max': float(attempt.score_max) if attempt.score_max else None,
                'time_spent_seconds': attempt.time_spent_seconds,
                'started_at': attempt.started_at,
                'completed_at': attempt.completed_at,
                'last_accessed': attempt.last_accessed
            }
            progress['attempt_history'].append(attempt_data)
        
        # Calculate progress summary
        latest_attempt = attempts.last()
        if latest_attempt:
            progress['progress_summary'] = {
                'current_status': latest_attempt.lesson_status,
                'current_score': float(latest_attempt.score_raw) if latest_attempt.score_raw else None,
                'total_time_spent': sum(a.time_spent_seconds or 0 for a in attempts),
                'last_accessed': latest_attempt.last_accessed,
                'is_completed': latest_attempt.lesson_status in ['completed', 'passed'],
                'is_passed': latest_attempt.lesson_status == 'passed'
            }
        
        return progress
    
    @staticmethod
    def _parse_scorm_time(time_str):
        """
        Parse SCORM time format to seconds
        
        Args:
            time_str (str): SCORM time format (hhhh:mm:ss.ss)
            
        Returns:
            int: Time in seconds
        """
        if not time_str:
            return 0
        
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + int(seconds)
        except (ValueError, IndexError):
            pass
        
        return 0
    
    @staticmethod
    def generate_learner_report(user_id, scorm_package_id=None):
        """
        Generate comprehensive report for a learner
        
        Args:
            user_id (int): User ID
            scorm_package_id (int, optional): Specific SCORM package
            
        Returns:
            dict: Learner report
        """
        user = User.objects.get(id=user_id)
        
        # Get all attempts for user
        attempts_query = ScormAttempt.objects.filter(user_id=user_id)
        if scorm_package_id:
            attempts_query = attempts_query.filter(scorm_package_id=scorm_package_id)
        
        attempts = attempts_query.select_related('scorm_package', 'scorm_package__topic')
        
        report = {
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name
            },
            'summary': ScormQueryManager.get_user_performance_summary(user_id),
            'courses': [],
            'generated_at': models.DateTimeField(auto_now=True)
        }
        
        # Group attempts by course
        courses = {}
        for attempt in attempts:
            package = attempt.scorm_package
            course_id = package.topic.course.id if package.topic.course else None
            
            if course_id not in courses:
                courses[course_id] = {
                    'course_id': course_id,
                    'course_title': package.topic.course.title if package.topic.course else 'Unknown Course',
                    'package_title': package.title,
                    'attempts': []
                }
            
            courses[course_id]['attempts'].append({
                'attempt_number': attempt.attempt_number,
                'lesson_status': attempt.lesson_status,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'score_max': float(attempt.score_max) if attempt.score_max else None,
                'time_spent_seconds': attempt.time_spent_seconds,
                'started_at': attempt.started_at,
                'completed_at': attempt.completed_at
            })
        
        report['courses'] = list(courses.values())
        return report
    
    @staticmethod
    def generate_course_report(scorm_package_id):
        """
        Generate comprehensive report for a SCORM course
        
        Args:
            scorm_package_id (int): SCORM package ID
            
        Returns:
            dict: Course report
        """
        package = ScormPackage.objects.select_related('topic', 'topic__course').get(id=scorm_package_id)
        attempts = ScormAttempt.objects.filter(scorm_package_id=scorm_package_id).select_related('user')
        
        report = {
            'package': {
                'id': package.id,
                'title': package.title,
                'version': package.version,
                'course_title': package.topic.course.title if package.topic.course else 'Unknown Course'
            },
            'analytics': ScormQueryManager.get_course_performance_analytics(scorm_package_id),
            'learners': [],
            'generated_at': models.DateTimeField(auto_now=True)
        }
        
        # Group attempts by user
        users = {}
        for attempt in attempts:
            user_id = attempt.user.id
            
            if user_id not in users:
                users[user_id] = {
                    'user': {
                        'id': attempt.user.id,
                        'username': attempt.user.username,
                        'email': attempt.user.email,
                        'first_name': attempt.user.first_name,
                        'last_name': attempt.user.last_name
                    },
                    'attempts': []
                }
            
            users[user_id]['attempts'].append({
                'attempt_number': attempt.attempt_number,
                'lesson_status': attempt.lesson_status,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'score_max': float(attempt.score_max) if attempt.score_max else None,
                'time_spent_seconds': attempt.time_spent_seconds,
                'started_at': attempt.started_at,
                'completed_at': attempt.completed_at
            })
        
        report['learners'] = list(users.values())
        return report