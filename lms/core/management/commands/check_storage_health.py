"""
Management command to check and fix storage health across the entire LMS
"""
from django.core.management.base import BaseCommand
from django.apps import apps
from core.utils.file_validation import (
    check_storage_health, 
    fix_storage_inconsistencies,
    validate_storage_consistency
)
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check and fix storage health across the entire LMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix storage inconsistencies automatically',
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Check specific model (e.g., scorm.ELearningPackage)',
        )
        parser.add_argument(
            '--field',
            type=str,
            help='Check specific field (e.g., package_file)',
        )

    def handle(self, *args, **options):
        fix_mode = options['fix']
        specific_model = options.get('model')
        specific_field = options.get('field')
        
        self.stdout.write("🔍 Checking LMS Storage Health...")
        
        # Check overall storage health
        health = check_storage_health()
        
        self.stdout.write(f"\n📊 Storage Health Summary:")
        self.stdout.write(f"  S3 Configured: {'✅' if health['s3_configured'] else '❌'}")
        self.stdout.write(f"  Local Media Available: {'✅' if health['local_media_available'] else '❌'}")
        self.stdout.write(f"  Storage Accessible: {'✅' if health['storage_accessible'] else '❌'}")
        
        if health['issues']:
            self.stdout.write(f"\n⚠️  Issues Found:")
            for issue in health['issues']:
                self.stdout.write(f"  - {issue}")
        
        # Check specific models with file fields
        models_to_check = [
            ('scorm.ELearningPackage', 'package_file'),
            ('courses.Topic', 'content_file'),
            ('certificates.CertificateTemplate', 'template_file'),
            ('conferences.Conference', 'local_file'),
            ('lms_messages.Message', 'file'),
            ('discussions.Discussion', 'file'),
            ('reports.Report', 'file'),
        ]
        
        if specific_model:
            models_to_check = [(specific_model, specific_field or 'file')]
        
        total_issues = 0
        total_fixed = 0
        
        for model_path, field_name in models_to_check:
            try:
                app_label, model_name = model_path.split('.')
                model_class = apps.get_model(app_label, model_name)
                
                if not model_class:
                    self.stdout.write(f"❌ Model not found: {model_path}")
                    continue
                
                self.stdout.write(f"\n🔍 Checking {model_path}.{field_name}...")
                
                # Check if field exists
                if not hasattr(model_class, field_name):
                    self.stdout.write(f"  ⚠️  Field {field_name} not found in {model_path}")
                    continue
                
                # Get all objects with files
                objects = model_class.objects.exclude(**{f"{field_name}__isnull": True}).exclude(**{f"{field_name}": ""})
                total_objects = objects.count()
                
                if total_objects == 0:
                    self.stdout.write(f"  ℹ️  No objects with {field_name} found")
                    continue
                
                self.stdout.write(f"  📁 Found {total_objects} objects with {field_name}")
                
                issues_found = 0
                for obj in objects:
                    file_field = getattr(obj, field_name)
                    if not file_field:
                        continue
                    
                    validation = validate_storage_consistency(file_field)
                    if not validation['valid']:
                        issues_found += 1
                        total_issues += 1
                        
                        self.stdout.write(f"    ❌ {obj} - {validation['error']}")
                        
                        if fix_mode:
                            # Apply fixes based on model type
                            if hasattr(obj, 'is_extracted'):
                                obj.is_extracted = False
                            if hasattr(obj, 'extraction_error'):
                                obj.extraction_error = validation['error']
                            if hasattr(obj, 'extracted_path'):
                                obj.extracted_path = ""
                            if hasattr(obj, 'manifest_path'):
                                obj.manifest_path = ""
                            if hasattr(obj, 'launch_file'):
                                obj.launch_file = ""
                            
                            obj.save()
                            total_fixed += 1
                            self.stdout.write(f"    ✅ Fixed {obj}")
                
                if issues_found == 0:
                    self.stdout.write(f"  ✅ All {field_name} files are valid")
                else:
                    self.stdout.write(f"  ⚠️  Found {issues_found} issues with {field_name}")
                
            except Exception as e:
                self.stdout.write(f"❌ Error checking {model_path}: {str(e)}")
        
        # Summary
        self.stdout.write(f"\n📈 Summary:")
        self.stdout.write(f"  Total Issues Found: {total_issues}")
        if fix_mode:
            self.stdout.write(f"  Total Issues Fixed: {total_fixed}")
            if total_fixed > 0:
                self.stdout.write("  ✅ Storage inconsistencies have been fixed")
        else:
            self.stdout.write("  💡 Use --fix to automatically fix issues")
        
        if total_issues == 0:
            self.stdout.write("  🎉 All storage is healthy!")
        else:
            self.stdout.write("  ⚠️  Some storage issues were found")
