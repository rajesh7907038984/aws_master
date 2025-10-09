from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Grade
from django.db.models import Q, Max, Count, Case, When, IntegerField, OuterRef, Subquery
from assignments.models import Assignment, AssignmentSubmission, AssignmentFeedback
from assignments.forms import AssignmentGradingForm
from django.contrib.auth import get_user_model
from courses.models import Course, CourseEnrollment, Topic
from quiz.models import Quiz, QuizAttempt, QuizRubricEvaluation
from discussions.models import Discussion
from conferences.models import Conference, ConferenceRubricEvaluation
# SCORM imports for new implementation
from scorm.models import ScormAttempt
from django.shortcuts import get_object_or_404
from django.utils import timezone
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from lms_rubrics.models import RubricCriterion, RubricEvaluation, RubricOverallFeedback
from lms_rubrics.forms import RubricOverallFeedbackForm
from core.rbac_validators import ConditionalAccessValidator
from core.utils.type_guards import safe_get_string, safe_get_int
from .validators import validate_gradebook_request_data, GradebookValidationError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
import json
import logging
import hashlib
from django.db.models import Max, OuterRef, Subquery, Sum, Case, When, F, Q
from django.db.models.functions import Coalesce
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

def has_scorm_progress(attempt):
    """
    Check if a SCORM attempt represents actual progress (not just an initial attempt)
    """
    if not attempt:
        return False
    
    # Consider it progress if any of these conditions are met:
    # 1. Has been accessed (last_accessed is set) - this indicates user actually opened the content
    # 2. Has spent some time (more than 0 seconds) - this indicates user interaction
    # 3. Lesson status is completed or passed - this indicates actual completion
    # 4. Has a score AND last_accessed (score without access suggests programmatic assignment)
    
    # First check: User actually accessed the content
    if attempt.last_accessed:
        return True
    
    # Second check: User spent time on the content
    if attempt.total_time and attempt.total_time != '0000:00:00.00':
        return True
    
    # Third check: Content is completed or passed (regardless of access time)
    if attempt.lesson_status in ['completed', 'passed']:
        return True
        
    # Fourth check: Has a score AND was accessed (prevents false positives from programmatic scores)
    if attempt.score_raw and attempt.score_raw > 0 and attempt.last_accessed:
        return True
    
    # Check if there's meaningful progress data that indicates actual user interaction
    if attempt.cmi_data and isinstance(attempt.cmi_data, dict):
        # Look for meaningful progress indicators that suggest user interaction
        if attempt.cmi_data.get('progress', 0) > 0:
            return True
        if attempt.cmi_data.get('completion_percent', 0) > 0:
            return True
        # Only consider scorm_sync if there's also evidence of user interaction
        if (attempt.cmi_data.get('scorm_sync', False) and 
            (attempt.last_accessed or attempt.total_time != '0000:00:00.00')):
            return True
    
    return False

