"""
Management command to validate SCORM attempts for CMI compliance
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from scorm.models import ScormAttempt
from scorm.cmi_validator import CMIValidator
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Validate SCORM attempts for CMI compliance and fix custom value issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix non-compliant attempts by removing custom values',
        )
        parser.add_argument(
            '--attempt-id',
            type=int,
            help='Validate specific attempt ID',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Validate all attempts for specific package ID',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting SCORM CMI compliance validation...')
        )

        # Get attempts to validate
        if options['attempt_id']:
            attempts = ScormAttempt.objects.filter(id=options['attempt_id'])
        elif options['package_id']:
            attempts = ScormAttempt.objects.filter(scorm_package_id=options['package_id'])
        else:
            attempts = ScormAttempt.objects.all()

        total_attempts = attempts.count()
        self.stdout.write(f'Found {total_attempts} attempts to validate')

        if total_attempts == 0:
            self.stdout.write(self.style.WARNING('No attempts found to validate'))
            return

        # Validation counters
        stats = {
            'total': 0,
            'compliant': 0,
            'non_compliant': 0,
            'fixed': 0,
            'errors': 0
        }

        for attempt in attempts:
            stats['total'] += 1
            
            try:
                # Validate CMI data
                validation_result = CMIValidator.validate_cmi_data(
                    attempt.cmi_data, 
                    attempt.scorm_package.version
                )
                
                # Check score integrity
                score_integrity = CMIValidator.validate_score_integrity(attempt)
                
                # Extract score from CMI data only
                cmi_score = CMIValidator.extract_score_from_cmi(
                    attempt.cmi_data, 
                    attempt.scorm_package.version
                )
                
                is_compliant = validation_result['is_valid'] and score_integrity
                
                if is_compliant:
                    stats['compliant'] += 1
                    self.stdout.write(
                        f'✅ Attempt {attempt.id}: Compliant (CMI score: {cmi_score})'
                    )
                else:
                    stats['non_compliant'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠️  Attempt {attempt.id}: Non-compliant'
                        )
                    )
                    
                    if not validation_result['is_valid']:
                        self.stdout.write(
                            f'   Invalid fields: {validation_result["invalid_fields"]}'
                        )
                    
                    if not score_integrity:
                        self.stdout.write(
                            f'   Score integrity violation detected'
                        )
                    
                    # Fix if requested
                    if options['fix']:
                        if self._fix_attempt(attempt, cmi_score):
                            stats['fixed'] += 1
                            self.stdout.write(
                                self.style.SUCCESS(f'   Fixed attempt {attempt.id}')
                            )
                        else:
                            stats['errors'] += 1
                            self.stdout.write(
                                self.style.ERROR(f'   Failed to fix attempt {attempt.id}')
                            )
                
                # Log detailed compliance report
                CMIValidator.log_cmi_compliance_report(attempt)
                
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(
                    self.style.ERROR(f'❌ Error validating attempt {attempt.id}: {str(e)}')
                )
                logger.error(f'Error validating attempt {attempt.id}: {str(e)}')

        # Print summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('VALIDATION SUMMARY')
        self.stdout.write('='*50)
        self.stdout.write(f'Total attempts: {stats["total"]}')
        self.stdout.write(f'Compliant: {stats["compliant"]}')
        self.stdout.write(f'Non-compliant: {stats["non_compliant"]}')
        
        if options['fix']:
            self.stdout.write(f'Fixed: {stats["fixed"]}')
            self.stdout.write(f'Errors: {stats["errors"]}')
        
        compliance_rate = (stats['compliant'] / stats['total'] * 100) if stats['total'] > 0 else 0
        self.stdout.write(f'Compliance rate: {compliance_rate:.1f}%')
        
        if compliance_rate < 100:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  {stats["non_compliant"]} attempts are non-compliant with SCORM standards'
                )
            )
            if not options['fix']:
                self.stdout.write(
                    'Run with --fix to automatically fix non-compliant attempts'
                )
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✅ All attempts are SCORM compliant!')
            )

    def _fix_attempt(self, attempt, cmi_score):
        """
        Fix non-compliant attempt by removing custom values and using only CMI data
        """
        try:
            with transaction.atomic():
                # Remove custom score if it doesn't match CMI data
                if attempt.score_raw is not None and cmi_score is not None:
                    if abs(float(attempt.score_raw) - cmi_score) > 0.01:
                        logger.info(f'Fixing attempt {attempt.id}: score_raw {attempt.score_raw} -> {cmi_score}')
                        attempt.score_raw = cmi_score
                
                # Set score to None if no valid CMI score exists
                elif attempt.score_raw is not None and cmi_score is None:
                    logger.info(f'Fixing attempt {attempt.id}: removing invalid score_raw {attempt.score_raw}')
                    attempt.score_raw = None
                
                # Use CMI completion status only
                completion_status = CMIValidator.extract_completion_status_from_cmi(
                    attempt.cmi_data, 
                    attempt.scorm_package.version
                )
                
                # Update status fields based on CMI data only
                if completion_status.get('lesson_status'):
                    attempt.lesson_status = completion_status['lesson_status']
                
                if completion_status.get('completion_status'):
                    attempt.completion_status = completion_status['completion_status']
                
                if completion_status.get('success_status'):
                    attempt.success_status = completion_status['success_status']
                
                # Save the fixed attempt
                attempt.save()
                
                return True
                
        except Exception as e:
            logger.error(f'Error fixing attempt {attempt.id}: {str(e)}')
            return False