# Generated migration for adding branch field to Rubric

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('branches', '0001_initial'),
        ('lms_rubrics', '0005_rubricevaluation_student'),
    ]

    operations = [
        migrations.AddField(
            model_name='rubric',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                help_text='The branch this rubric belongs to',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rubrics',
                to='branches.branch'
            ),
        ),
    ] 