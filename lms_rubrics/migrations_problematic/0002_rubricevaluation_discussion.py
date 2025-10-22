# Generated manually

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('lms_rubrics', '0001_initial')
    ]

    operations = [
        migrations.AddField(
            model_name='rubricevaluation',
            name='discussion',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rubric_evaluations',
                to='discussions.discussion'
            ),
        ),
        migrations.AlterUniqueTogether(
            name='rubricevaluation',
            unique_together={('submission', 'criterion')},
        )
    ] 