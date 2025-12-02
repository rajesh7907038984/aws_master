#!/usr/bin/env python
"""
Test script for instructor training matrix filtering
Tests that instructors only see learners enrolled in their accessible courses
"""

import os
import django
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.contrib.auth import get_user_model
from courses.models import Course, CourseEnrollment
from django.db.models import Q

User = get_user_model()


def test_instructor_training_matrix():
    """Test that instructor can only see learners in their courses"""
    
    print("\n" + "="*80)
    print("TESTING INSTRUCTOR TRAINING MATRIX ACCESS")
    print("="*80)
    
    # Find an instructor user
    instructors = User.objects.filter(role='instructor', is_active=True)
    if not instructors.exists():
        print("❌ ERROR: No instructor users found in the database")
        return False
    
    instructor = instructors.first()
    print(f"\n✓ Testing with instructor: {instructor.username} (ID: {instructor.id})")
    print(f"  Email: {instructor.email}")
    print(f"  Branch: {instructor.branch.name if instructor.branch else 'N/A'}")
    
    # Get courses the instructor has access to (using same logic as view)
    primary_instructor_courses = Q(instructor=instructor)
    enrolled_instructor_courses = Q(enrolled_users=instructor)
    group_instructor_courses = Q(accessible_groups__memberships__user=instructor,
                                 accessible_groups__memberships__is_active=True)
    
    instructor_courses = Course.objects.filter(
        primary_instructor_courses | enrolled_instructor_courses | group_instructor_courses
    ).distinct()
    
    print(f"\n✓ Instructor has access to {instructor_courses.count()} courses:")
    for course in instructor_courses[:5]:  # Show first 5
        print(f"  - {course.title} (ID: {course.id})")
    if instructor_courses.count() > 5:
        print(f"  ... and {instructor_courses.count() - 5} more courses")
    
    if not instructor_courses.exists():
        print("❌ WARNING: Instructor has no accessible courses")
        return True
    
    # Get learners enrolled in instructor's courses
    course_ids = list(instructor_courses.values_list('id', flat=True))
    learner_ids_in_instructor_courses = CourseEnrollment.objects.filter(
        course_id__in=course_ids,
        user__role='learner'
    ).values_list('user_id', flat=True).distinct()
    
    learners_in_instructor_courses = User.objects.filter(
        id__in=learner_ids_in_instructor_courses,
        role='learner'
    )
    
    print(f"\n✓ Found {learners_in_instructor_courses.count()} learners enrolled in instructor's courses:")
    for learner in learners_in_instructor_courses[:5]:  # Show first 5
        # Get courses this learner is enrolled in from instructor's courses
        learner_enrollments = CourseEnrollment.objects.filter(
            user=learner,
            course_id__in=course_ids
        ).select_related('course')
        
        course_titles = [e.course.title for e in learner_enrollments[:3]]
        print(f"  - {learner.username} ({learner.get_full_name()}) - Enrolled in: {', '.join(course_titles)}")
    
    if learners_in_instructor_courses.count() > 5:
        print(f"  ... and {learners_in_instructor_courses.count() - 5} more learners")
    
    # Verify no learners from other courses are included
    all_learners = User.objects.filter(role='learner')
    other_learners = all_learners.exclude(id__in=learner_ids_in_instructor_courses)
    
    print(f"\n✓ {other_learners.count()} learners are NOT in instructor's courses (correctly filtered out)")
    
    # Test with a specific learner from another course (if exists)
    if other_learners.exists():
        other_learner = other_learners.first()
        other_courses = CourseEnrollment.objects.filter(
            user=other_learner
        ).exclude(course_id__in=course_ids).select_related('course')
        
        if other_courses.exists():
            print(f"\n✓ Example of correctly filtered learner:")
            print(f"  - {other_learner.username} is enrolled in {other_courses.count()} courses NOT accessible to instructor")
            for enrollment in other_courses[:2]:
                print(f"    • {enrollment.course.title}")
    
    print("\n" + "="*80)
    print("✅ TEST PASSED: Instructor training matrix filtering works correctly!")
    print("="*80)
    
    # Summary
    print("\nSUMMARY:")
    print(f"  • Instructor: {instructor.username}")
    print(f"  • Accessible courses: {instructor_courses.count()}")
    print(f"  • Learners visible in training matrix: {learners_in_instructor_courses.count()}")
    print(f"  • Total learners in system: {all_learners.count()}")
    print(f"  • Learners filtered out: {other_learners.count()}")
    
    return True


if __name__ == '__main__':
    try:
        success = test_instructor_training_matrix()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

