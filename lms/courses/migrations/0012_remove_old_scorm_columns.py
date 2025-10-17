# Generated manually to remove old SCORM columns

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0011_add_scorm_mastery_score_fields'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE courses_topic DROP COLUMN IF EXISTS native_scorm_package_id;",
            reverse_sql="-- No reverse operation needed"
        ),
        migrations.RunSQL(
            sql="ALTER TABLE courses_topicprogress DROP COLUMN IF EXISTS scorm_registration;",
            reverse_sql="-- No reverse operation needed"
        ),
        migrations.RunSQL(
            sql="ALTER TABLE branches_branch DROP COLUMN IF EXISTS scorm_integration_enabled;",
            reverse_sql="-- No reverse operation needed"
        ),
    ]
