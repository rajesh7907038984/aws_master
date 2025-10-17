#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
E-Learning Ecosystem Verification Script
Verifies SCORM, xAPI, and cmi5 tracking data and identifies issues
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ELearningTracking, ELearningPackage
from lrs.models import Statement, CMI5AU, CMI5Registration, CMI5Session
from django.utils import timezone
from datetime import timedelta
import json

def verify_elearning_ecosystem():
    """Verify complete e-learning ecosystem"""
    print("Verifying E-Learning Ecosystem...")
    print("=" * 60)
    
    # Check SCORM packages
    packages = ELearningPackage.objects.all()
    print(f"Total E-Learning Packages: {packages.count()}")
    
    for package in packages:
        print(f"  - {package.title} ({package.package_type})")
        print(f"    Topic: {package.topic.title}")
        print(f"    Extracted: {package.is_extracted}")
        print(f"    Launch File: {package.launch_file}")
        print(f"    Created: {package.created_at}")
        print("---")
    
    # Check SCORM tracking
    tracking = ELearningTracking.objects.all()
    print(f"\nTotal SCORM Tracking Records: {tracking.count()}")
    
    recent_tracking = tracking.filter(
        updated_at__gte=timezone.now() - timedelta(days=7)
    )
    print(f"Recent Tracking (7 days): {recent_tracking.count()}")
    
    for record in recent_tracking[:10]:
        print(f"  - User: {record.user.username}")
        print(f"    Package: {record.elearning_package.title}")
        print(f"    Status: {record.completion_status}")
        print(f"    Score: {record.score_raw}")
        print(f"    Updated: {record.updated_at}")
        print(f"    Raw data keys: {len(record.raw_data)}")
        print("---")
    
    # Check for incomplete tracking
    incomplete_tracking = ELearningTracking.objects.filter(
        completion_status='incomplete',
        updated_at__gte=timezone.now() - timedelta(days=1)
    )
    print(f"Incomplete tracking records (last 24h): {incomplete_tracking.count()}")
    
    # Check xAPI statements
    statements = Statement.objects.all()
    print(f"\nTotal xAPI Statements: {statements.count()}")
    
    recent_statements = statements.filter(
        timestamp__gte=timezone.now() - timedelta(days=7)
    )
    print(f"Recent Statements (7 days): {recent_statements.count()}")
    
    # Check cmi5 AUs
    aus = CMI5AU.objects.all()
    print(f"\nTotal cmi5 AUs: {aus.count()}")
    
    # Check cmi5 registrations
    registrations = CMI5Registration.objects.all()
    print(f"Total cmi5 Registrations: {registrations.count()}")
    
    # Check cmi5 sessions
    sessions = CMI5Session.objects.all()
    print(f"Total cmi5 Sessions: {sessions.count()}")
    
    active_sessions = sessions.filter(is_active=True)
    print(f"Active Sessions: {active_sessions.count()}")
    
    # Check for potential issues
    print(f"\nPotential Issues:")
    
    # Check for packages without tracking
    packages_without_tracking = []
    for package in packages:
        if not ELearningTracking.objects.filter(elearning_package=package).exists():
            packages_without_tracking.append(package)
    
    if packages_without_tracking:
        print(f"WARNING: Packages without tracking: {len(packages_without_tracking)}")
        for package in packages_without_tracking:
            print(f"    - {package.title} ({package.package_type})")
    else:
        print("OK: All packages have tracking records")
    
    # Check for tracking without recent activity
    stale_tracking = ELearningTracking.objects.filter(
        updated_at__lt=timezone.now() - timedelta(days=30)
    )
    if stale_tracking.exists():
        print(f"WARNING: Stale tracking records (30+ days old): {stale_tracking.count()}")
    else:
        print("OK: No stale tracking records")
    
    # Check for tracking with empty raw_data
    empty_raw_data = ELearningTracking.objects.filter(raw_data={})
    if empty_raw_data.exists():
        print(f"WARNING: Tracking records with empty raw_data: {empty_raw_data.count()}")
    else:
        print("OK: All tracking records have raw_data")
    
    return {
        'packages': packages.count(),
        'tracking': tracking.count(),
        'statements': statements.count(),
        'aus': aus.count(),
        'registrations': registrations.count(),
        'sessions': sessions.count(),
        'packages_without_tracking': len(packages_without_tracking),
        'stale_tracking': stale_tracking.count(),
        'empty_raw_data': empty_raw_data.count()
    }

