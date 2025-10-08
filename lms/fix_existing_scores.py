#!/usr/bin/env python
"""
Fix existing SCORM scores that are in ScormAttempt but not in TopicProgress
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormAttempt
from courses.models import TopicProgress
from django.utils import timezone

def fix_scores():
    print("=" * 80)
    print("FIXING SCORM SCORES - Sync from ScormAttempt to TopicProgress")
    print("=" * 80)
    
    # Get all attempts with scores
    attempts_with_scores = ScormAttempt.objects.filter(
        score_raw__isnull=False
    ).select_related('scorm_package', 'scorm_package__topic', 'user').order_by('-last_accessed')
    
    print(f"\nFound {attempts_with_scores.count()} attempts with scores")
    
    fixed_count = 0
    for attempt in attempts_with_scores:
        try:
            topic = attempt.scorm_package.topic
            
            # Get or create TopicProgress
            progress, created = TopicProgress.objects.get_or_create(
                user=attempt.user,
                topic=topic
            )
            
            score_value = float(attempt.score_raw)
            
            # Update if needed
            needs_update = False
            if progress.last_score is None or float(progress.last_score) != score_value:
                progress.last_score = score_value
                needs_update = True
            
            if progress.best_score is None or score_value > float(progress.best_score):
                progress.best_score = score_value
                needs_update = True
            
            # Update progress_data
            progress.progress_data = progress.progress_data or {}
            progress.progress_data.update({
                'scorm_attempt_id': attempt.id,
                'lesson_status': attempt.lesson_status,
                'score_raw': score_value,
                'last_updated': timezone.now().isoformat(),
            })
            needs_update = True
            
            if needs_update:
                progress.save()
                fixed_count += 1
                print(f"✅ Fixed: User {attempt.user.username}, Topic {topic.id}, Score {score_value}")
        
        except Exception as e:
            print(f"❌ Error for attempt {attempt.id}: {str(e)}")
    
    print(f"\n" + "=" * 80)
    print(f"FIXED {fixed_count} TopicProgress records")
    print("=" * 80)

if __name__ == '__main__':
    fix_scores()

