"""
Management command to fix incorrect SCORM scores
This command identifies and corrects SCORM attempts where the TopicProgress
shows incorrect scores (like 100%) when the actual SCORM data shows different scores.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from scorm.models import ScormAttempt
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix incorrect SCORM scores in TopicProgress records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Fix scores for specific topic ID only',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Fix scores for specific user ID only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        topic_id = options.get('topic_id')
        user_id = options.get('user_id')

        self.stdout.write(" Scanning for incorrect SCORM scores...")

        # Find SCORM attempts with potential score mismatches
        attempts_query = ScormAttempt.objects.select_related(
            'user', 'scorm_package', 'scorm_package__topic'
        ).filter(
            score_raw__isnull=False
        )

        if topic_id:
            attempts_query = attempts_query.filter(scorm_package__topic_id=topic_id)
        if user_id:
            attempts_query = attempts_query.filter(user_id=user_id)

        incorrect_scores = []
        total_checked = 0

        for attempt in attempts_query:
            total_checked += 1
            
            try:
                # Get the corresponding TopicProgress
                topic_progress = TopicProgress.objects.filter(
                    user=attempt.user,
                    topic=attempt.scorm_package.topic
                ).first()

                if not topic_progress:
                    continue

                # Check for score mismatches
                actual_score = float(attempt.score_raw)
                topic_last_score = float(topic_progress.last_score) if topic_progress.last_score else 0
                topic_best_score = float(topic_progress.best_score) if topic_progress.best_score else 0

                # Flag as incorrect if:
                # 1. TopicProgress shows 100% but SCORM shows much lower
                # 2. TopicProgress shows higher score than SCORM
                # 3. TopicProgress shows completed but SCORM shows failed
                is_incorrect = False
                issues = []

                if topic_last_score >= 100 and actual_score < 50:
                    is_incorrect = True
                    issues.append(f"TopicProgress shows {topic_last_score}% but SCORM shows {actual_score}%")
                
                if topic_last_score > actual_score + 10:  # Allow small differences
                    is_incorrect = True
                    issues.append(f"TopicProgress ({topic_last_score}%) higher than SCORM ({actual_score}%)")

                if topic_progress.completed and attempt.lesson_status == 'failed':
                    is_incorrect = True
                    issues.append(f"TopicProgress shows completed but SCORM shows {attempt.lesson_status}")

                if is_incorrect:
                    incorrect_scores.append({
                        'attempt': attempt,
                        'topic_progress': topic_progress,
                        'actual_score': actual_score,
                        'topic_last_score': topic_last_score,
                        'topic_best_score': topic_best_score,
                        'scorm_status': attempt.lesson_status,
                        'issues': issues
                    })

            except Exception as e:
                logger.error(f"Error checking attempt {attempt.id}: {e}")
                continue

        self.stdout.write(f" Found {len(incorrect_scores)} incorrect scores out of {total_checked} attempts")

        if not incorrect_scores:
            self.stdout.write(" No incorrect scores found!")
            return

        # Show details of incorrect scores
        for i, item in enumerate(incorrect_scores[:10]):  # Show first 10
            attempt = item['attempt']
            tp = item['topic_progress']
            self.stdout.write(f"\n{i+1}. Attempt {attempt.id} (User: {attempt.user.username}, Topic: {attempt.scorm_package.topic.title})")
            self.stdout.write(f"   SCORM Score: {item['actual_score']}% (Status: {item['scorm_status']})")
            self.stdout.write(f"   TopicProgress: Last={item['topic_last_score']}%, Best={item['topic_best_score']}%, Completed={tp.completed}")
            for issue in item['issues']:
                self.stdout.write(f"    {issue}")

        if len(incorrect_scores) > 10:
            self.stdout.write(f"\n... and {len(incorrect_scores) - 10} more")

        if dry_run:
            self.stdout.write(f"\n DRY RUN: Would fix {len(incorrect_scores)} incorrect scores")
            return

        # Fix the incorrect scores
        self.stdout.write(f"\n Fixing {len(incorrect_scores)} incorrect scores...")
        
        fixed_count = 0
        with transaction.atomic():
            for item in incorrect_scores:
                try:
                    attempt = item['attempt']
                    topic_progress = item['topic_progress']
                    actual_score = item['actual_score']
                    scorm_status = item['scorm_status']

                    # Update TopicProgress with correct data
                    topic_progress.last_score = Decimal(str(actual_score))
                    
                    # Update best_score only if this is actually better
                    if topic_progress.best_score is None or actual_score > float(topic_progress.best_score):
                        topic_progress.best_score = Decimal(str(actual_score))

                    # Fix completion status based on SCORM status
                    if scorm_status in ['completed', 'passed']:
                        topic_progress.completed = True
                    elif scorm_status == 'failed':
                        topic_progress.completed = False

                    topic_progress.save()
                    fixed_count += 1

                    self.stdout.write(f" Fixed attempt {attempt.id}: {item['topic_last_score']}% → {actual_score}%")

                except Exception as e:
                    logger.error(f"Error fixing attempt {item['attempt'].id}: {e}")
                    self.stdout.write(f" Failed to fix attempt {item['attempt'].id}: {e}")

        self.stdout.write(f"\n Successfully fixed {fixed_count} incorrect scores!")
        self.stdout.write("💡 Tip: Run this command regularly to catch score mismatches early")
