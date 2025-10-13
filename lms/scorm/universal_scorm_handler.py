"""
Universal SCORM Handler
Handles all types of SCORM packages with proper score capture and result display
Supports: Rise 360, Storyline, Custom Interactive, xAPI, AICC, SCORM 2004
"""
import logging
import json
import re
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class UniversalScormHandler:
    """
    Universal handler for all SCORM package types
    Automatically detects package type and applies appropriate scoring logic
    """
    
    # Package type detection patterns
    PACKAGE_TYPES = {
        'rise360': {
            'launch_patterns': ['scormcontent/index.html'],
            'manifest_patterns': ['articulate', 'rise'],
            'scoring_method': 'slide_completion',
            'result_extraction': 'progress_percentage'
        },
        'storyline': {
            'launch_patterns': ['story.html', 'index_lms.html'],
            'manifest_patterns': ['storyline', 'articulate storyline'],
            'scoring_method': 'interaction_based',
            'result_extraction': 'suspend_data_analysis'
        },
        'custom_interactive': {
            'launch_patterns': ['index_lms.html'],
            'manifest_patterns': [],
            'scoring_method': 'quiz_assessment',
            'result_extraction': 'cmi_score_direct'
        },
        'xapi': {
            'launch_patterns': ['analytics-frame.html'],
            'manifest_patterns': ['xapi', 'tincan'],
            'scoring_method': 'experience_statements',
            'result_extraction': 'xapi_statements'
        },
        'aicc_legacy': {
            'launch_patterns': ['analytics-frame.html'],
            'manifest_patterns': ['aicc'],
            'scoring_method': 'legacy_tracking',
            'result_extraction': 'aicc_data'
        },
        'scorm2004': {
            'launch_patterns': ['index_lms.html'],
            'manifest_patterns': ['scorm 2004', 'version="2004"'],
            'scoring_method': 'objective_based',
            'result_extraction': 'sequencing_rules'
        }
    }
    
    def __init__(self, scorm_package, attempt):
        self.package = scorm_package
        self.attempt = attempt
        self.detected_type = self._detect_package_type()
        self.scoring_config = self.PACKAGE_TYPES.get(self.detected_type, {})
        
        logger.info(f"🔍 Universal Handler: Detected package type '{self.detected_type}' for package {self.package.id}")
    
    def _detect_package_type(self):
        """
        Automatically detect the SCORM package type based on various indicators
        """
        # Check launch URL patterns
        launch_url = self.package.launch_url.lower() if self.package.launch_url else ''
        
        # Check manifest patterns
        manifest_content = ''
        if self.package.manifest_data and 'raw_manifest' in self.package.manifest_data:
            manifest_content = self.package.manifest_data['raw_manifest'].lower()
        
        # Check filename patterns
        filename = ''
        if self.package.package_file:
            filename = self.package.package_file.name.lower()
        
        # Detection logic with priority order
        for package_type, config in self.PACKAGE_TYPES.items():
            # Check launch URL patterns
            for pattern in config['launch_patterns']:
                if pattern in launch_url:
                    # Verify with manifest patterns if available
                    if config['manifest_patterns']:
                        for manifest_pattern in config['manifest_patterns']:
                            if manifest_pattern in manifest_content or manifest_pattern in filename:
                                return package_type
                    else:
                        return package_type
            
            # Check manifest patterns directly
            for pattern in config['manifest_patterns']:
                if pattern in manifest_content or pattern in filename:
                    return package_type
        
        # Default to custom_interactive if no specific type detected
        return 'custom_interactive'
    
    def extract_score_universal(self):
        """
        Extract score using the appropriate method for the detected package type
        """
        scoring_method = self.scoring_config.get('scoring_method', 'cmi_score_direct')
        
        try:
            if scoring_method == 'slide_completion':
                return self._extract_rise360_score()
            elif scoring_method == 'interaction_based':
                return self._extract_storyline_score()
            elif scoring_method == 'quiz_assessment':
                return self._extract_quiz_score()
            elif scoring_method == 'experience_statements':
                return self._extract_xapi_score()
            elif scoring_method == 'legacy_tracking':
                return self._extract_aicc_score()
            elif scoring_method == 'objective_based':
                return self._extract_scorm2004_score()
            else:
                return self._extract_generic_score()
                
        except Exception as e:
            logger.error(f"❌ Universal Handler: Error extracting score for type {self.detected_type}: {str(e)}")
            return None
    
    def _extract_rise360_score(self):
        """Extract score from Articulate Rise 360 packages (slide-based)"""
        logger.info("📱 Extracting Rise 360 score (slide-based)")
        
        # Method 1: Check progress percentage
        if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
            return float(self.attempt.progress_percentage)
        
        # Method 2: Check slide completion
        if self.attempt.completed_slides and self.attempt.total_slides:
            try:
                completed_count = len(self.attempt.completed_slides) if isinstance(self.attempt.completed_slides, list) else 0
                if completed_count > 0 and self.attempt.total_slides > 0:
                    return (completed_count / self.attempt.total_slides) * 100
            except:
                pass
        
        # Method 3: Check CMI data for completion
        if self.attempt.cmi_data:
            completion_status = self.attempt.cmi_data.get('cmi.core.lesson_status') or self.attempt.cmi_data.get('cmi.completion_status')
            if completion_status in ['completed', 'passed']:
                return 100.0  # Rise 360 often doesn't have numeric scores, just completion
        
        return None
    
    def _extract_storyline_score(self):
        """Extract score from Articulate Storyline packages (interaction-based)"""
        logger.info("🎮 Extracting Storyline score (interaction-based)")
        
        # Method 1: Direct CMI score
        if self.attempt.cmi_data:
            score_raw = self.attempt.cmi_data.get('cmi.core.score.raw') or self.attempt.cmi_data.get('cmi.score.raw')
            if score_raw and str(score_raw).strip():
                try:
                    return float(score_raw)
                except:
                    pass
        
        # Method 2: Analyze suspend data for Storyline patterns
        if self.attempt.suspend_data:
            return self._extract_storyline_suspend_score()
        
        # Method 3: Check interactions
        interactions = self.attempt.interactions.all()
        if interactions.exists():
            total_score = 0
            total_weight = 0
            for interaction in interactions:
                if interaction.score_raw and interaction.weighting:
                    total_score += float(interaction.score_raw) * float(interaction.weighting)
                    total_weight += float(interaction.weighting)
            
            if total_weight > 0:
                return (total_score / total_weight)
        
        return None
    
    def _extract_storyline_suspend_score(self):
        """Extract score from Storyline suspend data"""
        try:
            # Try to decode JSON suspend data
            suspend_json = json.loads(self.attempt.suspend_data)
            
            if 'd' in suspend_json and isinstance(suspend_json['d'], list):
                # Decode Storyline compressed format
                decoded = ''.join([chr(x) for x in suspend_json['d'] if x < 256])
                
                # Look for score patterns in decoded data
                score_patterns = [
                    r'scors(\d+)',                    # scors88
                    r'scor"(\d+)',                   # scor"88
                    r'"score":\s*(\d+)',             # "score": 88
                    r'quiz_score["\s:]*(\d+)',       # quiz_score: 88
                    r'final_score["\s:]*(\d+)',      # final_score: 88
                ]
                
                for pattern in score_patterns:
                    match = re.search(pattern, decoded, re.IGNORECASE)
                    if match:
                        score = float(match.group(1))
                        if 0 <= score <= 100:
                            logger.info(f"📊 Storyline: Found score {score} using pattern {pattern}")
                            return score
                
                # Check for completion with empty score (often means 100%)
                completion_patterns = [
                    r'qd"true',                      # Quiz done = true
                    r'"qd"true',                     # Quiz done = true
                    r'quiz_done.*true',              # quiz_done: true
                    r'assessment_complete.*true',    # assessment_complete: true
                ]
                
                for pattern in completion_patterns:
                    if re.search(pattern, decoded, re.IGNORECASE):
                        # Check if score field is empty (indicates 100%)
                        if 'scor"' in decoded and not re.search(r'scor"(\d+)', decoded):
                            logger.info("📊 Storyline: Quiz complete with empty score - assuming 100%")
                            return 100.0
        
        except Exception as e:
            logger.warning(f"Storyline suspend data analysis failed: {str(e)}")
        
        return None
    
    def _extract_quiz_score(self):
        """Extract score from quiz/assessment packages"""
        logger.info("🎯 Extracting quiz/assessment score")
        
        # Method 1: Direct CMI score
        if self.attempt.cmi_data:
            score_raw = self.attempt.cmi_data.get('cmi.core.score.raw') or self.attempt.cmi_data.get('cmi.score.raw')
            if score_raw and str(score_raw).strip():
                try:
                    return float(score_raw)
                except:
                    pass
        
        # Method 2: Database score field
        if self.attempt.score_raw is not None:
            return float(self.attempt.score_raw)
        
        # Method 3: Calculate from interactions
        interactions = self.attempt.interactions.all()
        if interactions.exists():
            correct_count = 0
            total_count = 0
            
            for interaction in interactions:
                total_count += 1
                if interaction.result == 'correct':
                    correct_count += 1
            
            if total_count > 0:
                return (correct_count / total_count) * 100
        
        return None
    
    def _extract_xapi_score(self):
        """Extract score from xAPI/Tin Can packages"""
        logger.info("🌐 Extracting xAPI score")
        
        # xAPI packages often don't have traditional scores
        # Check for completion and experience-based metrics
        
        if self.attempt.cmi_data:
            # Check for xAPI-specific data
            completion_status = self.attempt.cmi_data.get('cmi.completion_status')
            success_status = self.attempt.cmi_data.get('cmi.success_status')
            
            if success_status == 'passed':
                return 100.0
            elif completion_status == 'completed':
                return 80.0  # Default score for completion
        
        return None
    
    def _extract_aicc_score(self):
        """Extract score from AICC/Legacy packages"""
        logger.info("📼 Extracting AICC/Legacy score")
        
        # AICC packages use different data model
        if self.attempt.cmi_data:
            # Check AICC-specific fields
            score = self.attempt.cmi_data.get('cmi.core.score.raw')
            if score:
                try:
                    return float(score)
                except:
                    pass
        
        # Default completion score
        if self.attempt.lesson_status in ['completed', 'passed']:
            return 100.0
        
        return None
    
    def _extract_scorm2004_score(self):
        """Extract score from SCORM 2004 packages"""
        logger.info("🎯 Extracting SCORM 2004 score")
        
        # SCORM 2004 uses different data model
        if self.attempt.cmi_data:
            # Check SCORM 2004 score fields
            score_raw = self.attempt.cmi_data.get('cmi.score.raw')
            score_scaled = self.attempt.cmi_data.get('cmi.score.scaled')
            
            if score_raw:
                try:
                    return float(score_raw)
                except:
                    pass
            
            if score_scaled:
                try:
                    # Convert scaled score (0-1) to percentage
                    return float(score_scaled) * 100
                except:
                    pass
        
        # Check objectives
        objectives = self.attempt.objectives.all()
        if objectives.exists():
            passed_objectives = objectives.filter(success_status='passed').count()
            total_objectives = objectives.count()
            
            if total_objectives > 0:
                return (passed_objectives / total_objectives) * 100
        
        return None
    
    def _extract_generic_score(self):
        """Generic score extraction for unknown package types"""
        logger.info("❓ Extracting generic score")
        
        # Try all common methods
        methods = [
            lambda: float(self.attempt.score_raw) if self.attempt.score_raw else None,
            lambda: float(self.attempt.cmi_data.get('cmi.core.score.raw', 0)) if self.attempt.cmi_data.get('cmi.core.score.raw') else None,
            lambda: float(self.attempt.cmi_data.get('cmi.score.raw', 0)) if self.attempt.cmi_data.get('cmi.score.raw') else None,
            lambda: float(self.attempt.progress_percentage) if self.attempt.progress_percentage else None,
        ]
        
        for method in methods:
            try:
                score = method()
                if score is not None and score >= 0:
                    return score
            except:
                continue
        
        return None
    
    def process_and_update_score(self):
        """
        Process the attempt and update score using universal handler
        """
        try:
            with transaction.atomic():
                logger.info(f"🔄 Universal Handler: Processing {self.detected_type} package (ID: {self.package.id})")
                
                # Extract score using appropriate method
                extracted_score = self.extract_score_universal()
                
                if extracted_score is not None:
                    logger.info(f"✅ Universal Handler: Extracted score {extracted_score} for {self.detected_type} package")
                    
                    # Update attempt with extracted score
                    old_score = self.attempt.score_raw
                    self.attempt.score_raw = Decimal(str(extracted_score))
                    
                    # Update lesson status based on score
                    mastery_score = self.package.mastery_score or 70
                    if extracted_score >= mastery_score:
                        self.attempt.lesson_status = 'passed'
                    else:
                        self.attempt.lesson_status = 'failed'
                    
                    # Set completion timestamp
                    if not self.attempt.completed_at:
                        self.attempt.completed_at = timezone.now()
                    
                    # Save to database
                    self.attempt.save()
                    
                    # Update TopicProgress
                    self._update_topic_progress(extracted_score)
                    
                    logger.info(f"🎉 Universal Handler: Successfully updated score {old_score} -> {extracted_score} for {self.detected_type}")
                    return True
                else:
                    logger.warning(f"⚠️ Universal Handler: No score found for {self.detected_type} package")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Universal Handler: Error processing {self.detected_type} package: {str(e)}")
            return False
    
    def _update_topic_progress(self, score_value):
        """Update TopicProgress with the extracted score"""
        try:
            from courses.models import TopicProgress
            
            progress, created = TopicProgress.objects.get_or_create(
                user=self.attempt.user,
                topic=self.package.topic,
                defaults={'attempts': 0}
            )
            
            # Update scores
            progress.last_score = float(score_value)
            if progress.best_score is None or float(score_value) > progress.best_score:
                progress.best_score = float(score_value)
            
            # Mark as completed
            if not progress.completed:
                progress.completed = True
                progress.completion_method = f'scorm_{self.detected_type}'
                progress.completed_at = timezone.now()
            
            # Update progress data
            progress.progress_data = {
                'scorm_package_type': self.detected_type,
                'scoring_method': self.scoring_config.get('scoring_method'),
                'universal_handler': True,
                'sync_timestamp': timezone.now().isoformat(),
            }
            
            progress.save()
            logger.info(f"📈 Universal Handler: Updated TopicProgress for {self.detected_type}")
            
        except Exception as e:
            logger.error(f"❌ Universal Handler: Error updating TopicProgress: {str(e)}")


def process_scorm_with_universal_handler(attempt):
    """
    Main entry point for universal SCORM processing
    """
    handler = UniversalScormHandler(attempt.scorm_package, attempt)
    return handler.process_and_update_score()
