# Generated manually for complete SCORM CMI and xAPI field support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scorm', '0016_remove_scorm_interaction_table'),
    ]

    operations = [
        # SCORM 1.2 Additional CMI Fields
        migrations.AddField(
            model_name='scormattempt',
            name='cmi_student_preferences',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='SCORM 1.2 student preferences (audio, language, speed, text)'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='cmi_objectives_12',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='SCORM 1.2 objectives data with scores and status'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='cmi_interactions_12',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='SCORM 1.2 interactions data with responses and results'
            ),
        ),
        
        # SCORM 2004 Additional CMI Fields
        migrations.AddField(
            model_name='scormattempt',
            name='cmi_comments_from_learner',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='SCORM 2004 learner comments with timestamps and locations'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='cmi_comments_from_lms',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='SCORM 2004 LMS comments with timestamps and locations'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='cmi_objectives_2004',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='SCORM 2004 objectives data with progress measures and status'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='cmi_interactions_2004',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='SCORM 2004 interactions data with enhanced tracking'
            ),
        ),
        
        # xAPI Event Data Fields
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_events',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='xAPI event statements array'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_actor',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='xAPI actor data (name, mbox, etc.)'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_verb',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='xAPI verb data (id, display)'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_object',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='xAPI object data (id, definition)'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_result',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='xAPI result data (score, success, completion, duration)'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_context',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='xAPI context data (registration, activities, extensions)'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_timestamp',
            field=models.DateTimeField(
                blank=True,
                help_text='xAPI event timestamp',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_stored',
            field=models.DateTimeField(
                blank=True,
                help_text='xAPI stored timestamp',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_authority',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='xAPI authority data'
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_version',
            field=models.CharField(
                blank=True,
                default='1.0.3',
                help_text='xAPI version',
                max_length=10
            ),
        ),
        migrations.AddField(
            model_name='scormattempt',
            name='xapi_attachments',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='xAPI attachments array'
            ),
        ),
    ]
