#!/usr/bin/env python3
"""
Test script to debug Azure AD member fetching
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from groups.azure_ad_utils import AzureADGroupAPI, AzureADAPIError
from branches.models import Branch
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_fetch_members():
    """Test fetching members from Azure AD"""
    
    print("\n" + "="*60)
    print("AZURE AD MEMBER FETCH TEST")
    print("="*60 + "\n")
    
    # Get the branch (adjust the branch name as needed)
    try:
        print("Step 1: Finding branch with Teams integration...")
        branches = Branch.objects.filter(teams_integration_enabled=True)
        print(f"Found {branches.count()} branch(es) with Teams integration enabled")
        
        branch = branches.first()
        if not branch:
            print("ERROR: No branch with Teams integration enabled found")
            # Show all branches
            all_branches = Branch.objects.all()
            print(f"\nAll branches ({all_branches.count()}):")
            for b in all_branches:
                print(f"  - {b.name} (Teams enabled: {b.teams_integration_enabled})")
            return
        
        print(f"✓ Using branch: {branch.name}")
        
        # Initialize API
        print("\nStep 2: Initializing Azure AD API...")
        api = AzureADGroupAPI(branch)
        print("✓ Azure AD API initialized successfully")
        
        # Get all groups
        print("\nStep 3: Fetching all groups...")
        categorized_groups = api.get_groups_by_type()
        total_groups = sum(len(groups) for groups in categorized_groups.values())
        print(f"✓ Found {total_groups} total groups")
        
        # Find the Lync group
        lync_group = None
        group_id = None
        
        print("\nStep 4: Finding Lync group...")
        for category in categorized_groups.values():
            for group in category:
                if 'lync' in group['displayName'].lower():
                    lync_group = group
                    group_id = group['id']
                    print(f"✓ Found Lync group: {group['displayName']}")
                    print(f"  Group ID: {group_id}")
                    break
            if lync_group:
                break
        
        if not group_id:
            print("ERROR: Lync group not found!")
            # Show all groups
            print("\nAvailable groups:")
            for category, groups in categorized_groups.items():
                print(f"\n{category} ({len(groups)} groups):")
                for g in groups[:10]:  # Show first 10 only
                    print(f"  - {g['displayName']}")
            return
        
        # Fetch members
        print(f"\nStep 5: Fetching members for group ID: {group_id}")
        members = api.get_group_members(group_id)
        
        print(f"\n{'='*60}")
        print(f"RESULT: Found {len(members)} members")
        print(f"{'='*60}\n")
        
        if members:
            print("First 5 members:")
            for i, member in enumerate(members[:5]):
                print(f"\nMember {i+1}:")
                print(f"  RAW DATA: {member}")
                print(f"  Display Name: {member.get('displayName')}")
                print(f"  Email (mail): {member.get('mail')}")
                print(f"  UPN: {member.get('userPrincipalName')}")
                print(f"  ID: {member.get('id')}")
                print(f"  All fields: {list(member.keys())}")
        else:
            print("⚠️  WARNING: No members found!")
            print("This could mean:")
            print("  1. The API endpoint is not returning members")
            print("  2. API permissions are insufficient")
            print("  3. The group actually has no members")
            
    except AzureADAPIError as e:
        logger.error(f"Azure AD API Error: {str(e)}")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_fetch_members()

