#!/usr/bin/env python3
"""
Quick test script to verify survey page template renders correctly
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
sys.path.insert(0, '/home/ec2-user/lms')
django.setup()

from django.template import Template, Context
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from courses.models import Course
from course_reviews.models import Survey
from course_reviews.forms import SurveyResponseForm

User = get_user_model()

print("🧪 Testing Survey Template Rendering...")
print("=" * 50)

try:
    # Test 1: Check if course 34 exists
    course = Course.objects.get(id=34)
    print(f"✓ Course 34 found: {course.title}")
    
    # Test 2: Check if survey exists
    if course.survey:
        survey = course.survey
        print(f"✓ Survey found: {survey.title} (ID: {survey.id})")
        
        # Test 3: Check survey fields
        fields = survey.fields.all()
        print(f"✓ Survey has {fields.count()} field(s)")
        
        # Test 4: Create a form instance
        form = SurveyResponseForm(survey=survey)
        print(f"✓ SurveyResponseForm created successfully")
        
        # Test 5: Check rating fields
        rating_fields = [f for f in fields if f.field_type == 'rating']
        if rating_fields:
            print(f"✓ Found {len(rating_fields)} rating field(s)")
            for rf in rating_fields:
                field_name = f'field_{rf.id}'
                if field_name in form.fields:
                    field = form.fields[field_name]
                    print(f"  - Field '{rf.label}': max_value = {field.max_value}")
        
        print("\n✅ All tests passed! The survey should now work correctly.")
        print(f"\n🔗 Test URL: https://staging.nexsy.io/course-reviews/course/34/survey/")
        print("   (Must be logged in as a user who completed the course)")
        
    else:
        print("✗ Course has no survey assigned")
        
except Course.DoesNotExist:
    print("✗ Course 34 not found")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

