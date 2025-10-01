"""
Management command to test and validate SCORM score calculations
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from courses.models import TopicProgress, Topic
from scorm_cloud.models import SCORMRegistration
from core.utils.scoring import ScoreCalculationService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test and validate SCORM score calculations in learning activities report'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix-scores',
            action='store_true',
            help='Fix any incorrectly calculated scores',
        )
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Test specific topic ID',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting SCORM score validation...')
        )

        # Get SCORM topics
        if options.get('topic_id'):
            topics = Topic.objects.filter(id=options['topic_id'])
        else:
            topics = Topic.objects.filter(
                Q(scorm_content__isnull=False) |
                Q(scorm_package__isnull=False)
            ).distinct()

        if not topics.exists():
            self.stdout.write(
                self.style.WARNING('No SCORM topics found.')
            )
            return

        total_topics = topics.count()
        processed = 0
        fixed = 0
        errors = 0

        for topic in topics:
            try:
                self.stdout.write(f"\nProcessing topic: {topic.title}")
                
                # Get topic progress records
                progress_records = TopicProgress.objects.filter(topic=topic)
                
                if not progress_records.exists():
                    self.stdout.write(f"  No progress records found for {topic.title}")
                    continue

                # Check SCORM registrations
                scorm_registrations = SCORMRegistration.objects.filter(
                    registration_id__in=progress_records.exclude(
                        scorm_registration__isnull=True
                    ).values_list('scorm_registration', flat=True)
                )

                self.stdout.write(f"  Found {progress_records.count()} progress records")
                self.stdout.write(f"  Found {scorm_registrations.count()} SCORM registrations")

                # Analyze scores
                scores_analyzed = 0
                scores_fixed = 0
                
                for progress in progress_records.exclude(last_score__isnull=True):
                    scores_analyzed += 1
                    original_score = progress.last_score
                    
                    # Test score normalization
                    normalized_score = ScoreCalculationService.normalize_score(original_score)
                    
                    if normalized_score != original_score:
                        self.stdout.write(
                            f"    Score normalization: {original_score} -> {normalized_score}"
                        )
                        
                        if options.get('fix_scores'):
                            progress.last_score = normalized_score
                            progress.save(update_fields=['last_score'])
                            scores_fixed += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"    Fixed score for user {progress.user.username}")
                            )

                # Calculate average score using new method
                valid_scores = []
                for progress in progress_records.exclude(last_score__isnull=True):
                    normalized_score = ScoreCalculationService.normalize_score(progress.last_score)
                    if normalized_score is not None:
                        valid_scores.append(float(normalized_score))

                average_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0

                self.stdout.write(f"  Scores analyzed: {scores_analyzed}")
                self.stdout.write(f"  Scores fixed: {scores_fixed}")
                self.stdout.write(f"  Calculated average score: {average_score:.2f}%")

                processed += 1
                fixed += scores_fixed

            except Exception as e:
                errors += 1
                logger.error(f"Error processing topic {topic.id}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Error processing {topic.title}: {str(e)}")
                )

        # Summary
        self.stdout.write(
            self.style.SUCCESS(f"\n=== SUMMARY ===")
        )
        self.stdout.write(f"Total topics: {total_topics}")
        self.stdout.write(f"Processed: {processed}")
        self.stdout.write(f"Scores fixed: {fixed}")
        self.stdout.write(f"Errors: {errors}")

        if options.get('fix_scores'):
            self.stdout.write(
                self.style.SUCCESS("Score fixing enabled - changes have been saved.")
            )
        else:
            self.stdout.write(
                self.style.WARNING("Score fixing disabled - use --fix-scores to apply changes.")
            )
