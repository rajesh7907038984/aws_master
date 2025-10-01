from django.core.management.base import BaseCommand
from conferences.models import Conference
from conferences.views import clean_zoom_url_format
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up Zoom URLs to simple format (domain/j/meeting_id?pwd=password)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--conference-id',
            type=int,
            help='Clean only a specific conference by ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        conference_id = options.get('conference_id')
        
        # Get conferences to process
        if conference_id:
            conferences = Conference.objects.filter(id=conference_id, meeting_platform='zoom')
            if not conferences.exists():
                self.stdout.write(
                    self.style.ERROR(f'Conference with ID {conference_id} not found or not a Zoom meeting')
                )
                return
        else:
            conferences = Conference.objects.filter(
                meeting_platform='zoom',
                meeting_link__isnull=False
            ).exclude(meeting_link='')
        
        total_conferences = conferences.count()
        self.stdout.write(f'Found {total_conferences} Zoom conferences to process')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        updated_count = 0
        
        for conference in conferences:
            original_link = conference.meeting_link
            
            # Skip if already in simple format (only has domain, meeting ID, and optional password)
            if ('uname=' not in original_link and 
                'confno=' not in original_link and 
                'stype=' not in original_link and 
                'webclient=' not in original_link and
                'fromPWA=' not in original_link and
                '_x_zm_rtaid=' not in original_link and
                '_x_zm_rhtaid=' not in original_link and
                'role=' not in original_link):
                self.stdout.write(f'Conference {conference.id}: Already in clean format')
                continue
            
            # Generate clean URL
            clean_link = clean_zoom_url_format(conference)
            
            if clean_link != original_link:
                self.stdout.write(f'Conference {conference.id} ({conference.title}):')
                self.stdout.write(f'  FROM: {original_link}')
                self.stdout.write(f'  TO:   {clean_link}')
                
                if not dry_run:
                    conference.meeting_link = clean_link
                    conference.save(update_fields=['meeting_link'])
                    self.stdout.write(self.style.SUCCESS('  ✓ Updated'))
                else:
                    self.stdout.write(self.style.WARNING('  → Would update (dry run)'))
                
                updated_count += 1
            else:
                self.stdout.write(f'Conference {conference.id}: No changes needed')
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'DRY RUN COMPLETE: {updated_count} conferences would be updated')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'COMPLETE: Updated {updated_count} conferences')
            ) 