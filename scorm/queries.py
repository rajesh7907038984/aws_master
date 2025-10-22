# -*- coding: utf-8 -*-
"""
SCORM Database Queries
Collection of queries for retrieving SCORM interaction data
"""
from django.db import models
from django.db.models import Q, Count, Avg, Sum, Max, Min
from django.contrib.auth import get_user_model
from .models import ScormPackage, ScormAttempt, ScormInteraction, ScormObjective, ScormComment

User = get_user_model()


class ScormQueryManager:
    """
    Manager for SCORM-related database queries
    """
    
    @staticmethod
    def get_user_interactions(user_id, scorm_package_id=None):
        """
        Get all interactions for a specific user
        
        Args:
            user_id (int): User ID
            scorm_package_id (int, optional): Specific SCORM package ID
            
        Returns:
            QuerySet: ScormInteraction objects
        """
        query = ScormInteraction.objects.filter(attempt__user_id=user_id)
        
        if scorm_package_id:
            query = query.filter(attempt__scorm_package_id=scorm_package_id)
        
        return query.select_related('attempt', 'attempt__user', 'attempt__scorm_package')
    
    @staticmethod
    def get_course_interactions(scorm_package_id):
        """
        Get all interactions for a specific SCORM course
        
        Args:
            scorm_package_id (int): SCORM package ID
            
        Returns:
            QuerySet: ScormInteraction objects
        """
        return ScormInteraction.objects.filter(
            attempt__scorm_package_id=scorm_package_id
        ).select_related('attempt', 'attempt__user')
    
    @staticmethod
    def get_interaction_analytics(scorm_package_id=None, user_id=None):
        """
        Get analytics for interactions
        
        Args:
            scorm_package_id (int, optional): Specific SCORM package
            user_id (int, optional): Specific user
            
        Returns:
            dict: Analytics data
        """
        query = ScormInteraction.objects.all()
        
        if scorm_package_id:
            query = query.filter(attempt__scorm_package_id=scorm_package_id)
        
        if user_id:
            query = query.filter(attempt__user_id=user_id)
        
        analytics = {
            'total_interactions': query.count(),
            'correct_interactions': query.filter(result='correct').count(),
            'incorrect_interactions': query.filter(result='incorrect').count(),
            'interaction_types': {},
            'average_latency': 0,
            'top_performers': [],
            'difficult_interactions': []
        }
        
        # Calculate accuracy rate
        if analytics['total_interactions'] > 0:
            analytics['accuracy_rate'] = (
                analytics['correct_interactions'] / analytics['total_interactions']
            ) * 100
        
        # Group by interaction type
        type_counts = query.values('interaction_type').annotate(
            count=Count('id'),
            correct=Count('id', filter=Q(result='correct')),
            incorrect=Count('id', filter=Q(result='incorrect'))
        )
        
        for item in type_counts:
            interaction_type = item['interaction_type']
            analytics['interaction_types'][interaction_type] = {
                'total': item['count'],
                'correct': item['correct'],
                'incorrect': item['incorrect'],
                'accuracy_rate': (item['correct'] / item['count']) * 100 if item['count'] > 0 else 0
            }
        
        # Calculate average latency
        latencies = query.exclude(latency='').values_list('latency', flat=True)
        if latencies:
            # Convert SCORM latency format to seconds and calculate average
            total_seconds = 0
            count = 0
            for latency in latencies:
                if latency.startswith('PT') and latency.endswith('S'):
                    try:
                        seconds = float(latency[2:-1])
                        total_seconds += seconds
                        count += 1
                    except ValueError:
                        continue
            
            if count > 0:
                analytics['average_latency'] = total_seconds / count
        
        return analytics
    
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
            'average_score': 0,
            'total_time_spent': 0,
            'courses_taken': attempts.values('scorm_package').distinct().count(),
            'interaction_summary': {},
            'recent_activity': []
        }
        
        # Calculate average score
        scores = [float(attempt.score_raw) for attempt in attempts if attempt.score_raw]
        if scores:
            summary['average_score'] = sum(scores) / len(scores)
        
        # Calculate total time spent
        for attempt in attempts:
            if attempt.total_time:
                time_seconds = ScormQueryManager._parse_scorm_time(attempt.total_time)
                summary['total_time_spent'] += time_seconds
        
        # Get interaction summary
        interactions = ScormInteraction.objects.filter(attempt__user_id=user_id)
        summary['interaction_summary'] = {
            'total_interactions': interactions.count(),
            'correct_interactions': interactions.filter(result='correct').count(),
            'accuracy_rate': 0
        }
        
        if summary['interaction_summary']['total_interactions'] > 0:
            summary['interaction_summary']['accuracy_rate'] = (
                summary['interaction_summary']['correct_interactions'] / 
                summary['interaction_summary']['total_interactions']
            ) * 100
        
        # Get recent activity
        recent_attempts = attempts.order_by('-last_accessed')[:5]
        summary['recent_activity'] = [
            {
                'course_title': attempt.scorm_package.title,
                'status': attempt.lesson_status,
                'score': float(attempt.score_raw) if attempt.score_raw else None,
                'last_accessed': attempt.last_accessed
            }
            for attempt in recent_attempts
        ]
        
        return summary
    
    @staticmethod
    def get_course_performance_analytics(scorm_package_id):
        """
        Get performance analytics for a specific SCORM course
        
        Args:
            scorm_package_id (int): SCORM package ID
            
        Returns:
            dict: Course performance analytics
        """
        attempts = ScormAttempt.objects.filter(scorm_package_id=scorm_package_id)
        interactions = ScormInteraction.objects.filter(attempt__scorm_package_id=scorm_package_id)
        
        analytics = {
            'course_info': {
                'package_id': scorm_package_id,
                'total_attempts': attempts.count(),
                'unique_learners': attempts.values('user').distinct().count()
            },
            'completion_rates': {
                'completed': attempts.filter(lesson_status='completed').count(),
                'passed': attempts.filter(lesson_status='passed').count(),
                'failed': attempts.filter(lesson_status='failed').count(),
                'incomplete': attempts.filter(lesson_status='incomplete').count()
            },
            'scoring_analytics': {
                'average_score': 0,
                'highest_score': 0,
                'lowest_score': 0,
                'score_distribution': {}
            },
            'interaction_analytics': {
                'total_interactions': interactions.count(),
                'most_difficult_interactions': [],
                'interaction_type_performance': {}
            },
            'time_analytics': {
                'average_completion_time': 0,
                'fastest_completion': 0,
                'slowest_completion': 0
            }
        }
        
        # Calculate completion rates
        total_attempts = analytics['course_info']['total_attempts']
        if total_attempts > 0:
            for status in analytics['completion_rates']:
                analytics['completion_rates'][status] = (
                    analytics['completion_rates'][status] / total_attempts
                ) * 100
        
        # Calculate scoring analytics
        scores = [float(attempt.score_raw) for attempt in attempts if attempt.score_raw]
        if scores:
            analytics['scoring_analytics']['average_score'] = sum(scores) / len(scores)
            analytics['scoring_analytics']['highest_score'] = max(scores)
            analytics['scoring_analytics']['lowest_score'] = min(scores)
            
            # Score distribution
            score_ranges = [(0, 50), (50, 70), (70, 85), (85, 100)]
            for min_score, max_score in score_ranges:
                range_count = len([s for s in scores if min_score <= s < max_score])
                analytics['scoring_analytics']['score_distribution'][f'{min_score}-{max_score}'] = range_count
        
        # Calculate interaction analytics
        if interactions.exists():
            # Find most difficult interactions (lowest accuracy)
            interaction_accuracy = interactions.values('interaction_id').annotate(
                total=Count('id'),
                correct=Count('id', filter=Q(result='correct'))
            ).annotate(
                accuracy=Count('id', filter=Q(result='correct')) * 100.0 / Count('id')
            ).order_by('accuracy')[:5]
            
            analytics['interaction_analytics']['most_difficult_interactions'] = [
                {
                    'interaction_id': item['interaction_id'],
                    'accuracy_rate': item['accuracy'],
                    'total_attempts': item['total']
                }
                for item in interaction_accuracy
            ]
        
        # Calculate time analytics
        completion_times = []
        for attempt in attempts:
            if attempt.total_time:
                time_seconds = ScormQueryManager._parse_scorm_time(attempt.total_time)
                completion_times.append(time_seconds)
        
        if completion_times:
            analytics['time_analytics']['average_completion_time'] = sum(completion_times) / len(completion_times)
            analytics['time_analytics']['fastest_completion'] = min(completion_times)
            analytics['time_analytics']['slowest_completion'] = max(completion_times)
        
        return analytics
    
    @staticmethod
    def get_learner_progress_tracking(user_id, scorm_package_id):
        """
        Track learner progress through a SCORM course
        
        Args:
            user_id (int): User ID
            scorm_package_id (int): SCORM package ID
            
        Returns:
            dict: Progress tracking data
        """
        attempt = ScormAttempt.objects.filter(
            user_id=user_id,
            scorm_package_id=scorm_package_id
        ).order_by('-attempt_number').first()
        
        if not attempt:
            return {'error': 'No attempt found for this user and course'}
        
        interactions = ScormInteraction.objects.filter(attempt=attempt)
        objectives = ScormObjective.objects.filter(attempt=attempt)
        
        progress = {
            'attempt_info': {
                'attempt_number': attempt.attempt_number,
                'status': attempt.lesson_status,
                'completion_status': attempt.completion_status,
                'success_status': attempt.success_status,
                'score': float(attempt.score_raw) if attempt.score_raw else None,
                'started_at': attempt.started_at,
                'last_accessed': attempt.last_accessed,
                'completed_at': attempt.completed_at
            },
            'interaction_progress': {
                'total_interactions': interactions.count(),
                'completed_interactions': interactions.exclude(result='').count(),
                'correct_interactions': interactions.filter(result='correct').count(),
                'interaction_details': []
            },
            'objective_progress': {
                'total_objectives': objectives.count(),
                'completed_objectives': objectives.exclude(completion_status='not attempted').count(),
                'passed_objectives': objectives.filter(success_status='passed').count(),
                'objective_details': []
            },
            'time_tracking': {
                'total_time': attempt.total_time,
                'session_time': attempt.session_time,
                'time_spent_seconds': ScormQueryManager._parse_scorm_time(attempt.total_time)
            }
        }
        
        # Add interaction details
        for interaction in interactions:
            progress['interaction_progress']['interaction_details'].append({
                'interaction_id': interaction.interaction_id,
                'type': interaction.interaction_type,
                'result': interaction.result,
                'timestamp': interaction.timestamp,
                'latency': interaction.latency
            })
        
        # Add objective details
        for objective in objectives:
            progress['objective_progress']['objective_details'].append({
                'objective_id': objective.objective_id,
                'success_status': objective.success_status,
                'completion_status': objective.completion_status,
                'score': float(objective.score_raw) if objective.score_raw else None
            })
        
        return progress
    
    @staticmethod
    def _parse_scorm_time(time_str):
        """Parse SCORM time format to seconds"""
        if not time_str:
            return 0
        
        try:
            # SCORM format: hhhh:mm:ss.ss
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            pass
        
        return 0


