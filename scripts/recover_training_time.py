#!/usr/bin/env python3
"""
Training Time Recovery Script
Recovers training time data from existing SCORM session data and fixes TopicProgress records.
This script addresses the issue where SCORM time tracking failed to properly accumulate
session times into total_time and sync with TopicProgress.
"""

import os
import sys
import django
from datetime import datetime
import logging

# Setup Django environment
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from courses.models import TopicProgress
from scorm.models import ScormAttempt
import re

User = get_user_model()
logger = logging.getLogger(__name__)

class TrainingTimeRecoveryService:
    """
    Service to recover and fix training time data from SCORM attempts
    """
    
    def __init__(self):
        self.recovered_attempts = 0
        self.updated_progress = 0
        self.errors = []
        
    def parse_scorm_time_to_seconds(self, time_str):
        """Parse SCORM time format to seconds"""
        try:
            if not time_str or time_str == '0000:00:00.00':
                return 0
            
            # Handle SCORM 2004 format (PT1H30M45S)
            if time_str.startswith('PT'):
                return self._parse_iso_duration(time_str)
            
            # Handle SCORM 1.2 format (hhhh:mm:ss.ss)
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return int(hours * 3600 + minutes * 60 + seconds)
            
            return 0
        except (ValueError, IndexError, TypeError):
            return 0
    
    def _parse_iso_duration(self, duration_str):
        """Parse ISO 8601 duration format (PT1H30M45S) to seconds"""
        try:
            if not duration_str or not duration_str.startswith('PT'):
                return 0
            
            duration_str = duration_str[2:]  # Remove 'PT' prefix
            total_seconds = 0
            
            # Parse hours
            if 'H' in duration_str:
                hours_part = duration_str.split('H')[0]
                total_seconds += int(hours_part) * 3600
                duration_str = duration_str.split('H')[1]
            
            # Parse minutes
            if 'M' in duration_str:
                minutes_part = duration_str.split('M')[0]
                total_seconds += int(minutes_part) * 60
                duration_str = duration_str.split('M')[1]
            
            # Parse seconds
            if 'S' in duration_str:
                seconds_part = duration_str.split('S')[0]
                total_seconds += float(seconds_part)
            
            return int(total_seconds)
        except (ValueError, IndexError):
            return 0
    
    def format_scorm_time(self, seconds):
        """Format seconds to SCORM time format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:04d}:{minutes:02d}:{secs:05.2f}"
    
    def recover_scorm_attempts(self):
        """Recover time data from SCORM attempts"""
        print("🔄 Starting SCORM attempt time recovery...")
        
        # Get all attempts that have session time but no total time
        attempts_to_fix = ScormAttempt.objects.filter(
            session_time__isnull=False
        ).exclude(session_time='0000:00:00.00')
        
        print(f"Found {attempts_to_fix.count()} attempts with session time data")
        
        for attempt in attempts_to_fix:
            try:
                with transaction.atomic():
                    # Parse session time
                    session_seconds = self.parse_scorm_time_to_seconds(attempt.session_time)
                    
                    if session_seconds > 0:
                        # Update total time if it's currently zero
                        current_total = self.parse_scorm_time_to_seconds(attempt.total_time)
                        
                        if current_total == 0:
                            # Set total time to session time
                            attempt.total_time = self.format_scorm_time(session_seconds)
                            attempt.time_spent_seconds = session_seconds
                            
                            # Update detailed tracking
                            if not attempt.detailed_tracking:
                                attempt.detailed_tracking = {}
                            
                            attempt.detailed_tracking.update({
                                'total_time_seconds': session_seconds,
                                'last_session_duration': session_seconds,
                                'recovery_timestamp': timezone.now().isoformat(),
                                'recovery_method': 'session_time_recovery'
                            })
                            
                            attempt.save()
                            self.recovered_attempts += 1
                            
                            print(f"✅ Recovered attempt {attempt.id}: {session_seconds}s for user {attempt.user.email}")
                    
            except Exception as e:
                error_msg = f"Error recovering attempt {attempt.id}: {str(e)}"
                self.errors.append(error_msg)
                print(f"❌ {error_msg}")
        
        print(f"🔄 Recovered {self.recovered_attempts} SCORM attempts")
        return self.recovered_attempts
    
    def sync_topic_progress(self):
        """Sync TopicProgress with recovered SCORM time data"""
        print("🔄 Starting TopicProgress sync...")
        
        # Get all users with SCORM attempts
        users_with_attempts = User.objects.filter(
            scorm_attempts__isnull=False
        ).distinct()
        
        for user in users_with_attempts:
            try:
                with transaction.atomic():
                    # Get all SCORM attempts for this user
                    user_attempts = ScormAttempt.objects.filter(user=user)
                    
                    # Group by topic
                    topic_times = {}
                    
                    for attempt in user_attempts:
                        if attempt.time_spent_seconds and attempt.time_spent_seconds > 0:
                            topic = attempt.scorm_package.topic
                            if topic:
                                if topic.id not in topic_times:
                                    topic_times[topic.id] = {
                                        'topic': topic,
                                        'total_time': 0,
                                        'attempts': 0
                                    }
                                
                                # Use the maximum time from all attempts for this topic
                                topic_times[topic.id]['total_time'] = max(
                                    topic_times[topic.id]['total_time'],
                                    attempt.time_spent_seconds
                                )
                                topic_times[topic.id]['attempts'] += 1
                    
                    # Update TopicProgress for each topic
                    for topic_id, data in topic_times.items():
                        progress, created = TopicProgress.objects.get_or_create(
                            user=user,
                            topic=data['topic']
                        )
                        
                        # Update time spent
                        if data['total_time'] > 0:
                            progress.total_time_spent = data['total_time']
                            progress.last_accessed = timezone.now()
                            
                            # Update progress data
                            if not progress.progress_data:
                                progress.progress_data = {}
                            
                            progress.progress_data.update({
                                'recovery_timestamp': timezone.now().isoformat(),
                                'recovery_method': 'scorm_sync',
                                'scorm_attempts': data['attempts'],
                                'total_time_seconds': data['total_time']
                            })
                            
                            progress.save()
                            self.updated_progress += 1
                            
                            print(f"✅ Updated TopicProgress for {user.email} - {data['topic'].title}: {data['total_time']}s")
                    
            except Exception as e:
                error_msg = f"Error syncing TopicProgress for user {user.email}: {str(e)}"
                self.errors.append(error_msg)
                print(f"❌ {error_msg}")
        
        print(f"🔄 Updated {self.updated_progress} TopicProgress records")
        return self.updated_progress
    
    def fix_time_tracking_issues(self):
        """Fix underlying time tracking issues"""
        print("🔄 Fixing time tracking implementation...")
        
        # Update the enhanced time tracking to be more reliable
        from scorm.enhanced_time_tracking import EnhancedScormTimeTracker
        
        # Get attempts that still have zero time
        zero_time_attempts = ScormAttempt.objects.filter(
            time_spent_seconds=0,
            session_time__isnull=False
        ).exclude(session_time='0000:00:00.00')
        
        print(f"Found {zero_time_attempts.count()} attempts with zero time but session data")
        
        for attempt in zero_time_attempts:
            try:
                session_seconds = self.parse_scorm_time_to_seconds(attempt.session_time)
                if session_seconds > 0:
                    # Use the enhanced time tracker to fix this
                    tracker = EnhancedScormTimeTracker(attempt)
                    success = tracker.save_time_with_reliability(attempt.session_time)
                    
                    if success:
                        print(f"✅ Fixed time tracking for attempt {attempt.id}")
                    else:
                        # Manual fix
                        attempt.time_spent_seconds = session_seconds
                        attempt.total_time = self.format_scorm_time(session_seconds)
                        attempt.save()
                        print(f"✅ Manually fixed attempt {attempt.id}")
                        
            except Exception as e:
                error_msg = f"Error fixing attempt {attempt.id}: {str(e)}"
                self.errors.append(error_msg)
                print(f"❌ {error_msg}")
    
    def run_full_recovery(self):
        """Run the complete recovery process"""
        print("🚀 Starting Training Time Recovery Process")
        print("=" * 50)
        
        start_time = timezone.now()
        
        # Step 1: Recover SCORM attempts
        self.recover_scorm_attempts()
        
        # Step 2: Sync TopicProgress
        self.sync_topic_progress()
        
        # Step 3: Fix time tracking issues
        self.fix_time_tracking_issues()
        
        end_time = timezone.now()
        duration = end_time - start_time
        
        print("\n" + "=" * 50)
        print("🎉 Recovery Process Complete!")
        print(f"⏱️  Duration: {duration}")
        print(f"✅ Recovered SCORM attempts: {self.recovered_attempts}")
        print(f"✅ Updated TopicProgress records: {self.updated_progress}")
        print(f"❌ Errors encountered: {len(self.errors)}")
        
        if self.errors:
            print("\nErrors encountered:")
            for error in self.errors:
                print(f"  - {error}")
        
        return {
            'recovered_attempts': self.recovered_attempts,
            'updated_progress': self.updated_progress,
            'errors': len(self.errors),
            'duration': duration
        }

def main():
    """Main function to run the recovery"""
    recovery_service = TrainingTimeRecoveryService()
    results = recovery_service.run_full_recovery()
    
    print(f"\n📊 Final Results:")
    print(f"  - SCORM attempts recovered: {results['recovered_attempts']}")
    print(f"  - TopicProgress records updated: {results['updated_progress']}")
    print(f"  - Errors: {results['errors']}")
    print(f"  - Duration: {results['duration']}")

if __name__ == "__main__":
    main()
