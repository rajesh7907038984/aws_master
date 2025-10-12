"""
Management command to debug SCORM score issues.
Provides detailed analysis of score discrepancies and sync problems.

Usage:
    python manage.py debug_scorm_scores
    python manage.py debug_scorm_scores --topic-id 123
    python manage.py debug_scorm_scores --user-id 456
    python manage.py debug_scorm_scores --attempt-id 789
    python manage.py debug_scorm_scores --show-all  # Show all attempts, not just problematic ones
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress
from decimal import Decimal
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Debug SCORM score synchronization issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Debug only the specified topic ID',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Debug only the specified user ID',
        )
        parser.add_argument(
            '--attempt-id',
            type=int,
            help='Debug only the specified attempt ID',
        )
        parser.add_argument(
            '--show-all',
            action='store_true',
            help='Show all attempts, not just problematic ones',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        user_id = options.get('user_id')
        attempt_id = options.get('attempt_id')
        show_all = options['show_all']
        
        self.stdout.write(
            self.style.SUCCESS(' SCORM Score Debug Analysis')
        )
        
        # Build query filters
        filters = {}
        if topic_id:
            filters['scorm_package__topic_id'] = topic_id
        if user_id:
            filters['user_id'] = user_id
        if attempt_id:
            filters['id'] = attempt_id
            
        # Get ScormAttempts
        attempts = ScormAttempt.objects.filter(
            **filters
        ).select_related('user', 'scorm_package__topic').order_by('-started_at')
        
        total_attempts = attempts.count()
        self.stdout.write(f" Analyzing {total_attempts} SCORM attempts")
        
        if total_attempts == 0:
            self.stdout.write(self.style.WARNING("No SCORM attempts found"))
            return
        
        issues_found = 0
        score_mismatches = 0
        missing_topic_progress = 0
        sync_issues = 0
        
        for attempt in attempts:
            # Get corresponding TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user=attempt.user,
                topic=attempt.scorm_package.topic
            ).first()
            
            has_issues = False
            issues = []
            
            # Check 1: ScormAttempt has score but no TopicProgress
            if attempt.score_raw and not topic_progress:
                has_issues = True
                issues.append(" ScormAttempt has score but TopicProgress doesn't exist")
                missing_topic_progress += 1
            
            # Check 2: Score mismatches between ScormAttempt and TopicProgress
            if attempt.score_raw and topic_progress:
                if topic_progress.last_score != float(attempt.score_raw):
                    has_issues = True
                    issues.append(f"⚠️  Score mismatch: ScormAttempt={attempt.score_raw}, TopicProgress.last_score={topic_progress.last_score}")
                    score_mismatches += 1
                
                # Check progress_data sync
                progress_data = topic_progress.progress_data or {}
                stored_attempt_id = progress_data.get('scorm_attempt_id')
                if stored_attempt_id != attempt.id:
                    has_issues = True
                    issues.append(f"⚠️  Progress data out of sync: stored_attempt_id={stored_attempt_id}, current_attempt_id={attempt.id}")
                    sync_issues += 1
            
            # Check 3: Completion status mismatches
            if attempt.lesson_status in ['completed', 'passed'] and topic_progress and not topic_progress.completed:
                has_issues = True
                issues.append(f"⚠️  Completion mismatch: SCORM={attempt.lesson_status}, TopicProgress.completed={topic_progress.completed}")
            
            # Check 4: Score exists but lesson_status is incomplete
            if attempt.score_raw and attempt.score_raw > 0 and attempt.lesson_status == 'incomplete':
                has_issues = True
                issues.append(f"⚠️  Score exists but lesson_status is incomplete: score={attempt.score_raw}")
            
            # Display results
            if has_issues or show_all:
                if has_issues:
                    issues_found += 1
                    
                self.stdout.write(f"\n{'' if has_issues else ''} Attempt ID: {attempt.id}")
                self.stdout.write(f"  👤 User: {attempt.user.username} (ID: {attempt.user.id})")
                self.stdout.write(f"  📚 Topic: {attempt.scorm_package.topic.title} (ID: {attempt.scorm_package.topic.id})")
                self.stdout.write(f"  📅 Started: {attempt.started_at}")
                self.stdout.write(f"   SCORM Data:")
                self.stdout.write(f"    - Score: {attempt.score_raw}")
                self.stdout.write(f"    - Status: {attempt.lesson_status}")
                self.stdout.write(f"    - Last Accessed: {attempt.last_accessed}")
                self.stdout.write(f"    - Total Time: {attempt.total_time}")
                
                if topic_progress:
                    self.stdout.write(f"  📈 TopicProgress Data:")
                    self.stdout.write(f"    - Last Score: {topic_progress.last_score}")
                    self.stdout.write(f"    - Best Score: {topic_progress.best_score}")
                    self.stdout.write(f"    - Completed: {topic_progress.completed}")
                    self.stdout.write(f"    - Last Accessed: {topic_progress.last_accessed}")
                    self.stdout.write(f"    - Attempts: {topic_progress.attempts}")
                    
                    # Show progress_data details
                    progress_data = topic_progress.progress_data or {}
                    self.stdout.write(f"    - Stored Attempt ID: {progress_data.get('scorm_attempt_id')}")
                    self.stdout.write(f"    - Sync Method: {progress_data.get('sync_method', 'unknown')}")
                    self.stdout.write(f"    - Last Updated: {progress_data.get('last_updated', 'unknown')}")
                else:
                    self.stdout.write(f"  📈 TopicProgress:  Not found")
                
                if issues:
                    self.stdout.write(f"  🚨 Issues:")
                    for issue in issues:
                        self.stdout.write(f"    {issue}")
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f"\n📈 Debug Analysis Complete!"))
        self.stdout.write(f"   Total attempts analyzed: {total_attempts}")
        self.stdout.write(f"   Attempts with issues: {issues_found}")
        self.stdout.write(f"  ⚠️  Score mismatches: {score_mismatches}")
        self.stdout.write(f"   Missing TopicProgress: {missing_topic_progress}")
        self.stdout.write(f"  🔄 Sync issues: {sync_issues}")
        
        if issues_found > 0:
            self.stdout.write(self.style.WARNING(f"\n⚠️  Found {issues_found} attempts with issues"))
            self.stdout.write("Run 'python manage.py sync_scorm_scores' to fix these issues")
        else:
            self.stdout.write(self.style.SUCCESS("\n No issues found - all SCORM scores are properly synchronized!"))
        
        # Additional recommendations
        if score_mismatches > 0 or missing_topic_progress > 0:
            self.stdout.write("\n🔧 Recommended actions:")
            self.stdout.write("  1. Run: python manage.py sync_scorm_scores --dry-run")
            self.stdout.write("  2. Review the changes that would be made")
            self.stdout.write("  3. Run: python manage.py sync_scorm_scores")
            self.stdout.write("  4. Clear application caches")
            
        if sync_issues > 0:
            self.stdout.write("\n⚠️  Sync issues detected:")
            self.stdout.write("  This usually indicates that multiple SCORM attempts exist for the same user/topic.")
            self.stdout.write("  The sync command will update to the latest attempt.")
