# Generated migration for SCORM app
from django.db import migrations, models
import django.db.models.deletion

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

    initial = True

    dependencies = [
        ('users', '0001_initial'),  # Adjust if needed
    ]

    operations = [
        migrations.CreateModel(
            name='ScormPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(help_text='Title extracted from manifest', max_length=255)),
                ('version', models.CharField(blank=True, choices=[('1.2', 'SCORM 1.2'), ('2004', 'SCORM 2004')], help_text='SCORM version (1.2 or 2004)', max_length=16, null=True)),
                ('package_zip', models.FileField(blank=True, help_text='Original uploaded ZIP file', null=True, upload_to='scorm_packages/zips/')),
                ('extracted_path', models.CharField(blank=True, help_text='S3 path to extracted package directory', max_length=1024, null=True)),
                ('manifest_data', JSONField(blank=True, default=dict, help_text='Parsed manifest data (organizations, resources, metadata)')),
                ('processing_status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')], default='pending', help_text='Package processing status', max_length=32)),
                ('processing_error', models.TextField(blank=True, help_text='Error message if processing failed', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, help_text='User who uploaded this package', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_scorm_packages', to='users.CustomUser')),
            ],
            options={
                'verbose_name': 'SCORM Package',
                'verbose_name_plural': 'SCORM Packages',
                'ordering': ['-created_at'],
            },
        ),
    ]

