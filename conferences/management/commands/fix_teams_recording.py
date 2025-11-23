"""
Management command to fix Teams meeting auto-recording by fetching missing online_meeting_ids
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from conferences.models import Conference, ConferenceTimeSlot
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix Teams meeting auto-recording by fetching and saving missing online_meeting_ids'

    def add_arguments(self, parser):
        parser.add_argument(
            '--conference-id',
            type=int,
            help='Fix specific conference by ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--enable-recording',
            action='store_true',
            help='Also enable recording after fetching online_meeting_id',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        conference_id = options.get('conference_id')
        enable_recording = options['enable_recording']
        
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('Teams Meeting Auto-Recording Fix Utility'))
        self.stdout.write(self.style.WARNING('=' * 80))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made\n'))
        
        # Get conferences to fix
        if conference_id:
            conferences = Conference.objects.filter(id=conference_id, meeting_platform='teams')
            if not conferences.exists():
                self.stdout.write(self.style.ERROR(f'Conference {conference_id} not found or not a Teams conference'))
                return
        else:
            # Find all Teams conferences with pending recording status
            conferences = Conference.objects.filter(
                meeting_platform='teams',
                auto_recording_status='pending'
            )
        
        self.stdout.write(f'\n📋 Found {conferences.count()} Teams conference(s) to check\n')
        
        fixed_count = 0
        error_count = 0
        
        for conference in conferences:
            self.stdout.write(f'\n{"─" * 80}')
            self.stdout.write(f'Conference: {conference.title} (ID: {conference.id})')
            self.stdout.write(f'Recording Status: {conference.auto_recording_status}')
            self.stdout.write(f'Uses Time Slots: {conference.use_time_slots}')
            
            # Get Teams integration
            integration = None
            if hasattr(conference.created_by, 'branch') and conference.created_by.branch:
                integration = TeamsIntegration.objects.filter(
                    branch=conference.created_by.branch,
                    is_active=True
                ).first()
            
            if not integration:
                integration = TeamsIntegration.objects.filter(
                    user=conference.created_by,
                    is_active=True
                ).first()
            
            if not integration:
                self.stdout.write(self.style.ERROR('  ✗ No Teams integration found'))
                error_count += 1
                continue
            
            teams_client = TeamsAPIClient(integration)
            
            # Fix time slots if conference uses them
            if conference.use_time_slots:
                time_slots = conference.time_slots.all()
                self.stdout.write(f'\n  Time Slots: {time_slots.count()}')
                
                for ts in time_slots:
                    self.stdout.write(f'\n  Slot {ts.id} - {ts.date} {ts.start_time}:')
                    
                    if ts.online_meeting_id:
                        self.stdout.write(f'    ✓ Already has online_meeting_id: {ts.online_meeting_id[:30]}...')
                        continue
                    
                    if not ts.meeting_id:
                        self.stdout.write(self.style.WARNING('    ⚠ No meeting_id - skipping'))
                        continue
                    
                    # Fetch online meeting details
                    try:
                        user_email = None
                        if integration.service_account_email:
                            user_email = integration.service_account_email
                        elif conference.created_by and conference.created_by.email:
                            user_email = conference.created_by.email
                        elif integration.user and integration.user.email:
                            user_email = integration.user.email
                        
                        if not user_email:
                            self.stdout.write(self.style.ERROR('    ✗ No user email found'))
                            error_count += 1
                            continue
                        
                        # Get meeting details from Graph API
                        endpoint = f'/users/{user_email}/events/{ts.meeting_id}'
                        self.stdout.write(f'    📡 Fetching meeting details...')
                        
                        response = teams_client._make_request('GET', endpoint)
                        
                        # Try to get online meeting ID from response
                        online_meeting = response.get('onlineMeeting', {})
                        online_meeting_id = online_meeting.get('id')
                        
                        # If not found, try to extract from join URL
                        if not online_meeting_id and response.get('onlineMeeting', {}).get('joinUrl'):
                            join_url = response.get('onlineMeeting', {}).get('joinUrl')
                            self.stdout.write(f'    📡 Got join URL but no ID, trying to get ID from join URL...')
                            # The join URL format is: https://teams.microsoft.com/l/meetup-join/{thread_id}/...
                            # We need to query by the calendar event to get the actual online meeting ID
                            # Try alternative approach: query online meetings by calendar event
                            try:
                                online_meeting_endpoint = f'/users/{user_email}/onlineMeetings?$filter=subject eq \'{response.get("subject")}\''
                                online_meetings_response = teams_client._make_request('GET', online_meeting_endpoint)
                                meetings = online_meetings_response.get('value', [])
                                if meetings:
                                    online_meeting_id = meetings[0].get('id')
                                    self.stdout.write(f'    ✓ Found online meeting ID via query')
                            except Exception as e:
                                self.stdout.write(f'    ⚠ Could not query online meetings: {str(e)}')
                        
                        if online_meeting_id:
                            self.stdout.write(f'    ✓ Found online_meeting_id: {online_meeting_id[:30]}...')
                            
                            if not dry_run:
                                ts.online_meeting_id = online_meeting_id
                                ts.save(update_fields=['online_meeting_id'])
                                self.stdout.write(self.style.SUCCESS('    ✓ Saved to database'))
                                
                                # Enable recording if requested
                                if enable_recording:
                                    self.stdout.write('    🔴 Enabling auto-recording...')
                                    recording_result = teams_client.enable_meeting_recording(
                                        online_meeting_id, 
                                        user_email
                                    )
                                    
                                    if recording_result['success']:
                                        self.stdout.write(self.style.SUCCESS('    ✓ Recording enabled successfully'))
                                        # Update conference recording status
                                        conference.auto_recording_status = 'enabled'
                                        conference.auto_recording_enabled_at = timezone.now()
                                        conference.save(update_fields=['auto_recording_status', 'auto_recording_enabled_at'])
                                        fixed_count += 1
                                    else:
                                        self.stdout.write(self.style.ERROR(f'    ✗ Recording failed: {recording_result.get("error")}'))
                                        error_count += 1
                            else:
                                self.stdout.write('    (Would save to database)')
                                if enable_recording:
                                    self.stdout.write('    (Would enable recording)')
                        else:
                            self.stdout.write(self.style.WARNING('    ⚠ No online meeting ID found in response'))
                            error_count += 1
                            
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'    ✗ Error: {str(e)}'))
                        logger.error(f'Error fixing time slot {ts.id}: {str(e)}')
                        error_count += 1
            
            # Also check main conference meeting
            elif conference.meeting_id and not conference.online_meeting_id:
                self.stdout.write(f'\n  Main Conference Meeting:')
                
                try:
                    user_email = None
                    if integration.service_account_email:
                        user_email = integration.service_account_email
                    elif conference.created_by and conference.created_by.email:
                        user_email = conference.created_by.email
                    elif integration.user and integration.user.email:
                        user_email = integration.user.email
                    
                    if not user_email:
                        self.stdout.write(self.style.ERROR('    ✗ No user email found'))
                        error_count += 1
                        continue
                    
                    # Get meeting details from Graph API
                    endpoint = f'/users/{user_email}/events/{conference.meeting_id}'
                    self.stdout.write(f'    📡 Fetching meeting details...')
                    
                    response = teams_client._make_request('GET', endpoint)
                    
                    # Try to get online meeting ID from response
                    online_meeting = response.get('onlineMeeting', {})
                    online_meeting_id = online_meeting.get('id')
                    
                    # If not found, try to extract from join URL
                    if not online_meeting_id and response.get('onlineMeeting', {}).get('joinUrl'):
                        join_url = response.get('onlineMeeting', {}).get('joinUrl')
                        self.stdout.write(f'    📡 Got join URL but no ID, trying to get ID from join URL...')
                        # Try alternative approach: query online meetings by calendar event
                        try:
                            online_meeting_endpoint = f'/users/{user_email}/onlineMeetings?$filter=subject eq \'{response.get("subject")}\''
                            online_meetings_response = teams_client._make_request('GET', online_meeting_endpoint)
                            meetings = online_meetings_response.get('value', [])
                            if meetings:
                                online_meeting_id = meetings[0].get('id')
                                self.stdout.write(f'    ✓ Found online meeting ID via query')
                        except Exception as e:
                            self.stdout.write(f'    ⚠ Could not query online meetings: {str(e)}')
                    
                    if online_meeting_id:
                        self.stdout.write(f'    ✓ Found online_meeting_id: {online_meeting_id[:30]}...')
                        
                        if not dry_run:
                            conference.online_meeting_id = online_meeting_id
                            conference.save(update_fields=['online_meeting_id'])
                            self.stdout.write(self.style.SUCCESS('    ✓ Saved to database'))
                            
                            # Enable recording if requested
                            if enable_recording:
                                self.stdout.write('    🔴 Enabling auto-recording...')
                                recording_result = teams_client.enable_meeting_recording(
                                    online_meeting_id, 
                                    user_email
                                )
                                
                                if recording_result['success']:
                                    self.stdout.write(self.style.SUCCESS('    ✓ Recording enabled successfully'))
                                    conference.auto_recording_status = 'enabled'
                                    conference.auto_recording_enabled_at = timezone.now()
                                    conference.save(update_fields=['auto_recording_status', 'auto_recording_enabled_at'])
                                    fixed_count += 1
                                else:
                                    self.stdout.write(self.style.ERROR(f'    ✗ Recording failed: {recording_result.get("error")}'))
                                    error_count += 1
                        else:
                            self.stdout.write('    (Would save to database)')
                            if enable_recording:
                                self.stdout.write('    (Would enable recording)')
                    else:
                        self.stdout.write(self.style.WARNING('    ⚠ No online meeting ID found in response'))
                        error_count += 1
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'    ✗ Error: {str(e)}'))
                    logger.error(f'Error fixing conference {conference.id}: {str(e)}')
                    error_count += 1
        
        # Summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('\n📊 SUMMARY\n'))
        self.stdout.write(f'Conferences checked: {conferences.count()}')
        if enable_recording:
            self.stdout.write(f'Successfully fixed: {fixed_count}')
        self.stdout.write(f'Errors: {error_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 This was a DRY RUN - no changes were made'))
            self.stdout.write(self.style.WARNING('Run without --dry-run to apply changes'))
        
        if not enable_recording:
            self.stdout.write(self.style.WARNING('\n⚠️  Recording was NOT enabled'))
            self.stdout.write(self.style.WARNING('Run with --enable-recording to also enable recording'))
        
        self.stdout.write('\n' + '=' * 80 + '\n')

