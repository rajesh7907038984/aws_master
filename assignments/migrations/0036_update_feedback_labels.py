# Generated manually to fix missing dependency
# This migration was referenced by lms_rubrics but didn't exist

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("assignments", "0027_update_default_status_to_not_graded"),
    ]

    operations = [
        # Placeholder migration to satisfy dependencies
        # Feedback label updates likely happened in another migration or were manual
    ]
