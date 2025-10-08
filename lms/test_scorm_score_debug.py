#!/usr/bin/env python
"""
Debug script to check what happens during SetValue
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from decimal import Decimal
from scorm.models import ScormAttempt
from scorm.api_handler_enhanced import ScormAPIHandlerEnhanced

def debug_set_value():
    """Debug SetValue behavior"""
    
    print("=" * 80)
    print("DEBUG: SetValue Score Behavior")
    print("=" * 80)
    
    # Get a test attempt
    attempt = ScormAttempt.objects.order_by('-last_accessed').first()
    
    if not attempt:
        print("❌ No SCORM attempts found")
        return
    
    print(f"\n📊 Attempt ID: {attempt.id}")
    print(f"   User: {attempt.user.username}")
    
    # Create handler
    handler = ScormAPIHandlerEnhanced(attempt)
    handler.initialize()
    
    # Check initial state
    print(f"\n🔍 BEFORE SetValue:")
    print(f"   handler.attempt.score_raw (in memory): {handler.attempt.score_raw}")
    print(f"   handler.attempt.cmi_data: {handler.attempt.cmi_data.get('cmi.core.score.raw', 'KEY NOT FOUND')}")
    print(f"   DB attempt.score_raw: {attempt.score_raw}")
    
    # Set score
    test_score = "92.5"
    print(f"\n🔄 Calling SetValue('cmi.core.score.raw', '{test_score}')")
    result = handler.set_value('cmi.core.score.raw', test_score)
    print(f"   Result: {result}")
    
    # Check after SetValue
    print(f"\n🔍 AFTER SetValue (before refresh):")
    print(f"   handler.attempt.score_raw (in memory): {handler.attempt.score_raw}")
    print(f"   handler.attempt.cmi_data: {handler.attempt.cmi_data.get('cmi.core.score.raw', 'KEY NOT FOUND')}")
    print(f"   type(handler.attempt.score_raw): {type(handler.attempt.score_raw)}")
    
    # Refresh from DB (before commit)
    attempt.refresh_from_db()
    print(f"\n🔍 AFTER refresh_from_db (before commit):")
    print(f"   DB attempt.score_raw: {attempt.score_raw}")
    print(f"   DB attempt.cmi_data: {attempt.cmi_data.get('cmi.core.score.raw', 'KEY NOT FOUND')}")
    
    # Now commit
    print(f"\n🔄 Calling Commit()")
    result = handler.commit()
    print(f"   Result: {result}")
    
    # Check after commit
    print(f"\n🔍 AFTER Commit (before refresh):")
    print(f"   handler.attempt.score_raw (in memory): {handler.attempt.score_raw}")
    print(f"   handler.attempt.cmi_data: {handler.attempt.cmi_data.get('cmi.core.score.raw', 'KEY NOT FOUND')}")
    
    # Refresh from DB (after commit)
    attempt.refresh_from_db()
    print(f"\n🔍 AFTER refresh_from_db (after commit):")
    print(f"   DB attempt.score_raw: {attempt.score_raw}")
    print(f"   DB attempt.cmi_data: {attempt.cmi_data.get('cmi.core.score.raw', 'KEY NOT FOUND')}")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    try:
        debug_set_value()
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

