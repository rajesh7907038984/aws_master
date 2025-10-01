# Generated manually to fix missing dependency
# This migration was referenced by lms_rubrics but didn't exist

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("discussions", "0003_add_rubric_field"),
    ]

    operations = [
        # Placeholder migration to satisfy dependencies
        # The instructions field already exists in the Discussion model from 0001_initial
    ]
