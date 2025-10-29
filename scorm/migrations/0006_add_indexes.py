# Generated migration to add database indexes to ScormPackage
from django.db import migrations, models


class Migration(migrations.Migration):
    
    dependencies = [
        ('scorm', '0005_populate_primary_resource_fields'),
    ]
    
    operations = [
        migrations.AddIndex(
            model_name='scormpackage',
            index=models.Index(fields=['processing_status', 'created_at'], name='scorm_scorm_process_idx'),
        ),
        migrations.AddIndex(
            model_name='scormpackage',
            index=models.Index(fields=['created_by', 'processing_status'], name='scorm_scorm_created_idx'),
        ),
        migrations.AddIndex(
            model_name='scormpackage',
            index=models.Index(fields=['version', 'authoring_tool'], name='scorm_scorm_version_idx'),
        ),
    ]

