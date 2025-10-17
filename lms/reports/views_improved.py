"""
Improved Reports Views with Enhanced Data Accuracy
Fixes time and score data issues in learning reports
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.urls import reverse
from django.db.models import Sum, Avg, Count, Q, F
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
import logging

from courses.models import TopicProgress, CourseEnrollment
from django.contrib.auth import get_user_model
from core.utils.scoring import ScoreCalculationService
from core.utils.timezone_utils import TimezoneUtils

User = get_user_model()
logger = logging.getLogger(__name__)

def _get_user_report_data_improved(request, user_id):
    """
    Enhanced helper function to get all user report data with improved accuracy.
    Includes data validation, consistency checks, and better error handling.
    """
    try:
        user = get_object_or_404(User, id=user_id)
        logger.info(f"Getting report data for user: {user.username}")
        
        # Check if the user has access to view this user's data
        if request.user.role == 'learner':
            if request.user.id != user_id:
                messages.error(request, "You can only view your own profile report")
                return None
        elif not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin'] or 
                request.user.role == 'admin'):
            if not (request.user.branch and user.branch and request.user.branch.id == user.branch.id):
                messages.error(request, "You don't have permission to view this user's data")
                return None
    except Http404:
        logger.warning(f"User with ID {user_id} not found")
        messages.error(request, f"User with ID {user_id} not found")
        return None
    
    # Ensure data consistency before calculations
    _ensure_data_consistency(user)
    
    # Get user course statistics with improved logic
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    user_stats = User.objects.filter(id=user_id).annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        
        # In progress: enrolled, not completed, but has been accessed at some point
        in_progress_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False
        ), distinct=True),
        
        # Not started: enrolled but never accessed
        not_started_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=True
        ), distinct=True),
        
        total_time_spent=Sum('topic_progress__total_time_spent', default=0)
    ).first()
    
    # Handle user with no stats
    if not user_stats:
        user_stats = User.objects.get(id=user_id)
        user_stats.assigned_count = 0
        user_stats.completed_count = 0
        user_stats.in_progress_count = 0
        user_stats.not_passed_count = 0
        user_stats.not_started_count = 0
        user_stats.total_time_spent = 0
    
    # Calculate completion rate
    if user_stats.assigned_count > 0:
        completion_rate = round((user_stats.completed_count / user_stats.assigned_count) * 100, 1)
    else:
        completion_rate = 0.0
    
    # Get user enrolled courses with detailed information and calculated fields
    user_courses = CourseEnrollment.objects.filter(user=user).select_related('course').order_by('-enrolled_at')
    
    # Add calculated fields for each enrollment with improved accuracy
    for enrollment in user_courses:
        # Ensure completion status is accurate
        enrollment.sync_completion_status()
        
        # Calculate progress percentage
        enrollment.calculated_progress = enrollment.progress_percentage
        
        # Get all topic progress for this course with better filtering
        course_topic_progress = TopicProgress.objects.filter(
            user=user,
            topic__courses=enrollment.course
        )
        
        # Calculate accurate average score from completed topics
        enrollment.calculated_score = _calculate_accurate_course_score(course_topic_progress)
        
        # Calculate total time spent on course with validation
        course_stats = course_topic_progress.aggregate(
            total_time=Sum('total_time_spent', default=0),
            total_attempts=Sum('attempts', default=0)
        )
        
        enrollment.course_time_spent = max(0, course_stats['total_time'] or 0)  # Ensure non-negative
        enrollment.course_attempts = course_stats['total_attempts'] or 0
        
        # Format time spent for display with timezone support
        user_timezone = TimezoneUtils.get_user_timezone(user)
        enrollment.formatted_time_spent = TimezoneUtils.format_time_spent(
            enrollment.course_time_spent,
            user_timezone
        )
    
    # Recalculate user stats after syncing completion status
    user_stats = User.objects.filter(id=user_id).annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        
        # In progress: enrolled, not completed, accessed recently (within 30 days)
        in_progress_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False,
            courseenrollment__last_accessed__gte=thirty_days_ago
        ), distinct=True),
        
        # Not passed: enrolled, not completed, but hasn't been accessed recently (>30 days)
        not_passed_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False,
            courseenrollment__last_accessed__lt=thirty_days_ago
        ), distinct=True),
        
        # Not started: enrolled but never accessed
        not_started_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=True
        ), distinct=True),
        
        total_time_spent=Sum('topic_progress__total_time_spent', default=0)
    ).first()
    
    # Handle user with no stats
    if not user_stats:
        user_stats = User.objects.get(id=user_id)
        user_stats.assigned_count = 0
        user_stats.completed_count = 0
        user_stats.in_progress_count = 0
        user_stats.not_passed_count = 0
        user_stats.not_started_count = 0
        user_stats.total_time_spent = 0
    
    # Recalculate completion rate with updated data
    if user_stats.assigned_count > 0:
        completion_rate = round((user_stats.completed_count / user_stats.assigned_count) * 100, 1)
    else:
        completion_rate = 0.0
    
    # Format training time with proper null handling and timezone support
    total_seconds = user_stats.total_time_spent if user_stats.total_time_spent is not None else 0
    # Ensure non-negative values and handle potential data corruption
    total_seconds = max(0, total_seconds)
    
    # Use timezone-aware formatting
    user_timezone = TimezoneUtils.get_user_timezone(user)
    training_time = TimezoneUtils.format_time_spent(total_seconds, user_timezone)
    
    # Get Learning Activities data with improved accuracy
    topic_progress = TopicProgress.objects.filter(
        user=user
    ).select_related('topic').order_by('-last_accessed')
    
    # Add formatted time for each progress record
    for progress in topic_progress:
        progress.formatted_time = TimezoneUtils.format_time_spent(
            progress.total_time_spent or 0,
            user_timezone
        )
    
    # Get user timeline activities
    from reports.models import Event
    user_activities = Event.objects.filter(user=user).select_related('course').order_by('-created_at')[:20]
    
    # Prepare context data
    context = {
        'user': user,
        'user_stats': user_stats,
        'completion_rate': completion_rate,
        'completed_courses': user_stats.completed_count,
        'courses_in_progress': user_stats.in_progress_count,
        'courses_not_passed': user_stats.not_passed_count,
        'courses_not_started': user_stats.not_started_count,
        'total_courses': user_stats.assigned_count,
        'training_time': training_time,
        'user_courses': user_courses,
        'topic_progress': topic_progress,
        'user_activities': user_activities,
        'user_timezone': user_timezone,
    }
    
    return context

def _ensure_data_consistency(user):
    """
    Ensure data consistency for a user's progress records
    """
    try:
        # Fix negative time values
        TopicProgress.objects.filter(
            user=user,
            total_time_spent__lt=0
        ).update(total_time_spent=0)
        
        # Fix null scores for completed records
        TopicProgress.objects.filter(
            user=user,
            completed=True,
            last_score__isnull=True
        ).update(last_score=0.00)
        
        # Validate and normalize scores
        progress_records = TopicProgress.objects.filter(
            user=user,
            last_score__isnull=False
        )
        
        for progress in progress_records:
            normalized_score = ScoreCalculationService.normalize_score(progress.last_score)
            if normalized_score is not None and normalized_score != progress.last_score:
                progress.last_score = normalized_score
                progress.save()
        
        logger.info(f"Data consistency ensured for user {user.username}")
        
    except Exception as e:
        logger.error(f"Error ensuring data consistency for user {user.id}: {e}")

def _calculate_accurate_course_score(course_topic_progress):
    """
    Calculate accurate course score with proper validation
    """
    try:
        # Get completed topics with valid scores
        completed_progress = course_topic_progress.filter(
            completed=True,
            last_score__isnull=False
        )
        
        if not completed_progress.exists():
            return None
        
        # Calculate average score with proper normalization
        scores = []
        for progress in completed_progress:
            normalized_score = ScoreCalculationService.normalize_score(progress.last_score)
            if normalized_score is not None:
                scores.append(float(normalized_score))
        
        if scores:
            avg_score = sum(scores) / len(scores)
            return round(avg_score, 2)
        
        return None
        
    except Exception as e:
        logger.error(f"Error calculating course score: {e}")
        return None

def _validate_time_data(user):
    """
    Validate and fix time data for a user
    """
    try:
        # Check for data inconsistencies
        invalid_time_records = TopicProgress.objects.filter(
            user=user,
            total_time_spent__lt=0
        )
        
        if invalid_time_records.exists():
            logger.warning(f"Found {invalid_time_records.count()} records with negative time for user {user.id}")
            invalid_time_records.update(total_time_spent=0)
        
        # Check for accessed records with zero time
        zero_time_accessed = TopicProgress.objects.filter(
            user=user,
            total_time_spent=0,
            last_accessed__isnull=False
        ).exclude(last_accessed=F('first_accessed'))
        
        if zero_time_accessed.exists():
            logger.warning(f"Found {zero_time_accessed.count()} accessed records with zero time for user {user.id}")
            # Set minimum time for accessed records
            zero_time_accessed.update(total_time_spent=60)
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating time data for user {user.id}: {e}")
        return False

def _validate_score_data(user):
    """
    Validate and fix score data for a user
    """
    try:
        # Check for invalid scores
        invalid_scores = TopicProgress.objects.filter(
            user=user,
            last_score__isnull=False
        ).exclude(last_score__gte=0).exclude(last_score__lte=100)
        
        if invalid_scores.exists():
            logger.warning(f"Found {invalid_scores.count()} records with invalid scores for user {user.id}")
            for record in invalid_scores:
                normalized_score = ScoreCalculationService.normalize_score(record.last_score)
                if normalized_score is not None:
                    record.last_score = normalized_score
                    record.save()
        
        # Check for completed records with null scores
        completed_null_scores = TopicProgress.objects.filter(
            user=user,
            completed=True,
            last_score__isnull=True
        )
        
        if completed_null_scores.exists():
            logger.warning(f"Found {completed_null_scores.count()} completed records with null scores for user {user.id}")
            completed_null_scores.update(last_score=0.00)
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating score data for user {user.id}: {e}")
        return False
