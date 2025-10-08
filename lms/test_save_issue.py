#!/usr/bin/env python
"""
Test if there's an issue with saving ScormAttempt with score data
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

def test_save():
    print("=" * 80)
    print("TEST: ScormAttempt Save Behavior")
    print("=" * 80)
    
    # Get an attempt
    attempt = ScormAttempt.objects.order_by('-last_accessed').first()
    
    if not attempt:
        print("No attempts found")
        return
    
    print(f"\n📊 Attempt ID: {attempt.id}")
    print(f"   Initial score_raw: {attempt.score_raw}")
    print(f"   Initial cmi_data keys: {list(attempt.cmi_data.keys())[:10]}")
    
    # Manually set score
    print(f"\n🔄 Setting score_raw = 75.5")
    attempt.score_raw = Decimal('75.5')
    print(f"   After set (before save): {attempt.score_raw}")
    
    # Set in cmi_data too
    print(f"\n🔄 Setting cmi_data['cmi.core.score.raw'] = '75.5'")
    attempt.cmi_data['cmi.core.score.raw'] = '75.5'
    print(f"   After set: {attempt.cmi_data.get('cmi.core.score.raw')}")
    
    # Save
    print(f"\n🔄 Calling attempt.save()")
    attempt.save()
    print(f"   After save (same object): {attempt.score_raw}")
    print(f"   CMI data: {attempt.cmi_data.get('cmi.core.score.raw')}")
    
    # Reload from DB
    print(f"\n🔄 Reloading from database")
    attempt_id = attempt.id
    attempt_reloaded = ScormAttempt.objects.get(id=attempt_id)
    print(f"   Reloaded score_raw: {attempt_reloaded.score_raw}")
    print(f"   Reloaded CMI data: {attempt_reloaded.cmi_data.get('cmi.core.score.raw')}")
    
    # Check if it persisted
    if attempt_reloaded.score_raw and float(attempt_reloaded.score_raw) == 75.5:
        print(f"\n✅ SUCCESS: Score persisted correctly!")
    else:
        print(f"\n❌ FAILURE: Score did NOT persist! Expected 75.5, got {attempt_reloaded.score_raw}")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    try:
        test_save()
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

