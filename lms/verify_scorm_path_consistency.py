#!/usr/bin/env python
"""
Comprehensive SCORM Path Consistency Verification Script
Verifies that all SCORM path construction is consistent across the project
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ELearningPackage
from scorm.storage import SCORMS3Storage

def verify_scorm_paths():
    """Verify all SCORM packages have consistent paths"""
    print('=' * 60)
    print('SCORM Path Consistency Verification')
    print('=' * 60)
    
    storage = SCORMS3Storage()
    packages = ELearningPackage.objects.all()
    
    print(f'\nTotal SCORM packages: {packages.count()}\n')
    
    all_issues = []
    all_good = []
    
    for pkg in packages:
        topic_id = pkg.topic_id
        extracted_path = pkg.extracted_path
        launch_file = pkg.launch_file
        
        if not extracted_path:
            print(f'⚠️  Topic {topic_id}: No extracted path (not extracted yet)')
            continue
        
        if not launch_file:
            print(f'⚠️  Topic {topic_id}: No launch file')
            continue
        
        # Path consistency checks
        issues = []
        
        # Check for double prefixes
        if 'packages/packages/' in extracted_path:
            issues.append('Double packages/ prefix')
        if 'elearning/elearning/' in extracted_path:
            issues.append('Double elearning/ prefix')
        if extracted_path.startswith('elearning/packages/'):
            issues.append('Should not have elearning/ prefix in DB')
        
        # Check if file exists in S3
        full_path = f'{extracted_path}/{launch_file}'
        file_exists = storage.exists(full_path)
        
        if not file_exists:
            issues.append(f'File not found in S3: {full_path}')
        
        # Check URL generation
        try:
            url = storage.url(full_path)
            if 'elearning/elearning/' in url:
                issues.append('Generated URL has double elearning/ prefix')
        except Exception as e:
            issues.append(f'URL generation failed: {e}')
        
        # Report results
        if issues:
            all_issues.append((topic_id, issues))
            print(f'❌ Topic {topic_id}:')
            print(f'   Path: {extracted_path}')
            print(f'   Launch: {launch_file}')
            for issue in issues:
                print(f'   ⚠️  {issue}')
        else:
            all_good.append(topic_id)
            print(f'✅ Topic {topic_id}:')
            print(f'   Path: {extracted_path}')
            print(f'   Launch: {launch_file}')
            print(f'   S3: {full_path}')
            print(f'   Status: All checks passed!')
        print()
    
    # Summary
    print('=' * 60)
    print('Summary')
    print('=' * 60)
    print(f'✅ Packages with consistent paths: {len(all_good)}')
    print(f'❌ Packages with issues: {len(all_issues)}')
    
    if all_issues:
        print('\n⚠️  Issues found in:')
        for topic_id, issues in all_issues:
            print(f'   Topic {topic_id}: {", ".join(issues)}')
    else:
        print('\n🎉 All SCORM packages have consistent paths!')
    
    print('=' * 60)
    
    return len(all_issues) == 0

if __name__ == '__main__':
    success = verify_scorm_paths()
    exit(0 if success else 1)