class ScormReportGenerator:
    """
    Generator for SCORM reports
    """
    
    @staticmethod
    def generate_learner_report(user_id, scorm_package_id=None):
        """
        Generate comprehensive learner report
        
        Args:
            user_id (int): User ID
            scorm_package_id (int, optional): Specific SCORM package
            
        Returns:
            dict: Learner report data
        """
        report = {
            'learner_info': {
                'user_id': user_id,
                'username': User.objects.get(id=user_id).username
            },
            'performance_summary': ScormQueryManager.get_user_performance_summary(user_id),
            'course_analytics': [],
            'interaction_analytics': ScormQueryManager.get_interaction_analytics(user_id=user_id),
            'recommendations': []
        }
        
        # Get course-specific analytics if package ID provided
        if scorm_package_id:
            report['course_analytics'].append(
                ScormQueryManager.get_course_performance_analytics(scorm_package_id)
            )
            report['progress_tracking'] = ScormQueryManager.get_learner_progress_tracking(
                user_id, scorm_package_id
            )
        
        # Generate recommendations
        performance = report['performance_summary']
        if performance['average_score'] < 70:
            report['recommendations'].append('Consider additional study time')
        
        if performance['interaction_summary']['accuracy_rate'] < 80:
            report['recommendations'].append('Review incorrect answers and retake course')
        
        return report
    
    @staticmethod
    def generate_course_report(scorm_package_id):
        """
        Generate comprehensive course report
        
        Args:
            scorm_package_id (int): SCORM package ID
            
        Returns:
            dict: Course report data
        """
        report = {
            'course_info': {
                'package_id': scorm_package_id,
                'package': ScormPackage.objects.get(id=scorm_package_id)
            },
            'performance_analytics': ScormQueryManager.get_course_performance_analytics(scorm_package_id),
            'interaction_analytics': ScormQueryManager.get_interaction_analytics(scorm_package_id=scorm_package_id),
            'learner_rankings': [],
            'recommendations': []
        }
        
        # Get top performers
        top_performers = ScormAttempt.objects.filter(
            scorm_package_id=scorm_package_id,
            score_raw__isnull=False
        ).order_by('-score_raw')[:10]
        
        report['learner_rankings'] = [
            {
                'user_id': attempt.user_id,
                'username': attempt.user.username,
                'score': float(attempt.score_raw),
                'status': attempt.lesson_status,
                'completed_at': attempt.completed_at
            }
            for attempt in top_performers
        ]
        
        # Generate recommendations
        analytics = report['performance_analytics']
        if analytics['completion_rates']['failed'] > 20:
            report['recommendations'].append('Consider reviewing course content difficulty')
        
        if analytics['time_analytics']['average_completion_time'] > 3600:  # 1 hour
            report['recommendations'].append('Course may be too long, consider breaking into modules')
        
        return report
