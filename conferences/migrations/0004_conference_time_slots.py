# Generated manually on 2025-11-09 for time slots feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('conferences', '0003_initial'),
    ]

    operations = [
        # Add use_time_slots field to Conference model
        migrations.AddField(
            model_name='conference',
            name='use_time_slots',
            field=models.BooleanField(default=False, help_text='Enable multiple time slot options for learners to choose from'),
        ),
        
        # Create ConferenceTimeSlot model
        migrations.CreateModel(
            name='ConferenceTimeSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('timezone', models.CharField(default='UTC', help_text='Timezone for this time slot', max_length=100)),
                ('max_participants', models.IntegerField(default=0, help_text='Maximum participants for this slot (0 = unlimited)')),
                ('current_participants', models.IntegerField(default=0, help_text='Current number of participants')),
                ('meeting_link', models.URLField(blank=True, max_length=500, null=True)),
                ('meeting_id', models.CharField(blank=True, max_length=255, null=True)),
                ('meeting_password', models.CharField(blank=True, max_length=100, null=True)),
                ('is_available', models.BooleanField(default=True, help_text='Is this slot available for selection?')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('conference', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_slots', to='conferences.conference')),
            ],
            options={
                'ordering': ['date', 'start_time'],
            },
        ),
        
        # Create ConferenceTimeSlotSelection model
        migrations.CreateModel(
            name='ConferenceTimeSlotSelection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('outlook_event_id', models.CharField(blank=True, max_length=255, null=True)),
                ('calendar_added', models.BooleanField(default=False)),
                ('calendar_add_attempted_at', models.DateTimeField(blank=True, null=True)),
                ('calendar_error', models.TextField(blank=True, null=True)),
                ('selected_at', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('conference', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_slot_selections', to='conferences.conference')),
                ('time_slot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='selections', to='conferences.conferencetimeslot')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_slot_selections', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        
        # Add indexes for Conference.use_time_slots
        migrations.AddIndex(
            model_name='conference',
            index=models.Index(fields=['use_time_slots'], name='conferences_use_tim_idx'),
        ),
        
        # Add indexes for ConferenceTimeSlot
        migrations.AddIndex(
            model_name='conferencetimeslot',
            index=models.Index(fields=['conference', 'date', 'start_time'], name='conferences_ts_conf_date_idx'),
        ),
        migrations.AddIndex(
            model_name='conferencetimeslot',
            index=models.Index(fields=['is_available'], name='conferences_ts_avail_idx'),
        ),
        
        # Add indexes for ConferenceTimeSlotSelection
        migrations.AddIndex(
            model_name='conferencetimeslotselection',
            index=models.Index(fields=['time_slot', 'user'], name='conferences_tss_slot_user_idx'),
        ),
        migrations.AddIndex(
            model_name='conferencetimeslotselection',
            index=models.Index(fields=['conference', 'user'], name='conferences_tss_conf_user_idx'),
        ),
        migrations.AddIndex(
            model_name='conferencetimeslotselection',
            index=models.Index(fields=['selected_at'], name='conferences_tss_selected_idx'),
        ),
        
        # Add unique constraint for ConferenceTimeSlotSelection
        migrations.AlterUniqueTogether(
            name='conferencetimeslotselection',
            unique_together={('conference', 'user')},
        ),
    ]

