#!/usr/bin/env python3
"""
Teams Integration Diagnostic Script
Run this to diagnose Teams sync issues for conferences
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.base')

# Initialize Django
django.setup()

from account_settings.models import TeamsIntegration
from conferences.models import Conference
from django.contrib.auth import get_user_model

def diagnose_teams_sync_issue():
    """Diagnose Teams sync issues"""

    print("=" * 70)
    print("TEAMS INTEGRATION DIAGNOSTIC REPORT")
    print("=" * 70)
    print()

    # Find the conference
    try:
        conference = Conference.objects.get(id=52)
        print(f"[OK] Conference found: {conference.title}")
        print(f"  - Created by: {conference.created_by.username} ({conference.created_by.email})")
        print(f"  - Meeting platform: {conference.meeting_platform}")
        print(f"  - Meeting ID: {conference.meeting_id or 'None'}")
        print(f"  - Meeting link: {conference.meeting_link or 'None'}")
        print(f"  - Branch: {conference.created_by.branch.name if conference.created_by.branch else 'None'}")
        print()
    except Conference.DoesNotExist:
        print("[ERROR] Conference with ID 52 not found")
        return

    # Check branch-level Teams integration
    if conference.created_by.branch:
        branch_integrations = TeamsIntegration.objects.filter(
            branch=conference.created_by.branch,
            is_active=True
        )

        if branch_integrations.exists():
            integration = branch_integrations.first()
            print("[OK] Branch-level Teams integration found:")
            print(f"  - Name: {integration.name}")
            print(f"  - Active: {integration.is_active}")
            print(f"  - Client ID: {'***' + integration.client_id[-4:] if integration.client_id else 'MISSING'}")
            print(f"  - Tenant ID: {'***' + integration.tenant_id[-4:] if integration.tenant_id else 'MISSING'}")
            print(f"  - Service Account: {integration.service_account_email or 'NOT SET'}")
            print(f"  - Last sync: {integration.last_sync_datetime or 'Never'}")
        else:
            print("[ERROR] No active branch-level Teams integration found")
            print("  This is likely the ROOT CAUSE of the sync failure!")

            # Check if there are inactive integrations
            inactive_integrations = TeamsIntegration.objects.filter(branch=conference.created_by.branch)
            if inactive_integrations.exists():
                print(f"  Found {inactive_integrations.count()} inactive integration(s)")
                for integration in inactive_integrations:
                    print(f"    - {integration.name}: Active={integration.is_active}")
            else:
                print("  No branch integrations configured at all")
    else:
        print("[ERROR] Conference creator has no branch assigned")

    print()

    # Check user-level Teams integration as fallback
    user_integrations = TeamsIntegration.objects.filter(
        user=conference.created_by,
        is_active=True
    )

    if user_integrations.exists():
        integration = user_integrations.first()
        print("[OK] User-level Teams integration found (fallback):")
        print(f"  - Name: {integration.name}")
        print(f"  - Client ID: {'***' + integration.client_id[-4:] if integration.client_id else 'MISSING'}")
        print(f"  - Tenant ID: {'***' + integration.tenant_id[-4:] if integration.tenant_id else 'MISSING'}")
    else:
        print("[ERROR] No active user-level Teams integration found")

    print()

    # Check branch Teams integration enablement
    if conference.created_by.branch:
        branch_enabled = getattr(conference.created_by.branch, 'teams_integration_enabled', False)
        print(f"Branch Teams integration enabled: {'[YES]' if branch_enabled else '[NO]'}")
        if not branch_enabled:
            print("  This is another potential cause - branch integration is disabled!")

    print()

    # Provide solutions
    print("=" * 70)
    print("RECOMMENDED SOLUTIONS:")
    print("=" * 70)

    issues_found = []

    if not conference.created_by.branch:
        issues_found.append("Conference creator has no branch assigned")

    if conference.created_by.branch and not TeamsIntegration.objects.filter(
        branch=conference.created_by.branch, is_active=True
    ).exists():
        issues_found.append("No active branch-level Teams integration configured")

    if conference.created_by.branch and not getattr(conference.created_by.branch, 'teams_integration_enabled', False):
        issues_found.append("Branch-level Teams integration is disabled")

    if not TeamsIntegration.objects.filter(user=conference.created_by, is_active=True).exists():
        issues_found.append("No active user-level Teams integration as fallback")

    if not conference.meeting_id:
        issues_found.append("Conference has no meeting ID")

    if issues_found:
        print("ISSUES FOUND:")
        for i, issue in enumerate(issues_found, 1):
            print(f"{i}. {issue}")
        print()

    print("TO FIX THE SYNC ISSUE:")
    print()
    print("1. ENABLE BRANCH-LEVEL TEAMS INTEGRATION:")
    print("   - Go to Account Settings → Integrations → Microsoft Teams")
    print("   - Ensure 'Teams Integration' is enabled for your branch")
    print("   - Configure Client ID, Client Secret, Tenant ID, and Service Account Email")
    print()

    print("2. VERIFY SERVICE ACCOUNT:")
    print("   - Service account email must exist in Azure AD")
    print("   - Must have Exchange Online license")
    print("   - Must have Teams API permissions")
    print()

    print("3. TEST CONNECTION:")
    print("   - Use the 'Test Connection' button in Teams integration settings")
    print("   - Verify API connectivity before attempting sync")
    print()

    print("4. CHECK PERMISSIONS:")
    print("   - Conference creator must be branch admin")
    print("   - Branch must have Teams integration enabled")
    print("   - Service account must have Teams API access")
    print()

if __name__ == '__main__':
    diagnose_teams_sync_issue()
