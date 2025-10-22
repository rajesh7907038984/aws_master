#!/usr/bin/env python3
"""
Management command to fix SCORM 1.2 progress tracking issues
Recalculates and updates progress data for existing SCORM 1.2 attempts
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix SCORM 1.2 progress tracking by recalculating progress data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix progress for specific SCORM package ID'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Fix progress for specific user ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if progress data already exists'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔧 SCORM 1.2 Progress Fix Tool')
        )
        self.stdout.write('=' * 50)
        
        # Get SCORM 1.2 attempts
        attempts_query = ScormAttempt.objects.filter(
            scorm_package__version='1.2'
        ).select_related('user', 'scorm_package', 'scorm_package__topic')
        
        if options['package_id']:
            attempts_query = attempts_query.filter(scorm_package_id=options['package_id'])
            self.stdout.write(f'📦 Filtering by package ID: {options["package_id"]}')
        
        if options['user_id']:
            attempts_query = attempts_query.filter(user_id=options['user_id'])
            self.stdout.write(f'👤 Filtering by user ID: {options["user_id"]}')
        
        attempts = attempts_query.order_by('user__username', 'scorm_package__topic__title')
        
        if not attempts.exists():
            self.stdout.write(
                self.style.WARNING('❌ No SCORM 1.2 attempts found matching criteria')
            )
            return
        
        self.stdout.write(f'📊 Found {attempts.count()} SCORM 1.2 attempts to process')
        self.stdout.write('')
        
        fixed_count = 0
        skipped_count = 0
        error_count = 0
        
        for attempt in attempts:
            try:
                result = self._fix_attempt_progress(attempt, options)
                if result == 'fixed':
                    fixed_count += 1
                elif result == 'skipped':
                    skipped_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error processing attempt {attempt.id}: {str(e)}')
                )
                error_count += 1
        
        # Summary
        self.stdout.write('')
        self.stdout.write('=' * 50)
        self.stdout.write(f'📈 Summary:')
        self.stdout.write(f'   ✅ Fixed: {fixed_count}')
        self.stdout.write(f'   ⏭️  Skipped: {skipped_count}')
        self.stdout.write(f'   ❌ Errors: {error_count}')
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('🔍 DRY RUN - No changes were made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ SCORM 1.2 progress fix completed')
            )

    def _fix_attempt_progress(self, attempt, options):
        """Fix progress data for a single SCORM 1.2 attempt"""
        try:
            # Calculate progress percentage
            progress_percentage = self._calculate_scorm_1_2_progress(attempt)
            
            # Get or create topic progress
            topic = attempt.scorm_package.topic
            progress, created = TopicProgress.objects.get_or_create(
                user=attempt.user,
                topic=topic
            )
            
            # Check if we should skip this attempt
            if not options['force'] and progress.progress_data.get('progress_percentage') is not None:
                self.stdout.write(
                    f'⏭️  Skipping attempt {attempt.id} (user: {attempt.user.username}) - progress already calculated'
                )
                return 'skipped'
            
            # Update progress data
            progress_data = {
                'scorm_attempt_id': attempt.id,
                'lesson_status': attempt.lesson_status,
                'completion_status': attempt.completion_status,
                'success_status': attempt.success_status,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'score_max': float(attempt.score_max) if attempt.score_max else None,
                'score_min': float(attempt.score_min) if attempt.score_min else None,
                'score_scaled': float(attempt.score_scaled) if attempt.score_scaled else None,
                'total_time': attempt.total_time,
                'session_time': attempt.session_time,
                'lesson_location': attempt.lesson_location,
                'suspend_data': attempt.suspend_data,
                'entry': attempt.entry,
                'exit_mode': attempt.exit_mode,
                'progress_percentage': progress_percentage,
                'completion_percent': progress_percentage,
                'last_updated': timezone.now().isoformat(),
                'sync_method': 'fix_scorm_1_2_progress',
                'sync_timestamp': timezone.now().isoformat(),
            }
            
            if not options['dry_run']:
                with transaction.atomic():
                    progress.progress_data = progress_data
                    
                    # Update completion status
                    is_completed = attempt.lesson_status in ['completed', 'passed']
                    if is_completed and not progress.completed:
                        progress.completed = True
                        progress.completion_method = 'scorm'
                        progress.completed_at = attempt.completed_at or timezone.now()
                    
                    # Update scores
                    if attempt.score_raw is not None:
                        progress.last_score = float(attempt.score_raw)
                        if progress.best_score is None or float(attempt.score_raw) > progress.best_score:
                            progress.best_score = float(attempt.score_raw)
                    
                    # Update attempts
                    progress.attempts = max(progress.attempts or 0, attempt.attempt_number)
                    
                    progress.save()
            
            self.stdout.write(
                f'✅ Fixed attempt {attempt.id} (user: {attempt.user.username}, topic: {topic.title}) - progress: {progress_percentage}%'
            )
            return 'fixed'
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error fixing attempt {attempt.id}: {str(e)}')
            )
            return 'error'

    def _calculate_scorm_1_2_progress(self, attempt):
        """Calculate progress percentage for SCORM 1.2 based on lesson_status and other factors"""
        try:
            lesson_status = attempt.lesson_status
            
            # SCORM 1.2 progress calculation based on lesson_status
            if lesson_status == 'completed':
                return 100.0
            elif lesson_status == 'passed':
                return 100.0
            elif lesson_status == 'failed':
                return 100.0  # Failed but completed
            elif lesson_status == 'incomplete':
                # Check if there's location data to estimate progress
                if attempt.lesson_location:
                    # If there's a lesson location, assume some progress
                    return 50.0
                else:
                    return 25.0  # Started but not much progress
            elif lesson_status == 'browsed':
                return 25.0  # Browsed but not completed
            else:  # not_attempted
                return 0.0
                
        except Exception as e:
            logger.error(f"Error calculating SCORM 1.2 progress for attempt {attempt.id}: {str(e)}")
            return 0.0
