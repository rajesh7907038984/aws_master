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
def get_activity_best_score(activity, student_id, grades, quiz_attempts):
    """
    Get the BEST score data for a specific activity and student (highest score achieved)
    Usage: {% get_activity_best_score activity student.id grades quiz_attempts removed_registrations as score_data %}
    """
    try:
        from decimal import Decimal
        student_id = int(student_id)
        
        if activity['type'] == 'assignment':
            # Look for assignment grade for this student and assignment
            best_grade = None
            best_score = None
            
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
                            'submission': grade.submission,
                            'is_best_score': True
                        }
                    else:
                        # Track the best score
                        if grade.score is not None:
                            if best_score is None or grade.score > best_score:
                                best_score = grade.score
                                best_grade = grade
            
            if best_grade:
                # Check if submission is late for graded assignments too
                is_late = False
                assignment = activity['object']
                if best_grade.submission and assignment.due_date and best_grade.submission.submitted_at:
                    is_late = best_grade.submission.submitted_at > assignment.due_date
                
                return {
                    'score': best_grade.score,
                    'max_score': activity['max_score'],
                    'date': best_grade.updated_at,
                    'type': 'assignment',
                    'object': activity['object'],
                    'submission': best_grade.submission,
                    'is_late': is_late,
                    'is_best_score': True
                }
            
            # If no Grade record found, check for AssignmentSubmission directly
            from assignments.models import AssignmentSubmission
            submission = AssignmentSubmission.objects.filter(
                assignment=activity['object'],
                user_id=student_id
            ).order_by('-submitted_at').first()
            
            if submission:
                # Determine submission status
                status = 'submitted'
                is_late = False
                
                if submission.grade is None:
                    status = 'submitted'
                elif submission.grade >= activity['max_score'] * 0.7:  # 70% passing threshold
                    status = 'passed'
                else:
                    status = 'failed'
                
                if submission.submitted_at and activity['object'].due_date:
                    is_late = submission.submitted_at > activity['object'].due_date
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
                    'is_late': is_late,
                    'is_best_score': True
                }
            
            return {'score': None, 'max_score': activity['max_score'], 'type': 'assignment', 'object': activity['object'], 'is_best_score': True}
            
        elif activity['type'] == 'quiz':
            # Look for quiz attempts for this student and quiz - find the BEST score
            best_attempt = None
            best_score = None
            
            for attempt in quiz_attempts:
                if attempt.user_id == student_id and attempt.quiz_id == activity['object'].id:
                    if attempt.score is not None:
                        if best_score is None or attempt.score > best_score:
                            best_score = attempt.score
                            best_attempt = attempt
            
            if best_attempt:
                # Check if quiz has a rubric and if there's a rubric evaluation
                quiz = activity['object']
                final_score = best_attempt.score
                score_source = 'auto'  # Default to auto calculation
                max_score = activity['max_score']
                
                if quiz.rubric:
                    try:
                        # Import here to avoid circular imports
                        from quiz.models import QuizRubricEvaluation
                        
                        # Check if there's a rubric evaluation for this attempt
                        rubric_evaluations = QuizRubricEvaluation.objects.filter(
                            quiz_attempt=best_attempt
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
                    # For non-rubric quizzes, best_attempt.score is a percentage (0-100)
                    # Keep as percentage for consistent display
                    final_score = best_attempt.score
                    max_score = 100
                
                return {
                    'score': final_score,
                    'max_score': max_score,
                    'date': best_attempt.end_time or best_attempt.start_time,
                    'type': 'quiz',
                    'object': activity['object'],
                    'attempt': best_attempt,
                    'score_source': score_source,  # Track whether it's from rubric or auto calculation
                    'is_best_score': True
                }
            return {'score': None, 'max_score': activity['max_score'], 'type': 'quiz', 'object': activity['object'], 'is_best_score': True}
            
        elif activity['type'] == 'discussion':
            # Check for discussion rubric evaluations
            discussion = activity['object']
            max_score = discussion.rubric.total_points if discussion.rubric else 0
            
            if discussion.rubric:
                try:
                    # Import here to avoid circular imports
                    from lms_rubrics.models import RubricEvaluation
                    
                    # Get all evaluations for this student and discussion
                    evaluations = RubricEvaluation.objects.filter(
                        rubric=discussion.rubric,
                        student_id=student_id,
                        content_type__model='discussion',
                        object_id=discussion.id
                    ).order_by('-created_at')
                    
                    if evaluations.exists():
                        total_score = sum(evaluation.points for evaluation in evaluations)
                        latest_evaluation = evaluations.order_by('-created_at').first()
                        
                        return {
                            'score': total_score,
                            'max_score': max_score,
                            'date': latest_evaluation.created_at,
                            'type': 'discussion',
                            'object': discussion,
                            'evaluations': evaluations,
                            'is_best_score': True
                        }
                except Exception as e:
                    # If there's any error getting discussion evaluations, fall back to no score
                    pass
            
            return {
                'score': None,
                'max_score': max_score,
                'type': 'discussion',
                'object': discussion,
                'is_best_score': True
            }
            
        elif activity['type'] == 'conference':
            # Check for conference rubric evaluations
            conference = activity['object']
            max_score = conference.rubric.total_points if conference.rubric else 0
            
            if conference.rubric:
                try:
                    # Import here to avoid circular imports
                    from conferences.models import ConferenceRubricEvaluation, ConferenceAttendance
                    
                    # Check if student attended the conference
                    attendance = ConferenceAttendance.objects.filter(
                        conference=conference,
                        user_id=student_id
                    ).first()
                    
                    if attendance:
                        # Get all evaluations for this student and conference
                        evaluations = ConferenceRubricEvaluation.objects.filter(
                            conference=conference,
                            student_id=student_id
                        ).order_by('-created_at')
                        
                        if evaluations.exists():
                            total_score = sum(evaluation.points for evaluation in evaluations)
                            latest_evaluation = evaluations.order_by('-created_at').first()
                            
                            return {
                                'score': total_score,
                                'max_score': max_score,
                                'date': latest_evaluation.created_at,
                                'type': 'conference',
                                'object': conference,
                                'attendance': attendance,
                                'evaluations': evaluations,
                                'is_best_score': True
                            }
                except Exception as e:
                    # If there's any error getting conference evaluations, fall back to no score
                    pass
            
            return {
                'score': None,
                'max_score': max_score,
                'type': 'conference',
                'object': conference,
                'is_best_score': True
            }
            
        # removed activity type removed
        # removed topic activity type removed
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
            
        # removed activity type removed
        # removed topic activity type removed
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
                            
                # removed activity type removed
        elif activity['type'] == 'removed_topic':
            # Handle removed topics - check TopicProgress for scores
            try:
                from courses.models import TopicProgress
                
                topic_progress = TopicProgress.objects.filter(
                    topic=activity['object'],
                    user_id=student_id
                ).first()
                
                if topic_progress and topic_progress.last_score is not None:
                    # Convert the score (typically 0-100) to a percentage of max_score
                    score_percentage = Decimal(str(topic_progress.last_score)) / Decimal('100')
                    activity_score = score_percentage * activity_max_score
                    
                    # Add to total only if completed or has a passing score
                    if topic_progress.completed or float(topic_progress.last_score) >= 70:
                        total_earned += activity_score
            except Exception:
                pass
            
            # Add total possible points for removed topic
            total_possible += activity_max_score
        
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
def get_removed_registration(removed_registrations, package_id):
    """
    Get the first removed attempt for a specific package (using removedAttempt model)
    Usage: {% get_removed_registration removed_registrations activity.object.id as registration %}
    Note: removed_registrations is actually removed_attempts in the context
    """
    try:
        package_id = int(package_id)
        # removed functionality removed
        return None
    except (ValueError, AttributeError, TypeError):
        return None

@register.simple_tag
def course_has_activities(course, activity_type, assignments=None, quizzes=None, quiz_attempts=None, discussions=None, conferences=None, removed_registrations=None):
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
        elif activity_type == 'discussion' and discussions:
            return any(discussion.course and discussion.course.id == course.id and discussion.rubric for discussion in discussions)
        elif activity_type == 'conference' and conferences:
            return any(conference.course and conference.course.id == course.id and conference.rubric for conference in conferences)
        elif activity_type == 'removed' and removed_registrations:
            # For removed, check if there are any packages available in the course (via topics)
            try:
                from courses.models import Topic
                # Check if the course has any removed topics
                removed_topics = Topic.objects.filter(
                    coursetopic__course=course,
                    content_type='removed'
                )
                return removed_topics.exists()
            except Exception:
                return False
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
def get_removed_registration_for_topic(removed_registrations, student_id, topic_id):
    """
    Get the removed attempt for a specific student and topic (using removedAttempt model)
    Usage: {% get_removed_registration_for_topic removed_registrations student.id topic.id as registration %}
    Note: removed_registrations is actually removed_attempts in the context
    """
    try:
        student_id = int(student_id)
        topic_id = int(topic_id)
        
        # removed functionality removed
        return None
    except (ValueError, AttributeError, TypeError):
        return None 

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
        has_completed_activity = False
        
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
                        has_completed_activity = True
                    # Also count completed activities even without scores (for removed completions)
                    elif (score_data.get('completed', False) or 
                          score_data.get('completion_status') == 'completed' or 
                          score_data.get('success_status') == 'passed') and not score_data.get('excused', False):
                        # Award full points for completed activities without scores
                        total_earned += Decimal(str(score_data.get('max_score', 0)))
                        has_completed_activity = True
        
        # Calculate percentage
        if total_possible > 0:
            percentage = round((total_earned / total_possible) * 100)
        else:
            percentage = 0
        
        return {
            'earned': total_earned,
            'possible': total_possible,
            'percentage': percentage,
            'has_completed_activity': has_completed_activity
        }
    except (ValueError, TypeError, KeyError):
        return {
            'earned': Decimal('0'),
            'possible': Decimal('0'),
            'percentage': 0,
            'has_completed_activity': False
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
        'removed': 'SCO',
        'removed_topic': 'SCO'
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
    
    elif activity_type == 'removed':
        if score_data.get('score') and score_data.get('lesson_status') in ['completed', 'passed']:
            return 'Completed'
        elif score_data.get('attempt'):  # Changed from 'registration' to 'attempt'
            return 'In Progress'
        else:
            return 'Not Started'
    
    return 'Unknown'