"""
Management command to diagnose and fix SCORM score issues comprehensively
"""
import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormPackage, ScormAttempt
from scorm.score_sync_service import ScormScoreSyncService
from courses.models import TopicProgress

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Diagnose and fix SCORM scoring issues including mastery scores and attempt scores'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Actually fix the issues (otherwise just report them)'
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Specific SCORM package ID to check'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Specific user ID to check'
        )

    def handle(self, *args, **options):
        fix_mode = options.get('fix', False)
        package_id = options.get('package_id')
        user_id = options.get('user_id')
        
        self.stdout.write(self.style.WARNING(
            f"{'FIXING' if fix_mode else 'DIAGNOSING'} SCORM scoring issues..."
        ))
        
        # 1. Check mastery scores
        self.check_mastery_scores(fix_mode, package_id)
        
        # 2. Check attempt scores
        self.check_attempt_scores(fix_mode, package_id, user_id)
        
        # 3. Check score synchronization
        self.check_score_sync(fix_mode, package_id, user_id)
        
        # 4. Check for missing scores on first attempts
        self.check_first_attempt_scores(fix_mode, package_id, user_id)
    
    def check_mastery_scores(self, fix_mode, package_id=None):
        """Check and fix mastery scores that might be stored incorrectly"""
        self.stdout.write("\n" + self.style.SUCCESS("=== Checking Mastery Scores ==="))
        
        packages = ScormPackage.objects.all()
        if package_id:
            packages = packages.filter(id=package_id)
        
        issues_found = 0
        for package in packages:
            # Check if mastery score looks suspiciously low (might be raw count instead of percentage)
            if package.mastery_score and package.mastery_score < 20:
                self.stdout.write(
                    f"\n⚠️  Package '{package.title}' (ID: {package.id}) has suspiciously low mastery score: {package.mastery_score}"
                )
                
                # Check manifest data for clues
                manifest_mastery = package.manifest_data.get('mastery_score') if package.manifest_data else None
                self.stdout.write(f"   Manifest mastery score: {manifest_mastery}")
                
                # Check if this might be a question count instead of percentage
                if package.description or package.title:
                    import re
                    # Look for question count in title/description
                    question_match = re.search(r'(\d+)\s*questions?', 
                                             f"{package.title} {package.description}", re.IGNORECASE)
                    if question_match:
                        total_questions = int(question_match.group(1))
                        self.stdout.write(f"   Found {total_questions} questions mentioned")
                        
                        # Calculate possible percentage
                        if package.mastery_score < total_questions:
                            possible_percentage = (package.mastery_score / total_questions) * 100
                            self.stdout.write(
                                f"   🤔 Mastery score {package.mastery_score} might be question count "
                                f"for {possible_percentage:.0f}% passing rate"
                            )
                            
                            if fix_mode and possible_percentage in [70, 75, 80, 85, 90]:
                                # Common passing percentages
                                old_score = package.mastery_score
                                package.mastery_score = Decimal(str(possible_percentage))
                                package.save()
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"   ✅ Fixed: {old_score} -> {possible_percentage}%"
                                    )
                                )
                                issues_found += 1
        
        self.stdout.write(f"\nMastery score issues found: {issues_found}")
    
    def check_attempt_scores(self, fix_mode, package_id=None, user_id=None):
        """Check for attempt score issues"""
        self.stdout.write("\n" + self.style.SUCCESS("=== Checking Attempt Scores ==="))
        
        attempts = ScormAttempt.objects.select_related('scorm_package', 'user').all()
        if package_id:
            attempts = attempts.filter(scorm_package_id=package_id)
        if user_id:
            attempts = attempts.filter(user_id=user_id)
        
        issues_found = 0
        for attempt in attempts:
            issues = []
            
            # Check for score in CMI data but not in score_raw
            cmi_score_12 = attempt.cmi_data.get('cmi.core.score.raw') if attempt.cmi_data else None
            cmi_score_2004 = attempt.cmi_data.get('cmi.score.raw') if attempt.cmi_data else None
            cmi_score = cmi_score_12 or cmi_score_2004
            
            if cmi_score and cmi_score != '':
                try:
                    cmi_score_val = float(cmi_score)
                    if attempt.score_raw is None:
                        issues.append(f"CMI has score {cmi_score_val} but score_raw is None")
                        if fix_mode:
                            attempt.score_raw = Decimal(str(cmi_score_val))
                            attempt.save()
                            self.stdout.write(
                                self.style.SUCCESS(f"   ✅ Set score_raw = {cmi_score_val}")
                            )
                    elif abs(float(attempt.score_raw) - cmi_score_val) > 0.01:
                        issues.append(
                            f"Score mismatch: score_raw={attempt.score_raw}, "
                            f"cmi={cmi_score_val}"
                        )
                        if fix_mode:
                            attempt.score_raw = Decimal(str(cmi_score_val))
                            attempt.save()
                            self.stdout.write(
                                self.style.SUCCESS(f"   ✅ Fixed score_raw = {cmi_score_val}")
                            )
                except:
                    pass
            
            # Check for completed status with no score
            if attempt.lesson_status in ['completed', 'passed'] and attempt.score_raw is None:
                issues.append(f"Status is '{attempt.lesson_status}' but no score")
            
            if issues:
                issues_found += len(issues)
                self.stdout.write(
                    f"\n⚠️  Attempt {attempt.id} (User: {attempt.user.username}, "
                    f"Package: {attempt.scorm_package.title}):"
                )
                for issue in issues:
                    self.stdout.write(f"   - {issue}")
        
        self.stdout.write(f"\nAttempt score issues found: {issues_found}")
    
    def check_score_sync(self, fix_mode, package_id=None, user_id=None):
        """Check if scores are properly synced to TopicProgress"""
        self.stdout.write("\n" + self.style.SUCCESS("=== Checking Score Synchronization ==="))
        
        attempts = ScormAttempt.objects.select_related('scorm_package__topic', 'user').all()
        if package_id:
            attempts = attempts.filter(scorm_package_id=package_id)
        if user_id:
            attempts = attempts.filter(user_id=user_id)
        
        sync_issues = 0
        for attempt in attempts:
            if not hasattr(attempt.scorm_package, 'topic'):
                continue
                
            topic = attempt.scorm_package.topic
            topic_progress = TopicProgress.objects.filter(
                user=attempt.user,
                topic=topic
            ).first()
            
            if attempt.score_raw is not None:
                attempt_score = float(attempt.score_raw)
                
                if not topic_progress:
                    self.stdout.write(
                        f"\n⚠️  No TopicProgress for attempt {attempt.id} "
                        f"(User: {attempt.user.username}, Topic: {topic.title})"
                    )
                    if fix_mode:
                        ScormScoreSyncService.sync_score(attempt)
                        self.stdout.write(self.style.SUCCESS("   ✅ Created TopicProgress"))
                    sync_issues += 1
                elif topic_progress.last_score != attempt_score:
                    self.stdout.write(
                        f"\n⚠️  Score mismatch for attempt {attempt.id}: "
                        f"ScormAttempt={attempt_score}, TopicProgress={topic_progress.last_score}"
                    )
                    if fix_mode:
                        ScormScoreSyncService.sync_score(attempt, force=True)
                        self.stdout.write(self.style.SUCCESS("   ✅ Synced score"))
                    sync_issues += 1
        
        self.stdout.write(f"\nScore sync issues found: {sync_issues}")
    
    def check_first_attempt_scores(self, fix_mode, package_id=None, user_id=None):
        """Check for the specific issue of first attempts not saving scores properly"""
        self.stdout.write("\n" + self.style.SUCCESS("=== Checking First Attempt Score Issues ==="))
        
        # Group attempts by user and package
        from django.db.models import Min, Count
        attempt_groups = ScormAttempt.objects.values('user', 'scorm_package').annotate(
            first_attempt_id=Min('id'),
            total_attempts=Count('id')
        ).filter(total_attempts__gt=1)
        
        if package_id:
            attempt_groups = attempt_groups.filter(scorm_package_id=package_id)
        if user_id:
            attempt_groups = attempt_groups.filter(user_id=user_id)
        
        issues_found = 0
        for group in attempt_groups:
            first_attempt = ScormAttempt.objects.get(id=group['first_attempt_id'])
            second_attempt = ScormAttempt.objects.filter(
                user_id=group['user'],
                scorm_package_id=group['scorm_package'],
                attempt_number=2
            ).first()
            
            if second_attempt:
                # Check if first attempt has no score but second does
                if (first_attempt.score_raw is None and 
                    second_attempt.score_raw is not None):
                    self.stdout.write(
                        f"\n⚠️  First attempt missing score pattern detected:"
                    )
                    self.stdout.write(
                        f"   User: {first_attempt.user.username}"
                    )
                    self.stdout.write(
                        f"   Package: {first_attempt.scorm_package.title}"
                    )
                    self.stdout.write(
                        f"   First attempt score: None"
                    )
                    self.stdout.write(
                        f"   Second attempt score: {second_attempt.score_raw}"
                    )
                    
                    # Check CMI data for possible score
                    cmi_score = (first_attempt.cmi_data.get('cmi.core.score.raw') or 
                               first_attempt.cmi_data.get('cmi.score.raw') 
                               if first_attempt.cmi_data else None)
                    
                    if cmi_score:
                        self.stdout.write(f"   CMI data has score: {cmi_score}")
                        if fix_mode:
                            try:
                                first_attempt.score_raw = Decimal(str(float(cmi_score)))
                                first_attempt.save()
                                ScormScoreSyncService.sync_score(first_attempt, force=True)
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"   ✅ Fixed first attempt score: {cmi_score}"
                                    )
                                )
                            except:
                                pass
                    
                    issues_found += 1
        
        self.stdout.write(f"\nFirst attempt score issues found: {issues_found}")
        
        if not fix_mode and issues_found > 0:
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠️  Run with --fix flag to automatically fix these issues"
                )
            )
