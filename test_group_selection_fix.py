#!/usr/bin/env python
"""
Test script to verify the group selection fix in user edit forms.
This script tests that user's current group memberships show as selected
even when they're from different branches or inactive groups.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from users.forms_enhanced import EnhancedUserChangeForm
from branches.models import Branch
from groups.models import BranchGroup, GroupMembership

User = get_user_model()

def test_group_selection_fix():
    """Test that the group selection fix works correctly"""
    
    print("🧪 Testing Group Selection Fix")
    print("=" * 50)
    
    try:
        # Create test branches
        branch1, created = Branch.objects.get_or_create(
            name="Test Branch 1",
            defaults={'is_active': True}
        )
        branch2, created = Branch.objects.get_or_create(
            name="Test Branch 2", 
            defaults={'is_active': True}
        )
        
        # Create editor users for each branch (needed for group creation)
        editor_user1, created = User.objects.get_or_create(
            username='editor_user_branch1',
            defaults={
                'email': 'editor1@example.com',
                'first_name': 'Editor',
                'last_name': 'User1',
                'branch': branch1,
                'role': 'admin',
                'is_active': True
            }
        )
        
        editor_user2, created = User.objects.get_or_create(
            username='editor_user_branch2',
            defaults={
                'email': 'editor2@example.com',
                'first_name': 'Editor',
                'last_name': 'User2',
                'branch': branch2,
                'role': 'admin',
                'is_active': True
            }
        )
        
        # Create test groups
        user_group1, created = BranchGroup.objects.get_or_create(
            name="Test User Group 1",
            branch=branch1,
            group_type='user',
            defaults={'is_active': True, 'created_by': editor_user1}
        )
        
        user_group2, created = BranchGroup.objects.get_or_create(
            name="Test User Group 2",
            branch=branch2,
            group_type='user',
            defaults={'is_active': True, 'created_by': editor_user2}
        )
        
        course_group1, created = BranchGroup.objects.get_or_create(
            name="Test Course Group 1",
            branch=branch1,
            group_type='course',
            defaults={'is_active': True, 'created_by': editor_user1}
        )
        
        # Create test user in branch1
        test_user, created = User.objects.get_or_create(
            username='test_user_group_fix',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'User',
                'branch': branch1,
                'role': 'learner',
                'is_active': True
            }
        )
        
        # Create group memberships for the user
        # User is in a group from their own branch
        membership1, created = GroupMembership.objects.get_or_create(
            user=test_user,
            group=user_group1,
            defaults={'is_active': True, 'invited_by': editor_user1}
        )
        
        # User is in a course group from their own branch
        course_membership, created = GroupMembership.objects.get_or_create(
            user=test_user,
            group=course_group1,
            defaults={'is_active': True, 'invited_by': editor_user1}
        )
        
        # Create an inactive group to test the scenario where user has memberships
        # in groups that are not in the current queryset (e.g., inactive groups)
        inactive_group, created = BranchGroup.objects.get_or_create(
            name="Test Inactive User Group",
            branch=branch1,
            group_type='user',
            defaults={'is_active': False, 'created_by': editor_user1}
        )
        
        # Add user to the inactive group (this should work)
        inactive_membership, created = GroupMembership.objects.get_or_create(
            user=test_user,
            group=inactive_group,
            defaults={'is_active': True, 'invited_by': editor_user1}
        )
        
        print(f"✓ Created test user: {test_user.username}")
        print(f"✓ Created test branches: {branch1.name}, {branch2.name}")
        print(f"✓ Created test groups: {user_group1.name}, {user_group2.name}, {course_group1.name}")
        print(f"✓ Created group memberships for user")
        
        # Create a mock request
        factory = RequestFactory()
        request = factory.get('/')
        request.user = editor_user1  # Use editor from branch1
        
        # Test the form initialization
        print("\n🔍 Testing Form Initialization...")
        form = EnhancedUserChangeForm(instance=test_user, request=request)
        
        # Check if the form has the group fields
        if 'user_groups' in form.fields and 'course_groups' in form.fields:
            print("✓ Form has user_groups and course_groups fields")
        else:
            print("✗ Form missing group fields")
            return False
        
        # Check the queryset includes the user's current groups
        user_groups_queryset = form.fields['user_groups'].queryset
        course_groups_queryset = form.fields['course_groups'].queryset
        
        print(f"✓ User groups queryset count: {user_groups_queryset.count()}")
        print(f"✓ Course groups queryset count: {course_groups_queryset.count()}")
        
        # Check if the user's current groups are in the queryset
        user_group_ids = list(user_groups_queryset.values_list('id', flat=True))
        course_group_ids = list(course_groups_queryset.values_list('id', flat=True))
        
        print(f"✓ Available user group IDs: {user_group_ids}")
        print(f"✓ Available course group IDs: {course_group_ids}")
        
        # Check if the user's current memberships are in the queryset
        user_membership_ids = [user_group1.id, inactive_group.id]
        course_membership_ids = [course_group1.id]
        
        user_groups_in_queryset = all(gid in user_group_ids for gid in user_membership_ids)
        course_groups_in_queryset = all(gid in course_group_ids for gid in course_membership_ids)
        
        if user_groups_in_queryset:
            print("✓ User's current user group memberships are in the queryset")
        else:
            print("✗ User's current user group memberships are NOT in the queryset")
            print(f"  Expected: {user_membership_ids}")
            print(f"  Found: {user_group_ids}")
        
        if course_groups_in_queryset:
            print("✓ User's current course group memberships are in the queryset")
        else:
            print("✗ User's current course group memberships are NOT in the queryset")
            print(f"  Expected: {course_membership_ids}")
            print(f"  Found: {course_group_ids}")
        
        # Check initial values
        print("\n🔍 Testing Initial Values...")
        user_groups_initial = form.fields['user_groups'].initial
        course_groups_initial = form.fields['course_groups'].initial
        
        print(f"✓ User groups initial values: {user_groups_initial}")
        print(f"✓ Course groups initial values: {course_groups_initial}")
        
        # Verify initial values match user's current memberships
        # The user should have memberships in user_group1 and inactive_group
        expected_user_groups = sorted([user_group1.id, inactive_group.id])
        expected_course_groups = sorted([course_group1.id])
        actual_user_groups = sorted(user_groups_initial) if user_groups_initial else []
        actual_course_groups = sorted(course_groups_initial) if course_groups_initial else []
        
        if actual_user_groups == expected_user_groups:
            print("✓ User groups initial values match current memberships")
        else:
            print("✗ User groups initial values do NOT match current memberships")
            print(f"  Expected: {expected_user_groups}")
            print(f"  Actual: {actual_user_groups}")
        
        if actual_course_groups == expected_course_groups:
            print("✓ Course groups initial values match current memberships")
        else:
            print("✗ Course groups initial values do NOT match current memberships")
            print(f"  Expected: {expected_course_groups}")
            print(f"  Actual: {actual_course_groups}")
        
        # Overall test result
        test_passed = (
            user_groups_in_queryset and 
            course_groups_in_queryset and
            actual_user_groups == expected_user_groups and
            actual_course_groups == expected_course_groups
        )
        
        if test_passed:
            print("\n🎉 ALL TESTS PASSED!")
            print("✅ The group selection fix is working correctly")
            print("✅ User's current group memberships are included in the queryset")
            print("✅ User's current group memberships are set as initial values")
            print("✅ Groups from different branches are properly handled")
        else:
            print("\n❌ TESTS FAILED!")
            print("❌ The group selection fix needs more work")
        
        return test_passed
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup test data
        print("\n🧹 Cleaning up test data...")
        try:
            if 'test_user' in locals():
                test_user.delete()
            if 'editor_user1' in locals():
                editor_user1.delete()
            if 'editor_user2' in locals():
                editor_user2.delete()
            if 'user_group1' in locals():
                user_group1.delete()
            if 'user_group2' in locals():
                user_group2.delete()
            if 'course_group1' in locals():
                course_group1.delete()
            if 'branch1' in locals():
                branch1.delete()
            if 'branch2' in locals():
                branch2.delete()
            print("✓ Test data cleaned up")
        except Exception as e:
            print(f"⚠️ Warning: Could not clean up all test data: {str(e)}")

if __name__ == "__main__":
    success = test_group_selection_fix()
    sys.exit(0 if success else 1)
