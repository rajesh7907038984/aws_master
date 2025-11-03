"""
Management command to sync SCORM time tracking to TopicProgress records
This fixes the issue where SCORM time is tracked but not showing in reports
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum
from courses.models import TopicProgress, Topic
from scorm.models import ScormEnrollment, ScormAttempt


class Command(BaseCommand):
    help = 'Sync SCORM time tracking data to TopicProgress records for accurate reporting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync for specific user ID only',
        )
        parser.add_argument(
            '--course-id',
            type=int,
            help='Sync for specific course ID only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id = options.get('user_id')
        course_id = options.get('course_id')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        # Get all SCORM topics
        scorm_topics = Topic.objects.filter(content_type='Scorm')
        
        if course_id:
            scorm_topics = scorm_topics.filter(coursetopic__course_id=course_id)
        
        self.stdout.write(f"\n📦 Found {scorm_topics.count()} SCORM topics")
        
        # Get SCORM enrollments
        scorm_enrollments = ScormEnrollment.objects.select_related('user', 'topic', 'package')
        
        if user_id:
            scorm_enrollments = scorm_enrollments.filter(user_id=user_id)
        if course_id:
            scorm_enrollments = scorm_enrollments.filter(topic__coursetopic__course_id=course_id)
        
        total_enrollments = scorm_enrollments.count()
        self.stdout.write(f"👥 Processing {total_enrollments} SCORM enrollments\n")
        
        synced_count = 0
        created_count = 0
        skipped_count = 0
        
        for enrollment in scorm_enrollments:
            # Calculate total time from all attempts
            total_time_from_attempts = ScormAttempt.objects.filter(
                enrollment=enrollment
            ).aggregate(total=Sum('total_time_seconds'))['total'] or 0
            
            # Use the enrollment's total_time_seconds if it's already calculated
            scorm_time = max(enrollment.total_time_seconds, total_time_from_attempts)
            
            if scorm_time == 0:
                skipped_count += 1
                continue
            
            # Find or create TopicProgress
            # First try to find with course context
            from courses.views import get_topic_course
            course = get_topic_course(enrollment.topic)
            
            try:
                if course:
                    topic_progress, created = TopicProgress.objects.get_or_create(
                        user=enrollment.user,
                        topic=enrollment.topic,
                        course=course,
                        defaults={
                            'total_time_spent': scorm_time,
                            'attempts': enrollment.total_attempts,
                            'last_score': enrollment.last_score,
                            'best_score': enrollment.best_score,
                            'completed': enrollment.enrollment_status in ['completed', 'passed']
                        }
                    )
                else:
                    # Legacy: without course context
                    topic_progress, created = TopicProgress.objects.get_or_create(
                        user=enrollment.user,
                        topic=enrollment.topic,
                        course__isnull=True,
                        defaults={
                            'total_time_spent': scorm_time,
                            'attempts': enrollment.total_attempts,
                            'last_score': enrollment.last_score,
                            'best_score': enrollment.best_score,
                            'completed': enrollment.enrollment_status in ['completed', 'passed']
                        }
                    )
                
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Created TopicProgress for {enrollment.user.username} - "
                            f"{enrollment.topic.title[:50]} - {scorm_time}s"
                        )
                    )
                else:
                    # Update existing record if SCORM has more time
                    if topic_progress.total_time_spent < scorm_time:
                        old_time = topic_progress.total_time_spent
                        
                        if not dry_run:
                            topic_progress.total_time_spent = scorm_time
                            topic_progress.attempts = enrollment.total_attempts
                            topic_progress.last_score = enrollment.last_score or topic_progress.last_score
                            topic_progress.best_score = enrollment.best_score or topic_progress.best_score
                            topic_progress.completed = enrollment.enrollment_status in ['completed', 'passed'] or topic_progress.completed
                            topic_progress.save()
                        
                        synced_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"🔄 Updated {enrollment.user.username} - {enrollment.topic.title[:50]}: "
                                f"{old_time}s → {scorm_time}s (+{scorm_time - old_time}s)"
                            )
                        )
                    else:
                        skipped_count += 1
                        
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"❌ Error processing {enrollment.user.username} - {enrollment.topic.title[:50]}: {str(e)}"
                    )
                )
        
        # Summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS(f"📊 SYNC COMPLETE"))
        self.stdout.write(f"   Created: {created_count}")
        self.stdout.write(f"   Updated: {synced_count}")
        self.stdout.write(f"   Skipped: {skipped_count}")
        self.stdout.write(f"   Total processed: {total_enrollments}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  This was a DRY RUN - no changes were made"))
            self.stdout.write("Run without --dry-run to apply changes")
        
        self.stdout.write("=" * 80)

