from django import template
from core.utils.type_guards import safe_get_float, safe_get_int

register = template.Library()

@register.simple_tag
def get_grade(grades, student_id, assignment_id):
    """
    Template tag to get the grade for a specific student-assignment pair.
    Usage: {% get_grade grades student.id assignment.id as grade %}
    Returns the most recent grade if duplicates exist.
    """
    try:
        # Convert to correct types if needed
        student_id = int(student_id)
        assignment_id = int(assignment_id)
        
        # Track the most recent grade
        most_recent_grade = None
        most_recent_date = None
        
        # Find all matching grades and keep the most recent one
        for grade in grades:
            if grade.student_id == student_id and grade.assignment_id == assignment_id:
                # If this is the first match or it's more recent than what we have
                if most_recent_grade is None or grade.updated_at > most_recent_date:
                    most_recent_grade = grade
                    most_recent_date = grade.updated_at
        
        return most_recent_grade
    except (ValueError, AttributeError, TypeError):
        return None

@register.simple_tag
def get_quiz_attempt(quiz_attempts, student_id, quiz_id):
    """
    Template tag to get the quiz attempt for a specific student-quiz pair.
    Usage: {% get_quiz_attempt quiz_attempts student.id quiz.id as attempt %}
    Returns the most recent attempt if duplicates exist.
    """
    try:
        # Convert to correct types if needed
        student_id = int(student_id)
        quiz_id = int(quiz_id)
        
        # Track the most recent attempt
        most_recent_attempt = None
        most_recent_date = None
        
        # Find all matching attempts and keep the most recent one
        for attempt in quiz_attempts:
            if attempt.user_id == student_id and attempt.quiz_id == quiz_id:
                # If this is the first match or it's more recent than what we have
                attempt_date = attempt.end_time or attempt.start_time
                if most_recent_attempt is None or attempt_date > most_recent_date:
                    most_recent_attempt = attempt
                    most_recent_date = attempt_date
        
        return most_recent_attempt
    except (ValueError, AttributeError, TypeError):
        return None

@register.filter
def filter_grade(grades, args):
    """
    Filter to get the grade for a specific student-assignment pair.
    Usage: {{ grades|filter_grade:student,assignment }}
    """
    try:
        # Split the args on comma
        if isinstance(args, str):
            args_parts = args.split(',')
            if len(args_parts) != 2:
                return None
            student_id, assignment_id = args_parts
            
            # Convert to integers if needed
            try:
                student_id = int(student_id)
                assignment_id = int(assignment_id)
            except (ValueError, TypeError):
                return None
                
            # Find the matching grade
            for grade in grades:
                if grade.student_id == student_id and grade.assignment_id == assignment_id:
                    return grade
        else:
            # Handle tuple/list input
            student, assignment = args
            for grade in grades:
                if grade.student_id == student.id and grade.assignment_id == assignment.id:
                    return grade
        return None
    except (ValueError, AttributeError, TypeError) as e:
        return None 

@register.filter
def mul(value, arg):
    """
    Multiplies the value by the argument
    Usage: {{ value|mul:arg }}
    """
    try:
        val = safe_get_float({'val': value}, 'val', 0.0)
        arg_val = safe_get_float({'arg': arg}, 'arg', 0.0)
        return val * arg_val
    except (ValueError, TypeError):
        return 0

@register.filter
def get_item(dictionary, key):
    """
    Gets an item from a dictionary using a key
    Usage: {{ dictionary|get_item:key }}
    """
    try:
        if isinstance(dictionary, dict):
            return dictionary.get(key)
        else:
            return None
    except (TypeError, AttributeError):
        return None


