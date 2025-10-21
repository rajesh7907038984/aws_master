# Generated migration

from django.db import migrations
from django.utils import timezone


def populate_rubric_history(apps, schema_editor):
    """Create history records for existing rubric evaluations"""
    RubricEvaluation = apps.get_model('lms_rubrics', 'RubricEvaluation')
    RubricEvaluationHistory = apps.get_model('lms_rubrics', 'RubricEvaluationHistory')
    
    # Get all existing evaluations
    evaluations = RubricEvaluation.objects.all()
    
    for evaluation in evaluations:
        # Check if history already exists
        history_exists = RubricEvaluationHistory.objects.filter(
            submission=evaluation.submission,
            discussion=evaluation.discussion,
            criterion=evaluation.criterion,
            student=evaluation.student
        ).exists()
        
        if not history_exists:
            # Create history record for existing evaluation
            RubricEvaluationHistory.objects.create(
                submission=evaluation.submission,
                discussion=evaluation.discussion,
                criterion=evaluation.criterion,
                rating=evaluation.rating,
                points=evaluation.points,
                comments=evaluation.comments,
                evaluated_by=evaluation.evaluated_by,
                student=evaluation.student,
                version=1,
                evaluation_date=evaluation.created_at or timezone.now(),
                is_current=True
            )


def reverse_populate_history(apps, schema_editor):
    """Remove history records created by this migration"""
    RubricEvaluationHistory = apps.get_model('lms_rubrics', 'RubricEvaluationHistory')
    # Delete all v1 history records
    RubricEvaluationHistory.objects.filter(version=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('lms_rubrics', '0012_add_rubric_evaluation_history'),
    ]

    operations = [
        migrations.RunPython(populate_rubric_history, reverse_populate_history),
    ] 