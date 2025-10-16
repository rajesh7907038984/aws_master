from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('courses', '0007_remove_scorm_tables'),
    ]

    operations = [
        migrations.RunSQL(
            "DELETE FROM courses_topic WHERE content_type = 'SCORM';",
            reverse_sql="-- No reverse operation needed"
        ),
        migrations.RunSQL(
            "DELETE FROM courses_topicprogress WHERE topic_id IN (SELECT id FROM courses_topic WHERE content_type = 'SCORM');",
            reverse_sql="-- No reverse operation needed"
        ),
        migrations.RunSQL(
            "DELETE FROM courses_coursetopic WHERE topic_id IN (SELECT id FROM courses_topic WHERE content_type = 'SCORM');",
            reverse_sql="-- No reverse operation needed"
        ),
    ]
