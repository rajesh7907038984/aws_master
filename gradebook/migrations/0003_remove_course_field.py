# Generated migration to fix Bug #3: Remove redundant course field from Grade model
# The course can be accessed via assignment.course, so this field is redundant

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('gradebook', '0002_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='grade',
            name='course',
        ),
    ]

