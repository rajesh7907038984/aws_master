# Generated manually to fix circular dependency
# This migration adds the rubric field that was removed from 0002_initial

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discussions", "0002_initial"),
        ("lms_rubrics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="discussion",
            name="rubric",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional rubric to evaluate this discussion",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="discussions",
                to="lms_rubrics.rubric",
            ),
        ),
    ]
