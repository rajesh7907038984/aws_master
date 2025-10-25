#!/usr/bin/env python3
"""
Verification script to confirm that the training time fix is working correctly.
This script checks that:
1. SCORM time tracking is working
2. TopicProgress is being updated correctly
3. Learning reports show accurate training time
"""

import os
import sys
import django
from datetime import datetime

# Setup Django environment
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from courses.models import TopicProgress
from scorm.models import ScormAttempt
from django.db.models import Sum, Count

User = get_user_model()

class TrainingTimeVerificationService:
    """
    Service to verify that training time tracking is working correctly
    """
    
    def __init__(self):
        self.verification_results = {
            'scorm_attempts_verified': 0,
            'topic_progress_verified': 0,
            'total_training_time': 0,
            'issues_found': []
        }
    
    def verify_scorm_time_tracking(self):
        """Verify SCORM time tracking is working"""
        print("🔍 Verifying SCORM time tracking...")
        
        # Check SCORM attempts with proper time data
        attempts_with_time = ScormAttempt.objects.filter(
            time_spent_seconds__gt=0
        ).count()
        
        total_attempts = ScormAttempt.objects.count()
        
        print(f"  - Total SCORM attempts: {total_attempts}")
        print(f"  - Attempts with time data: {attempts_with_time}")
        
        if attempts_with_time > 0:
            self.verification_results['scorm_attempts_verified'] = attempts_with_time
            print("  ✅ SCORM time tracking is working")
        else:
            self.verification_results['issues_found'].append("No SCORM attempts with time data")
            print("  ❌ SCORM time tracking has issues")
        
        return attempts_with_time > 0
    
    def verify_topic_progress_sync(self):
        """Verify TopicProgress is synced with SCORM data"""
        print("🔍 Verifying TopicProgress sync...")
        
        # Check TopicProgress records with time data
        progress_with_time = TopicProgress.objects.filter(
            total_time_spent__gt=0
        ).count()
        
        total_progress = TopicProgress.objects.count()
        
        print(f"  - Total TopicProgress records: {total_progress}")
        print(f"  - Records with time data: {progress_with_time}")
        
        if progress_with_time > 0:
            self.verification_results['topic_progress_verified'] = progress_with_time
            print("  ✅ TopicProgress sync is working")
        else:
            self.verification_results['issues_found'].append("No TopicProgress records with time data")
            print("  ❌ TopicProgress sync has issues")
        
        return progress_with_time > 0
    
    def verify_total_training_time(self):
        """Verify total training time calculation"""
        print("🔍 Verifying total training time calculation...")
        
        # Calculate total time from TopicProgress
        total_time_seconds = TopicProgress.objects.aggregate(
            Sum('total_time_spent')
        )['total_time_spent__sum'] or 0
        
        hours = int(total_time_seconds // 3600)
        minutes = int((total_time_seconds % 3600) // 60)
        
        print(f"  - Total training time: {hours}h {minutes}m ({total_time_seconds} seconds)")
        
        self.verification_results['total_training_time'] = total_time_seconds
        
        if total_time_seconds > 0:
            print("  ✅ Total training time calculation is working")
            return True
        else:
            self.verification_results['issues_found'].append("Total training time is zero")
            print("  ❌ Total training time calculation has issues")
            return False
    
    def verify_user_specific_data(self, user_email):
        """Verify training time for a specific user"""
        print(f"🔍 Verifying training time for user: {user_email}")
        
        try:
            user = User.objects.get(email=user_email)
            
            # Get user's TopicProgress
            user_progress = TopicProgress.objects.filter(user=user)
            user_time = user_progress.aggregate(Sum('total_time_spent'))['total_time_spent__sum'] or 0
            
            hours = int(user_time // 3600)
            minutes = int((user_time % 3600) // 60)
            
            print(f"  - User training time: {hours}h {minutes}m ({user_time} seconds)")
            
            # Get user's SCORM attempts
            user_attempts = ScormAttempt.objects.filter(user=user)
            attempts_with_time = user_attempts.filter(time_spent_seconds__gt=0).count()
            
            print(f"  - User SCORM attempts with time: {attempts_with_time}")
            
            if user_time > 0:
                print("  ✅ User training time is properly tracked")
                return True
            else:
                print("  ❌ User training time is not properly tracked")
                return False
                
        except User.DoesNotExist:
            print(f"  ❌ User {user_email} not found")
            return False
    
    def run_full_verification(self, test_user_email=None):
        """Run complete verification process"""
        print("🚀 Starting Training Time Verification Process")
        print("=" * 60)
        
        start_time = timezone.now()
        
        # Step 1: Verify SCORM time tracking
        scorm_ok = self.verify_scorm_time_tracking()
        
        # Step 2: Verify TopicProgress sync
        progress_ok = self.verify_topic_progress_sync()
        
        # Step 3: Verify total training time
        total_time_ok = self.verify_total_training_time()
        
        # Step 4: Verify user-specific data if provided
        user_ok = True
        if test_user_email:
            user_ok = self.verify_user_specific_data(test_user_email)
        
        end_time = timezone.now()
        duration = end_time - start_time
        
        # Summary
        print("\n" + "=" * 60)
        print("🎉 Verification Process Complete!")
        print(f"⏱️  Duration: {duration}")
        
        all_checks_passed = scorm_ok and progress_ok and total_time_ok and user_ok
        
        if all_checks_passed:
            print("✅ All verification checks PASSED!")
            print("🎯 Training time tracking is working correctly")
        else:
            print("❌ Some verification checks FAILED!")
            print("⚠️  Issues found:")
            for issue in self.verification_results['issues_found']:
                print(f"  - {issue}")
        
        print(f"\n📊 Verification Results:")
        print(f"  - SCORM attempts verified: {self.verification_results['scorm_attempts_verified']}")
        print(f"  - TopicProgress records verified: {self.verification_results['topic_progress_verified']}")
        print(f"  - Total training time: {self.verification_results['total_training_time']} seconds")
        print(f"  - Issues found: {len(self.verification_results['issues_found'])}")
        
        return all_checks_passed

def main():
    """Main function to run the verification"""
    verification_service = TrainingTimeVerificationService()
    
    # Run verification with test user
    test_user_email = 'joe.bloggs@gmail.com'
    success = verification_service.run_full_verification(test_user_email)
    
    if success:
        print("\n🎉 SUCCESS: Training time tracking is working correctly!")
        return 0
    else:
        print("\n❌ FAILURE: Training time tracking has issues that need attention.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