def pre_calculate_student_scores(students, activities, grades, quiz_attempts, scorm_attempts, conference_evaluations, initial_assessment_attempts=None):
    """
    Pre-calculate all student scores for activities to reduce template computation.
    Returns a dictionary structure: {student_id: {activity_id: score_data}}
    """
    # Initialize score data structure
    score_data = {}
    
    try:
        # Create lookups for efficient data retrieval
        grade_lookup = {}
        for grade in grades:
            key = (grade.student_id, grade.assignment_id)
            grade_lookup[key] = grade
        
        quiz_attempt_lookup = {}
        for attempt in quiz_attempts:
            key = (attempt.user_id, attempt.quiz_id)
            # Keep only the latest attempt for each student-quiz pair
            if key not in quiz_attempt_lookup or attempt.end_time > quiz_attempt_lookup[key].end_time:
                quiz_attempt_lookup[key] = attempt
        
        # Add initial assessment attempts to the same lookup
        if initial_assessment_attempts:
            for attempt in initial_assessment_attempts:
                key = (attempt.user_id, attempt.quiz_id)
                # Keep only the latest attempt for each student-quiz pair
                if key not in quiz_attempt_lookup or attempt.end_time > quiz_attempt_lookup[key].end_time:
                    quiz_attempt_lookup[key] = attempt
        
        scorm_lookup = {}
        if scorm_attempts:
            for attempt in scorm_attempts:
                key = (attempt.user_id, attempt.scorm_package_id)
                # Keep only the latest attempt for each student-scorm pair
                if key not in scorm_lookup:
                    scorm_lookup[key] = attempt
                elif attempt.last_accessed and scorm_lookup[key].last_accessed:
                    # Both have last_accessed, compare them
                    if attempt.last_accessed > scorm_lookup[key].last_accessed:
                        scorm_lookup[key] = attempt
                elif attempt.last_accessed and not scorm_lookup[key].last_accessed:
                    # New attempt has last_accessed but stored one doesn't, prefer the one with data
                    scorm_lookup[key] = attempt
                # If neither has last_accessed, keep the first one encountered (most recent by query order)
        
        conference_lookup = {}
        for evaluation in conference_evaluations:
            key = (evaluation.attendance.user_id, evaluation.conference_id)
            if key not in conference_lookup:
                conference_lookup[key] = []
            conference_lookup[key].append(evaluation)
        
        # Calculate scores for each student-activity pair
        for student in students:
            try:
                student_scores = {}
                
                for activity in activities:
                    try:
                        activity_id = activity['object'].id
                        activity_type = activity['type']
                        
                        if activity_type == 'assignment':
                            key = (student.id, activity_id)
                            if key in grade_lookup:
                                grade = grade_lookup[key]
                                if grade.excused:
                                    student_scores[activity_id] = {
                                        'score': None,
                                        'max_score': activity['max_score'],
                                        'excused': True,
                                        'date': grade.updated_at,
                                        'type': 'assignment',
                                        'submission': grade.submission
                                    }
                                else:
                                    # Check if submission is late
                                    is_late = False
                                    if grade.submission and activity['object'].due_date and grade.submission.submitted_at:
                                        is_late = grade.submission.submitted_at > activity['object'].due_date
                                    
                                    student_scores[activity_id] = {
                                        'score': grade.score,
                                        'max_score': activity['max_score'],
                                        'date': grade.updated_at,
                                        'type': 'assignment',
                                        'submission': grade.submission,
                                        'is_late': is_late
                                    }
                            else:
                                # Check for submission without grade
                                try:
                                    from assignments.models import AssignmentSubmission
                                    submission = AssignmentSubmission.objects.filter(
                                        assignment=activity['object'],
                                        user_id=student.id
                                    ).first()
                                    
                                    if submission:
                                        is_late = False
                                        if activity['object'].due_date and submission.submitted_at:
                                            is_late = submission.submitted_at > activity['object'].due_date
                                        
                                        # BUGFIX: Check if submission has been graded
                                        # If submission.grade is None but submission exists with status submitted/not_graded,
                                        # we should still show that there's a submission (not "Not Submitted")
                                        student_scores[activity_id] = {
                                            'score': submission.grade,  # Can be None if not graded yet
                                            'max_score': activity['max_score'],
                                            'date': submission.submitted_at,
                                            'type': 'assignment',
                                            'submission': submission,  # This is key - always include submission object
                                            'is_late': is_late,
                                            'has_submission': True  # Explicit flag to indicate submission exists
                                        }
                                    else:
                                        student_scores[activity_id] = {
                                            'score': None,
                                            'max_score': activity['max_score'],
                                            'type': 'assignment',
                                            'has_submission': False  # Explicit flag - no submission
                                        }
                                except Exception as e:
                                    logger.error(f"Error processing assignment submission for student {student.id}, activity {activity_id}: {str(e)}")
                                    student_scores[activity_id] = {
                                        'score': None,
                                        'max_score': activity['max_score'],
                                        'type': 'assignment',
                                        'has_submission': False
                                    }
                        
                        elif activity_type == 'quiz':
                            key = (student.id, activity_id)
                            if key in quiz_attempt_lookup:
                                attempt = quiz_attempt_lookup[key]
                                final_score = attempt.score
                                max_score = activity['max_score']
                                
                                # Check for rubric evaluation
                                quiz = activity['object']
                                if quiz.rubric:
                                    try:
                                        from quiz.models import QuizRubricEvaluation
                                        rubric_evaluations = QuizRubricEvaluation.objects.filter(
                                            quiz_attempt=attempt
                                        )
                                        if rubric_evaluations.exists():
                                            final_score = sum(evaluation.points for evaluation in rubric_evaluations)
                                            max_score = quiz.rubric.total_points
                                    except Exception as e:
                                        logger.error(f"Error processing quiz rubric evaluation for student {student.id}, quiz {activity_id}: {str(e)}")
                                        pass
                                else:
                                    # For non-rubric quizzes, attempt.score is a percentage (0-100)
                                    # Keep as percentage for consistent display
                                    final_score = attempt.score
                                    max_score = 100
                                
                                student_scores[activity_id] = {
                                    'score': final_score,
                                    'max_score': max_score,
                                    'date': attempt.end_time or attempt.start_time,
                                    'type': 'quiz',
                                    'attempt': attempt
                                }
                            else:
                                student_scores[activity_id] = {
                                    'score': None,
                                    'max_score': activity['max_score'],
                                    'type': 'quiz',
                                    'attempt': None
                                }
                        
                        elif activity_type == 'initial_assessment':
                            key = (student.id, activity_id)
                            if key in quiz_attempt_lookup:
                                attempt = quiz_attempt_lookup[key]
                                # For initial assessments, we show classification rather than just score
                                assessment_data = attempt.calculate_assessment_classification()
                                
                                # For initial assessments, keep as percentage for consistent display
                                quiz = activity['object']
                                final_score = attempt.score
                                max_score = 100
                                
                                student_scores[activity_id] = {
                                    'score': final_score,
                                    'max_score': max_score,
                                    'date': attempt.end_time or attempt.start_time,
                                    'type': 'initial_assessment',
                                    'attempt': attempt,
                                    'classification': assessment_data.get('classification', 'N/A') if assessment_data else 'N/A',
                                    'classification_data': assessment_data,
                                    'is_informational': True
                                }
                            else:
                                student_scores[activity_id] = {
                                    'score': None,
                                    'max_score': activity['max_score'],
                                    'type': 'initial_assessment',
                                    'is_informational': True,
                                    'attempt': None
                                }
                        
                        elif activity_type == 'discussion':
                            discussion = activity['object']
                            max_score = discussion.rubric.total_points if discussion.rubric else 0
                            
                            # Check for rubric evaluations
                            if discussion.rubric:
                                try:
                                    from lms_rubrics.models import RubricEvaluation
                                    evaluations = RubricEvaluation.objects.filter(
                                        discussion=discussion,
                                        student_id=student.id
                                    )
                                    if evaluations.exists():
                                        total_score = sum(evaluation.points for evaluation in evaluations)
                                        latest_evaluation = evaluations.order_by('-created_at').first()
                                        
                                        student_scores[activity_id] = {
                                            'score': total_score,
                                            'max_score': max_score,
                                            'date': latest_evaluation.created_at,
                                            'type': 'discussion',
                                            'evaluations': evaluations
                                        }
                                    else:
                                        student_scores[activity_id] = {
                                            'score': None,
                                            'max_score': max_score,
                                            'type': 'discussion'
                                        }
                                except Exception as e:
                                    logger.error(f"Error processing discussion rubric evaluation for student {student.id}, discussion {activity_id}: {str(e)}")
                                    student_scores[activity_id] = {
                                        'score': None,
                                        'max_score': max_score,
                                        'type': 'discussion'
                                    }
                            else:
                                student_scores[activity_id] = {
                                    'score': None,
                                    'max_score': max_score,
                                    'type': 'discussion'
                                }
                        
                        elif activity_type == 'conference':
                            key = (student.id, activity_id)
                            conference = activity['object']
                            max_score = conference.rubric.total_points if conference.rubric else 0
                            
                            if key in conference_lookup:
                                evaluations = conference_lookup[key]
                                total_score = sum(evaluation.points for evaluation in evaluations)
                                latest_evaluation = max(evaluations, key=lambda e: e.created_at)
                                
                                student_scores[activity_id] = {
                                    'score': total_score,
                                    'max_score': max_score,
                                    'date': latest_evaluation.created_at,
                                    'type': 'conference',
                                    'evaluations': evaluations
                                }
                            else:
                                student_scores[activity_id] = {
                                    'score': None,
                                    'max_score': max_score,
                                    'type': 'conference'
                                }
                        
                        elif activity_type == 'scorm':
                            key = (student.id, activity_id)
                            if key in scorm_lookup:
                                attempt = scorm_lookup[key]
                                
                                # Check if attempt has meaningful data (including TOC navigation data)
                                has_attempt_data = (
                                    attempt.score_raw is not None or 
                                    attempt.lesson_status in ['completed', 'passed'] or
                                    attempt.last_accessed is not None or
                                    attempt.total_time != '0000:00:00.00' or
                                    attempt.lesson_location or  # TOC navigation bookmark
                                    attempt.suspend_data or    # TOC progress data
                                    (attempt.navigation_history and len(attempt.navigation_history) > 0)  # Navigation history
                                )
                                
                                if has_attempt_data:
                                    # Get the highest score from TopicProgress (source of truth for gradebook)
                                    try:
                                        from courses.models import TopicProgress
                                        topic = activity['object'].topic if hasattr(activity['object'], 'topic') else None
                                        topic_progress = TopicProgress.objects.filter(
                                            topic=topic,
                                            user=student
                                        ).first() if topic else None
                                        
                                        # Use TopicProgress last_score (most recent/live score) to match SCORM results page
                                        score_value = None
                                        if topic_progress and topic_progress.last_score is not None:
                                            score_value = float(topic_progress.last_score)
                                        elif topic_progress and topic_progress.best_score is not None:
                                            score_value = float(topic_progress.best_score)
                                        elif attempt.score_raw is not None:
                                            score_value = float(attempt.score_raw)
                                        
                                        # Determine completion status based on score and lesson_status
                                        if score_value is not None:
                                            if score_value >= 70:  # Passing threshold
                                                completion_status = 'passed'
                                                success_status = 'passed'
                                            else:
                                                completion_status = 'failed'
                                                success_status = 'failed'
                                        elif attempt.lesson_status in ['completed', 'passed']:
                                            completion_status = 'completed'
                                            success_status = 'passed'
                                        else:
                                            completion_status = 'incomplete'
                                            success_status = 'unknown'
                                    except Exception as e:
                                        logger.error(f"Error getting TopicProgress for SCORM: {str(e)}")
                                        score_value = float(attempt.score_raw) if attempt.score_raw else None
                                        completion_status = attempt.lesson_status
                                        success_status = attempt.success_status
                                    
                                    student_scores[activity_id] = {
                                        'score': score_value,
                                        'max_score': attempt.score_max or 100,
                                        'date': attempt.last_accessed,
                                        'type': 'scorm',
                                        'attempt': attempt,
                                        'lesson_status': completion_status,
                                        'success_status': success_status,
                                        'completed': completion_status in ['completed', 'passed']
                                    }
                                else:
                                    # Registration exists but has no meaningful data
                                    # Check TopicProgress as fallback
                                    try:
                                        from courses.models import TopicProgress
                                        
                                        # Find the topic linked to this SCORM package
                                        # SCORM packages are directly linked to topics
                                        topic = activity['object'].topic if hasattr(activity['object'], 'topic') else None
                                        
                                        if topic:
                                            topic_progress = TopicProgress.objects.filter(
                                                topic=topic,
                                                user=student
                                            ).first()
                                            
                                            if topic_progress and (topic_progress.completed or topic_progress.best_score is not None or topic_progress.last_score is not None):
                                                # Use TopicProgress data
                                                completion_status = 'completed' if topic_progress.completed else 'incomplete'
                                                success_status = 'unknown'
                                                
                                                # Get score from last_score (most recent/live) to match SCORM results page
                                                score_value = None
                                                if topic_progress.last_score is not None:
                                                    score_value = float(topic_progress.last_score)
                                                elif topic_progress.best_score is not None:
                                                    score_value = float(topic_progress.best_score)
                                                else:
                                                    # Fallback: check progress_data for SCORM score
                                                    progress_data = topic_progress.progress_data or {}
                                                    score_raw = progress_data.get('score_raw')
                                                    if score_raw is not None:
                                                        try:
                                                            score_value = float(score_raw)
                                                        except (ValueError, TypeError):
                                                            pass
                                                
                                                if score_value is not None:
                                                    if score_value >= 70:
                                                        success_status = 'passed'
                                                    else:
                                                        success_status = 'failed'
                                                elif topic_progress.completed:
                                                    success_status = 'passed'
                                                
                                                student_scores[activity_id] = {
                                                    'score': score_value,
                                                    'max_score': 100,
                                                    'date': topic_progress.last_accessed,
                                                    'type': 'scorm',
                                                    'topic_progress': topic_progress,
                                                    'completion_status': completion_status,
                                                    'success_status': success_status,
                                                    'completed': topic_progress.completed
                                                }
                                            else:
                                                student_scores[activity_id] = {
                                                    'score': None,
                                                    'max_score': 100,
                                                    'type': 'scorm'
                                                }
                                        else:
                                            student_scores[activity_id] = {
                                                'score': None,
                                                'max_score': 100,
                                                'type': 'scorm'
                                            }
                                    except Exception as e:
                                        logger.error(f"Error checking TopicProgress for scorm {activity_id}, student {student.id}: {str(e)}")
                                        student_scores[activity_id] = {
                                            'score': None,
                                            'max_score': 100,
                                            'type': 'scorm'
                                        }
                            else:
                                # No registration found - check TopicProgress as fallback
                                try:
                                    from courses.models import TopicProgress
                                    
                                    # Find the topic linked to this SCORM package
                                    # SCORM packages are directly linked to topics
                                    topic = activity['object'].topic if hasattr(activity['object'], 'topic') else None
                                    
                                    if topic:
                                        topic_progress = TopicProgress.objects.filter(
                                            topic=topic,
                                            user=student
                                        ).first()
                                        
                                        if topic_progress and (topic_progress.completed or topic_progress.best_score is not None or topic_progress.last_score is not None):
                                            # Use TopicProgress data
                                            completion_status = 'completed' if topic_progress.completed else 'incomplete'
                                            success_status = 'unknown'
                                            
                                            # Use last_score (most recent/live) to match SCORM results page
                                            score_value = topic_progress.last_score if topic_progress.last_score is not None else topic_progress.best_score
                                            
                                            if score_value is not None:
                                                if float(score_value) >= 70:
                                                    success_status = 'passed'
                                                else:
                                                    success_status = 'failed'
                                            elif topic_progress.completed:
                                                success_status = 'passed'
                                            
                                            student_scores[activity_id] = {
                                                'score': float(score_value) if score_value else None,
                                                'max_score': 100,
                                                'date': topic_progress.last_accessed,
                                                'type': 'scorm',
                                                'topic_progress': topic_progress,
                                                'completion_status': completion_status,
                                                'success_status': success_status,
                                                'completed': topic_progress.completed
                                            }
                                        else:
                                            student_scores[activity_id] = {
                                                'score': None,
                                                'max_score': 100,
                                                'type': 'scorm'
                                            }
                                    else:
                                        student_scores[activity_id] = {
                                            'score': None,
                                            'max_score': 100,
                                            'type': 'scorm'
                                        }
                                except Exception as e:
                                    logger.error(f"Error checking TopicProgress for scorm {activity_id}, student {student.id}: {str(e)}")
                                    student_scores[activity_id] = {
                                        'score': None,
                                        'max_score': 100,
                                        'type': 'scorm'
                                    }
                        
                        elif activity_type == 'scorm_topic':
                            # Handle SCORM topics that track progress via TopicProgress model
                            try:
                                from courses.models import TopicProgress
                                
                                topic_progress = TopicProgress.objects.filter(
                                    topic=activity['object'],
                                    user=student
                                ).first()
                                
                                if topic_progress and (topic_progress.best_score is not None or topic_progress.last_score is not None or topic_progress.completed or topic_progress.attempts > 0 or topic_progress.last_accessed):
                                    # Calculate completion status
                                    completion_status = 'completed' if topic_progress.completed else 'incomplete'
                                    
                                    # Get score from last_score (most recent/live) to match SCORM results page
                                    score_value = None
                                    if topic_progress.last_score is not None:
                                        score_value = float(topic_progress.last_score)
                                    elif topic_progress.best_score is not None:
                                        score_value = float(topic_progress.best_score)
                                    else:
                                        # Fallback: check progress_data for SCORM score
                                        progress_data = topic_progress.progress_data or {}
                                        score_raw = progress_data.get('score_raw')
                                        if score_raw is not None:
                                            try:
                                                score_value = float(score_raw)
                                            except (ValueError, TypeError):
                                                pass
                                    
                                    # Determine success status based on score
                                    success_status = 'unknown'
                                    if score_value is not None:
                                        # Consider passed if score is 70% or higher (typical passing threshold)
                                        if score_value >= 70:
                                            success_status = 'passed'
                                        else:
                                            success_status = 'failed'
                                    elif topic_progress.completed:
                                        success_status = 'passed'
                                    elif topic_progress.last_accessed and not topic_progress.completed and score_value is None:
                                        # Learner has accessed but not completed or scored - show as in progress
                                        success_status = 'in_progress'
                                    
                                    student_scores[activity_id] = {
                                        'score': score_value,
                                        'max_score': 100,  # SCORM scores are typically 0-100 scale
                                        'date': topic_progress.last_accessed,
                                        'type': 'scorm_topic',
                                        'topic_progress': topic_progress,
                                        'completion_status': completion_status,
                                        'success_status': success_status,
                                        'completed': topic_progress.completed
                                    }
                                else:
                                    student_scores[activity_id] = {
                                        'score': None,
                                        'max_score': 100,
                                        'type': 'scorm_topic'
                                    }
                            except Exception as e:
                                logger.error(f"Error fetching TopicProgress for scorm_topic {activity_id}, student {student.id}: {str(e)}")
                                student_scores[activity_id] = {
                                    'score': None,
                                    'max_score': 100,
                                    'type': 'scorm_topic'
                                }
                    
                    except Exception as e:
                        logger.error(f"Error processing activity {activity_id} for student {student.id}: {str(e)}")
                        # Add a fallback score entry
                        student_scores[activity_id] = {
                            'score': None,
                            'max_score': activity.get('max_score', 0),
                            'type': activity.get('type', 'unknown')
                        }
                
                score_data[student.id] = student_scores
            
            except Exception as e:
                logger.error(f"Error processing student {student.id}: {str(e)}")
                # Initialize empty score data for this student
                score_data[student.id] = {}
    
    except Exception as e:
        logger.error(f"Error in pre_calculate_student_scores: {str(e)}")
        # Return empty score data as fallback
        score_data = {}
    
    return score_data

def prepare_activity_display_data(activities, user_role):
    """
    Prepare activity data with pre-calculated display conditions for better template performance.
    """
    display_activities = []
    
    for activity in activities:
        activity_data = {
            'object': activity['object'],
            'type': activity['type'],
            'created_at': activity['created_at'],
            'title': activity['title'],
            'max_score': activity['max_score'],
            'activity_number': activity['activity_number'],
            'activity_name': activity['activity_name'],
            
            # Pre-calculate display conditions
            'is_active': getattr(activity['object'], 'is_active', True),
            'is_published': getattr(activity['object'], 'status', 'active') == 'published',
            'has_max_score': activity['max_score'] > 0,
            'show_grade_buttons': user_role != 'learner',
            'truncated_title': activity['title'][:15] + '...' if len(activity['title']) > 15 else activity['title'],
            
            # Activity type specific data
            'type_label': {
                'assignment': 'ASG',
                'quiz': 'QUZ',
                'discussion': 'DSC',
                'conference': 'CNF',
                'scorm': 'SCO',
                'scorm_topic': 'SCO'
            }.get(activity['type'], 'UNK'),
            
            'type_class': f"activity-type-{activity['type']}",
        }
        
        # Add specific conditions for each type
        if activity['type'] == 'quiz':
            activity_data['is_inactive'] = not getattr(activity['object'], 'is_active', True)
            activity_data['passing_score'] = getattr(activity['object'], 'passing_score', 70)
            
        elif activity['type'] == 'discussion':
            activity_data['is_participation'] = activity['max_score'] == 0
            
        elif activity['type'] == 'conference':
            activity_data['is_attendance'] = activity['max_score'] == 0
            
        display_activities.append(activity_data)
    
    return display_activities

def calculate_score_display_class(score, max_score):
    """
    Calculate the CSS class for score display based on percentage.
    """
    if not score or not max_score or max_score == 0:
        return 'grade-none'
    
    # Convert to float to handle decimal.Decimal and float type mixing with error handling
    try:
        percentage = round((float(score) / float(max_score)) * 100)
    except (ValueError, TypeError, ZeroDivisionError):
        return 'grade-none'
    
    if percentage >= 90:
        return 'grade-excellent'
    elif percentage >= 80:
        return 'grade-good'
    elif percentage >= 70:
        return 'grade-average'
    else:
        return 'grade-poor'

