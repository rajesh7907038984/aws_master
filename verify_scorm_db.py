#!/usr/bin/env python3
"""
SCORM Database Verification Script
Run this after interacting with SCORM content to verify all data is saving properly
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from courses.models import Topic, TopicProgress
from users.models import CustomUser
from django.db.models import Q
import json
from datetime import datetime

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def verify_scorm_data():
    """Verify SCORM data is being saved correctly"""
    
    print_section("SCORM DATABASE VERIFICATION")
    
    # Find SCORM topics
    scorm_topics = Topic.objects.filter(content_type='SCORM')
    print(f"\n✓ Found {scorm_topics.count()} SCORM topics in database")
    
    if scorm_topics.count() == 0:
        print("\n⚠️  No SCORM topics found. Please create one first.")
        return
    
    # Find SCORM progress records
    scorm_progress = TopicProgress.objects.filter(topic__content_type='SCORM')
    print(f"✓ Found {scorm_progress.count()} SCORM progress records")
    
    if scorm_progress.count() == 0:
        print("\n⚠️  No SCORM progress found. Please launch a SCORM topic first.")
        return
    
    print_section("RECENT SCORM ACTIVITY")
    
    # Show recent SCORM progress
    recent = scorm_progress.order_by('-last_accessed')[:5]
    
    for i, progress in enumerate(recent, 1):
        print(f"\n[{i}] User: {progress.user.username} | Topic: {progress.topic.title[:50]}")
        print(f"    Topic ID: {progress.topic.id} | Progress ID: {progress.id}")
        print(f"    Last Accessed: {progress.last_accessed}")
        print(f"    First Accessed: {progress.first_accessed}")
        
        # Completion Status
        if progress.completed:
            print(f"    ✅ COMPLETED at {progress.completed_at}")
            print(f"    Completion Method: {progress.completion_method}")
        else:
            print(f"    ⏳ IN PROGRESS")
        
        # Score Data
        if progress.last_score:
            print(f"    📊 Last Score: {progress.last_score}")
        if progress.best_score:
            print(f"    🏆 Best Score: {progress.best_score}")
        
        # Time Data
        minutes = progress.total_time_spent // 60
        seconds = progress.total_time_spent % 60
        print(f"    ⏱️  Total Time: {minutes}m {seconds}s ({progress.total_time_spent} seconds)")
        
        # Attempts
        print(f"    🔄 Attempts: {progress.attempts}")
        
        # SCORM-specific data
        if progress.progress_data:
            print(f"\n    📦 SCORM DATA:")
            pd = progress.progress_data
            
            if 'scorm_completion_status' in pd:
                print(f"       - Completion Status: {pd['scorm_completion_status']}")
            if 'scorm_success_status' in pd:
                print(f"       - Success Status: {pd['scorm_success_status']}")
            if 'scorm_score' in pd:
                print(f"       - SCORM Score: {pd['scorm_score']}")
            if 'scorm_max_score' in pd:
                print(f"       - Max Score: {pd['scorm_max_score']}")
            if 'scorm_total_time' in pd:
                print(f"       - SCORM Time Format: {pd['scorm_total_time']}")
            if 'scorm_lesson_location' in pd:
                print(f"       - Last Location: {pd['scorm_lesson_location']}")
            if 'scorm_suspend_data' in pd:
                suspend_len = len(str(pd['scorm_suspend_data']))
                print(f"       - Suspend Data: {suspend_len} characters")
            if 'scorm_session_id' in pd:
                print(f"       - Session ID: {pd['scorm_session_id'][:30]}...")
            if 'scorm_last_seq' in pd:
                print(f"       - Last Sequence: {pd['scorm_last_seq']}")
        
        # Bookmark data (for resume)
        if progress.bookmark:
            print(f"\n    🔖 BOOKMARK (Resume Data):")
            bm = progress.bookmark
            if 'lesson_location' in bm:
                print(f"       - Location: {bm['lesson_location']}")
            if 'suspend_data' in bm:
                suspend_len = len(str(bm['suspend_data']))
                print(f"       - Suspend Data: {suspend_len} characters")
                if suspend_len > 0:
                    print(f"       ✅ Resume data available!")

    print_section("STATISTICS")
    
    # Overall stats
    total_progress = scorm_progress.count()
    completed_count = scorm_progress.filter(completed=True).count()
    in_progress_count = total_progress - completed_count
    
    print(f"\n📈 Overall SCORM Statistics:")
    print(f"   Total Progress Records: {total_progress}")
    print(f"   Completed: {completed_count} ({completed_count/total_progress*100:.1f}%)")
    print(f"   In Progress: {in_progress_count} ({in_progress_count/total_progress*100:.1f}%)")
    
    # Scores
    with_scores = scorm_progress.filter(last_score__isnull=False).count()
    if with_scores > 0:
        avg_score = scorm_progress.filter(last_score__isnull=False).aggregate(
            avg_score=django.db.models.Avg('last_score')
        )['avg_score']
        print(f"   Records with Scores: {with_scores}")
        print(f"   Average Score: {avg_score:.2f}")
    
    # Time spent
    total_time = scorm_progress.aggregate(
        total=django.db.models.Sum('total_time_spent')
    )['total']
    if total_time:
        hours = total_time // 3600
        minutes = (total_time % 3600) // 60
        print(f"   Total Time Spent: {hours}h {minutes}m")
    
    print_section("DATA INTEGRITY CHECKS")
    
    checks_passed = 0
    total_checks = 7
    
    # Check 1: All progress records have users
    if scorm_progress.filter(user__isnull=True).count() == 0:
        print("✅ All progress records linked to users")
        checks_passed += 1
    else:
        print("❌ Some progress records missing user")
    
    # Check 2: All progress records have topics
    if scorm_progress.filter(topic__isnull=True).count() == 0:
        print("✅ All progress records linked to topics")
        checks_passed += 1
    else:
        print("❌ Some progress records missing topic")
    
    # Check 3: Completed records have completion dates
    completed = scorm_progress.filter(completed=True)
    if completed.count() == 0 or completed.filter(completed_at__isnull=True).count() == 0:
        print("✅ All completed records have completion dates")
        checks_passed += 1
    else:
        print("❌ Some completed records missing completion date")
    
    # Check 4: Progress data is valid JSON
    invalid_json = 0
    for p in scorm_progress:
        if p.progress_data is None or not isinstance(p.progress_data, dict):
            invalid_json += 1
    if invalid_json == 0:
        print("✅ All progress_data fields are valid JSON")
        checks_passed += 1
    else:
        print(f"❌ {invalid_json} records have invalid progress_data")
    
    # Check 5: Time tracking makes sense
    negative_time = scorm_progress.filter(total_time_spent__lt=0).count()
    if negative_time == 0:
        print("✅ All time tracking values are valid")
        checks_passed += 1
    else:
        print(f"❌ {negative_time} records have negative time")
    
    # Check 6: Scores are in valid range
    invalid_scores = scorm_progress.filter(
        Q(last_score__lt=0) | Q(last_score__gt=100) |
        Q(best_score__lt=0) | Q(best_score__gt=100)
    ).count()
    if invalid_scores == 0:
        print("✅ All scores are in valid range (0-100)")
        checks_passed += 1
    else:
        print(f"❌ {invalid_scores} records have out-of-range scores")
    
    # Check 7: Best score >= last score (when both exist)
    score_issues = 0
    for p in scorm_progress.filter(last_score__isnull=False, best_score__isnull=False):
        if p.best_score < p.last_score:
            score_issues += 1
    if score_issues == 0:
        print("✅ Best scores are >= last scores")
        checks_passed += 1
    else:
        print(f"❌ {score_issues} records have best_score < last_score")
    
    print(f"\n📊 Integrity Score: {checks_passed}/{total_checks} checks passed")
    
    if checks_passed == total_checks:
        print("🎉 All integrity checks passed!")
    
    print_section("TEST A SPECIFIC USER (Optional)")
    print("\nTo test a specific user's SCORM progress:")
    print("python verify_scorm_db.py <username> <topic_id>")
    
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    import django.db.models
    
    if len(sys.argv) > 2:
        username = sys.argv[1]
        topic_id = sys.argv[2]
        
        try:
            user = CustomUser.objects.get(username=username)
            topic = Topic.objects.get(id=topic_id)
            progress = TopicProgress.objects.filter(user=user, topic=topic).first()
            
            if progress:
                print(f"\n🔍 Detailed Progress for {username} on Topic #{topic_id}:")
                print(json.dumps({
                    'user': username,
                    'topic': topic.title,
                    'completed': progress.completed,
                    'completion_method': progress.completion_method,
                    'last_score': float(progress.last_score) if progress.last_score else None,
                    'best_score': float(progress.best_score) if progress.best_score else None,
                    'total_time_spent': progress.total_time_spent,
                    'attempts': progress.attempts,
                    'progress_data': progress.progress_data,
                    'bookmark': progress.bookmark,
                    'completed_at': progress.completed_at.isoformat() if progress.completed_at else None,
                    'last_accessed': progress.last_accessed.isoformat() if progress.last_accessed else None,
                }, indent=2))
            else:
                print(f"\n❌ No progress found for {username} on topic #{topic_id}")
        except CustomUser.DoesNotExist:
            print(f"\n❌ User '{username}' not found")
        except Topic.DoesNotExist:
            print(f"\n❌ Topic #{topic_id} not found")
    else:
        verify_scorm_data()

