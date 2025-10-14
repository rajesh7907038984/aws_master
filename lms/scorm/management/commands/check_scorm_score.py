"""
Django management command to check SCORM scores for a specific user
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress

User = get_user_model()


class Command(BaseCommand):
    help = 'Check SCORM scores for a specific user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to check')
        parser.add_argument('--topic-id', type=int, help='Specific topic ID to check', default=None)

    def handle(self, *args, **options):
        username = options['username']
        topic_id = options.get('topic_id')
        
        self.stdout.write("\n" + "="*80)
        self.stdout.write(f"Checking SCORM data for user: {username}")
        self.stdout.write("="*80 + "\n")
        
        try:
            user = User.objects.filter(username=username).first()
            
            if not user:
                self.stdout.write(self.style.ERROR(f"❌ User '{username}' not found in the database!"))
                return
            
            self.stdout.write(self.style.SUCCESS(f"✅ User found: {user.username} (ID: {user.id})"))
            self.stdout.write(f"   Name: {user.get_full_name()}")
            self.stdout.write(f"   Email: {user.email}\n")
            
            # Get all SCORM attempts for this user
            attempts = ScormAttempt.objects.filter(user=user).select_related('scorm_package__topic').order_by('-last_accessed')
            
            self.stdout.write(f"📊 Total SCORM attempts: {attempts.count()}\n")
            
            if attempts.count() == 0:
                self.stdout.write(self.style.WARNING("⚠️  No SCORM attempts found for this user!"))
                return
            
            # Filter by topic ID if specified
            if topic_id:
                attempts = attempts.filter(scorm_package__topic__id=topic_id)
                self.stdout.write(f"\n{'='*80}")
                self.stdout.write(f"Filtering for SCORM Topic ID {topic_id}")
                self.stdout.write("="*80 + "\n")
                
                if not attempts.exists():
                    self.stdout.write(self.style.ERROR(f"❌ No attempts found for SCORM Topic ID {topic_id}"))
                    return
            
            # Display each attempt
            for attempt in attempts:
                self.stdout.write(f"\n{'─'*80}")
                self.stdout.write(f"Attempt #{attempt.attempt_number} (ID: {attempt.id})")
                self.stdout.write("─"*80)
                self.stdout.write(f"Topic ID: {attempt.scorm_package.topic.id}")
                self.stdout.write(f"Topic: {attempt.scorm_package.topic.title}")
                self.stdout.write(f"Package Version: {attempt.scorm_package.version}")
                self.stdout.write(f"Lesson Status: {attempt.lesson_status}")
                self.stdout.write(f"Completion Status: {attempt.completion_status}")
                self.stdout.write(f"Success Status: {attempt.success_status}")
                
                self.stdout.write(f"\n📈 SCORE INFORMATION:")
                self.stdout.write(f"   Score Raw: {attempt.score_raw}")
                self.stdout.write(f"   Score Min: {attempt.score_min}")
                self.stdout.write(f"   Score Max: {attempt.score_max}")
                self.stdout.write(f"   Score Scaled: {attempt.score_scaled}")
                self.stdout.write(f"   Progress %: {attempt.progress_percentage}")
                
                self.stdout.write(f"\n⏱️  TIME TRACKING:")
                self.stdout.write(f"   Total Time: {attempt.total_time}")
                self.stdout.write(f"   Session Time: {attempt.session_time}")
                self.stdout.write(f"   Time Spent (seconds): {attempt.time_spent_seconds}")
                
                self.stdout.write(f"\n📅 TIMESTAMPS:")
                self.stdout.write(f"   Started: {attempt.started_at}")
                self.stdout.write(f"   Last Accessed: {attempt.last_accessed}")
                self.stdout.write(f"   Completed: {attempt.completed_at}")
                
                self.stdout.write(f"\n📍 BOOKMARK DATA:")
                self.stdout.write(f"   Lesson Location: {attempt.lesson_location}")
                self.stdout.write(f"   Last Visited Slide: {attempt.last_visited_slide}")
                suspend_preview = attempt.suspend_data[:100] if attempt.suspend_data else 'None'
                self.stdout.write(f"   Suspend Data (first 100 chars): {suspend_preview}...")
                
                # Check CMI data for scores
                if attempt.cmi_data:
                    self.stdout.write(f"\n🔍 CMI DATA INSPECTION:")
                    score_keys = [k for k in attempt.cmi_data.keys() if 'score' in k.lower()]
                    if score_keys:
                        self.stdout.write(f"   Score-related keys found:")
                        for key in score_keys:
                            self.stdout.write(f"      {key}: {attempt.cmi_data[key]}")
                    else:
                        self.stdout.write(self.style.WARNING("   ⚠️  No score-related keys found in CMI data"))
                        self.stdout.write(f"   CMI data keys: {list(attempt.cmi_data.keys())[:10]}")
                
                # Check TopicProgress
                topic_progress = TopicProgress.objects.filter(
                    user=user,
                    topic=attempt.scorm_package.topic
                ).first()
                
                if topic_progress:
                    self.stdout.write(f"\n📊 TOPIC PROGRESS (Backend):")
                    self.stdout.write(f"   Last Score: {topic_progress.last_score}")
                    self.stdout.write(f"   Best Score: {topic_progress.best_score}")
                    self.stdout.write(f"   Completed: {topic_progress.completed}")
                    self.stdout.write(f"   Attempts: {topic_progress.attempts}")
                    self.stdout.write(f"   Last Accessed: {topic_progress.last_accessed}")
                    
                    # Compare scores
                    if attempt.score_raw != topic_progress.last_score:
                        self.stdout.write(self.style.ERROR("\n⚠️  SCORE MISMATCH DETECTED!"))
                        self.stdout.write(f"   ScormAttempt.score_raw: {attempt.score_raw}")
                        self.stdout.write(f"   TopicProgress.last_score: {topic_progress.last_score}")
                        self.stdout.write(self.style.ERROR("\n   This indicates the score was NOT properly saved to the backend!"))
                    else:
                        self.stdout.write(self.style.SUCCESS("\n✅ Scores match - data is synchronized correctly"))
                else:
                    self.stdout.write(self.style.ERROR("\n❌ NO TOPIC PROGRESS FOUND!"))
                    self.stdout.write(self.style.ERROR("   This means the score was never saved to the backend TopicProgress table!"))
                
                self.stdout.write("\n")
            
            self.stdout.write("="*80)
            self.stdout.write("Database check completed!")
            self.stdout.write("="*80 + "\n")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ ERROR: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())

