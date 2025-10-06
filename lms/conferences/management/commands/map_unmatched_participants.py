from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q
import logging

from conferences.models import Conference, ConferenceAttendance, ConferenceParticipant
from users.models import CustomUser as User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Map unmatched conference participants to LMS users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--conference-id',
            type=int,
            help='Conference ID to check for unmatched participants',
        )
        parser.add_argument(
            '--list-unmatched',
            action='store_true',
            help='List all unmatched participants for the conference',
        )
        parser.add_argument(
            '--auto-map',
            action='store_true',
            help='Attempt automatic mapping using enhanced fuzzy matching',
        )
        parser.add_argument(
            '--participant-name',
            type=str,
            help='Specific participant name to map',
        )
        parser.add_argument(
            '--username',
            type=str,
            help='LMS username to map the participant to',
        )

    def handle(self, *args, **options):
        conference_id = options.get('conference_id')
        list_unmatched = options.get('list_unmatched')
        auto_map = options.get('auto_map')
        participant_name = options.get('participant_name')
        username = options.get('username')

        if not conference_id:
            raise CommandError('Please specify --conference-id')

        try:
            conference = Conference.objects.get(id=conference_id)
        except Conference.DoesNotExist:
            raise CommandError(f'Conference with ID {conference_id} does not exist')

        self.stdout.write(f'Working with conference: {conference.title}')

        if list_unmatched:
            self.list_unmatched_participants(conference)
        elif auto_map:
            self.auto_map_participants(conference)
        elif participant_name and username:
            self.manual_map_participant(conference, participant_name, username)
        else:
            self.stdout.write('Available options:')
            self.stdout.write('  --list-unmatched: Show unmatched participants')
            self.stdout.write('  --auto-map: Attempt automatic mapping')
            self.stdout.write('  --participant-name "Name" --username "username": Manual mapping')

    def list_unmatched_participants(self, conference):
        """List unmatched participants with detailed suggestions"""
        self.stdout.write(self.style.WARNING('\n📋 UNMATCHED PARTICIPANTS:'))
        
        # Get unmatched ConferenceParticipant records (user=None)
        unmatched_participants = ConferenceParticipant.objects.filter(
            conference=conference,
            user__isnull=True
        )
        
        if not unmatched_participants.exists():
            self.stdout.write(self.style.SUCCESS(' All participants are already mapped!'))
            return

        self.stdout.write(f'Found {unmatched_participants.count()} unmatched participants:\n')
        
        for i, participant in enumerate(unmatched_participants, 1):
            self.stdout.write(f'{i}. {self.style.WARNING(participant.display_name)}')
            if participant.email_address:
                self.stdout.write(f'   Email: {participant.email_address}')
            self.stdout.write(f'   Duration: {participant.total_duration_minutes} minutes')
            self.stdout.write(f'   Join Time: {participant.join_timestamp}')
            self.stdout.write(f'   Platform ID: {participant.platform_participant_id}')
            
            # Show potential matches
            suggestions = self.find_potential_matches(participant.display_name, participant.email_address, conference)
            if suggestions:
                self.stdout.write('   Potential matches:')
                for j, suggestion in enumerate(suggestions, 1):
                    self.stdout.write(f'     {j}. {suggestion}')
            else:
                self.stdout.write('   No potential matches found')
            
            self.stdout.write('')  # Empty line

    def find_potential_matches(self, participant_name, participant_email, conference):
        """Find potential user matches for a participant"""
        suggestions = []
        
        if not participant_name:
            return suggestions
            
        name_parts = participant_name.split()
        if len(name_parts) < 2:
            return suggestions
            
        first_name = name_parts[0]
        last_name = name_parts[-1]
        
        # 1. Exact name matches within branch
        if conference.created_by.branch:
            exact_matches = User.objects.filter(
                branch=conference.created_by.branch,
                first_name__iexact=first_name,
                last_name__iexact=last_name
            )
            for match in exact_matches:
                suggestions.append(f"EXACT: {match.username} ({match.get_full_name()}) - {match.email} - {match.role}")
        
        # 2. Partial matches within branch (learners only)
        if conference.created_by.branch:
            partial_matches = User.objects.filter(
                branch=conference.created_by.branch,
                role='learner'
            ).filter(
                Q(first_name__icontains=first_name) |
                Q(last_name__icontains=last_name)
            )[:3]
            for match in partial_matches:
                suggestions.append(f"PARTIAL: {match.username} ({match.get_full_name()}) - {match.email}")
        
        # 3. Email matches
        if participant_email:
            email_matches = User.objects.filter(email__iexact=participant_email)
            for match in email_matches:
                branch_name = match.branch.name if match.branch else 'No branch'
                suggestions.append(f"EMAIL: {match.username} ({match.get_full_name()}) - {match.email} - {branch_name}")
        
        # 4. Username similarity
        clean_name = participant_name.replace(' ', '').lower()
        username_matches = User.objects.filter(
            username__icontains=clean_name[:6]  # First 6 chars of clean name
        )[:2]
        for match in username_matches:
            branch_name = match.branch.name if match.branch else 'No branch'
            suggestions.append(f"USERNAME: {match.username} ({match.get_full_name()}) - {match.email} - {branch_name}")
            
        return suggestions

    def auto_map_participants(self, conference):
        """Attempt automatic mapping using enhanced fuzzy matching"""
        self.stdout.write(self.style.WARNING('\n🤖 ATTEMPTING AUTO-MAPPING:'))
        
        unmatched_participants = ConferenceParticipant.objects.filter(
            conference=conference,
            user__isnull=True
        )
        
        if not unmatched_participants.exists():
            self.stdout.write(self.style.SUCCESS(' All participants are already mapped!'))
            return

        mapped_count = 0
        
        for participant in unmatched_participants:
            user = self.enhanced_participant_matching(participant, conference)
            if user:
                # Create attendance record
                attendance, created = ConferenceAttendance.objects.get_or_create(
                    conference=conference,
                    user=user,
                    defaults={
                        'participant_id': participant.platform_participant_id,
                        'join_time': participant.join_timestamp,
                        'leave_time': participant.leave_timestamp,
                        'duration_minutes': participant.total_duration_minutes or 0,
                        'attendance_status': 'present',
                        'device_info': {
                            'matched_via': 'auto_mapping_command',
                            'original_zoom_name': participant.display_name,
                            'mapping_timestamp': timezone.now().isoformat(),
                            **participant.tracking_data
                        }
                    }
                )
                
                # Update participant record
                participant.user = user
                participant.save(update_fields=['user'])
                
                mapped_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f' Mapped: {participant.display_name} -> {user.username} ({user.get_full_name()})')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f' Could not auto-map: {participant.display_name}')
                )
        
        self.stdout.write(f'\nAuto-mapped {mapped_count} out of {unmatched_participants.count()} participants')

    def enhanced_participant_matching(self, participant, conference):
        """Enhanced matching logic similar to the sync function"""
        participant_name = participant.display_name
        participant_email = participant.email_address
        
        if not participant_name:
            return None
            
        # Try the same enhanced matching logic as in the sync function
        name_parts = participant_name.split()
        if len(name_parts) < 2:
            return None
            
        first_name = name_parts[0]
        last_name = name_parts[-1]
        
        # Method 1: Exact match within branch
        if conference.created_by.branch:
            exact_matches = User.objects.filter(
                branch=conference.created_by.branch,
                first_name__iexact=first_name,
                last_name__iexact=last_name
            )
            if exact_matches.count() == 1:
                return exact_matches.first()
        
        # Method 2: Email match
        if participant_email:
            email_match = User.objects.filter(email__iexact=participant_email).first()
            if email_match and email_match.branch == conference.created_by.branch:
                return email_match
        
        # Method 3: Learner-specific match within branch
        if conference.created_by.branch:
            learner_matches = User.objects.filter(
                branch=conference.created_by.branch,
                role='learner',
                first_name__icontains=first_name,
                last_name__icontains=last_name
            )
            if learner_matches.count() == 1:
                return learner_matches.first()
        
        return None

    def manual_map_participant(self, conference, participant_name, username):
        """Manually map a participant to a user"""
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User with username "{username}" does not exist')
        
        # Find the participant
        participant = ConferenceParticipant.objects.filter(
            conference=conference,
            display_name__icontains=participant_name,
            user__isnull=True
        ).first()
        
        if not participant:
            raise CommandError(f'No unmatched participant found with name containing "{participant_name}"')
        
        # Create attendance record
        attendance, created = ConferenceAttendance.objects.get_or_create(
            conference=conference,
            user=user,
            defaults={
                'participant_id': participant.platform_participant_id,
                'join_time': participant.join_timestamp,
                'leave_time': participant.leave_timestamp,
                'duration_minutes': participant.total_duration_minutes or 0,
                'attendance_status': 'present',
                'device_info': {
                    'matched_via': 'manual_mapping_command',
                    'original_zoom_name': participant.display_name,
                    'mapping_timestamp': timezone.now().isoformat(),
                    'mapped_by': 'admin_command',
                    **participant.tracking_data
                }
            }
        )
        
        # Update participant record
        participant.user = user
        participant.save(update_fields=['user'])
        
        self.stdout.write(
            self.style.SUCCESS(f' Successfully mapped: {participant.display_name} -> {user.username} ({user.get_full_name()})')
        ) 