def check_recent_activity():
    """Check for recent SCORM activity"""
    print(f"\nRecent Activity Check:")
    print("=" * 40)
    
    # Check last 24 hours
    last_24h = timezone.now() - timedelta(hours=24)
    recent_tracking = ELearningTracking.objects.filter(
        updated_at__gte=last_24h
    ).order_by('-updated_at')
    
    print(f"Tracking updates in last 24h: {recent_tracking.count()}")
    
    for record in recent_tracking[:5]:
        print(f"  - {record.user.username} - {record.elearning_package.title}")
        print(f"    Status: {record.completion_status}")
        print(f"    Score: {record.score_raw}")
        print(f"    Updated: {record.updated_at}")
        print(f"    Raw data: {len(record.raw_data)} elements")
        print("---")
    
    return recent_tracking.count()

def check_authentication_issues():
    """Check for potential authentication issues"""
    print(f"\nAuthentication Issues Check:")
    print("=" * 40)
    
    # Check for tracking records without proper user association
    orphaned_tracking = ELearningTracking.objects.filter(user__isnull=True)
    if orphaned_tracking.exists():
        print(f"WARNING: Orphaned tracking records: {orphaned_tracking.count()}")
    else:
        print("OK: No orphaned tracking records")
    
    # Check for packages without proper extraction
    unextracted_packages = ELearningPackage.objects.filter(is_extracted=False)
    if unextracted_packages.exists():
        print(f"WARNING: Unextracted packages: {unextracted_packages.count()}")
        for package in unextracted_packages:
            print(f"    - {package.title}: {package.extraction_error}")
    else:
        print("OK: All packages are extracted")
    
    return {
        'orphaned_tracking': orphaned_tracking.count(),
        'unextracted_packages': unextracted_packages.count()
    }

def main():
    """Main verification function"""
    print("E-Learning Ecosystem Verification")
    print("=" * 60)
    
    try:
        # Run all checks
        results = verify_elearning_ecosystem()
        recent_activity = check_recent_activity()
        auth_issues = check_authentication_issues()
        
        # Summary
        print(f"\nVerification Summary:")
        print("=" * 40)
        print(f"E-Learning Packages: {results['packages']}")
        print(f"Tracking Records: {results['tracking']}")
        print(f"xAPI Statements: {results['statements']}")
        print(f"cmi5 AUs: {results['aus']}")
        print(f"cmi5 Registrations: {results['registrations']}")
        print(f"cmi5 Sessions: {results['sessions']}")
        print(f"Recent Activity (24h): {recent_activity}")
        
        # Issues summary
        total_issues = (
            results['packages_without_tracking'] + 
            results['stale_tracking'] + 
            results['empty_raw_data'] +
            auth_issues['orphaned_tracking'] +
            auth_issues['unextracted_packages']
        )
        
        if total_issues == 0:
            print(f"\nSUCCESS: All systems operational! No issues found.")
        else:
            print(f"\nWARNING: Total issues found: {total_issues}")
            print(f"   - Packages without tracking: {results['packages_without_tracking']}")
            print(f"   - Stale tracking records: {results['stale_tracking']}")
            print(f"   - Empty raw_data: {results['empty_raw_data']}")
            print(f"   - Orphaned tracking: {auth_issues['orphaned_tracking']}")
            print(f"   - Unextracted packages: {auth_issues['unextracted_packages']}")
        
        return results
        
    except Exception as e:
        print(f"ERROR: Error during verification: {str(e)}")
        return None

if __name__ == '__main__':
    results = main()
    if results:
        print(f"\nVerification completed successfully!")
    else:
        print(f"\nVerification failed!")
        sys.exit(1)