def enhance_student_scores_with_display_data(student_scores, activities):
    """
    Enhance student scores with pre-calculated display data.
    """
    enhanced_scores = {}
    
    for student_id, scores in student_scores.items():
        enhanced_student_scores = {}
        
        for activity_id, score_data in scores.items():
            enhanced_score = score_data.copy()
            
            # Add display class
            enhanced_score['display_class'] = calculate_score_display_class(
                score_data.get('score'), 
                score_data.get('max_score')
            )
            
            # Add formatted score display
            if score_data.get('score') is not None:
                enhanced_score['formatted_score'] = f"{score_data['score']:.1f}/{score_data['max_score']:.1f}"
            else:
                enhanced_score['formatted_score'] = "Not graded"
            
            # Add date formatting
            if score_data.get('date'):
                enhanced_score['formatted_date'] = score_data['date'].strftime('%b %d, %Y')
            
            enhanced_student_scores[activity_id] = enhanced_score
        
        enhanced_scores[student_id] = enhanced_student_scores
    
    return enhanced_scores

# Create your views here.
@login_required
def gradebook_index(request):
    """
    Display the gradebook with activity-wise filtering.
    Show activities from all courses grouped by type, with filters for each activity type.
    """
    user = request.user
    User = get_user_model()
    
    # Get filters and search from request
    activity_filter = request.GET.get('activity_type', 'all')
    course_filter = request.GET.get('course', 'all')
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '').strip()
    
    # Get courses based on user role with proper branch filtering
    if user.role == 'learner':
        # Show student's enrolled courses
        enrolled_courses_ids = CourseEnrollment.objects.filter(
            user=user,
            course__is_active=True  # Only active courses
        ).values_list('course_id', flat=True)
        
        all_courses = Course.objects.filter(id__in=enrolled_courses_ids).order_by('title')
        
    elif user.role == 'instructor':
        # Show courses where user is the instructor or enrolled - filtered by branch
        instructor_courses = Course.objects.filter(
            instructor=user, 
            is_active=True,
            branch=user.branch  # Ensure branch filtering
        )
        enrolled_courses_ids = CourseEnrollment.objects.filter(
            user=user,
            course__is_active=True,
            course__branch=user.branch  # Ensure branch filtering
        ).values_list('course_id', flat=True)
        enrolled_courses = Course.objects.filter(
            id__in=enrolled_courses_ids, 
            is_active=True,
            branch=user.branch  # Ensure branch filtering
        )
        
        # Combine and remove duplicates
        all_courses = (instructor_courses | enrolled_courses).distinct().order_by('title')
        
    elif user.role == 'admin':
        # Branch admin can only see courses from their effective branch (supports branch switching)
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(user, request)
        if effective_branch:
            all_courses = Course.objects.filter(
                is_active=True,
                branch=effective_branch
            ).order_by('title')
        else:
            all_courses = Course.objects.none()
        
    elif user.role == 'globaladmin' or user.is_superuser:
        # Global Admin: Show all active courses
        all_courses = Course.objects.filter(is_active=True).order_by('title')
    elif user.role == 'superadmin':
        # Super Admin: Show courses within their assigned businesses only
        from core.utils.business_filtering import filter_courses_by_business
        all_courses = filter_courses_by_business(user).filter(is_active=True).order_by('title')
        
    else:
        all_courses = Course.objects.none()

    # Apply course filter if specified
    if course_filter != 'all':
        try:
            selected_course_id = int(course_filter)
            courses = all_courses.filter(id=selected_course_id)
        except (ValueError, TypeError):
            courses = all_courses
    else:
        courses = all_courses
    
    # Get all activities from the accessible courses, organized by type
    activities_data = []
    
    if courses.exists():
        # Get assignments with course associations only - optimized with select_related
        assignments = Assignment.objects.filter(
            Q(course__in=courses) |  # Direct course relationship
            Q(courses__in=courses) |  # M2M course relationship
            Q(topics__courses__in=courses)  # Topic-based course relationship
        ).filter(
            is_active=True  # Only active assignments
        ).filter(
            # Either have active topics OR have no topics at all (direct course assignments)
            Q(topics__status='active') |  # Has active topics
            Q(topics__isnull=True)  # Has no topics (direct course assignment)
        ).distinct().select_related('course').prefetch_related(
            'courses', 
            'topics__courses',
            'attachments'
        ).order_by('created_at')

        # Get regular quizzes (exclude initial assessments and VAK tests from grading) - optimized
        quizzes = Quiz.objects.filter(
            Q(course__in=courses) |  # Direct course relationship
            Q(topics__courses__in=courses)  # Topic-based course relationship
        ).filter(
            is_active=True  # Only active quizzes
        ).filter(
            # Either have active topics OR have no topics at all
            Q(topics__status='active') |
            Q(topics__isnull=True)
        ).exclude(
            # Exclude only VAK tests from gradebook grading (include initial assessments)
            Q(is_vak_test=True)
        ).distinct().select_related('course', 'rubric').prefetch_related(
            'topics__courses',
            'questions'
        ).order_by('created_at')

        # Initial assessments are now included in the main quizzes query above

        # Get discussions with course associations only
        discussions = Discussion.objects.filter(
            Q(course__in=courses) |  # Direct course relationship
            Q(topics__courses__in=courses)  # Topic-based course relationship
        ).filter(
            status='published'  # Only published discussions
        ).filter(
            # Either have active topics OR have no topics at all
            Q(topics__status='active') |
            Q(topics__isnull=True)
        ).distinct().prefetch_related('course', 'topics__courses').order_by('created_at')

        # Get conferences with course associations only
        conferences = Conference.objects.filter(
            Q(course__in=courses) |  # Direct course relationship
            Q(topics__courses__in=courses)  # Topic-based course relationship
        ).filter(
            status='published'  # Only published conferences
        ).filter(
            # Either have active topics OR have no topics at all
            Q(topics__status='active') |
            Q(topics__isnull=True)
        ).distinct().prefetch_related('course', 'topics__courses').order_by('created_at')

        # Get SCORM topics with course associations
        scorm_topics = []
        try:
            # Get SCORM topics from accessible courses
            scorm_topics = Topic.objects.filter(
                content_type='SCORM',
                status='active',  # Only active SCORM topics
                coursetopic__course__in=courses  # Through CourseTopic relationship
            ).distinct().prefetch_related(
                'coursetopic_set__course'  # Prefetch course relationships
            ).order_by('created_at')
        except Exception as e:
            logger.error(f"Error filtering SCORM topics: {str(e)}")
            scorm_topics = []

        # Helper function to get course info for activities
        def get_activity_course_info(activity, activity_type):
            course_info = None
            if activity_type == 'assignment':
                if hasattr(activity, 'course') and activity.course:
                    course_info = activity.course
                elif hasattr(activity, 'courses') and activity.courses.exists():
                    course_info = activity.courses.first()
                elif hasattr(activity, 'topics') and activity.topics.exists():
                    topic = activity.topics.first()
                    if hasattr(topic, 'courses') and topic.courses.exists():
                        course_info = topic.courses.first()
            elif activity_type in ['quiz', 'discussion', 'conference']:
                if hasattr(activity, 'course') and activity.course:
                    course_info = activity.course
                elif hasattr(activity, 'topics') and activity.topics.exists():
                    topic = activity.topics.first()
                    if hasattr(topic, 'courses') and topic.courses.exists():
                        course_info = topic.courses.first()
            elif activity_type == 'scorm_topic':
                # For SCORM topics, get course through CourseTopic relationship
                if hasattr(activity, 'coursetopic_set'):
                    course_topic = activity.coursetopic_set.first()
                    if course_topic:
                        course_info = course_topic.course
            return course_info

        # Process activities based on filter
        if activity_filter == 'all' or activity_filter == 'assignment':
            for assignment in assignments:
                course_info = get_activity_course_info(assignment, 'assignment')
                if course_info:  # Only include if has course association
                    # Use rubric total_points if assignment has rubric, otherwise use assignment max_score
                    max_score = assignment.rubric.total_points if assignment.rubric else assignment.max_score
                    activities_data.append({
                        'object': assignment,
                        'type': 'assignment',
                        'title': assignment.title,
                        'course': course_info,
                        'created_at': assignment.created_at,
                        'max_score': max_score,
                    })

        if activity_filter == 'all' or activity_filter == 'quiz' or activity_filter == 'initial_assessment':
            for quiz in quizzes:
                course_info = get_activity_course_info(quiz, 'quiz')
                if course_info:  # Only include if has course association
                    # Use rubric total_points if quiz has rubric, otherwise use quiz total_points
                    max_score = quiz.rubric.total_points if quiz.rubric else (quiz.total_points or 0)
                    
                    # Determine activity type and include based on filter
                    if quiz.is_initial_assessment:
                        if activity_filter == 'all' or activity_filter == 'initial_assessment':
                            activities_data.append({
                                'object': quiz,
                                'type': 'initial_assessment',
                                'title': quiz.title,
                                'course': course_info,
                                'created_at': quiz.created_at,
                                'max_score': max_score,
                            })
                    else:
                        if activity_filter == 'all' or activity_filter == 'quiz':
                            activities_data.append({
                                'object': quiz,
                                'type': 'quiz',
                                'title': quiz.title,
                                'course': course_info,
                                'created_at': quiz.created_at,
                                'max_score': max_score,
                            })

        if activity_filter == 'all' or activity_filter == 'discussion':
            for discussion in discussions:
                course_info = get_activity_course_info(discussion, 'discussion')
                if course_info and discussion.rubric:  # Only include if has course association AND rubric
                    # Use rubric total_points if discussion has rubric
                    max_score = discussion.rubric.total_points
                    activities_data.append({
                        'object': discussion,
                        'type': 'discussion',
                        'title': discussion.title,
                        'course': course_info,
                        'created_at': discussion.created_at,
                        'max_score': max_score,
                    })

        if activity_filter == 'all' or activity_filter == 'conference':
            for conference in conferences:
                course_info = get_activity_course_info(conference, 'conference')
                if course_info and hasattr(conference, 'rubric') and conference.rubric:  # Only include if has course association AND rubric
                    max_score = conference.rubric.total_points
                    activities_data.append({
                        'object': conference,
                        'type': 'conference',
                        'title': conference.title,
                        'course': course_info,
                        'created_at': conference.created_at,
                        'max_score': max_score,
                    })

        if activity_filter == 'all' or activity_filter == 'scorm':
            for scorm_topic in scorm_topics:
                course_info = get_activity_course_info(scorm_topic, 'scorm_topic')
                if course_info:  # Only include if has course association
                    activities_data.append({
                        'object': scorm_topic,
                        'type': 'scorm_topic',
                        'title': scorm_topic.title,
                        'course': course_info,
                        'created_at': scorm_topic.created_at if hasattr(scorm_topic, 'created_at') else timezone.now(),
                        'max_score': 100,
                    })

    # Apply search filter if provided
    if search_query:
        filtered_activities = []
        search_lower = search_query.lower()
        for activity in activities_data:
            # Search in activity title and course title
            if (search_lower in activity['title'].lower() or 
                search_lower in activity['course'].title.lower()):
                filtered_activities.append(activity)
        activities_data = filtered_activities

    # Apply status filter if provided
    if status_filter != 'all':
        def calculate_activity_status(activity, user_id):
            """Helper function to calculate activity status"""
            try:
                from assignments.models import AssignmentSubmission
                from quiz.models import QuizAttempt
                from discussions.models import Comment
                from conferences.models import ConferenceAttendance
                from courses.models import TopicProgress
                
                user_id = int(user_id)
                activity_type = activity.get('type')
                activity_obj = activity.get('object')
                
                if activity_type == 'assignment':
                    submission = AssignmentSubmission.objects.filter(
                        assignment=activity_obj,
                        user_id=user_id
                    ).first()
                    
                    if submission:
                        # Check actual submission status from database
                        if submission.status == 'returned':
                            return "Returned"
                        elif submission.status == 'missing':
                            return "Missing"
                        elif submission.grade is not None:
                            return "Graded"
                        elif submission.status in ['submitted', 'not_graded']:
                            # Both 'submitted' and 'not_graded' represent submitted work
                            return "Submitted"
                        else:
                            return "Submitted"
                    else:
                        return "Not Started"
                        
                elif activity_type == 'quiz':
                    attempt = QuizAttempt.objects.filter(
                        quiz=activity_obj,
                        user_id=user_id
                    ).order_by('-start_time').first()  # Get most recent attempt
                    
                    if attempt:
                        if attempt.is_completed and attempt.end_time:
                            return "Completed"
                        elif attempt.start_time and not attempt.end_time:
                            return "In Progress"
                        else:
                            return "Completed"  # Fallback for completed attempts
                    else:
                        return "Not Started"
                        
                elif activity_type == 'initial_assessment':
                    attempt = QuizAttempt.objects.filter(
                        quiz=activity_obj,
                        user_id=user_id,
                        is_completed=True
                    ).order_by('-end_time').first()  # Get most recent completed attempt
                    
                    if attempt:
                        return "Completed"
                    else:
                        return "Not Started"
                        
                elif activity_type == 'discussion':
                    # Check for discussion comments/participation
                    comment = Comment.objects.filter(
                        discussion=activity_obj,
                        created_by_id=user_id
                    ).first()
                    
                    if comment:
                        return "Participated"
                    else:
                        return "Not Started"
                        
                elif activity_type == 'conference':
                    try:
                        attendance = ConferenceAttendance.objects.filter(
                            conference=activity_obj,
                            user_id=user_id
                        ).first()
                        
                        if attendance:
                            # Check attendance status from database
                            if attendance.attendance_status == 'present':
                                return "Attended"
                            elif attendance.attendance_status == 'absent':
                                return "Absent"
                            else:
                                return "Registered"
                        else:
                            return "Not Started"
                    except Exception as e:
                        logger.error(f"Error checking conference attendance: {str(e)}")
                        return "Not Started"
                        
                elif activity_type == 'scorm_topic':
                    progress = TopicProgress.objects.filter(
                        topic=activity_obj,
                        user_id=user_id
                    ).first()
                    
                    if progress:
                        if progress.completed:
                            return "Completed"
                        elif progress.last_score is not None:
                            # Check if passed or failed based on score
                            if float(progress.last_score) >= 70:
                                return "Completed"
                            else:
                                return "Failed"
                        elif (progress.attempts > 0 or progress.last_accessed) and not progress.completed:
                            # Learner has attempted/accessed but not completed - consider as failed
                            return "Failed"
                        else:
                            return "Not Started"
                    else:
                        return "Not Started"
                
                return "Not Started"
                
            except Exception as e:
                logger.error(f"Error calculating activity status: {str(e)}")
                return "Not Started"
        
        filtered_activities = []
        for activity in activities_data:
            # Calculate activity status for current user
            activity_status = calculate_activity_status(activity, user.id)
            
            # Normalize status for comparison
            normalized_activity_status = activity_status.lower().replace(' ', '-')
            
            if normalized_activity_status == status_filter:
                filtered_activities.append(activity)
        activities_data = filtered_activities

    # Group activities by course for better organization
    activities_by_course = {}
    for activity in activities_data:
        course = activity['course']
        course_key = f"{course.id}_{course.title}"
        if course_key not in activities_by_course:
            activities_by_course[course_key] = {
                'course': course,
                'activities': []
            }
        activities_by_course[course_key]['activities'].append(activity)
    
    # Sort activities within each course by creation date
    for course_group in activities_by_course.values():
        course_group['activities'].sort(key=lambda x: x['created_at'], reverse=True)
    
    # Sort courses alphabetically
    grouped_activities = sorted(activities_by_course.values(), key=lambda x: x['course'].title)

    # Activity type choices for filter dropdown
    activity_types = [
        ('all', 'All Activities'),
        ('assignment', 'Assignments'),
        ('quiz', 'Quizzes'),
        ('initial_assessment', 'Initial Assessments'),
        ('discussion', 'Discussions'),
        ('conference', 'Conferences'),
        ('scorm', 'SCORM Content'),
    ]
    
    # Course choices for filter dropdown
    course_choices = [('all', 'All Courses')]
    for course in all_courses:
        course_choices.append((str(course.id), course.title))
    
    # Status choices for filter dropdown
    status_choices = [
        ('all', 'All Statuses'),
        ('not-started', 'Not Started'),
        ('in-progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('graded', 'Graded'),
        ('returned', 'Returned'),
        ('missing', 'Missing'),
        ('participated', 'Participated'),
        ('attended', 'Attended'),
        ('absent', 'Absent'),
        ('registered', 'Registered'),
    ]
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Gradebook', 'icon': 'fa-graduation-cap'}
    ]
    
    context = {
        'activities': activities_data,  # Keep original for count
        'grouped_activities': grouped_activities,  # New grouped format
        'activity_types': activity_types,
        'course_choices': course_choices,
        'status_choices': status_choices,
        'current_filter': activity_filter,
        'current_course_filter': course_filter,
        'current_status_filter': status_filter,
        'search_query': search_query,
        'courses': courses,
        'all_courses': all_courses,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'gradebook/index.html', context)

