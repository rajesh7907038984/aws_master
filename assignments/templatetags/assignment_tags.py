from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to get an item from a dictionary.
    Usage: {{ dictionary|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def get_field_answer(submission, field_id):
    """
    Template filter to get the latest submitted field answer iteration for a specific field from a submission.
    Usage: {{ submission|get_field_answer:field.id }}
    """
    if not submission or not field_id:
        return ""
    
    try:
        # Convert field_id to int if it's a string
        if isinstance(field_id, str) and field_id.isdigit():
            field_id = int(field_id)
        elif not isinstance(field_id, int):
            return ""
            
        # Try to use the prefetched data first (new iteration system)
        if hasattr(submission, '_prefetched_objects_cache') and 'field_answer_iterations' in submission._prefetched_objects_cache:
            # Find the latest submitted iteration for this field
            latest_iteration = None
            for iteration in submission.field_answer_iterations.all():
                if iteration.field.id == field_id and iteration.is_submitted:
                    if latest_iteration is None or iteration.iteration_number > latest_iteration.iteration_number:
                        latest_iteration = iteration
            if latest_iteration:
                return latest_iteration.answer_text
        else:
            # Fallback to database query for iterations
            from assignments.models import TextSubmissionAnswerIteration
            latest_iteration = TextSubmissionAnswerIteration.objects.filter(
                submission=submission, 
                field_id=field_id,
                is_submitted=True
            ).order_by('-iteration_number').first()
            if latest_iteration:
                return latest_iteration.answer_text
            
            # Fallback to old model for backwards compatibility
            from assignments.models import TextSubmissionAnswer
            answer = TextSubmissionAnswer.objects.filter(
                submission=submission, 
                field_id=field_id
            ).first()
            if answer:
                return answer.answer_text
    except Exception as e:
        # Log error for debugging but don't break the template
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_field_answer filter: {e}")
    
    return ""

@register.filter
def get_question_answer(submission, question_id):
    """
    Template filter to get a question answer for a specific question from a submission.
    Usage: {{ submission|get_question_answer:question.id }}
    """
    if not submission or not question_id:
        return ""
    
    try:
        # Convert question_id to int if it's a string
        if isinstance(question_id, str) and question_id.isdigit():
            question_id = int(question_id)
        elif not isinstance(question_id, int):
            return ""
            
        # Try to use the prefetched data first
        if hasattr(submission, '_prefetched_objects_cache') and 'text_answers' in submission._prefetched_objects_cache:
            for answer in submission.text_answers.all():
                if answer.question.id == question_id:
                    return answer.answer_text
        else:
            # Fallback to database query
            from assignments.models import TextQuestionAnswer
            answer = TextQuestionAnswer.objects.filter(
                submission=submission, 
                question_id=question_id
            ).first()
            if answer:
                return answer.answer_text
    except Exception as e:
        # Log error for debugging but don't break the template
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_question_answer filter: {e}")
    
    return ""

@register.filter
def get_text_fields(assignment):
    """
    Template filter to safely get text fields from an assignment.
    Usage: {{ assignment|get_text_fields }}
    """
    try:
        return list(assignment.text_fields.all())
    except Exception:
        return []

@register.filter
def get_field_answers(field):
    """
    Template filter to safely get answers for a field.
    Usage: {{ field|get_field_answers }}
    """
    try:
        return list(field.answers.all())
    except Exception:
        return []

@register.filter
def get_criterion_ratings(criterion):
    """
    Template filter to safely get ratings for a criterion.
    Usage: {{ criterion|get_criterion_ratings }}
    """
    try:
        return list(criterion.ratings.all())
    except Exception:
        return []

@register.filter
def get_attachments(attachments):
    """
    Template filter to safely get attachments.
    Usage: {{ attachments|get_attachments }}
    """
    try:
        if hasattr(attachments, 'all'):
            return list(attachments.all())
        else:
            return list(attachments)
    except Exception:
        return [] 

@register.filter
def get_field_feedback(submission, field_id):
    """
    Template filter to get instructor feedback text for the latest submitted iteration of a specific text submission field.
    Usage: {{ submission|get_field_feedback:field.id }}
    Returns the feedback text (string) or an empty string if none exists.
    """
    if not submission or not field_id:
        return ""

    try:
        # Ensure field_id is an int
        if isinstance(field_id, str) and field_id.isdigit():
            field_id = int(field_id)
        elif not isinstance(field_id, int):
            return ""

        # Find the latest submitted iteration for this field
        latest_iteration = None
        if hasattr(submission, '_prefetched_objects_cache') and 'field_answer_iterations' in submission._prefetched_objects_cache:
            for iteration in submission.field_answer_iterations.all():
                if iteration.field.id == field_id and iteration.is_submitted:
                    if latest_iteration is None or iteration.iteration_number > latest_iteration.iteration_number:
                        latest_iteration = iteration
        else:
            # Fallback DB query for iterations
            from assignments.models import TextSubmissionAnswerIteration
            latest_iteration = TextSubmissionAnswerIteration.objects.filter(
                submission=submission, 
                field_id=field_id,
                is_submitted=True
            ).order_by('-iteration_number').first()
            
            # Fallback to old model for backwards compatibility
            if not latest_iteration:
                from assignments.models import TextSubmissionAnswer
                answer_obj = TextSubmissionAnswer.objects.filter(submission=submission, field_id=field_id).first()
                if answer_obj:
                    # Get the most recent feedback entry from old model
                    feedback_qs = answer_obj.feedback_entries.order_by('-created_at').first()
                    return feedback_qs.feedback_text if feedback_qs and feedback_qs.feedback_text else ""

        if not latest_iteration:
            return ""

        # Get the latest feedback for this iteration
        feedback_qs = None
        if hasattr(latest_iteration, '_prefetched_objects_cache') and 'feedback_entries' in latest_iteration._prefetched_objects_cache:
            feedback_entries = list(latest_iteration.feedback_entries.all())
            feedback_qs = feedback_entries[0] if feedback_entries else None
        else:
            # Get the most recent feedback entry (ordering is by -created_at)
            feedback_qs = latest_iteration.feedback_entries.order_by('-created_at').first()

        return feedback_qs.feedback_text if feedback_qs and feedback_qs.feedback_text else ""
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_field_feedback filter: {e}")
        return ""

@register.filter
def get_question_feedback(submission, question_id):
    """
    Template filter to get instructor feedback text for a specific text question answer.
    Usage: {{ submission|get_question_feedback:question.id }}
    Returns the feedback text (string) or an empty string if none exists.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not submission or not question_id:
        logger.debug(f"get_question_feedback: No submission ({submission}) or question_id ({question_id})")
        return ""

    try:
        # Ensure question_id is an int
        if isinstance(question_id, str) and question_id.isdigit():
            question_id = int(question_id)
        elif not isinstance(question_id, int):
            logger.debug(f"get_question_feedback: Invalid question_id type: {type(question_id)}")
            return ""

        # Attempt to locate the answer via prefetched cache
        answer_obj = None
        if hasattr(submission, '_prefetched_objects_cache') and 'text_answers' in submission._prefetched_objects_cache:
            for ans in submission.text_answers.all():
                if ans.question.id == question_id:
                    answer_obj = ans
                    break
        else:
            from assignments.models import TextQuestionAnswer
            answer_obj = TextQuestionAnswer.objects.filter(submission=submission, question_id=question_id).first()

        if not answer_obj:
            logger.debug(f"get_question_feedback: No answer found for submission {submission.id}, question {question_id}")
            return ""

        # Retrieve latest feedback
        feedback_entry = None
        if hasattr(answer_obj, '_prefetched_objects_cache') and 'feedback_entries' in answer_obj._prefetched_objects_cache:
            feedback_list = list(answer_obj.feedback_entries.all())
            feedback_entry = feedback_list[0] if feedback_list else None
        else:
            feedback_entry = answer_obj.feedback_entries.first()

        if feedback_entry:
            logger.debug(f"get_question_feedback: Found feedback for submission {submission.id}, question {question_id}: {feedback_entry.feedback_text[:50]}...")
            return feedback_entry.feedback_text
        else:
            logger.debug(f"get_question_feedback: No feedback entry found for submission {submission.id}, question {question_id}")
            return ""
    except Exception as e:
        logger.error(f"Error in get_question_feedback filter: {e}")
        return "" 

@register.filter
def get_field_answer_timestamp(submission, field_id):
    """
    Template filter to get the timestamp when the latest field answer iteration was submitted.
    Usage: {{ submission|get_field_answer_timestamp:field.id }}
    """
    if not submission or not field_id:
        return None
    
    try:
        # Convert field_id to int if it's a string
        if isinstance(field_id, str) and field_id.isdigit():
            field_id = int(field_id)
        elif not isinstance(field_id, int):
            return None
            
        # Find the latest submitted iteration for this field
        latest_iteration = None
        if hasattr(submission, '_prefetched_objects_cache') and 'field_answer_iterations' in submission._prefetched_objects_cache:
            for iteration in submission.field_answer_iterations.all():
                if iteration.field.id == field_id and iteration.is_submitted:
                    if latest_iteration is None or iteration.iteration_number > latest_iteration.iteration_number:
                        latest_iteration = iteration
        else:
            # Fallback DB query for iterations
            from assignments.models import TextSubmissionAnswerIteration
            latest_iteration = TextSubmissionAnswerIteration.objects.filter(
                submission=submission, 
                field_id=field_id,
                is_submitted=True
            ).order_by('-iteration_number').first()
            
            # Fallback to old model for backwards compatibility
            if not latest_iteration:
                from assignments.models import TextSubmissionAnswer
                answer = TextSubmissionAnswer.objects.filter(
                    submission=submission, 
                    field_id=field_id
                ).first()
                if answer:
                    return answer.updated_at
        
        if latest_iteration:
            return latest_iteration.submitted_at or latest_iteration.updated_at
    except Exception as e:
        # Log error for debugging but don't break the template
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_field_answer_timestamp filter: {e}")
    
    return None 