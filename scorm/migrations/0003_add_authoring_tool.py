# Generated migration to add authoring_tool field to ScormPackage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scorm', '0002_add_launch_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='scormpackage',
            name='authoring_tool',
            field=models.CharField(
                blank=True,
                choices=[
                    ('unknown', 'Unknown'),
                    ('storyline', 'Articulate Storyline'),
                    ('rise', 'Articulate Rise'),
                    ('captivate', 'Adobe Captivate'),
                    ('ispring', 'iSpring'),
                    ('elucidat', 'Elucidat'),
                    ('dominknow', 'DominKnow'),
                    ('lectora', 'Lectora'),
                    ('adapt', 'Adapt Learning'),
                    ('other', 'Other'),
                ],
                default='unknown',
                help_text='Authoring tool used to create this SCORM package',
                max_length=32,
                null=True
            ),
        ),
    ]

