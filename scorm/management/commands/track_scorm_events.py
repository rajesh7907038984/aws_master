"""
Management command to create detailed SCORM event tracking.
This helps debug issues with completion, resume, and scoring.

Usage:
    python manage.py track_scorm_events
    python manage.py track_scorm_events --user-id 123
    python manage.py track_scorm_events --topic-id 456 
    python manage.py track_scorm_events --recent 24  # Last 24 hours
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress
from django.contrib.auth import get_user_model
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Track SCORM events and interactions for debugging'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Track events for specific user ID',
        )
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Track events for specific topic ID',
        )
        parser.add_argument(
            '--recent',
            type=int,
            help='Show events from last N hours (default: show all)',
        )
        parser.add_argument(
            '--incomplete-only',
            action='store_true',
            help='Show only incomplete attempts (for resume debugging)',
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        topic_id = options.get('topic_id')
        recent_hours = options.get('recent')
        incomplete_only = options['incomplete_only']
        
        self.stdout.write(
            self.style.SUCCESS('🔍 SCORM Event Tracking Analysis')
        )
        
        # Build filters
        filters = {}
        if user_id:
            filters['user_id'] = user_id
        if topic_id:
            filters['scorm_package__topic_id'] = topic_id
        
        if recent_hours:
            since = timezone.now() - timedelta(hours=recent_hours)
            filters['last_accessed__gte'] = since
            
        if incomplete_only:
            filters['lesson_status__in'] = ['incomplete', 'not_attempted']
        
        attempts = ScormAttempt.objects.filter(
            **filters
        ).select_related('user', 'scorm_package__topic').order_by('-last_accessed')
        
        total_attempts = attempts.count()
        self.stdout.write(f"📊 Found {total_attempts} SCORM attempts")
        
        if total_attempts == 0:
            self.stdout.write(self.style.WARNING("No SCORM attempts found matching criteria"))
            return
        
        # Analyze each attempt
        resume_working = 0
        false_completions = 0
        legitimate_completions = 0
        navigation_exits = 0
        
        for attempt in attempts:
            self.stdout.write(f"\n{'=' * 60}")
            self.stdout.write(f"🔍 Attempt ID: {attempt.id}")
            self.stdout.write(f"👤 User: {attempt.user.username} (ID: {attempt.user.id})")
            self.stdout.write(f"📚 Topic: {attempt.scorm_package.topic.title} (ID: {attempt.scorm_package.topic.id})")
            self.stdout.write(f"📅 Started: {attempt.started_at}")
            self.stdout.write(f"⏰ Last Accessed: {attempt.last_accessed}")
            self.stdout.write(f"🎯 Status: {attempt.lesson_status}")
            self.stdout.write(f"📊 Score: {attempt.score_raw}")
            self.stdout.write(f"🔄 Entry Mode: {attempt.entry}")
            
            # Analyze bookmark data
            has_bookmark = bool(attempt.lesson_location or attempt.suspend_data)
            self.stdout.write(f"🔖 Has Resume Data: {has_bookmark}")
            
            if has_bookmark:
                self.stdout.write(f"  📍 Lesson Location: {repr(attempt.lesson_location)}")
                self.stdout.write(f"  💾 Suspend Data: {len(attempt.suspend_data) if attempt.suspend_data else 0} chars")
                
                # Check if this is a legitimate resume scenario
                if attempt.entry == 'resume':
                    resume_working += 1
                    self.stdout.write(f"  ✅ Resume: Working correctly (entry=resume)")
                else:
                    self.stdout.write(f"  ⚠️  Resume: Entry mode is '{attempt.entry}' but should be 'resume'")
            
            # Analyze completion legitimacy
            if attempt.lesson_status in ['passed', 'completed']:
                # Check if this looks like a false completion
                has_interaction_evidence = (
                    attempt.total_time != '0000:00:00.00' or
                    (attempt.suspend_data and len(attempt.suspend_data) > 100) or
                    attempt.lesson_location or
                    (attempt.last_accessed and attempt.started_at and 
                     (attempt.last_accessed - attempt.started_at).total_seconds() > 60)
                )
                
                if has_interaction_evidence:
                    legitimate_completions += 1
                    self.stdout.write(f"  ✅ Completion: Appears legitimate (has interaction evidence)")
                else:
                    false_completions += 1
                    self.stdout.write(f"  ❌ Completion: Suspicious (no interaction evidence)")
                    self.stdout.write(f"    - Total time: {attempt.total_time}")
                    self.stdout.write(f"    - Session duration: {(attempt.last_accessed - attempt.started_at).total_seconds()} seconds")
                    self.stdout.write(f"    - Suspend data: {len(attempt.suspend_data) if attempt.suspend_data else 0} chars")
            
            # Check exit mode
            if attempt.exit_mode:
                self.stdout.write(f"🚪 Exit Mode: {attempt.exit_mode}")
                if attempt.exit_mode == 'logout' and attempt.lesson_status == 'incomplete':
                    navigation_exits += 1
                    self.stdout.write(f"  ℹ️  User navigated away (good - preserved incomplete state)")
            
            # Check CMI data for debugging
            if attempt.cmi_data:
                cmi_entry = attempt.cmi_data.get('cmi.core.entry') or attempt.cmi_data.get('cmi.entry')
                cmi_location = attempt.cmi_data.get('cmi.core.lesson_location') or attempt.cmi_data.get('cmi.location')
                cmi_suspend = attempt.cmi_data.get('cmi.suspend_data')
                
                self.stdout.write(f"🗂️  CMI Data:")
                self.stdout.write(f"    Entry: {cmi_entry}")
                self.stdout.write(f"    Location: {repr(cmi_location)}")
                self.stdout.write(f"    Suspend: {len(cmi_suspend) if cmi_suspend else 0} chars")
        
        # Summary
        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(self.style.SUCCESS("📈 SCORM Event Analysis Summary"))
        self.stdout.write(f"  📊 Total attempts analyzed: {total_attempts}")
        self.stdout.write(f"  🔖 Resume working correctly: {resume_working}")
        self.stdout.write(f"  ✅ Legitimate completions: {legitimate_completions}")
        self.stdout.write(f"  ❌ Suspicious completions: {false_completions}")
        self.stdout.write(f"  🚪 Navigation exits: {navigation_exits}")
        
        if false_completions > 0:
            self.stdout.write(self.style.ERROR(f"\n⚠️  {false_completions} suspicious completions detected!"))
            self.stdout.write("These may be false completions caused by navigation or threshold extraction.")
            self.stdout.write("Consider investigating these attempts manually.")
        
        if incomplete_only and resume_working > 0:
            self.stdout.write(self.style.SUCCESS(f"\n✅ Resume functionality appears to be working for {resume_working} attempts"))
        elif incomplete_only and resume_working == 0:
            self.stdout.write(self.style.WARNING("\n⚠️  No working resume attempts found"))
            
        # Recommendations
        if false_completions > legitimate_completions and false_completions > 0:
            self.stdout.write(self.style.ERROR("\n🚨 ALERT: More false completions than legitimate ones!"))
            self.stdout.write("Action required:")
            self.stdout.write("  1. Check SCORM content for auto-completion bugs")
            self.stdout.write("  2. Review score extraction patterns")
            self.stdout.write("  3. Consider resetting suspicious completion attempts")
