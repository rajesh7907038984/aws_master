from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.apps import apps
from .models import RubricCriterionOutcome, OutcomeEvaluation, Outcome


@receiver(post_save, sender='lms_rubrics.RubricEvaluation')
def update_outcome_evaluations_on_rubric_evaluation(sender, instance, created, **kwargs):
    """
    Update outcome evaluations when a rubric evaluation is saved.
    """
    try:
        # Get all outcomes connected to this criterion
        connections = RubricCriterionOutcome.objects.filter(
            criterion=instance.criterion
        ).select_related('outcome')
        
        # Update evaluations for each connected outcome
        for connection in connections:
            outcome = connection.outcome
            student = instance.student if instance.student else instance.submission.user if instance.submission else None
            
            if student:
                outcome.update_student_evaluation(student)
    
    except Exception as e:
        # Log error but don't break the evaluation save
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations: {str(e)}")


@receiver(post_delete, sender='lms_rubrics.RubricEvaluation')
def update_outcome_evaluations_on_rubric_evaluation_delete(sender, instance, **kwargs):
    """
    Update outcome evaluations when a rubric evaluation is deleted.
    """
    try:
        # Get all outcomes connected to this criterion
        connections = RubricCriterionOutcome.objects.filter(
            criterion=instance.criterion
        ).select_related('outcome')
        
        # Update evaluations for each connected outcome
        for connection in connections:
            outcome = connection.outcome
            student = instance.student if instance.student else instance.submission.user if instance.submission else None
            
            if student:
                outcome.update_student_evaluation(student)
    
    except Exception as e:
        # Log error but don't break the deletion
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations after deletion: {str(e)}")


@receiver(post_save, sender='quiz.QuizRubricEvaluation')
def update_outcome_evaluations_on_quiz_rubric_evaluation(sender, instance, created, **kwargs):
    """
    Update outcome evaluations when a quiz rubric evaluation is saved.
    """
    try:
        # Get all outcomes connected to this criterion
        connections = RubricCriterionOutcome.objects.filter(
            criterion=instance.criterion
        ).select_related('outcome')
        
        # Update evaluations for each connected outcome
        for connection in connections:
            outcome = connection.outcome
            student = instance.quiz_attempt.user
            
            if student:
                outcome.update_student_evaluation(student)
    
    except Exception as e:
        # Log error but don't break the evaluation save
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations from quiz: {str(e)}")


@receiver(post_delete, sender='quiz.QuizRubricEvaluation')
def update_outcome_evaluations_on_quiz_rubric_evaluation_delete(sender, instance, **kwargs):
    """
    Update outcome evaluations when a quiz rubric evaluation is deleted.
    """
    try:
        # Get all outcomes connected to this criterion
        connections = RubricCriterionOutcome.objects.filter(
            criterion=instance.criterion
        ).select_related('outcome')
        
        # Update evaluations for each connected outcome
        for connection in connections:
            outcome = connection.outcome
            student = instance.quiz_attempt.user
            
            if student:
                outcome.update_student_evaluation(student)
    
    except Exception as e:
        # Log error but don't break the deletion
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations after quiz deletion: {str(e)}")


@receiver(post_save, sender='conferences.ConferenceRubricEvaluation')
def update_outcome_evaluations_on_conference_rubric_evaluation(sender, instance, created, **kwargs):
    """
    Update outcome evaluations when a conference rubric evaluation is saved.
    """
    try:
        # Get all outcomes connected to this criterion
        connections = RubricCriterionOutcome.objects.filter(
            criterion=instance.criterion
        ).select_related('outcome')
        
        # Update evaluations for each connected outcome
        for connection in connections:
            outcome = connection.outcome
            student = instance.attendance.user
            
            if student:
                outcome.update_student_evaluation(student)
    
    except Exception as e:
        # Log error but don't break the evaluation save
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations from conference: {str(e)}")


