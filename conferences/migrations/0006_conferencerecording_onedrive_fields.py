# Generated migration for Teams OneDrive recording storage

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conferences', '0005_auto_20251111_0047'),
    ]

    operations = [
        # Add OneDrive/SharePoint storage fields
        migrations.AddField(
            model_name='conferencerecording',
            name='onedrive_item_id',
            field=models.CharField(
                blank=True,
                help_text='OneDrive item ID',
                max_length=255,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='onedrive_drive_id',
            field=models.CharField(
                blank=True,
                help_text='OneDrive drive ID',
                max_length=255,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='onedrive_file_path',
            field=models.CharField(
                blank=True,
                help_text='Full path in OneDrive',
                max_length=1000,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='onedrive_web_url',
            field=models.URLField(
                blank=True,
                help_text='Web viewing URL',
                max_length=1000,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='onedrive_download_url',
            field=models.URLField(
                blank=True,
                help_text='Direct download URL from OneDrive',
                max_length=1000,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='stored_in_onedrive',
            field=models.BooleanField(
                default=False,
                help_text='Whether recording is stored in OneDrive'
            ),
        ),
        
        # Add Teams meeting recording metadata
        migrations.AddField(
            model_name='conferencerecording',
            name='meeting_recording_id',
            field=models.CharField(
                blank=True,
                help_text='Teams meeting recording ID',
                max_length=255,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='recording_content_url',
            field=models.URLField(
                blank=True,
                help_text='Content URL from Teams',
                max_length=1000,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='created_by_name',
            field=models.CharField(
                blank=True,
                help_text='Name of person who created recording',
                max_length=255,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='created_by_email',
            field=models.EmailField(
                blank=True,
                help_text='Email of person who created recording',
                max_length=254,
                null=True
            ),
        ),
        
        # Add download tracking fields
        migrations.AddField(
            model_name='conferencerecording',
            name='download_count',
            field=models.IntegerField(
                default=0,
                help_text='Number of times recording has been downloaded'
            ),
        ),
        migrations.AddField(
            model_name='conferencerecording',
            name='last_downloaded_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Last download timestamp',
                null=True
            ),
        ),
        
        # Add index for OneDrive lookups
        migrations.AddIndex(
            model_name='conferencerecording',
            index=models.Index(
                fields=['onedrive_item_id'],
                name='conferences_onedrive_item_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='conferencerecording',
            index=models.Index(
                fields=['stored_in_onedrive', 'status'],
                name='conferences_onedrive_status_idx'
            ),
        ),
    ]

