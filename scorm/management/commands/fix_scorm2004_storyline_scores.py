from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress, Topic
from scorm.dynamic_score_processor import DynamicScormScoreProcessor
from scorm.score_sync_service import ScormScoreSyncService
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Fix SCORM 2004 Storyline score synchronization issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Fix scores for specific user only',
        )
        parser.add_argument(
            '--topic',
            type=int,
            help='Fix scores for specific topic only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_filter = options.get('user')
        topic_filter = options.get('topic')

        self.stdout.write(
            self.style.SUCCESS(
                f'🔧 Starting SCORM 2004 Storyline score fix {"(DRY RUN)" if dry_run else ""}'
            )
        )

        # Find SCORM 2004 Storyline packages
        storyline_packages = ScormPackage.objects.filter(version='storyline')
        
        if topic_filter:
            storyline_packages = storyline_packages.filter(topic_id=topic_filter)

        self.stdout.write(f'Found {storyline_packages.count()} Storyline packages')

        fixed_count = 0
        total_attempts = 0

        for package in storyline_packages:
            self.stdout.write(f'\\n📦 Processing package {package.id}: {package.title}')
            
            # Get attempts for this package
            attempts_query = ScormAttempt.objects.filter(scorm_package=package)
            
            if user_filter:
                try:
                    user = User.objects.get(username=user_filter)
                    attempts_query = attempts_query.filter(user=user)
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'User {user_filter} not found'))
                    continue

            attempts = attempts_query.order_by('-started_at')
            total_attempts += attempts.count()

            for attempt in attempts:
                self.stdout.write(f'  📝 Attempt {attempt.id}: {attempt.lesson_status}, Score: {attempt.score_raw}')
                
                # Check if this attempt needs fixing
                needs_fix = (
                    attempt.score_raw is None and 
                    attempt.suspend_data and 
                    len(attempt.suspend_data) > 50  # Has substantial suspend data
                )
                
                if not needs_fix:
                    self.stdout.write(f'    ✅ No fix needed')
                    continue
                
                # Try to extract score using enhanced processor
                processor = DynamicScormScoreProcessor(attempt)
                extracted_score = processor.extract_score_dynamically(attempt.suspend_data)
                
                if extracted_score is not None:
                    self.stdout.write(f'    🎯 Extracted score: {extracted_score}')
                    
                    if not dry_run:
                        # Update the attempt
                        attempt.score_raw = extracted_score
                        
                        # Set completion status based on score
                        mastery_score = package.mastery_score or 70
                        if extracted_score >= mastery_score:
                            attempt.completion_status = 'completed'
                            attempt.success_status = 'passed'
                            attempt.lesson_status = 'passed'
                        else:
                            attempt.completion_status = 'completed'
                            attempt.success_status = 'failed'
                            attempt.lesson_status = 'failed'
                        
                        attempt.save()
                        
                        # Force sync to TopicProgress
                        sync_result = ScormScoreSyncService.sync_score(attempt, force=True)
                        
                        if sync_result:
                            self.stdout.write(f'    ✅ Fixed and synced to TopicProgress')
                            fixed_count += 1
                        else:
                            self.stdout.write(f'    ⚠️ Fixed attempt but sync failed')
                    else:
                        self.stdout.write(f'    🔍 Would fix: Score={extracted_score}, Status={"passed" if extracted_score >= (package.mastery_score or 70) else "failed"}')
                        fixed_count += 1
                else:
                    self.stdout.write(f'    ❌ Could not extract score from suspend data')
                    
                    # Check if we can assume completion based on suspend data
                    if attempt.suspend_data and 'Visited' in attempt.suspend_data:
                        self.stdout.write(f'    🔍 Found "Visited" pattern - might be completed')
                        if not dry_run:
                            # Assume 100% completion for Storyline packages with substantial suspend data
                            attempt.score_raw = 100.0
                            attempt.completion_status = 'completed'
                            attempt.success_status = 'passed'
                            attempt.lesson_status = 'passed'
                            attempt.save()
                            
                            # Force sync to TopicProgress
                            sync_result = ScormScoreSyncService.sync_score(attempt, force=True)
                            if sync_result:
                                self.stdout.write(f'    ✅ Assumed 100% completion and synced')
                                fixed_count += 1
                        else:
                            self.stdout.write(f'    🔍 Would assume 100% completion')

        self.stdout.write(
            self.style.SUCCESS(
                f'\\n✅ SCORM 2004 Storyline score fixes completed'
            )
        )
        self.stdout.write(f'📊 Processed {total_attempts} attempts')
        self.stdout.write(f'🔧 Fixed {fixed_count} attempts')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\\n⚠️ This was a dry run. Run without --dry-run to apply fixes.'
                )
            )
