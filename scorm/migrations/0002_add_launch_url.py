# Generated migration to add launch_url field to ScormPackage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scorm', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='scormpackage',
            name='launch_url',
            field=models.CharField(
                blank=True,
                help_text='Full launch URL path for this SCORM package (e.g., /scorm/player/123/story.html)',
                max_length=2048,
                null=True
            ),
        ),
    ]

