#!/usr/bin/env python
"""Fix SCORM package 305 extracted path"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ELearningPackage

# Fix the extracted path for topic 305
pkg = ELearningPackage.objects.get(topic_id=305)
print(f'Before: {pkg.extracted_path}')
pkg.extracted_path = 'packages/305'
pkg.save()
print(f'After: {pkg.extracted_path}')
print('Fixed successfully!')