@login_required
def course_gradebook_detail(request, course_id):
    """
    Display detailed gradebook for a specific course in table format.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    user = request.user
    User = get_user_model()
    
    try:
        # Get the specific course
        course = get_object_or_404(Course, id=course_id)
        
        # Check permissions
        if user.role == 'instructor':
            # Instructors can access if they are assigned to the course OR enrolled in the course OR have group access
            has_permission = (
                course.instructor == user or
                CourseEnrollment.objects.filter(course=course, user=user).exists() or
                # Check for group-based access
                course.accessible_groups.filter(
                    memberships__user=user,
                    memberships__is_active=True,
                    memberships__custom_role__name__icontains='instructor'
                ).exists()
            )
            if not has_permission:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("You don't have permission to view this gradebook.")
        elif user.role == 'learner':
            # Learners can only see their own grades in courses they're enrolled in
            if not CourseEnrollment.objects.filter(course=course, user=user).exists():
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("You are not enrolled in this course.")
        elif user.role not in ['admin', 'superadmin', 'globaladmin']:
            # Other roles don't have permission
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("You don't have permission to view this gradebook.")
        
        # Get students for this course with proper optimization
        if user.role == 'learner':
            students = User.objects.filter(id=user.id).select_related('branch')
        else:
            students = User.objects.filter(
                Q(enrolled_courses__id=course_id) & Q(role='learner')
            ).distinct().select_related('branch').prefetch_related('enrolled_courses')
        
        # Add pagination for better performance with large student lists
        page_size = 50  # Configurable page size
        page = request.GET.get('page', 1)
        
        # Get total count before pagination
        total_students = students.count()
        
        # Apply pagination
        paginator = Paginator(students, page_size)
        try:
            students_page = paginator.page(page)
        except PageNotAnInteger:
            students_page = paginator.page(1)
        except EmptyPage:
            students_page = paginator.page(paginator.num_pages)
        
        # Use paginated students for the rest of the view
        students = students_page.object_list
        
    except Exception as e:
        logger.error(f"Error in course_gradebook_detail: {str(e)}")
        from django.contrib import messages
        messages.error(request, "An error occurred while loading the gradebook. Please try again.")
        return redirect('gradebook:index')
    
    # Get all activities for this course grouped by type
    # Include activities linked through direct course, M2M courses, and topic relationships
    # Also filter for active/published status where applicable
    
    try:
        # Assignments: Check direct course, M2M courses, and topic-based relationships
        assignments = Assignment.objects.filter(
            Q(course=course) |  # Direct course relationship
            Q(courses=course) |  # M2M course relationship
            Q(topics__courses=course)  # Topic-based course relationship
        ).filter(
            is_active=True  # Only active assignments
        ).filter(
            # Either have active topics OR have no topics at all (direct course assignments)
            Q(topics__status='active') |  # Has active topics
            Q(topics__isnull=True)  # Has no topics (direct course assignment)
        ).distinct().select_related('course', 'user', 'rubric').prefetch_related('courses', 'topics').order_by('created_at')
        
        # Quizzes: Check direct course and topic relationships (include initial assessments, exclude only VAK tests)
        quizzes = Quiz.objects.filter(
            Q(course=course) |  # Direct course relationship
            Q(topics__courses=course)  # Topic-based course relationship
        ).filter(
            is_active=True  # Only active quizzes
        ).filter(
            # Either have active topics OR have no topics at all
            Q(topics__status='active') |
            Q(topics__isnull=True)
        ).exclude(
            # Exclude only VAK tests from gradebook grading (include initial assessments)
            Q(is_vak_test=True)
        ).distinct().select_related('course', 'creator', 'rubric').prefetch_related('topics').order_by('created_at')

        # Initial assessments are now included in the main quizzes query above
        
        # Discussions: Check direct course and topic relationships
        discussions = Discussion.objects.filter(
            Q(course=course) |  # Direct course relationship
            Q(topics__courses=course)  # Topic-based course relationship
        ).filter(
            status='published'  # Only published discussions
        ).filter(
            # Either have active topics OR have no topics at all
            Q(topics__status='active') |
            Q(topics__isnull=True)
        ).distinct().select_related('course', 'created_by', 'rubric').prefetch_related('topics').order_by('created_at')
        
        # Conferences: Check direct course and topic relationships
        conferences = Conference.objects.filter(
            Q(course=course) |  # Direct course relationship
            Q(topics__courses=course)  # Topic-based course relationship
        ).filter(
            status='published'  # Only published conferences
        ).filter(
            # Either have active topics OR have no topics at all
            Q(topics__status='active') |
            Q(topics__isnull=True)
        ).distinct().select_related('course', 'created_by', 'rubric').prefetch_related('topics').order_by('created_at')
        
    except Exception as e:
        logger.error(f"Error fetching activities for course {course_id}: {str(e)}")
        # Initialize empty querysets as fallback
        assignments = Assignment.objects.none()
        quizzes = Quiz.objects.none()
        discussions = Discussion.objects.none()
        conferences = Conference.objects.none()
    
    # Get SCORM topics for this course
    scorm_packages = []
    scorm_topics_without_packages = []  # Keep track of topics without packages
    try:
        # Get topics that contain SCORM content for this course
        scorm_topics = Topic.objects.filter(
            coursetopic__course=course,
            content_type='SCORM',
            status='active'  # Only include active/published SCORM topics
        ).prefetch_related('coursetopic_set__course').order_by('created_at')
        
        for topic in scorm_topics:
            # Check if topic has a SCORM package
            try:
                if hasattr(topic, 'scorm_package') and topic.scorm_package:
                    scorm_packages.append(topic.scorm_package)
                else:
                    # Topic exists but has no package - still include it in activities
                    scorm_topics_without_packages.append(topic)
            except Exception as e:
                logger.error(f"Error processing SCORM topic {topic.id}: {str(e)}")
                # If there's an error, still include the topic
                scorm_topics_without_packages.append(topic)
    except Exception as e:
        logger.error(f"Error fetching SCORM content for course {course_id}: {str(e)}")
        # Continue without SCORM content
        pass
    
    # Calculate overview metrics
    students_count = total_students  # Use total count, not paginated count
    # Count only discussions and conferences that have rubrics
    discussions_with_rubrics = discussions.filter(rubric__isnull=False).count()
    conferences_with_rubrics = conferences.filter(rubric__isnull=False).count()
    total_activities = assignments.count() + quizzes.count() + discussions_with_rubrics + conferences_with_rubrics + len(scorm_packages) + len(scorm_topics_without_packages)
    
    # Calculate activity status counts
    # Get all submissions and attempts with optimized queries
    all_submissions = AssignmentSubmission.objects.filter(
        assignment__in=assignments,
        user__in=students
    ).select_related('assignment', 'user', 'graded_by').order_by('-submitted_at')
    
    # Get quiz attempts for this course (ordered by end time) with optimized queries
    # Only get the latest attempt per student-quiz pair
    
    # Get the latest attempt time for each student-quiz pair
    latest_attempts = QuizAttempt.objects.filter(
        quiz=OuterRef('quiz'),
        user=OuterRef('user'),
        is_completed=True
    ).order_by('-end_time')
    
    quiz_attempts = QuizAttempt.objects.filter(
        user__in=students,
        quiz__in=quizzes,
        is_completed=True,
        end_time__in=Subquery(latest_attempts.values('end_time')[:1])
    ).select_related('quiz', 'user', 'quiz__rubric').order_by('-end_time')

    # Initial assessment attempts are now included in the main quiz_attempts query above
    
    # SCORM attempts with optimized queries
    all_scorm_attempts = ScormAttempt.objects.filter(
        scorm_package__in=scorm_packages,
        user__in=students
    ).select_related('scorm_package', 'user').order_by('-last_accessed')
    
    # Calculate total possible activity instances (students × activities)
    total_possible_instances = students_count * total_activities
    
    # Count submitted activities - include 'not_graded' as it represents submitted work awaiting grading
    submitted_assignments = all_submissions.filter(status__in=['submitted', 'not_graded', 'graded', 'returned']).count()
    submitted_quizzes = quiz_attempts.count()  # This now includes initial assessment attempts
    # Only count completed SCORM activities as submitted
    submitted_scorm = all_scorm_attempts.filter(lesson_status='completed').count()
    
    # Count SCORM topics (tracked via TopicProgress) as submitted if completed
    submitted_scorm_topics = 0
    if scorm_topics_without_packages:
        from courses.models import TopicProgress
        for topic in scorm_topics_without_packages:
            submitted_scorm_topics += TopicProgress.objects.filter(
                topic=topic,
                user__in=students,
                completed=True
            ).count()
    
    total_submitted = submitted_assignments + submitted_quizzes + submitted_scorm + submitted_scorm_topics
    
    # Count in-progress activities (for more accurate metrics)
    # Only count SCORM attempts that have actual progress
    in_progress_scorm = 0
    for attempt in all_scorm_attempts:
        if attempt.lesson_status == 'incomplete':
            # Check if there's actual progress
            has_progress = has_scorm_progress(attempt)
            if has_progress:
                in_progress_scorm += 1
    
    # Count SCORM topics in progress (accessed but not completed)
    in_progress_scorm_topics = 0
    if scorm_topics_without_packages:
        from courses.models import TopicProgress
        for topic in scorm_topics_without_packages:
            # Count as in progress if accessed or has attempts but not completed
            in_progress_scorm_topics += TopicProgress.objects.filter(
                topic=topic,
                user__in=students,
                completed=False
            ).filter(
                Q(last_accessed__isnull=False) | Q(attempts__gt=0)
            ).count()
    
    # Adjust not started calculation to account for in-progress activities
    total_started = total_submitted + in_progress_scorm + in_progress_scorm_topics
    total_not_started = total_possible_instances - total_started
    
    # Ensure not started count is non-negative
    total_not_started = max(0, total_not_started)
    
    overview_metrics = {
        'students_count': students_count,
        'total_activities': total_activities,
        'total_not_started': total_not_started,
        'total_submitted': total_submitted,
        'total_in_progress': in_progress_scorm + in_progress_scorm_topics,
    }
    
    # Create organized activities list with type-specific numbering
    activities = []
    
    # Add assignments with numbering
    assignment_counter = 1
    for assignment in assignments:
        # Use rubric total_points if assignment has rubric, otherwise use assignment max_score
        max_score = assignment.rubric.total_points if assignment.rubric else assignment.max_score
        activities.append({
            'object': assignment,
            'type': 'assignment',
            'created_at': assignment.created_at,
            'title': assignment.title,
            'max_score': max_score,
            'activity_number': assignment_counter,
            'activity_name': f"Assignment {assignment_counter}"
        })
        assignment_counter += 1
    
    # Add quizzes and initial assessments with separate numbering
    quiz_counter = 1
    assessment_counter = 1
    for quiz in quizzes:
        # Use rubric total_points if quiz has rubric, otherwise use 100 for percentage-based scoring
        max_score = quiz.rubric.total_points if quiz.rubric else 100
        
        if quiz.is_initial_assessment:
            # Handle initial assessments
            activities.append({
                'object': quiz,
                'type': 'initial_assessment',
                'created_at': quiz.created_at,
                'title': quiz.title,
                'max_score': max_score,
                'activity_number': assessment_counter,
                'activity_name': f"Initial Assessment {assessment_counter}"
            })
            assessment_counter += 1
        else:
            # Handle regular quizzes
            activities.append({
                'object': quiz,
                'type': 'quiz',
                'created_at': quiz.created_at,
                'title': quiz.title,
                'max_score': max_score,
                'activity_number': quiz_counter,
                'activity_name': f"Quiz {quiz_counter}"
            })
            quiz_counter += 1

    # Initial assessments are now handled in the quiz loop above
    
    # Add discussions with numbering (only if they have rubrics)
    discussion_counter = 1
    for discussion in discussions:
        if discussion.rubric:  # Only include discussions with rubrics
            # Use rubric total_points since discussion has rubric
            max_score = discussion.rubric.total_points
            activities.append({
                'object': discussion,
                'type': 'discussion',
                'created_at': discussion.created_at,
                'title': discussion.title,
                'max_score': max_score,
                'activity_number': discussion_counter,
                'activity_name': f"Discussion {discussion_counter}"
            })
            discussion_counter += 1
    
    # Add conferences with numbering (only if they have rubrics)
    conference_counter = 1
    for conference in conferences:
        if conference.rubric:  # Only include conferences with rubrics
            # Calculate max score from rubric
            max_score = conference.rubric.total_points
            
            activities.append({
                'object': conference,
                'type': 'conference',
                'created_at': conference.created_at,
                'title': conference.title,
                'max_score': max_score,
                'activity_number': conference_counter,
                'activity_name': f"Conference {conference_counter}"
            })
            conference_counter += 1
    
    # Add SCORM packages with numbering
    scorm_counter = 1
    for scorm_package in scorm_packages:
        activities.append({
            'object': scorm_package,
            'type': 'scorm',
            'created_at': scorm_package.upload_date if hasattr(scorm_package, 'upload_date') else timezone.now(),
            'title': scorm_package.title if hasattr(scorm_package, 'title') else 'SCORM Content',
            'max_score': 100,  # SCORM scores are typically on a 0-100 scale
            'activity_number': scorm_counter,
            'activity_name': f"SCORM {scorm_counter}"
        })
        scorm_counter += 1
    
    # Add SCORM topics without packages
    for scorm_topic in scorm_topics_without_packages:
        activities.append({
            'object': scorm_topic,  # Use the topic object instead of package
            'type': 'scorm_topic',  # Different type to distinguish from packages
            'created_at': scorm_topic.created_at if hasattr(scorm_topic, 'created_at') else timezone.now(),
            'title': scorm_topic.title,
            'max_score': 100,  # SCORM scores are typically on a 0-100 scale
            'activity_number': scorm_counter,
            'activity_name': f"SCORM {scorm_counter}"
        })
        scorm_counter += 1
    
    # Sort activities by creation date to ensure consistent ordering
    activities.sort(key=lambda x: x['created_at'])
    
    # Cache the activities for better performance
    try:
        activities_cache_key = f"gradebook:activities:course:{course_id}"
        cache.set(activities_cache_key, activities, timeout=600)  # Cache for 10 minutes
        logger.debug(f"Cached activities for course {course_id}")
    except Exception as e:
        logger.error(f"Error caching activities for course {course_id}: {str(e)}")
    
    # Log activity counts for debugging (using proper logger)
    logger.debug(f"Course {course.id} ({course.title}) activities found: "
                f"Assignments: {assignments.count()}, Quizzes: {quizzes.count()}, "
                f"Discussions: {discussions.count()}, Conferences: {conferences.count()}, "
                f"SCORM packages: {len(scorm_packages)}, SCORM topics without packages: {len(scorm_topics_without_packages)}, "
                f"Total activities: {len(activities)}, User role: {user.role}")
    
    # Calculate total possible points (convert all to Decimal to avoid type mismatch)
    total_possible_points = sum([Decimal(str(activity['max_score'])) for activity in activities if activity['max_score'] > 0])
    
    try:
        # Get grades for all assignments in this course with optimized queries
        all_grades = Grade.objects.filter(
            student__in=students,
            assignment__in=assignments
        ).select_related(
            'student', 
            'assignment__course', 
            'submission__graded_by'
        ).prefetch_related(
            'assignment__courses'
        ).order_by('-updated_at')
        
        # Use a more efficient approach to get unique grades (latest per student-assignment pair)
        
        # Get the latest grade for each student-assignment pair using a single query
        latest_grade_times = all_grades.values('student_id', 'assignment_id').annotate(
            latest_update=Max('updated_at')
        )
        
        # Create a lookup dictionary for efficient filtering
        latest_lookup = {
            (item['student_id'], item['assignment_id']): item['latest_update']
            for item in latest_grade_times
        }
        
        # Filter grades to only include the latest ones
        grades = [
            grade for grade in all_grades
            if grade.updated_at == latest_lookup.get((grade.student_id, grade.assignment_id))
        ]
        
        # Get quiz attempts for this course (ordered by end time) with optimized queries
        quiz_attempts = QuizAttempt.objects.filter(
            user__in=students,
            quiz__in=quizzes,
            is_completed=True
        ).select_related(
            'quiz__course', 
            'quiz__rubric',
            'user'
        ).prefetch_related(
            'quiz__topics__courses'
            # 'useranswer_set__question',  # Commented out - invalid prefetch_related parameter
            # 'useranswer_set__answer'  # Commented out - invalid prefetch_related parameter
        ).order_by('-end_time')
        
        # Get SCORM attempts for this course with optimized queries
        scorm_attempts = ScormAttempt.objects.filter(
            user__in=students,
            scorm_package__in=scorm_packages
        ).select_related(
            'scorm_package',
            'user'
        ).order_by('-last_accessed')
        
        # Get conference rubric evaluations for this course with optimized queries
        conference_evaluations = ConferenceRubricEvaluation.objects.filter(
            conference__in=conferences,
            attendance__user__in=students
        ).select_related('conference', 'attendance__user', 'criterion', 'evaluated_by', 'conference__rubric').order_by('-created_at')
        
    except Exception as e:
        logger.error(f"Error fetching gradebook data for course {course_id}: {str(e)}")
        # Initialize empty lists/querysets as fallback
        grades = []
        quiz_attempts = QuizAttempt.objects.none()
        scorm_attempts = ScormAttempt.objects.none()
        conference_evaluations = ConferenceRubricEvaluation.objects.none()
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/gradebook/', 'label': 'Gradebook', 'icon': 'fa-graduation-cap'},
        {'label': f'{course.title} - Detailed Gradebook', 'icon': 'fa-table'}
    ]
    
    # Pre-calculate all student scores for better performance
    try:
        # Generate cache key for student scores with proper invalidation support
        from core.utils.cache_invalidation import CacheInvalidationManager
        
        students_hash = hashlib.md5(str(sorted([s.id for s in students])).encode()).hexdigest()[:8]
        cache_key = f"gradebook:scores:course:{course_id}:students:{students_hash}"
        
        # Try to get from cache first
        student_scores = cache.get(cache_key)
        
        if student_scores is None:
            # Not in cache, calculate and cache
            # Note: initial_assessment_attempts are included in quiz_attempts now
            student_scores = pre_calculate_student_scores(
                students, activities, grades, quiz_attempts, 
                scorm_attempts, conference_evaluations, None
            )
            # Cache for 5 minutes (reduced for more frequent updates)
            cache.set(cache_key, student_scores, timeout=300)
            logger.debug(f"Cached student scores for course {course_id}")
        else:
            logger.debug(f"Retrieved cached student scores for course {course_id}")
        
    except Exception as e:
        logger.error(f"Error pre-calculating student scores for course {course_id}: {str(e)}")
        # Initialize empty score data as fallback
        student_scores = {}
    
    # Prepare display data for the template
    display_activities = prepare_activity_display_data(activities, user.role)
    
    # Enhance scores with display data
    enhanced_student_scores = enhance_student_scores_with_display_data(student_scores, activities)
    
    # Get outcome evaluations for students in this course
    outcome_evaluations = {}
    outcome_summary = {}
    course_rubrics = set()
    connected_outcomes = set()
    
    # Initialize variables to prevent NameError
    has_rubrics = False
    has_outcome_connections = False
    
    try:
        from lms_outcomes.models import OutcomeEvaluation, Outcome, RubricCriterionOutcome
        
        # First check if there are rubric-outcome connections for this course's assignments/quizzes
        for assignment in assignments:
            if assignment.rubric:
                course_rubrics.add(assignment.rubric)
        for quiz in quizzes:
            if quiz.rubric:
                course_rubrics.add(quiz.rubric)
        
        # Get outcomes connected to this course's rubrics
        if course_rubrics:
            rubric_criteria = []
            for rubric in course_rubrics:
                rubric_criteria.extend(rubric.criteria.all())
            
            connections = RubricCriterionOutcome.objects.filter(
                criterion__in=rubric_criteria
            ).select_related('outcome', 'criterion')
            
            for connection in connections:
                connected_outcomes.add(connection.outcome)
        
        # Auto-calculate outcome evaluations for students if connections exist but evaluations don't
        if connected_outcomes and students:
            for outcome in connected_outcomes:
                for student in students:
                    # Check if evaluation exists
                    if not OutcomeEvaluation.objects.filter(outcome=outcome, student=student).exists():
                        # Try to calculate and save evaluation
                        try:
                            outcome.update_student_evaluation(student)
                        except Exception as eval_error:
                            logger.warning(f"Could not auto-calculate outcome evaluation for {student} and {outcome}: {str(eval_error)}")
        
        # Get all outcome evaluations for students in this course
        evaluations = OutcomeEvaluation.objects.filter(
            student__in=students
        ).select_related('outcome', 'student').order_by('outcome__title', 'student__first_name', 'student__last_name')
        
        # Organize evaluations by student and outcome
        for evaluation in evaluations:
            student_id = evaluation.student.id
            outcome_id = evaluation.outcome.id
            
            if student_id not in outcome_evaluations:
                outcome_evaluations[student_id] = {}
            
            outcome_evaluations[student_id][outcome_id] = {
                'score': evaluation.score,
                'proficiency_level': evaluation.proficiency_level,
                'evidence_count': evaluation.evidence_count,
                'calculation_date': evaluation.calculation_date,
                'outcome': evaluation.outcome
            }
        
        # Get unique outcomes for this course's students (include connected outcomes even if no evaluations yet)
        unique_outcomes = set()
        # Add outcomes that have evaluations
        outcome_ids_with_evaluations = Outcome.objects.filter(
            evaluations__student__in=students
        ).distinct()
        unique_outcomes.update(outcome_ids_with_evaluations)
        # Add connected outcomes (for comprehensive tracking)
        unique_outcomes.update(connected_outcomes)
        
        unique_outcomes = sorted(unique_outcomes, key=lambda x: x.title)
        
        # Calculate summary statistics for each outcome
        for outcome in unique_outcomes:
            student_evaluations = OutcomeEvaluation.objects.filter(
                outcome=outcome,
                student__in=students
            )
            
            if student_evaluations.exists():
                scores = [eval.score for eval in student_evaluations]
                proficiency_levels = [eval.proficiency_level for eval in student_evaluations]
                
                # Count proficiency levels
                level_counts = {}
                for level in proficiency_levels:
                    level_counts[level] = level_counts.get(level, 0) + 1
                
                outcome_summary[outcome.id] = {
                    'outcome': outcome,
                    'total_students': len(scores),
                    'average_score': sum(scores) / len(scores) if scores else 0,
                    'highest_score': max(scores) if scores else 0,
                    'lowest_score': min(scores) if scores else 0,
                    'proficiency_distribution': level_counts,
                    'mastery_rate': round(len([s for s in scores if s >= outcome.mastery_points]) / len(scores) * 100) if scores else 0
                }
            else:
                # Create placeholder summary for connected outcomes with no evaluations yet
                outcome_summary[outcome.id] = {
                    'outcome': outcome,
                    'total_students': 0,
                    'average_score': 0,
                    'highest_score': 0,
                    'lowest_score': 0,
                    'proficiency_distribution': {},
                    'mastery_rate': 0
                }
        
    except Exception as e:
        logger.error(f"Error fetching outcome evaluations: {str(e)}")
        outcome_evaluations = {}
        outcome_summary = {}
        connected_outcomes = set()

    # Check if this course has rubrics with outcome connections
    has_rubrics = bool(course_rubrics)
    has_outcome_connections = bool(connected_outcomes)


    context = {
        'course': course,
        'students': students,
        'assignments': assignments,
        'quizzes': quizzes,
        'grades': grades,
        'quiz_attempts': quiz_attempts,
        'scorm_attempts': scorm_attempts,
        'scorm_packages': scorm_packages,
        'discussions': discussions,
        'conferences': conferences,
        'conference_evaluations': conference_evaluations,
        'activities': display_activities, # Use prepared activities for template
        'total_possible_points': total_possible_points,
        'breadcrumbs': breadcrumbs,
        'overview_metrics': overview_metrics,
        # Pagination context
        'students_page': students_page,
        'total_students': total_students,
        'page_size': page_size,
        'current_page': page,
        # Pre-calculated score data
        'student_scores': enhanced_student_scores,
        # Outcome mastery data
        'outcome_evaluations': outcome_evaluations,
        'outcome_summary': outcome_summary,
        # Outcome connection status
        'has_outcome_connections': has_outcome_connections,
        'has_rubrics': has_rubrics,
    }
    
    return render(request, 'gradebook/course_detail.html', context)


@login_required
def assignment_grade_sidebar(request, assignment_id, student_id):
    """
    Render the assignment grading sidebar content
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # RBAC v0.1 Compliant Access Control
    user = request.user
    can_grade = False
    
    if user.role == 'globaladmin':
        can_grade = True  # FULL access
    elif user.role == 'superadmin':
        can_grade = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_grade = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_grade = True  # CONDITIONAL access (assigned courses/assignments)
    
    if not can_grade:
        return HttpResponse('Unauthorized', status=403)
    
    # Additional validation for assignment access - instructor should only grade their assignments or have group access
    if user.role == 'instructor':
        has_assignment_access = (
            assignment.user == user or 
            assignment.course.instructor == user or
            # Check for group-based access
            assignment.course.accessible_groups.filter(
                memberships__user=user,
                memberships__is_active=True,
                memberships__custom_role__name__icontains='instructor'
            ).exists()
        )
        if not has_assignment_access:
            return HttpResponse('Unauthorized - Assignment access denied', status=403)
    
    # Get or create submission
    submission_id = request.GET.get('submission_id')
    if submission_id:
        submission = get_object_or_404(AssignmentSubmission, id=submission_id)
    else:
        submission = AssignmentSubmission.objects.filter(
            assignment=assignment, 
            user=student
        ).first()
    
    # Get ALL submissions for this student and assignment (for history)
    all_submissions = AssignmentSubmission.objects.filter(
        assignment=assignment, 
        user=student
    ).select_related('graded_by').prefetch_related(
        'feedback_entries', 'grade_history'
    ).order_by('-submitted_at')
    
    # Get existing feedback
    feedback = None
    if submission:
        feedback = AssignmentFeedback.objects.filter(submission=submission).first()
    
    # Create the grading form with proper TinyMCE integration
    grading_form = AssignmentGradingForm(
        assignment=assignment,
        submission=submission,
        current_user=request.user
    )
    
    # Get rubric data if available
    rubric_data = None
    if assignment.rubric:
        rubric_data = {
            'rubric': assignment.rubric,
            'criteria': assignment.rubric.criteria.prefetch_related('ratings').all(),
            'evaluations': {}
        }
        
        if submission:
            evaluations = RubricEvaluation.objects.filter(
                submission=submission
            ).select_related('criterion', 'rating')
            
            for evaluation in evaluations:
                rubric_data['evaluations'][evaluation.criterion.id] = evaluation
    
    context = {
        'assignment': assignment,
        'student': student,
        'submission': submission,
        'all_submissions': all_submissions,
        'feedback': feedback,
        'grading_form': grading_form,
        'rubric_data': rubric_data,
    }
    
    return render(request, 'gradebook/partials/assignment_grade_sidebar.html', context)


