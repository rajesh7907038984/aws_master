"""
Management command to fix SCORM progress synchronization issues
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt
from courses.models import TopicProgress
from django.utils import timezone
import re

User = get_user_model()


class Command(BaseCommand):
    help = 'Fix SCORM progress synchronization issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username to fix progress for (optional)',
        )
        parser.add_argument(
            '--attempt-id',
            type=int,
            help='Specific attempt ID to fix (optional)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if progress seems correct',
        )

    def handle(self, *args, **options):
        self.stdout.write('=== SCORM Progress Synchronization Fix ===')
        
        # Get attempts to fix
        if options['attempt_id']:
            attempts = ScormAttempt.objects.filter(id=options['attempt_id'])
        elif options['user']:
            user = User.objects.get(username=options['user'])
            attempts = ScormAttempt.objects.filter(user=user)
        else:
            attempts = ScormAttempt.objects.all()
        
        fixed_count = 0
        
        for attempt in attempts:
            self.stdout.write(f'\n--- Processing Attempt {attempt.id} ---')
            self.stdout.write(f'User: {attempt.user.username}')
            self.stdout.write(f'Topic: {attempt.scorm_package.topic.title}')
            
            # Check if progress needs fixing
            needs_fix = False
            
            # Check suspend data for progress
            if attempt.suspend_data:
                progress_match = re.search(r'progress=(\d+)', attempt.suspend_data)
                if progress_match:
                    suspend_progress = int(progress_match.group(1))
                    if attempt.progress_percentage != suspend_progress:
                        needs_fix = True
                        self.stdout.write(f'Suspend data shows {suspend_progress}% but tracking shows {attempt.progress_percentage}%')
            
            # Check if progress is 0 but there's activity
            if attempt.progress_percentage == 0 and (attempt.lesson_location or attempt.suspend_data):
                needs_fix = True
                self.stdout.write('Progress is 0% but there is activity data')
            
            if needs_fix or options['force']:
                self.fix_attempt_progress(attempt)
                fixed_count += 1
            else:
                self.stdout.write('No fix needed')
        
        self.stdout.write(f'\n=== Fix Complete ===')
        self.stdout.write(f'Fixed {fixed_count} attempts')
    
    def fix_attempt_progress(self, attempt):
        """Fix progress for a specific attempt"""
        try:
            # Parse suspend data
            if attempt.suspend_data:
                progress_match = re.search(r'progress=(\d+)', attempt.suspend_data)
                current_slide_match = re.search(r'current_slide=([^&]+)', attempt.suspend_data)
                completed_slides_match = re.search(r'completed_slides=([^&]+)', attempt.suspend_data)
                
                if progress_match:
                    progress_percentage = int(progress_match.group(1))
                    current_slide = current_slide_match.group(1) if current_slide_match else 'current'
                    completed_slides = []
                    
                    if completed_slides_match:
                        completed_slides = [s.strip() for s in completed_slides_match.group(1).split(',') if s.strip()]
                    
                    # Update progress
                    attempt.progress_percentage = progress_percentage
                    attempt.last_visited_slide = f'slide_{current_slide}' if current_slide != 'current' else 'current'
                    attempt.completed_slides = completed_slides
                    
                    # Update detailed tracking
                    if not attempt.detailed_tracking:
                        attempt.detailed_tracking = {}
                    
                    attempt.detailed_tracking.update({
                        'progress_percentage': float(progress_percentage),
                        'current_slide': attempt.last_visited_slide,
                        'completed_slides': completed_slides,
                        'progress_source': 'management_command_fix',
                        'last_progress_update': timezone.now().isoformat(),
                        'sync_method': 'manual_fix'
                    })
                    
                    attempt.save()
                    
                    # Update TopicProgress
                    try:
                        topic_progress = TopicProgress.objects.get(
                            user=attempt.user,
                            topic=attempt.scorm_package.topic
                        )
                        topic_progress.progress_data.update({
                            'progress_percentage': float(progress_percentage),
                            'completed_slides': completed_slides,
                            'last_visited_slide': attempt.last_visited_slide,
                            'last_updated': timezone.now().isoformat(),
                        })
                        topic_progress.save()
                        
                        self.stdout.write(f'✅ Fixed progress: {progress_percentage}%')
                        self.stdout.write(f'✅ Updated TopicProgress')
                    except TopicProgress.DoesNotExist:
                        self.stdout.write('⚠️  No TopicProgress found')
                    
                else:
                    self.stdout.write('⚠️  No progress found in suspend data')
            else:
                self.stdout.write('⚠️  No suspend data found')
                
        except Exception as e:
            self.stdout.write(f'❌ Error fixing attempt: {str(e)}')