@register.simple_tag
def get_activity_score(activity, student_id, grades, quiz_attempts):
    """
    Get the score data for a specific activity and student
    Usage: {% get_activity_score activity student.id grades quiz_attempts as score_data %}
    """
    try:
        from decimal import Decimal
        student_id = int(student_id)
        
        if activity['type'] == 'assignment':
            # Look for assignment grade for this student and assignment
            for grade in grades:
                if grade.student_id == student_id and grade.assignment_id == activity['object'].id:
                    # Check if grade is excused
                    if getattr(grade, 'excused', False):
                        return {
                            'score': None,
                            'max_score': activity['max_score'],
                            'excused': True,
                            'date': grade.updated_at,
                            'type': 'assignment',
                            'object': activity['object'],
                            'submission': grade.submission
                        }
                    else:
                        # Check if submission is late for graded assignments too
                        is_late = False
                        assignment = activity['object']
                        if grade.submission and assignment.due_date and grade.submission.submitted_at:
                            is_late = grade.submission.submitted_at > assignment.due_date
                        
                        return {
                            'score': grade.score,
                            'max_score': activity['max_score'],
                            'date': grade.updated_at,
                            'type': 'assignment',
                            'object': activity['object'],
                            'submission': grade.submission,
                            'is_late': is_late
                        }
            
            # If no Grade record found, check for AssignmentSubmission directly
            from assignments.models import AssignmentSubmission
            submission = AssignmentSubmission.objects.filter(
                assignment=activity['object'],
                user_id=student_id
            ).order_by('-submitted_at').first()
            
            if submission:
                # Check if submission is late by comparing with assignment due date
                is_late = False
                assignment = activity['object']
                if assignment.due_date and submission.submitted_at:
                    is_late = submission.submitted_at > assignment.due_date
                
                # Update status to include late if applicable
                status = submission.status
                if is_late and status not in ['returned', 'excused'] and submission.grade is not None:
                    status = 'late'
                
                # Return submission data even if not graded yet
                return {
                    'score': submission.grade,  # May be None if not graded
                    'max_score': activity['max_score'],
                    'date': submission.submitted_at,
                    'type': 'assignment',
                    'object': activity['object'],
                    'submission': submission,
                    'status': status,
                    'is_late': is_late
                }
            
            return {'score': None, 'max_score': activity['max_score'], 'type': 'assignment', 'object': activity['object']}
            
        elif activity['type'] == 'quiz':
            # Look for quiz attempt for this student and quiz
            latest_attempt = None
            for attempt in quiz_attempts:
                if attempt.user_id == student_id and attempt.quiz_id == activity['object'].id:
                    if latest_attempt is None or (attempt.end_time or attempt.start_time) > (latest_attempt.end_time or latest_attempt.start_time):
                        latest_attempt = attempt
            
            if latest_attempt:
                # Check if quiz has a rubric and if there's a rubric evaluation
                quiz = activity['object']
                final_score = latest_attempt.score
                score_source = 'auto'  # Default to auto calculation
                max_score = activity['max_score']
                
                if quiz.rubric:
                    try:
                        # Import here to avoid circular imports
                        from quiz.models import QuizRubricEvaluation
                        
                        # Check if there's a rubric evaluation for this attempt
                        rubric_evaluations = QuizRubricEvaluation.objects.filter(
                            quiz_attempt=latest_attempt
                        )
                        
                        if rubric_evaluations.exists():
                            # Calculate total rubric score (convert float to Decimal for consistency)
                            rubric_total = sum(Decimal(str(evaluation.points)) for evaluation in rubric_evaluations)
                            final_score = rubric_total
                            score_source = 'rubric'
                            # Use rubric total_points as max_score when rubric evaluation exists
                            max_score = quiz.rubric.total_points
                    except Exception as e:
                        # If there's any error getting rubric evaluation, fall back to auto score
                        pass
                else:
                    # For non-rubric quizzes, latest_attempt.score is a percentage (0-100)
                    # Keep as percentage for consistent display
                    final_score = latest_attempt.score
                    max_score = 100
                
                return {
                    'score': final_score,
                    'max_score': max_score,
                    'date': latest_attempt.end_time or latest_attempt.start_time,
                    'type': 'quiz',
                    'object': activity['object'],
                    'attempt': latest_attempt,
                    'score_source': score_source  # Track whether it's from rubric or auto calculation
                }
            return {'score': None, 'max_score': activity['max_score'], 'type': 'quiz', 'object': activity['object']}
            
        elif activity['type'] == 'discussion':
            # Check for discussion rubric evaluations
            discussion = activity['object']
            max_score = discussion.rubric.total_points if discussion.rubric else 0
            
            if discussion.rubric:
                try:
                    # Import here to avoid circular imports
                    from lms_rubrics.models import RubricEvaluation
                    
                    # Get all rubric evaluations for this discussion and student
                    evaluations = RubricEvaluation.objects.filter(
                        discussion=discussion,
                        student_id=student_id
                    ).select_related('criterion')
                    
                    if evaluations.exists():
                        # Calculate total score from rubric evaluations
                        total_score = sum(evaluation.points for evaluation in evaluations)
                        latest_evaluation = evaluations.order_by('-created_at').first()
                        
                        return {
                            'score': total_score,
                            'max_score': max_score,
                            'date': latest_evaluation.created_at,
                            'type': 'discussion',
                            'object': discussion,
                            'evaluations': evaluations
                        }
                except Exception:
                    # If there's any error getting discussion evaluations, fall back to no score
                    pass
            
            return {
                'score': None,
                'max_score': max_score,
                'type': 'discussion',
                'object': discussion
            }
            
        elif activity['type'] == 'conference':
            # Check for conference rubric evaluations
            conference = activity['object']
            max_score = conference.rubric.total_points if conference.rubric else 0
            
            if conference.rubric:
                try:
                    # Import here to avoid circular imports
                    from conferences.models import ConferenceRubricEvaluation, ConferenceAttendance
                    
                    # Get the attendance record for this student and conference
                    attendance = ConferenceAttendance.objects.filter(
                        conference=conference,
                        user_id=student_id
                    ).first()
                    
                    if attendance:
                        # Get all rubric evaluations for this attendance
                        evaluations = ConferenceRubricEvaluation.objects.filter(
                            conference=conference,
                            attendance=attendance
                        ).select_related('criterion')
                        
                        if evaluations.exists():
                            # Calculate total score from rubric evaluations
                            total_score = sum(evaluation.points for evaluation in evaluations)
                            latest_evaluation = evaluations.order_by('-created_at').first()
                            
                            return {
                                'score': total_score,
                                'max_score': max_score,
                                'date': latest_evaluation.created_at,
                                'type': 'conference',
                                'object': conference,
                                'attendance': attendance,
                                'evaluations': evaluations
                            }
                except Exception:
                    # If there's any error getting conference evaluations, fall back to no score
                    pass
            
            return {
                'score': None,
                'max_score': max_score,
                'type': 'conference',
                'object': conference
            }
        
        elif activity['type'] == 'scorm':
            # Get SCORM score from TopicProgress
            from courses.models import TopicProgress
            from core.utils.scoring import ScoreCalculationService
            
            topic = activity['object']
            try:
                progress = TopicProgress.objects.filter(
                    user_id=student_id,
                    topic=topic
                ).first()
                
                if progress:
                    progress_data = progress.progress_data or {}
                    scorm_score = progress_data.get('scorm_score', progress.last_score)
                    scorm_max_score = progress_data.get('scorm_max_score', activity.get('max_score', 100))
                    
                    # Check if this is a quiz-based SCORM (has meaningful score) or content-only
                    # Only treat as quiz-based if score is not None AND not zero
                    has_meaningful_score = (progress.last_score is not None and 
                                          float(progress.last_score if progress.last_score is not None else 0) > 0)
                    
                    if has_meaningful_score:
                        # Quiz-based SCORM - return score
                        normalized_score = ScoreCalculationService.normalize_score(scorm_score)
                        
                        return {
                            'score': float(normalized_score) if normalized_score is not None else float(scorm_score),
                            'max_score': float(scorm_max_score) if scorm_max_score else activity.get('max_score', 100),
                            'date': progress.completed_at or progress.last_accessed,
                            'type': 'scorm',
                            'object': topic,
                            'completed': progress.completed,
                            'can_resume': bool(progress.bookmark)
                        }
                    else:
                        # Content-only SCORM - return completion status only
                        return {
                            'score': None,
                            'max_score': activity.get('max_score', 100),
                            'date': progress.completed_at or progress.last_accessed,
                            'type': 'scorm',
                            'object': topic,
                            'completed': progress.completed,
                            'can_resume': bool(progress.bookmark)
                        }
            except Exception:
                pass
            
            return {
                'score': None,
                'max_score': activity.get('max_score', 100),
                'type': 'scorm',
                'object': activity['object'],
                'completed': False,
                'can_resume': False
            }
            
    except (ValueError, AttributeError, TypeError):
        return {'score': None, 'max_score': 0, 'type': 'unknown'}