@login_required
def quiz_grade_sidebar(request, quiz_id, student_id):
    """
    Render the quiz grading sidebar content
    """
    quiz = get_object_or_404(Quiz, id=quiz_id)
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # Prevent grading of VAK tests only (allow initial assessments to be graded)
    if quiz.is_vak_test:
        return HttpResponse('VAK tests cannot be graded through the gradebook. These are diagnostic tools stored in user profiles.', status=403)
    
    # RBAC v0.1 Compliant Access Control
    user = request.user
    can_grade = False
    
    if user.role == 'globaladmin':
        can_grade = True  # FULL access
    elif user.role == 'superadmin':
        can_grade = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_grade = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_grade = True  # CONDITIONAL access (assigned courses/quizzes)
    
    if not can_grade:
        return HttpResponse('Unauthorized', status=403)
    
    # Additional validation for quiz access - instructor should only grade their quizzes
    if user.role == 'instructor':
        if hasattr(quiz, 'creator') and quiz.creator != user:
            return HttpResponse('Unauthorized - Quiz access denied', status=403)
    
    # Get the quiz attempt
    attempt_id = request.GET.get('attempt_id')
    if attempt_id:
        attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    else:
        attempt = QuizAttempt.objects.filter(
            quiz=quiz, 
            user=student,
            is_completed=True
        ).first()
    
    # Get rubric data if available
    rubric_data = None
    overall_feedback = None
    if quiz.rubric:
        rubric_data = {
            'rubric': quiz.rubric,
            'criteria': quiz.rubric.criteria.prefetch_related('ratings').all(),
            'evaluations': {}
        }
        
        # Import here to avoid circular imports
        from quiz.models import QuizRubricEvaluation
        
        if attempt:
            evaluations = QuizRubricEvaluation.objects.filter(
                quiz_attempt=attempt
            ).select_related('criterion', 'rating')
            
            for evaluation in evaluations:
                rubric_data['evaluations'][evaluation.criterion.id] = evaluation
        
        # Get existing overall feedback for this quiz attempt
        if attempt:
            from lms_rubrics.models import RubricOverallFeedback
            try:
                overall_feedback = RubricOverallFeedback.objects.get(
                    quiz_attempt=attempt,
                    student=student
                )
            except RubricOverallFeedback.DoesNotExist:
                overall_feedback = None
    
    # Create the feedback form for the template
    feedback_form = None
    if quiz.rubric:
        from lms_rubrics.forms import RubricOverallFeedbackForm
        if overall_feedback:
            feedback_form = RubricOverallFeedbackForm(
                instance=overall_feedback,
                context_type='quiz',
                context_object=attempt,
                student=student,
                rubric=quiz.rubric,
                current_user=request.user
            )
        else:
            feedback_form = RubricOverallFeedbackForm(
                context_type='quiz',
                context_object=attempt,
                student=student,
                rubric=quiz.rubric,
                current_user=request.user
            )
    
    context = {
        'quiz': quiz,
        'student': student,
        'attempt': attempt,
        'rubric_data': rubric_data,
        'overall_feedback': overall_feedback,
        'feedback_form': feedback_form,
    }
    
    return render(request, 'gradebook/partials/quiz_grade_sidebar.html', context)


