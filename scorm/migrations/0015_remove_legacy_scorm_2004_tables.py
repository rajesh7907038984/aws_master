# Generated manually on 2025-01-27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scorm', '0014_add_has_score_requirement'),
    ]

    operations = [
        # Remove foreign key constraint from courses_topic first
        migrations.RunSQL(
            "ALTER TABLE courses_topic DROP CONSTRAINT IF EXISTS courses_topic_scorm_package_id_a0b36d75_fk_scorm_200;",
            reverse_sql="-- No reverse operation needed"
        ),
        
        # Drop the legacy SCORM 2004 tables
        migrations.RunSQL(
            """
            DROP TABLE IF EXISTS scorm_2004_scormattempt CASCADE;
            DROP TABLE IF EXISTS scorm_2004_scormsco CASCADE;
            DROP TABLE IF EXISTS scorm_2004_scormpackage CASCADE;
            """,
            reverse_sql="-- No reverse operation needed - these are legacy tables"
        ),
        
        # Remove the scorm_package_id column from courses_topic if it exists
        migrations.RunSQL(
            "ALTER TABLE courses_topic DROP COLUMN IF EXISTS scorm_package_id;",
            reverse_sql="-- No reverse operation needed"
        ),
    ]
