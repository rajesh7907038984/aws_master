#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification Script for Mandatory Auto-Recording
Date: November 20, 2025

This script verifies that all Teams meetings have auto-recording enabled.
"""

import os
import sys
import django

# Set up Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from conferences.models import Conference
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count


def verify_recording_enforcement():
    """Verify that auto-recording is properly enforced"""
    print("=" * 80)
    print("MANDATORY AUTO-RECORDING VERIFICATION")
    print("=" * 80)
    print()
    
    # Check recent Teams conferences
    print("1. Checking Recent Teams Conferences")
    print("-" * 80)
    
    recent_teams = Conference.objects.filter(
        meeting_platform='teams',
        created_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-created_at')
    
    if recent_teams.exists():
        print("Found {} Teams conferences in the last 7 days:\n".format(recent_teams.count()))
        
        for conf in recent_teams[:10]:  # Show first 10
            status_emoji = "✅" if conf.auto_recording_status == 'enabled' else "⚠️"
            print("{} {}".format(status_emoji, conf.title))
            print("   Status: {}".format(conf.auto_recording_status))
            print("   Created: {}".format(conf.created_at.strftime('%Y-%m-%d %H:%M:%S')))
            if conf.auto_recording_enabled_at:
                print("   Recording Enabled: {}".format(conf.auto_recording_enabled_at.strftime('%Y-%m-%d %H:%M:%S')))
            print()
    else:
        print("No Teams conferences found in the last 7 days.")
        print("Create a new conference to test auto-recording.\n")
    
    # Check recording status distribution
    print("2. Recording Status Distribution (All Time)")
    print("-" * 80)
    
    status_dist = Conference.objects.filter(
        meeting_platform='teams'
    ).values('auto_recording_status').annotate(count=Count('id')).order_by('-count')
    
    if status_dist:
        print()
        for stat in status_dist:
            status = stat['auto_recording_status']
            count = stat['count']
            percentage = (count / Conference.objects.filter(meeting_platform='teams').count()) * 100
            
            if status == 'enabled':
                emoji = "✅"
            elif status.startswith('failed'):
                emoji = "❌"
            else:
                emoji = "⏳"
            
            print("{} {:30s}: {:4d} ({:5.1f}%)".format(emoji, status, count, percentage))
        print()
    else:
        print("No Teams conferences found.\n")
    
    # Check conferences with recordings
    print("3. Conferences with Recordings")
    print("-" * 80)
    
    from conferences.models import ConferenceRecording
    
    recordings_count = ConferenceRecording.objects.filter(
        conference__meeting_platform='teams'
    ).count()
    
    onedrive_recordings = ConferenceRecording.objects.filter(
        conference__meeting_platform='teams',
        stored_in_onedrive=True
    ).count()
    
    print("Total Recordings: {}".format(recordings_count))
    print("OneDrive Recordings: {}".format(onedrive_recordings))
    
    if recordings_count > 0:
        print("OneDrive Storage Rate: {:.1f}%".format((onedrive_recordings/recordings_count)*100))
    print()
    
    # Check for failed recordings
    print("4. Failed Recording Status")
    print("-" * 80)
    
    failed_conferences = Conference.objects.filter(
        meeting_platform='teams',
        auto_recording_status__startswith='failed'
    ).order_by('-created_at')
    
    if failed_conferences.exists():
        print("⚠️ Found {} conferences with failed recording setup:\n".format(failed_conferences.count()))
        
        for conf in failed_conferences[:5]:  # Show first 5
            print("Conference: {}".format(conf.title))
            print("Status: {}".format(conf.auto_recording_status))
            print("Created: {}".format(conf.created_at.strftime('%Y-%m-%d %H:%M:%S')))
            print()
        
        print("ACTION REQUIRED:")
        print("- Check Teams integration credentials")
        print("- Verify API permissions (OnlineMeetings.ReadWrite.All)")
        print("- Review logs for error details")
        print()
    else:
        print("✅ No failed recording setups found.\n")
    
    # Verify code implementation
    print("5. Code Implementation Check")
    print("-" * 80)
    
    # Check if teams_api.py has the enforcement code
    teams_api_path = '/home/ec2-user/lms/teams_integration/utils/teams_api.py'
    if os.path.exists(teams_api_path):
        with open(teams_api_path, 'r') as f:
            content = f.read()
            if "ENFORCE MANDATORY RECORDING" in content:
                print("✅ Mandatory recording enforcement found in teams_api.py")
            else:
                print("⚠️ Mandatory recording enforcement NOT found in teams_api.py")
            
            if "enable_recording=True" in content:
                print("✅ Default enable_recording=True parameter found")
            else:
                print("⚠️ Default enable_recording=True parameter NOT found")
    else:
        print("❌ teams_api.py not found")
    
    # Check if conferences/views.py explicitly passes enable_recording=True
    views_path = '/home/ec2-user/lms/conferences/views.py'
    if os.path.exists(views_path):
        with open(views_path, 'r') as f:
            content = f.read()
            if "enable_recording=True  # MANDATORY" in content:
                print("✅ Explicit enable_recording=True found in conferences/views.py")
            else:
                print("⚠️ Explicit enable_recording=True NOT found in conferences/views.py")
    else:
        print("❌ conferences/views.py not found")
    
    print()
    
    # Summary
    print("=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    total_teams = Conference.objects.filter(meeting_platform='teams').count()
    enabled_count = Conference.objects.filter(
        meeting_platform='teams',
        auto_recording_status='enabled'
    ).count()
    failed_count = Conference.objects.filter(
        meeting_platform='teams',
        auto_recording_status__startswith='failed'
    ).count()
    
    print("Total Teams Conferences: {}".format(total_teams))
    print("Recording Enabled: {} ({:.1f}%)".format(enabled_count, (enabled_count/total_teams*100) if total_teams > 0 else 0))
    print("Recording Failed: {} ({:.1f}%)".format(failed_count, (failed_count/total_teams*100) if total_teams > 0 else 0))
    print()
    
    if failed_count > 0:
        print("⚠️ ATTENTION: Some conferences have failed recording setup.")
        print("   Check Teams integration and API permissions.")
    elif enabled_count == total_teams and total_teams > 0:
        print("✅ SUCCESS: All conferences have recording enabled!")
    else:
        print("⏳ Some conferences are pending recording setup.")
    
    print()
    print("=" * 80)
    print("For detailed logs, run:")
    print("  tail -f /home/ec2-user/lms/logs/lms.log | grep -i recording")
    print("=" * 80)


if __name__ == '__main__':
    try:
        verify_recording_enforcement()
    except Exception as e:
        print("❌ Error running verification: {}".format(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)

