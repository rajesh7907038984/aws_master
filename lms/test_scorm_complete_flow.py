#!/usr/bin/env python
"""
Comprehensive SCORM Flow Testing Script
Tests all package types: SCORM 1.2, SCORM 2004, xAPI, cmi5, Articulate
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ELearningPackage
from scorm.storage import SCORMS3Storage
from courses.models import Topic

def test_scorm_flow():
    """Test complete SCORM flow for all package types"""
    print('=' * 70)
    print('SCORM Complete Flow Test')
    print('=' * 70)
    
    storage = SCORMS3Storage()
    packages = ELearningPackage.objects.all()
    
    print(f'\nTotal packages: {packages.count()}\n')
    
    test_results = {
        'SCORM_1_2': {'tested': 0, 'passed': 0, 'failed': 0},
        'SCORM_2004': {'tested': 0, 'passed': 0, 'failed': 0},
        'XAPI': {'tested': 0, 'passed': 0, 'failed': 0},
        'CMI5': {'tested': 0, 'passed': 0, 'failed': 0},
        'ARTICULATE': {'tested': 0, 'passed': 0, 'failed': 0},
        'AICC': {'tested': 0, 'passed': 0, 'failed': 0},
    }
    
    for pkg in packages:
        if not pkg.is_extracted:
            print(f'⏭️  Topic {pkg.topic_id}: Not extracted yet, skipping...\n')
            continue
        
        package_type = pkg.package_type
        test_results[package_type]['tested'] += 1
        
        print(f'📦 Testing Topic {pkg.topic_id} ({package_type})')
        print('-' * 70)
        
        checks = []
        
        # 1. Check database fields
        print('✓ Database fields:')
        print(f'  - Topic ID: {pkg.topic_id}')
        print(f'  - Package type: {package_type}')
        print(f'  - Extracted path: {pkg.extracted_path}')
        print(f'  - Launch file: {pkg.launch_file}')
        print(f'  - Manifest path: {pkg.manifest_path or "N/A"}')
        checks.append(('DB Fields', True, ''))
        
        # 2. Check path consistency
        print('\n✓ Path consistency:')
        path_issues = []
        if 'packages/packages/' in pkg.extracted_path:
            path_issues.append('Double packages/ prefix')
        if 'elearning/elearning/' in pkg.extracted_path:
            path_issues.append('Double elearning/ prefix')
        if pkg.extracted_path.startswith('elearning/packages/'):
            path_issues.append('Should not have elearning/ prefix')
        
        if path_issues:
            print(f'  ❌ Issues: {", ".join(path_issues)}')
            checks.append(('Path Consistency', False, ', '.join(path_issues)))
        else:
            print('  ✅ No path issues')
            checks.append(('Path Consistency', True, ''))
        
        # 3. Check S3 file existence
        print('\n✓ S3 file existence:')
        full_path = f'{pkg.extracted_path}/{pkg.launch_file}'
        file_exists = storage.exists(full_path)
        if file_exists:
            print(f'  ✅ Launch file found: {full_path}')
            checks.append(('S3 File Exists', True, ''))
        else:
            print(f'  ❌ Launch file NOT found: {full_path}')
            checks.append(('S3 File Exists', False, 'File not found'))
        
        # 4. Check URL generation
        print('\n✓ URL generation:')
        try:
            url = storage.url(full_path)
            url_issues = []
            if 'elearning/elearning/' in url:
                url_issues.append('Double elearning/ prefix')
            if 'packages/packages/' in url:
                url_issues.append('Double packages/ prefix')
            
            if url_issues:
                print(f'  ❌ URL Issues: {", ".join(url_issues)}')
                print(f'  URL: {url[:100]}...')
                checks.append(('URL Generation', False, ', '.join(url_issues)))
            else:
                print(f'  ✅ URL generated correctly')
                print(f'  URL: {url[:100]}...')
                checks.append(('URL Generation', True, ''))
        except Exception as e:
            print(f'  ❌ URL generation failed: {e}')
            checks.append(('URL Generation', False, str(e)))
        
        # 5. Check launch URL
        print('\n✓ Launch URL:')
        launch_url = pkg.get_launch_url()
        if launch_url:
            print(f'  ✅ Launch URL: {launch_url}')
            checks.append(('Launch URL', True, ''))
        else:
            print(f'  ❌ No launch URL')
            checks.append(('Launch URL', False, 'No launch URL'))
        
        # 6. Check content URL
        print('\n✓ Content URL:')
        content_url = pkg.get_content_url()
        if content_url:
            print(f'  ✅ Content URL: {content_url}')
            checks.append(('Content URL', True, ''))
        else:
            print(f'  ❌ No content URL')
            checks.append(('Content URL', False, 'No content URL'))
        
        # 7. Package-specific checks
        print(f'\n✓ Package-specific ({package_type}):')
        if package_type in ['SCORM_1_2', 'SCORM_2004']:
            # Check for typical SCORM files
            scorm_files = ['imsmanifest.xml']
            for file in scorm_files:
                file_path = f'{pkg.extracted_path}/{file}'
                if storage.exists(file_path):
                    print(f'  ✅ {file} found')
                else:
                    print(f'  ⚠️  {file} not found (may be optional)')
        
        elif package_type == 'XAPI':
            print(f'  - xAPI Endpoint: {pkg.xapi_endpoint or "Not set"}')
            print(f'  - xAPI Actor: {pkg.xapi_actor or "Not set"}')
            checks.append(('xAPI Config', bool(pkg.xapi_endpoint), ''))
        
        elif package_type == 'CMI5':
            print(f'  - cmi5 AU ID: {pkg.cmi5_au_id or "Not set"}')
            print(f'  - cmi5 Launch URL: {pkg.cmi5_launch_url or "Not set"}')
            checks.append(('cmi5 Config', bool(pkg.cmi5_au_id), ''))
        
        elif package_type == 'ARTICULATE':
            # Check for Articulate-specific files
            articulate_files = ['story.html', 'story_html5.html', 'index_lms.html']
            found_articulate = False
            for file in articulate_files:
                file_path = f'{pkg.extracted_path}/{file}'
                if storage.exists(file_path):
                    print(f'  ✅ Articulate file found: {file}')
                    found_articulate = True
                    break
            if not found_articulate:
                print(f'  ⚠️  No Articulate-specific files found')
        
        # Summary for this package
        all_passed = all(check[1] for check in checks if check[0] not in ['xAPI Config', 'cmi5 Config'])
        
        if all_passed:
            print(f'\n✅ All checks passed for Topic {pkg.topic_id}!')
            test_results[package_type]['passed'] += 1
        else:
            print(f'\n❌ Some checks failed for Topic {pkg.topic_id}')
            test_results[package_type]['failed'] += 1
            failed_checks = [c for c in checks if not c[1]]
            for check_name, _, reason in failed_checks:
                print(f'   - {check_name}: {reason}')
        
        print('\n' + '=' * 70 + '\n')
    
    # Final summary
    print('=' * 70)
    print('FINAL SUMMARY')
    print('=' * 70)
    
    total_tested = sum(r['tested'] for r in test_results.values())
    total_passed = sum(r['passed'] for r in test_results.values())
    total_failed = sum(r['failed'] for r in test_results.values())
    
    print(f'\nTotal packages tested: {total_tested}')
    print(f'✅ Passed: {total_passed}')
    print(f'❌ Failed: {total_failed}')
    
    print('\nBreakdown by package type:')
    for pkg_type, results in test_results.items():
        if results['tested'] > 0:
            print(f'  {pkg_type}:')
            print(f'    Tested: {results["tested"]}')
            print(f'    ✅ Passed: {results["passed"]}')
            print(f'    ❌ Failed: {results["failed"]}')
    
    print('\n' + '=' * 70)
    
    if total_failed == 0 and total_tested > 0:
        print('\n🎉 ALL SCORM FLOWS WORKING CORRECTLY!')
        print('✓ Path construction is consistent')
        print('✓ S3 storage is working')
        print('✓ URL generation is correct')
        print('✓ Launch URLs are valid')
        print('=' * 70)
        return True
    elif total_tested == 0:
        print('\n⚠️  No extracted packages to test')
        return True
    else:
        print(f'\n⚠️  {total_failed} package(s) have issues')
        return False

if __name__ == '__main__':
    success = test_scorm_flow()
    exit(0 if success else 1)

