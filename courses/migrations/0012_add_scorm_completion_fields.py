# Generated manually on 2025-01-27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0011_auto_20251027_2023'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='scorm_completion_status',
            field=models.CharField(
                choices=[
                    ('not_attempted', 'Not Attempted'),
                    ('incomplete', 'Incomplete'),
                    ('completed', 'Completed'),
                    ('passed', 'Passed'),
                    ('failed', 'Failed'),
                ],
                help_text='SCORM course completion status (cmi.core.lesson_status)',
                max_length=20,
                null=True,
                blank=True
            ),
        ),
        migrations.AddField(
            model_name='course',
            name='scorm_lesson_status',
            field=models.CharField(
                choices=[
                    ('not_attempted', 'Not Attempted'),
                    ('incomplete', 'Incomplete'),
                    ('completed', 'Completed'),
                    ('passed', 'Passed'),
                    ('failed', 'Failed'),
                    ('browsed', 'Browsed'),
                ],
                help_text='SCORM lesson status for the entire course',
                max_length=20,
                null=True,
                blank=True
            ),
        ),
        migrations.AddField(
            model_name='course',
            name='scorm_completion_data',
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text='Complete SCORM completion data for the course'
            ),
        ),
    ]
