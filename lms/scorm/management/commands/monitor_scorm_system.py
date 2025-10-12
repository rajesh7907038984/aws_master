"""
SCORM System Monitoring and Validation Command
Provides comprehensive monitoring for SCORM uploads and learner progress
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from scorm.models import ScormAttempt, ScormPackage
from scorm.score_sync_service import ScormScoreSyncService
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Monitor and validate SCORM system health for ongoing uploads and learner interactions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--validate-recent',
            type=int,
            default=24,
            help='Validate SCORM attempts from the last N hours (default: 24)'
        )
        parser.add_argument(
            '--fix-issues',
            action='store_true',
            help='Automatically fix found issues'
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Monitor specific SCORM package only'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Monitor specific user only'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== SCORM System Monitor Started ==='))
        
        hours = options['validate_recent']
        fix_issues = options['fix_issues']
        package_id = options.get('package_id')
        user_id = options.get('user_id')
        
        since = timezone.now() - timedelta(hours=hours)
        
        # Build query filters
        filters = {'last_accessed__gte': since}
        if package_id:
            filters['scorm_package_id'] = package_id
        if user_id:
            filters['user_id'] = user_id
        
        # Get recent SCORM attempts
        recent_attempts = ScormAttempt.objects.filter(**filters).order_by('-last_accessed')
        
        self.stdout.write(f'Monitoring {recent_attempts.count()} SCORM attempts from last {hours} hours')
        
        # Statistics
        stats = {
            'total_attempts': recent_attempts.count(),
            'with_scores': 0,
            'without_scores': 0,
            'synced_successfully': 0,
            'sync_failed': 0,
            'issues_found': 0,
            'issues_fixed': 0,
            'new_packages': 0
        }
        
        # Check recent package uploads
        recent_packages = ScormPackage.objects.filter(created_at__gte=since)
        stats['new_packages'] = recent_packages.count()
        
        if stats['new_packages'] > 0:
            self.stdout.write(f'\\n=== New SCORM Packages ({stats["new_packages"]}) ===')
            for pkg in recent_packages:
                self.stdout.write(f'  Package {pkg.id}: Topic {pkg.topic_id} - {pkg.title}')
                self.stdout.write(f'    Launch URL: {pkg.launch_url}')
                self.stdout.write(f'    Version: {pkg.version}')
                
                # Check if package has attempts
                pkg_attempts = ScormAttempt.objects.filter(scorm_package=pkg).count()
                self.stdout.write(f'    Attempts: {pkg_attempts}')
        
        # Check attempts
        self.stdout.write(f'\\n=== Analyzing Recent Attempts ===')
        
        for attempt in recent_attempts:
            has_score = attempt.score_raw is not None
            stats['with_scores' if has_score else 'without_scores'] += 1
            
            # Check if TopicProgress exists
            topic_progress = TopicProgress.objects.filter(
                user=attempt.user,
                topic=attempt.scorm_package.topic
            ).first()
            
            # Calculate interaction time
            interaction_time = 0
            if attempt.last_accessed and attempt.started_at:
                interaction_time = (attempt.last_accessed - attempt.started_at).total_seconds()
            
            # Detect issues
            issues = []
            
            # Issue 1: User has meaningful interaction but no TopicProgress
            if interaction_time > 30 and not topic_progress:
                issues.append('Missing TopicProgress despite user interaction')
            
            # Issue 2: User has score in ScormAttempt but not in TopicProgress
            if has_score and topic_progress and topic_progress.last_score != float(attempt.score_raw):
                issues.append(f'Score mismatch: Attempt={attempt.score_raw}, TopicProgress={topic_progress.last_score}')
            
            # Issue 3: User has CMI data indicating interaction but no score/progress sync
            if (attempt.cmi_data and len(attempt.cmi_data) > 5 and 
                interaction_time > 60 and not has_score and 
                (not topic_progress or topic_progress.last_score is None)):
                issues.append('Has CMI interaction data but no score sync')
            
            # Issue 4: Lesson status shows progress but TopicProgress not updated
            if (attempt.lesson_status in ['completed', 'passed', 'failed'] and
                (not topic_progress or not topic_progress.completed)):
                issues.append(f'Lesson status "{attempt.lesson_status}" but TopicProgress not completed')
            
            if issues:
                stats['issues_found'] += len(issues)
                self.stdout.write(
                    self.style.WARNING(f'  ISSUES for Attempt {attempt.id} (User: {attempt.user.username}):')
                )
                for issue in issues:
                    self.stdout.write(f'    - {issue}')
                
                # Try to fix issues if requested
                if fix_issues:
                    self.stdout.write('    Attempting to fix...')
                    try:
                        with transaction.atomic():
                            # Force sync the score
                            sync_success = ScormScoreSyncService.sync_score(attempt, force=True)
                            if sync_success:
                                stats['issues_fixed'] += 1
                                stats['synced_successfully'] += 1
                                self.stdout.write(
                                    self.style.SUCCESS(f'    ✓ Fixed via force sync')
                                )
                            else:
                                stats['sync_failed'] += 1
                                self.stdout.write(
                                    self.style.ERROR(f'    ✗ Force sync failed')
                                )
                    except Exception as e:
                        stats['sync_failed'] += 1
                        self.stdout.write(
                            self.style.ERROR(f'    ✗ Fix failed: {str(e)}')
                        )
            else:
                # No issues, but try sync anyway to ensure consistency
                try:
                    sync_success = ScormScoreSyncService.sync_score(attempt)
                    stats['synced_successfully' if sync_success else 'sync_failed'] += 1
                except Exception as e:
                    stats['sync_failed'] += 1
                    logger.error(f'Sync failed for attempt {attempt.id}: {e}')
        
        # Summary
        self.stdout.write(f'\\n=== Summary ===')
        for key, value in stats.items():
            label = key.replace('_', ' ').title()
            style = self.style.SUCCESS if 'success' in key or 'fixed' in key else (
                self.style.WARNING if 'issue' in key or 'fail' in key else self.style.HTTP_INFO
            )
            self.stdout.write(style(f'{label}: {value}'))
        
        # Recommendations
        if stats['issues_found'] > 0:
            self.stdout.write(f'\\n=== Recommendations ===')
            if not fix_issues:
                self.stdout.write('  • Run with --fix-issues to automatically resolve sync problems')
            
            if stats['sync_failed'] > 0:
                self.stdout.write('  • Check server logs for detailed error information')
                self.stdout.write('  • Verify database connectivity and permissions')
            
            if stats['new_packages'] > 0:
                self.stdout.write('  • Test new SCORM packages thoroughly')
                self.stdout.write('  • Verify S3 content extraction completed successfully')
        
        # Future monitoring suggestion
        if stats['total_attempts'] > 0:
            self.stdout.write(f'\\n=== Future Monitoring ===')
            self.stdout.write(f'  • Set up cron job to run this command every hour:')
            self.stdout.write(f'    python manage.py monitor_scorm_system --validate-recent=1 --fix-issues')
            self.stdout.write(f'  • Monitor logs for automatic fixes and escalate if sync_failed increases')
        
        self.stdout.write(self.style.SUCCESS('\\n=== SCORM System Monitor Complete ==='))
