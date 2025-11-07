# Generated manually to increase file field lengths to 500

from django.db import migrations, models
import assignments.models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0004_increase_file_field_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='assignment',
            name='attachment',
            field=models.FileField(blank=True, help_text='Supporting documents for the assignment (Use AssignmentAttachment for new documents)', max_length=500, null=True, upload_to=assignments.models.assignment_file_path),
        ),
        migrations.AlterField(
            model_name='assignmentattachment',
            name='file',
            field=models.FileField(help_text='Supporting document for the assignment', max_length=500, upload_to=assignments.models.assignment_file_path),
        ),
        migrations.AlterField(
            model_name='assignmentfeedback',
            name='audio_feedback',
            field=models.FileField(blank=True, help_text='Audio feedback file (mp3, wav, m4a, etc.)', max_length=500, null=True, upload_to=assignments.models.assignment_file_path),
        ),
        migrations.AlterField(
            model_name='assignmentfeedback',
            name='video_feedback',
            field=models.FileField(blank=True, help_text='Video feedback file (mp4, mov, avi, etc.)', max_length=500, null=True, upload_to=assignments.models.assignment_file_path),
        ),
        migrations.AlterField(
            model_name='assignmentsubmission',
            name='submission_file',
            field=models.FileField(blank=True, max_length=500, null=True, upload_to=assignments.models.assignment_file_path),
        ),
    ]

