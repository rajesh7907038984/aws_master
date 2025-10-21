# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        ('lms_rubrics', '0004_add_rubric_evaluation'),
    ]

    operations = [
        migrations.AddField(
            model_name='rubricevaluation',
            name='student',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='received_evaluations',
                to='users.customuser'
            ),
        ),
        migrations.AlterUniqueTogether(
            name='rubricevaluation',
            unique_together={
                ('submission', 'criterion'),
                ('discussion', 'criterion', 'student'),
            },
        ),
    ] 