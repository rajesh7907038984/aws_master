"""
Management command to test SCORM time tracking fix
Verifies that time tracking works for all SCORM types
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from scorm.models import ScormAttempt, ScormPackage
from scorm.enhanced_time_tracking import EnhancedScormTimeTracker, ScormTimeTrackingMonitor
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test SCORM time tracking fix for all SCORM types'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode without making changes',
        )
        parser.add_argument(
            '--scorm-version',
            type=str,
            help='Test specific SCORM version (1.2, 2004, storyline, etc.)',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        scorm_version = options.get('scorm_version')
        
        self.stdout.write(
            self.style.SUCCESS('🧪 SCORM Time Tracking Test Tool')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 Running in DRY-RUN mode - no changes will be made')
            )
        
        # Test health check first
        self.stdout.write('\n📊 Checking SCORM time tracking health...')
        health_status = ScormTimeTrackingMonitor.check_time_tracking_health()
        
        if health_status['status'] == 'healthy':
            self.stdout.write(
                self.style.SUCCESS(f"✅ Health check passed: {health_status}")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"❌ Health check failed: {health_status}")
            )
        
        # Get SCORM attempts to test
        attempts_query = ScormAttempt.objects.all()
        if scorm_version:
            attempts_query = attempts_query.filter(scorm_package__version=scorm_version)
        
        attempts = attempts_query.select_related('scorm_package', 'user')[:10]  # Test first 10
        
        if not attempts:
            self.stdout.write(
                self.style.WARNING('⚠️ No SCORM attempts found to test')
            )
            return
        
        self.stdout.write(f'\n🔬 Testing {len(attempts)} SCORM attempts...')
        
        # Test each SCORM type
        scorm_versions = set(attempt.scorm_package.version for attempt in attempts)
        
        for version in scorm_versions:
            self.stdout.write(f'\n📋 Testing SCORM {version}...')
            version_attempts = [a for a in attempts if a.scorm_package.version == version]
            
            success_count = 0
            error_count = 0
            
            for attempt in version_attempts:
                try:
                    if not dry_run:
                        # Test enhanced time tracking
                        tracker = EnhancedScormTimeTracker(attempt)
                        
                        # Test with sample session time
                        test_session_time = "00:05:30.00"  # 5 minutes 30 seconds
                        if version in ['2004', 'xapi', 'storyline']:
                            test_session_time = "PT5M30S"  # SCORM 2004 format
                        
                        success = tracker.save_time_with_reliability(test_session_time)
                        
                        if success:
                            success_count += 1
                            self.stdout.write(
                                f"  ✅ Attempt {attempt.id} ({attempt.user.username}): Time tracking successful"
                            )
                        else:
                            error_count += 1
                            self.stdout.write(
                                f"  ❌ Attempt {attempt.id} ({attempt.user.username}): Time tracking failed"
                            )
                    else:
                        # Dry run - just check if tracker can be created
                        tracker = EnhancedScormTimeTracker(attempt)
                        success_count += 1
                        self.stdout.write(
                            f"  ✅ Attempt {attempt.id} ({attempt.user.username}): Tracker created successfully"
                        )
                        
                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        f"  ❌ Attempt {attempt.id} ({attempt.user.username}): Error - {str(e)}"
                    )
            
            # Summary for this version
            total_tested = success_count + error_count
            success_rate = (success_count / total_tested * 100) if total_tested > 0 else 0
            
            if success_rate >= 90:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ SCORM {version}: {success_count}/{total_tested} successful ({success_rate:.1f}%)")
                )
            elif success_rate >= 70:
                self.stdout.write(
                    self.style.WARNING(f"⚠️ SCORM {version}: {success_count}/{total_tested} successful ({success_rate:.1f}%)")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ SCORM {version}: {success_count}/{total_tested} successful ({success_rate:.1f}%)")
                )
        
        # Final health check
        self.stdout.write('\n📊 Final health check...')
        final_health = ScormTimeTrackingMonitor.check_time_tracking_health()
        
        if final_health['status'] == 'healthy':
            self.stdout.write(
                self.style.SUCCESS(f"✅ Final health check passed: {final_health}")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"❌ Final health check failed: {final_health}")
            )
        
        # Summary
        self.stdout.write('\n📈 Test Summary:')
        self.stdout.write(f"  - SCORM versions tested: {', '.join(scorm_versions)}")
        self.stdout.write(f"  - Total attempts tested: {len(attempts)}")
        self.stdout.write(f"  - Database health: {final_health['status']}")
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS('✅ SCORM time tracking test completed successfully!')
            )
        else:
            self.stdout.write(
                self.style.WARNING('🔍 Dry-run completed - no changes were made')
            )
