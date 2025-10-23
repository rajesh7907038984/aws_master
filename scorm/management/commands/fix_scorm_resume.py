"""
Management command to fix SCORM resume functionality issues
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormAttempt, ScormPackage
from scorm.enhanced_resume_handler import handle_scorm_resume
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix SCORM resume functionality issues for existing attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix resume for specific SCORM package ID'
        )
        parser.add_argument(
            '--attempt-id',
            type=int,
            help='Fix resume for specific attempt ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force fix even for attempts that seem OK'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔧 SCORM Resume Fix Tool'))
        self.stdout.write('=' * 50)
        
        dry_run = options['dry_run']
        force = options['force']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get attempts to fix
        attempts = self.get_attempts_to_fix(options)
        
        if not attempts.exists():
            self.stdout.write(self.style.WARNING('No attempts found to fix'))
            return
        
        self.stdout.write(f'Found {attempts.count()} attempts to process')
        
        fixed_count = 0
        error_count = 0
        
        for attempt in attempts:
            try:
                if self.fix_attempt_resume(attempt, dry_run, force):
                    fixed_count += 1
                    self.stdout.write(f'✅ Fixed attempt {attempt.id} (User: {attempt.user.username}, Package: {attempt.scorm_package.id})')
                else:
                    self.stdout.write(f'ℹ️  Attempt {attempt.id} already OK')
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'❌ Error fixing attempt {attempt.id}: {str(e)}'))
        
        self.stdout.write('=' * 50)
        self.stdout.write(f'Summary: {fixed_count} fixed, {error_count} errors')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('Resume fixes applied successfully!'))

    def get_attempts_to_fix(self, options):
        """Get attempts that need resume fixes"""
        attempts = ScormAttempt.objects.select_related('scorm_package', 'user').all()
        
        if options['package_id']:
            attempts = attempts.filter(scorm_package_id=options['package_id'])
        
        if options['attempt_id']:
            attempts = attempts.filter(id=options['attempt_id'])
        
        # Filter for incomplete attempts that might have resume issues
        attempts = attempts.filter(
            lesson_status__in=['incomplete', 'not_attempted']
        )
        
        return attempts

    def fix_attempt_resume(self, attempt, dry_run=False, force=False):
        """Fix resume functionality for a specific attempt"""
        
        # Check if attempt already has proper resume data
        has_proper_resume = (
            attempt.entry == 'resume' and
            attempt.cmi_data and
            (
                (attempt.scorm_package.version == '1.2' and 'cmi.core.entry' in attempt.cmi_data) or
                (attempt.scorm_package.version == '2004' and 'cmi.entry' in attempt.cmi_data)
            )
        )
        
        if has_proper_resume and not force:
            return False  # Already OK
        
        if dry_run:
            self.stdout.write(f'  Would fix attempt {attempt.id}:')
            self.stdout.write(f'    Current entry: {attempt.entry}')
            self.stdout.write(f'    Has CMI data: {bool(attempt.cmi_data)}')
            self.stdout.write(f'    Lesson location: {attempt.lesson_location or "None"}')
            self.stdout.write(f'    Suspend data: {len(attempt.suspend_data) if attempt.suspend_data else 0} chars')
            return True
        
        # Apply the enhanced resume handler
        try:
            with transaction.atomic():
                success = handle_scorm_resume(attempt)
                
                if success:
                    # Verify the fix
                    attempt.refresh_from_db()
                    if attempt.entry == 'resume' and attempt.cmi_data:
                        return True
                    else:
                        logger.warning(f"Resume fix verification failed for attempt {attempt.id}")
                        return False
                else:
                    logger.warning(f"Enhanced resume handler failed for attempt {attempt.id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error fixing resume for attempt {attempt.id}: {str(e)}")
            raise
