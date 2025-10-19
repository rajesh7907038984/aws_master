#!/usr/bin/env python
"""Fix all SCORM packages with double packages/ prefix"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ELearningPackage

# Find all packages with double prefix
packages = ELearningPackage.objects.filter(extracted_path__contains='packages/packages')

print(f'Found {packages.count()} packages with double prefix:')
for pkg in packages:
    print(f'  Topic {pkg.topic_id}: {pkg.extracted_path}')

# Fix all packages
fixed_count = 0
for pkg in packages:
    old_path = pkg.extracted_path
    # Remove the duplicate "packages/" prefix
    new_path = old_path.replace('packages/packages/', 'packages/')
    pkg.extracted_path = new_path
    pkg.save()
    print(f'  Fixed Topic {pkg.topic_id}: {old_path} -> {new_path}')
    fixed_count += 1

print(f'\nFixed {fixed_count} packages successfully!')