@register.simple_tag
def calculate_student_total(student_id, activities, grades, quiz_attempts):
    """
    Calculate total score for a student across all activities
    Usage: {% calculate_student_total student.id activities grades quiz_attempts as total_data %}
    Uses only the latest submission/attempt for each activity
    """
    try:
        from decimal import Decimal
        student_id = int(student_id)
        total_earned = Decimal('0')
        total_possible = Decimal('0')  # Changed to Decimal for consistent precision
        
        for activity in activities:
            if activity['max_score'] > 0:  # Only count activities with scores
                # Convert to Decimal for consistent precision
                activity_max_score = Decimal(str(activity['max_score']))
                
                if activity['type'] == 'assignment':
                    # For assignments, use activity max_score as is
                    total_possible += activity_max_score
                    
                    # Look for all assignment grades for this student and assignment
                    matching_grades = []
                    for grade in grades:
                        if grade.student_id == student_id and grade.assignment_id == activity['object'].id:
                            matching_grades.append(grade)
                    
                    # Use the most recent grade if available
                    if matching_grades:
                        latest_grade = max(matching_grades, key=lambda g: g.updated_at)
                        if latest_grade.score is not None and not getattr(latest_grade, 'excused', False):
                            total_earned += Decimal(str(latest_grade.score))
                            
                elif activity['type'] == 'quiz':
                    # Look for all quiz attempts for this student and quiz
                    matching_attempts = []
                    for attempt in quiz_attempts:
                        if attempt.user_id == student_id and attempt.quiz_id == activity['object'].id:
                            matching_attempts.append(attempt)
                    
                    # Use the most recent attempt if available
                    if matching_attempts:
                        latest_attempt = max(matching_attempts, key=lambda a: a.end_time or a.start_time)
                        if latest_attempt.score is not None:
                            # Check if quiz has a rubric and if there's a rubric evaluation
                            quiz = activity['object']
                            final_score = Decimal(str(latest_attempt.score))
                            quiz_max_score = activity_max_score
                            
                            if quiz.rubric:
                                try:
                                    # Import here to avoid circular imports
                                    from quiz.models import QuizRubricEvaluation
                                    
                                    # Check if there's a rubric evaluation for this attempt
                                    rubric_evaluations = QuizRubricEvaluation.objects.filter(
                                        quiz_attempt=latest_attempt
                                    )
                                    
                                    if rubric_evaluations.exists():
                                        # Calculate total rubric score (convert float to Decimal for consistency)
                                        rubric_total = sum(Decimal(str(evaluation.points)) for evaluation in rubric_evaluations)
                                        final_score = rubric_total
                                        # Use rubric total_points as max_score when rubric evaluation exists
                                        quiz_max_score = Decimal(str(quiz.rubric.total_points))
                                except Exception:
                                    # If there's any error getting rubric evaluation, fall back to auto score
                                    pass
                            else:
                                # For non-rubric quizzes, latest_attempt.score is a percentage
                                # Convert percentage to points based on quiz total_points
                                if quiz.total_points and quiz.total_points > 0:
                                    final_score = (Decimal(str(latest_attempt.score)) * Decimal(str(quiz.total_points))) / Decimal('100')
                                    quiz_max_score = Decimal(str(quiz.total_points))
                                else:
                                    # Fallback: treat as percentage-based scoring
                                    final_score = Decimal(str(latest_attempt.score))
                                    quiz_max_score = Decimal('100')
                            
                            total_earned += final_score
                            total_possible += quiz_max_score
                    else:
                        # No attempt found, just add the max score to total_possible
                        total_possible += activity_max_score
                            
                elif activity['type'] == 'discussion':
                    # Look for discussion rubric evaluations
                    discussion = activity['object']
                    
                    if discussion.rubric:
                        try:
                            # Import here to avoid circular imports
                            from lms_rubrics.models import RubricEvaluation
                            
                            # Get all rubric evaluations for this discussion and student
                            evaluations = RubricEvaluation.objects.filter(
                                discussion=discussion,
                                student_id=student_id
                            )
                            
                            if evaluations.exists():
                                # Calculate total score from rubric evaluations
                                total_score = sum(Decimal(str(evaluation.points)) for evaluation in evaluations)
                                total_earned += total_score
                        except Exception:
                            # If there's any error getting discussion evaluations, continue without adding to total
                            pass
                    
                    # Add total possible points for discussion
                    total_possible += activity_max_score
                    
                elif activity['type'] == 'conference':
                    # Look for conference rubric evaluations
                    conference = activity['object']
                    
                    if conference.rubric:
                        try:
                            # Import here to avoid circular imports
                            from conferences.models import ConferenceRubricEvaluation, ConferenceAttendance
                            
                            # Get the attendance record for this student and conference
                            attendance = ConferenceAttendance.objects.filter(
                                conference=conference,
                                user_id=student_id
                            ).first()
                            
                            if attendance:
                                # Get all rubric evaluations for this attendance
                                evaluations = ConferenceRubricEvaluation.objects.filter(
                                    conference=conference,
                                    attendance=attendance
                                )
                                
                                if evaluations.exists():
                                    # Calculate total score from rubric evaluations
                                    total_score = sum(Decimal(str(evaluation.points)) for evaluation in evaluations)
                                    total_earned += total_score
                        except Exception:
                            # If there's any error getting conference evaluations, continue without adding to total
                            pass
                    
                    # Add total possible points for conference
                    total_possible += activity_max_score
                
                elif activity['type'] == 'scorm':
                    # Handle SCORM topics
                    from courses.models import TopicProgress
                    from core.utils.scoring import ScoreCalculationService
                    
                    topic = activity['object']
                    
                    try:
                        progress = TopicProgress.objects.filter(
                            user_id=student_id,
                            topic=topic
                        ).first()
                        
                        # Only count SCORM in total if it has a meaningful score (quiz-based)
                        has_meaningful_score = (progress and progress.last_score is not None and 
                                              float(progress.last_score if progress.last_score is not None else 0) > 0)
                        
                        if has_meaningful_score:
                            # Quiz-based SCORM - count in total
                            total_possible += activity_max_score
                            
                            progress_data = progress.progress_data or {}
                            scorm_score = progress_data.get('scorm_score', progress.last_score)
                            scorm_max_score = progress_data.get('scorm_max_score', activity.get('max_score', 100))
                            
                            # Normalize score
                            normalized_score = ScoreCalculationService.normalize_score(scorm_score)
                            
                            if normalized_score is not None:
                                total_earned += Decimal(str(normalized_score))
                            else:
                                total_earned += Decimal(str(scorm_score))
                        # else: Content-only SCORM - don't count in total points
                    except Exception:
                        # If error, just don't add to earned or possible
                        pass
                            
                else:
                    # For any other activity types, just add the max_score to total_possible
                    total_possible += activity_max_score
        
        # Calculate percentage with proper precision
        percentage = round((total_earned / total_possible * 100), 1) if total_possible > 0 else Decimal('0')
        
        return {
            'earned': round(float(total_earned), 1),  # Round to one decimal place for display
            'possible': round(float(total_possible), 1),  # Round to one decimal place for display
            'percentage': round(float(percentage), 1)  # Round to one decimal place
        }
        
    except (ValueError, AttributeError, TypeError) as e:
        import logging
        logging.error(f"Error in calculate_student_total: {str(e)}")
        return {'earned': 0, 'possible': 0, 'percentage': 0}


