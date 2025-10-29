# Generated migration to add resource fields to ScormPackage
from django.db import migrations, models

# Use Django's JSONField if available (Django 3.1+), otherwise use postgres JSONField
try:
    from django.db.models import JSONField
except ImportError:
    try:
        from django.contrib.postgres.fields import JSONField
    except ImportError:
        # Fallback
        JSONField = models.TextField


class Migration(migrations.Migration):

    dependencies = [
        ('scorm', '0003_add_authoring_tool'),
    ]

    operations = [
        migrations.AddField(
            model_name='scormpackage',
            name='resources',
            field=JSONField(
                blank=True,
                default=list,
                help_text='Raw manifest resources array'
            ),
        ),
        migrations.AddField(
            model_name='scormpackage',
            name='primary_resource_identifier',
            field=models.CharField(
                blank=True,
                help_text='Unique identifier of the primary SCORM resource',
                max_length=128,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='scormpackage',
            name='primary_resource_type',
            field=models.CharField(
                blank=True,
                choices=[('webcontent', 'Web Content')],
                help_text='SCORM resource @type attribute',
                max_length=32,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='scormpackage',
            name='primary_resource_scorm_type',
            field=models.CharField(
                blank=True,
                choices=[('sco', 'SCO'), ('asset', 'Asset')],
                help_text='adlcp:scormType attribute (sco or asset)',
                max_length=16,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='scormpackage',
            name='primary_resource_href',
            field=models.CharField(
                blank=True,
                help_text='Entry point HTML file (href from primary resource)',
                max_length=2048,
                null=True
            ),
        ),
    ]

