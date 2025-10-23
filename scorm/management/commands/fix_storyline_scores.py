"""
Management command to fix Storyline SCORM score synchronization issues
Specifically designed to handle Storyline completion patterns and score extraction
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress, Topic
from scorm.score_sync_service import ScormScoreSyncService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix Storyline SCORM score synchronization issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Fix scores for specific topic ID',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Fix scores for specific user ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if scores already exist',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        user_id = options.get('user_id')
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🔧 Starting Storyline SCORM score fix {"(DRY RUN)" if dry_run else ""}'
            )
        )
        
        # Build query filters
        filters = {}
        if topic_id:
            filters['scorm_package__topic_id'] = topic_id
        if user_id:
            filters['user_id'] = user_id
            
        # Get all SCORM attempts
        attempts = ScormAttempt.objects.filter(**filters).select_related(
            'user', 'scorm_package__topic'
        ).order_by('user', 'scorm_package__topic', '-last_accessed')
        
        total_attempts = attempts.count()
        self.stdout.write(f"📊 Found {total_attempts} SCORM attempts to check")
        
        if total_attempts == 0:
            self.stdout.write(self.style.WARNING("No SCORM attempts found"))
            return
            
        fixed_count = 0
        storyline_fixed = 0
        sync_issues = 0
        
        for attempt in attempts:
            try:
                # Check if this is a Storyline attempt
                is_storyline = (
                    attempt.scorm_package.version == 'storyline' or
                    'storyline' in (attempt.scorm_package.package_file.name or '').lower() or
                    'scors' in (attempt.suspend_data or '') or
                    'qd"true' in (attempt.suspend_data or '')
                )
                
                if is_storyline:
                    self.stdout.write(f"\n🎯 Processing Storyline attempt {attempt.id} for user {attempt.user.username}")
                    
                    # Check for Storyline completion patterns
                    storyline_completed = False
                    if attempt.suspend_data:
                        storyline_patterns = [
                            'qd"true', 'qd":true', 'quiz_done":true', 
                            'assessment_done":true', 'lesson_done":true',
                            'complete":true', 'finished":true'
                        ]
                        storyline_completed = any(pattern in attempt.suspend_data for pattern in storyline_patterns)
                        
                        if storyline_completed:
                            self.stdout.write(f"  ✅ Found Storyline completion patterns in suspend_data")
                    
                    # Check if score needs to be synced
                    topic = attempt.scorm_package.topic
                    topic_progress = TopicProgress.objects.filter(
                        user=attempt.user,
                        topic=topic
                    ).first()
                    
                    needs_sync = False
                    sync_reason = ""
                    
                    if not topic_progress:
                        needs_sync = True
                        sync_reason = "No TopicProgress record exists"
                    elif storyline_completed and not topic_progress.completed:
                        needs_sync = True
                        sync_reason = "Storyline completed but TopicProgress not marked as completed"
                    elif attempt.score_raw and topic_progress.last_score != float(attempt.score_raw):
                        needs_sync = True
                        sync_reason = f"Score mismatch: ScormAttempt={attempt.score_raw}, TopicProgress={topic_progress.last_score}"
                    elif storyline_completed and not attempt.score_raw and not topic_progress.last_score:
                        needs_sync = True
                        sync_reason = "Storyline completed but no score in either ScormAttempt or TopicProgress"
                    
                    if needs_sync:
                        self.stdout.write(f"  🔧 {sync_reason}")
                        
                        if not dry_run:
                            # Force sync the score
                            if ScormScoreSyncService.sync_score(attempt, force=True):
                                self.stdout.write(f"  ✅ Successfully synced score for attempt {attempt.id}")
                                storyline_fixed += 1
                            else:
                                self.stdout.write(f"  ❌ Failed to sync score for attempt {attempt.id}")
                                sync_issues += 1
                        else:
                            self.stdout.write(f"  🔍 Would sync score for attempt {attempt.id}")
                            storyline_fixed += 1
                    else:
                        self.stdout.write(f"  ✅ No sync needed for attempt {attempt.id}")
                
                # Also check regular SCORM attempts
                else:
                    if not dry_run:
                        if ScormScoreSyncService.sync_score(attempt, force=force):
                            fixed_count += 1
                    else:
                        if ScormScoreSyncService.verify_score_consistency(attempt.user.id, attempt.scorm_package.topic.id):
                            fixed_count += 1
                            
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Error processing attempt {attempt.id}: {str(e)}")
                )
                sync_issues += 1
        
        # Summary
        self.stdout.write(f"\n📊 Summary:")
        self.stdout.write(f"  - Total attempts processed: {total_attempts}")
        self.stdout.write(f"  - Storyline fixes: {storyline_fixed}")
        self.stdout.write(f"  - Regular SCORM fixes: {fixed_count}")
        self.stdout.write(f"  - Sync issues: {sync_issues}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 DRY RUN - No changes were made"))
        else:
            self.stdout.write(self.style.SUCCESS("✅ Storyline SCORM score fixes completed"))
