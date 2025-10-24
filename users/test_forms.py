"""
Test script to verify enhanced forms are working correctly
"""

from django.test import TestCase
from django.test.client import RequestFactory
from django.contrib.auth import get_user_model
from .forms_enhanced import EnhancedUserCreationForm, EnhancedUserChangeForm
from branches.models import Branch
from groups.models import BranchGroup

User = get_user_model()

def test_enhanced_forms():
    """Test that enhanced forms have the required fields"""
    
    # Test EnhancedUserCreationForm
    print("Testing EnhancedUserCreationForm...")
    form = EnhancedUserCreationForm()
    required_fields = ['user_groups', 'course_groups']
    
    for field in required_fields:
        if field in form.fields:
            print(f"✓ {field} field found")
        else:
            print(f"✗ {field} field missing")
    
    # Test EnhancedUserChangeForm
    print("\nTesting EnhancedUserChangeForm...")
    form = EnhancedUserChangeForm()
    
    for field in required_fields:
        if field in form.fields:
            print(f"✓ {field} field found")
        else:
            print(f"✗ {field} field missing")
    
    print("\nForm field analysis complete!")

if __name__ == "__main__":
    test_enhanced_forms()
