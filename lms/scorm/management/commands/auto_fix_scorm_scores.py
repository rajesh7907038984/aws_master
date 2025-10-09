"""
Management command that automatically detects and fixes SCORM score issues.
This command can be run as a cron job to continuously maintain data integrity.

Usage:
    python manage.py auto_fix_scorm_scores
    python manage.py auto_fix_scorm_scores --recent 24  # Last 24 hours only
    python manage.py auto_fix_scorm_scores --all        # Check all attempts
    python manage.py auto_fix_scorm_scores --topic-id 48 # Specific topic
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from scorm.models import ScormAttempt
from scorm.dynamic_score_processor import auto_process_scorm_score
from scorm.real_time_validator import ScormScoreValidator
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Automatically detect and fix SCORM score synchronization issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recent',
            type=int,
            help='Process attempts from last N hours (default: 1)',
            default=1
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process all attempts (can be slow)',
        )
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Process only specific topic ID',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Process only specific user ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        recent_hours = options['recent']
        process_all = options['all']
        topic_id = options.get('topic_id')
        user_id = options.get('user_id')
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🔄 Auto-Fix SCORM Scores {"(DRY RUN)" if dry_run else ""}'
            )
        )
        
        # Build query filters
        filters = {}
        if topic_id:
            filters['scorm_package__topic_id'] = topic_id
        if user_id:
            filters['user_id'] = user_id
        
        if process_all:
            self.stdout.write("📊 Processing ALL SCORM attempts...")
            attempts = ScormAttempt.objects.filter(**filters)
        else:
            since = timezone.now() - timedelta(hours=recent_hours)
            filters['last_accessed__gte'] = since
            self.stdout.write(f"📊 Processing SCORM attempts from last {recent_hours} hours...")
            attempts = ScormAttempt.objects.filter(**filters)
        
        attempts = attempts.select_related('user', 'scorm_package__topic').order_by('-last_accessed')
        total_attempts = attempts.count()
        
        if total_attempts == 0:
            self.stdout.write(self.style.WARNING("No SCORM attempts found to process"))
            return
        
        self.stdout.write(f"🎯 Found {total_attempts} attempts to analyze")
        
        processed = 0
        issues_detected = 0
        auto_fixed = 0
        skipped = 0
        
        for attempt in attempts:
            try:
                processed += 1
                
                # Check if this attempt needs processing
                needs_processing = (
                    # Has suspend data but no score
                    (attempt.suspend_data and not attempt.score_raw) or
                    # Has score but status doesn't match
                    (attempt.score_raw and attempt.lesson_status == 'not_attempted') or
                    # TopicProgress is out of sync
                    self._check_topic_progress_sync(attempt)
                )
                
                if not needs_processing:
                    skipped += 1
                    continue
                
                issues_detected += 1
                self.stdout.write(f"\n🔍 Processing Attempt {attempt.id}:")
                self.stdout.write(f"  👤 User: {attempt.user.username}")
                self.stdout.write(f"  📚 Topic: {attempt.scorm_package.topic.title} (ID: {attempt.scorm_package.topic.id})")
                self.stdout.write(f"  📦 Package: {attempt.scorm_package.version} - {attempt.scorm_package.title}")
                self.stdout.write(f"  📊 Current: Status={attempt.lesson_status}, Score={attempt.score_raw}")
                
                if dry_run:
                    # Show what would be done
                    self.stdout.write(f"  🔮 Would process suspend data ({len(attempt.suspend_data) if attempt.suspend_data else 0} chars)")
                    auto_fixed += 1  # Count as "would fix"
                else:
                    # Actually process the attempt
                    success = auto_process_scorm_score(attempt)
                    
                    if success:
                        # Re-fetch to see changes
                        attempt.refresh_from_db()
                        self.stdout.write(f"  ✅ Fixed: Status={attempt.lesson_status}, Score={attempt.score_raw}")
                        auto_fixed += 1
                    else:
                        self.stdout.write(f"  ❌ Could not extract valid score from suspend data")
                
                # Progress indicator
                if processed % 10 == 0:
                    self.stdout.write(f"\n📈 Progress: {processed}/{total_attempts}")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Error processing attempt {attempt.id}: {str(e)}")
                )
        
        # Summary
        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("🎯 Auto-Fix Complete!"))
        self.stdout.write(f"  📊 Total processed: {processed}")
        self.stdout.write(f"  🔍 Issues detected: {issues_detected}")
        self.stdout.write(f"  ✅ Auto-fixed: {auto_fixed}")
        self.stdout.write(f"  ⏭️  Skipped (already good): {skipped}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  This was a DRY RUN - no changes were made"))
            self.stdout.write("Run without --dry-run to apply fixes")
        elif auto_fixed > 0:
            self.stdout.write(self.style.SUCCESS(f"\n✅ Successfully auto-fixed {auto_fixed} SCORM score issues"))
            
            # Clear application caches
            from django.core.cache import cache
            cache.clear()
            self.stdout.write("🗑️  Cleared application caches for immediate UI updates")
        
        # Recommendations for automation
        if auto_fixed > 0:
            self.stdout.write("\n🔧 Automation Recommendations:")
            self.stdout.write("  1. Add this command to cron: '*/15 * * * * python manage.py auto_fix_scorm_scores'")
            self.stdout.write("  2. Monitor logs for patterns in SCORM authoring tools")
            self.stdout.write("  3. Consider real-time processing in API handlers")
    
    def _check_topic_progress_sync(self, attempt):
        """Check if TopicProgress is out of sync with ScormAttempt"""
        if not attempt.score_raw:
            return False
            
        try:
            from courses.models import TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user=attempt.user,
                topic=attempt.scorm_package.topic
            ).first()
            
            if not topic_progress:
                return True  # Missing TopicProgress
                
            # Check score sync
            if topic_progress.last_score != float(attempt.score_raw):
                return True  # Score mismatch
                
            # Check completion sync
            if (attempt.lesson_status in ['passed', 'completed'] and 
                not topic_progress.completed):
                return True  # Completion mismatch
                
            return False  # All synced
            
        except Exception:
            return False
