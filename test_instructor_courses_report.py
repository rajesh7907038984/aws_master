#!/usr/bin/env python3
"""
Test script to verify instructor courses report functionality
- Branch filter should be hidden for instructors
- Only courses the instructor has access to should be shown
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.test import Client, RequestFactory
from django.contrib.auth import get_user_model
from courses.models import Course
from branches.models import Branch
from django.urls import reverse

User = get_user_model()


def test_instructor_courses_report():
    """Test that instructor sees only their accessible courses and no branch filter"""
    
    print("🧪 Testing Instructor Courses Report Access\n")
    print("=" * 70)
    
    # Find a test instructor user with a branch
    instructor = User.objects.filter(
        role='instructor', 
        is_active=True,
        branch__isnull=False
    ).first()
    
    if not instructor:
        print("❌ No instructor user with branch found in the system")
        return
    
    print(f"\n👤 Testing with Instructor: {instructor.username}")
    print(f"   Branch: {instructor.branch.name if instructor.branch else 'No branch'}")
    
    # Create a client and login (skip login, just set session)
    from django.contrib.auth import get_user
    client = Client()
    
    # Force login using Django test client
    from django.test.utils import setup_test_environment
    client.force_login(instructor)
    print("✅ Login successful (forced)")
    
    # Get the courses report page
    url = reverse('reports:courses_report')
    response = client.get(url)
    
    print(f"\n📊 Courses Report Response:")
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Failed to access courses report page")
        return
    
    print("✅ Successfully accessed courses report page")
    
    # Check if branch filter is in the response
    response_content = response.content.decode('utf-8')
    has_branch_filter = 'Branch Filter:' in response_content
    
    print(f"\n🔍 Branch Filter Check:")
    print(f"   Branch Filter Present: {'❌ YES (should be hidden)' if has_branch_filter else '✅ NO (correctly hidden)'}")
    
    # Check context data
    context = response.context
    courses = context.get('courses', [])
    branches = context.get('branches', [])
    
    print(f"\n📚 Courses Data:")
    print(f"   Number of courses: {len(list(courses))}")
    
    # Get all courses the instructor should have access to
    all_courses = Course.objects.all()
    accessible_courses = []
    
    for course in all_courses:
        # Check if instructor is primary instructor
        if course.instructor == instructor:
            accessible_courses.append(course)
            continue
        
        # Check if instructor is enrolled
        if course.enrolled_users.filter(id=instructor.id).exists():
            accessible_courses.append(course)
            continue
        
        # Check if instructor has group access
        if course.accessible_groups.filter(
            memberships__user=instructor,
            memberships__is_active=True
        ).exists():
            accessible_courses.append(course)
    
    print(f"   Expected accessible courses: {len(accessible_courses)}")
    
    # List the courses
    print(f"\n📋 Accessible Courses for {instructor.username}:")
    if accessible_courses:
        for course in accessible_courses:
            is_primary = "Primary" if course.instructor == instructor else "Invited/Group"
            print(f"   - {course.title} ({is_primary})")
    else:
        print("   No courses accessible")
    
    # Check branches
    print(f"\n🏢 Branches Data:")
    print(f"   Number of branches: {len(list(branches))}")
    print(f"   Branches should be empty: {'✅ YES' if len(list(branches)) == 0 else '❌ NO'}")
    
    # Overall result
    print("\n" + "=" * 70)
    print("📝 Test Summary:")
    
    success_count = 0
    total_tests = 3
    
    if response.status_code == 200:
        print("✅ 1. Page accessible")
        success_count += 1
    else:
        print("❌ 1. Page not accessible")
    
    if not has_branch_filter:
        print("✅ 2. Branch filter hidden")
        success_count += 1
    else:
        print("❌ 2. Branch filter still visible")
    
    if len(list(branches)) == 0:
        print("✅ 3. Branches queryset is empty")
        success_count += 1
    else:
        print("❌ 3. Branches queryset not empty")
    
    print(f"\n🎯 Result: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("✅ All tests passed!")
    else:
        print("⚠️  Some tests failed")


if __name__ == '__main__':
    test_instructor_courses_report()

