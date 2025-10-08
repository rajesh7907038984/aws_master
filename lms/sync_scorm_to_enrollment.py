#!/usr/bin/env python
"""
Sync SCORM data (time, completion, scores) to CourseEnrollment for accurate reporting
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress, Course, CourseEnrollment, CourseTopic
from django.utils import timezone
from django.db.models import Sum

def parse_scorm_time_to_seconds(time_str):
    """Convert SCORM time format (hhhh:mm:ss.ss) to seconds"""
    try:
        if not time_str or time_str == '0000:00:00.00':
            return 0
        parts = time_str.split(':')
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        return 0
    except (ValueError, IndexError, TypeError):
        return 0

def format_seconds_to_readable(total_seconds):
    """Convert seconds to readable format (Xh Ym)"""
    if total_seconds == 0:
        return "0h 0m"
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return f"{hours}h {minutes}m"

def sync_scorm_data_to_enrollments():
    print("=" * 80)
    print("SYNCING SCORM DATA TO COURSE ENROLLMENTS")
    print("=" * 80)
    
    # Get course 29 specifically
    try:
        course = Course.objects.get(id=29)
        print(f"\n✅ Found course: {course.title} (ID: {course.id})")
    except Course.DoesNotExist:
        print("\n❌ Course 29 not found")
        return
    
    # Get all SCORM topics in this course
    scorm_topics = []
    course_topics = CourseTopic.objects.filter(course=course).select_related('topic')
    
    for ct in course_topics:
        topic = ct.topic
        if hasattr(topic, 'scorm_package'):
            scorm_topics.append(topic)
    
    print(f"Found {len(scorm_topics)} SCORM topics in course")
    
    # Get all enrollments for this course
    enrollments = CourseEnrollment.objects.filter(course=course).select_related('user')
    print(f"Found {enrollments.count()} enrollments")
    
    updated_count = 0
    
    for enrollment in enrollments:
        user = enrollment.user
        print(f"\n📊 Processing: {user.username}")
        
        # Collect data from all SCORM topics for this user
        total_time_seconds = 0
        completed_topics = 0
        total_topics = len(scorm_topics)
        has_score = False
        
        for topic in scorm_topics:
            # Get TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user=user,
                topic=topic
            ).first()
            
            if topic_progress:
                # Count completed topics
                if topic_progress.completed:
                    completed_topics += 1
                
                # Check for score
                if topic_progress.last_score is not None:
                    has_score = True
                
                # Get time from progress_data
                progress_data = topic_progress.progress_data or {}
                total_time_str = progress_data.get('total_time', '0000:00:00.00')
                time_seconds = parse_scorm_time_to_seconds(total_time_str)
                total_time_seconds += time_seconds
                
                print(f"   Topic {topic.id}: completed={topic_progress.completed}, time={total_time_str} ({time_seconds}s)")
            
            # Also check ScormAttempt for more accurate time
            try:
                scorm_package = topic.scorm_package
                latest_attempt = ScormAttempt.objects.filter(
                    user=user,
                    scorm_package=scorm_package
                ).order_by('-last_accessed').first()
                
                if latest_attempt and latest_attempt.total_time:
                    attempt_seconds = parse_scorm_time_to_seconds(latest_attempt.total_time)
                    if attempt_seconds > time_seconds:  # Use the larger value
                        total_time_seconds = total_time_seconds - time_seconds + attempt_seconds
                        print(f"   Updated with attempt time: {latest_attempt.total_time} ({attempt_seconds}s)")
            except Exception as e:
                pass
        
        # Update enrollment
        needs_update = False
        
        # Update time spent
        time_formatted = format_seconds_to_readable(total_time_seconds)
        if not hasattr(enrollment, 'total_time_spent') or enrollment.total_time_spent != time_formatted:
            enrollment.total_time_spent = time_formatted
            needs_update = True
            print(f"   ⏱️  Updated time: {time_formatted}")
        
        # Update progress percentage
        if total_topics > 0:
            progress_pct = (completed_topics / total_topics) * 100
            if not hasattr(enrollment, 'progress_percentage') or enrollment.progress_percentage != progress_pct:
                enrollment.progress_percentage = progress_pct
                needs_update = True
                print(f"   📈 Updated progress: {progress_pct:.1f}%")
        
        # Update completion status
        if completed_topics == total_topics and total_topics > 0:
            if not enrollment.completed:
                enrollment.completed = True
                enrollment.completion_date = timezone.now()
                needs_update = True
                print(f"   ✅ Marked as completed")
        
        # Update last accessed
        if has_score or completed_topics > 0:
            if not enrollment.last_accessed:
                enrollment.last_accessed = timezone.now()
                needs_update = True
        
        if needs_update:
            enrollment.save()
            updated_count += 1
            print(f"   💾 Saved enrollment updates")
        else:
            print(f"   ℹ️  No updates needed")
    
    print(f"\n" + "=" * 80)
    print(f"UPDATED {updated_count} ENROLLMENTS")
    print("=" * 80)

if __name__ == '__main__':
    sync_scorm_data_to_enrollments()

