"""
SCORM CMI Data Validator
Ensures all SCORM data comes from proper CMI fields and follows SCORM standards
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class CMIValidator:
    """
    Validates SCORM CMI data to ensure compliance with SCORM standards
    """
    
    # Valid SCORM 1.2 CMI fields - Complete set
    SCORM_12_VALID_FIELDS = {
        # Core fields
        'cmi.core.student_id',
        'cmi.core.student_name', 
        'cmi.core.lesson_location',
        'cmi.core.credit',
        'cmi.core.lesson_status',
        'cmi.core.entry',
        'cmi.core.score.raw',
        'cmi.core.score.max',
        'cmi.core.score.min',
        'cmi.core.total_time',
        'cmi.core.lesson_mode',
        'cmi.core.exit',
        'cmi.core.session_time',
        'cmi.suspend_data',
        'cmi.launch_data',
        'cmi.comments',
        'cmi.comments_from_lms',
        
        # Student data fields
        'cmi.student_data.mastery_score',
        'cmi.student_data.max_time_allowed',
        'cmi.student_data.time_limit_action',
        
        # Student preference fields
        'cmi.student_preference.audio',
        'cmi.student_preference.language',
        'cmi.student_preference.speed',
        'cmi.student_preference.text',
        
        # Objectives fields
        'cmi.objectives._count',
        'cmi.objectives.n.id',
        'cmi.objectives.n.score.raw',
        'cmi.objectives.n.score.max',
        'cmi.objectives.n.score.min',
        'cmi.objectives.n.status',
        
        # Interactions fields
        'cmi.interactions._count',
        'cmi.interactions.n.id',
        'cmi.interactions.n.objectives._count',
        'cmi.interactions.n.objectives.m.id',
        'cmi.interactions.n.time',
        'cmi.interactions.n.type',
        'cmi.interactions.n.correct_responses._count',
        'cmi.interactions.n.correct_responses.m.pattern',
        'cmi.interactions.n.weighting',
        'cmi.interactions.n.student_response',
        'cmi.interactions.n.result',
        'cmi.interactions.n.latency',
    }
    
    # Valid SCORM 2004 CMI fields - Complete set
    SCORM_2004_VALID_FIELDS = {
        # Core fields
        'cmi.learner_id',
        'cmi.learner_name',
        'cmi.location',
        'cmi.completion_status',
        'cmi.success_status',
        'cmi.entry',
        'cmi.exit',
        'cmi.credit',
        'cmi.mode',
        'cmi.progress_measure',
        'cmi.score.raw',
        'cmi.score.min',
        'cmi.score.max',
        'cmi.score.scaled',
        'cmi.total_time',
        'cmi.session_time',
        'cmi.suspend_data',
        'cmi.launch_data',
        'cmi.max_time_allowed',
        'cmi.time_limit_action',
        
        # Comments from learner fields
        'cmi.comments_from_learner._count',
        'cmi.comments_from_learner.n.comment',
        'cmi.comments_from_learner.n.location',
        'cmi.comments_from_learner.n.timestamp',
        
        # Comments from LMS fields
        'cmi.comments_from_lms._count',
        'cmi.comments_from_lms.n.comment',
        'cmi.comments_from_lms.n.location',
        'cmi.comments_from_lms.n.timestamp',
        
        # Objectives fields
        'cmi.objectives._count',
        'cmi.objectives.n.id',
        'cmi.objectives.n.score.raw',
        'cmi.objectives.n.score.min',
        'cmi.objectives.n.score.max',
        'cmi.objectives.n.score.scaled',
        'cmi.objectives.n.progress_measure',
        'cmi.objectives.n.success_status',
        'cmi.objectives.n.completion_status',
        
        # Interactions fields
        'cmi.interactions._count',
        'cmi.interactions.n.id',
        'cmi.interactions.n.type',
        'cmi.interactions.n.timestamp',
        'cmi.interactions.n.weighting',
        'cmi.interactions.n.learner_response',
        'cmi.interactions.n.correct_responses._count',
        'cmi.interactions.n.correct_responses.m.pattern',
        'cmi.interactions.n.result',
        'cmi.interactions.n.latency',
        'cmi.interactions.n.description',
        'cmi.interactions.n.objectives._count',
        'cmi.interactions.n.objectives.m.id',
    }
    
    @classmethod
    def validate_cmi_data(cls, cmi_data: Dict[str, Any], scorm_version: str = '1.2') -> Dict[str, Any]:
        """
        Validate CMI data to ensure it contains only valid SCORM fields
        
        Args:
            cmi_data: Dictionary containing CMI data
            scorm_version: SCORM version ('1.2' or '2004')
            
        Returns:
            Dict containing validation results
        """
        validation_result = {
            'is_valid': True,
            'invalid_fields': [],
            'warnings': [],
            'valid_fields': [],
            'score_fields': [],
            'completion_fields': []
        }
        
        if not cmi_data:
            validation_result['warnings'].append('No CMI data provided')
            return validation_result
        
        valid_fields = cls.SCORM_12_VALID_FIELDS if scorm_version == '1.2' else cls.SCORM_2004_VALID_FIELDS
        
        for field, value in cmi_data.items():
            if field in valid_fields:
                validation_result['valid_fields'].append(field)
                
                # Track score-related fields
                if 'score' in field.lower():
                    validation_result['score_fields'].append(field)
                
                # Track completion-related fields
                if any(keyword in field.lower() for keyword in ['completion', 'status', 'success']):
                    validation_result['completion_fields'].append(field)
            else:
                validation_result['invalid_fields'].append(field)
                validation_result['is_valid'] = False
                logger.warning(f"Invalid CMI field detected: {field}")
        
        # Check for required fields
        required_fields = cls._get_required_fields(scorm_version)
        missing_required = []
        for field in required_fields:
            if field not in cmi_data:
                missing_required.append(field)
        
        if missing_required:
            validation_result['warnings'].append(f"Missing required CMI fields: {missing_required}")
        
        return validation_result
    
    @classmethod
    def _get_required_fields(cls, scorm_version: str) -> List[str]:
        """Get required CMI fields for SCORM version"""
        if scorm_version == '1.2':
            return [
                'cmi.core.student_id',
                'cmi.core.student_name',
                'cmi.core.lesson_status',
                'cmi.core.entry'
            ]
        else:  # SCORM 2004
            return [
                'cmi.learner_id',
                'cmi.learner_name',
                'cmi.completion_status',
                'cmi.success_status',
                'cmi.entry'
            ]
    
    @classmethod
    def extract_score_from_cmi(cls, cmi_data: Dict[str, Any], scorm_version: str = '1.2') -> Optional[float]:
        """
        Extract score from CMI data using only valid SCORM fields
        
        Args:
            cmi_data: Dictionary containing CMI data
            scorm_version: SCORM version ('1.2' or '2004')
            
        Returns:
            Score value or None if no valid score found
        """
        scores = []
        
        if scorm_version == '1.2':
            # SCORM 1.2 score fields
            score_fields = [
                'cmi.core.score.raw',
                'cmi.core.score.scaled',
                'cmi.objectives.n.score.raw',
                'cmi.objectives.n.score.scaled'
            ]
        else:
            # SCORM 2004 score fields
            score_fields = [
                'cmi.score.raw',
                'cmi.score.scaled',
                'cmi.objectives.n.score.raw',
                'cmi.objectives.n.score.scaled',
                'cmi.interactions.n.objectives.n.score.raw',
                'cmi.interactions.n.objectives.n.score.scaled'
            ]
        
        for field in score_fields:
            if field in cmi_data and cmi_data[field] is not None:
                try:
                    score_value = float(cmi_data[field])
                    
                    # Handle scaled scores (0-1 to 0-100)
                    if 'scaled' in field and 0 <= score_value <= 1:
                        score_value = score_value * 100
                    
                    if 0 <= score_value <= 100:
                        scores.append(score_value)
                        logger.info(f"CMI Validator: Found valid score {score_value} in field {field}")
                except (ValueError, TypeError):
                    logger.warning(f"CMI Validator: Invalid score value in field {field}: {cmi_data[field]}")
        
        return max(scores) if scores else None
    
    @classmethod
    def extract_completion_status_from_cmi(cls, cmi_data: Dict[str, Any], scorm_version: str = '1.2') -> Dict[str, str]:
        """
        Extract completion status from CMI data using only valid SCORM fields
        
        Args:
            cmi_data: Dictionary containing CMI data
            scorm_version: SCORM version ('1.2' or '2004')
            
        Returns:
            Dictionary with completion status information
        """
        status = {
            'completion_status': None,
            'success_status': None,
            'lesson_status': None
        }
        
        if scorm_version == '1.2':
            # SCORM 1.2 completion fields
            if 'cmi.core.lesson_status' in cmi_data:
                status['lesson_status'] = cmi_data['cmi.core.lesson_status']
            
            if 'cmi.core.credit' in cmi_data:
                status['completion_status'] = cmi_data['cmi.core.credit']
        else:
            # SCORM 2004 completion fields
            if 'cmi.completion_status' in cmi_data:
                status['completion_status'] = cmi_data['cmi.completion_status']
            
            if 'cmi.success_status' in cmi_data:
                status['success_status'] = cmi_data['cmi.success_status']
        
        return status
    
    @classmethod
    def validate_score_integrity(cls, attempt) -> bool:
        """
        Validate that attempt scores come from CMI data only
        
        Args:
            attempt: ScormAttempt instance
            
        Returns:
            True if score integrity is maintained, False otherwise
        """
        # Check if score_raw matches CMI data
        cmi_score = cls.extract_score_from_cmi(attempt.cmi_data, attempt.scorm_package.version)
        
        if attempt.score_raw is not None and cmi_score is not None:
            # Allow small floating point differences
            if abs(float(attempt.score_raw) - cmi_score) > 0.01:
                logger.error(f"Score integrity violation: attempt.score_raw={attempt.score_raw} != CMI score={cmi_score}")
                return False
        
        return True
    
    @classmethod
    def log_cmi_compliance_report(cls, attempt) -> None:
        """
        Log a comprehensive CMI compliance report for an attempt
        
        Args:
            attempt: ScormAttempt instance
        """
        validation = cls.validate_cmi_data(attempt.cmi_data, attempt.scorm_package.version)
        
        logger.info(f"CMI Compliance Report for Attempt {attempt.id}:")
        logger.info(f"  Valid: {validation['is_valid']}")
        logger.info(f"  Valid fields: {len(validation['valid_fields'])}")
        logger.info(f"  Invalid fields: {validation['invalid_fields']}")
        logger.info(f"  Score fields: {validation['score_fields']}")
        logger.info(f"  Completion fields: {validation['completion_fields']}")
        
        if validation['warnings']:
            logger.warning(f"  Warnings: {validation['warnings']}")
        
        # Check score integrity
        if not cls.validate_score_integrity(attempt):
            logger.error(f"  SCORE INTEGRITY VIOLATION detected!")
    
    @classmethod
    def validate_xapi_event(cls, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate xAPI event data structure
        
        Args:
            event_data: Dictionary containing xAPI event data
            
        Returns:
            Dict containing validation results
        """
        validation_result = {
            'is_valid': True,
            'missing_fields': [],
            'invalid_fields': [],
            'warnings': []
        }
        
        # Required xAPI fields
        required_fields = ['actor', 'verb', 'object']
        for field in required_fields:
            if field not in event_data:
                validation_result['missing_fields'].append(field)
                validation_result['is_valid'] = False
        
        # Validate actor structure
        if 'actor' in event_data:
            actor = event_data['actor']
            if not isinstance(actor, dict):
                validation_result['invalid_fields'].append('actor')
                validation_result['is_valid'] = False
            elif 'name' not in actor and 'mbox' not in actor:
                validation_result['warnings'].append('Actor missing name or mbox')
        
        # Validate verb structure
        if 'verb' in event_data:
            verb = event_data['verb']
            if not isinstance(verb, dict):
                validation_result['invalid_fields'].append('verb')
                validation_result['is_valid'] = False
            elif 'id' not in verb:
                validation_result['warnings'].append('Verb missing id')
        
        # Validate object structure
        if 'object' in event_data:
            obj = event_data['object']
            if not isinstance(obj, dict):
                validation_result['invalid_fields'].append('object')
                validation_result['is_valid'] = False
            elif 'id' not in obj:
                validation_result['warnings'].append('Object missing id')
        
        return validation_result
    
    @classmethod
    def extract_xapi_score(cls, event_data: Dict[str, Any]) -> Optional[float]:
        """
        Extract score from xAPI event data
        
        Args:
            event_data: Dictionary containing xAPI event data
            
        Returns:
            Score value or None if no valid score found
        """
        if 'result' not in event_data:
            return None
        
        result = event_data['result']
        if not isinstance(result, dict):
            return None
        
        if 'score' in result:
            score = result['score']
            if isinstance(score, dict):
                # Try raw score first
                if 'raw' in score and score['raw'] is not None:
                    try:
                        return float(score['raw'])
                    except (ValueError, TypeError):
                        pass
                
                # Try scaled score
                if 'scaled' in score and score['scaled'] is not None:
                    try:
                        scaled_score = float(score['scaled'])
                        # Convert scaled score (0-1) to percentage (0-100)
                        if 0 <= scaled_score <= 1:
                            return scaled_score * 100
                    except (ValueError, TypeError):
                        pass
        
        return None
    
    @classmethod
    def extract_xapi_completion_status(cls, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract completion status from xAPI event data
        
        Args:
            event_data: Dictionary containing xAPI event data
            
        Returns:
            Dictionary with completion status information
        """
        status = {
            'completion': None,
            'success': None,
            'verb': None
        }
        
        if 'result' in event_data:
            result = event_data['result']
            if isinstance(result, dict):
                status['completion'] = result.get('completion')
                status['success'] = result.get('success')
        
        if 'verb' in event_data:
            verb = event_data['verb']
            if isinstance(verb, dict):
                status['verb'] = verb.get('id')
        
        return status
