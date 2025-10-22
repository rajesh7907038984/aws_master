from django.core.management.base import BaseCommand
from django.db import migrations, models
import os

class Command(BaseCommand):
    help = 'Create timezone migration manually'

    def handle(self, *args, **options):
        # Create the migration file manually
        migration_content = '''# Generated manually for timezone support
from django.db import migrations, models
import django.db.models.deletion
import pytz

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0030_delete_usersession'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserTimezone',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timezone', models.CharField(default='UTC', help_text="User's preferred timezone (e.g., 'America/New_York', 'Europe/London')", max_length=100)),
                ('auto_detected', models.BooleanField(default=False, help_text='Whether timezone was auto-detected from browser')),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='timezone_preference', to='users.customuser')),
            ],
            options={
                'verbose_name': 'User Timezone',
                'verbose_name_plural': 'User Timezones',
                'db_table': 'users_usertimezone',
            },
        ),
    ]
'''

        # Write the migration file
        migration_path = os.path.join('users', 'migrations', '0031_usertimezone.py')
        os.makedirs(os.path.dirname(migration_path), exist_ok=True)
        
        with open(migration_path, 'w') as f:
            f.write(migration_content)
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created migration file: {migration_path}')
        )