@register.simple_tag
def course_has_activities(course, activity_type, assignments=None, quizzes=None, quiz_attempts=None, discussions=None, conferences=None):
    """
    Check if a course has activities of a specific type
    MODIFIED: Always show activities if they exist in the course, regardless of student interaction
    Usage: {% course_has_activities course 'assignment' assignments=assignments %}
    Usage: {% course_has_activities course 'quiz' quizzes=quizzes %}
    """
    try:
        if activity_type == 'assignment' and assignments:
            return any(assignment.course and assignment.course.id == course.id for assignment in assignments)
        elif activity_type == 'quiz' and quizzes:
            # Always check for quiz existence first, regardless of attempts
            return any(quiz.course and quiz.course.id == course.id for quiz in quizzes)
        elif activity_type == 'scorm':
            # Check for SCORM topics in the course
            from courses.models import Topic
            return Topic.objects.filter(
                content_type='SCORM',
                scorm__isnull=False,
                courses=course
            ).exists()
        elif activity_type == 'discussion' and discussions:
            return any(discussion.course and discussion.course.id == course.id and discussion.rubric for discussion in discussions)
        elif activity_type == 'conference' and conferences:
            return any(conference.course and conference.course.id == course.id and conference.rubric for conference in conferences)
        return False
    except Exception:
        return False

