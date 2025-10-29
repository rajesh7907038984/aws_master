# Generated migration to add SCORM ForeignKey to Topic model
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0002_initial'),
        ('scorm', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='topic',
            name='scorm',
            field=models.ForeignKey(
                blank=True,
                help_text='Associated SCORM package for SCORM type topics',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='topics',
                to='scorm.scormpackage'
            ),
        ),
    ]