@receiver(post_delete, sender='conferences.ConferenceRubricEvaluation')
def update_outcome_evaluations_on_conference_rubric_evaluation_delete(sender, instance, **kwargs):
    """
    Update outcome evaluations when a conference rubric evaluation is deleted.
    """
    try:
        # Get all outcomes connected to this criterion
        connections = RubricCriterionOutcome.objects.filter(
            criterion=instance.criterion
        ).select_related('outcome')
        
        # Update evaluations for each connected outcome
        for connection in connections:
            outcome = connection.outcome
            student = instance.attendance.user
            
            if student:
                outcome.update_student_evaluation(student)
    
    except Exception as e:
        # Log error but don't break the deletion
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations after conference deletion: {str(e)}")


@receiver(post_save, sender=RubricCriterionOutcome)
def update_outcome_evaluations_on_connection_change(sender, instance, created, **kwargs):
    """
    Update outcome evaluations when a rubric-outcome connection is created or modified.
    This ensures that new connections retroactively calculate outcomes for existing evaluations.
    """
    try:
        outcome = instance.outcome
        criterion = instance.criterion
        
        # Get all students who have evaluations for this criterion
        from lms_rubrics.models import RubricEvaluation
        from users.models import CustomUser
        
        # Get students from regular rubric evaluations
        student_ids = set()
        
        # Assignment and Discussion evaluations
        evaluations = RubricEvaluation.objects.filter(
            criterion=criterion
        ).values_list('student_id', flat=True)
        student_ids.update([id for id in evaluations if id])
        
        # Submission-based evaluations (where student is from submission)
        submission_evaluations = RubricEvaluation.objects.filter(
            criterion=criterion,
            submission__isnull=False
        ).select_related('submission__user')
        student_ids.update([eval.submission.user.id for eval in submission_evaluations])
        
        # Quiz evaluations
        try:
            QuizRubricEvaluation = apps.get_model('quiz', 'QuizRubricEvaluation')
            quiz_evaluations = QuizRubricEvaluation.objects.filter(
                criterion=criterion
            ).select_related('quiz_attempt__user')
            student_ids.update([eval.quiz_attempt.user.id for eval in quiz_evaluations])
        except:
            pass
        
        # Conference evaluations
        try:
            ConferenceRubricEvaluation = apps.get_model('conferences', 'ConferenceRubricEvaluation')
            conference_evaluations = ConferenceRubricEvaluation.objects.filter(
                criterion=criterion
            ).select_related('attendance__user')
            student_ids.update([eval.attendance.user.id for eval in conference_evaluations])
        except:
            pass
        
        # Update outcome evaluations for all affected students
        for student_id in student_ids:
            try:
                student = CustomUser.objects.get(id=student_id)
                outcome.update_student_evaluation(student)
            except CustomUser.DoesNotExist:
                continue
    
    except Exception as e:
        # Log error but don't break the connection save
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations on connection change: {str(e)}")


@receiver(post_delete, sender=RubricCriterionOutcome)
def update_outcome_evaluations_on_connection_delete(sender, instance, **kwargs):
    """
    Update outcome evaluations when a rubric-outcome connection is deleted.
    """
    try:
        outcome = instance.outcome
        
        # Get all students who have evaluations for any criterion connected to this outcome
        from users.models import CustomUser
        
        # Get all students who have evaluations for this outcome (from remaining connections)
        remaining_connections = RubricCriterionOutcome.objects.filter(outcome=outcome)
        student_ids = set()
        
        for connection in remaining_connections:
            criterion = connection.criterion
            
            # Get students from all types of evaluations
            from lms_rubrics.models import RubricEvaluation
            
            evaluations = RubricEvaluation.objects.filter(
                criterion=criterion
            ).values_list('student_id', flat=True)
            student_ids.update([id for id in evaluations if id])
            
            # Add more evaluation types...
            # (Similar to above)
        
        # Update outcome evaluations for all affected students
        for student_id in student_ids:
            try:
                student = CustomUser.objects.get(id=student_id)
                outcome.update_student_evaluation(student)
            except CustomUser.DoesNotExist:
                continue
        
        # If no connections remain, potentially clean up orphaned evaluations
        if not remaining_connections.exists():
            # Optional: Delete evaluations that no longer have any basis
            # OutcomeEvaluation.objects.filter(outcome=outcome).delete()
            pass
    
    except Exception as e:
        # Log error but don't break the deletion
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating outcome evaluations on connection delete: {str(e)}")