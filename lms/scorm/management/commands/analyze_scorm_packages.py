"""
Management command to analyze existing SCORM packages and apply auto-scoring
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormPackage
from scorm.package_analyzer import ScormPackageAnalyzer
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Analyze existing SCORM packages and apply auto-scoring adjustments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-analysis of all packages, even if already analyzed',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Analyze specific package by ID',
        )

    def handle(self, *args, **options):
        force = options['force']
        package_id = options.get('package_id')
        
        if package_id:
            packages = ScormPackage.objects.filter(id=package_id)
            if not packages.exists():
                self.stdout.write(
                    self.style.ERROR(f'Package with ID {package_id} not found')
                )
                return
        else:
            # Get all packages
            packages = ScormPackage.objects.all()
        
        self.stdout.write(f'Found {packages.count()} SCORM packages to analyze')
        
        analyzed_count = 0
        auto_scoring_applied = 0
        
        for package in packages:
            try:
                # Check if already analyzed (unless force)
                if not force and package.package_metadata and package.package_metadata.get('detected_at'):
                    self.stdout.write(f'Skipping {package.title} (already analyzed)')
                    continue
                
                self.stdout.write(f'Analyzing {package.title}...')
                
                # Get manifest content for analysis
                manifest_content = None
                if hasattr(package, 'manifest_data') and package.manifest_data:
                    manifest_content = package.manifest_data.get('raw_manifest', '')
                
                # Analyze package
                with transaction.atomic():
                    package_metadata = ScormPackageAnalyzer.analyze_package(
                        package.manifest_data or {},
                        manifest_content
                    )
                    
                    # Update package metadata
                    package.package_metadata = package_metadata
                    package.save()
                    
                    analyzed_count += 1
                    
                    if package_metadata.get('needs_auto_scoring', False):
                        auto_scoring_applied += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f' {package.title}: Auto-scoring enabled '
                                f'({package_metadata["scoring_method"]}, '
                                f'{package_metadata["completion_method"]})'
                            )
                        )
                    else:
                        self.stdout.write(
                            f' {package.title}: Standard scoring '
                            f'({package_metadata["scoring_method"]}, '
                            f'{package_metadata["completion_method"]})'
                        )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error analyzing {package.title}: {str(e)}')
                )
                logger.error(f'Error analyzing package {package.id}: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n Analysis complete!\n'
                f'  Packages analyzed: {analyzed_count}\n'
                f'  Auto-scoring applied: {auto_scoring_applied}\n'
                f'  Standard scoring: {analyzed_count - auto_scoring_applied}'
            )
        )
