# Generated migration to preserve discussions when topics are deleted
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0006_sync_sequential_progression'),
    ]

    operations = [
        migrations.AlterField(
            model_name='discussion',
            name='topic',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='topic_discussion',
                to='courses.topic'
            ),
        ),
    ]

