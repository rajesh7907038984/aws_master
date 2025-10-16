from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('courses', '0006_course_survey'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS courses_scormregistration CASCADE;",
            reverse_sql="-- No reverse operation needed"
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS courses_scormattempt CASCADE;",
            reverse_sql="-- No reverse operation needed"
        ),
    ]
