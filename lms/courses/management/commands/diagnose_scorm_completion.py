import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from courses.models import Topic, TopicProgress
from scorm_cloud.models import SCORMRegistration, SCORMCloudContent

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Diagnose SCORM completion issues for topics and users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Specific topic ID to diagnose'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Specific user ID to diagnose'
        )
        parser.add_argument(
            '--fix-mismatches',
            action='store_true',
            help='Fix mismatched completion statuses'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== SCORM Completion Diagnostic Tool ==='))
        
        # Filter based on provided options
        topics_filter = {'content_type': 'SCORM'}
        if options['topic_id']:
            topics_filter['id'] = options['topic_id']
        
        scorm_topics = Topic.objects.filter(**topics_filter)
        total_topics = scorm_topics.count()
        
        self.stdout.write(f"Found {total_topics} SCORM topics to analyze")
        
        issues_found = 0
        fixed_count = 0
        
        for i, topic in enumerate(scorm_topics, 1):
            self.stdout.write(f"\n[{i}/{total_topics}] Analyzing Topic: {topic.title} (ID: {topic.id})")
            
            # Get all progress records for this topic
            progress_filter = {'topic': topic}
            if options['user_id']:
                progress_filter['user_id'] = options['user_id']
            
            progress_records = TopicProgress.objects.filter(**progress_filter)
            
            self.stdout.write(f"  Found {progress_records.count()} progress records")
            
            # Find SCORM content mapping
            scorm_content = SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id=str(topic.id)
            ).first()
            
            if not scorm_content:
                self.stdout.write(self.style.WARNING(f"  ⚠️  No SCORM content mapping found for topic {topic.id}"))
                continue
                
            self.stdout.write(f"  📦 SCORM Package: {scorm_content.package.title}")
            
            # Analyze each progress record
            for progress in progress_records:
                user = progress.user
                self.stdout.write(f"    👤 User: {user.username} ({user.get_full_name()})")
                
                # Find associated SCORM registration
                registration = SCORMRegistration.objects.filter(
                    user=user,
                    package=scorm_content.package
                ).first()
                
                if not registration:
                    self.stdout.write(f"      ❌ No SCORM registration found")
                    continue
                
                # Check for mismatches
                progress_completed = progress.completed
                progress_data_status = progress.progress_data.get('completion_status', 'unknown') if isinstance(progress.progress_data, dict) else 'unknown'
                registration_status = registration.completion_status or 'unknown'
                registration_success = registration.success_status or 'unknown'
                
                self.stdout.write(f"      📊 Progress.completed: {progress_completed}")
                self.stdout.write(f"      📊 Progress.progress_data.completion_status: {progress_data_status}")
                self.stdout.write(f"      📊 Registration.completion_status: {registration_status}")
                self.stdout.write(f"      📊 Registration.success_status: {registration_success}")
                
                # Detect issues
                has_issue = False
                
                # Issue 1: Registration shows completed but TopicProgress doesn't
                if (registration_status in ['completed', 'complete'] or registration_success == 'passed') and not progress_completed:
                    self.stdout.write(self.style.ERROR(f"      🚨 ISSUE: Registration completed but TopicProgress not marked complete"))
                    has_issue = True
                    issues_found += 1
                    
                    if options['fix_mismatches']:
                        progress.completed = True
                        progress.completion_method = 'scorm'
                        if not progress.completed_at:
                            progress.completed_at = timezone.now()
                        
                        # Update progress_data
                        if not isinstance(progress.progress_data, dict):
                            progress.progress_data = {}
                        
                        progress.progress_data.update({
                            'completion_status': registration_status,
                            'success_status': registration_success,
                            'fixed_by_diagnostic': timezone.now().isoformat()
                        })
                        
                        progress.save()
                        fixed_count += 1
                        self.stdout.write(self.style.SUCCESS(f"      ✅ FIXED: Updated TopicProgress to match registration"))
                
                # Issue 2: Inconsistent progress_data vs completed field
                if progress_data_status in ['completed', 'complete'] and not progress_completed:
                    self.stdout.write(self.style.WARNING(f"      ⚠️  WARNING: progress_data shows completed but completed field is False"))
                    has_issue = True
                    
                    if options['fix_mismatches']:
                        progress.completed = True
                        progress.completion_method = 'scorm'
                        if not progress.completed_at:
                            progress.completed_at = timezone.now()
                        progress.save()
                        fixed_count += 1
                        self.stdout.write(self.style.SUCCESS(f"      ✅ FIXED: Synced completed field with progress_data"))
                
                # Issue 3: Missing completion timestamps
                if progress_completed and not progress.completed_at:
                    self.stdout.write(self.style.WARNING(f"      ⚠️  WARNING: Completed but missing completed_at timestamp"))
                    has_issue = True
                    
                    if options['fix_mismatches']:
                        progress.completed_at = timezone.now()
                        progress.save()
                        fixed_count += 1
                        self.stdout.write(self.style.SUCCESS(f"      ✅ FIXED: Added missing completed_at timestamp"))
                
                if not has_issue:
                    self.stdout.write(f"      ✅ Status consistent")
                
                # Show additional info
                if progress.last_score:
                    self.stdout.write(f"      📈 Score: {progress.last_score}%")
                if registration.total_time:
                    self.stdout.write(f"      ⏱️  Time spent: {registration.total_time} seconds")
        
        # Summary
        self.stdout.write(f"\n=== DIAGNOSTIC SUMMARY ===")
        self.stdout.write(f"Topics analyzed: {total_topics}")
        self.stdout.write(f"Issues found: {issues_found}")
        
        if options['fix_mismatches']:
            self.stdout.write(self.style.SUCCESS(f"Issues fixed: {fixed_count}"))
        else:
            self.stdout.write(f"Run with --fix-mismatches to automatically fix issues")
        
        if issues_found == 0:
            self.stdout.write(self.style.SUCCESS("🎉 No SCORM completion issues found!"))
        else:
            if options['fix_mismatches']:
                self.stdout.write(self.style.SUCCESS("🔧 Issues have been resolved"))
            else:
                self.stdout.write(self.style.WARNING("🔍 Issues detected - use --fix-mismatches to resolve")) 