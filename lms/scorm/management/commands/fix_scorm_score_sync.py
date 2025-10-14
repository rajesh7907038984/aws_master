"""
Management command to fix SCORM score inconsistencies
This command synchronizes all SCORM scores between ScormAttempt and TopicProgress
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormAttempt, ScormPackage
from scorm.simple_data_handler import ScormDataHandler
from courses.models import TopicProgress, Course

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix SCORM score inconsistencies by synchronizing all attempts'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--course',
            type=int,
            help='Course ID to sync scores for (optional, syncs all if not provided)'
        )
        parser.add_argument(
            '--user',
            type=int,
            help='User ID to sync scores for (optional)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )
        parser.add_argument(
            '--fix-specific',
            nargs=2,
            metavar=('USER_ID', 'TOPIC_ID'),
            help='Fix a specific user-topic combination'
        )
    
    def handle(self, *args, **options):
        course_id = options.get('course')
        user_id = options.get('user')
        dry_run = options.get('dry_run')
        fix_specific = options.get('fix_specific')
        
        self.stdout.write(self.style.WARNING('Starting SCORM score synchronization...'))
        
        if fix_specific:
            # Fix a specific user-topic combination
            user_id, topic_id = map(int, fix_specific)
            self._fix_specific_score(user_id, topic_id, dry_run)
            return
        
        # Get attempts to process
        attempts = ScormAttempt.objects.select_related('user', 'scorm_package__topic')
        
        if course_id:
            # Filter by course
            course = Course.objects.get(id=course_id)
            topic_ids = course.topics.filter(content_type='SCORM').values_list('id', flat=True)
            attempts = attempts.filter(scorm_package__topic_id__in=topic_ids)
            self.stdout.write(f"Filtering for course: {course.title}")
        
        if user_id:
            attempts = attempts.filter(user_id=user_id)
            self.stdout.write(f"Filtering for user ID: {user_id}")
        
        # Process each attempt
        total = attempts.count()
        synced = 0
        failed = 0
        skipped = 0
        
        self.stdout.write(f"\nProcessing {total} SCORM attempts...")
        
        for i, attempt in enumerate(attempts):
            try:
                self.stdout.write(f"\n[{i+1}/{total}] Processing attempt {attempt.id}...")
                
                # Show current state
                topic = attempt.scorm_package.topic
                topic_progress = TopicProgress.objects.filter(
                    user=attempt.user,
                    topic=topic
                ).first()
                
                self.stdout.write(f"  User: {attempt.user.username}")
                self.stdout.write(f"  Topic: {topic.title}")
                self.stdout.write(f"  SCORM Status: {attempt.lesson_status}")
                self.stdout.write(f"  SCORM Score: {attempt.score_raw}")
                
                if topic_progress:
                    self.stdout.write(f"  TopicProgress Last Score: {topic_progress.last_score}")
                    self.stdout.write(f"  TopicProgress Best Score: {topic_progress.best_score}")
                else:
                    self.stdout.write("  TopicProgress: Not found")
                
                if dry_run:
                    # Just show what would be done
                    # Use simple approach to get score from attempt
                    score = float(attempt.score_raw) if attempt.score_raw else None
                    if score is not None:
                        self.stdout.write(self.style.SUCCESS(f"  Would sync score: {score}"))
                    else:
                        self.stdout.write(self.style.WARNING("  No score to sync"))
                    continue
                
                # Perform sync
                with transaction.atomic():
                    handler = ScormDataHandler(attempt)
                    if handler.force_sync():
                        synced += 1
                        
                        # Show updated state
                        topic_progress = TopicProgress.objects.filter(
                            user=attempt.user,
                            topic=topic
                        ).first()
                        
                        if topic_progress:
                            self.stdout.write(self.style.SUCCESS(
                                f"  ✓ Synced successfully - Last Score: {topic_progress.last_score}, "
                                f"Best Score: {topic_progress.best_score}"
                            ))
                        else:
                            self.stdout.write(self.style.ERROR("  ✗ TopicProgress not created"))
                    else:
                        skipped += 1
                        self.stdout.write(self.style.WARNING("  - Skipped (no valid score)"))
                        
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  ✗ Failed: {str(e)}"))
                logger.error(f"Failed to sync attempt {attempt.id}", exc_info=True)
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"Synchronization complete!"))
        self.stdout.write(f"Total attempts: {total}")
        self.stdout.write(f"Successfully synced: {synced}")
        self.stdout.write(f"Skipped (no score): {skipped}")
        self.stdout.write(f"Failed: {failed}")
    
    def _fix_specific_score(self, user_id, topic_id, dry_run):
        """Fix score for a specific user-topic combination"""
        self.stdout.write(f"\nFixing score for User ID: {user_id}, Topic ID: {topic_id}")
        
        # Simple consistency check and fix
        result = self._verify_simple_consistency(user_id, topic_id)
        
        self.stdout.write(f"SCORM Score: {result['scorm_score']}")
        self.stdout.write(f"TopicProgress Score: {result['topic_progress_score']}")
        self.stdout.write(f"Consistent: {result['consistent']}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run - would perform: {result['action_taken']}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Action: {result['action_taken']}"))
    
    def _verify_simple_consistency(self, user_id, topic_id):
        """Simple consistency check between SCORM attempt and TopicProgress"""
        try:
            from courses.models import Topic
            
            topic = Topic.objects.get(id=topic_id)
            
            # Get latest SCORM attempt
            latest_attempt = ScormAttempt.objects.filter(
                user_id=user_id,
                scorm_package=topic.scorm_package
            ).order_by('-last_accessed').first()
            
            if not latest_attempt:
                return {
                    'consistent': False,
                    'scorm_score': None,
                    'topic_progress_score': None,
                    'action_taken': 'No SCORM attempt found'
                }
            
            # Get TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user_id=user_id,
                topic_id=topic_id
            ).first()
            
            # Extract scores
            scorm_score = float(latest_attempt.score_raw) if latest_attempt.score_raw else None
            topic_score = float(topic_progress.last_score) if topic_progress and topic_progress.last_score else None
            
            # Check consistency
            consistent = scorm_score == topic_score
            
            if not consistent and scorm_score is not None:
                # Fix the inconsistency
                handler = ScormDataHandler(latest_attempt)
                if handler.force_sync():
                    action_taken = 'Score synchronized successfully'
                else:
                    action_taken = 'Failed to synchronize score'
            else:
                action_taken = 'Scores are already consistent'
            
            return {
                'consistent': consistent,
                'scorm_score': scorm_score,
                'topic_progress_score': topic_score,
                'action_taken': action_taken
            }
            
        except Exception as e:
            return {
                'consistent': False,
                'scorm_score': None,
                'topic_progress_score': None,
                'action_taken': f'Error: {str(e)}'
            }