@register.simple_tag
def should_hide_course(student_id, course_id, student_courses_with_activities, user_role=None):
    """
    Check if a course should be hidden for a student
    MODIFIED: Always show all courses regardless of activity status to display non-started activities
    Usage: {% should_hide_course student.id course.id student_courses_with_activities user.role as hide_course %}
    """
    try:
        # Always show all courses - never hide based on activities
        # This ensures non-started activities are visible for all users
        return False
    except (ValueError, TypeError, AttributeError):
        return False 


@register.simple_tag
def get_activity_status(activity, user_id):
    """
    Helper function to determine the status of an activity for a given user.
    Returns one of: not_started, in_progress, submitted, completed, graded, returned, missing, participated, attended, absent, registered
    """
    try:
        from assignments.models import AssignmentSubmission
        from quiz.models import QuizAttempt
        from discussions.models import Comment
        from conferences.models import ConferenceAttendance
        
        user_id = int(user_id)
        activity_type = activity.get('type')
        activity_obj = activity.get('object')
        
        if activity_type == 'assignment':
            submission = AssignmentSubmission.objects.filter(
                assignment=activity_obj,
                user_id=user_id
            ).first()
            
            if submission:
                if submission.status == 'returned':
                    return "returned"
                elif submission.status == 'missing':
                    return "missing"
                elif submission.grade is not None:
                    return "graded"
                elif submission.status in ['submitted', 'not_graded']:
                    # Both 'submitted' and 'not_graded' represent submitted work
                    return "submitted"
                else:
                    return "submitted"
            else:
                return "not_started"
                
        elif activity_type == 'quiz':
            attempt = QuizAttempt.objects.filter(
                quiz=activity_obj,
                user_id=user_id,
                is_completed=True
            ).order_by('-end_time').first()
            
            if attempt:
                return "completed"
            else:
                return "not_started"
                
        elif activity_type == 'conference':
            # Check for conference attendance
            try:
                from conferences.models import ConferenceRubricEvaluation
                
                attendance = ConferenceAttendance.objects.filter(
                    conference=activity_obj,
                    user_id=user_id
                ).first()
                
                if attendance:
                    # Check if there are rubric evaluations for this attendance
                    if activity_obj.rubric:
                        evaluations = ConferenceRubricEvaluation.objects.filter(
                            conference=activity_obj,
                            attendance=attendance
                        ).exists()
                        
                        if evaluations:
                            return "graded"
                        else:
                            return "attended"
                    else:
                        return "attended"
                else:
                    return "not_started"
            except Exception:
                return "not_started"
                
        # Add other activity types as needed
        return "not_started"
        
    except Exception:
        return "not_started"

