from django.core.management.base import BaseCommand
from conferences.models import Conference, ConferenceChat
from conferences.views import rematch_unmatched_chat_messages
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Re-match chat messages that were incorrectly matched or unmatched'

    def add_arguments(self, parser):
        parser.add_argument(
            '--conference-id',
            type=int,
            required=True,
            help='Conference ID to re-match chat messages for',
        )
        parser.add_argument(
            '--reset-all',
            action='store_true',
            help='Reset all chat messages to unmatched first, then re-match',
        )

    def handle(self, *args, **options):
        conference_id = options['conference_id']
        reset_all = options['reset_all']
        
        try:
            conference = Conference.objects.get(id=conference_id)
        except Conference.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Conference {conference_id} not found'))
            return
        
        self.stdout.write(f'Re-matching chat messages for conference: {conference.title}')
        
        # Get current chat message stats
        total_messages = ConferenceChat.objects.filter(conference=conference).count()
        matched_messages = ConferenceChat.objects.filter(
            conference=conference,
            sender__isnull=False
        ).count()
        unmatched_messages = total_messages - matched_messages
        
        self.stdout.write(f'Current status: {total_messages} total, {matched_messages} matched, {unmatched_messages} unmatched')
        
        if reset_all:
            # Reset all chat messages to unmatched
            self.stdout.write('Resetting all chat messages to unmatched...')
            ConferenceChat.objects.filter(conference=conference).update(sender=None)
            self.stdout.write(self.style.SUCCESS('All chat messages reset to unmatched'))
        
        # Re-match chat messages
        self.stdout.write('Re-matching chat messages...')
        matched_count = rematch_unmatched_chat_messages(conference)
        
        # Get final stats
        final_matched = ConferenceChat.objects.filter(
            conference=conference,
            sender__isnull=False
        ).count()
        final_unmatched = total_messages - final_matched
        
        self.stdout.write(self.style.SUCCESS(f'Re-matching complete!'))
        self.stdout.write(f'Results: {matched_count} newly matched messages')
        self.stdout.write(f'Final status: {total_messages} total, {final_matched} matched, {final_unmatched} unmatched')
        
        # Show breakdown by user role
        instructor_messages = ConferenceChat.objects.filter(
            conference=conference,
            sender=conference.created_by
        ).count()
        
        learner_messages = ConferenceChat.objects.filter(
            conference=conference,
            sender__isnull=False,
            sender__role='learner'
        ).count()
        
        other_messages = ConferenceChat.objects.filter(
            conference=conference,
            sender__isnull=False
        ).exclude(sender=conference.created_by).exclude(sender__role='learner').count()
        
        self.stdout.write(f'Breakdown: {instructor_messages} instructor, {learner_messages} learner, {other_messages} other, {final_unmatched} unmatched') 