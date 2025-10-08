#!/usr/bin/env python
"""
Debug script to investigate SCORM score synchronization issue
This script checks if scores from ScormAttempt are properly syncing to TopicProgress
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.db.models import Q
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress, Topic
from decimal import Decimal

def check_score_sync():
    """Check for SCORM attempts with scores that are not synced to TopicProgress"""
    
    print("=" * 80)
    print("SCORM SCORE SYNCHRONIZATION CHECK")
    print("=" * 80)
    
    # Get all SCORM attempts with scores
    attempts_with_scores = ScormAttempt.objects.filter(
        score_raw__isnull=False
    ).select_related('scorm_package', 'scorm_package__topic', 'user').order_by('-last_accessed')[:20]
    
    print(f"\nFound {attempts_with_scores.count()} recent SCORM attempts with scores")
    print("-" * 80)
    
    issues_found = []
    
    for attempt in attempts_with_scores:
        try:
            topic = attempt.scorm_package.topic
            
            # Get TopicProgress for this user and topic
            topic_progress = TopicProgress.objects.filter(
                user=attempt.user,
                topic=topic
            ).first()
            
            print(f"\n📊 Attempt ID: {attempt.id}")
            print(f"   User: {attempt.user.username} (ID: {attempt.user.id})")
            print(f"   Topic: {topic.title} (ID: {topic.id})")
            print(f"   SCORM Package: {attempt.scorm_package.title}")
            print(f"   Last Accessed: {attempt.last_accessed}")
            print(f"   ScormAttempt.score_raw: {attempt.score_raw}")
            print(f"   ScormAttempt.lesson_status: {attempt.lesson_status}")
            
            if topic_progress:
                print(f"   TopicProgress.last_score: {topic_progress.last_score}")
                print(f"   TopicProgress.best_score: {topic_progress.best_score}")
                print(f"   TopicProgress.completed: {topic_progress.completed}")
                print(f"   TopicProgress.last_accessed: {topic_progress.last_accessed}")
                
                # Check if scores match
                if attempt.score_raw is not None:
                    if topic_progress.last_score is None:
                        issues_found.append({
                            'type': 'MISSING_SCORE',
                            'attempt_id': attempt.id,
                            'user': attempt.user.username,
                            'topic': topic.title,
                            'scorm_score': attempt.score_raw,
                            'topic_score': None
                        })
                        print("   ❌ ISSUE: Score in ScormAttempt but NOT in TopicProgress!")
                    elif abs(float(attempt.score_raw) - float(topic_progress.last_score)) > 0.01:
                        issues_found.append({
                            'type': 'SCORE_MISMATCH',
                            'attempt_id': attempt.id,
                            'user': attempt.user.username,
                            'topic': topic.title,
                            'scorm_score': attempt.score_raw,
                            'topic_score': topic_progress.last_score
                        })
                        print(f"   ⚠️  WARNING: Score mismatch! ScormAttempt: {attempt.score_raw}, TopicProgress: {topic_progress.last_score}")
                    else:
                        print("   ✅ OK: Scores match")
            else:
                issues_found.append({
                    'type': 'NO_TOPIC_PROGRESS',
                    'attempt_id': attempt.id,
                    'user': attempt.user.username,
                    'topic': topic.title,
                    'scorm_score': attempt.score_raw
                })
                print("   ❌ CRITICAL: No TopicProgress record found!")
            
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total attempts checked: {attempts_with_scores.count()}")
    print(f"Issues found: {len(issues_found)}")
    
    if issues_found:
        print("\n⚠️  ISSUES DETECTED:")
        for issue in issues_found:
            print(f"\n  Type: {issue['type']}")
            print(f"  Attempt ID: {issue['attempt_id']}")
            print(f"  User: {issue['user']}")
            print(f"  Topic: {issue['topic']}")
            print(f"  SCORM Score: {issue.get('scorm_score', 'N/A')}")
            print(f"  Topic Score: {issue.get('topic_score', 'N/A')}")
    else:
        print("\n✅ No issues found - all scores are properly synchronized!")
    
    print("\n" + "=" * 80)
    
    return issues_found

if __name__ == '__main__':
    issues = check_score_sync()
    sys.exit(0 if not issues else 1)

