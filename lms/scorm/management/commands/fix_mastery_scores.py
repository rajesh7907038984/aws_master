"""
Management command to fix mastery scores for SCORM packages
Extracts mastery scores from manifest data and sets them properly
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from scorm.models import ScormPackage


class Command(BaseCommand):
    help = 'Fix mastery scores for SCORM packages from manifest data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix mastery score for specific package ID'
        )
        parser.add_argument(
            '--default-score',
            type=float,
            default=70.0,
            help='Default mastery score to use if not found in manifest (default: 70.0)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )

    def handle(self, *args, **options):
        package_id = options.get('package_id')
        default_score = options.get('default_score', 70.0)
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get packages to process
        if package_id:
            packages = ScormPackage.objects.filter(id=package_id)
            if not packages.exists():
                self.stdout.write(self.style.ERROR(f'Package {package_id} not found'))
                return
        else:
            packages = ScormPackage.objects.all()
        
        self.stdout.write(f'Processing {packages.count()} SCORM packages...')
        
        fixed_count = 0
        defaulted_count = 0
        skipped_count = 0
        
        for pkg in packages:
            self.stdout.write(f'\nPackage {pkg.id}: {pkg.title}')
            self.stdout.write(f'  Current mastery score: {pkg.mastery_score}%')
            
            # Check if mastery score needs fixing
            needs_fix = pkg.mastery_score is None or pkg.mastery_score == 0
            
            if not needs_fix:
                self.stdout.write(f'  ✅ Already has mastery score: {pkg.mastery_score}%')
                skipped_count += 1
                continue
            
            # Try to extract from manifest data
            manifest_mastery = None
            if pkg.manifest_data and 'mastery_score' in pkg.manifest_data:
                manifest_mastery = pkg.manifest_data['mastery_score']
                self.stdout.write(f'  📋 Manifest mastery score: {manifest_mastery}')
            
            # Determine new mastery score
            new_mastery = None
            if manifest_mastery is not None:
                try:
                    mastery_value = float(manifest_mastery)
                    if 0 <= mastery_value <= 100:
                        new_mastery = Decimal(str(mastery_value))
                        self.stdout.write(f'  ✅ Using manifest mastery score: {mastery_value}%')
                    else:
                        self.stdout.write(f'  ⚠️  Invalid mastery score in manifest: {mastery_value}')
                except (ValueError, TypeError):
                    self.stdout.write(f'  ⚠️  Could not parse mastery score from manifest: {manifest_mastery}')
            
            # Use default if no valid manifest score
            if new_mastery is None:
                new_mastery = Decimal(str(default_score))
                self.stdout.write(f'  🔧 Using default mastery score: {default_score}%')
                defaulted_count += 1
            else:
                fixed_count += 1
            
            # Update the package
            if not dry_run:
                with transaction.atomic():
                    pkg.mastery_score = new_mastery
                    pkg.save()
                    self.stdout.write(f'  💾 Updated mastery score to {new_mastery}%')
            else:
                self.stdout.write(f'  🔍 Would update mastery score to {new_mastery}%')
        
        # Summary
        self.stdout.write(f'\n{"="*50}')
        self.stdout.write(f'SUMMARY:')
        self.stdout.write(f'  Total packages processed: {packages.count()}')
        self.stdout.write(f'  Fixed from manifest: {fixed_count}')
        self.stdout.write(f'  Set to default: {defaulted_count}')
        self.stdout.write(f'  Skipped (already set): {skipped_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN COMPLETED - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('\nMastery scores fixed successfully!'))