@register.simple_tag
def has_feedback_available(activity, student_id):
    """
    Check if feedback is available for an activity and student
    Usage: {% has_feedback_available activity student.id as has_feedback %}
    """
    try:
        student_id = int(student_id)
        
        if activity['type'] == 'assignment':
            from assignments.models import AssignmentSubmission, AssignmentFeedback
            
            submission = AssignmentSubmission.objects.filter(
                assignment=activity['object'],
                user_id=student_id
            ).order_by('-submitted_at').first()
            
            if submission:
                # Check for overall feedback
                has_overall_feedback = AssignmentFeedback.objects.filter(
                    submission=submission
                ).exists()
                
                # Check for rubric evaluations
                has_rubric_feedback = False
                if activity['object'].rubric:
                    from lms_rubrics.models import RubricEvaluation
                    has_rubric_feedback = RubricEvaluation.objects.filter(
                        assignment_submission=submission
                    ).exists()
                
                # Check for question-specific iteration feedback
                has_question_feedback = False
                from assignments.models import TextQuestionAnswerIteration, TextQuestionIterationFeedback
                question_iterations = TextQuestionAnswerIteration.objects.filter(submission=submission)
                for iteration in question_iterations:
                    if TextQuestionIterationFeedback.objects.filter(iteration=iteration).exists():
                        has_question_feedback = True
                        break
                
                # Check if graded (has a grade)
                has_grade = submission.grade is not None
                
                return has_overall_feedback or has_rubric_feedback or has_question_feedback or has_grade
            
            return False
            
        elif activity['type'] == 'quiz':
            from quiz.models import QuizAttempt
            
            attempt = QuizAttempt.objects.filter(
                quiz=activity['object'],
                user_id=student_id,
                is_completed=True
            ).order_by('-end_time').first()
            
            if attempt:
                # Check for overall feedback text
                has_text_feedback = bool(attempt.feedback)
                
                # Check for rubric evaluations
                has_rubric_feedback = False
                if activity['object'].rubric:
                    has_rubric_feedback = attempt.rubric_evaluations.exists()
                
                # Check if scored
                has_score = attempt.score is not None
                
                return has_text_feedback or has_rubric_feedback or has_score
            
            return False
            
        elif activity['type'] == 'conference':
            # Check for conference rubric evaluations
            conference = activity['object']
            
            if conference.rubric:
                try:
                    from conferences.models import ConferenceRubricEvaluation, ConferenceAttendance
                    
                    # Get the attendance record for this student and conference
                    attendance = ConferenceAttendance.objects.filter(
                        conference=conference,
                        user_id=student_id
                    ).first()
                    
                    if attendance:
                        # Check for rubric evaluations
                        has_rubric_evaluations = ConferenceRubricEvaluation.objects.filter(
                            conference=conference,
                            attendance=attendance
                        ).exists()
                        
                        return has_rubric_evaluations
                except Exception:
                    pass
            
            return False
            
    except Exception:
        return False
    
    return False

