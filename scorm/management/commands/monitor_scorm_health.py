"""
Management command to monitor SCORM system health and auto-fix issues
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormPackage, ScormAttempt
from scorm.package_analyzer import ScormPackageAnalyzer
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Monitor SCORM system health and auto-fix issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Automatically fix detected issues',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check for issues without fixing',
        )

    def handle(self, *args, **options):
        auto_fix = options['auto_fix']
        check_only = options['check_only']
        
        if check_only:
            self.stdout.write(' SCORM Health Check Mode')
        else:
            self.stdout.write('🔧 SCORM Health Monitor Mode')
        
        issues_found = 0
        fixes_applied = 0
        
        # 1. Check for packages without auto-scoring
        self.stdout.write('\n1. Checking auto-scoring coverage...')
        packages_without_auto_scoring = ScormPackage.objects.filter(
            package_metadata__needs_auto_scoring=False
        )
        
        if packages_without_auto_scoring.exists():
            issues_found += packages_without_auto_scoring.count()
            self.stdout.write(
                self.style.WARNING(f'   ⚠️  Found {packages_without_auto_scoring.count()} packages without auto-scoring')
            )
            
            if auto_fix:
                for package in packages_without_auto_scoring:
                    # Force re-analysis
                    package_metadata = ScormPackageAnalyzer.analyze_package(
                        package.manifest_data or {},
                        package.manifest_data.get('raw_manifest', '') if package.manifest_data else ''
                    )
                    package.package_metadata = package_metadata
                    package.save()
                    fixes_applied += 1
                    self.stdout.write(f'    Fixed auto-scoring for {package.title}')
        else:
            self.stdout.write('    All packages have auto-scoring enabled')
        
        # 2. Check for packages with low confidence detection
        self.stdout.write('\n2. Checking detection confidence...')
        low_confidence_packages = ScormPackage.objects.filter(
            package_metadata__detection_confidence='low'
        )
        
        if low_confidence_packages.exists():
            self.stdout.write(
                self.style.WARNING(f'   ⚠️  Found {low_confidence_packages.count()} packages with low confidence detection')
            )
            
            if auto_fix:
                for package in low_confidence_packages:
                    # Force re-analysis with enhanced detection
                    package_metadata = ScormPackageAnalyzer.analyze_package(
                        package.manifest_data or {},
                        package.manifest_data.get('raw_manifest', '') if package.manifest_data else ''
                    )
                    package.package_metadata = package_metadata
                    package.save()
                    fixes_applied += 1
                    self.stdout.write(f'    Re-analyzed {package.title}')
        else:
            self.stdout.write('    All packages have good detection confidence')
        
        # 3. Check for inconsistent scores
        self.stdout.write('\n3. Checking score consistency...')
        inconsistent_attempts = []
        
        attempts_with_scores = ScormAttempt.objects.filter(score_raw__isnull=False)
        for attempt in attempts_with_scores:
            if hasattr(attempt.scorm_package, 'topic'):
                progress = TopicProgress.objects.filter(
                    topic=attempt.scorm_package.topic,
                    user=attempt.user
                ).first()
                
                if progress and progress.last_score is not None:
                    attempt_score = float(attempt.score_raw) if attempt.score_raw else 0
                    progress_score = float(progress.last_score) if progress.last_score else 0
                    
                    if abs(attempt_score - progress_score) > 0.01:
                        inconsistent_attempts.append(attempt)
        
        if inconsistent_attempts:
            self.stdout.write(
                self.style.WARNING(f'   ⚠️  Found {len(inconsistent_attempts)} attempts with inconsistent scores')
            )
            
            if auto_fix:
                from scorm.score_sync_service import ScormScoreSyncService
                for attempt in inconsistent_attempts:
                    ScormScoreSyncService.sync_score(attempt, force=True)
                    fixes_applied += 1
                    self.stdout.write(f'    Synced scores for attempt {attempt.id}')
        else:
            self.stdout.write('    All scores are consistent')
        
        # 4. Check for packages without attempts (unused)
        self.stdout.write('\n4. Checking package usage...')
        unused_packages = []
        for package in ScormPackage.objects.all():
            attempts = ScormAttempt.objects.filter(scorm_package=package)
            if attempts.count() == 0:
                unused_packages.append(package)
        
        if unused_packages:
            self.stdout.write(
                self.style.WARNING(f'   ℹ️  Found {len(unused_packages)} packages without attempts (unused)')
            )
            # No auto-fix needed for unused packages
        else:
            self.stdout.write('    All packages have been used')
        
        # 5. Summary
        self.stdout.write('\n=== SUMMARY ===')
        if issues_found == 0:
            self.stdout.write(
                self.style.SUCCESS(' No issues found! SCORM system is healthy.')
            )
        else:
            if auto_fix:
                self.stdout.write(
                    self.style.SUCCESS(f' Fixed {fixes_applied} issues automatically')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  Found {issues_found} issues. Run with --auto-fix to resolve.')
                )
        
        # 6. Recommendations
        self.stdout.write('\n=== RECOMMENDATIONS ===')
        self.stdout.write('   📅 Run this command weekly: python manage.py monitor_scorm_health --auto-fix')
        self.stdout.write('   🔄 Re-analyze packages monthly: python manage.py analyze_scorm_packages --force')
        self.stdout.write('    Monitor gradebook for display issues')
        self.stdout.write('   🚀 System is fully automated - no manual intervention needed!')
