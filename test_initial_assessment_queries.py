#!/usr/bin/env python
"""
Test script to verify N+1 query fix for Initial Assessment quizzes
Run this script to count database queries before and after the fix
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.test.utils import CaptureQueriesContext
from django.db import connection
from quiz.models import Quiz, QuizAttempt
from users.models import CustomUser


def test_query_count():
    """Test query count for initial assessment classification"""
    
    print("="*80)
    print("Testing Initial Assessment Query Optimization")
    print("="*80)
    
    # Find an initial assessment quiz
    initial_assessments = Quiz.objects.filter(
        is_initial_assessment=True,
        is_active=True
    ).first()
    
    if not initial_assessments:
        print("❌ No initial assessment quizzes found in database")
        print("   Please create an initial assessment quiz to test")
        return
    
    print(f"\n✓ Found initial assessment: {initial_assessments.title}")
    
    # Find completed attempts
    completed_attempts = QuizAttempt.objects.filter(
        quiz=initial_assessments,
        is_completed=True
    )[:10]  # Test with first 10 attempts
    
    if not completed_attempts.exists():
        print("❌ No completed attempts found for this initial assessment")
        print("   Please have students complete the assessment to test")
        return
    
    print(f"✓ Found {completed_attempts.count()} completed attempts")
    
    # Test WITHOUT optimization (simulating the bug)
    print("\n" + "-"*80)
    print("TEST 1: Without prefetch_related (simulating the bug)")
    print("-"*80)
    
    with CaptureQueriesContext(connection) as context:
        attempts_without_prefetch = QuizAttempt.objects.filter(
            quiz=initial_assessments,
            is_completed=True
        ).select_related('quiz', 'user')[:10]
        
        # Calculate classification for each (this triggers N+1 queries)
        classifications = []
        for attempt in attempts_without_prefetch:
            classification = attempt.calculate_assessment_classification()
            classifications.append(classification)
    
    queries_without = len(context.captured_queries)
    print(f"Queries executed: {queries_without}")
    print(f"Attempts processed: {len(classifications)}")
    print(f"Average queries per attempt: {queries_without / len(classifications):.1f}")
    
    # Test WITH optimization (the fix)
    print("\n" + "-"*80)
    print("TEST 2: With prefetch_related (after the fix)")
    print("-"*80)
    
    with CaptureQueriesContext(connection) as context:
        attempts_with_prefetch = QuizAttempt.objects.filter(
            quiz=initial_assessments,
            is_completed=True
        ).select_related('quiz', 'user').prefetch_related(
            'quiz__questions',
            'user_answers__question'
        )[:10]
        
        # Calculate classification for each (optimized)
        classifications_optimized = []
        for attempt in attempts_with_prefetch:
            classification = attempt.calculate_assessment_classification()
            classifications_optimized.append(classification)
    
    queries_with = len(context.captured_queries)
    print(f"Queries executed: {queries_with}")
    print(f"Attempts processed: {len(classifications_optimized)}")
    print(f"Average queries per attempt: {queries_with / len(classifications_optimized):.1f}")
    
    # Calculate improvement
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    reduction = queries_without - queries_with
    reduction_percent = (reduction / queries_without * 100) if queries_without > 0 else 0
    
    print(f"\n📊 Query Reduction:")
    print(f"   Before fix: {queries_without} queries")
    print(f"   After fix:  {queries_with} queries")
    print(f"   Reduction:  {reduction} queries ({reduction_percent:.1f}% improvement)")
    
    if reduction_percent > 50:
        print(f"\n✅ EXCELLENT: {reduction_percent:.0f}% query reduction achieved!")
    elif reduction_percent > 25:
        print(f"\n✓ GOOD: {reduction_percent:.0f}% query reduction achieved")
    else:
        print(f"\n⚠️  WARNING: Only {reduction_percent:.0f}% reduction - investigation needed")
    
    # Verify results are identical
    print(f"\n🔍 Verification:")
    if len(classifications) == len(classifications_optimized):
        print(f"   ✓ Both methods processed {len(classifications)} attempts")
        
        # Check if classifications match
        mismatches = 0
        for i, (c1, c2) in enumerate(zip(classifications, classifications_optimized)):
            if c1 != c2:
                mismatches += 1
                print(f"   ❌ Mismatch at attempt {i+1}")
        
        if mismatches == 0:
            print(f"   ✓ All classification results match - fix is correct!")
        else:
            print(f"   ❌ {mismatches} mismatches found - investigation needed")
    else:
        print(f"   ❌ Different number of attempts processed")
    
    print("\n" + "="*80)
    print("Test completed!")
    print("="*80 + "\n")


def test_gradebook_query_count():
    """Test query count for gradebook view with initial assessments"""
    
    print("\n" + "="*80)
    print("Testing Gradebook View Query Count")
    print("="*80)
    
    # Find courses with initial assessments
    from courses.models import Course
    from django.db.models import Q
    
    courses = Course.objects.filter(
        Q(quizzes__is_initial_assessment=True) |
        Q(coursetopic__topic__quiz__is_initial_assessment=True)
    ).distinct()[:1]
    
    if not courses.exists():
        print("❌ No courses with initial assessments found")
        return
    
    course = courses.first()
    print(f"\n✓ Testing with course: {course.title}")
    
    # Get students enrolled in the course
    from courses.models import CourseEnrollment
    students = CustomUser.objects.filter(
        course_enrollments__course=course
    ).distinct()[:20]  # Test with 20 students
    
    if not students.exists():
        print("❌ No students enrolled in this course")
        return
    
    print(f"✓ Found {students.count()} enrolled students")
    
    # Get quizzes including initial assessments
    quizzes = Quiz.objects.filter(
        Q(course=course) | Q(topics__courses=course),
        is_active=True
    ).exclude(is_vak_test=True).distinct()
    
    print(f"✓ Found {quizzes.count()} quizzes (including initial assessments)")
    
    # Test the optimized query from gradebook views
    print("\n" + "-"*80)
    print("Fetching quiz attempts with optimization")
    print("-"*80)
    
    with CaptureQueriesContext(connection) as context:
        quiz_attempts = QuizAttempt.objects.filter(
            user__in=students,
            quiz__in=quizzes,
            is_completed=True
        ).select_related(
            'quiz__course', 
            'quiz__rubric',
            'user'
        ).prefetch_related(
            'quiz__topics__courses',
            'quiz__questions',
            'user_answers__question'
        ).order_by('-end_time')
        
        # Force evaluation and calculate classifications
        attempt_count = 0
        for attempt in quiz_attempts:
            if attempt.quiz.is_initial_assessment:
                classification = attempt.calculate_assessment_classification()
                attempt_count += 1
    
    query_count = len(context.captured_queries)
    
    print(f"\n📊 Results:")
    print(f"   Queries executed: {query_count}")
    print(f"   Initial assessment attempts processed: {attempt_count}")
    print(f"   Total attempts fetched: {quiz_attempts.count()}")
    
    if attempt_count > 0:
        avg_queries = query_count / attempt_count
        print(f"   Average queries per initial assessment: {avg_queries:.1f}")
        
        if avg_queries < 2:
            print(f"\n✅ EXCELLENT: Very efficient query optimization!")
        elif avg_queries < 5:
            print(f"\n✓ GOOD: Efficient query optimization")
        else:
            print(f"\n⚠️  WARNING: Query count higher than expected")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    try:
        test_query_count()
        test_gradebook_query_count()
        
        print("\n" + "="*80)
        print("✓ All tests completed successfully!")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

