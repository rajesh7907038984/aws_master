from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Grade
from django.db.models import Q, Max, Count, Case, When, IntegerField, OuterRef, Subquery, Sum, F
from assignments.models import Assignment, AssignmentSubmission, AssignmentFeedback
from assignments.forms import AssignmentGradingForm
from django.contrib.auth import get_user_model
from courses.models import Course, CourseEnrollment, Topic
from quiz.models import Quiz, QuizAttempt, QuizRubricEvaluation
from discussions.models import Discussion
from conferences.models import Conference, ConferenceRubricEvaluation
from scorm.models import ELearningPackage, ELearningTracking
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
import json
import logging
import hashlib
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.db import transaction

logger = logging.getLogger(__name__)


def pre_calculate_student_scores(students, activities, grades, quiz_attempts, conference_evaluations, initial_assessment_attempts=None) -> dict:
    """
    Pre-calculate all student scores for activities to reduce template computation.
    Returns a dictionary structure: {student_id: {activity_id: score_data}}
    """
    # Initialize score data structure
    score_data = {}
    
    # Use atomic transaction to prevent race conditions
    with transaction.atomic():
        try:
            # Create lookups for efficient data retrieval
            grade_lookup = {}
            for grade in grades:
                key = (grade.student_id, grade.assignment_id)
                grade_lookup[key] = grade
            
            # Use pagination to prevent memory leaks for large datasets
            quiz_attempt_lookup = {}
            batch_size = 1000  # Process in batches to prevent memory issues
            
            for i in range(0, len(quiz_attempts), batch_size):
                batch = quiz_attempts[i:i + batch_size]
                for attempt in batch:
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
            
            conference_lookup = {}
            for evaluation in conference_evaluations:
                key = (evaluation.attendance.user_id, evaluation.conference_id)
                if key not in conference_lookup:
                    conference_lookup[key] = []
                conference_lookup[key].append(evaluation)
            
            # Initialize student_scores dictionary
            student_scores = {}
            
            # Calculate scores for each student-activity pair
            for student in students:
                logger.debug(f"Processing student: {student.username} (ID: {student.id})")
                try:
                    student_scores[student.id] = {}
                    
                    for activity in activities:
                        try:
                            activity_id = activity['object'].id
                            activity_type = activity['type']
                            
                            if activity_type == 'assignment':
                                key = (student.id, activity_id)
                                if key in grade_lookup:
                                    grade = grade_lookup[key]
                                    if grade.excused:
                                        student_scores[student.id][activity_id] = {
                                            'score': None,
                                            'max_score': activity['max_score'],
                                            'excused': True,
                                            'date': grade.updated_at,
                                            'type': 'assignment',
                                            'submission': grade.submission,
                                            'score_source': 'manual'
                                        }
                                    else:
                                        # Check if submission is late
                                        is_late = False
                                        if grade.submission and activity['object'].due_date and grade.submission.submitted_at:
                                            is_late = grade.submission.submitted_at > activity['object'].due_date
                                        
                                        student_scores[student.id][activity_id] = {
                                            'score': grade.score,
                                            'max_score': activity['max_score'],
                                            'date': grade.updated_at,
                                            'type': 'assignment',
                                            'submission': grade.submission,
                                            'is_late': is_late,
                                            'score_source': 'manual'
                                        }
                                else:
                                    # Check for submission without grade
                                    try:
                                        submission = AssignmentSubmission.objects.filter(
                                            assignment=activity['object'],
                                            user_id=student.id
                                        ).first()
                                        
                                        if submission:
                                            is_late = False
                                            if activity['object'].due_date and submission.submitted_at:
                                                is_late = submission.submitted_at > activity['object'].due_date
                                            
                                            student_scores[student.id][activity_id] = {
                                                'score': submission.grade,
                                                'max_score': activity['max_score'],
                                                'date': submission.submitted_at,
                                                'type': 'assignment',
                                                'submission': submission,
                                                'is_late': is_late,
                                                'has_submission': True,
                                                'score_source': 'manual'
                                            }
                                        else:
                                            student_scores[student.id][activity_id] = {
                                                'score': None,
                                                'max_score': activity['max_score'],
                                                'type': 'assignment',
                                                'has_submission': False,
                                                'score_source': 'manual'
                                            }
                                    except Exception as e:
                                        logger.error(f"Error processing assignment submission for student {student.id}, activity {activity_id}: {str(e)}", exc_info=True)
                                        student_scores[student.id][activity_id] = {
                                            'score': None,
                                            'max_score': activity['max_score'],
                                            'type': 'assignment',
                                            'has_submission': False,
                                            'score_source': 'manual'
                                        }
                            
                            elif activity_type == 'quiz':
                                key = (student.id, activity_id)
                                if key in quiz_attempt_lookup:
                                    attempt = quiz_attempt_lookup[key]
                                    final_score = attempt.score
                                    max_score = activity['max_score']
                                    score_source = 'auto'
                                    
                                    # Check for rubric evaluation
                                    quiz = activity['object']
                                    if quiz.rubric:
                                        try:
                                            rubric_evaluations = QuizRubricEvaluation.objects.filter(
                                                quiz_attempt=attempt
                                            )
                                            if rubric_evaluations.exists():
                                                final_score = sum(evaluation.points for evaluation in rubric_evaluations)
                                                max_score = quiz.rubric.total_points
                                                score_source = 'rubric'
                                        except Exception as e:
                                            logger.error(f"Error processing quiz rubric evaluation for student {student.id}, quiz {activity_id}: {str(e)}", exc_info=True)
                                            pass
                                    else:
                                        final_score = attempt.score
                                        max_score = 100
                                        score_source = 'auto'
                                    
                                    student_scores[student.id][activity_id] = {
                                        'score': final_score,
                                        'max_score': max_score,
                                        'date': attempt.end_time or attempt.start_time,
                                        'type': 'quiz',
                                        'attempt': attempt,
                                        'score_source': score_source
                                    }
                                else:
                                    student_scores[student.id][activity_id] = {
                                        'score': None,
                                        'max_score': activity['max_score'],
                                        'type': 'quiz',
                                        'attempt': None,
                                        'score_source': 'auto'
                                    }
                            
                            elif activity_type == 'initial_assessment':
                                key = (student.id, activity_id)
                                if key in quiz_attempt_lookup:
                                    attempt = quiz_attempt_lookup[key]
                                    assessment_data = attempt.calculate_assessment_classification()
                                    
                                    quiz = activity['object']
                                    final_score = attempt.score
                                    max_score = 100
                                    
                                    student_scores[student.id][activity_id] = {
                                        'score': final_score,
                                        'max_score': max_score,
                                        'date': attempt.end_time or attempt.start_time,
                                        'type': 'initial_assessment',
                                        'attempt': attempt,
                                        'classification': assessment_data.get('classification', 'N/A') if assessment_data else 'N/A',
                                        'classification_data': assessment_data,
                                        'is_informational': True,
                                        'score_source': 'auto'
                                    }
                                else:
                                    student_scores[student.id][activity_id] = {
                                        'score': None,
                                        'max_score': activity['max_score'],
                                        'type': 'initial_assessment',
                                        'attempt': None,
                                        'score_source': 'auto'
                                    }
                            
                            elif activity_type == 'conference':
                                key = (student.id, activity_id)
                                if key in conference_lookup:
                                    evaluations = conference_lookup[key]
                                    total_score = sum(eval.score for eval in evaluations if eval.score is not None)
                                    max_score = activity['max_score']
                                    
                                    student_scores[student.id][activity_id] = {
                                        'score': total_score,
                                        'max_score': max_score,
                                        'date': max(eval.created_at for eval in evaluations),
                                        'type': 'conference',
                                        'evaluations': evaluations,
                                        'score_source': 'manual'
                                    }
                                else:
                                    student_scores[student.id][activity_id] = {
                                        'score': None,
                                        'max_score': activity['max_score'],
                                        'type': 'conference',
                                        'evaluations': [],
                                        'score_source': 'manual'
                                    }
                            
                        except Exception as e:
                            logger.error(f"Error processing activity {activity_id} for student {student.id}: {str(e)}", exc_info=True)
                            student_scores[student.id][activity_id] = {
                                'score': None,
                                'max_score': activity.get('max_score', 0),
                                'type': activity_type,
                                'error': str(e),
                                'score_source': 'error'
                            }
                
                except Exception as e:
                    logger.error(f"Error processing student {student.id}: {str(e)}", exc_info=True)
                    student_scores[student.id] = {}
            
            return student_scores
            
        except Exception as e:
            logger.error(f"Error in pre_calculate_student_scores: {str(e)}", exc_info=True)
            return {}
    
    return score_data
