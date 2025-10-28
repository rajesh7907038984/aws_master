"""
Django management command to fix Storyline SCORM completion issues
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from scorm.storyline_completion_fixer import StorylineCompletionFixer
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Fix Storyline SCORM completion issues automatically'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Fix attempts for specific user (username)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fix all incomplete attempts across all users',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        fix_all = options.get('all')
        dry_run = options.get('dry_run')
        verbose = options.get('verbose')

        if verbose:
            logging.basicConfig(level=logging.INFO)

        self.stdout.write(
            self.style.SUCCESS('🔧 Storyline Completion Fixer Starting...')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  DRY RUN MODE - No changes will be made')
            )

        try:
            fixer = StorylineCompletionFixer()

            if username:
                # Fix specific user
                try:
                    user = User.objects.get(username=username)
                    self.stdout.write(f"Fixing attempts for user: {username}")
                    
                    if dry_run:
                        self._dry_run_user(user)
                    else:
                        fixed, skipped = fixer.fix_user_attempts(user)
                        self._show_results(fixed, skipped, fixer.errors)

                except User.DoesNotExist:
                    raise CommandError(f"User '{username}' does not exist")

            elif fix_all:
                # Fix all users
                self.stdout.write("Fixing all incomplete attempts...")
                
                if dry_run:
                    self._dry_run_all()
                else:
                    fixed, skipped = fixer.fix_all_incomplete_attempts()
                    self._show_results(fixed, skipped, fixer.errors)

            else:
                # Show help
                self.stdout.write(
                    self.style.WARNING(
                        'Please specify --username USERNAME or --all to fix attempts'
                    )
                )
                self.stdout.write('Use --help for more options')

        except Exception as e:
            raise CommandError(f"Error running fixer: {str(e)}")

    def _dry_run_user(self, user):
        """Show what would be fixed for a specific user"""
        from scorm.models import ScormAttempt
        
        incomplete_attempts = ScormAttempt.objects.filter(
            user=user,
            lesson_status='incomplete',
            suspend_data__isnull=False
        ).exclude(suspend_data='')

        self.stdout.write(f"\nFound {incomplete_attempts.count()} incomplete attempts:")
        
        fixer = StorylineCompletionFixer()
        would_fix = 0
        
        for attempt in incomplete_attempts:
            analysis = fixer._analyze_suspend_data(attempt.suspend_data)
            
            if analysis['should_be_completed']:
                would_fix += 1
                self.stdout.write(
                    f"  ✅ Would fix attempt {attempt.id} (Topic: {attempt.scorm_package.topic.title})"
                )
                self.stdout.write(f"      Reason: {analysis['reason']}")
            else:
                self.stdout.write(
                    f"  ⏭️  Would skip attempt {attempt.id} (Topic: {attempt.scorm_package.topic.title})"
                )
                self.stdout.write(f"      Reason: {analysis['reason']}")
        
        self.stdout.write(f"\nWould fix {would_fix} attempts")

    def _dry_run_all(self):
        """Show what would be fixed globally"""
        from scorm.models import ScormAttempt
        
        incomplete_attempts = ScormAttempt.objects.filter(
            lesson_status='incomplete',
            suspend_data__isnull=False
        ).exclude(suspend_data='')

        self.stdout.write(f"\nFound {incomplete_attempts.count()} incomplete attempts globally:")
        
        fixer = StorylineCompletionFixer()
        would_fix = 0
        users_affected = set()
        
        for attempt in incomplete_attempts:
            analysis = fixer._analyze_suspend_data(attempt.suspend_data)
            
            if analysis['should_be_completed']:
                would_fix += 1
                users_affected.add(attempt.user.username)
                self.stdout.write(
                    f"  ✅ Would fix attempt {attempt.id} (User: {attempt.user.username}, Topic: {attempt.scorm_package.topic.title})"
                )
                self.stdout.write(f"      Reason: {analysis['reason']}")
        
        self.stdout.write(f"\nWould fix {would_fix} attempts for {len(users_affected)} users")

    def _show_results(self, fixed, skipped, errors):
        """Show results of the fix operation"""
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Fix Complete!')
        )
        self.stdout.write(f"Fixed: {fixed} attempts")
        self.stdout.write(f"Skipped: {skipped} attempts")
        
        if errors:
            self.stdout.write(
                self.style.ERROR(f"Errors: {len(errors)}")
            )
            for error in errors:
                self.stdout.write(f"  ❌ {error}")
        
        if fixed > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    '🎉 Slide-based SCORM scores are now properly saved to database!'
                )
            )