@login_required
def discussion_grade_sidebar(request, discussion_id, student_id):
    """
    Render the discussion grading sidebar content
    """
    from discussions.models import Discussion
    discussion = get_object_or_404(Discussion, id=discussion_id)
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # RBAC v0.1 Compliant Access Control
    user = request.user
    can_grade = False
    
    if user.role == 'globaladmin':
        can_grade = True  # FULL access
    elif user.role == 'superadmin':
        can_grade = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_grade = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_grade = True  # CONDITIONAL access (assigned courses/discussions)
    
    if not can_grade:
        return HttpResponse('Unauthorized', status=403)
    
    # Additional validation for discussion access
    if user.role == 'instructor':
        # Check if instructor has access through various means
        has_discussion_access = False
        
        # 1. If instructor created the discussion
        if hasattr(discussion, 'created_by') and discussion.created_by == user:
            has_discussion_access = True
        
        # 2. If instructor is assigned to the course containing this discussion
        elif hasattr(discussion, 'course') and discussion.course:
            if discussion.course.instructor == user:
                has_discussion_access = True
            else:
                # 3. Check for group-based access
                has_discussion_access = discussion.course.accessible_groups.filter(
                    memberships__user=user,
                    memberships__is_active=True,
                    memberships__custom_role__name__icontains='instructor'
                ).exists()
        
        # 4. Check if discussion is linked to courses through topics that the instructor has access to
        if not has_discussion_access:
            from courses.models import Course, CourseEnrollment
            # Check topic-based course access
            topic_courses = Course.objects.filter(
                coursetopic__topic__discussion=discussion
            ).distinct()
            
            for course in topic_courses:
                if (course.instructor == user or 
                    course.accessible_groups.filter(
                        memberships__user=user,
                        memberships__is_active=True,
                        memberships__custom_role__name__icontains='instructor'
                    ).exists()):
                    has_discussion_access = True
                    break
        
        # 5. Allow branch-level access for instructors in the same branch
        if not has_discussion_access and user.branch:
            # Check if discussion creator is from same branch or discussion course is from same branch
            if (hasattr(discussion, 'created_by') and discussion.created_by and 
                discussion.created_by.branch == user.branch):
                has_discussion_access = True
            elif (hasattr(discussion, 'course') and discussion.course and 
                  discussion.course.branch == user.branch):
                has_discussion_access = True
        
        if not has_discussion_access:
            return HttpResponse('Unauthorized - Discussion access denied', status=403)
    
    # Get student participation data
    from discussions.models import Comment
    student_comments = Comment.objects.filter(
        discussion=discussion,
        created_by=student
    ).select_related('parent').order_by('created_at')
    
    student_interactions = {
        'comment_count': student_comments.filter(parent__isnull=True).count(),
        'reply_count': student_comments.filter(parent__isnull=False).count(),
        'comments': student_comments,
        'likes_given': student.liked_comments.filter(discussion=discussion).count() + (1 if student in discussion.likes.all() else 0),
        'has_participated': student_comments.exists() or student in discussion.likes.all()
    }
    
    # Get rubric data if available
    rubric_data = None
    overall_feedback = None
    if discussion.rubric:
        rubric_data = {
            'rubric': discussion.rubric,
            'criteria': discussion.rubric.criteria.prefetch_related('ratings').all(),
            'evaluations': {}
        }
        
        # Get existing evaluations for this student
        evaluations = RubricEvaluation.objects.filter(
            discussion=discussion,
            student=student
        ).select_related('criterion', 'rating')
        
        for evaluation in evaluations:
            rubric_data['evaluations'][evaluation.criterion.id] = evaluation
        
        # Get existing overall feedback for this student
        try:
            overall_feedback = RubricOverallFeedback.objects.get(
                discussion=discussion,
                student=student
            )
        except RubricOverallFeedback.DoesNotExist:
            overall_feedback = None

    # Always create the feedback form for the template (like assignment sidebar)
    from lms_rubrics.forms import RubricOverallFeedbackForm
    if overall_feedback:
        feedback_form = RubricOverallFeedbackForm(instance=overall_feedback)
    else:
        feedback_form = RubricOverallFeedbackForm()
    
    context = {
        'discussion': discussion,
        'student': student,
        'student_interactions': student_interactions,
        'rubric_data': rubric_data,
        'overall_feedback': overall_feedback,
        'feedback_form': feedback_form,
    }
    
    return render(request, 'gradebook/partials/discussion_grade_sidebar.html', context)


