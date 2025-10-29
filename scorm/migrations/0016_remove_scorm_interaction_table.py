# Generated manually on 2025-01-27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scorm', '0015_remove_legacy_scorm_2004_tables'),
    ]

    operations = [
        # Drop the scorm_interaction table
        migrations.RunSQL(
            "DROP TABLE IF EXISTS scorm_interaction CASCADE;",
            reverse_sql="-- No reverse operation needed - removing unused table"
        ),
    ]
