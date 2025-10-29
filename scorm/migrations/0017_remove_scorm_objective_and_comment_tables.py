# Generated manually on 2025-01-27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scorm', '0016_remove_scorm_interaction_table'),
    ]

    operations = [
        # Drop the scorm_objective table
        migrations.RunSQL(
            "DROP TABLE IF EXISTS scorm_objective CASCADE;",
            reverse_sql="-- No reverse operation needed - removing unused table"
        ),
        
        # Drop the scorm_comment table
        migrations.RunSQL(
            "DROP TABLE IF EXISTS scorm_comment CASCADE;",
            reverse_sql="-- No reverse operation needed - removing unused table"
        ),
    ]
