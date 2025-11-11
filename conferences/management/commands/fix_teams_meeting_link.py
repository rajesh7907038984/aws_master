"""
Django management command to check and fix Teams conference meeting links.
Usage: python manage.py fix_teams_meeting_link <conference_id>
"""

from django.core.management.base import BaseCommand, CommandError
from conferences.models import Conference
from django.utils import timezone


class Command(BaseCommand):
    help = 'Check and fix Teams conference meeting links'

    def add_arguments(self, parser):
        parser.add_argument(
            'conference_id',
            type=int,
            nargs='?',
            help='Conference ID to check/fix (optional - if not provided, checks all Teams conferences)'
        )
        parser.add_argument(
            '--list-invalid',
            action='store_true',
            help='List all conferences with invalid Teams links'
        )

    def handle(self, *args, **options):
        conference_id = options.get('conference_id')
        list_invalid = options.get('list_invalid', False)

        if list_invalid:
            self.list_invalid_conferences()
            return

        if conference_id:
            self.check_single_conference(conference_id)
        else:
            self.check_all_conferences()

    def check_single_conference(self, conference_id):
        """Check a single conference's meeting link"""
        try:
            conference = Conference.objects.get(id=conference_id)
        except Conference.DoesNotExist:
            raise CommandError('Conference with ID {} does not exist'.format(conference_id))

        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS('CONFERENCE DETAILS - ID: {}'.format(conference.id)))
        self.stdout.write("=" * 80)
        self.stdout.write('Title: {}'.format(conference.title))
        self.stdout.write('Platform: {}'.format(conference.meeting_platform))
        self.stdout.write('Status: {}'.format(conference.meeting_status))
        self.stdout.write('Created by: {}'.format(
            conference.created_by.username if conference.created_by else 'N/A'
        ))
        self.stdout.write('-' * 80)
        self.stdout.write('Meeting ID: {}'.format(conference.meeting_id or 'NOT SET'))
        self.stdout.write('Meeting Link: {}'.format(conference.meeting_link or 'NOT SET'))
        self.stdout.write('-' * 80)

        # Validate the meeting link
        is_valid, error_message = self.validate_teams_link(conference.meeting_link)
        
        if is_valid:
            self.stdout.write(self.style.SUCCESS('\n✓ Meeting link is VALID'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ Meeting link is INVALID'))
            self.stdout.write(self.style.ERROR('  Reason: {}'.format(error_message)))
            
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write(self.style.WARNING('HOW TO FIX:'))
            self.stdout.write('=' * 80)
            self.stdout.write('1. Go to: https://vle.nexsy.io/admin/conferences/conference/{}/change/'.format(conference.id))
            self.stdout.write('2. Use the Teams integration to create a new meeting link, OR')
            self.stdout.write('3. Create a meeting in Microsoft Teams and paste the join link')
            self.stdout.write('\nProper Teams meeting link format:')
            self.stdout.write('  https://teams.microsoft.com/l/meetup-join/19%3ameeting_xxxxx...')
            self.stdout.write('\nDO NOT USE:')
            self.stdout.write('  - "Meet Now" links')
            self.stdout.write('  - Instant meeting links')
            self.stdout.write('  - Chat links')

    def check_all_conferences(self):
        """Check all Teams conferences"""
        teams_conferences = Conference.objects.filter(meeting_platform='teams')
        total = teams_conferences.count()
        
        self.stdout.write('=' * 80)
        self.stdout.write('CHECKING ALL TEAMS CONFERENCES')
        self.stdout.write('=' * 80)
        self.stdout.write('Total Teams conferences: {}\n'.format(total))
        
        valid_count = 0
        invalid_count = 0
        
        for conference in teams_conferences:
            is_valid, error_message = self.validate_teams_link(conference.meeting_link)
            
            if is_valid:
                valid_count += 1
                self.stdout.write(self.style.SUCCESS('✓ ID {}: {} - VALID'.format(
                    conference.id, conference.title[:50]
                )))
            else:
                invalid_count += 1
                self.stdout.write(self.style.ERROR('✗ ID {}: {} - INVALID ({})'.format(
                    conference.id, conference.title[:50], error_message
                )))
        
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write('SUMMARY')
        self.stdout.write('=' * 80)
        self.stdout.write('Valid: {}'.format(valid_count))
        self.stdout.write('Invalid: {}'.format(invalid_count))
        self.stdout.write('Total: {}'.format(total))

    def list_invalid_conferences(self):
        """List all conferences with invalid Teams links"""
        teams_conferences = Conference.objects.filter(meeting_platform='teams')
        
        invalid_conferences = []
        for conference in teams_conferences:
            is_valid, error_message = self.validate_teams_link(conference.meeting_link)
            if not is_valid:
                invalid_conferences.append((conference, error_message))
        
        if not invalid_conferences:
            self.stdout.write(self.style.SUCCESS('\n✓ All Teams conferences have valid meeting links!'))
            return
        
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.WARNING('CONFERENCES WITH INVALID TEAMS LINKS'))
        self.stdout.write('=' * 80)
        
        for conference, error_message in invalid_conferences:
            self.stdout.write('\nID: {}'.format(conference.id))
            self.stdout.write('Title: {}'.format(conference.title))
            self.stdout.write('Link: {}'.format(conference.meeting_link or 'NOT SET'))
            self.stdout.write('Issue: {}'.format(error_message))
            self.stdout.write('Fix URL: https://vle.nexsy.io/admin/conferences/conference/{}/change/'.format(
                conference.id
            ))
            self.stdout.write('-' * 80)
        
        self.stdout.write('\nTotal invalid: {}'.format(len(invalid_conferences)))

    def validate_teams_link(self, meeting_link):
        """
        Validate a Teams meeting link
        Returns: (is_valid: bool, error_message: str)
        """
        if not meeting_link:
            return False, "No meeting link configured"
        
        if meeting_link.strip() == '':
            return False, "Meeting link is empty"
        
        if 'teams.microsoft.com' not in meeting_link and 'teams.live.com' not in meeting_link:
            return False, "Not a Teams URL"
        
        # Check for invalid "meet-now" links
        if 'meet-now' in meeting_link.lower() or '/v2/meet/' in meeting_link:
            return False, "Invalid 'meet-now' instant meeting link"
        
        # Check for proper meeting join link format
        if not ('/l/meetup-join/' in meeting_link or '/meetup-join/' in meeting_link):
            return False, "Not a proper meeting join link format"
        
        return True, ""

