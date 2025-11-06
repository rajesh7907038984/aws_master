# Generated migration to remove deprecated is_read field

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lms_messages', '0002_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='message',
            name='is_read',
        ),
    ]