@register.simple_tag
def get_conference_score(conference, student_id):
    """
    Get conference score for a specific student and conference
    Usage: {% get_conference_score conference student.id as score_data %}
    """
    try:
        student_id = int(student_id)
        max_score = conference.rubric.total_points if conference.rubric else 0
        
        if conference.rubric:
            try:
                # Import here to avoid circular imports
                from conferences.models import ConferenceRubricEvaluation, ConferenceAttendance
                
                # Get the attendance record for this student and conference
                attendance = ConferenceAttendance.objects.filter(
                    conference=conference,
                    user_id=student_id
                ).first()
                
                if attendance:
                    # Get all rubric evaluations for this attendance
                    evaluations = ConferenceRubricEvaluation.objects.filter(
                        conference=conference,
                        attendance=attendance
                    ).select_related('criterion')
                    
                    if evaluations.exists():
                        # Calculate total score from rubric evaluations
                        total_score = sum(evaluation.points for evaluation in evaluations)
                        latest_evaluation = evaluations.order_by('-created_at').first()
                        
                        return {
                            'score': total_score,
                            'max_score': max_score,
                            'date': latest_evaluation.created_at,
                            'type': 'conference',
                            'object': conference,
                            'attendance': attendance,
                            'evaluations': evaluations
                        }
            except Exception:
                # If there's any error getting conference evaluations, fall back to no score
                pass
        
        return {
            'score': None,
            'max_score': max_score,
            'type': 'conference',
            'object': conference
        }
        
    except (ValueError, AttributeError, TypeError):
        return {
            'score': None,
            'max_score': 0,
            'type': 'conference',
            'object': conference
        }

@register.simple_tag
def has_student_participation(activity, student_id):
    """
    Check if a student has participated in an activity (discussion or conference).
    
    Args:
        activity: Dictionary containing activity data
        student_id: Student ID to check
    
    Returns:
        Boolean indicating if student has participated
    """
    try:
        student_id = int(student_id)
        activity_type = activity.get('type')
        activity_obj = activity.get('object')
        
        if activity_type == 'discussion':
            # Check if student has made any comments on the discussion
            from discussions.models import Comment
            return Comment.objects.filter(
                discussion=activity_obj,
                created_by_id=student_id
            ).exists()
            
        elif activity_type == 'conference':
            # Check if student has any attendance record for the conference
            from conferences.models import ConferenceAttendance
            return ConferenceAttendance.objects.filter(
                conference=activity_obj,
                user_id=student_id
            ).exists()
            
        return False  # For other activity types, assume participation check not needed
        
    except (ValueError, AttributeError, TypeError):
        return False

@register.simple_tag
def get_participation_status(activity, student_id):
    """
    Get detailed participation status for a student in an activity.
    
    Args:
        activity: Dictionary containing activity data
        student_id: Student ID to check
    
    Returns:
        String indicating participation status
    """
    try:
        student_id = int(student_id)
        activity_type = activity.get('type')
        activity_obj = activity.get('object')
        
        if activity_type == 'discussion':
            # Check comments made by the student
            from discussions.models import Comment
            comments = Comment.objects.filter(
                discussion=activity_obj,
                created_by_id=student_id
            )
            
            if comments.exists():
                comment_count = comments.count()
                return f"{comment_count} comment{'s' if comment_count != 1 else ''}"
            else:
                return "No interaction"
                
        elif activity_type == 'conference':
            # Check attendance for the conference
            from conferences.models import ConferenceAttendance
            attendance = ConferenceAttendance.objects.filter(
                conference=activity_obj,
                user_id=student_id
            ).first()
            
            if attendance:
                if attendance.attendance_status == 'present':
                    if attendance.duration_minutes:
                        return f"Attended ({attendance.duration_minutes} min)"
                    else:
                        return "Attended"
                elif attendance.attendance_status == 'late':
                    return "Attended (Late)"
                elif attendance.attendance_status == 'left_early':
                    return "Left Early"
                else:
                    return "Registered"
            else:
                return "No attendance"
                
        return "Unknown"
        
    except (ValueError, AttributeError, TypeError):
        return "Unknown"

@register.simple_tag
def get_student_activity_score(student_scores, student_id, activity_id):
    """
    Get pre-calculated score data for a specific student-activity pair.
    Usage: {% get_student_activity_score student_scores student.id activity.object.id as score_data %}
    """
    try:
        student_id = int(student_id)
        
        # Handle both integer and UUID activity IDs
        if isinstance(activity_id, str):
            # Try to convert to int first, if that fails, use as string (for UUIDs)
            try:
                activity_id = int(activity_id)
            except ValueError:
                # Keep as string for UUIDs
                pass
        
        if student_id in student_scores and activity_id in student_scores[student_id]:
            return student_scores[student_id][activity_id]
        
        return {'score': None, 'max_score': 0, 'type': 'unknown'}
    except (ValueError, TypeError, KeyError):
        return {'score': None, 'max_score': 0, 'type': 'unknown'}

