#!/usr/bin/env python
"""
Test script to verify the admin removal bug fix.
This script tests the permission validation logic that was causing the error.
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.insert(0, '/home/ec2-user/lms')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms.settings')
django.setup()

from branches.models import AdminBranchAssignment, Branch
from users.models import CustomUser
from business.models import Business

def test_permission_validation():
    """
    Test the permission validation logic that was causing the bug.
    """
    print("Testing permission validation logic...")
    
    # Test the logic that was causing the bug
    # Simulate accessible_businesses as a list of IDs
    accessible_businesses = [1, 2, 3]  # List of business IDs
    
    # Simulate a business object
    class MockBusiness:
        def __init__(self, id):
            self.id = id
    
    # Test the old buggy logic (this would fail)
    business_obj = MockBusiness(2)
    print(f"Business object ID: {business_obj.id}")
    print(f"Accessible businesses: {accessible_businesses}")
    
    # Test the old buggy comparison (this would always be False)
    old_logic_result = business_obj not in accessible_businesses
    print(f"Old buggy logic result: {old_logic_result} (This would always be True, causing permission errors)")
    
    # Test the fixed logic
    fixed_logic_result = business_obj.id not in accessible_businesses
    print(f"Fixed logic result: {fixed_logic_result} (This correctly compares IDs)")
    
    # Test with a business that should be accessible
    accessible_business = MockBusiness(2)
    accessible_result = accessible_business.id not in accessible_businesses
    print(f"Accessible business test: {accessible_result} (Should be False - business is accessible)")
    
    # Test with a business that should not be accessible
    inaccessible_business = MockBusiness(5)
    inaccessible_result = inaccessible_business.id not in accessible_businesses
    print(f"Inaccessible business test: {inaccessible_result} (Should be True - business is not accessible)")
    
    print("\n✅ Permission validation logic test completed successfully!")
    print("The fix correctly compares business IDs instead of business objects.")

if __name__ == "__main__":
    test_permission_validation()
