"""
Management command to fix SCORM validation errors
Fixes attempts with missing navigation_history, detailed_tracking, session_data fields
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormAttempt
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix SCORM validation errors for existing attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--attempt-id',
            type=int,
            help='Fix specific attempt ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔧 SCORM Validation Error Fix Tool'))
        self.stdout.write('=' * 50)
        
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get attempts to fix
        attempts = ScormAttempt.objects.all()
        
        if options['attempt_id']:
            attempts = attempts.filter(id=options['attempt_id'])
        
        if not attempts.exists():
            self.stdout.write(self.style.WARNING('No attempts found to fix'))
            return
        
        self.stdout.write(f'Found {attempts.count()} attempts to process')
        
        fixed_count = 0
        error_count = 0
        
        for attempt in attempts:
            try:
                if self.fix_attempt_validation(attempt, dry_run):
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
            self.stdout.write(self.style.SUCCESS('Validation error fixes applied successfully!'))

    def fix_attempt_validation(self, attempt, dry_run=False):
        """Fix validation errors for a specific attempt"""
        
        # Check if attempt has validation issues
        needs_fix = False
        issues = []
        
        if not attempt.navigation_history:
            needs_fix = True
            issues.append('navigation_history is None/empty')
        if not attempt.detailed_tracking:
            needs_fix = True
            issues.append('detailed_tracking is None/empty')
        if not attempt.session_data:
            needs_fix = True
            issues.append('session_data is None/empty')
        
        if not needs_fix:
            return False  # Already OK
        
        if dry_run:
            self.stdout.write(f'  Would fix attempt {attempt.id}:')
            for issue in issues:
                self.stdout.write(f'    - {issue}')
            return True
        
        # Apply the fix
        try:
            with transaction.atomic():
                # Initialize missing fields
                if not attempt.navigation_history:
                    attempt.navigation_history = []
                if not attempt.detailed_tracking:
                    attempt.detailed_tracking = {}
                if not attempt.session_data:
                    attempt.session_data = {}
                
                # Save the attempt
                attempt.save()
                
                # Verify the fix
                attempt.refresh_from_db()
                if (attempt.navigation_history is not None and 
                    attempt.detailed_tracking is not None and 
                    attempt.session_data is not None):
                    return True
                else:
                    logger.warning(f"Validation fix verification failed for attempt {attempt.id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error fixing validation for attempt {attempt.id}: {str(e)}")
            raise