@register.simple_tag
def calculate_student_total_optimized(student_scores, student_id, activities):
    """
    Calculate student total using pre-calculated scores.
    Usage: {% calculate_student_total_optimized student_scores student.id activities as total_data %}
    """
    try:
        from decimal import Decimal
        
        student_id = int(student_id)
        total_earned = Decimal('0')
        total_possible = Decimal('0')
        
        if student_id in student_scores:
            for activity in activities:
                activity_id = activity['object'].id
                if activity_id in student_scores[student_id]:
                    score_data = student_scores[student_id][activity_id]
                    
                    # Skip initial assessments as they are informational only
                    if score_data.get('is_informational', False):
                        continue
                    
                    # Add to possible points
                    if score_data.get('max_score', 0) > 0:
                        total_possible += Decimal(str(score_data['max_score']))
                    
                    # Add to earned points if score exists and not excused
                    if score_data.get('score') is not None and not score_data.get('excused', False):
                        total_earned += Decimal(str(score_data['score']))
                    # Also count completed activities even without scores
                    elif (score_data.get('completed', False) or 
                          score_data.get('completion_status') == 'completed' or 
                          score_data.get('success_status') == 'passed') and not score_data.get('excused', False):
                        # Award full points for completed activities without scores
                        total_earned += Decimal(str(score_data.get('max_score', 0)))
        
        # Calculate percentage with proper decimal precision
        if total_possible > 0:
            percentage = round((total_earned / total_possible) * 100, 1)
        else:
            percentage = 0
        
        return {
            'earned': total_earned,
            'possible': total_possible,
            'percentage': percentage
        }
    except (ValueError, TypeError, KeyError):
        return {
            'earned': Decimal('0'),
            'possible': Decimal('0'),
            'percentage': 0
        }

@register.simple_tag
def get_score_display_class(score, max_score):
    """
    Get the CSS class for score display based on percentage.
    Usage: {% get_score_display_class score max_score %}
    """
    if not score or not max_score or max_score == 0:
        return 'grade-none'
    
    percentage = round((score / max_score) * 100)
    
    if percentage >= 90:
        return 'grade-excellent'
    elif percentage >= 80:
        return 'grade-good'
    elif percentage >= 70:
        return 'grade-average'
    else:
        return 'grade-poor'

@register.simple_tag
def format_score_display(score, max_score):
    """
    Format score for display.
    Usage: {% format_score_display score max_score %}
    """
    if score is not None and max_score is not None:
        return f"{score:.1f}/{max_score:.1f}"
    return "Not graded"

@register.simple_tag
def get_activity_type_label(activity_type):
    """
    Get the short label for an activity type.
    Usage: {% get_activity_type_label activity.type %}
    """
    labels = {
        'assignment': 'ASG',
        'quiz': 'QUZ',
        'discussion': 'DSC',
        'conference': 'CNF',
        'scorm': 'SCM',
    }
    return labels.get(activity_type, 'UNK')

@register.simple_tag
def should_show_grade_buttons(user_role):
    """
    Check if grade buttons should be shown for the user.
    Usage: {% should_show_grade_buttons user.role %}
    """
    return user_role != 'learner'

@register.simple_tag
def get_activity_status_text(activity_type, score_data):
    """
    Get status text for an activity based on its type and score data.
    Usage: {% get_activity_status_text activity.type score_data %}
    """
    if activity_type == 'assignment':
        if score_data.get('excused'):
            return 'Excused'
        elif score_data.get('score') is not None:
            return 'Graded'
        elif score_data.get('submission'):
            submission = score_data['submission']
            status = submission.status
            if status == 'submitted':
                return 'Submitted - Awaiting Grade'
            elif status == 'not_graded':
                return 'Submitted - Awaiting Grade'
            elif status == 'returned':
                return 'Returned for Revision'
            elif status == 'draft':
                return 'Draft'
            elif status == 'late':
                return 'Late Submission'
            else:
                return 'Submitted'
        else:
            return 'Not Started'
    
    elif activity_type == 'quiz':
        if score_data.get('score') is not None:
            return 'Completed'
        else:
            return 'Not Attempted'
    
    elif activity_type in ['discussion', 'conference']:
        if score_data.get('score') is not None:
            return 'Evaluated'
        else:
            return 'Not Evaluated'
    
    elif activity_type == 'scorm':
        if score_data.get('completed'):
            return 'Completed'
        elif score_data.get('score') is not None:
            return 'In Progress'
        else:
            return 'Not Started'
    
    return 'Unknown'