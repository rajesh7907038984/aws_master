#!/usr/bin/env python
"""
Test script to verify Teams auto-registration fixes
Run this in Django shell: python manage.py shell < test_teams_registration.py
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms.settings')
django.setup()

from django.contrib.auth import get_user_model
from conferences.models import Conference
from teams_integration.models import TeamsIntegration

User = get_user_model()

print("=" * 80)
print("MICROSOFT TEAMS AUTO-REGISTRATION TEST")
print("=" * 80)
print()

# Test 1: Check if users have emails
print("TEST 1: Checking user email addresses...")
print("-" * 80)
learners = User.objects.filter(role='learner')
learners_without_email = learners.filter(email__isnull=True) | learners.filter(email='')
print(f"Total learners: {learners.count()}")
print(f"Learners WITHOUT email: {learners_without_email.count()}")
if learners_without_email.exists():
    print("⚠️  WARNING: These learners cannot join Teams meetings:")
    for learner in learners_without_email[:5]:
        print(f"   - {learner.username} (ID: {learner.id})")
    if learners_without_email.count() > 5:
        print(f"   ... and {learners_without_email.count() - 5} more")
else:
    print("✅ All learners have email addresses")
print()

# Test 2: Check Teams integrations
print("TEST 2: Checking Teams integrations...")
print("-" * 80)
integrations = TeamsIntegration.objects.all()
active_integrations = integrations.filter(is_active=True)
print(f"Total Teams integrations: {integrations.count()}")
print(f"Active integrations: {active_integrations.count()}")
if active_integrations.exists():
    print("✅ Active Teams integrations found:")
    for integration in active_integrations:
        print(f"   - {integration.user.username}: {integration.user.email}")
else:
    print("⚠️  WARNING: No active Teams integrations found")
    print("   Auto-registration will fail without Teams integration")
print()

# Test 3: Check Teams conferences
print("TEST 3: Checking Teams conferences...")
print("-" * 80)
teams_conferences = Conference.objects.filter(meeting_platform='teams')
print(f"Total Teams conferences: {teams_conferences.count()}")
if teams_conferences.exists():
    conferences_without_meeting_id = teams_conferences.filter(meeting_id__isnull=True) | teams_conferences.filter(meeting_id='')
    conferences_without_link = teams_conferences.filter(meeting_link__isnull=True) | teams_conferences.filter(meeting_link='')
    
    print(f"Conferences WITHOUT meeting_id: {conferences_without_meeting_id.count()}")
    if conferences_without_meeting_id.exists():
        print("⚠️  WARNING: These conferences won't support auto-registration:")
        for conf in conferences_without_meeting_id[:5]:
            print(f"   - {conf.title} (ID: {conf.id})")
    
    print(f"Conferences WITHOUT meeting_link: {conferences_without_link.count()}")
    if conferences_without_link.exists():
        print("❌ ERROR: These conferences cannot be joined at all:")
        for conf in conferences_without_link[:5]:
            print(f"   - {conf.title} (ID: {conf.id})")
    
    if not conferences_without_meeting_id.exists() and not conferences_without_link.exists():
        print("✅ All Teams conferences are properly configured")
else:
    print("ℹ️  No Teams conferences found")
print()

# Test 4: Check conference organizers
print("TEST 4: Checking conference organizers...")
print("-" * 80)
if teams_conferences.exists():
    organizers_without_email = set()
    for conf in teams_conferences:
        if conf.created_by and (not conf.created_by.email or not conf.created_by.email.strip()):
            organizers_without_email.add(conf.created_by.username)
    
    if organizers_without_email:
        print(f"⚠️  WARNING: {len(organizers_without_email)} organizer(s) without email:")
        for organizer in list(organizers_without_email)[:5]:
            print(f"   - {organizer}")
        print("   Auto-registration may fail for their conferences")
    else:
        print("✅ All conference organizers have email addresses")
else:
    print("ℹ️  No Teams conferences to check")
print()

# Test 5: Check for meet-now links
print("TEST 5: Checking for problematic meeting links...")
print("-" * 80)
if teams_conferences.exists():
    problematic_conferences = []
    for conf in teams_conferences:
        if conf.meeting_link and ('meet-now' in conf.meeting_link.lower() or '/v2/meet/meet-now' in conf.meeting_link.lower()):
            if not conf.meeting_id:
                problematic_conferences.append(conf)
    
    if problematic_conferences:
        print(f"⚠️  WARNING: {len(problematic_conferences)} conference(s) with instant meeting links:")
        for conf in problematic_conferences[:5]:
            print(f"   - {conf.title} (ID: {conf.id})")
            print(f"     Link: {conf.meeting_link[:80]}...")
        print("   These conferences will be blocked from joining")
    else:
        print("✅ No problematic meeting links found")
else:
    print("ℹ️  No Teams conferences to check")
print()

# Summary
print("=" * 80)
print("SUMMARY")
print("=" * 80)

issues = []
if learners_without_email.count() > 0:
    issues.append(f"{learners_without_email.count()} learner(s) without email addresses")
if active_integrations.count() == 0:
    issues.append("No active Teams integrations")
if teams_conferences.exists():
    conferences_without_meeting_id = teams_conferences.filter(meeting_id__isnull=True) | teams_conferences.filter(meeting_id='')
    if conferences_without_meeting_id.count() > 0:
        issues.append(f"{conferences_without_meeting_id.count()} conference(s) without meeting_id")

if issues:
    print("⚠️  Issues found that may affect Teams auto-registration:")
    for i, issue in enumerate(issues, 1):
        print(f"   {i}. {issue}")
    print()
    print("📝 Recommended actions:")
    if learners_without_email.count() > 0:
        print("   - Ask learners to add email addresses to their profiles")
    if active_integrations.count() == 0:
        print("   - Set up Teams integration for instructors")
    if teams_conferences.exists():
        conferences_without_meeting_id = teams_conferences.filter(meeting_id__isnull=True) | teams_conferences.filter(meeting_id='')
        if conferences_without_meeting_id.count() > 0:
            print("   - Update conferences to include Teams meeting_id")
else:
    print("✅ All systems ready for Teams auto-registration!")
    print("   - All learners have emails")
    print("   - Teams integrations are active")
    print("   - Conferences are properly configured")

print()
print("=" * 80)
print("Test complete!")
print("=" * 80)