@login_required
def conference_grade_sidebar(request, conference_id, student_id):
    """
    Render the conference grading sidebar content
    """
    from conferences.models import Conference, ConferenceAttendance
    conference = get_object_or_404(Conference, id=conference_id)
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # RBAC v0.1 Compliant Access Control
    user = request.user
    can_grade = False
    
    if user.role == 'globaladmin':
        can_grade = True  # FULL access
    elif user.role == 'superadmin':
        can_grade = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_grade = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_grade = True  # CONDITIONAL access (assigned courses/conferences)
    
    if not can_grade:
        return HttpResponse('Unauthorized', status=403)
    
    # Additional validation for conference access
    if user.role == 'instructor':
        if hasattr(conference, 'created_by') and conference.created_by != user:
            # Check if the instructor is assigned to the course containing this conference or has group access
            has_conference_access = False
            if hasattr(conference, 'course') and conference.course:
                has_conference_access = (
                    conference.course.instructor == user or
                    # Check for group-based access
                    conference.course.accessible_groups.filter(
                        memberships__user=user,
                        memberships__is_active=True,
                        memberships__custom_role__name__icontains='instructor'
                    ).exists()
                )
            if not has_conference_access:
                return HttpResponse('Unauthorized - Conference access denied', status=403)
    
    # Get student attendance data
    attendance = ConferenceAttendance.objects.filter(
        conference=conference,
        user=student
    ).first()
    
    attendance_data = None
    if attendance:
        attendance_data = {
            'attendance': attendance,
            'join_time': attendance.join_time,
            'leave_time': attendance.leave_time,
            'duration_minutes': attendance.duration_minutes or 0,
            'has_attended': True
        }
    else:
        attendance_data = {
            'attendance': None,
            'has_attended': False
        }
    
    # Get rubric data if available
    rubric_data = None
    overall_feedback = None
    if conference.rubric and attendance:
        from conferences.models import ConferenceRubricEvaluation
        
        rubric_data = {
            'rubric': conference.rubric,
            'criteria': conference.rubric.criteria.prefetch_related('ratings').all(),
            'evaluations': {}
        }
        
        # Get existing evaluations for this student's attendance
        evaluations = ConferenceRubricEvaluation.objects.filter(
            conference=conference,
            attendance=attendance
        ).select_related('criterion', 'rating')
        
        for evaluation in evaluations:
            rubric_data['evaluations'][evaluation.criterion.id] = evaluation
        
        # Get existing overall feedback for this student's attendance
        try:
            overall_feedback = RubricOverallFeedback.objects.get(
                conference=conference,
                student=student
            )
        except RubricOverallFeedback.DoesNotExist:
            overall_feedback = None
    
    # Create the feedback form for the template
    feedback_form = None
    if conference.rubric:
        from lms_rubrics.forms import RubricOverallFeedbackForm
        if overall_feedback:
            feedback_form = RubricOverallFeedbackForm(instance=overall_feedback)
        else:
            feedback_form = RubricOverallFeedbackForm()
    
    context = {
        'conference': conference,
        'student': student,
        'attendance_data': attendance_data,
        'rubric_data': rubric_data,
        'overall_feedback': overall_feedback,
        'feedback_form': feedback_form,
    }
    
    return render(request, 'gradebook/partials/conference_grade_sidebar.html', context)


