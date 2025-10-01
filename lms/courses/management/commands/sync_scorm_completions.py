import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from courses.models import TopicProgress
from scorm_cloud.models import SCORMRegistration
from users.models import CustomUser

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync SCORM completion statuses from SCORM Cloud to fix missing completion indicators'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Sync only for specific username',
        )
        parser.add_argument(
            '--course-id',
            type=int,
            help='Sync only for specific course ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        course_id = options.get('course_id')
        dry_run = options.get('dry_run')
        
        self.stdout.write(f"Starting SCORM completion sync...")
        if dry_run:
            self.stdout.write("DRY RUN MODE - No changes will be made")
        
        # Get SCORM registrations to check
        registrations = SCORMRegistration.objects.all()
        
        if username:
            registrations = registrations.filter(user__username=username)
            self.stdout.write(f"Filtering by username: {username}")
        
        if course_id:
            # Filter by course through TopicProgress relationship
            registrations = registrations.filter(
                user__topic_progress__topic__coursetopic__course_id=course_id,
                user__topic_progress__topic__content_type='SCORM'
            ).distinct()
            self.stdout.write(f"Filtering by course ID: {course_id}")
        
        total_registrations = registrations.count()
        self.stdout.write(f"Found {total_registrations} SCORM registrations to check")
        
        updated_count = 0
        error_count = 0
        
        for i, registration in enumerate(registrations, 1):
            try:
                user = registration.user
                if not user:
                    self.stdout.write(f"Skipping registration {registration.registration_id} - no user")
                    continue
                
                self.stdout.write(f"[{i}/{total_registrations}] Checking {user.username} - {registration.registration_id}")
                
                # Find associated TopicProgress records
                topic_progress_records = TopicProgress.objects.filter(
                    scorm_registration=registration.registration_id
                )
                
                if not topic_progress_records.exists():
                    # Try to find by user and SCORM topic association
                    from scorm_cloud.models import SCORMCloudContent
                    scorm_contents = SCORMCloudContent.objects.filter(
                        package=registration.package,
                        content_type='topic'
                    )
                    
                    for scorm_content in scorm_contents:
                        try:
                            topic_id = int(scorm_content.content_id)
                            topic_progress = TopicProgress.objects.filter(
                                user=user,
                                topic_id=topic_id,
                                topic__content_type='SCORM'
                            ).first()
                            
                            if topic_progress:
                                topic_progress_records = [topic_progress]
                                self.stdout.write(f"  Found topic progress via content mapping: Topic {topic_id}")
                                break
                        except (ValueError, TypeError):
                            continue
                
                if not topic_progress_records:
                    self.stdout.write(f"  No associated TopicProgress records found")
                    continue
                
                # Check current SCORM Cloud status
                try:
                    sync_result = registration.sync_completion_status()
                    if sync_result:
                        self.stdout.write(f"  SCORM Cloud status: {registration.completion_status} / {registration.success_status}")
                        
                        # Check if any TopicProgress records were updated
                        for topic_progress in topic_progress_records:
                            topic_progress.refresh_from_db()
                            
                            before_completed = getattr(topic_progress, '_pre_sync_completed', topic_progress.completed)
                            
                            if topic_progress.completed and not before_completed:
                                updated_count += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"  ✓ Updated TopicProgress {topic_progress.id} for topic '{topic_progress.topic.title}'"
                                    )
                                )
                            elif topic_progress.completed:
                                self.stdout.write(f"  Already completed: {topic_progress.topic.title}")
                            else:
                                self.stdout.write(f"  Still incomplete: {topic_progress.topic.title}")
                    else:
                        self.stdout.write(f"  Failed to sync with SCORM Cloud")
                        error_count += 1
                        
                except Exception as sync_error:
                    self.stdout.write(f"  Error syncing: {str(sync_error)}")
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(f"  Error processing registration {registration.registration_id}: {str(e)}")
                error_count += 1
        
        self.stdout.write(f"\n--- Sync Complete ---")
        self.stdout.write(f"Total registrations checked: {total_registrations}")
        self.stdout.write(f"TopicProgress records updated: {updated_count}")
        self.stdout.write(f"Errors encountered: {error_count}")
        
        if updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully fixed {updated_count} SCORM completion status issues!"
                )
            )
        else:
            self.stdout.write("No completion status issues found to fix.") 