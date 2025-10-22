# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lms_rubrics', '0002_rubricevaluation_discussion'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='rubricevaluation',
            unique_together={
                ('submission', 'criterion'),
                ('discussion', 'criterion'),
            },
        ),
    ] 