@login_required
@require_http_methods(["POST"])
def ajax_save_grade(request):
    """
    Save grade via AJAX from the sidebar
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # RBAC v0.1 Compliant Access Control
    user = request.user
    can_grade = False
    
    if user.role == 'globaladmin':
        can_grade = True  # FULL access
    elif user.role == 'superadmin':
        can_grade = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_grade = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_grade = True  # CONDITIONAL access (assigned courses/assignments)
    
    if not can_grade:
        return JsonResponse({'success': False, 'error': 'Unauthorized'})
    
    try:
        logger.info(f" ajax_save_grade called by {user.username}")
        logger.info(f"📦 POST data: {dict(request.POST)}")
        logger.info(f"📁 FILES data: {list(request.FILES.keys())}")
        # Use comprehensive validation
        # Convert QueryDict to regular dict with single values (not lists)
        post_data = {key: value for key, value in request.POST.items()}
        try:
            validated_data = validate_gradebook_request_data(post_data)
            activity_type = validated_data['activity_type']
            activity_id = validated_data['activity_id']
            student_id = validated_data['student_id']
            grade = validated_data.get('grade')
            feedback_text = validated_data.get('feedback', '')
            status = validated_data.get('status', 'graded')
            submission_id = validated_data.get('submission_id')
            attempt_id = validated_data.get('attempt_id')
        except (ValidationError, GradebookValidationError) as e:
            return JsonResponse({'success': False, 'error': str(e)})
        
        User = get_user_model()
        student = get_object_or_404(User, id=student_id)
        
        if activity_type == 'assignment':
            assignment = get_object_or_404(Assignment, id=activity_id)
            
            # Additional validation for assignment access - instructor should only grade their assignments or have group access
            if user.role == 'instructor':
                has_assignment_access = (
                    assignment.user == user or 
                    assignment.course.instructor == user or
                    # Check for group-based access
                    assignment.course.accessible_groups.filter(
                        memberships__user=user,
                        memberships__is_active=True,
                        memberships__custom_role__name__icontains='instructor'
                    ).exists()
                )
                if not has_assignment_access:
                    return JsonResponse({'success': False, 'error': 'Assignment access denied'})
            
            if submission_id:
                submission = get_object_or_404(AssignmentSubmission, id=submission_id)
            else:
                submission, created = AssignmentSubmission.objects.get_or_create(
                    assignment=assignment,
                    user=student,
                    defaults={'status': 'not_graded'}
                )
            
            # Update submission with validated grade
            if grade is not None:
                submission.grade = float(grade)  # grade is already validated as Decimal
            submission.status = status
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()
            
            # Handle feedback (text, audio, video)
            audio_feedback = request.FILES.get('audio_feedback')
            video_feedback = request.FILES.get('video_feedback')
            
            logger.info(f"🎵 Audio feedback: {audio_feedback.name if audio_feedback else 'None'}")
            logger.info(f"🎥 Video feedback: {video_feedback.name if video_feedback else 'None'}")
            logger.info(f" Text feedback: {'Present' if feedback_text else 'None'}")
            
            if feedback_text or audio_feedback or video_feedback:
                # Get the most recent feedback or create a new one
                feedback = AssignmentFeedback.objects.filter(
                    submission=submission
                ).order_by('-created_at').first()
                
                if feedback:
                    # Update existing feedback
                    if feedback_text:
                        feedback.feedback = feedback_text
                    if audio_feedback:
                        feedback.audio_feedback = audio_feedback
                    if video_feedback:
                        feedback.video_feedback = video_feedback
                    feedback.created_by = request.user
                    feedback.save()
                else:
                    # Create new feedback
                    feedback = AssignmentFeedback.objects.create(
                        submission=submission,
                        feedback=feedback_text or '',
                        audio_feedback=audio_feedback,
                        video_feedback=video_feedback,
                        created_by=request.user
                    )
            
            # Handle rubric data
            rubric_data = request.POST.get('rubric_data')
            if rubric_data and assignment.rubric:
                try:
                    rubric_evaluations = json.loads(rubric_data)
                    for criterion_id, evaluation_data in rubric_evaluations.items():
                        if evaluation_data.get('points') is not None:
                            # Import here to avoid circular imports
                            from lms_rubrics.models import RubricRating
                            
                            defaults = {
                                'points': evaluation_data['points'],
                                'comments': evaluation_data.get('comments', ''),
                                'evaluated_by': request.user,
                                'student': student
                            }
                            
                            # Include rating if provided
                            rating_id = evaluation_data.get('rating_id')
                            if rating_id:
                                try:
                                    rating = RubricRating.objects.get(id=rating_id)
                                    defaults['rating'] = rating
                                except RubricRating.DoesNotExist:
                                    pass
                            
                            RubricEvaluation.objects.update_or_create(
                                submission=submission,
                                criterion_id=criterion_id,
                                defaults=defaults
                            )
                except json.JSONDecodeError:
                    pass
        
        elif activity_type == 'quiz' or activity_type == 'initial_assessment':
            quiz = get_object_or_404(Quiz, id=activity_id)
            
            # Prevent grading of initial assessments and VAK tests
            if quiz.is_initial_assessment or quiz.is_vak_test:
                return JsonResponse({
                    'success': False, 
                    'error': 'Initial assessments and VAK tests cannot be graded through the gradebook. These are diagnostic tools for informational purposes only. View detailed results in the student\'s profile.'
                })
            
            if attempt_id:
                attempt = get_object_or_404(QuizAttempt, id=attempt_id)
                
                # Handle manual grading override with validated grade
                if grade is not None:
                    attempt.manual_grade = float(grade)  # grade is already validated as Decimal
                    attempt.save()
                
                # Handle rubric data for quiz
                rubric_data = request.POST.get('rubric_data')
                if rubric_data and quiz.rubric:
                    try:
                        rubric_evaluations = json.loads(rubric_data)
                        # Import here to avoid circular imports
                        from quiz.models import QuizRubricEvaluation
                        from lms_rubrics.models import RubricRating
                        
                        for criterion_id, evaluation_data in rubric_evaluations.items():
                            if evaluation_data.get('points') is not None:
                                defaults = {
                                    'points': evaluation_data['points'],
                                    'comments': evaluation_data.get('comments', ''),
                                    'evaluated_by': request.user,
                                    'student': student
                                }
                                
                                # Include rating if provided
                                rating_id = evaluation_data.get('rating_id')
                                if rating_id:
                                    try:
                                        rating = RubricRating.objects.get(id=rating_id)
                                        defaults['rating'] = rating
                                    except RubricRating.DoesNotExist:
                                        pass
                                
                                QuizRubricEvaluation.objects.update_or_create(
                                    quiz_attempt=attempt,
                                    criterion_id=criterion_id,
                                    defaults=defaults
                                )
                    except json.JSONDecodeError:
                        pass
                
                # Handle overall feedback for quiz
                feedback_type = request.POST.get('feedback_type')
                if feedback_type == 'overall' and quiz.rubric:
                    overall_feedback = request.POST.get('feedback', '').strip()
                    audio_feedback = request.FILES.get('audio_feedback')
                    video_feedback = request.FILES.get('video_feedback')
                    
                    # Create or update overall feedback if provided
                    if overall_feedback or audio_feedback or video_feedback:
                        feedback_data = {
                            'feedback': overall_feedback,
                            'is_private': False,  # All feedback is visible
                            'created_by': request.user,
                            'student': student,
                            'rubric': quiz.rubric,
                            'quiz_attempt': attempt
                        }
                        
                        # Add files if provided
                        if audio_feedback:
                            feedback_data['audio_feedback'] = audio_feedback
                        if video_feedback:
                            feedback_data['video_feedback'] = video_feedback
                        
                        # Update or create feedback
                        overall_feedback_obj, created = RubricOverallFeedback.objects.update_or_create(
                            quiz_attempt=attempt,
                            student=student,
                            defaults=feedback_data
                        )
        
        elif activity_type == 'discussion':
            from discussions.models import Discussion
            discussion = get_object_or_404(Discussion, id=activity_id)
            
            # Additional validation for discussion access
            if user.role == 'instructor':
                if hasattr(discussion, 'created_by') and discussion.created_by != user:
                    if hasattr(discussion, 'course') and discussion.course and discussion.course.instructor != user:
                        return JsonResponse({'success': False, 'error': 'Discussion access denied'})
            
            # Handle rubric data for discussion
            rubric_data = request.POST.get('rubric_data')
            if rubric_data and discussion.rubric:
                try:
                    rubric_evaluations = json.loads(rubric_data)
                    from lms_rubrics.models import RubricRating
                    
                    for criterion_id, evaluation_data in rubric_evaluations.items():
                        if evaluation_data.get('points') is not None:
                            defaults = {
                                'points': evaluation_data['points'],
                                'comments': evaluation_data.get('comments', ''),
                                'evaluated_by': request.user,
                                'student': student
                            }
                            
                            # Include rating if provided
                            rating_id = evaluation_data.get('rating_id')
                            if rating_id:
                                try:
                                    rating = RubricRating.objects.get(id=rating_id)
                                    defaults['rating'] = rating
                                except RubricRating.DoesNotExist:
                                    pass
                            
                            RubricEvaluation.objects.update_or_create(
                                discussion=discussion,
                                criterion_id=criterion_id,
                                student=student,
                                defaults=defaults
                            )
                except json.JSONDecodeError:
                    pass
            
            # Handle overall feedback for discussion
            overall_feedback = request.POST.get('feedback', '').strip()
            audio_feedback = request.FILES.get('audio_feedback')
            video_feedback = request.FILES.get('video_feedback')
            is_private = False  # All feedback is visible
            
            # Create or update overall feedback if provided
            if overall_feedback or audio_feedback or video_feedback:
                if discussion.rubric:
                    feedback_data = {
                        'feedback': overall_feedback,
                        'is_private': is_private,
                        'created_by': request.user,
                        'student': student,
                        'rubric': discussion.rubric,
                        'discussion': discussion
                    }
                    
                    # Add files if provided
                    if audio_feedback:
                        feedback_data['audio_feedback'] = audio_feedback
                    if video_feedback:
                        feedback_data['video_feedback'] = video_feedback
                    
                    # Update or create feedback
                    overall_feedback_obj, created = RubricOverallFeedback.objects.update_or_create(
                        discussion=discussion,
                        student=student,
                        defaults=feedback_data
                    )
        
        elif activity_type == 'conference':
            from conferences.models import Conference, ConferenceAttendance, ConferenceRubricEvaluation
            conference = get_object_or_404(Conference, id=activity_id)
            
            # Additional validation for conference access
            if user.role == 'instructor':
                if hasattr(conference, 'created_by') and conference.created_by != user:
                    if hasattr(conference, 'course') and conference.course and conference.course.instructor != user:
                        return JsonResponse({'success': False, 'error': 'Conference access denied'})
            
            # Get student attendance
            attendance = ConferenceAttendance.objects.filter(
                conference=conference,
                user=student
            ).first()
            
            if not attendance:
                return JsonResponse({'success': False, 'error': 'Student has no attendance record for this conference'})
            
            # Handle rubric data for conference
            rubric_data = request.POST.get('rubric_data')
            if rubric_data and conference.rubric:
                try:
                    rubric_evaluations = json.loads(rubric_data)
                    from lms_rubrics.models import RubricRating
                    
                    for criterion_id, evaluation_data in rubric_evaluations.items():
                        if evaluation_data.get('points') is not None:
                            defaults = {
                                'points': evaluation_data['points'],
                                'comments': evaluation_data.get('comments', ''),
                                'evaluated_by': request.user
                            }
                            
                            # Include rating if provided
                            rating_id = evaluation_data.get('rating_id')
                            if rating_id:
                                try:
                                    rating = RubricRating.objects.get(id=rating_id)
                                    defaults['rating'] = rating
                                except RubricRating.DoesNotExist:
                                    pass
                            
                            ConferenceRubricEvaluation.objects.update_or_create(
                                conference=conference,
                                attendance=attendance,
                                criterion_id=criterion_id,
                                defaults=defaults
                            )
                except json.JSONDecodeError:
                    pass
            
            # Handle overall feedback for conference
            overall_feedback = request.POST.get('feedback', '').strip()
            audio_feedback = request.FILES.get('audio_feedback')
            video_feedback = request.FILES.get('video_feedback')
            is_private = False  # All feedback is visible
            
            # Create or update overall feedback if provided
            if overall_feedback or audio_feedback or video_feedback:
                if conference.rubric:
                    feedback_data = {
                        'feedback': overall_feedback,
                        'is_private': is_private,
                        'created_by': request.user,
                        'student': student,
                        'rubric': conference.rubric,
                        'conference': conference
                    }
                    
                    # Add files if provided
                    if audio_feedback:
                        feedback_data['audio_feedback'] = audio_feedback
                    if video_feedback:
                        feedback_data['video_feedback'] = video_feedback
                    
                    # Update or create feedback
                    overall_feedback_obj, created = RubricOverallFeedback.objects.update_or_create(
                        conference=conference,
                        student=student,
                        defaults=feedback_data
                    )
        
        logger.info(f" Grade saved successfully for {activity_type} ID {activity_id}, student {student_id}")
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f" Error saving grade: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_gradebook_csv(request, course_id):
    """
    Export gradebook data to CSV format for a specific course.
    """
    import csv
    from django.http import HttpResponse
    from django.utils import timezone
    from datetime import datetime
    
    user = request.user
    User = get_user_model()
    
    try:
        # Get the specific course
        course = get_object_or_404(Course, id=course_id)
        
        # Check permissions (same as course_gradebook_detail)
        if user.role == 'instructor':
            has_permission = (
                course.instructor == user or
                CourseEnrollment.objects.filter(course=course, user=user).exists() or
                course.accessible_groups.filter(
                    memberships__user=user,
                    memberships__is_active=True,
                    memberships__custom_role__name__icontains='instructor'
                ).exists()
            )
            if not has_permission:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("You don't have permission to export this gradebook.")
        elif user.role == 'learner':
            if not CourseEnrollment.objects.filter(course=course, user=user).exists():
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("You are not enrolled in this course.")
        elif user.role not in ['admin', 'superadmin', 'globaladmin']:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("You don't have permission to export this gradebook.")
        
        # Get students for this course
        if user.role == 'learner':
            students = User.objects.filter(id=user.id).select_related('branch')
        else:
            students = User.objects.filter(
                Q(enrolled_courses__id=course_id) & Q(role='learner')
            ).distinct().select_related('branch').prefetch_related('enrolled_courses')
        
        # Get all activities for this course (same logic as course_gradebook_detail)
        assignments = Assignment.objects.filter(
            Q(course=course) | Q(courses=course) | Q(topics__courses=course)
        ).filter(
            is_active=True
        ).filter(
            Q(topics__status='active') | Q(topics__isnull=True)
        ).distinct().select_related('course', 'user', 'rubric').prefetch_related('courses', 'topics').order_by('created_at')
        
        quizzes = Quiz.objects.filter(
            Q(course=course) | Q(topics__courses=course)
        ).filter(
            is_active=True
        ).filter(
            Q(topics__status='active') | Q(topics__isnull=True)
        ).exclude(
            Q(is_vak_test=True)
        ).distinct().select_related('course', 'creator', 'rubric').prefetch_related('topics').order_by('created_at')
        
        discussions = Discussion.objects.filter(
            Q(course=course) | Q(topics__courses=course)
        ).filter(
            status='published'
        ).filter(
            Q(topics__status='active') | Q(topics__isnull=True)
        ).distinct().select_related('course', 'created_by', 'rubric').prefetch_related('topics').order_by('created_at')
        
        conferences = Conference.objects.filter(
            Q(course=course) | Q(topics__courses=course)
        ).filter(
            status='published'
        ).filter(
            Q(topics__status='active') | Q(topics__isnull=True)
        ).distinct().select_related('course', 'created_by', 'rubric').prefetch_related('topics').order_by('created_at')
        
        # Get SCORM packages
        scorm_packages = []
        scorm_topics_without_packages = []
        try:
            scorm_topics = Topic.objects.filter(
                coursetopic__course=course,
                content_type='SCORM',
                status='active'
            ).prefetch_related('coursetopic_set__course').order_by('created_at')
            
            for topic in scorm_topics:
                try:
                    # Check if topic has a SCORM package
                    if hasattr(topic, 'scorm_package') and topic.scorm_package:
                        scorm_packages.append(topic.scorm_package)
                    else:
                        scorm_topics_without_packages.append(topic)
                except Exception as e:
                    logger.error(f"Error processing SCORM topic {topic.id}: {str(e)}")
                    scorm_topics_without_packages.append(topic)
        except Exception as e:
            logger.error(f"Error fetching SCORM content for course {course_id}: {str(e)}")
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="gradebook_{course.title}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        
        # Create header row
        headers = ['Student Name', 'Student Email', 'Student ID', 'Branch']
        
        # Add assignment columns
        for assignment in assignments:
            headers.append(f'Assignment: {assignment.title}')
        
        # Add quiz columns
        for quiz in quizzes:
            headers.append(f'Quiz: {quiz.title}')
        
        # Add discussion columns (only those with rubrics)
        for discussion in discussions.filter(rubric__isnull=False):
            headers.append(f'Discussion: {discussion.title}')
        
        # Add conference columns (only those with rubrics)
        for conference in conferences.filter(rubric__isnull=False):
            headers.append(f'Conference: {conference.title}')
        
        # Add SCORM columns
        for package in scorm_packages:
            headers.append(f'SCORM: {package.title}')
        
        for topic in scorm_topics_without_packages:
            headers.append(f'SCORM Topic: {topic.title}')
        
        # Add overall grade column
        headers.append('Overall Grade')
        
        writer.writerow(headers)
        
        # Get all submissions and attempts for performance
        all_submissions = AssignmentSubmission.objects.filter(
            assignment__in=assignments,
            user__in=students
        ).select_related('assignment', 'user', 'graded_by')
        
        # Get quiz attempts
        latest_attempts = QuizAttempt.objects.filter(
            quiz=OuterRef('quiz'),
            user=OuterRef('user'),
            is_completed=True
        ).order_by('-end_time')
        
        quiz_attempts = QuizAttempt.objects.filter(
            user__in=students,
            quiz__in=quizzes,
            is_completed=True,
            end_time__in=Subquery(latest_attempts.values('end_time')[:1])
        ).select_related('quiz', 'user', 'quiz__rubric')
        
        # Get SCORM attempts
        all_scorm_attempts = ScormAttempt.objects.filter(
            scorm_package__in=scorm_packages,
            user__in=students
        ).select_related('scorm_package', 'user')
        
        # Write data rows
        for student in students:
            row = [
                student.get_full_name() or student.username,
                student.email,
                student.id,
                student.branch.name if student.branch else 'N/A'
            ]
            
            # Add assignment grades
            for assignment in assignments:
                submission = all_submissions.filter(
                    assignment=assignment,
                    user=student
                ).first()
                
                if submission:
                    if submission.status == 'graded' and submission.grade is not None:
                        row.append(f"{submission.grade}/{assignment.max_points}")
                    elif submission.status in ['submitted', 'not_graded']:
                        row.append('Submitted')
                    else:
                        row.append(submission.status.title())
                else:
                    row.append('Not Started')
            
            # Add quiz grades
            for quiz in quizzes:
                attempt = quiz_attempts.filter(
                    quiz=quiz,
                    user=student
                ).first()
                
                if attempt:
                    if attempt.score is not None:
                        row.append(f"{attempt.score}/{quiz.max_points}")
                    else:
                        row.append('Completed')
                else:
                    row.append('Not Started')
            
            # Add discussion grades (only those with rubrics)
            for discussion in discussions.filter(rubric__isnull=False):
                # For discussions, we would need to check rubric evaluations
                # This is a simplified version - you might want to add more detailed grading logic
                row.append('N/A')  # Placeholder for discussion grades
            
            # Add conference grades (only those with rubrics)
            for conference in conferences.filter(rubric__isnull=False):
                # For conferences, we would need to check rubric evaluations
                # This is a simplified version - you might want to add more detailed grading logic
                row.append('N/A')  # Placeholder for conference grades
            
            # Add SCORM grades
            for package in scorm_packages:
                attempt = all_scorm_attempts.filter(
                    scorm_package=package,
                    user=student
                ).first()
                
                if attempt:
                    if attempt.lesson_status == 'completed':
                        row.append('Completed')
                    elif attempt.lesson_status == 'incomplete':
                        row.append('In Progress')
                    else:
                        row.append(attempt.lesson_status.title())
                else:
                    row.append('Not Started')
            
            # Add SCORM topics without packages - check TopicProgress
            for topic in scorm_topics_without_packages:
                from courses.models import TopicProgress
                topic_progress = TopicProgress.objects.filter(
                    topic=topic,
                    user=student
                ).first()
                
                if topic_progress:
                    if topic_progress.completed:
                        row.append('Completed')
                    elif topic_progress.last_score is not None:
                        # Use last_score (most recent/live) to match SCORM results page
                        if float(topic_progress.last_score) >= 70:
                            row.append(f"Completed ({topic_progress.last_score}%)")
                        else:
                            row.append(f"Failed ({topic_progress.last_score}%)")
                    elif topic_progress.best_score is not None:
                        # Fallback to best_score if last_score not available
                        if float(topic_progress.best_score) >= 70:
                            row.append(f"Completed ({topic_progress.best_score}%)")
                        else:
                            row.append(f"Failed ({topic_progress.last_score}%)")
                    elif (topic_progress.attempts > 0 or topic_progress.last_accessed) and not topic_progress.completed:
                        row.append('Failed')
                    else:
                        row.append('Not Started')
                else:
                    row.append('Not Started')
            
            # Calculate overall grade (simplified)
            # Grade calculation logic
            row.append('N/A')
            
            writer.writerow(row)
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting gradebook for course {course_id}: {str(e)}")
        from django.contrib import messages
        messages.error(request, "An error occurred while exporting the gradebook. Please try again.")
        return redirect('gradebook:course_detail', course_id=course_id)
