#!/usr/bin/env python
"""
Debug script to investigate SCORM attempts and their data
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

def check_scorm_attempts():
    """Check all SCORM attempts and their data"""
    
    print("=" * 80)
    print("SCORM ATTEMPTS INVESTIGATION")
    print("=" * 80)
    
    # Get all SCORM attempts (recent ones)
    all_attempts = ScormAttempt.objects.all().select_related(
        'scorm_package', 'scorm_package__topic', 'user'
    ).order_by('-last_accessed')[:20]
    
    print(f"\nFound {all_attempts.count()} recent SCORM attempts")
    print("-" * 80)
    
    for attempt in all_attempts:
        try:
            topic = attempt.scorm_package.topic
            
            print(f"\n📊 Attempt ID: {attempt.id}")
            print(f"   User: {attempt.user.username} (ID: {attempt.user.id})")
            print(f"   Topic: {topic.title} (ID: {topic.id})")
            print(f"   SCORM Package: {attempt.scorm_package.title}")
            print(f"   Last Accessed: {attempt.last_accessed}")
            print(f"   Lesson Status: {attempt.lesson_status}")
            print(f"   Completion Status: {attempt.completion_status}")
            print(f"   Success Status: {attempt.success_status}")
            print(f"   Score Raw: {attempt.score_raw}")
            print(f"   Score Max: {attempt.score_max}")
            print(f"   Score Min: {attempt.score_min}")
            print(f"   Total Time: {attempt.total_time}")
            print(f"   Lesson Location: {attempt.lesson_location}")
            
            # Check CMI data for score
            cmi_data = attempt.cmi_data or {}
            score_keys = [k for k in cmi_data.keys() if 'score' in k.lower()]
            if score_keys:
                print(f"   CMI Score Data:")
                for key in score_keys:
                    print(f"     - {key}: {cmi_data[key]}")
            
            # Check TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user=attempt.user,
                topic=topic
            ).first()
            
            if topic_progress:
                print(f"   TopicProgress:")
                print(f"     - last_score: {topic_progress.last_score}")
                print(f"     - best_score: {topic_progress.best_score}")
                print(f"     - completed: {topic_progress.completed}")
                print(f"     - last_accessed: {topic_progress.last_accessed}")
                
                # Check progress_data for score
                progress_data = topic_progress.progress_data or {}
                if 'score_raw' in progress_data:
                    print(f"     - progress_data.score_raw: {progress_data['score_raw']}")
            else:
                print(f"   ❌ No TopicProgress found")
            
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    
    # Check course 29 specifically
    print("\n" + "=" * 80)
    print("COURSE 29 SPECIFIC CHECK")
    print("=" * 80)
    
    from courses.models import Course
    try:
        course = Course.objects.get(id=29)
        print(f"\nCourse: {course.title}")
        
        # Get all SCORM packages in this course
        topics = Topic.objects.filter(
            coursetopic__course=course
        ).prefetch_related('scorm_package')
        
        scorm_topics = [t for t in topics if hasattr(t, 'scorm_package')]
        print(f"SCORM Topics in Course 29: {len(scorm_topics)}")
        
        for topic in scorm_topics[:5]:  # First 5
            print(f"\n  Topic: {topic.title} (ID: {topic.id})")
            try:
                scorm_pkg = topic.scorm_package
                print(f"    SCORM Package: {scorm_pkg.title}")
                
                # Get recent attempts for this package
                attempts = ScormAttempt.objects.filter(
                    scorm_package=scorm_pkg
                ).order_by('-last_accessed')[:3]
                
                print(f"    Recent Attempts: {attempts.count()}")
                for att in attempts:
                    print(f"      - User: {att.user.username}, Score: {att.score_raw}, Status: {att.lesson_status}")
            except Exception as e:
                print(f"    No SCORM package: {str(e)}")
        
    except Course.DoesNotExist:
        print("Course 29 not found")
    except Exception as e:
        print(f"Error checking course 29: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_scorm_attempts()

